"""Event processing pipeline.

Responsible for:
1. Idempotency — dedup by razorpay_event_id
2. Normalization — raw → RevenueEvent
3. Customer upsert — find-or-create
4. Recovery state management — with out-of-order handling
5. Audit logging — every decision is recorded with a reason
6. Full Recovery Pipeline — diagnosis → policy → dispatch (P0-1)
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reclaim.db.models import (
    AuditLog,
    Customer,
    Event,
    EventType,
    ProcessingStatus,
    RecoveryMemory,
    RecoveryState,
    RecoveryStateEnum,
)
from reclaim.ingestion.normalizer import (
    NORMALIZER_DISPATCH,
    SYNTHETIC_EVENTS,
    EventCategory,
    normalize_synthetic,
    razorpay_event_to_internal,
)
from reclaim.common.money import format_audit_case_reason
from reclaim.ingestion.schemas import RevenueEvent

logger = logging.getLogger(__name__)


async def process_webhook_event(
    db: AsyncSession,
    raw_payload: dict,
    razorpay_event_id: str,
    event_type_str: str,
) -> None:
    """Main processing pipeline for a single webhook event.

    This function is called from a BackgroundTask so the webhook endpoint
    can return 200 immediately.

    Pipeline stages (all run in the same background task):
      1. Idempotency check
      2. Parse event type
      3. Upsert customer
      4. Normalize event
      5. Insert event row
      6. Recovery state management (with out-of-order handling)
      7. *** FULL RECOVERY LOOP (P0-1) ***
         For payment_failed events — runs synchronously within the background task:
           a. FailureClassifier.classify() → DiagnosisOutput (LLM + heuristic fallback)
           b. evaluate_policy_with_db_context() → PolicyVerdict (deterministic rules engine)
              - Fetches live RecoveryMemory from DB so fatigue/preferred_channel are real, not defaults
           c. dispatch_recovery_action() → executes or blocks the recovery action
         For payment_captured / order_paid events — calls handle_outcome_transition()
         to update RecoveryMemory with the successful outcome.

    CONSTRAINT: The LLM may ONLY diagnose/classify. All financial/contact decisions
    flow exclusively through the deterministic policy engine (rules.py). The LLM
    output is treated as untrusted input to that engine only.

    Args:
        db: Async database session.
        raw_payload: The full raw webhook body as a dict.
        razorpay_event_id: The unique event identifier for idempotency.
        event_type_str: Internal event type string (e.g. "payment_failed").
    """

    # -----------------------------------------------------------------
    # 1. Idempotency check
    # -----------------------------------------------------------------
    existing = await db.execute(
        select(Event).where(Event.razorpay_event_id == razorpay_event_id)
    )
    existing_event = existing.scalar_one_or_none()

    if existing_event is not None:
        # Already seen — mark as duplicate and bail
        if existing_event.processing_status != ProcessingStatus.ignored_duplicate:
            existing_event.processing_status = ProcessingStatus.ignored_duplicate
            await db.commit()
        logger.info(f"Duplicate event ignored: {razorpay_event_id}")
        return

    # -----------------------------------------------------------------
    # 2. Parse event type
    # -----------------------------------------------------------------
    try:
        event_type = EventType(event_type_str)
    except ValueError:
        logger.warning(f"Unknown event type: {event_type_str}")
        return

    # -----------------------------------------------------------------
    # 3. Upsert customer
    # -----------------------------------------------------------------
    customer = await _upsert_customer(db, raw_payload)

    # -----------------------------------------------------------------
    # 4. Normalize the event
    # -----------------------------------------------------------------
    normalized = _normalize_event(
        raw_payload=raw_payload,
        event_type_str=event_type_str,
        customer_id=str(customer.id),
        razorpay_event_id=razorpay_event_id,
    )

    # -----------------------------------------------------------------
    # 5. Insert event row
    # -----------------------------------------------------------------
    event = Event(
        razorpay_event_id=razorpay_event_id,
        event_type=event_type,
        raw_payload=raw_payload,
        normalized_payload=normalized.model_dump(mode="json") if normalized else None,
        received_at=datetime.now(timezone.utc),
        processed_at=datetime.now(timezone.utc),
        processing_status=ProcessingStatus.processed,
    )
    db.add(event)
    await db.flush()  # get the event.id

    # -----------------------------------------------------------------
    # 6. Recovery state management (with out-of-order handling)
    # -----------------------------------------------------------------
    recovery_state = await _manage_recovery_state(
        db=db,
        event=event,
        customer=customer,
        normalized=normalized,
        event_type=event_type,
    )

    # -----------------------------------------------------------------
    # 7. Full Recovery Pipeline (P0-1)
    #
    # Runs AFTER state management so we always have a RecoveryState to
    # attach audit logs to.  Never crashes the webhook — all failures
    # are caught, logged, and reflected in the audit trail.
    # -----------------------------------------------------------------
    if recovery_state is not None:
        if event_type == EventType.payment_failed or event_type in (
            EventType.checkout_abandoned,
            EventType.invoice_overdue,
            EventType.subscription_halted,
        ):
            # Only invoke for freshly-created recovery states (state == failed).
            # Out-of-order duplicates return None from _manage_recovery_state.
            if recovery_state.state == RecoveryStateEnum.failed:
                await _invoke_recovery_pipeline(
                    db=db,
                    event=event,
                    customer=customer,
                    recovery_state=recovery_state,
                    normalized=normalized,
                )

        elif event_type in (
            EventType.payment_captured,
            EventType.order_paid,
            EventType.payment_link_paid,
        ):
            # Payment succeeded → update RecoveryMemory with outcome
            if recovery_state.state == RecoveryStateEnum.recovered:
                await _invoke_outcome_observer(db=db, recovery_state=recovery_state)

    await db.commit()
    logger.info(f"Processed event: {razorpay_event_id} ({event_type_str})")


# ---------------------------------------------------------------------------
# Recovery Pipeline Invocation (P0-1 — full loop wiring)
# ---------------------------------------------------------------------------

async def _invoke_recovery_pipeline(
    db: AsyncSession,
    event: Event,
    customer: Customer,
    recovery_state: RecoveryState,
    normalized: RevenueEvent | None,
) -> None:
    """Invoke the full diagnosis → policy → dispatch pipeline for a failure event.

    CONSTRAINT: The LLM may ONLY diagnose/classify — it NEVER authorizes money
    movement, discounts, or contact actions directly.  All financial/contact
    decisions flow exclusively through the deterministic policy engine (rules.py).

    If the LLM call fails (no API key, rate limit, etc.), we fall back to the
    deterministic heuristic_classify() so the pipeline always completes.
    """
    from reclaim.diagnosis.classifier import FailureClassifier, heuristic_classify
    from reclaim.diagnosis.schemas import DiagnosisValidationError
    from reclaim.orchestrator.executors.dispatcher import (
        evaluate_policy_with_db_context,
        dispatch_recovery_action,
    )

    try:
        # ------------------------------------------------------------------
        # Step A: Diagnosis — LLM classification with heuristic fallback.
        # The LLM output is UNTRUSTED INPUT to the policy engine only.
        # ------------------------------------------------------------------
        diagnosis_output = None
        diagnosed_cause = "INSUFFICIENT_FUNDS"  # safe default

        if normalized is not None:
            if os.environ.get("RECLAIM_FORCE_HEURISTIC_DIAGNOSIS") == "1":
                diagnosis_output = heuristic_classify(normalized)
                diagnosed_cause = diagnosis_output.cause
            else:
                try:
                    classifier = FailureClassifier()
                    diagnosis_output = classifier.classify(normalized)
                    diagnosed_cause = diagnosis_output.cause
                    logger.info(
                        f"[Pipeline] event={event.razorpay_event_id} "
                        f"diagnosed_cause={diagnosed_cause} "
                        f"confidence={diagnosis_output.confidence:.3f}"
                    )
                except DiagnosisValidationError as diag_err:
                    # LLM unavailable or returned bad output — use heuristic
                    logger.warning(
                        f"[Pipeline] LLM diagnosis failed for {event.razorpay_event_id}, "
                        f"using heuristic fallback. Reason: {diag_err}"
                    )
                    diagnosis_output = heuristic_classify(normalized)
                    diagnosed_cause = diagnosis_output.cause
                except Exception as diag_exc:
                    logger.error(
                        f"[Pipeline] Unexpected error during diagnosis for "
                        f"{event.razorpay_event_id}: {diag_exc}. Using heuristic."
                    )
                    if normalized:
                        diagnosis_output = heuristic_classify(normalized)
                        diagnosed_cause = diagnosis_output.cause

        # Audit the diagnosis result
        await _audit(
            db=db,
            event=event,
            recovery_state=recovery_state,
            actor="diagnosis_engine",
            action=f"diagnosed:{diagnosed_cause}",
            reason=(
                f"Diagnosis: {diagnosed_cause} "
                f"(confidence={getattr(diagnosis_output, 'confidence', 0.0):.3f}, "
                f"source={'llm' if diagnosis_output else 'default'})"
            ),
            metadata={
                "diagnosed_cause": diagnosed_cause,
                "confidence": getattr(diagnosis_output, "confidence", 0.0),
            },
        )

        # ------------------------------------------------------------------
        # Step B: Policy Evaluation — fully deterministic rules engine.
        # Fetches real RecoveryMemory from DB so fatigue/preferred_channel
        # reflect actual customer history (not silent zero-defaults). (P1-7)
        # ------------------------------------------------------------------
        verdict = await evaluate_policy_with_db_context(
            db=db,
            customer=customer,
            recovery_state=recovery_state,
            diagnosis_cause=diagnosed_cause,
            diagnosis_output=diagnosis_output,
            event=event,
        )

        logger.info(
            f"[Pipeline] event={event.razorpay_event_id} "
            f"policy_decision={verdict.decision.value} "
            f"channel={verdict.channel}"
        )

        # Audit the policy verdict
        await _audit(
            db=db,
            event=event,
            recovery_state=recovery_state,
            actor="policy_engine",
            action=f"policy_verdict:{verdict.decision.value}",
            reason=verdict.reason,
            metadata={
                "decision": verdict.decision.value,
                "channel": verdict.channel,
                "tier": verdict.tier.value if verdict.tier else None,
                "max_discount_paise": verdict.max_discount_paise,
            },
        )

        # ------------------------------------------------------------------
        # Step C: Dispatch — executes ACT/WAIT/BLOCK per policy verdict.
        # LLM output never reaches this function — only the PolicyVerdict
        # produced by the deterministic rules engine does.
        # ------------------------------------------------------------------
        dispatch_result = await dispatch_recovery_action(
            db=db,
            verdict=verdict,
            recovery_state=recovery_state,
            customer=customer,
            event=event,
        )

        logger.info(
            f"[Pipeline] event={event.razorpay_event_id} "
            f"dispatch_result={dispatch_result.get('status')} "
            f"channel={dispatch_result.get('channel', 'none')}"
        )

    except Exception as pipeline_exc:
        # The pipeline must NEVER crash the webhook handler.
        # Log the failure, write it to the audit trail, and continue.
        logger.exception(
            f"[Pipeline] Unhandled error in recovery pipeline for "
            f"event={event.razorpay_event_id}: {pipeline_exc}"
        )
        await _audit(
            db=db,
            event=event,
            recovery_state=recovery_state,
            actor="orchestrator",
            action="pipeline_error",
            reason=f"Recovery pipeline encountered an error: {str(pipeline_exc)[:500]}",
            metadata={"error": str(pipeline_exc)[:500]},
        )


async def _invoke_outcome_observer(
    db: AsyncSession,
    recovery_state: RecoveryState,
) -> None:
    """Update RecoveryMemory when a payment is confirmed recovered.

    Called when payment_captured/order_paid transitions a RecoveryState to 'recovered'.
    Updates historical_response_rate, preferred_channel, avg_response_latency_hours.

    Data provenance: RecoveryMemory fields are populated from historical payment
    event data processed through this pipeline — NOT from LLM inference off a
    single failed event.
    """
    try:
        from reclaim.orchestrator.outcome_observer import handle_outcome_transition
        await handle_outcome_transition(db=db, recovery_state=recovery_state)
        logger.info(
            f"[Pipeline] RecoveryMemory updated for customer "
            f"{recovery_state.customer_id} after successful recovery."
        )
    except Exception as obs_exc:
        logger.error(
            f"[Pipeline] Failed to update RecoveryMemory for "
            f"customer={recovery_state.customer_id}: {obs_exc}"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_event(
    raw_payload: dict,
    event_type_str: str,
    customer_id: str,
    razorpay_event_id: str,
) -> RevenueEvent | None:
    """Route to the correct normalizer and return a RevenueEvent."""
    # Override the event_id in raw for normalizers to use
    raw_with_id = {**raw_payload, "event_id": razorpay_event_id}

    if event_type_str in NORMALIZER_DISPATCH:
        normalizer = NORMALIZER_DISPATCH[event_type_str]
        return normalizer(raw_with_id, customer_id)
    elif event_type_str in SYNTHETIC_EVENTS:
        category = (
            EventCategory.cart_abandonment
            if event_type_str == "checkout_abandoned"
            else EventCategory.invoice_overdue
        )
        return normalize_synthetic(raw_with_id, customer_id, category)
    else:
        # Subscription events, payment_link events — normalize minimally
        return _normalize_generic(raw_with_id, customer_id, event_type_str)


def _normalize_generic(
    raw: dict, customer_id: str, event_type_str: str
) -> RevenueEvent:
    """Minimal normalizer for event types without a dedicated handler."""
    payment = raw.get("payload", {}).get("payment", {}).get("entity", {})
    amount = payment.get("amount", 0)

    return RevenueEvent(
        event_id=raw.get("event_id", ""),
        event_category=EventCategory.payment_failure,
        customer_id=customer_id,
        amount=Decimal(str(amount)),
        currency=payment.get("currency", "INR"),
        failure_reason_raw=None,
        occurred_at=datetime.now(timezone.utc),
        source_metadata={"event_type": event_type_str},
    )


async def _upsert_customer(
    db: AsyncSession, raw_payload: dict
) -> Customer:
    """Find or create a customer from the webhook payload."""
    payment = (
        raw_payload.get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )

    rz_customer_id = payment.get("customer_id")
    email = payment.get("email")
    contact = payment.get("contact")

    # Try to find by Razorpay customer ID first
    if rz_customer_id:
        result = await db.execute(
            select(Customer).where(
                Customer.razorpay_customer_id == rz_customer_id
            )
        )
        customer = result.scalar_one_or_none()
        if customer:
            return customer

    # Try by email
    if email:
        result = await db.execute(
            select(Customer).where(Customer.email == email)
        )
        customer = result.scalar_one_or_none()
        if customer:
            # Backfill razorpay_customer_id if we just learned it
            if rz_customer_id and not customer.razorpay_customer_id:
                customer.razorpay_customer_id = rz_customer_id
            return customer

    # Create new customer
    customer = Customer(
        razorpay_customer_id=rz_customer_id,
        email=email,
        phone=contact,
        created_at=datetime.now(timezone.utc),
    )
    db.add(customer)
    await db.flush()
    return customer


def _get_order_id(raw_payload: dict) -> str | None:
    """Extract the order_id from a Razorpay webhook payload."""
    payment = (
        raw_payload.get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )
    order_id = payment.get("order_id")
    if not order_id:
        order = (
            raw_payload.get("payload", {})
            .get("order", {})
            .get("entity", {})
        )
        order_id = order.get("id")
    return order_id


async def _find_existing_recovery_by_order(
    db: AsyncSession, order_id: str, customer: Customer
) -> RecoveryState | None:
    """Find an existing recovery_state for the same order_id and customer."""
    if not order_id:
        return None

    result = await db.execute(
        select(RecoveryState, Event)
        .join(Event, RecoveryState.event_id == Event.id)
        .where(RecoveryState.customer_id == customer.id)
        .order_by(RecoveryState.updated_at.desc())
    )
    rows = result.all()
    for rs, evt in rows:
        if _get_order_id(evt.raw_payload) == order_id:
            return rs
    return None


async def _manage_recovery_state(
    db: AsyncSession,
    event: Event,
    customer: Customer,
    normalized: RevenueEvent | None,
    event_type: EventType,
) -> RecoveryState | None:
    """Create or update recovery_state with out-of-order event handling.

    Returns the RecoveryState that should be used for the recovery pipeline,
    or None if no pipeline invocation is needed (e.g. duplicate/ignored events).
    """
    amount = normalized.amount if normalized else Decimal("0")
    order_id = _get_order_id(event.raw_payload)

    # Find existing recovery state for the same order
    existing = await _find_existing_recovery_by_order(db, order_id, customer) if order_id else None

    # --- Out-of-order handling ---

    if event_type in (
        EventType.payment_captured,
        EventType.order_paid,
        EventType.payment_link_paid,
    ):
        # SUCCESS event arrived
        if existing and existing.state in (
            RecoveryStateEnum.failed,
            RecoveryStateEnum.waiting,
            RecoveryStateEnum.nudged,
            RecoveryStateEnum.promised,
        ):
            # Transition to recovered
            old_state = existing.state.value
            existing.state = RecoveryStateEnum.recovered
            existing.updated_at = datetime.now(timezone.utc)

            await _audit(
                db,
                event=event,
                recovery_state=existing,
                actor="system",
                action=f"state_transition: {old_state} → recovered",
                reason=f"Payment captured/order paid/link paid (event {event.razorpay_event_id}), "
                       f"recovering from {old_state} state",
            )
            return existing  # Return so outcome observer can be triggered

        if existing and existing.state == RecoveryStateEnum.recovered:
            # Already recovered — log and ignore
            await _audit(
                db,
                event=event,
                recovery_state=existing,
                actor="system",
                action="duplicate_success_ignored",
                reason="Payment already recovered, ignoring duplicate success event",
            )
            return None  # No pipeline needed

        # No existing recovery state for a success event — nothing to do
        return None

    if event_type == EventType.payment_failed:
        # FAILURE event arrived
        if existing and existing.state == RecoveryStateEnum.recovered:
            # Stale failure after recovery — do NOT reopen
            await _audit(
                db,
                event=event,
                recovery_state=existing,
                actor="system",
                action="stale_failure_ignored",
                reason="stale event ignored, payment already captured",
            )
            return None  # No pipeline needed

        if existing and existing.state in (
            RecoveryStateEnum.failed,
            RecoveryStateEnum.waiting,
            RecoveryStateEnum.nudged,
        ):
            # Already tracking this failure — log duplicate
            await _audit(
                db,
                event=event,
                recovery_state=existing,
                actor="system",
                action="duplicate_failure_noted",
                reason=f"Additional failure event received, state already {existing.state.value}",
            )
            return None  # Don't re-dispatch

    # --- No existing state, or event type needs a new recovery row ---

    if event_type == EventType.payment_failed:
        new_state = RecoveryState(
            customer_id=customer.id,
            event_id=event.id,
            amount=amount,
            state=RecoveryStateEnum.failed,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(new_state)
        await db.flush()

        await _audit(
            db,
            event=event,
            recovery_state=new_state,
            actor="system",
            action="recovery_state_created",
            reason=format_audit_case_reason("Payment failed", amount),
            metadata={"amount_paise": int(amount)},
        )
        return new_state  # Fresh state → pipeline should run
    elif event_type in (
        EventType.checkout_abandoned,
        EventType.invoice_overdue,
        EventType.subscription_halted,
    ):
        new_state = RecoveryState(
            customer_id=customer.id,
            event_id=event.id,
            amount=amount,
            state=RecoveryStateEnum.failed,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(new_state)
        await db.flush()

        await _audit(
            db,
            event=event,
            recovery_state=new_state,
            actor="system",
            action="recovery_state_created",
            reason=format_audit_case_reason(event_type.value, amount),
            metadata={"amount_paise": int(amount)},
        )
        return new_state  # Fresh state → pipeline should run

    return None


async def _audit(
    db: AsyncSession,
    event: Event,
    recovery_state: RecoveryState | None,
    actor: str,
    action: str,
    reason: str,
    metadata: dict | None = None,
) -> None:
    """Write an audit log entry. Reason is always required."""
    log = AuditLog(
        event_id=event.id,
        recovery_state_id=recovery_state.id if recovery_state else None,
        actor=actor,
        action=action,
        reason=reason,
        metadata_=metadata or {},
        created_at=datetime.now(timezone.utc),
    )
    db.add(log)
    await db.flush()

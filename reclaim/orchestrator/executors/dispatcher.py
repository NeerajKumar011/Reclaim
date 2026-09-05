"""Dispatcher — routes PolicyVerdict decisions to the appropriate channel executor.

Handles ALLOW, MODIFY (review queue), and BLOCK policy decision types.
Provides DB-backed live policy context gathering for real production execution.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from reclaim.db.models import (
    AuditLog,
    Customer,
    Event,
    RecoveryMemory,
    RecoveryState,
    RecoveryStateEnum,
    ReviewQueue,
)
from reclaim.diagnosis.classifier import heuristic_classify
from reclaim.diagnosis.evaluate_model import TRAIN_JSONL_PATH
from reclaim.diagnosis.ml_recovery_model import RecoveryMLModel, MODEL_SAVE_PATH, train_and_save_model
from reclaim.diagnosis.schemas import DiagnosisOutput
from reclaim.orchestrator.executors.razorpay_executor import RazorpayExecutor
from reclaim.orchestrator.executors.simulated_executor import SimulatedExecutor
from reclaim.orchestrator.state_machine import transition_state
from reclaim.policy.rules import evaluate as evaluate_policy, CHANNEL_COST_PAISE
from reclaim.policy.verdict import PolicyDecisionEnum, PolicyVerdict

logger = logging.getLogger(__name__)

_LIVE_ML_MODEL: Optional[RecoveryMLModel] = None


def _get_live_ml_model() -> RecoveryMLModel:
    """Lazy-initialize or load the ML recovery model for live DB evaluations."""
    global _LIVE_ML_MODEL
    if _LIVE_ML_MODEL is None:
        model = RecoveryMLModel()
        if not MODEL_SAVE_PATH.exists():
            if TRAIN_JSONL_PATH.exists():
                model = train_and_save_model(TRAIN_JSONL_PATH)
            else:
                model.is_fitted = False
        else:
            model.load()
        _LIVE_ML_MODEL = model
    return _LIVE_ML_MODEL


async def get_live_policy_context(
    db: AsyncSession,
    customer: Customer,
    recovery_state: RecoveryState,
    event: Optional[Event] = None,
    diagnosis_cause: str = "UNKNOWN",
    diagnosis_output: Optional[DiagnosisOutput] = None,
) -> Dict[str, Any]:
    """Query live DB tables (AuditLog, RecoveryState) to build real policy context.

    Computes:
      - contacts_this_week: Count of dispatch audit logs for this customer in past 7 days.
      - hours_since_last_contact: Hours since most recent dispatch audit log for this customer.
      - confidence: Real confidence score from DiagnosisOutput or heuristic fallback.
      - recovery_probability: Real ML recovery prediction for this record via RecoveryMLModel.
      - daily_spend_so_far_paise: Total intervention spend in AuditLog today.
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Contacts this week (past 7 days)
    seven_days_ago = now_utc - timedelta(days=7)
    rs_subq = select(RecoveryState.id).where(RecoveryState.customer_id == customer.id)
    
    cnt_stmt = select(func.count(AuditLog.id)).where(
        AuditLog.recovery_state_id.in_(rs_subq),
        AuditLog.action.like("dispatch:%"),
        AuditLog.created_at >= seven_days_ago,
    )
    cnt_res = await db.execute(cnt_stmt)
    contacts_this_week = cnt_res.scalar() or 0

    # 2. Hours since last contact
    last_stmt = (
        select(AuditLog)
        .where(
            AuditLog.recovery_state_id.in_(rs_subq),
            AuditLog.action.like("dispatch:%"),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    last_res = await db.execute(last_stmt)
    last_audit = last_res.scalar_one_or_none()

    if last_audit and last_audit.created_at:
        last_dt = last_audit.created_at
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        hours_since_last_contact = (now_utc - last_dt).total_seconds() / 3600.0
    else:
        hours_since_last_contact = float("inf")

    # 3. Confidence score
    if diagnosis_output is not None:
        confidence = diagnosis_output.confidence
    else:
        raw_payload = event.raw_payload if event else {}
        diag = heuristic_classify(raw_payload)
        confidence = diag.confidence

    # 4. Recovery probability from RecoveryMLModel.
    # IMPORTANT (P1-6): Use the RAW Razorpay error_code for failure_reason_raw,
    # NOT the AI-diagnosed cause — keeping training/inference feature schemas aligned.
    # The AI diagnosis is stored separately as `diagnosed_cause` (not used by the ML model).
    ml_model = _get_live_ml_model()
    raw_payload = event.raw_payload if event else {}
    raw_error_code = (
        raw_payload.get("payload", {})
        .get("payment", {})
        .get("entity", {})
        .get("error_code")
    )  # Raw Razorpay error code, e.g. "BAD_REQUEST_ERROR"
    record_dict = {
        "amount": int(recovery_state.amount * 100) if recovery_state.amount else 0,
        "event_category": event.event_type.value if event else "payment_failure",
        "failure_reason_raw": raw_error_code,  # raw field, NOT AI diagnosis
        "diagnosed_cause": diagnosis_cause,     # AI/heuristic output as separate feature
        "diagnosis_confidence": diagnosis_output.confidence if diagnosis_output else 0.5,
        "source_metadata": raw_payload.get("source_metadata", {}),
    }
    if ml_model and ml_model.is_fitted:
        recovery_probability = float(ml_model.predict_proba([record_dict])[0])
    else:
        recovery_probability = 0.50

    # 5. Daily spend so far today
    start_of_today = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    spend_stmt = select(AuditLog.action).where(
        AuditLog.action.like("dispatch:%"),
        AuditLog.created_at >= start_of_today,
    )
    spend_res = await db.execute(spend_stmt)
    actions = spend_res.scalars().all()

    daily_spend_so_far_paise = 0
    for act in actions:
        channel_name = act.replace("dispatch:", "")
        daily_spend_so_far_paise += CHANNEL_COST_PAISE.get(channel_name, 25)

    return {
        "contacts_this_week": contacts_this_week,
        "hours_since_last_contact": hours_since_last_contact,
        "confidence": confidence,
        "recovery_probability": recovery_probability,
        "daily_spend_so_far_paise": daily_spend_so_far_paise,
    }


async def evaluate_policy_with_db_context(
    db: AsyncSession,
    customer: Customer,
    recovery_state: RecoveryState,
    diagnosis_cause: str,
    diagnosis_output: Optional[DiagnosisOutput] = None,
    event: Optional[Event] = None,
) -> PolicyVerdict:
    """Evaluate Policy Engine rules using real DB-backed live context parameters.

    Fetches:
      - Live interaction context (contact counts, cooldown, spend) from AuditLog
      - RecoveryMemory for this customer (P1-7) — so fatigue, preferred_channel,
        and historical_response_rate are real customer history, not zero-defaults
    """
    ctx = await get_live_policy_context(
        db=db,
        customer=customer,
        recovery_state=recovery_state,
        event=event,
        diagnosis_cause=diagnosis_cause,
        diagnosis_output=diagnosis_output,
    )
    amount_paise = int(recovery_state.amount * 100) if recovery_state.amount else 0

    # P1-7: Fetch RecoveryMemory from DB so fatigue/preferred_channel are real values.
    # Data provenance: RecoveryMemory is only written by outcome_observer.py from
    # confirmed payment events — NOT inferred by the LLM.
    mem_res = await db.execute(
        select(RecoveryMemory).where(RecoveryMemory.customer_id == customer.id)
    )
    recovery_memory = mem_res.scalar_one_or_none()

    return evaluate_policy(
        diagnosis_cause=diagnosis_cause,
        customer=customer,
        amount_paise=amount_paise,
        confidence=ctx["confidence"],
        contacts_this_week=ctx["contacts_this_week"],
        hours_since_last_contact=ctx["hours_since_last_contact"],
        recovery_probability=ctx["recovery_probability"],
        daily_spend_so_far_paise=ctx["daily_spend_so_far_paise"],
        recovery_memory=recovery_memory,
    )


async def dispatch_recovery_action(
    db: AsyncSession,
    verdict: PolicyVerdict,
    recovery_state: RecoveryState,
    customer: Customer,
    event: Optional[Event] = None,
    razorpay_executor: Optional[RazorpayExecutor] = None,
    simulated_executor: Optional[SimulatedExecutor] = None,
) -> dict:
    """Dispatch recovery action based on PolicyVerdict.

    Returns:
        Dict summarizing execution result (status, channel, dispatch_details).
    """
    rz_exec = razorpay_executor or RazorpayExecutor()
    sim_exec = simulated_executor or SimulatedExecutor()

    # 1. ALLOW Decision
    if verdict.decision == PolicyDecisionEnum.ALLOW:
        if verdict.channel == "razorpay_payment_link":
            amount_paise = int(recovery_state.amount * 100) if recovery_state.amount else 0
            link_info = rz_exec.create_payment_link(
                amount_paise=amount_paise,
                customer=customer,
                description=verdict.reason,
            )

            # Audit log for payment link dispatch
            audit_entry = AuditLog(
                event_id=event.id if event else recovery_state.event_id,
                recovery_state_id=recovery_state.id,
                actor="orchestrator",
                action="dispatch:razorpay_payment_link",
                reason=f"Payment link created: {link_info.get('short_url', link_info.get('id'))}",
                metadata_=link_info,
                created_at=datetime.now(timezone.utc),
            )
            db.add(audit_entry)
            await db.flush()

            # Transition state to nudged
            await transition_state(
                db=db,
                recovery_state=recovery_state,
                target_state=RecoveryStateEnum.nudged,
                reason=f"Dispatched Razorpay payment link: {verdict.reason}",
                actor="orchestrator",
                event=event,
            )

            return {
                "status": "dispatched",
                "decision": "ALLOW",
                "channel": verdict.channel,
                "result": link_info,
            }

        else:
            # Simulated channel (sms, whatsapp, voice_call, human_escalation)
            dispatch_log = await sim_exec.dispatch(
                db=db,
                customer=customer,
                channel=verdict.channel,
                reason=verdict.reason,
                max_discount_paise=verdict.max_discount_paise,
                event=event,
                recovery_state_id=recovery_state.id if recovery_state else None,
            )

            # Transition state to nudged
            await transition_state(
                db=db,
                recovery_state=recovery_state,
                target_state=RecoveryStateEnum.nudged,
                reason=f"Dispatched via simulated channel {verdict.channel}: {verdict.reason}",
                actor="orchestrator",
                event=event,
            )

            return {
                "status": "dispatched",
                "decision": "ALLOW",
                "channel": verdict.channel,
                "dispatch_id": str(dispatch_log.id),
            }

    # 2. MODIFY Decision — Enqueue for Human Review
    elif verdict.decision == PolicyDecisionEnum.MODIFY:
        review_entry = ReviewQueue(
            event_id=event.id if event else recovery_state.event_id,
            customer_id=customer.id,
            reason=verdict.reason,
            created_at=datetime.now(timezone.utc),
            resolved=False,
        )
        db.add(review_entry)
        await db.flush()

        audit_entry = AuditLog(
            event_id=event.id if event else recovery_state.event_id,
            recovery_state_id=recovery_state.id,
            actor="orchestrator",
            action="review_queue_enqueued",
            reason=f"Enqueued in review queue: {verdict.reason}",
            metadata_={"review_id": str(review_entry.id), "channel": verdict.channel},
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit_entry)
        await db.flush()

        logger.info(f"Enqueued RecoveryState {recovery_state.id} into review_queue ({verdict.reason})")

        return {
            "status": "enqueued_for_review",
            "decision": "MODIFY",
            "review_id": str(review_entry.id),
            "reason": verdict.reason,
        }

    # 3. BLOCK Decision — Cooldown / No Dispatch
    elif verdict.decision == PolicyDecisionEnum.BLOCK:
        audit_entry = AuditLog(
            event_id=event.id if event else recovery_state.event_id,
            recovery_state_id=recovery_state.id,
            actor="orchestrator",
            action="policy_block",
            reason=f"Execution blocked by policy: {verdict.reason}",
            metadata_={"channel": verdict.channel},
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit_entry)
        await db.flush()

        # If currently failed, move to waiting
        if recovery_state.state == RecoveryStateEnum.failed:
            await transition_state(
                db=db,
                recovery_state=recovery_state,
                target_state=RecoveryStateEnum.waiting,
                reason=f"Policy blocked dispatch — moved to waiting: {verdict.reason}",
                actor="orchestrator",
                event=event,
            )

        logger.info(f"Blocked dispatch for RecoveryState {recovery_state.id}: {verdict.reason}")

        return {
            "status": "blocked",
            "decision": "BLOCK",
            "reason": verdict.reason,
        }

    else:
        raise ValueError(f"Unknown policy decision type: {verdict.decision}")

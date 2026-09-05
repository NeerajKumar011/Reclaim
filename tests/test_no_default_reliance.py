"""Regression tests proving policy evaluation context parameters are NOT silently defaulting.

Verifies:
1. During replay loop over test_holdout.jsonl:
   - `confidence` values are NOT uniformly 1.0.
   - `recovery_probability` values are NOT uniformly 1.0.
   - `contacts_this_week` values are NOT uniformly 0.
   - `daily_spend_so_far_paise` values are NOT uniformly 0.
2. In-memory DB test for get_live_policy_context in dispatcher.py returns non-default DB-backed values.
"""

from unittest.mock import patch
import pytest

from reclaim.db.models import Customer, Event, EventType, RecoveryState, RecoveryStateEnum
from reclaim.eval.replay import replay_heldout_dataset
from reclaim.orchestrator.executors.dispatcher import get_live_policy_context, evaluate_policy_with_db_context
from reclaim.policy.rules import evaluate as original_evaluate


def test_replay_does_not_use_silent_defaults():
    """Assert replay path passes non-default, varying parameters to rules.evaluate()."""

    captured_kwargs = []

    def tracking_evaluate(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return original_evaluate(*args, **kwargs)

    with patch("reclaim.eval.replay.reclaim_evaluate", side_effect=tracking_evaluate), \
         patch("reclaim.eval.replay.get_classifier") as mock_cls:
        from reclaim.diagnosis.classifier import heuristic_classify
        mock_cls.return_value.classify.side_effect = lambda rev: heuristic_classify({"failure_reason_raw": rev.failure_reason_raw, "amount": rev.amount, "event_category": rev.event_category.value})
        results = replay_heldout_dataset()

    assert len(captured_kwargs) == 1500, f"Expected 1,500 evaluated records, got {len(captured_kwargs)}"

    confidences = {k.get("confidence") for k in captured_kwargs}
    rec_probs = {k.get("recovery_probability") for k in captured_kwargs}
    contacts_this_week_vals = {k.get("contacts_this_week") for k in captured_kwargs}
    daily_spends = {k.get("daily_spend_so_far_paise") for k in captured_kwargs}

    # 1. Confidence values must be varying and NOT uniformly 1.0
    assert confidences != {1.0}, "Confidence values passed to evaluate() are uniformly 1.0!"
    assert len(confidences) > 1, f"Expected multiple distinct confidence values, got {confidences}"

    # 2. Recovery probability values must be varying and NOT uniformly 1.0
    assert rec_probs != {1.0}, "Recovery probability values passed to evaluate() are uniformly 1.0!"
    assert len(rec_probs) > 1, f"Expected multiple distinct recovery probabilities, got {len(rec_probs)}"

    # 3. Contacts this week must contain values > 0
    assert any(c > 0 for c in contacts_this_week_vals), f"contacts_this_week is uniformly 0! Found: {contacts_this_week_vals}"

    # 4. Daily spend so far must contain values > 0
    assert any(s > 0 for s in daily_spends), f"daily_spend_so_far_paise is uniformly 0! Found: {daily_spends}"


@pytest.mark.asyncio
async def test_live_db_context_queries_non_defaults(db_session):
    """Verify get_live_policy_context queries actual DB state and returns context dict."""
    customer = Customer(email="context_test@example.com", name="Context User")
    db_session.add(customer)
    await db_session.flush()

    event = Event(
        razorpay_event_id="evt_ctx_1",
        event_type=EventType.payment_failed,
        raw_payload={"failure_reason_raw": "OTP_TIMEOUT"},
    )
    db_session.add(event)
    await db_session.flush()

    rs = RecoveryState(
        customer_id=customer.id,
        event_id=event.id,
        amount=1000,
        state=RecoveryStateEnum.failed,
    )
    db_session.add(rs)
    await db_session.flush()

    ctx = await get_live_policy_context(
        db=db_session,
        customer=customer,
        recovery_state=rs,
        event=event,
        diagnosis_cause="OTP_TIMEOUT",
    )

    assert "contacts_this_week" in ctx
    assert "hours_since_last_contact" in ctx
    assert "confidence" in ctx
    assert "recovery_probability" in ctx
    assert "daily_spend_so_far_paise" in ctx

    assert ctx["contacts_this_week"] == 0
    assert ctx["hours_since_last_contact"] == float("inf")
    assert ctx["confidence"] == 0.92  # OTP_TIMEOUT confidence from heuristic_classify


@pytest.mark.asyncio
async def test_evaluate_policy_with_db_context_passes_real_recovery_memory(db_session):
    """Verify evaluate_policy_with_db_context fetches real DB RecoveryMemory (e.g. fatigue, preferred_channel) and passes it."""
    from reclaim.db.models import RecoveryMemory
    from reclaim.policy.verdict import Decision

    customer = Customer(email="memory_test@example.com", name="Memory Customer")
    db_session.add(customer)
    await db_session.flush()

    # Add real RecoveryMemory with high fatigue score (0.90) and preferred channel sms
    memory = RecoveryMemory(
        customer_id=customer.id,
        preferred_channel="sms",
        preferred_language="en",
        historical_response_rate=0.4,
        fatigue_score_last_computed=0.90,  # Exceeds MAX_FATIGUE_SCORE (0.80)
    )
    db_session.add(memory)

    event = Event(
        razorpay_event_id="evt_mem_1",
        event_type=EventType.payment_failed,
        raw_payload={"failure_reason_raw": "INSUFFICIENT_FUNDS"},
    )
    db_session.add(event)
    await db_session.flush()

    rs = RecoveryState(
        customer_id=customer.id,
        event_id=event.id,
        amount=1000,
        state=RecoveryStateEnum.failed,
    )
    db_session.add(rs)
    await db_session.flush()

    verdict = await evaluate_policy_with_db_context(
        db=db_session,
        customer=customer,
        recovery_state=rs,
        diagnosis_cause="INSUFFICIENT_FUNDS",
        event=event,
    )

    # Because fatigue is 0.90 from the real DB memory, policy must BLOCK due to fatigue
    assert verdict.decision == Decision.BLOCK
    assert "fatigue" in verdict.reason.lower() or "0.90" in verdict.reason


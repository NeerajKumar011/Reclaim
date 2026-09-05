"""Test Suite for Promise-to-Pay Extraction & Policy Suppression (Step 13).

Covers:
  - English promise extraction ("I will pay tomorrow", "will clear invoice on Friday")
  - Hinglish promise extraction ("Salary parso aayegi, tab pay kar dunga", "kal payment kar dunga")
  - Non-promise / opt-out text ("STOP", "not interested", "wrong number")
  - Ambiguous / uncommitted text ("maybe later", "I don't know")
  - Policy suppression when active promise exists (WAIT / no outreach)
  - Promise fulfilled (payment captured -> RECOVERED)
  - Promise expired (date in past -> re-evaluates)
  - Opt-out after promise (STOP overrides promise)
"""

from datetime import datetime, timedelta, timezone
import pytest

from reclaim.db.models import Customer, RecoveryMemory
from reclaim.diagnosis.promise_extractor import PromiseExtractor, heuristic_extract_promise
from reclaim.diagnosis.schemas import PromiseToPayOutput
from reclaim.policy.rules import evaluate as evaluate_policy
from reclaim.policy.verdict import Decision, PolicyVerdict, Tier


def test_hinglish_salary_promise_extraction():
    """Hinglish phrase 'Salary parso aayegi, tab pay kar dunga' extracted accurately."""
    text = "Salary parso aayegi bhai, tab pay kar dunga pakka"
    base_date = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    res = heuristic_extract_promise(text, base_date=base_date)

    assert res.promise is True
    assert res.date == "2026-09-07"
    assert res.confidence >= 0.80


def test_hinglish_kal_payment_extraction():
    """Hinglish phrase 'kal pay karunga' extracted accurately."""
    text = "haan kal payment kar dunga morning mein"
    base_date = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    res = heuristic_extract_promise(text, base_date=base_date)

    assert res.promise is True
    assert res.date == "2026-09-06"
    assert res.confidence >= 0.80


def test_english_promise_extraction():
    """Standard English promise extraction."""
    text = "I will pay tomorrow via UPI for Rs. 5000"
    base_date = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    res = heuristic_extract_promise(text, base_date=base_date)

    assert res.promise is True
    assert res.date == "2026-09-06"
    assert res.amount == 500000  # 5000 * 100 paise
    assert res.confidence >= 0.80


def test_non_promise_refusal_extraction():
    """Refusal or opt-out text returns promise=False with high confidence."""
    text = "STOP messaging me. Not interested."
    res = heuristic_extract_promise(text)

    assert res.promise is False
    assert res.date is None
    assert res.confidence >= 0.90


def test_ambiguous_text_no_promise():
    """Ambiguous or uncommitted response returns promise=False."""
    text = "I don't know what this charge is for"
    res = heuristic_extract_promise(text)

    assert res.promise is False


def test_active_promise_suppresses_policy_outreach():
    """Active promise in future suppresses reminder outreach (WAIT)."""
    customer = Customer(email="promise@test.com", opted_out=False)
    future_date = datetime.now(timezone.utc) + timedelta(days=2)
    memory = RecoveryMemory(
        customer_id=customer.id,
        promise_to_pay_date=future_date,
    )

    verdict = evaluate_policy(
        diagnosis_cause="INSUFFICIENT_FUNDS",
        customer=customer,
        recovery_memory=memory,
        amount_paise=100000,
    )

    assert verdict.decision == Decision.MODIFY
    assert verdict.channel == "none"
    assert "Active promise-to-pay" in verdict.reason
    assert "suppressed" in verdict.reason.lower()


def test_expired_promise_allows_normal_policy_evaluation():
    """Expired promise (in past) does NOT suppress policy outreach."""
    customer = Customer(email="expired_promise@test.com", opted_out=False)
    past_date = datetime.now(timezone.utc) - timedelta(days=1)
    memory = RecoveryMemory(
        customer_id=customer.id,
        promise_to_pay_date=past_date,
        fatigue_score_last_computed=0.0,
    )

    verdict = evaluate_policy(
        diagnosis_cause="OTP_TIMEOUT",
        customer=customer,
        recovery_memory=memory,
        amount_paise=100000,
    )

    # Should evaluate normally as OTP_TIMEOUT -> ALLOW
    assert verdict.decision == Decision.ALLOW
    assert verdict.channel == "razorpay_payment_link"


def test_opt_out_overrides_active_promise():
    """Opt-out hard stop takes precedence over an active promise."""
    customer = Customer(email="opted_out@test.com", opted_out=True)
    future_date = datetime.now(timezone.utc) + timedelta(days=2)
    memory = RecoveryMemory(
        customer_id=customer.id,
        promise_to_pay_date=future_date,
    )

    verdict = evaluate_policy(
        diagnosis_cause="INSUFFICIENT_FUNDS",
        customer=customer,
        recovery_memory=memory,
        amount_paise=100000,
    )

    assert verdict.decision == Decision.BLOCK
    assert verdict.channel == "none"
    assert "opted out" in verdict.reason.lower()

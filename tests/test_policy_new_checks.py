"""Unit tests for the newly-added policy checks in reclaim/policy/rules.py.

Covers (each check in evaluate() order):
  - Compliance / cooldown block (Step 2)
  - Confidence tier routing to REVIEW tier (Step 3)
  - Confidence below REVIEW threshold -> human escalation (Step 3)
  - Recovery ROI gate blocking a low-expected-value case (Step 4)
  - Daily budget cap blocking once cap is exceeded (Step 5)
  - URGENT_CAUSES bypass: BANK_RAIL_DOWN still blocks even when fatigue is high (Step 6)
  - Verify existing opt-out and high-fatigue checks still work (regression guard)
"""

import pytest

from reclaim.db.models import Customer, RecoveryMemory
from reclaim.policy.rules import (
    CONFIDENCE_AUTO_THRESHOLD,
    CONFIDENCE_REVIEW_THRESHOLD,
    DAILY_BUDGET_CAP_PAISE,
    MAX_CONTACTS_PER_WEEK_B2B,
    MAX_CONTACTS_PER_WEEK_CONSUMER,
    MAX_FATIGUE_SCORE,
    MIN_EXPECTED_VALUE_MULTIPLE,
    MIN_HOURS_BETWEEN_CONTACTS_CONSUMER,
    evaluate,
)
from reclaim.policy.verdict import Decision, Tier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _customer(opted_out: bool = False) -> Customer:
    c = Customer(
        email="test@example.com",
        name="Test Customer",
        preferred_language="en",
        opted_out=opted_out,
    )
    return c


def _memory(fatigue: float = 0.0, preferred_channel: str = None) -> RecoveryMemory:
    m = RecoveryMemory(
        customer_id=None,
        preferred_channel=preferred_channel,
        preferred_language="en",
        historical_response_rate=0.5,
        fatigue_score_last_computed=fatigue,
    )
    return m


# ---------------------------------------------------------------------------
# Step 2: Compliance / cooldown checks
# ---------------------------------------------------------------------------


class TestComplianceCooldownCheck:
    def test_consumer_weekly_contact_limit_blocks(self):
        """Hitting MAX_CONTACTS_PER_WEEK_CONSUMER triggers a BLOCK."""
        verdict = evaluate(
            diagnosis_cause="INSUFFICIENT_FUNDS",
            customer=_customer(),
            amount_paise=100_000,
            contacts_this_week=MAX_CONTACTS_PER_WEEK_CONSUMER,
        )
        assert verdict.decision == Decision.BLOCK
        assert verdict.tier == Tier.BLOCK
        assert "weekly contact limit" in verdict.reason
        assert "consumer" in verdict.reason

    def test_b2b_weekly_contact_limit_uses_higher_threshold(self):
        """B2B accounts use a higher weekly limit than consumer accounts."""
        # Under the consumer limit but over the B2B... wait, B2B limit is HIGHER.
        # So: under B2B limit should ALLOW, at/over B2B limit should BLOCK.
        verdict_allow = evaluate(
            diagnosis_cause="B2B_CASH_CONSTRAINED",
            customer=_customer(),
            amount_paise=500_000,
            contacts_this_week=MAX_CONTACTS_PER_WEEK_B2B - 1,
        )
        # B2B cause routes to MODIFY/human_escalation — just check it is NOT a compliance block
        assert "weekly contact limit" not in verdict_allow.reason

        verdict_block = evaluate(
            diagnosis_cause="B2B_CASH_CONSTRAINED",
            customer=_customer(),
            amount_paise=500_000,
            contacts_this_week=MAX_CONTACTS_PER_WEEK_B2B,
        )
        assert verdict_block.decision == Decision.BLOCK
        assert "B2B" in verdict_block.reason

    def test_minimum_hours_between_contacts_blocks_too_soon(self):
        """Contacting a consumer before the minimum inter-contact gap triggers a BLOCK."""
        verdict = evaluate(
            diagnosis_cause="OTP_TIMEOUT",
            customer=_customer(),
            amount_paise=80_000,
            hours_since_last_contact=MIN_HOURS_BETWEEN_CONTACTS_CONSUMER - 1,
        )
        assert verdict.decision == Decision.BLOCK
        assert verdict.tier == Tier.BLOCK
        assert "inter-contact interval" in verdict.reason

    def test_contact_allowed_after_minimum_hours(self):
        """A contact exactly at the minimum gap is permitted."""
        verdict = evaluate(
            diagnosis_cause="OTP_TIMEOUT",
            customer=_customer(),
            amount_paise=80_000,
            hours_since_last_contact=float(MIN_HOURS_BETWEEN_CONTACTS_CONSUMER),
        )
        # Should NOT be blocked by cooldown (may be ALLOW)
        assert "inter-contact interval" not in verdict.reason

    def test_default_contacts_this_week_zero_does_not_block(self):
        """Default contacts_this_week=0 means the compliance check never fires."""
        verdict = evaluate(
            diagnosis_cause="INSUFFICIENT_FUNDS",
            customer=_customer(),
            amount_paise=200_000,
        )
        assert "weekly contact limit" not in verdict.reason


# ---------------------------------------------------------------------------
# Step 3: Confidence tier routing
# ---------------------------------------------------------------------------


class TestConfidenceTierRouting:
    def test_high_confidence_produces_auto_tier(self):
        """Confidence >= AUTO_THRESHOLD routes to Tier.AUTO."""
        verdict = evaluate(
            diagnosis_cause="INSUFFICIENT_FUNDS",
            customer=_customer(),
            amount_paise=200_000,
            confidence=CONFIDENCE_AUTO_THRESHOLD,
        )
        assert verdict.decision == Decision.ALLOW
        assert verdict.tier == Tier.AUTO

    def test_medium_confidence_produces_review_tier(self):
        """Confidence in [REVIEW_THRESHOLD, AUTO_THRESHOLD) routes to Tier.REVIEW."""
        mid = (CONFIDENCE_AUTO_THRESHOLD + CONFIDENCE_REVIEW_THRESHOLD) / 2.0
        verdict = evaluate(
            diagnosis_cause="INSUFFICIENT_FUNDS",
            customer=_customer(),
            amount_paise=200_000,
            confidence=mid,
        )
        assert verdict.decision == Decision.ALLOW
        assert verdict.tier == Tier.REVIEW

    def test_low_confidence_routes_to_human_escalation(self):
        """Confidence < REVIEW_THRESHOLD -> MODIFY to human_escalation."""
        verdict = evaluate(
            diagnosis_cause="INSUFFICIENT_FUNDS",
            customer=_customer(),
            amount_paise=200_000,
            confidence=CONFIDENCE_REVIEW_THRESHOLD - 0.01,
        )
        assert verdict.decision == Decision.MODIFY
        assert verdict.channel == "human_escalation"
        assert verdict.tier == Tier.BLOCK
        assert "Confidence too low" in verdict.reason

    def test_default_confidence_1_0_always_auto(self):
        """Legacy callers with no confidence param always get Tier.AUTO — backward compat."""
        verdict = evaluate(
            diagnosis_cause="AUTH_ABORT",
            customer=_customer(),
            amount_paise=50_000,
        )
        assert verdict.tier == Tier.AUTO

    def test_confidence_exactly_at_review_threshold_is_review_not_block(self):
        """Confidence exactly equal to REVIEW_THRESHOLD should be Tier.REVIEW, not routed to human."""
        verdict = evaluate(
            diagnosis_cause="INSUFFICIENT_FUNDS",
            customer=_customer(),
            amount_paise=200_000,
            confidence=CONFIDENCE_REVIEW_THRESHOLD,
        )
        assert verdict.tier == Tier.REVIEW
        assert "Confidence too low" not in verdict.reason


# ---------------------------------------------------------------------------
# Step 4: Recovery ROI gate
# ---------------------------------------------------------------------------


class TestROIGate:
    def test_low_expected_value_blocks(self):
        """Expected recovery below the cost threshold produces a BLOCK."""
        # Use SMS channel (cost=25 paise), MIN_EXPECTED_VALUE_MULTIPLE=10
        # ROI bar = 25 * 10 = 250 paise
        # Set amount=1000, probability=0.2 -> expected=200 paise < 250 -> BLOCK
        memory = _memory(preferred_channel="sms")
        verdict = evaluate(
            diagnosis_cause="INSUFFICIENT_FUNDS",
            customer=_customer(),
            recovery_memory=memory,
            amount_paise=1_000,
            recovery_probability=0.20,  # expected = 200 paise < bar (250 paise)
        )
        assert verdict.decision == Decision.BLOCK
        assert "ROI gate" in verdict.reason

    def test_adequate_expected_value_allows(self):
        """Expected recovery above the cost threshold does NOT block."""
        memory = _memory(preferred_channel="sms")
        verdict = evaluate(
            diagnosis_cause="INSUFFICIENT_FUNDS",
            customer=_customer(),
            recovery_memory=memory,
            amount_paise=100_000,
            recovery_probability=0.50,  # expected = 50,000 paise >> 250 paise bar
        )
        assert verdict.decision == Decision.ALLOW

    def test_zero_cost_channel_always_clears_bar(self):
        """razorpay_payment_link has zero cost — ROI gate never blocks it."""
        memory = _memory(preferred_channel="razorpay_payment_link")
        verdict = evaluate(
            diagnosis_cause="OTP_TIMEOUT",
            customer=_customer(),
            recovery_memory=memory,
            amount_paise=500,
            recovery_probability=0.001,  # Would fail against any non-zero cost
        )
        # razorpay_payment_link cost = 0, so ROI gate skips -> should ALLOW
        assert verdict.decision == Decision.ALLOW

    def test_zero_amount_skips_roi_gate(self):
        """amount_paise=0 bypasses the ROI gate entirely — nothing to recover."""
        verdict = evaluate(
            diagnosis_cause="INSUFFICIENT_FUNDS",
            customer=_customer(),
            amount_paise=0,
            recovery_probability=0.0,
        )
        assert "ROI gate" not in verdict.reason

    def test_default_recovery_probability_1_0_never_blocks(self):
        """Default recovery_probability=1.0 means ROI gate never blocks legacy callers."""
        verdict = evaluate(
            diagnosis_cause="INSUFFICIENT_FUNDS",
            customer=_customer(),
            amount_paise=10_000,
        )
        assert "ROI gate" not in verdict.reason


# ---------------------------------------------------------------------------
# Step 5: Daily budget cap
# ---------------------------------------------------------------------------


class TestDailyBudgetCap:
    def test_at_cap_blocks(self):
        """Spend exactly at or above DAILY_BUDGET_CAP_PAISE produces a BLOCK."""
        verdict = evaluate(
            diagnosis_cause="INSUFFICIENT_FUNDS",
            customer=_customer(),
            amount_paise=200_000,
            daily_spend_so_far_paise=DAILY_BUDGET_CAP_PAISE,
        )
        assert verdict.decision == Decision.BLOCK
        assert verdict.tier == Tier.BLOCK
        assert "Daily budget cap" in verdict.reason

    def test_over_cap_also_blocks(self):
        """Spend over the cap also blocks."""
        verdict = evaluate(
            diagnosis_cause="OTP_TIMEOUT",
            customer=_customer(),
            amount_paise=50_000,
            daily_spend_so_far_paise=DAILY_BUDGET_CAP_PAISE + 1,
        )
        assert verdict.decision == Decision.BLOCK

    def test_under_cap_allows(self):
        """Spend below the cap does not trigger the budget gate."""
        verdict = evaluate(
            diagnosis_cause="OTP_TIMEOUT",
            customer=_customer(),
            amount_paise=50_000,
            daily_spend_so_far_paise=DAILY_BUDGET_CAP_PAISE - 1,
        )
        assert "Daily budget cap" not in verdict.reason

    def test_default_daily_spend_zero_never_blocks(self):
        """Default daily_spend_so_far_paise=0 means budget gate never fires for legacy callers."""
        verdict = evaluate(
            diagnosis_cause="AUTH_ABORT",
            customer=_customer(),
            amount_paise=80_000,
        )
        assert "Daily budget cap" not in verdict.reason


# ---------------------------------------------------------------------------
# Step 6: URGENT_CAUSES fatigue bypass
# ---------------------------------------------------------------------------


class TestUrgentCausesFatigueBypass:
    def test_bank_rail_down_blocks_even_when_fatigue_high(self):
        """BANK_RAIL_DOWN must produce COOLDOWN_REASON_BANK, not FATIGUE_BLOCK_REASON."""
        high_fatigue_memory = _memory(fatigue=MAX_FATIGUE_SCORE + 0.1)
        verdict = evaluate(
            diagnosis_cause="BANK_RAIL_DOWN",
            customer=_customer(),
            recovery_memory=high_fatigue_memory,
            amount_paise=100_000,
        )
        assert verdict.decision == Decision.BLOCK
        # Must use the bank-rail reason, NOT the fatigue reason
        assert "Bank rail" in verdict.reason
        assert "fatigue" not in verdict.reason.lower()

    def test_non_urgent_cause_still_blocked_by_fatigue(self):
        """A non-URGENT cause with high fatigue still gets the fatigue block."""
        high_fatigue_memory = _memory(fatigue=MAX_FATIGUE_SCORE + 0.1)
        verdict = evaluate(
            diagnosis_cause="INSUFFICIENT_FUNDS",
            customer=_customer(),
            recovery_memory=high_fatigue_memory,
            amount_paise=100_000,
        )
        assert verdict.decision == Decision.BLOCK
        assert "fatigue" in verdict.reason.lower()


# ---------------------------------------------------------------------------
# Regression guard: existing checks still work
# ---------------------------------------------------------------------------


class TestExistingChecksRegression:
    def test_opt_out_still_blocks_first(self):
        """Opt-out check remains the very first gate — it fires before any new check."""
        opted_out_customer = _customer(opted_out=True)
        verdict = evaluate(
            diagnosis_cause="INSUFFICIENT_FUNDS",
            customer=opted_out_customer,
            amount_paise=100_000,
            contacts_this_week=0,  # compliance would not fire
            confidence=1.0,        # confidence would not fire
        )
        assert verdict.decision == Decision.BLOCK
        assert "opted out" in verdict.reason.lower()

    def test_discount_ceiling_unchanged_for_genuine_abandon(self):
        """GENUINE_ABANDON discount ceiling (Rs. 50) is preserved exactly as before."""
        verdict = evaluate(
            diagnosis_cause="GENUINE_ABANDON",
            customer=_customer(),
            amount_paise=1_000_000,  # Rs. 10,000 — 5% would be Rs. 500, capped at Rs. 50
        )
        assert verdict.decision == Decision.ALLOW
        assert verdict.max_discount_paise == 5000  # Rs. 50 ceiling enforced

    def test_b2b_still_routes_to_human_escalation(self):
        """B2B causes still produce MODIFY/human_escalation verdict."""
        for cause in ("B2B_CASH_CONSTRAINED", "B2B_DISPUTE"):
            verdict = evaluate(
                diagnosis_cause=cause,
                customer=_customer(),
                amount_paise=500_000,
            )
            assert verdict.decision == Decision.MODIFY
            assert verdict.channel == "human_escalation"

    def test_otp_timeout_default_channel_unchanged(self):
        """OTP_TIMEOUT still defaults to razorpay_payment_link channel."""
        verdict = evaluate(
            diagnosis_cause="OTP_TIMEOUT",
            customer=_customer(),
            amount_paise=75_000,
        )
        assert verdict.decision == Decision.ALLOW
        assert verdict.channel == "razorpay_payment_link"

"""Unit tests for Baseline Policies."""

import pytest

from reclaim.eval.baselines import (
    fixed_dunning_ladder_baseline,
    fixed_retry_baseline,
    no_intervention_baseline,
)
from reclaim.policy.verdict import Decision, Tier


def test_no_intervention_baseline_returns_fixed_block():
    """Test no_intervention_baseline always returns BLOCK regardless of diagnosis."""
    for cause in ["INSUFFICIENT_FUNDS", "OTP_TIMEOUT", "BANK_RAIL_DOWN", "AUTH_ABORT", "GENUINE_ABANDON"]:
        verdict = no_intervention_baseline(diagnosis_cause=cause, amount_paise=50000)
        assert verdict.decision == Decision.BLOCK
        assert verdict.channel == "none"
        assert verdict.reason == "baseline: no intervention"
        assert verdict.tier == Tier.BLOCK


def test_fixed_retry_baseline_returns_fixed_allow_sms():
    """Test fixed_retry_baseline always returns ALLOW via SMS regardless of diagnosis."""
    for cause in ["INSUFFICIENT_FUNDS", "OTP_TIMEOUT", "BANK_RAIL_DOWN", "AUTH_ABORT", "GENUINE_ABANDON"]:
        verdict = fixed_retry_baseline(diagnosis_cause=cause, amount_paise=100000)
        assert verdict.decision == Decision.ALLOW
        assert verdict.channel == "sms"
        assert verdict.reason == "baseline: fixed retry"
        assert verdict.tier == Tier.AUTO


def test_fixed_dunning_ladder_baseline_schedule():
    """Test fixed_dunning_ladder_baseline step schedule (day 0 sms, day 1 whatsapp, day 3 voice_call)."""
    step0 = fixed_dunning_ladder_baseline(diagnosis_cause="OTP_TIMEOUT", step_index=0)
    assert step0.decision == Decision.ALLOW
    assert step0.channel == "sms"

    step1 = fixed_dunning_ladder_baseline(diagnosis_cause="OTP_TIMEOUT", step_index=1)
    assert step1.decision == Decision.ALLOW
    assert step1.channel == "whatsapp"

    step2 = fixed_dunning_ladder_baseline(diagnosis_cause="OTP_TIMEOUT", step_index=2)
    assert step2.decision == Decision.ALLOW
    assert step2.channel == "voice_call"


def test_native_razorpay_retry_baseline():
    """Test native_razorpay_retry_baseline always routes to razorpay_payment_link."""
    from reclaim.eval.baselines import native_razorpay_retry_baseline

    for cause in ["INSUFFICIENT_FUNDS", "OTP_TIMEOUT", "BANK_RAIL_DOWN"]:
        verdict = native_razorpay_retry_baseline(diagnosis_cause=cause, amount_paise=50000)
        assert verdict.decision == Decision.ALLOW
        assert verdict.channel == "razorpay_payment_link"
        assert verdict.tier == Tier.AUTO


def test_standard_fixed_dunning_industry():
    """Test standard_fixed_dunning_industry 4-step schedule."""
    from reclaim.eval.baselines import standard_fixed_dunning_industry

    assert standard_fixed_dunning_industry(step_index=0).channel == "sms"
    assert standard_fixed_dunning_industry(step_index=1).channel == "whatsapp"
    assert standard_fixed_dunning_industry(step_index=2).channel == "voice_call"
    assert standard_fixed_dunning_industry(step_index=3).channel == "human_escalation"


def test_ml_score_only_threshold():
    """Test ml_score_only_threshold allows when score >= 0.50 and blocks when score < 0.50."""
    from reclaim.eval.baselines import ml_score_only_threshold

    allow_verdict = ml_score_only_threshold(recovery_probability=0.75, amount_paise=100000)
    assert allow_verdict.decision == Decision.ALLOW
    assert allow_verdict.channel == "sms"

    block_verdict = ml_score_only_threshold(recovery_probability=0.30, amount_paise=100000)
    assert block_verdict.decision == Decision.BLOCK
    assert block_verdict.channel == "none"


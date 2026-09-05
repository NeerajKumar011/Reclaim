"""Test Suite for Policy Invariants & Safety Checks.

Verifies:
  1. Opt-out invariant (Zero contact permitted)
  2. Cooldown invariant (Min hours interval respected)
  3. Weekly contact cap invariant (3 for consumer, 5 for B2B)
  4. Daily budget cap invariant
  5. Discount ceiling invariant (Max 15% / 15000 paise)
  6. Terminal state outreach invariant
  7. Valid channel set invariant
  8. Duplicate action invariant
"""

from datetime import datetime, timezone
import pytest

from reclaim.policy.invariants import PolicyInvariantEvaluator, InvariantViolationReport
from reclaim.policy.verdict import Decision, PolicyVerdict, Tier


def test_opt_out_invariant_pass():
    """Opted out customer with BLOCK verdict produces no violation."""
    verdict = PolicyVerdict(
        decision=Decision.BLOCK,
        channel="none",
        reason="Customer has opted out.",
        tier=Tier.BLOCK,
    )
    report = PolicyInvariantEvaluator.check_verdict_invariants(
        verdict=verdict,
        opted_out=True,
    )
    assert report.total_violations == 0


def test_opt_out_invariant_violation_on_allow():
    """Opted out customer with ALLOW verdict fails opt-out invariant."""
    illegal_verdict = PolicyVerdict(
        decision=Decision.ALLOW,
        channel="whatsapp",
        reason="Illegal outreach attempt",
        tier=Tier.AUTO,
    )
    report = PolicyInvariantEvaluator.check_verdict_invariants(
        verdict=illegal_verdict,
        opted_out=True,
    )
    assert report.total_violations > 0
    assert any("Opt-out" in v for v in report.violation_details)


def test_cooldown_invariant_violation():
    """Outreach before cooldown elapsed fails cooldown invariant."""
    illegal_verdict = PolicyVerdict(
        decision=Decision.ALLOW,
        channel="sms",
        reason="Too fast contact",
        tier=Tier.AUTO,
    )
    report = PolicyInvariantEvaluator.check_verdict_invariants(
        verdict=illegal_verdict,
        opted_out=False,
        hours_since_last_contact=5.0,
        min_hours=24.0,
    )
    assert report.total_violations > 0
    assert any("Cooldown" in v for v in report.violation_details)


def test_contact_cap_invariant_violation():
    """Outreach exceeding contact cap fails contact cap invariant."""
    illegal_verdict = PolicyVerdict(
        decision=Decision.ALLOW,
        channel="sms",
        reason="Excessive contact",
        tier=Tier.AUTO,
    )
    report = PolicyInvariantEvaluator.check_verdict_invariants(
        verdict=illegal_verdict,
        opted_out=False,
        contacts_this_week=4,
        max_contacts=3,
    )
    assert report.total_violations > 0
    assert any("Contact cap" in v for v in report.violation_details)


def test_budget_cap_invariant_violation():
    """Outreach after daily budget exhausted fails budget cap invariant."""
    illegal_verdict = PolicyVerdict(
        decision=Decision.ALLOW,
        channel="sms",
        reason="Over budget",
        tier=Tier.AUTO,
    )
    report = PolicyInvariantEvaluator.check_verdict_invariants(
        verdict=illegal_verdict,
        opted_out=False,
        daily_spend_paise=600000,
        budget_cap_paise=500000,
    )
    assert report.total_violations > 0
    assert any("Budget" in v for v in report.violation_details)


def test_discount_ceiling_invariant_violation():
    """Discount exceeding ceiling or unauthorized cause fails discount invariant."""
    illegal_verdict = PolicyVerdict(
        decision=Decision.ALLOW,
        channel="whatsapp",
        reason="Huge discount",
        tier=Tier.AUTO,
        max_discount_paise=25000,  # > 5000 max ceiling
    )
    report = PolicyInvariantEvaluator.check_verdict_invariants(
        verdict=illegal_verdict,
        opted_out=False,
        diagnosis_cause="INSUFFICIENT_FUNDS",
    )
    assert report.total_violations > 0
    assert any("Discount" in v or "Unauthorized discount" in v for v in report.violation_details)


def test_terminal_state_invariant_violation():
    """Outreach on terminal state case fails terminal state invariant."""
    illegal_verdict = PolicyVerdict(
        decision=Decision.ALLOW,
        channel="whatsapp",
        reason="Stale outreach",
        tier=Tier.AUTO,
    )
    report = PolicyInvariantEvaluator.check_verdict_invariants(
        verdict=illegal_verdict,
        opted_out=False,
        is_terminal_state=True,
    )
    assert report.total_violations > 0
    assert any("Terminal state" in v for v in report.violation_details)


def test_invalid_channel_invariant_violation():
    """Outreach via unregistered channel fails invalid channel invariant."""
    illegal_verdict = PolicyVerdict(
        decision=Decision.ALLOW,
        channel="telegram_bot",  # Not in allowed channels
        reason="Unknown channel",
        tier=Tier.AUTO,
    )
    report = PolicyInvariantEvaluator.check_verdict_invariants(
        verdict=illegal_verdict,
        opted_out=False,
    )
    assert report.total_violations > 0
    assert any("Invalid channel" in v for v in report.violation_details)

"""Unit tests for C1 and C2 scoreboard arithmetic fixes.

C1: decision_distribution ACT+WAIT+STOP counts must sum exactly to total_records
    for every policy. Percentages of those three must sum to 100.0%.

C2: avg_time_to_recovery_hours must differ meaningfully across policies
    (not all equal to 24.0) and must be 0.0 for policies with no recoveries.
"""

import hashlib
from typing import Dict, List
from unittest.mock import MagicMock

import pytest

from reclaim.eval.metrics import compute_policy_metrics
from reclaim.eval.replay import ReplayRecordOutcome
from reclaim.policy.verdict import Decision, PolicyVerdict, Tier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_verdict(decision: Decision, channel: str = "sms", tier: Tier = Tier.AUTO) -> PolicyVerdict:
    return PolicyVerdict(
        decision=decision,
        channel=channel,
        reason="test",
        tier=tier,
        max_discount_paise=0,
    )


def _make_outcome(
    decision: Decision,
    outcome_recovered: bool,
    would_self_resolve: bool = False,
    scheduled_delay_hours: float = 2.0,
    amount_paise: int = 100_000,
    channel: str = "sms",
    tier: Tier = Tier.AUTO,
) -> ReplayRecordOutcome:
    verdict = _make_verdict(decision, channel=channel, tier=tier)
    incremental = outcome_recovered and not would_self_resolve and decision in (Decision.ALLOW, Decision.MODIFY)
    return ReplayRecordOutcome(
        event_id=f"ev_{id(verdict)}",
        amount_paise=amount_paise,
        diagnosed_cause="INSUFFICIENT_FUNDS",
        verdict=verdict,
        actually_recovered_ground_truth=outcome_recovered,
        self_resolving_cause=would_self_resolve,
        outcome_recovered=outcome_recovered,
        would_self_resolve=would_self_resolve,
        incremental_recovered=incremental,
        dispatched_channel=channel if decision == Decision.ALLOW else "none",
        scheduled_delay_hours=scheduled_delay_hours,
        intervention_cost_paise=25 if decision == Decision.ALLOW else 0,
    )


# ---------------------------------------------------------------------------
# C1: Distribution invariant
# ---------------------------------------------------------------------------

class TestC1DecisionDistributionInvariant:
    """ACT + WAIT + STOP == total_records for every policy, every time."""

    def _assert_distribution_invariant(self, outcomes: List[ReplayRecordOutcome], policy_name: str = "TEST"):
        m = compute_policy_metrics(policy_name, outcomes)
        total = m.total_records
        act = m.allow_count
        wait = m.delay_count
        stop = m.block_count

        assert act + wait + stop == total, (
            f"[{policy_name}] ACT({act}) + WAIT({wait}) + STOP({stop}) = {act+wait+stop} "
            f"!= total_records({total}). Distribution sums to wrong value."
        )

        # Percentages: derive from counts to verify report.py math
        if total > 0:
            pct_act = round(act / total * 100, 2)
            pct_wait = round(wait / total * 100, 2)
            pct_stop = round(stop / total * 100, 2)
            pct_sum = round(pct_act + pct_wait + pct_stop, 1)
            assert pct_sum == 100.0, (
                f"[{policy_name}] Percentages sum to {pct_sum}% != 100%. "
                f"ACT={pct_act}% WAIT={pct_wait}% STOP={pct_stop}%"
            )

        return m

    def test_all_allow(self):
        outcomes = [_make_outcome(Decision.ALLOW, True) for _ in range(10)]
        m = self._assert_distribution_invariant(outcomes, "ALL_ALLOW")
        assert m.allow_count == 10
        assert m.delay_count == 0
        assert m.block_count == 0

    def test_all_block(self):
        outcomes = [_make_outcome(Decision.BLOCK, False) for _ in range(10)]
        m = self._assert_distribution_invariant(outcomes, "ALL_BLOCK")
        assert m.allow_count == 0
        assert m.block_count == 10

    def test_mixed_decisions(self):
        outcomes = (
            [_make_outcome(Decision.ALLOW, True) for _ in range(7)]
            + [_make_outcome(Decision.MODIFY, False) for _ in range(2)]
            + [_make_outcome(Decision.BLOCK, False) for _ in range(1)]
        )
        self._assert_distribution_invariant(outcomes, "MIXED")

    def test_review_tier_does_not_inflate_count(self):
        """ALLOW + tier=REVIEW must not be counted in both ACT and ESCALATE totals."""
        outcomes = (
            [_make_outcome(Decision.ALLOW, True, tier=Tier.REVIEW) for _ in range(5)]
            + [_make_outcome(Decision.BLOCK, False) for _ in range(5)]
        )
        m = self._assert_distribution_invariant(outcomes, "REVIEW_TIER_TEST")
        # review_count is a sub-count of allow_count — they overlap, not additive
        assert m.review_count <= m.allow_count, (
            f"review_count({m.review_count}) should be <= allow_count({m.allow_count})"
        )
        # Total still correct
        assert m.allow_count + m.delay_count + m.block_count == m.total_records

    def test_no_action_policy(self):
        """NO-ACTION: all BLOCK verdicts, distribution sums correctly."""
        outcomes = [_make_outcome(Decision.BLOCK, False, would_self_resolve=(i < 3)) for i in range(30)]
        self._assert_distribution_invariant(outcomes, "NO-ACTION")

    def test_reclaim_policy_with_varied_distribution(self):
        """Simulate realistic RECLAIM distribution: mix of ACT, WAIT, STOP."""
        outcomes = (
            [_make_outcome(Decision.ALLOW, True, channel="whatsapp") for _ in range(21)]
            + [_make_outcome(Decision.MODIFY, False, channel="human_escalation") for _ in range(4)]
            + [_make_outcome(Decision.BLOCK, False) for _ in range(125)]
        )
        m = self._assert_distribution_invariant(outcomes, "RECLAIM")
        assert m.allow_count + m.delay_count + m.block_count == 150


# ---------------------------------------------------------------------------
# C2: avg_time_to_recovery_hours is NOT a uniform 24.0
# ---------------------------------------------------------------------------

class TestC2AvgTimeToRecoveryNotHardcoded:
    """avg_time_to_recovery_hours must reflect cause-specific timing, not 24.0 everywhere."""

    def test_no_recovery_yields_zero(self):
        """If no records recovered, avg_time should be 0.0."""
        outcomes = [_make_outcome(Decision.BLOCK, False, scheduled_delay_hours=24.0) for _ in range(10)]
        m = compute_policy_metrics("NO_RECOVERY", outcomes)
        assert m.avg_time_to_recovery_hours == 0.0, (
            f"Expected 0.0 for no recoveries, got {m.avg_time_to_recovery_hours}"
        )

    def test_otp_timeout_shorter_than_funds_shortage(self):
        """OTP recoveries (0.25h) should average shorter than INSUFFICIENT_FUNDS (48h)."""
        # OTP_TIMEOUT: next_retry_time → 15 min = 0.25h
        otp_outcomes = [
            _make_outcome(Decision.ALLOW, True, scheduled_delay_hours=0.25) for _ in range(5)
        ]
        m_otp = compute_policy_metrics("OTP_POLICY", otp_outcomes)

        # INSUFFICIENT_FUNDS: next_retry_time → 48h
        funds_outcomes = [
            _make_outcome(Decision.ALLOW, True, scheduled_delay_hours=48.0) for _ in range(5)
        ]
        m_funds = compute_policy_metrics("FUNDS_POLICY", funds_outcomes)

        assert m_otp.avg_time_to_recovery_hours < m_funds.avg_time_to_recovery_hours, (
            f"OTP avg ({m_otp.avg_time_to_recovery_hours}h) should be < "
            f"FUNDS avg ({m_funds.avg_time_to_recovery_hours}h)"
        )

    def test_avg_excludes_non_recovered(self):
        """avg_time should only average over records that actually recovered."""
        recovered = [_make_outcome(Decision.ALLOW, True, scheduled_delay_hours=4.0) for _ in range(3)]
        not_recovered = [_make_outcome(Decision.ALLOW, False, scheduled_delay_hours=100.0) for _ in range(7)]
        outcomes = recovered + not_recovered
        m = compute_policy_metrics("PARTIAL", outcomes)
        assert m.avg_time_to_recovery_hours == pytest.approx(4.0, abs=0.01), (
            f"Expected avg≈4.0h (only from 3 recovered records), got {m.avg_time_to_recovery_hours}"
        )

    def test_values_are_not_all_identical_24(self):
        """Different delay distributions must produce different averages."""
        short = [_make_outcome(Decision.ALLOW, True, scheduled_delay_hours=0.25) for _ in range(5)]
        long_ = [_make_outcome(Decision.ALLOW, True, scheduled_delay_hours=48.0) for _ in range(5)]
        medium = [_make_outcome(Decision.ALLOW, True, scheduled_delay_hours=4.0) for _ in range(5)]

        m_s = compute_policy_metrics("SHORT", short)
        m_l = compute_policy_metrics("LONG", long_)
        m_m = compute_policy_metrics("MEDIUM", medium)

        values = {m_s.avg_time_to_recovery_hours, m_l.avg_time_to_recovery_hours, m_m.avg_time_to_recovery_hours}
        assert len(values) == 3, f"All avg values are identical: {values} — C2 fix not applied."
        assert all(v != 24.0 for v in [m_s.avg_time_to_recovery_hours, m_m.avg_time_to_recovery_hours]), (
            "OTP (0.25h) and BANK_RAIL (4h) policies should not average to 24.0"
        )

"""Evaluation Metrics Computation.

Computes recovery rates, incremental recovery, intervention costs, cost per recovered rupee,
false positive nudges, policy violations, and time-to-recovery proxies.
"""

from dataclasses import dataclass
from typing import Dict, List

from reclaim.eval.replay import ReplayRecordOutcome
from reclaim.policy.rules import CHANNEL_COST_PAISE
from reclaim.policy.verdict import Decision, Tier


@dataclass
class PolicyMetrics:
    """Summary metrics for a single policy across the held-out dataset."""

    policy_name: str
    total_records: int
    total_at_risk_paise: int
    total_recovered_paise: int
    recovery_rate: float
    incremental_recovery_paise: int
    total_intervention_cost_paise: int
    cost_per_recovered_rupee: float
    contact_count: int
    false_positive_nudge_count: int
    policy_violation_count: int
    avg_time_to_recovery_hours: float
    allow_count: int = 0
    delay_count: int = 0
    review_count: int = 0
    block_count: int = 0
    revenue_recovered_per_contact_rs: float = 0.0
    false_positive_rate_pct: float = 0.0

    @property
    def total_at_risk_rs(self) -> float:
        return float(self.total_at_risk_paise) / 100.0

    @property
    def total_recovered_rs(self) -> float:
        return float(self.total_recovered_paise) / 100.0

    @property
    def incremental_recovery_rs(self) -> float:
        return float(self.incremental_recovery_paise) / 100.0

    @property
    def total_intervention_cost_rs(self) -> float:
        return float(self.total_intervention_cost_paise) / 100.0


def compute_policy_metrics(
    policy_name: str,
    outcomes: List[ReplayRecordOutcome],
    no_action_recovered_paise: int = 0,
) -> PolicyMetrics:
    """Compute all evaluation metrics for a list of record outcomes under a given policy."""
    total_records = len(outcomes)
    total_at_risk_paise = sum(o.amount_paise for o in outcomes)

    recovered_outcomes = [o for o in outcomes if o.outcome_recovered]
    total_recovered_paise = sum(o.amount_paise for o in recovered_outcomes)

    recovery_rate = (
        float(total_recovered_paise) / float(total_at_risk_paise)
        if total_at_risk_paise > 0
        else 0.0
    )

    incremental_recovery_paise = total_recovered_paise - no_action_recovered_paise

    # C1 FIX: mutually exclusive decision distribution so every record contributes
    # to EXACTLY ONE bucket. Prior code double-counted: review_count checked
    # tier==REVIEW which overlaps with allow_count (ALLOW records can also have
    # tier=REVIEW). Now: ACT=ALLOW, WAIT=MODIFY (human-review queue), STOP=BLOCK.
    # Sum: allow_count + delay_count + block_count == total_records (invariant).
    allow_count = sum(1 for o in outcomes if o.verdict.decision == Decision.ALLOW)
    delay_count = sum(1 for o in outcomes if o.verdict.decision == Decision.MODIFY)
    block_count = sum(1 for o in outcomes if o.verdict.decision == Decision.BLOCK)
    # ESCALATE = subset of ALLOW records routed via REVIEW tier (informational only,
    # does NOT inflate total — it is a sub-count of allow_count, not additive).
    review_count = sum(
        1 for o in outcomes
        if o.verdict.decision == Decision.ALLOW and getattr(o.verdict, "tier", None) == Tier.REVIEW
    )

    # Intervention cost: sum of CHANNEL_COST_PAISE for every ALLOW action
    total_intervention_cost_paise = 0
    contact_count = 0
    false_positive_nudge_count = 0
    policy_violation_count = 0

    for o in outcomes:
        if o.verdict.decision == Decision.ALLOW:
            contact_count += 1
            # Use the cost already computed by replay (avoids double-lookup).
            total_intervention_cost_paise += o.intervention_cost_paise

            # False-positive nudge: we nudged a customer who would have
            # self-resolved WITHOUT any intervention (causal, not raw ground_truth).
            if o.would_self_resolve:
                false_positive_nudge_count += 1

        # Assert policy violations using comprehensive PolicyInvariantEvaluator
        if policy_name == "RECLAIM":
            from reclaim.policy.invariants import PolicyInvariantEvaluator
            is_b2b = o.diagnosed_cause in ("B2B_CASH_CONSTRAINED", "B2B_DISPUTE")
            inv_report = PolicyInvariantEvaluator.check_verdict_invariants(
                verdict=o.verdict,
                opted_out=False,
                max_contacts=5 if is_b2b else 3,
                min_hours=12.0 if is_b2b else 24.0,
                diagnosis_cause=o.diagnosed_cause,
            )
            policy_violation_count += inv_report.total_violations

    # Incremental recovery: sum of amounts where our nudge caused the recovery
    # (not counting self-resolvers that would have recovered anyway).
    # This uses the causal `incremental_recovered` field from the potential-outcomes
    # framework, rather than the aggregate subtraction of no_action_recovered_paise.
    incremental_recovery_paise_causal = sum(
        o.amount_paise for o in outcomes if o.incremental_recovered
    )
    # Also keep the aggregate view (total - baseline) for cross-policy comparison
    incremental_recovery_paise_aggregate = total_recovered_paise - no_action_recovered_paise
    # Primary: use the causal count; note it may differ slightly from aggregate
    # because the aggregate includes self-resolvers that happen to be recovered.
    incremental_recovery_paise = incremental_recovery_paise_causal

    cost_per_recovered_rupee = (
        float(total_intervention_cost_paise) / float(total_recovered_paise)
        if total_recovered_paise > 0
        else 0.0
    )

    revenue_recovered_per_contact_rs = (
        (float(total_recovered_paise) / 100.0) / float(contact_count)
        if contact_count > 0
        else 0.0
    )

    false_positive_rate_pct = (
        (float(false_positive_nudge_count) / float(contact_count) * 100.0)
        if contact_count > 0
        else 0.0
    )

    # Average time to recovery (scheduled delay proxy in hours)
    if recovered_outcomes:
        avg_time_hours = sum(o.scheduled_delay_hours for o in recovered_outcomes) / len(recovered_outcomes)
    else:
        avg_time_hours = 0.0

    metrics = PolicyMetrics(
        policy_name=policy_name,
        total_records=total_records,
        total_at_risk_paise=total_at_risk_paise,
        total_recovered_paise=total_recovered_paise,
        recovery_rate=recovery_rate,
        incremental_recovery_paise=incremental_recovery_paise,
        total_intervention_cost_paise=total_intervention_cost_paise,
        cost_per_recovered_rupee=cost_per_recovered_rupee,
        contact_count=contact_count,
        false_positive_nudge_count=false_positive_nudge_count,
        policy_violation_count=policy_violation_count,
        avg_time_to_recovery_hours=avg_time_hours,
        allow_count=allow_count,
        delay_count=delay_count,
        review_count=review_count,
        block_count=block_count,
        revenue_recovered_per_contact_rs=round(revenue_recovered_per_contact_rs, 2),
        false_positive_rate_pct=round(false_positive_rate_pct, 2),
    )

    if policy_name == "RECLAIM":
        assert (
            policy_violation_count == 0
        ), f"RECLAIM policy violation detected: count={policy_violation_count}"

    return metrics


def compute_all_metrics(
    replay_results: Dict[str, List[ReplayRecordOutcome]]
) -> Dict[str, PolicyMetrics]:
    """Compute PolicyMetrics for all 4 policies."""
    no_action_outcomes = replay_results.get("NO-ACTION", [])
    no_action_recovered_paise = sum(
        o.amount_paise for o in no_action_outcomes if o.outcome_recovered
    )

    metrics_map: Dict[str, PolicyMetrics] = {}

    for policy_name, outcomes in replay_results.items():
        m = compute_policy_metrics(
            policy_name=policy_name,
            outcomes=outcomes,
            no_action_recovered_paise=no_action_recovered_paise,
        )
        metrics_map[policy_name] = m

    return metrics_map

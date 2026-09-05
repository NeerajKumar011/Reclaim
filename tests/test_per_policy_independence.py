"""Unit test verifying Per-Policy Outcome Independence."""

import pytest

from reclaim.eval.baselines import (
    fixed_retry_baseline,
    no_intervention_baseline,
)
from reclaim.eval.metrics import compute_policy_metrics
from reclaim.eval.replay import simulate_record_outcome
from reclaim.policy.rules import evaluate as reclaim_evaluate


def test_per_policy_independence_on_synthetic_batch():
    """Verify that different policies compute recovered totals independently on a 10-record batch."""
    records = []
    for i in range(10):
        # Even records: INSUFFICIENT_FUNDS (recoverable = True)
        # Odd records: OTP_TIMEOUT (recoverable = False)
        is_even = i % 2 == 0
        record = {
            "event_id": f"event_indep_{i:03d}",
            "event_category": "payment_failure",
            "customer_id": f"cust_indep_{i:03d}",
            "amount": 100000,  # ₹1,000 each (100,000 paise)
            "currency": "INR",
            "failure_reason_raw": "INSUFFICIENT_FUNDS" if is_even else "OTP_TIMEOUT",
            "source_metadata": {
                "customer_segment": "returning",
                "historical_response": "high",
            },
            "ground_truth": {
                "true_cause": "INSUFFICIENT_FUNDS" if is_even else "OTP_TIMEOUT",
                "true_recovery_probability": 0.90 if is_even else 0.10,
                "actually_recovered": is_even,
            },
        }
        records.append(record)

    # 1. Run NO-ACTION policy
    no_action_outcomes = [
        simulate_record_outcome(r, no_intervention_baseline, "no_action") for r in records
    ]
    no_action_metrics = compute_policy_metrics("NO-ACTION", no_action_outcomes)

    # 2. Run FIXED-RETRY policy
    fixed_retry_outcomes = [
        simulate_record_outcome(r, fixed_retry_baseline, "fixed_retry") for r in records
    ]
    fixed_retry_metrics = compute_policy_metrics("FIXED-RETRY", fixed_retry_outcomes)

    # 3. Run RECLAIM policy
    reclaim_outcomes = [
        simulate_record_outcome(r, reclaim_evaluate, "reclaim") for r in records
    ]
    reclaim_metrics = compute_policy_metrics("RECLAIM", reclaim_outcomes)

    # Assert NO-ACTION recovered is less than FIXED-RETRY
    assert no_action_metrics.total_recovered_paise < fixed_retry_metrics.total_recovered_paise

    # Assert math correctness: total at risk = 10 * 100,000 = 1,000,000 paise (₹10,000)
    assert no_action_metrics.total_at_risk_paise == 1000000
    assert fixed_retry_metrics.total_at_risk_paise == 1000000

    # Verify per-policy contact counts differ
    assert no_action_metrics.contact_count == 0
    assert fixed_retry_metrics.contact_count == 10
    assert reclaim_metrics.contact_count <= 10

    # Verify causal consistency: any record that self-resolves under NO-ACTION
    # is also recovered under active intervention policies (treatment monotonicity).
    no_action_recovered_ids = {o.event_id for o in no_action_outcomes if o.outcome_recovered}
    fixed_recovered_ids = {o.event_id for o in fixed_retry_outcomes if o.outcome_recovered}
    reclaim_recovered_ids = {o.event_id for o in reclaim_outcomes if o.outcome_recovered}

    assert no_action_recovered_ids.issubset(fixed_recovered_ids)
    assert no_action_recovered_ids.issubset(reclaim_recovered_ids)

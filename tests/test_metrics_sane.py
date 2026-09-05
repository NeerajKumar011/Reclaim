"""Unit test verifying Sanity of Computed Metrics."""

import pytest

from reclaim.eval.metrics import compute_all_metrics
from reclaim.eval.replay import replay_heldout_dataset


def test_metrics_sanity_on_heldout_dataset():
    """Run replay engine on held-out test set and verify sanity bounds of computed metrics."""
    replay_results = replay_heldout_dataset()
    metrics_map = compute_all_metrics(replay_results)

    assert "NO-ACTION" in metrics_map
    assert "FIXED-RETRY" in metrics_map
    assert "FIXED-DUNNING" in metrics_map
    assert "RECLAIM" in metrics_map

    for name, m in metrics_map.items():
        # Recovery rate must be between 0.0 and 1.0
        assert 0.0 <= m.recovery_rate <= 1.0, f"{name} recovery_rate out of bounds: {m.recovery_rate}"

        # Total recovered <= total at risk
        assert m.total_recovered_paise <= m.total_at_risk_paise

        # Contact count must be non-negative
        assert m.contact_count >= 0

        # Cost per recovered rupee must be non-negative
        assert m.cost_per_recovered_rupee >= 0.0

    # RECLAIM specific constraints
    reclaim_metrics = metrics_map["RECLAIM"]
    assert (
        reclaim_metrics.policy_violation_count == 0
    ), f"RECLAIM policy violations must be 0, found: {reclaim_metrics.policy_violation_count}"

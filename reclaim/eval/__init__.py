"""Evaluation package — baselines, replay engine, metrics, and report generator."""

from reclaim.eval.baselines import (
    fixed_dunning_ladder_baseline,
    fixed_retry_baseline,
    no_intervention_baseline,
)
from reclaim.eval.metrics import PolicyMetrics, compute_all_metrics
from reclaim.eval.replay import replay_heldout_dataset
from reclaim.eval.report import run_evaluation

__all__ = [
    "no_intervention_baseline",
    "fixed_retry_baseline",
    "fixed_dunning_ladder_baseline",
    "replay_heldout_dataset",
    "compute_all_metrics",
    "PolicyMetrics",
    "run_evaluation",
]

"""Unit test verifying Ground Truth Isolation during Replay.

Asserts that diagnosis and policy functions never receive ground_truth fields as input.
"""

import inspect
from unittest.mock import MagicMock, patch

import pytest

from reclaim.eval.replay import simulate_record_outcome
from reclaim.policy.rules import evaluate as reclaim_evaluate


def test_policy_function_signature_no_ground_truth():
    """Inspect reclaim.policy.rules.evaluate signature to confirm ground_truth is not a parameter."""
    sig = inspect.signature(reclaim_evaluate)
    param_names = list(sig.parameters.keys())

    assert "ground_truth" not in param_names
    assert "actually_recovered" not in param_names
    assert "true_cause" not in param_names


def test_simulate_record_outcome_ground_truth_isolation():
    """Mock policy function and verify call args do NOT include ground_truth dictionary."""
    dummy_record = {
        "event_id": "test_leak_001",
        "event_category": "payment_failure",
        "customer_id": "cust_leak_123",
        "amount": 50000,
        "currency": "INR",
        "failure_reason_raw": "GATEWAY_TIMEOUT",
        "source_metadata": {
            "customer_segment": "returning",
            "historical_response": "high",
        },
        "ground_truth": {
            "true_cause": "OTP_TIMEOUT",
            "true_recovery_probability": 0.85,
            "actually_recovered": True,
        },
    }

    mock_policy = MagicMock(side_effect=reclaim_evaluate)

    outcome = simulate_record_outcome(
        record=dummy_record,
        policy_func=mock_policy,
        policy_name="reclaim",
    )

    # Inspect call args of mock_policy
    assert mock_policy.called
    call_args, call_kwargs = mock_policy.call_args

    # Check positional args
    for arg in call_args:
        if isinstance(arg, dict):
            assert "ground_truth" not in arg

    # Check keyword args
    for k, v in call_kwargs.items():
        assert k not in ("ground_truth", "true_cause", "actually_recovered")
        if isinstance(v, dict):
            assert "ground_truth" not in v

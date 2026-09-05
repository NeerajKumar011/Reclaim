"""Tests for ML Model vs Heuristic Baseline Evaluation.

Verifies:
1. evaluate_models() runs cleanly on validation.jsonl.
2. Returns comparable metrics dicts for both ML and heuristic baseline.
3. Neither model touches test_holdout.jsonl.
"""

from pathlib import Path
import pytest

from reclaim.diagnosis.evaluate_model import evaluate_models, VAL_JSONL_PATH
from reclaim.synthetic_data.generator import generate_dataset


@pytest.fixture(scope="module", autouse=True)
def ensure_datasets_exist():
    """Ensure synthetic data files are present."""
    if not VAL_JSONL_PATH.exists():
        generate_dataset(total_records=1000, seed=42)


def test_evaluate_models_metrics_structure():
    """Verify evaluate_models returns valid metrics dict for both models."""
    results = evaluate_models(val_path=VAL_JSONL_PATH)

    assert "heuristic" in results
    assert "ml_model" in results

    heuristic_m = results["heuristic"]
    ml_m = results["ml_model"]

    for metric in ["accuracy", "precision", "recall", "f1"]:
        assert metric in heuristic_m
        assert metric in ml_m
        assert 0.0 <= heuristic_m[metric] <= 1.0
        assert 0.0 <= ml_m[metric] <= 1.0


def test_holdout_protection():
    """Verify loading test_holdout.jsonl in evaluate_models triggers a protection error."""
    holdout_path = VAL_JSONL_PATH.parent / "test_holdout.jsonl"
    with pytest.raises((ValueError, AssertionError)):
        evaluate_models(val_path=holdout_path)


def test_live_inference_feature_vector_alignment():
    """Verify live inference feature vectors match training feature schema and separate raw failure reason from AI diagnosis."""
    from reclaim.diagnosis.ml_recovery_model import extract_features, RecoveryMLModel

    # Training record example
    train_record = {
        "amount": 99900,
        "event_category": "payment_failure",
        "failure_reason_raw": "BAD_REQUEST_ERROR",
        "source_metadata": {
            "prior_retry_count": 1,
            "day_of_month": 15,
            "customer_segment": "returning",
            "historical_response": "high",
        },
    }

    # Live inference record constructed in dispatcher.py
    live_record = {
        "amount": 99900,
        "event_category": "payment_failure",
        "failure_reason_raw": "BAD_REQUEST_ERROR",  # Raw gateway code
        "diagnosed_cause": "INSUFFICIENT_FUNDS",    # AI diagnosis kept separate
        "diagnosis_confidence": 0.99,
        "source_metadata": {
            "prior_retry_count": 1,
            "day_of_month": 15,
            "customer_segment": "returning",
            "historical_response": "high",
        },
    }

    train_num, train_cat = extract_features(train_record)
    live_num, live_cat = extract_features(live_record)

    assert len(train_num) == len(live_num) == 3
    assert len(train_cat) == len(live_cat) == 4
    assert train_cat[1] == live_cat[1] == "BAD_REQUEST_ERROR"
    assert live_record["diagnosed_cause"] == "INSUFFICIENT_FUNDS"
    assert live_record["diagnosed_cause"] != live_record["failure_reason_raw"]

    # Model can predict proba on live inference dict
    train_rec1 = {**train_record, "ground_truth": {"actually_recovered": False}}
    train_rec2 = {**train_record, "ground_truth": {"actually_recovered": True}}
    model = RecoveryMLModel()
    model.train([train_rec1, train_rec2])
    probs = model.predict_proba([live_record])
    assert len(probs) == 1
    assert 0.0 <= probs[0] <= 1.0


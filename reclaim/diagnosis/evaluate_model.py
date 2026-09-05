"""Model Evaluation Script.

Evaluates the ML recovery model against the heuristic baseline on validation.jsonl.
Calculates Accuracy, Precision, Recall, and F1-score for both approaches.

CRITICAL RESTRICTION:
  Do NOT load or evaluate test_holdout.jsonl in this script!
  test_holdout.jsonl is strictly reserved for Phase 5's evaluation harness.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List

import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

from reclaim.diagnosis.ml_recovery_model import (
    RecoveryMLModel,
    heuristic_predict,
    train_and_save_model,
    MODEL_SAVE_PATH,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "synthetic_data" / "output"
VAL_JSONL_PATH = DATA_DIR / "validation.jsonl"
TRAIN_JSONL_PATH = DATA_DIR / "train.jsonl"
HOLDOUT_JSONL_PATH = DATA_DIR / "test_holdout.jsonl"


def load_records(filepath: Path) -> List[Dict[str, Any]]:
    """Load JSONL records from file."""
    # RESTRICTION ASSERTION
    if "test_holdout" in filepath.name:
        raise ValueError(
            "FORBIDDEN: test_holdout.jsonl must NOT be evaluated in Phase 2! "
            "It is strictly reserved for Phase 5's evaluation harness."
        )

    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Calculate accuracy, precision, recall, and f1 score."""
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
    }


def evaluate_models(val_path: Path = VAL_JSONL_PATH) -> Dict[str, Dict[str, float]]:
    """Train ML model if needed, run ML model & heuristic baseline on validation dataset, and compare."""
    # Explicit check to guarantee test_holdout.jsonl is not touched
    assert "test_holdout" not in str(val_path), "test_holdout.jsonl is reserved for Phase 5 eval!"

    # Ensure train and val datasets exist
    if not val_path.exists() or not TRAIN_JSONL_PATH.exists():
        raise FileNotFoundError(
            "Synthetic datasets missing! Run `python -m reclaim.synthetic_data.generator` first."
        )

    val_records = load_records(val_path)
    y_true = np.array(
        [1 if r.get("ground_truth", {}).get("actually_recovered", False) else 0 for r in val_records]
    )

    # Train or load ML model
    ml_model = RecoveryMLModel()
    if not MODEL_SAVE_PATH.exists():
        logger.info("Trained model not found. Training on train.jsonl...")
        ml_model = train_and_save_model(TRAIN_JSONL_PATH)
    else:
        ml_model.load()

    # Predictions
    ml_preds = ml_model.predict(val_records)
    heuristic_preds = heuristic_predict(val_records)

    # Metrics calculation
    ml_metrics = calculate_metrics(y_true, ml_preds)
    heuristic_metrics = calculate_metrics(y_true, heuristic_preds)

    print("\n" + "=" * 60)
    print("RECLAIM MODEL EVALUATION REPORT (Validation Set)")
    print("=" * 60)
    print(f"Validation Records Evaluated: {len(val_records)}")
    print("-" * 60)
    print("HEURISTIC BASELINE METRICS:")
    print(f"  Accuracy : {heuristic_metrics['accuracy']:.4f}")
    print(f"  Precision: {heuristic_metrics['precision']:.4f}")
    print(f"  Recall   : {heuristic_metrics['recall']:.4f}")
    print(f"  F1 Score : {heuristic_metrics['f1']:.4f}")
    print("-" * 60)
    print("ML RECOVERY MODEL METRICS:")
    print(f"  Accuracy : {ml_metrics['accuracy']:.4f}")
    print(f"  Precision: {ml_metrics['precision']:.4f}")
    print(f"  Recall   : {ml_metrics['recall']:.4f}")
    print(f"  F1 Score : {ml_metrics['f1']:.4f}")
    print("-" * 60)

    diff_acc = ml_metrics['accuracy'] - heuristic_metrics['accuracy']
    diff_f1 = ml_metrics['f1'] - heuristic_metrics['f1']

    if ml_metrics['f1'] > heuristic_metrics['f1']:
        print(f"SUCCESS: ML Model beats Heuristic baseline by +{diff_f1:.4f} F1 (+{diff_acc:.4f} Accuracy)!")
    elif ml_metrics['f1'] == heuristic_metrics['f1']:
        print("RESULT: ML Model and Heuristic baseline achieved equal performance.")
    else:
        print(f"NOTE: Heuristic baseline outperformed ML Model by {-diff_f1:.4f} F1.")

    print("=" * 60 + "\n")

    return {
        "heuristic": heuristic_metrics,
        "ml_model": ml_metrics,
    }


if __name__ == "__main__":
    evaluate_models()

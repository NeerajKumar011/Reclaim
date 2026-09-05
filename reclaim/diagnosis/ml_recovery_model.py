"""ML Recovery Model & Heuristic Baseline.

Trains a scikit-learn GradientBoostingClassifier on train.jsonl causal features
to predict whether a payment event will actually be recovered.

Also implements a heuristic baseline function based on static cause base-rates
for benchmark comparison in evaluate_model.py.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import OneHotEncoder

from reclaim.synthetic_data.causal_config import BASE_RECOVERY_PROBABILITY

logger = logging.getLogger(__name__)

MODEL_SAVE_PATH = Path(__file__).parent / "output" / "recovery_model.joblib"
ENCODER_SAVE_PATH = Path(__file__).parent / "output" / "feature_encoder.joblib"


def extract_features(record: Dict[str, Any]) -> Tuple[List[float], List[str]]:
    """Extract raw numerical & categorical features from a synthetic event record."""
    meta = record.get("source_metadata", {})
    amount_paise = float(record.get("amount", 0))
    log_amount = float(np.log1p(amount_paise))

    event_category = str(record.get("event_category", "payment_failure"))
    failure_reason_raw = str(record.get("failure_reason_raw", "UNKNOWN"))
    customer_segment = str(meta.get("customer_segment", "new"))
    historical_response = str(meta.get("historical_response", "none"))

    prior_retry_count = float(meta.get("prior_retry_count", 0))
    day_of_month = float(meta.get("day_of_month", 15))

    num_features = [log_amount, prior_retry_count, day_of_month]
    cat_features = [event_category, failure_reason_raw, customer_segment, historical_response]

    return num_features, cat_features


class RecoveryMLModel:
    """Non-LLM Machine Learning classifier predicting payment recovery probability."""

    def __init__(self):
        self.clf = GradientBoostingClassifier(n_estimators=100, max_depth=4, random_state=42)
        self.encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        self.is_fitted = False

    def _prepare_dataset(self, records: List[Dict[str, Any]], is_train: bool = False) -> Tuple[np.ndarray, np.ndarray]:
        """Convert a list of record dicts into feature matrix X and target array y."""
        num_list = []
        cat_list = []
        y_list = []

        for rec in records:
            num_f, cat_f = extract_features(rec)
            num_list.append(num_f)
            cat_list.append(cat_f)
            gt = rec.get("ground_truth", {})
            y_list.append(1 if gt.get("actually_recovered", False) else 0)

        num_arr = np.array(num_list, dtype=np.float32)

        if is_train:
            cat_encoded = self.encoder.fit_transform(cat_list)
        else:
            cat_encoded = self.encoder.transform(cat_list)

        X = np.hstack([num_arr, cat_encoded])
        y = np.array(y_list, dtype=np.int32)
        return X, y

    def train(self, train_records: List[Dict[str, Any]]):
        """Train the classifier on synthetic training records."""
        X_train, y_train = self._prepare_dataset(train_records, is_train=True)
        self.clf.fit(X_train, y_train)
        self.is_fitted = True

    def predict_proba(self, records: List[Dict[str, Any]]) -> np.ndarray:
        """Predict recovery probability array for input records."""
        if not self.is_fitted:
            raise RuntimeError("Model is not trained yet! Call train() or load() first.")
        X, _ = self._prepare_dataset(records, is_train=False)
        return self.clf.predict_proba(X)[:, 1]

    def predict(self, records: List[Dict[str, Any]], threshold: float = 0.50) -> np.ndarray:
        """Predict binary recovery outcome (0 or 1) using probability threshold."""
        probs = self.predict_proba(records)
        return (probs >= threshold).astype(int)

    def save(self, model_path: Path = MODEL_SAVE_PATH, encoder_path: Path = ENCODER_SAVE_PATH):
        """Save trained model and feature encoder to disk."""
        model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.clf, model_path)
        joblib.dump(self.encoder, encoder_path)
        logger.info(f"Saved ML recovery model to {model_path}")

    def load(self, model_path: Path = MODEL_SAVE_PATH, encoder_path: Path = ENCODER_SAVE_PATH):
        """Load trained model and feature encoder from disk."""
        self.clf = joblib.load(model_path)
        self.encoder = joblib.load(encoder_path)
        self.is_fitted = True


# ---------------------------------------------------------------------------
# Heuristic Baseline Implementation
# ---------------------------------------------------------------------------

def _infer_cause_from_record(record: Dict[str, Any]) -> str:
    """Heuristically infer cause from raw record fields without ML."""
    reason = str(record.get("failure_reason_raw", "")).upper()
    category = record.get("event_category", "")

    if "BALANCE" in reason or "INSUFFICIENT" in reason or reason == "BAD_REQUEST_ERROR":
        return "INSUFFICIENT_FUNDS"
    elif "TIMEOUT" in reason or "OTP" in reason:
        return "OTP_TIMEOUT"
    elif "GATEWAY" in reason or "DOWN" in reason or "BANK" in reason:
        return "BANK_RAIL_DOWN"
    elif "CANCEL" in reason or "ABORT" in reason or "CLOSED" in reason:
        return "AUTH_ABORT"
    elif "DISPUTE" in reason or "PO" in reason:
        return "B2B_DISPUTE"
    elif "OVERDUE" in reason or "CREDIT" in reason:
        return "B2B_CASH_CONSTRAINED"
    elif category == "cart_abandonment":
        return "GENUINE_ABANDON"
    elif category == "invoice_overdue":
        return "B2B_CASH_CONSTRAINED"
    return "INSUFFICIENT_FUNDS"  # default fallback


def heuristic_predict_prob(record: Dict[str, Any]) -> float:
    """Heuristic baseline prediction: returns static cause base recovery rate."""
    cause = _infer_cause_from_record(record)
    return BASE_RECOVERY_PROBABILITY.get(cause, 0.50)


def heuristic_predict(records: List[Dict[str, Any]], threshold: float = 0.50) -> np.ndarray:
    """Heuristic baseline predictions (0 or 1 array) for a list of records."""
    probs = np.array([heuristic_predict_prob(r) for r in records])
    return (probs >= threshold).astype(int)


def train_and_save_model(train_jsonl_path: Path) -> RecoveryMLModel:
    """Utility to load train.jsonl, train model, and save to disk."""
    records = []
    with open(train_jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    model = RecoveryMLModel()
    model.train(records)
    model.save()
    return model

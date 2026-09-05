"""Synthetic Data Generator for RECLAIM.

Generates 10,000 RevenueEvent-shaped records split 70/15/15 into:
  - train.jsonl (7,000 records)
  - validation.jsonl (1,500 records)
  - test_holdout.jsonl (1,500 records)

Each record contains valid RevenueEvent fields PLUS a `ground_truth` object:
  {"true_cause": ..., "true_recovery_probability": ..., "actually_recovered": bool}
"""

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List

from reclaim.synthetic_data.causal_config import (
    BASE_RECOVERY_PROBABILITY,
    EVENT_CATEGORY_CAUSE_PROBABILITIES,
    AMOUNT_BUCKET_FACTORS,
    CUSTOMER_SEGMENT_FACTORS,
    HISTORICAL_RESPONSE_FACTORS,
    get_amount_bucket,
    get_day_of_month_factor,
    get_retry_factor,
)

OUTPUT_DIR = Path(__file__).parent / "output"
FIXED_BASE_EPOCH = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

# Mapping from true_cause to realistic Razorpay raw failure codes
CAUSE_TO_RAW_FAILURE_REASON: Dict[str, List[str]] = {
    "INSUFFICIENT_FUNDS": ["BAD_REQUEST_ERROR", "INSUFFICIENT_FUNDS", "PAYMENT_FAILED_LOW_BALANCE"],
    "OTP_TIMEOUT": ["GATEWAY_TIMEOUT", "OTP_EXPIRED", "AUTHENTICATION_TIMEOUT"],
    "BANK_RAIL_DOWN": ["GATEWAY_ERROR", "BANK_SERVER_UNAVAILABLE", "NPCI_DOWN"],
    "AUTH_ABORT": ["USER_CANCELLED", "AUTH_DROPPED_BY_USER", "CHECKOUT_CLOSED"],
    "GENUINE_ABANDON": ["CHECKOUT_ABANDONED", "USER_EXIT"],
    "B2B_CASH_CONSTRAINED": ["PAYMENT_OVERDUE", "CREDIT_PERIOD_EXCEEDED"],
    "B2B_DISPUTE": ["INVOICE_DISPUTE", "PO_MISMATCH"],
}


def sample_from_dist(dist: Dict[str, float]) -> str:
    """Sample a key from a probability distribution dict."""
    keys = list(dist.keys())
    weights = list(dist.values())
    return random.choices(keys, weights=weights, k=1)[0]


def generate_single_event(seed_index: int) -> Dict[str, Any]:
    """Generate one synthetic event record with ground truth."""

    # Select event category (60% payment_failure, 25% cart_abandonment, 15% invoice_overdue)
    category_dist = {
        "payment_failure": 0.60,
        "cart_abandonment": 0.25,
        "invoice_overdue": 0.15,
    }
    event_category = sample_from_dist(category_dist)

    # Sample root cause given event_category
    cause_dist = EVENT_CATEGORY_CAUSE_PROBABILITIES[event_category]
    true_cause = sample_from_dist(cause_dist)

    # Deterministic customer profile from seed_index
    customer_uuid = f"cust_synth_{seed_index % 1000:06d}"
    customer_segment = random.choices(
        ["new", "returning", "vip"], weights=[0.4, 0.5, 0.1], k=1
    )[0]
    historical_response = random.choices(
        ["high", "medium", "low", "none"], weights=[0.25, 0.40, 0.25, 0.10], k=1
    )[0]

    # Generate timestamp within the last 30 days from FIXED_BASE_EPOCH
    days_ago = random.uniform(0, 30)
    event_time = FIXED_BASE_EPOCH - timedelta(days=days_ago)
    day_of_month = event_time.day

    # Amount in paise (₹100 to ₹100,000)
    if event_category == "invoice_overdue":
        amount_paise = random.randint(500000, 10000000)  # ₹5,000 to ₹100,000
    else:
        amount_paise = random.randint(10000, 1000000)    # ₹100 to ₹10,000

    # Retry count
    prior_retry_count = random.choices([0, 1, 2, 3], weights=[0.6, 0.25, 0.1, 0.05], k=1)[0]

    # Raw failure reason code
    failure_codes = CAUSE_TO_RAW_FAILURE_REASON.get(true_cause, ["UNKNOWN_ERROR"])
    failure_reason_raw = random.choice(failure_codes)

    # Calculate true recovery probability using causal factors
    base_prob = BASE_RECOVERY_PROBABILITY[true_cause]
    amount_bucket = get_amount_bucket(amount_paise)
    amount_factor = AMOUNT_BUCKET_FACTORS.get(amount_bucket, 1.0)
    day_factor = get_day_of_month_factor(day_of_month, true_cause)
    retry_factor = get_retry_factor(prior_retry_count)
    segment_factor = CUSTOMER_SEGMENT_FACTORS.get(customer_segment, 1.0)
    response_factor = HISTORICAL_RESPONSE_FACTORS.get(historical_response, 1.0)

    raw_prob = (
        base_prob
        * amount_factor
        * day_factor
        * retry_factor
        * segment_factor
        * response_factor
    )

    # Clamp probability to [0.01, 0.99]
    true_recovery_prob = round(max(0.01, min(0.99, raw_prob)), 4)

    # Simulate actual recovery outcome
    actually_recovered = random.random() < true_recovery_prob

    # Generate IDs
    payment_id = f"pay_synth_{seed_index:06d}"
    order_id = f"order_synth_{seed_index:06d}"
    event_id = f"{event_category}:{payment_id}"

    # Build RevenueEvent compatible dict
    record = {
        "event_id": event_id,
        "event_category": event_category,
        "customer_id": customer_uuid,
        "amount": amount_paise,
        "currency": "INR",
        "failure_reason_raw": failure_reason_raw,
        "occurred_at": event_time.isoformat(),
        "source_metadata": {
            "payment_id": payment_id,
            "order_id": order_id,
            "method": random.choice(["upi", "card", "netbanking"]),
            "customer_segment": customer_segment,
            "prior_retry_count": prior_retry_count,
            "day_of_month": day_of_month,
            "historical_response": historical_response,
        },
        "ground_truth": {
            "true_cause": true_cause,
            "true_recovery_probability": true_recovery_prob,
            "actually_recovered": actually_recovered,
        },
    }

    return record


def generate_dataset(
    total_records: int = 10000,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    seed: int = 42,
    output_dir: Path | None = None,
) -> Dict[str, int]:
    """Generate total_records synthetic events and save into train, val, test_holdout JSONL files."""
    random.seed(seed)
    target_dir = output_dir or OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    n_train = int(total_records * train_ratio)
    n_val = int(total_records * val_ratio)
    n_test = total_records - n_train - n_val

    all_records = [generate_single_event(i) for i in range(total_records)]

    train_records = all_records[:n_train]
    val_records = all_records[n_train : n_train + n_val]
    test_records = all_records[n_train + n_val :]

    splits = {
        "train.jsonl": train_records,
        "validation.jsonl": val_records,
        "test_holdout.jsonl": test_records,
    }

    counts = {}
    for filename, records in splits.items():
        filepath = target_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")
        counts[filename] = len(records)

    print(f"Generated synthetic dataset in {target_dir}:")
    for fname, count in counts.items():
        print(f"  - {fname}: {count} records")

    return counts


if __name__ == "__main__":
    generate_dataset()

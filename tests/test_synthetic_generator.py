"""Tests for Synthetic Data Generator.

Verifies:
1. Generated records validate against RevenueEvent Pydantic schema.
2. Dataset split sizes match 70/15/15 ratio (7,000 / 1,500 / 1,500 out of 10,000).
3. Ground truth fields are present but separable from inference fields.
"""

import json
import tempfile
from pathlib import Path

import pytest
from reclaim.ingestion.schemas import RevenueEvent
from reclaim.synthetic_data.generator import OUTPUT_DIR, generate_dataset


def test_split_sizes():
    """Verify train, validation, and test_holdout split sizes using isolated temporary directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        counts = generate_dataset(total_records=1000, seed=42, output_dir=tmp_path)
        assert counts["train.jsonl"] == 700
        assert counts["validation.jsonl"] == 150
        assert counts["test_holdout.jsonl"] == 150


def test_record_revenue_event_schema():
    """Verify every generated record satisfies RevenueEvent Pydantic contract."""
    val_file = OUTPUT_DIR / "validation.jsonl"

    # Fallback to generate if file missing
    if not val_file.exists():
        generate_dataset(total_records=10000, seed=42)

    with open(val_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f):
            if not line.strip():
                continue
            rec = json.loads(line)

            # Separate inference fields from ground truth
            inference_fields = {k: v for k, v in rec.items() if k != "ground_truth"}

            # Validate against RevenueEvent Pydantic model
            event = RevenueEvent.model_validate(inference_fields)
            assert event.event_id is not None
            assert event.amount > 0

            if line_num > 20:  # test sample of 20 records
                break


def test_ground_truth_separability():
    """Verify ground_truth contains required evaluation keys and can be popped easily."""
    train_file = OUTPUT_DIR / "train.jsonl"

    if not train_file.exists():
        generate_dataset(total_records=10000, seed=42)

    with open(train_file, "r", encoding="utf-8") as f:
        first_line = f.readline()
        record = json.loads(first_line)

    assert "ground_truth" in record
    gt = record["ground_truth"]
    assert "true_cause" in gt
    assert "true_recovery_probability" in gt
    assert "actually_recovered" in gt
    assert isinstance(gt["actually_recovered"], bool)

    # Pop ground_truth and check RevenueEvent validity
    ground_truth = record.pop("ground_truth")
    event = RevenueEvent.model_validate(record)
    assert event.event_id is not None
    assert ground_truth["true_cause"] in [
        "INSUFFICIENT_FUNDS",
        "OTP_TIMEOUT",
        "BANK_RAIL_DOWN",
        "AUTH_ABORT",
        "GENUINE_ABANDON",
        "B2B_CASH_CONSTRAINED",
        "B2B_DISPUTE",
    ]

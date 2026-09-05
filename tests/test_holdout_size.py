"""Unit test asserting held-out test dataset size."""

from reclaim.eval.replay import TEST_HOLDOUT_PATH, load_holdout_records


def test_holdout_dataset_has_1500_records():
    """Assert test_holdout.jsonl has exactly 1,500 records."""
    assert TEST_HOLDOUT_PATH.exists(), f"Held-out dataset missing at {TEST_HOLDOUT_PATH}"
    records = load_holdout_records(TEST_HOLDOUT_PATH)
    assert len(records) == 1500, f"Expected 1500 held-out records, found {len(records)}"

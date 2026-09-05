import json
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from reclaim.diagnosis.ml_recovery_model import RecoveryMLModel

if __name__ == "__main__":
    train_path = Path(__file__).parent.parent / "reclaim" / "synthetic_data" / "output" / "train.jsonl"
    records = []
    with open(train_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    model = RecoveryMLModel()
    model.train(records)
    model.save()
    print(f"Successfully retrained and saved ML model on {len(records)} training records!")

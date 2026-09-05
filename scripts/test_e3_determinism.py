"""E3 determinism test: run generator twice with same seed, compare SHA256 hashes."""
import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from reclaim.synthetic_data.generator import generate_dataset

with tempfile.TemporaryDirectory() as d1:
    generate_dataset(total_records=100, seed=42, output_dir=Path(d1))
    with open(Path(d1) / "test_holdout.jsonl", "rb") as f:
        h1 = hashlib.sha256(f.read()).hexdigest()

with tempfile.TemporaryDirectory() as d2:
    generate_dataset(total_records=100, seed=42, output_dir=Path(d2))
    with open(Path(d2) / "test_holdout.jsonl", "rb") as f:
        h2 = hashlib.sha256(f.read()).hexdigest()

print(f"Run 1 SHA256: {h1}")
print(f"Run 2 SHA256: {h2}")
print(f"MATCH: {h1 == h2}")
assert h1 == h2, "FAIL: dataset outputs differ between runs with same seed!"
print("PASS: byte-identical output confirmed.")

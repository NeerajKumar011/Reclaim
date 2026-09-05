"""Run the N=150 eval in pure-heuristic mode (no LLM calls).

Patches the LLM client so every call immediately raises DiagnosisValidationError
instead of hitting the Gemini API. The FailureClassifier catches that and falls
back to heuristic_classify. The scoreboard is then produced using 100% heuristic
diagnosis — documented in the output as such.

Usage:
    python scripts/run_heuristic_eval.py --sample-size 150
"""

import os
import sys
import argparse
from pathlib import Path

os.environ["RECLAIM_FORCE_HEURISTIC"] = "1"

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Patch LLM BEFORE any reclaim imports read the API key
from reclaim.diagnosis.schemas import DiagnosisValidationError

import reclaim.diagnosis.classifier as _clf
import reclaim.diagnosis.llm_client as _llm

def _heuristic_only_classify(self, event, customer_history=None, mock_response=None):
    return _clf.heuristic_classify(event)

_clf.FailureClassifier.classify = _heuristic_only_classify
_llm.LLMClient.generate_structured = lambda self, *a, **kw: (_ for _ in ()).throw(
    DiagnosisValidationError("HEURISTIC-ONLY MODE")
)

# Now safe to import eval modules
from reclaim.eval.report import run_evaluation

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-size", "-n", type=int, default=150)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print(f"\n[MODE] Heuristic-only (LLM disabled — daily quota exhausted)")
    print(f"[MODE] All diagnoses use heuristic_classify(); no Gemini API calls made.\n")
    run_evaluation(sample_size=args.sample_size, seed=args.seed)

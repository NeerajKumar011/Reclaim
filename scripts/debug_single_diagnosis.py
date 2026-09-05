"""debug_single_diagnosis.py — Verify Gemini connectivity in isolation.

Constructs one real, non-mocked RevenueEvent and runs it through
FailureClassifier.classify() without any mock_response. Prints:
  - Whether GEMINI_API_KEY is set and its length
  - The raw Gemini response text
  - The parsed DiagnosisOutput
  - The module-level Gemini call counter after the call

Usage:
    python scripts/debug_single_diagnosis.py
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging so we can see INFO-level output from LLMClient
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)

from reclaim.config import get_settings
from reclaim.diagnosis.classifier import FailureClassifier
import reclaim.diagnosis.llm_client as _llm_mod
from reclaim.ingestion.schemas import EventCategory, RevenueEvent


def main() -> None:
    # --- 1. API key presence check ---
    settings = get_settings()
    key = settings.GEMINI_API_KEY
    if key:
        print(f"\n[CONFIG] GEMINI_API_KEY is SET, length={len(key)}")
    else:
        print("\n[CONFIG] GEMINI_API_KEY is EMPTY — Gemini calls will fail and fall back to heuristic!")

    # --- 2. Build a real RevenueEvent (no mock, no ground_truth) ---
    event = RevenueEvent(
        event_id="debug-001",
        customer_id="cust-debug-nk",
        amount=49900,  # ₹499.00
        currency="INR",
        event_category=EventCategory.payment_failure,
        failure_reason_raw="BAD_REQUEST_ERROR",
        occurred_at=datetime(2026, 8, 15, 9, 30, 0, tzinfo=timezone.utc),
        source_metadata={
            "method": "upi",
            "bank": "HDFC",
            "historical_response": "medium",
        },
    )

    print(f"\n[EVENT] Constructed RevenueEvent:")
    print(f"  event_id       = {event.event_id}")
    print(f"  event_category = {event.event_category.value}")
    print(f"  amount         = Rs.{float(event.amount) / 100:.2f}")
    print(f"  failure_reason = {event.failure_reason_raw}")

    # --- 3. Run classifier (real LLM call, no mock_response) ---
    print("\n[CLASSIFIER] Calling FailureClassifier.classify() — this will hit Gemini if key is set...")

    # Monkey-patch to capture raw response for display (without altering _call_llm logic)
    _raw_response_holder: list = []
    _original_call_llm = _llm_mod.LLMClient._call_llm

    def _capturing_call_llm(self, prompt: str, system_prompt=None) -> str:
        result = _original_call_llm(self, prompt, system_prompt)
        _raw_response_holder.append(result)
        return result

    _llm_mod.LLMClient._call_llm = _capturing_call_llm  # type: ignore[method-assign]

    try:
        classifier = FailureClassifier()
        diagnosis = classifier.classify(event)
    finally:
        _llm_mod.LLMClient._call_llm = _original_call_llm  # type: ignore[method-assign]

    # --- 4. Report results ---
    print(f"\n[RESULT] DiagnosisOutput:")
    print(f"  cause      = {diagnosis.cause}")
    print(f"  confidence = {diagnosis.confidence:.4f}")

    if _raw_response_holder:
        raw = _raw_response_holder[0]
        print(f"\n[RAW GEMINI RESPONSE] (length={len(raw)} chars):")
        print("-" * 60)
        print(raw)
        print("-" * 60)
    else:
        print("\n[RAW GEMINI RESPONSE] No raw response captured — LLM was not called (fell back to heuristic).")

    counter = _llm_mod._gemini_call_counter
    print(f"\n[COUNTER] _gemini_call_counter after this run = {counter}")
    if counter == 0:
        print("  [WARNING] Counter is 0 - Gemini SDK was NOT reached. Check GEMINI_API_KEY and model name.")
    else:
        print(f"  [OK] Counter incremented to {counter} - Gemini SDK was called successfully.")



if __name__ == "__main__":
    main()

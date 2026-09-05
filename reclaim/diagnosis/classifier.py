"""Failure Classifier — Diagnoses the root cause of a RevenueEvent.

Uses LLMClient to classify payment failures, cart abandonments, and overdue invoices
into the fixed RECLAIM taxonomy:
  - INSUFFICIENT_FUNDS
  - OTP_TIMEOUT
  - BANK_RAIL_DOWN
  - AUTH_ABORT
  - GENUINE_ABANDON
  - B2B_CASH_CONSTRAINED
  - B2B_DISPUTE
"""

import logging
from typing import Dict, Any, Optional

from reclaim.diagnosis.llm_client import LLMClient
from reclaim.diagnosis.schemas import DiagnosisOutput, DiagnosisValidationError
from reclaim.ingestion.schemas import RevenueEvent

logger = logging.getLogger(__name__)


PROMPT_TEMPLATE = """You are RECLAIM's Payment Failure Diagnosis System.

Analyze the following payment event and determine the root cause of failure.

=== EVENT CONTEXT ===
- Event Category: {event_category}
- Raw Failure Reason: {failure_reason_raw}
- Amount (in paise): {amount_paise} (₹{amount_rupees:.2f})
- Currency: {currency}
- Customer History: {customer_history}
- Source Metadata: {source_metadata}

=== TAXONOMY (Choose EXACTLY ONE) ===
1. INSUFFICIENT_FUNDS    - Customer account lacked balance/credit limit
2. OTP_TIMEOUT           - SMS OTP failed, network timeout, or expired OTP
3. BANK_RAIL_DOWN        - Bank server outage, NPCI rail down, core banking error
4. AUTH_ABORT            - Customer manually closed payment/3DS window during auth
5. GENUINE_ABANDON       - Customer decided not to buy (window shopping, price check)
6. B2B_CASH_CONSTRAINED  - Overdue B2B invoice due to working capital/cash flow delay
7. B2B_DISPUTE           - Overdue B2B invoice due to billing, PO, or quality dispute

=== INSTRUCTIONS ===
- Output JSON strictly matching this schema:
  {{
    "cause": "<ONE_OF_TAXONOMY_ABOVE>",
    "confidence": <float_between_0_and_1>
  }}
- Do NOT output any other text outside the JSON.
"""

SYSTEM_PROMPT = "You are an expert payment risk analyst. You output strictly valid JSON matching the requested schema."



def heuristic_classify(record_or_event: Dict[str, Any] | RevenueEvent) -> DiagnosisOutput:
    """Deterministically diagnose root cause and confidence from record features when LLM is unavailable."""
    if isinstance(record_or_event, RevenueEvent):
        reason = str(record_or_event.failure_reason_raw or "").upper()
        category = record_or_event.event_category.value
    else:
        reason = str(record_or_event.get("failure_reason_raw", "")).upper()
        category = str(record_or_event.get("event_category", ""))

    if "OTP" in reason or "TIMEOUT" in reason or "EXPIRED" in reason:
        return DiagnosisOutput(cause="OTP_TIMEOUT", confidence=0.92)
    elif "BANK" in reason or "DOWN" in reason or "NPCI" in reason or "GATEWAY_ERROR" in reason:
        return DiagnosisOutput(cause="BANK_RAIL_DOWN", confidence=0.88)
    elif "CANCEL" in reason or "ABORT" in reason or "CLOSED" in reason or "USER_EXIT" in reason:
        return DiagnosisOutput(cause="AUTH_ABORT", confidence=0.85)
    elif "DISPUTE" in reason or "PO_MISMATCH" in reason:
        return DiagnosisOutput(cause="B2B_DISPUTE", confidence=0.82)
    elif "OVERDUE" in reason or "CREDIT" in reason or category == "invoice_overdue":
        return DiagnosisOutput(cause="B2B_CASH_CONSTRAINED", confidence=0.78)
    elif category == "cart_abandonment" or "ABANDON" in reason:
        return DiagnosisOutput(cause="GENUINE_ABANDON", confidence=0.80)
    elif "LOW_BALANCE" in reason or "INSUFFICIENT" in reason:
        return DiagnosisOutput(cause="INSUFFICIENT_FUNDS", confidence=0.85)
    elif "BAD_REQUEST" in reason or "PAYMENT_FAILED" in reason:
        # Generic failure code -> medium confidence (0.55), falling into Tier.REVIEW range [0.40, 0.70)
        return DiagnosisOutput(cause="INSUFFICIENT_FUNDS", confidence=0.55)
    else:
        # Unknown failure reason -> low confidence (0.35), falling below Tier.REVIEW threshold (0.40) -> routed to human queue
        return DiagnosisOutput(cause="INSUFFICIENT_FUNDS", confidence=0.35)


class FailureClassifier:
    """Classifies RevenueEvent failure root cause using LLM, with deterministic fallback."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def classify(
        self,
        event: RevenueEvent,
        customer_history: Optional[Dict[str, Any]] = None,
        mock_response: Optional[str] = None,
    ) -> DiagnosisOutput:
        """Diagnose root cause for a given RevenueEvent.

        Args:
            event: The normalized RevenueEvent instance.
            customer_history: Optional dict of past customer payment behavior.
            mock_response: Optional JSON string for offline testing/mocking.

        Returns:
            DiagnosisOutput containing diagnosed cause and confidence score.
        """
        if mock_response is not None:
            return self.llm_client.generate_structured(
                prompt="",
                schema_cls=DiagnosisOutput,
                mock_response=mock_response,
            )

        amount_rupees = float(event.amount) / 100.0
        prompt = PROMPT_TEMPLATE.format(
            event_category=event.event_category.value,
            failure_reason_raw=event.failure_reason_raw or "None",
            amount_paise=int(event.amount),
            amount_rupees=amount_rupees,
            currency=event.currency,
            customer_history=customer_history or {"prior_failures": 0, "prior_recoveries": 0},
            source_metadata=event.source_metadata,
        )

        try:
            return self.llm_client.generate_structured(
                prompt=prompt,
                schema_cls=DiagnosisOutput,
                system_prompt=SYSTEM_PROMPT,
            )
        except DiagnosisValidationError as dvexc:
            logger.warning(
                f"LLM diagnosis failed for event_id={getattr(event, 'event_id', '?')} — "
                f"falling back to heuristic_classify. Reason: {dvexc}"
            )
            return heuristic_classify(event)



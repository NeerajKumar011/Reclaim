"""Promise-to-Pay Extractor — Extracts payment commitment from customer text replies.

Uses LLMClient to analyze unstructured customer communications (WhatsApp / Email / SMS replies)
and extract:
  - promise: bool (did the customer commit to pay?)
  - date: Optional[str] (ISO date or descriptive promised pay date)
  - amount: Optional[int] (promised payment amount in paise)
  - confidence: float (0.0 to 1.0)

Includes deterministic heuristic parser for English & Hinglish as reliable fallback.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from reclaim.diagnosis.llm_client import LLMClient
from reclaim.diagnosis.schemas import PromiseToPayOutput, DiagnosisValidationError

PROMPT_TEMPLATE = """You are RECLAIM's Customer Response Analysis System.

Analyze the following customer message reply to a payment recovery nudge.

=== CUSTOMER MESSAGE ===
"{customer_reply}"

=== INSTRUCTIONS ===
1. Determine if the customer is making a clear commitment (promise) to pay.
2. If a date is mentioned (e.g., "tomorrow", "next Friday", "on 1st of next month"), extract or infer the date.
3. If an amount is mentioned, extract it in PAISE (100 paise = ₹1).
4. Output JSON strictly matching this schema:
  {{
    "promise": <true_or_false>,
    "date": <string_date_or_null>,
    "amount": <integer_amount_paise_or_null>,
    "confidence": <float_between_0_and_1>
  }}
- Output ONLY valid JSON matching the schema.
"""

SYSTEM_PROMPT = "You are a customer intent analysis assistant. Output strictly valid JSON."


def heuristic_extract_promise(customer_reply: str, base_date: Optional[datetime] = None) -> PromiseToPayOutput:
    """Deterministic rule-based extractor for English & Hinglish customer responses."""
    text = (customer_reply or "").strip().lower()
    now = base_date or datetime.now(timezone.utc)

    if not text:
        return PromiseToPayOutput(promise=False, date=None, amount=None, confidence=0.0)

    # Explicit Opt-Out / Refusal phrases
    opt_out_patterns = [
        r"\bstop\b", r"\bunsubscribe\b", r"\bdon'?t message\b", r"\bnot interested\b",
        r"\bnever\b", r"\bcancel\b", r"\bfraud\b", r"\bspam\b", r"\bwrong number\b"
    ]
    if any(re.search(p, text) for p in opt_out_patterns):
        return PromiseToPayOutput(promise=False, date=None, amount=None, confidence=0.95)

    # Promise commitment indicators (Hinglish + English)
    promise_indicators = [
        r"\bsalary\b", r"\bparso\b", r"\bkal\b", r"\btomorrow\b", r"\bnext week\b",
        r"\bpay kar dunga\b", r"\bkar dunga\b", r"\bpay karunga\b", r"\bclear karunga\b",
        r"\bwill pay\b", r"\bwill clear\b", r"\bpaying on\b", r"\bpromise\b",
        r"\bshaam ko\b", r"\bevening\b", r"\bby monday\b", r"\bby friday\b", r"\b1st\b"
    ]

    has_promise = any(re.search(p, text) for p in promise_indicators)

    # Date inference
    promised_date_str = None
    if "parso" in text or "day after tomorrow" in text:
        target = now + timedelta(days=2)
        promised_date_str = target.strftime("%Y-%m-%d")
    elif "kal" in text or "tomorrow" in text:
        target = now + timedelta(days=1)
        promised_date_str = target.strftime("%Y-%m-%d")
    elif "salary" in text:
        # Default typical salary payment window (end of month / next few days)
        target = now + timedelta(days=2)
        promised_date_str = target.strftime("%Y-%m-%d")
    elif "next week" in text:
        target = now + timedelta(days=7)
        promised_date_str = target.strftime("%Y-%m-%d")
    elif "shaam" in text or "evening" in text or "today" in text:
        promised_date_str = now.strftime("%Y-%m-%d")

    # Amount extraction (if any ₹ or Rs or numeric amount mentioned)
    amount_paise = None
    amt_match = re.search(r"(?:rs\.?|inr|₹)\s*([0-9,]+)", text)
    if amt_match:
        try:
            amt_num = int(amt_match.group(1).replace(",", ""))
            amount_paise = amt_num * 100
        except ValueError:
            amount_paise = None

    confidence = 0.90 if (has_promise and promised_date_str) else (0.75 if has_promise else 0.20)

    return PromiseToPayOutput(
        promise=has_promise,
        date=promised_date_str,
        amount=amount_paise,
        confidence=confidence,
    )


class PromiseExtractor:
    """Extracts structured PromiseToPayOutput from customer text reply."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def extract(
        self,
        customer_reply: str,
        mock_response: Optional[str] = None,
    ) -> PromiseToPayOutput:
        """Extract promise-to-pay commitment from customer reply text."""
        # Check if mock_response provided (offline testing)
        if mock_response:
            return self.llm_client.generate_structured(
                prompt=PROMPT_TEMPLATE.format(customer_reply=customer_reply),
                schema_cls=PromiseToPayOutput,
                system_prompt=SYSTEM_PROMPT,
                mock_response=mock_response,
            )

        # Try LLM if configured
        if self.llm_client.api_key and self.llm_client.client:
            try:
                prompt = PROMPT_TEMPLATE.format(customer_reply=customer_reply)
                return self.llm_client.generate_structured(
                    prompt=prompt,
                    schema_cls=PromiseToPayOutput,
                    system_prompt=SYSTEM_PROMPT,
                )
            except (DiagnosisValidationError, Exception):
                return heuristic_extract_promise(customer_reply)

        # Fast deterministic heuristic fallback
        return heuristic_extract_promise(customer_reply)

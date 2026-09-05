"""Promise-to-Pay Extractor — Extracts payment commitment from customer text replies.

Uses LLMClient to analyze unstructured customer communications (WhatsApp / Email / SMS replies)
and extract:
  - promise: bool (did the customer commit to pay?)
  - date: Optional[str] (ISO date or descriptive promised pay date)
  - amount: Optional[int] (promised payment amount in paise)
  - confidence: float (0.0 to 1.0)
"""

from typing import Optional

from reclaim.diagnosis.llm_client import LLMClient
from reclaim.diagnosis.schemas import PromiseToPayOutput

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


class PromiseExtractor:
    """Extracts structured PromiseToPayOutput from customer text reply."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def extract(
        self,
        customer_reply: str,
        mock_response: Optional[str] = None,
    ) -> PromiseToPayOutput:
        """Extract promise-to-pay commitment from customer reply text.

        Args:
            customer_reply: Free text reply from customer.
            mock_response: Optional JSON string for offline testing/mocking.

        Returns:
            PromiseToPayOutput instance.
        """
        prompt = PROMPT_TEMPLATE.format(customer_reply=customer_reply)

        return self.llm_client.generate_structured(
            prompt=prompt,
            schema_cls=PromiseToPayOutput,
            system_prompt=SYSTEM_PROMPT,
            mock_response=mock_response,
        )

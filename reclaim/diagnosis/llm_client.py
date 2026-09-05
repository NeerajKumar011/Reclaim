"""LLM Client Wrapper for Gemini & Groq APIs.

Handles structured JSON output parsing and validation against Pydantic schemas.
Retries once on validation failure before raising DiagnosisValidationError.

TODO (Phase 3 Handoff Point): Handled by Policy Engine. If DiagnosisValidationError is raised,
the Policy Engine catches it and falls back to a deterministic default recovery action.
"""

import json
import logging
import re
import time
from typing import Type, TypeVar, Optional, Any

from pydantic import BaseModel, ValidationError

from reclaim.config import get_settings
from reclaim.diagnosis.schemas import DiagnosisValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# SDK call counter — incremented ONLY when an actual SDK call is reached.
# Visible at INFO level for the first 3 calls to confirm live connectivity.
# ---------------------------------------------------------------------------
_gemini_call_counter: int = 0
_llm_call_counter: int = 0

MODEL_NAME = "gemini-3.5-flash-lite"
GROQ_MODEL_NAME = "llama-3.3-70b-versatile"


def _clean_json_text(text: str) -> str:
    """Extract JSON block from LLM output if wrapped in markdown fence."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


class LLMClient:
    """Wrapper around Gemini / Groq API with structured Pydantic response validation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ):
        settings = get_settings()
        self.provider = (provider or settings.LLM_PROVIDER or "gemini").lower()
        self._gemini_client = None
        self._groq_client = None

        if self.provider == "groq":
            self.api_key = api_key or settings.GROQ_API_KEY
            self.model = model or GROQ_MODEL_NAME
            if self.api_key:
                logger.info(
                    f"LLMClient initialised (Groq) — GROQ_API_KEY present, length={len(self.api_key)}, model={self.model}"
                )
            else:
                logger.warning(
                    "LLMClient initialised (Groq) — GROQ_API_KEY is EMPTY or not set. "
                    "Calls will raise DiagnosisValidationError and fall back to heuristic."
                )
        else:
            self.api_key = api_key or settings.GEMINI_API_KEY
            self.model = model or MODEL_NAME
            if self.api_key:
                logger.info(
                    f"LLMClient initialised (Gemini) — GEMINI_API_KEY present, length={len(self.api_key)}, model={self.model}"
                )
            else:
                logger.warning(
                    "LLMClient initialised (Gemini) — GEMINI_API_KEY is EMPTY or not set. "
                    "Calls will raise DiagnosisValidationError and fall back to heuristic."
                )

    @property
    def gemini_client(self):
        """Lazy-initialize Gemini client."""
        if self._gemini_client is None:
            if not self.api_key:
                return None
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=self.api_key)
            except ImportError:
                raise DiagnosisValidationError(
                    "google-genai package is not installed. Install with `pip install google-genai` to use Gemini provider."
                )
        return self._gemini_client

    @property
    def groq_client(self):
        """Lazy-initialize Groq client."""
        if self._groq_client is None:
            if not self.api_key:
                return None
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=self.api_key)
            except ImportError:
                raise DiagnosisValidationError(
                    "groq package is not installed. Install with `pip install groq` to use Groq provider."
                )
        return self._groq_client

    @property
    def client(self):
        """Lazy-initialize client for active provider."""
        if self.provider == "groq":
            return self.groq_client
        return self.gemini_client

    def generate_structured(
        self,
        prompt: str,
        schema_cls: Type[T],
        system_prompt: Optional[str] = None,
        mock_response: Optional[str] = None,
    ) -> T:
        """Call LLM and parse/validate response into schema_cls Pydantic model.

        Retries ONCE on JSON/validation failure.
        Raises DiagnosisValidationError on persistent failure.
        """
        # Support mock testing when mock_response is provided
        if mock_response is not None:
            return self._parse_and_validate(mock_response, schema_cls)

        if not self.api_key:
            raise DiagnosisValidationError(
                f"{self.provider.upper()}_API_KEY is not configured. Cannot call LLM API.",
                raw_response=None,
            )

        # Attempt 1
        raw_output_1 = self._call_llm(prompt, system_prompt)
        try:
            return self._parse_and_validate(raw_output_1, schema_cls)
        except (json.JSONDecodeError, ValidationError) as err1:
            logger.warning(f"First LLM validation attempt failed: {err1}. Retrying once...")

            # Attempt 2 (Retry prompt with error context)
            retry_prompt = (
                f"{prompt}\n\n"
                f"IMPORTANT: Your previous response failed validation with error: {str(err1)}.\n"
                f"Please respond strictly with valid JSON matching the schema."
            )
            raw_output_2 = self._call_llm(retry_prompt, system_prompt)
            try:
                return self._parse_and_validate(raw_output_2, schema_cls)
            except (json.JSONDecodeError, ValidationError) as err2:
                logger.error(f"Second LLM validation attempt failed: {err2}.")
                raise DiagnosisValidationError(
                    f"LLM output validation failed after retry: {err2}",
                    raw_response=raw_output_2,
                ) from err2

    def _call_llm(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Make raw call to LLM provider with backoff handling for rate limits."""
        global _gemini_call_counter, _llm_call_counter

        if self.provider == "groq":
            return self._call_groq(prompt, system_prompt)
        return self._call_gemini(prompt, system_prompt)

    def _call_gemini(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call Gemini API with retry logic."""
        global _gemini_call_counter, _llm_call_counter
        from google.genai import types, errors

        config = None
        if system_prompt:
            config = types.GenerateContentConfig(system_instruction=system_prompt)

        max_attempts = 5
        backoff_sec = 60.0

        for attempt in range(1, max_attempts + 1):
            try:
                _gemini_call_counter += 1
                _llm_call_counter += 1
                current_call = _gemini_call_counter

                response = self.gemini_client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                raw_text = response.text or ""

                if current_call <= 3:
                    logger.info(
                        f"[GeminiCall #{current_call}] SDK call succeeded. "
                        f"Response length={len(raw_text)} chars. "
                        f"Preview: {raw_text[:120]!r}"
                    )

                return raw_text
            except (errors.APIError, Exception) as err:
                is_rate_limit = False
                api_retry_delay: Optional[float] = None

                if isinstance(err, errors.APIError):
                    code = getattr(err, "code", None)
                    err_str = str(err)
                    if code == 429 or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        is_rate_limit = True
                        import re as _re
                        _match = _re.search(r"'retryDelay':\s*'(\d+(?:\.\d+)?)s'", err_str)
                        if _match:
                            api_retry_delay = min(float(_match.group(1)) + 2.0, 120.0)

                if is_rate_limit and attempt < max_attempts:
                    wait = api_retry_delay if api_retry_delay is not None else min(backoff_sec, 120.0)
                    logger.warning(
                        f"Gemini API rate limit hit (attempt {attempt}/{max_attempts}). "
                        f"Backing off for {wait:.1f}s before retry... Error: {err}"
                    )
                    time.sleep(wait)
                    backoff_sec *= 2
                else:
                    raise

    def _call_groq(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call Groq API with retry logic."""
        global _llm_call_counter
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        max_attempts = 5
        backoff_sec = 10.0

        for attempt in range(1, max_attempts + 1):
            try:
                _llm_call_counter += 1
                current_call = _llm_call_counter

                completion = self.groq_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
                raw_text = completion.choices[0].message.content or ""

                if current_call <= 3:
                    logger.info(
                        f"[GroqCall #{current_call}] SDK call succeeded. "
                        f"Response length={len(raw_text)} chars. "
                        f"Preview: {raw_text[:120]!r}"
                    )

                return raw_text
            except Exception as err:
                err_str = str(err).lower()
                is_rate_limit = "429" in err_str or "rate limit" in err_str
                if is_rate_limit and attempt < max_attempts:
                    logger.warning(
                        f"Groq API rate limit hit (attempt {attempt}/{max_attempts}). "
                        f"Backing off for {backoff_sec:.1f}s before retry... Error: {err}"
                    )
                    time.sleep(backoff_sec)
                    backoff_sec *= 2
                else:
                    raise

    def _parse_and_validate(self, text: str, schema_cls: Type[T]) -> T:
        """Clean markdown text, parse JSON, and validate against Pydantic schema."""
        cleaned = _clean_json_text(text)
        data = json.loads(cleaned)
        return schema_cls.model_validate(data)



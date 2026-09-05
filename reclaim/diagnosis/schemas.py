"""Pydantic schemas and custom exceptions for Diagnosis Engine."""

from typing import Literal, Optional
from pydantic import BaseModel, Field

# Fixed taxonomy — DO NOT INVENT NEW CATEGORIES
TAXONOMY_TYPES = Literal[
    "INSUFFICIENT_FUNDS",
    "OTP_TIMEOUT",
    "BANK_RAIL_DOWN",
    "AUTH_ABORT",
    "GENUINE_ABANDON",
    "B2B_CASH_CONSTRAINED",
    "B2B_DISPUTE",
]


class DiagnosisOutput(BaseModel):
    """Structured output for payment failure diagnosis."""
    cause: TAXONOMY_TYPES = Field(
        ..., description="Diagnosed root cause from fixed taxonomy"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0"
    )


class PromiseToPayOutput(BaseModel):
    """Structured output for customer promise-to-pay extraction."""
    promise: bool = Field(
        ..., description="True if customer explicitly promised to pay"
    )
    date: Optional[str] = Field(
        default=None, description="Promised payment date if specified (ISO format YYYY-MM-DD or descriptive)"
    )
    amount: Optional[int] = Field(
        default=None, description="Promised payment amount in paise if specified"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0"
    )


class DiagnosisValidationError(Exception):
    """Exception raised when LLM output validation fails after retry attempts.

    TODO (Phase 3 Handoff Point): The policy engine MUST catch this exception
    and fall back to a deterministic default policy rule (e.g. standard retry
    schedule for unknown cause).
    """

    def __init__(self, message: str, raw_response: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.raw_response = raw_response

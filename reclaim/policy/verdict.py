"""
Policy verdict — the output shape every policy decision returns.

`reason` is mandatory on every path, including ALLOW, because this string
powers the "why we did / didn't act" audit trail and dashboard feature.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Decision(str, Enum):
    ALLOW = "ALLOW"
    MODIFY = "MODIFY"
    BLOCK = "BLOCK"


# Alias for backward compatibility
PolicyDecisionEnum = Decision


class Tier(str, Enum):
    AUTO = "AUTO"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"



class PolicyVerdict(BaseModel):
    decision: Decision
    channel: Optional[str] = None
    reason: str = Field(
        ...,
        min_length=1,
        description="Mandatory human-readable justification for this verdict.",
    )
    tier: Tier
    max_discount_paise: int = 0  # Never set by the LLM — only by a hard-coded rule below.
    metadata: dict = Field(default_factory=dict)
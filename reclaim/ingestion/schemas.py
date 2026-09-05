"""Pydantic schemas for the ingestion layer.

RevenueEvent is the normalized contract that all event types map to.
RazorpayWebhookEnvelope describes the outer Razorpay webhook payload shape.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EventCategory(str, Enum):
    """High-level event classification for downstream diagnosis."""
    payment_failure = "payment_failure"
    cart_abandonment = "cart_abandonment"
    invoice_overdue = "invoice_overdue"
    payment_success = "payment_success"  # for captured / paid events


class RevenueEvent(BaseModel):
    """Normalized payload contract.

    All event types (Razorpay-native and synthetic) are mapped to this shape.
    Amounts are in **paise** (100 paise = ₹1) to match Razorpay's native units
    and avoid floating-point ambiguity.
    """

    event_id: str = Field(
        ..., description="Matches razorpay_event_id on the events table"
    )
    event_category: EventCategory = Field(
        ..., description="High-level category: payment_failure | cart_abandonment | invoice_overdue | payment_success"
    )
    customer_id: str = Field(
        ..., description="Internal customer UUID (string representation)"
    )
    amount: Decimal = Field(
        ..., description="Amount in paise (100 paise = ₹1)"
    )
    currency: str = Field(
        default="INR", description="ISO 4217 currency code"
    )
    failure_reason_raw: Optional[str] = Field(
        default=None,
        description="Raw Razorpay error code if present (e.g. BAD_REQUEST_ERROR)",
    )
    occurred_at: datetime = Field(
        ..., description="When the event occurred (ISO 8601 UTC)"
    )
    source_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context: order_id, invoice_id, subscription_id, method, etc.",
    )


class RazorpayPaymentEntity(BaseModel):
    """Shape of payload.payment.entity from Razorpay webhooks."""
    id: str
    amount: int  # paise
    currency: str = "INR"
    status: str
    method: Optional[str] = None
    order_id: Optional[str] = None
    invoice_id: Optional[str] = None
    customer_id: Optional[str] = None
    email: Optional[str] = None
    contact: Optional[str] = None
    error_code: Optional[str] = None
    error_description: Optional[str] = None
    error_reason: Optional[str] = None
    captured: Optional[bool] = None
    created_at: Optional[int] = None  # unix timestamp

    model_config = {"extra": "allow"}


class RazorpayOrderEntity(BaseModel):
    """Shape of payload.order.entity from Razorpay webhooks."""
    id: str
    amount: int
    status: str
    currency: str = "INR"

    model_config = {"extra": "allow"}


class RazorpayWebhookPayload(BaseModel):
    """The payload object inside the Razorpay webhook envelope."""
    payment: Optional[dict[str, Any]] = None
    order: Optional[dict[str, Any]] = None
    subscription: Optional[dict[str, Any]] = None
    payment_link: Optional[dict[str, Any]] = None
    invoice: Optional[dict[str, Any]] = None

    model_config = {"extra": "allow"}


class RazorpayWebhookEnvelope(BaseModel):
    """Outer Razorpay webhook event shape.

    Example:
    {
        "entity": "event",
        "account_id": "acc_xxx",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": { ... },
        "created_at": 1691735748
    }
    """
    entity: str = "event"
    account_id: Optional[str] = None
    event: str  # e.g. "payment.failed"
    contains: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: int  # unix timestamp

    model_config = {"extra": "allow"}

"""Event normalizer — maps raw Razorpay webhook payloads to the RevenueEvent contract.

One function per event type. Each extracts relevant fields from the raw Razorpay
payload and returns a RevenueEvent-compatible dict (validated by Pydantic upstream).

Amounts are kept in **paise** (Razorpay's native unit).
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from reclaim.ingestion.schemas import EventCategory, RevenueEvent


def _unix_to_iso(ts: int | None) -> datetime:
    """Convert a Unix timestamp to a timezone-aware UTC datetime."""
    if ts is None:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _extract_payment_entity(raw: dict[str, Any]) -> dict[str, Any]:
    """Safely extract the payment entity from the Razorpay payload."""
    payment = raw.get("payload", {}).get("payment", {})
    return payment.get("entity", payment)


def _extract_order_entity(raw: dict[str, Any]) -> dict[str, Any]:
    """Safely extract the order entity from the Razorpay payload."""
    order = raw.get("payload", {}).get("order", {})
    return order.get("entity", order)


# ---------------------------------------------------------------------------
# Razorpay-native event normalizers
# ---------------------------------------------------------------------------

def normalize_payment_failed(
    raw: dict[str, Any], customer_id: str
) -> RevenueEvent:
    """Normalize a payment.failed event."""
    payment = _extract_payment_entity(raw)
    event_id = raw.get("account_id", "") + "_" + payment.get("id", "")
    # Use the top-level event id if available
    event_id = raw.get("event_id", event_id)

    return RevenueEvent(
        event_id=event_id,
        event_category=EventCategory.payment_failure,
        customer_id=customer_id,
        amount=Decimal(str(payment.get("amount", 0))),
        currency=payment.get("currency", "INR"),
        failure_reason_raw=payment.get("error_code") or payment.get("error_description"),
        occurred_at=_unix_to_iso(raw.get("created_at") or payment.get("created_at")),
        source_metadata={
            "payment_id": payment.get("id"),
            "order_id": payment.get("order_id"),
            "method": payment.get("method"),
            "error_code": payment.get("error_code"),
            "error_description": payment.get("error_description"),
            "error_reason": payment.get("error_reason"),
        },
    )


def normalize_payment_captured(
    raw: dict[str, Any], customer_id: str
) -> RevenueEvent:
    """Normalize a payment.captured event."""
    payment = _extract_payment_entity(raw)
    event_id = raw.get("event_id", raw.get("account_id", "") + "_" + payment.get("id", ""))

    return RevenueEvent(
        event_id=event_id,
        event_category=EventCategory.payment_success,
        customer_id=customer_id,
        amount=Decimal(str(payment.get("amount", 0))),
        currency=payment.get("currency", "INR"),
        failure_reason_raw=None,
        occurred_at=_unix_to_iso(raw.get("created_at") or payment.get("created_at")),
        source_metadata={
            "payment_id": payment.get("id"),
            "order_id": payment.get("order_id"),
            "method": payment.get("method"),
        },
    )


def normalize_order_paid(
    raw: dict[str, Any], customer_id: str
) -> RevenueEvent:
    """Normalize an order.paid event."""
    payment = _extract_payment_entity(raw)
    order = _extract_order_entity(raw)
    event_id = raw.get("event_id", raw.get("account_id", "") + "_" + order.get("id", ""))

    return RevenueEvent(
        event_id=event_id,
        event_category=EventCategory.payment_success,
        customer_id=customer_id,
        amount=Decimal(str(order.get("amount", 0) or payment.get("amount", 0))),
        currency=order.get("currency", payment.get("currency", "INR")),
        failure_reason_raw=None,
        occurred_at=_unix_to_iso(raw.get("created_at")),
        source_metadata={
            "payment_id": payment.get("id"),
            "order_id": order.get("id"),
            "order_status": order.get("status"),
            "method": payment.get("method"),
        },
    )


# ---------------------------------------------------------------------------
# Synthetic / non-native event normalizers
# ---------------------------------------------------------------------------

def normalize_synthetic(
    raw: dict[str, Any], customer_id: str, category: EventCategory
) -> RevenueEvent:
    """Normalize a synthetic event (checkout_abandoned, invoice_overdue).

    These events don't come from Razorpay natively. They arrive pre-shaped
    in a format close to RevenueEvent. We just fill in defaults.
    """
    return RevenueEvent(
        event_id=raw.get("event_id", ""),
        event_category=category,
        customer_id=customer_id,
        amount=Decimal(str(raw.get("amount", 0))),
        currency=raw.get("currency", "INR"),
        failure_reason_raw=raw.get("failure_reason_raw"),
        occurred_at=_unix_to_iso(raw.get("created_at")) if isinstance(raw.get("created_at"), int) else datetime.now(timezone.utc),
        source_metadata=raw.get("source_metadata", {}),
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

# Map Razorpay event names (dot-separated) to our normalizer functions
_RAZORPAY_EVENT_MAP: dict[str, str] = {
    "payment.failed": "payment_failed",
    "payment.captured": "payment_captured",
    "order.paid": "order_paid",
    "subscription.charged": "subscription_charged",
    "subscription.halted": "subscription_halted",
    "payment_link.paid": "payment_link_paid",
    "checkout.abandoned": "checkout_abandoned",
    "invoice.overdue": "invoice_overdue",
}


def razorpay_event_to_internal(event_name: str) -> str | None:
    """Convert a Razorpay dot-separated event name to our internal enum value."""
    return _RAZORPAY_EVENT_MAP.get(event_name)


NORMALIZER_DISPATCH = {
    "payment_failed": normalize_payment_failed,
    "payment_captured": normalize_payment_captured,
    "order_paid": normalize_order_paid,
}

SYNTHETIC_EVENTS = {"checkout_abandoned", "invoice_overdue"}

"""Normalizer unit tests.

Validates that each normalizer function correctly maps raw Razorpay payloads
to the RevenueEvent Pydantic schema.
"""

import pytest
from decimal import Decimal

from reclaim.ingestion.normalizer import (
    normalize_payment_failed,
    normalize_payment_captured,
    normalize_order_paid,
    normalize_synthetic,
)
from reclaim.ingestion.schemas import EventCategory, RevenueEvent


class TestNormalizePaymentFailed:
    def test_basic_mapping(self):
        raw = {
            "entity": "event",
            "account_id": "acc_test",
            "event": "payment.failed",
            "event_id": "evt_001",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_001",
                        "amount": 50000,
                        "currency": "INR",
                        "status": "failed",
                        "method": "upi",
                        "order_id": "order_001",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_description": "OTP mismatch",
                        "error_reason": "payment_failed",
                        "created_at": 1691735748,
                    }
                }
            },
            "created_at": 1691735750,
        }

        result = normalize_payment_failed(raw, "customer-uuid-123")

        assert isinstance(result, RevenueEvent)
        assert result.event_id == "evt_001"
        assert result.event_category == EventCategory.payment_failure
        assert result.customer_id == "customer-uuid-123"
        assert result.amount == Decimal("50000")
        assert result.currency == "INR"
        assert result.failure_reason_raw == "BAD_REQUEST_ERROR"
        assert result.source_metadata["payment_id"] == "pay_001"
        assert result.source_metadata["order_id"] == "order_001"
        assert result.source_metadata["method"] == "upi"

    def test_missing_error_code(self):
        raw = {
            "event_id": "evt_no_error",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_002",
                        "amount": 10000,
                        "currency": "INR",
                        "status": "failed",
                        "created_at": 1691735748,
                    }
                }
            },
            "created_at": 1691735750,
        }

        result = normalize_payment_failed(raw, "cust-002")
        assert result.failure_reason_raw is None


class TestNormalizePaymentCaptured:
    def test_basic_mapping(self):
        raw = {
            "event_id": "evt_cap_001",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_cap_001",
                        "amount": 75000,
                        "currency": "INR",
                        "status": "captured",
                        "method": "card",
                        "order_id": "order_cap_001",
                        "captured": True,
                        "created_at": 1691735800,
                    }
                }
            },
            "created_at": 1691735802,
        }

        result = normalize_payment_captured(raw, "cust-cap-001")

        assert result.event_category == EventCategory.payment_success
        assert result.amount == Decimal("75000")
        assert result.failure_reason_raw is None
        assert result.source_metadata["payment_id"] == "pay_cap_001"


class TestNormalizeOrderPaid:
    def test_uses_order_amount(self):
        raw = {
            "event_id": "evt_ord_001",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_ord_001",
                        "amount": 50000,
                        "currency": "INR",
                        "status": "captured",
                        "method": "upi",
                    }
                },
                "order": {
                    "entity": {
                        "id": "order_ord_001",
                        "amount": 50000,
                        "status": "paid",
                        "currency": "INR",
                    }
                },
            },
            "created_at": 1691735900,
        }

        result = normalize_order_paid(raw, "cust-ord-001")

        assert result.event_category == EventCategory.payment_success
        assert result.amount == Decimal("50000")
        assert result.source_metadata["order_id"] == "order_ord_001"


class TestNormalizeSynthetic:
    def test_checkout_abandoned(self):
        raw = {
            "event_id": "synth_001",
            "amount": 30000,
            "currency": "INR",
            "failure_reason_raw": None,
            "created_at": 1691736000,
            "source_metadata": {"cart_id": "cart_001"},
        }

        result = normalize_synthetic(
            raw, "cust-synth-001", EventCategory.cart_abandonment
        )

        assert result.event_category == EventCategory.cart_abandonment
        assert result.amount == Decimal("30000")
        assert result.source_metadata["cart_id"] == "cart_001"

    def test_invoice_overdue(self):
        raw = {
            "event_id": "synth_002",
            "amount": 100000,
            "currency": "INR",
            "created_at": 1691736100,
            "source_metadata": {"invoice_id": "inv_001"},
        }

        result = normalize_synthetic(
            raw, "cust-synth-002", EventCategory.invoice_overdue
        )

        assert result.event_category == EventCategory.invoice_overdue
        assert result.amount == Decimal("100000")

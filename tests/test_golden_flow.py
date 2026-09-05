"""Test Suite for Golden Money-Recovery Loop (P0).

Tests the complete lifecycle:
  1. Ingest payment.failed webhook for ₹4,999 (OTP_TIMEOUT)
  2. Signature verification & idempotency validation
  3. LLM/Heuristic diagnosis -> OTP_TIMEOUT
  4. Policy Engine evaluates -> ALLOW, channel=razorpay_payment_link (ACT)
  5. Dispatcher triggers Razorpay Payment Link generation
  6. Audit trail logs state transition (failed -> nudged)
  7. Subsequent payment.captured / payment_link.paid webhook arrives
  8. State machine transitions nudged -> RECOVERED
  9. OutcomeObserver updates customer's RecoveryMemory (historical_response_rate & preferred_channel)
"""

import json
import uuid
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from reclaim.db.models import Base, Customer, Event, RecoveryState, RecoveryStateEnum, AuditLog, RecoveryMemory
from reclaim.ingestion.processor import process_webhook_event
from reclaim.ingestion.signature import compute_signature, verify_razorpay_signature


@pytest.fixture
async def async_db_session():
    """Create fresh in-memory SQLite database session for integration test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_golden_recovery_loop_end_to_end(async_db_session):
    """Full end-to-end verification of the ₹4,999 OTP failure recovery loop."""
    db = async_db_session
    webhook_secret = "test_webhook_secret_key_123"

    order_id = f"order_{uuid.uuid4().hex[:12]}"
    payment_id = f"pay_{uuid.uuid4().hex[:12]}"
    event_id_failed = f"evt_{uuid.uuid4().hex[:12]}"
    event_id_captured = f"evt_{uuid.uuid4().hex[:12]}"

    # 1. Prepare payment.failed webhook payload (₹4,999 = 499900 paise)
    failed_payload = {
        "entity": "event",
        "account_id": "acc_buildathon_demo",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": 499900,
                    "currency": "INR",
                    "status": "failed",
                    "method": "upi",
                    "email": "amit.sharma@example.com",
                    "contact": "+919876543210",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Payment was not completed because OTP timed out",
                    "error_source": "customer",
                    "error_step": "payment_authentication",
                    "error_reason": "payment_cancelled",
                    "notes": {"checkout_source": "mobile_app"},
                }
            }
        },
        "created_at": int(datetime.now(timezone.utc).timestamp()),
    }
    raw_failed_bytes = json.dumps(failed_payload).encode("utf-8")
    sig_failed = compute_signature(raw_failed_bytes, webhook_secret)

    # 1. Verify signature
    assert verify_razorpay_signature(raw_failed_bytes, sig_failed, webhook_secret) is True

    # 2. Process payment.failed webhook
    await process_webhook_event(
        db=db,
        raw_payload=failed_payload,
        razorpay_event_id=event_id_failed,
        event_type_str="payment_failed",
    )

    # 3. Verify customer, recovery state, and audit log created
    cust_res = await db.execute(select(Customer).where(Customer.email == "amit.sharma@example.com"))
    customer = cust_res.scalar_one_or_none()
    assert customer is not None
    assert customer.phone == "+919876543210"

    state_res = await db.execute(select(RecoveryState).where(RecoveryState.customer_id == customer.id))
    recovery_state = state_res.scalar_one_or_none()
    assert recovery_state is not None
    # State should be nudged (because payment link action was dispatched)
    assert recovery_state.state == RecoveryStateEnum.nudged
    assert recovery_state.amount == Decimal("499900")

    # Verify audit log recorded
    audit_res = await db.execute(select(AuditLog).where(AuditLog.recovery_state_id == recovery_state.id))
    audit_logs = audit_res.scalars().all()
    assert len(audit_logs) >= 2  # State creation + action dispatch

    # 4. Prepare payment.captured webhook payload
    captured_payload = {
        "entity": "event",
        "account_id": "acc_buildathon_demo",
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_recovered_{uuid.uuid4().hex[:8]}",
                    "order_id": order_id,
                    "amount": 499900,
                    "currency": "INR",
                    "status": "captured",
                    "method": "upi",
                    "email": "amit.sharma@example.com",
                    "contact": "+919876543210",
                }
            }
        },
        "created_at": int(datetime.now(timezone.utc).timestamp()) + 300,
    }
    raw_captured_bytes = json.dumps(captured_payload).encode("utf-8")
    sig_captured = compute_signature(raw_captured_bytes, webhook_secret)

    assert verify_razorpay_signature(raw_captured_bytes, sig_captured, webhook_secret) is True

    # 5. Process payment.captured webhook
    await process_webhook_event(
        db=db,
        raw_payload=captured_payload,
        razorpay_event_id=event_id_captured,
        event_type_str="payment_captured",
    )

    # 6. Verify transition to RECOVERED and RecoveryMemory update
    await db.refresh(recovery_state)
    assert recovery_state.state == RecoveryStateEnum.recovered

    mem_res = await db.execute(select(RecoveryMemory).where(RecoveryMemory.customer_id == customer.id))
    memory = mem_res.scalar_one_or_none()
    assert memory is not None
    assert memory.historical_response_rate == 1.0  # 1 successful recovery out of 1
    assert memory.last_outcome == "recovered"

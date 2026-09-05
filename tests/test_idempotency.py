"""Idempotency tests.

Verify that sending the same webhook payload twice results in:
- Exactly 1 row with processing_status = 'processed'
- The duplicate is marked as 'ignored_duplicate'
- No duplicate recovery_state or customer rows
"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from reclaim.db.models import Event, ProcessingStatus, RecoveryState, Customer
from reclaim.ingestion.processor import process_webhook_event
from tests.conftest import make_payment_failed_payload


@pytest.mark.asyncio
async def test_idempotency_dedup(db_session: AsyncSession):
    """Sending the same event twice: first is processed, second is ignored_duplicate."""
    payload = make_payment_failed_payload(
        payment_id="pay_idem_001",
        order_id="order_idem_001",
    )
    event_id = "payment.failed:pay_idem_001"

    # First call — should be processed
    await process_webhook_event(
        db=db_session,
        raw_payload=payload,
        razorpay_event_id=event_id,
        event_type_str="payment_failed",
    )

    # Verify first event was processed
    result = await db_session.execute(
        select(Event).where(Event.razorpay_event_id == event_id)
    )
    first_event = result.scalar_one()
    assert first_event.processing_status == ProcessingStatus.processed

    # Second call — same payload, same event ID
    await process_webhook_event(
        db=db_session,
        raw_payload=payload,
        razorpay_event_id=event_id,
        event_type_str="payment_failed",
    )

    # Verify still only 1 event row
    count_result = await db_session.execute(
        select(func.count()).select_from(Event).where(
            Event.razorpay_event_id == event_id
        )
    )
    assert count_result.scalar() == 1

    # The existing event should now be marked as ignored_duplicate
    result = await db_session.execute(
        select(Event).where(Event.razorpay_event_id == event_id)
    )
    event = result.scalar_one()
    assert event.processing_status == ProcessingStatus.ignored_duplicate


@pytest.mark.asyncio
async def test_idempotency_single_recovery_state(db_session: AsyncSession):
    """Duplicate events should not create duplicate recovery_state rows."""
    payload = make_payment_failed_payload(
        payment_id="pay_idem_002",
        order_id="order_idem_002",
    )
    event_id = "payment.failed:pay_idem_002"

    # Send twice
    await process_webhook_event(
        db=db_session,
        raw_payload=payload,
        razorpay_event_id=event_id,
        event_type_str="payment_failed",
    )
    await process_webhook_event(
        db=db_session,
        raw_payload=payload,
        razorpay_event_id=event_id,
        event_type_str="payment_failed",
    )

    # Should have exactly 1 recovery_state row
    count = await db_session.execute(
        select(func.count()).select_from(RecoveryState)
    )
    assert count.scalar() == 1


@pytest.mark.asyncio
async def test_idempotency_single_customer(db_session: AsyncSession):
    """Duplicate events for the same email should not create duplicate customers."""
    payload = make_payment_failed_payload(
        payment_id="pay_idem_003",
        order_id="order_idem_003",
        email="idempotent@example.com",
    )
    event_id = "payment.failed:pay_idem_003"

    # Send twice
    await process_webhook_event(
        db=db_session,
        raw_payload=payload,
        razorpay_event_id=event_id,
        event_type_str="payment_failed",
    )
    await process_webhook_event(
        db=db_session,
        raw_payload=payload,
        razorpay_event_id=event_id,
        event_type_str="payment_failed",
    )

    # Should have exactly 1 customer row for this email
    count = await db_session.execute(
        select(func.count()).select_from(Customer).where(
            Customer.email == "idempotent@example.com"
        )
    )
    assert count.scalar() == 1

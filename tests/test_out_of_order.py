"""Out-of-order event handling tests.

Scenario: payment fails, then payment is captured, then a STALE failure
arrives late. The system should:
1. Create recovery_state = 'failed' on the first failure
2. Transition to 'recovered' when the capture arrives
3. NOT reopen the case when the stale failure arrives — log to audit_log
   with reason "stale event ignored, payment already captured"
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reclaim.db.models import (
    AuditLog,
    Event,
    RecoveryState,
    RecoveryStateEnum,
)
from reclaim.ingestion.processor import process_webhook_event
from tests.conftest import make_payment_captured_payload, make_payment_failed_payload


@pytest.mark.asyncio
async def test_out_of_order_captured_after_failed(db_session: AsyncSession):
    """payment_captured after payment_failed → state transitions to 'recovered'."""
    order_id = "order_ooo_001"

    # Step 1: payment_failed
    failed_payload = make_payment_failed_payload(
        payment_id="pay_ooo_fail_001",
        order_id=order_id,
    )
    await process_webhook_event(
        db=db_session,
        raw_payload=failed_payload,
        razorpay_event_id="payment.failed:pay_ooo_fail_001",
        event_type_str="payment_failed",
    )

    # Verify recovery_state is 'failed' or 'nudged' (since recovery loop ran)
    result = await db_session.execute(select(RecoveryState))
    rs = result.scalar_one()
    assert rs.state in (RecoveryStateEnum.failed, RecoveryStateEnum.nudged)

    # Step 2: payment_captured for the same order
    captured_payload = make_payment_captured_payload(
        payment_id="pay_ooo_cap_001",
        order_id=order_id,
    )
    await process_webhook_event(
        db=db_session,
        raw_payload=captured_payload,
        razorpay_event_id="payment.captured:pay_ooo_cap_001",
        event_type_str="payment_captured",
    )

    # Verify recovery_state transitioned to 'recovered'
    await db_session.refresh(rs)
    assert rs.state == RecoveryStateEnum.recovered


@pytest.mark.asyncio
async def test_out_of_order_stale_failure_after_recovery(db_session: AsyncSession):
    """Late payment_failed after recovery → state stays 'recovered', audit log explains why."""
    order_id = "order_ooo_002"

    # Step 1: payment_failed
    failed_payload = make_payment_failed_payload(
        payment_id="pay_ooo_fail_002",
        order_id=order_id,
    )
    await process_webhook_event(
        db=db_session,
        raw_payload=failed_payload,
        razorpay_event_id="payment.failed:pay_ooo_fail_002",
        event_type_str="payment_failed",
    )

    # Step 2: payment_captured
    captured_payload = make_payment_captured_payload(
        payment_id="pay_ooo_cap_002",
        order_id=order_id,
    )
    await process_webhook_event(
        db=db_session,
        raw_payload=captured_payload,
        razorpay_event_id="payment.captured:pay_ooo_cap_002",
        event_type_str="payment_captured",
    )

    # Verify recovered
    result = await db_session.execute(select(RecoveryState))
    rs = result.scalar_one()
    assert rs.state == RecoveryStateEnum.recovered

    # Step 3: STALE payment_failed arrives late (different payment_id, same order)
    stale_payload = make_payment_failed_payload(
        payment_id="pay_ooo_stale_002",
        order_id=order_id,
    )
    await process_webhook_event(
        db=db_session,
        raw_payload=stale_payload,
        razorpay_event_id="payment.failed:pay_ooo_stale_002",
        event_type_str="payment_failed",
    )

    # Verify state STILL 'recovered' — not reopened
    await db_session.refresh(rs)
    assert rs.state == RecoveryStateEnum.recovered

    # Verify audit log has the stale event entry
    audit_result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "stale_failure_ignored"
        )
    )
    audit_entry = audit_result.scalar_one()
    assert "stale event ignored, payment already captured" in audit_entry.reason


@pytest.mark.asyncio
async def test_out_of_order_full_scenario(db_session: AsyncSession):
    """Full scenario: failed → captured → stale failed. Assert final state and audit trail."""
    order_id = "order_ooo_full"

    # 1. Failed
    await process_webhook_event(
        db=db_session,
        raw_payload=make_payment_failed_payload(
            payment_id="pay_full_fail", order_id=order_id
        ),
        razorpay_event_id="payment.failed:pay_full_fail",
        event_type_str="payment_failed",
    )

    # 2. Captured
    await process_webhook_event(
        db=db_session,
        raw_payload=make_payment_captured_payload(
            payment_id="pay_full_cap", order_id=order_id
        ),
        razorpay_event_id="payment.captured:pay_full_cap",
        event_type_str="payment_captured",
    )

    # 3. Stale failed
    await process_webhook_event(
        db=db_session,
        raw_payload=make_payment_failed_payload(
            payment_id="pay_full_stale", order_id=order_id
        ),
        razorpay_event_id="payment.failed:pay_full_stale",
        event_type_str="payment_failed",
    )

    # Final assertions
    rs_result = await db_session.execute(select(RecoveryState))
    rs = rs_result.scalar_one()
    assert rs.state == RecoveryStateEnum.recovered

    # Should have at least 3 audit log entries
    audit_result = await db_session.execute(select(AuditLog))
    audit_entries = audit_result.scalars().all()
    assert len(audit_entries) >= 3

    # Check specific audit actions exist
    actions = {e.action for e in audit_entries}
    assert "recovery_state_created" in actions
    assert "stale_failure_ignored" in actions

    # One of the entries should mention state transition to recovered
    transition_entries = [
        e for e in audit_entries if "recovered" in e.action
    ]
    assert len(transition_entries) >= 1

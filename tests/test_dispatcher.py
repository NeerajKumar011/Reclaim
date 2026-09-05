"""Unit tests for Recovery Dispatcher."""

from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from sqlalchemy import select

from reclaim.db.models import (
    AuditLog,
    Customer,
    Event,
    EventType,
    RecoveryState,
    RecoveryStateEnum,
    ReviewQueue,
    SimulatedDispatchLog,
)
from reclaim.orchestrator.executors.dispatcher import dispatch_recovery_action
from reclaim.orchestrator.executors.razorpay_executor import RazorpayExecutor
from reclaim.policy.verdict import PolicyDecisionEnum, PolicyVerdict, Tier


@pytest.mark.asyncio
async def test_dispatcher_allow_razorpay_link(db_session):
    """Test ALLOW decision with razorpay_payment_link channel."""
    customer = Customer(email="disp_allow@example.com", name="Dispatch User")
    db_session.add(customer)
    await db_session.flush()

    event = Event(
        razorpay_event_id="evt_disp_1",
        event_type=EventType.payment_failed,
        raw_payload={},
    )
    db_session.add(event)
    await db_session.flush()

    state = RecoveryState(
        customer_id=customer.id,
        event_id=event.id,
        amount=Decimal("1500.00"),
        state=RecoveryStateEnum.failed,
    )
    db_session.add(state)
    await db_session.flush()

    verdict = PolicyVerdict(
        decision=PolicyDecisionEnum.ALLOW,
        channel="razorpay_payment_link",
        reason="OTP Timeout — prompt retry",
        tier=Tier.AUTO,
        max_discount_paise=0,
    )

    # Mock Razorpay executor call
    mock_rz = RazorpayExecutor()
    mock_rz.create_payment_link = MagicMock(return_value={
        "id": "plink_mock_test123",
        "short_url": "https://rzp.io/i/test",
        "status": "created",
    })

    res = await dispatch_recovery_action(
        db=db_session,
        verdict=verdict,
        recovery_state=state,
        customer=customer,
        event=event,
        razorpay_executor=mock_rz,
    )

    assert res["status"] == "dispatched"
    assert state.state == RecoveryStateEnum.nudged
    mock_rz.create_payment_link.assert_called_once()

    # Check audit log
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.recovery_state_id == state.id)
    )
    logs = audit_res.scalars().all()
    assert any("dispatch:razorpay_payment_link" in log.action for log in logs)


@pytest.mark.asyncio
async def test_dispatcher_allow_simulated_channel(db_session):
    """Test ALLOW decision with simulated channel (whatsapp)."""
    customer = Customer(email="sim_whatsapp@example.com", phone="+919999988888")
    db_session.add(customer)
    await db_session.flush()

    event = Event(
        razorpay_event_id="evt_disp_2",
        event_type=EventType.payment_failed,
        raw_payload={},
    )
    db_session.add(event)
    await db_session.flush()

    state = RecoveryState(
        customer_id=customer.id,
        event_id=event.id,
        amount=Decimal("800.00"),
        state=RecoveryStateEnum.failed,
    )
    db_session.add(state)
    await db_session.flush()

    verdict = PolicyVerdict(
        decision=PolicyDecisionEnum.ALLOW,
        channel="whatsapp",
        reason="Insufficient funds nudge",
        tier=Tier.AUTO,
        max_discount_paise=1000,
    )

    res = await dispatch_recovery_action(
        db=db_session,
        verdict=verdict,
        recovery_state=state,
        customer=customer,
        event=event,
    )

    assert res["status"] == "dispatched"
    assert state.state == RecoveryStateEnum.nudged

    # Verify simulated_dispatch_log entry
    disp_res = await db_session.execute(
        select(SimulatedDispatchLog).where(SimulatedDispatchLog.customer_id == customer.id)
    )
    disp = disp_res.scalar_one_or_none()
    assert disp is not None
    assert disp.channel == "whatsapp"
    assert len(disp.message_body) > 0


@pytest.mark.asyncio
async def test_dispatcher_modify_lands_in_review_queue(db_session):
    """Test MODIFY decision lands in review_queue and does NOT dispatch."""
    customer = Customer(email="b2b_modify@example.com")
    db_session.add(customer)
    await db_session.flush()

    event = Event(
        razorpay_event_id="evt_disp_3",
        event_type=EventType.payment_failed,
        raw_payload={},
    )
    db_session.add(event)
    await db_session.flush()

    state = RecoveryState(
        customer_id=customer.id,
        event_id=event.id,
        amount=Decimal("50000.00"),
        state=RecoveryStateEnum.failed,
    )
    db_session.add(state)
    await db_session.flush()

    verdict = PolicyVerdict(
        decision=PolicyDecisionEnum.MODIFY,
        channel="human_escalation",
        reason="B2B dispute detected",
        tier=Tier.REVIEW,
        max_discount_paise=0,
    )

    res = await dispatch_recovery_action(
        db=db_session,
        verdict=verdict,
        recovery_state=state,
        customer=customer,
        event=event,
    )

    assert res["status"] == "enqueued_for_review"
    assert state.state == RecoveryStateEnum.failed  # State not nudged

    # Verify review_queue entry
    rq_res = await db_session.execute(
        select(ReviewQueue).where(ReviewQueue.customer_id == customer.id)
    )
    rq_entry = rq_res.scalar_one_or_none()
    assert rq_entry is not None
    assert rq_entry.reason == "B2B dispute detected"
    assert rq_entry.resolved is False

    # Verify NO simulated_dispatch_log was created
    disp_res = await db_session.execute(
        select(SimulatedDispatchLog).where(SimulatedDispatchLog.customer_id == customer.id)
    )
    assert disp_res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_dispatcher_block_does_not_dispatch(db_session):
    """Test BLOCK decision does not dispatch and moves state to waiting."""
    customer = Customer(email="block@example.com")
    db_session.add(customer)
    await db_session.flush()

    event = Event(
        razorpay_event_id="evt_disp_4",
        event_type=EventType.payment_failed,
        raw_payload={},
    )
    db_session.add(event)
    await db_session.flush()

    state = RecoveryState(
        customer_id=customer.id,
        event_id=event.id,
        amount=Decimal("2000.00"),
        state=RecoveryStateEnum.failed,
    )
    db_session.add(state)
    await db_session.flush()

    verdict = PolicyVerdict(
        decision=PolicyDecisionEnum.BLOCK,
        channel="none",
        reason="Bank rail down",
        tier=Tier.BLOCK,
        max_discount_paise=0,
    )

    res = await dispatch_recovery_action(
        db=db_session,
        verdict=verdict,
        recovery_state=state,
        customer=customer,
        event=event,
    )

    assert res["status"] == "blocked"
    assert state.state == RecoveryStateEnum.waiting

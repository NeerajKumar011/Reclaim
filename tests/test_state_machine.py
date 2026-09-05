"""Unit tests for Recovery State Machine."""

from decimal import Decimal
import pytest
from sqlalchemy import select

from reclaim.db.models import (
    AuditLog,
    Customer,
    Event,
    EventType,
    ProcessingStatus,
    RecoveryState,
    RecoveryStateEnum,
)
from reclaim.orchestrator.state_machine import (
    InvalidStateTransitionError,
    transition_state,
)


@pytest.mark.asyncio
async def test_legal_state_transitions(db_session):
    """Test all valid state transitions and audit logging."""
    # Create customer & event
    customer = Customer(email="statemachine@example.com", name="State Machine User")
    db_session.add(customer)
    await db_session.flush()

    event = Event(
        razorpay_event_id="evt_sm_1",
        event_type=EventType.payment_failed,
        raw_payload={},
        processing_status=ProcessingStatus.processed,
    )
    db_session.add(event)
    await db_session.flush()

    state = RecoveryState(
        customer_id=customer.id,
        event_id=event.id,
        amount=Decimal("1000.00"),
        state=RecoveryStateEnum.failed,
    )
    db_session.add(state)
    await db_session.flush()

    # 1. failed -> waiting
    state = await transition_state(
        db=db_session,
        recovery_state=state,
        target_state=RecoveryStateEnum.waiting,
        reason="Policy blocked — cooldown",
    )
    assert state.state == RecoveryStateEnum.waiting

    # 2. waiting -> nudged
    state = await transition_state(
        db=db_session,
        recovery_state=state,
        target_state=RecoveryStateEnum.nudged,
        reason="Nudge dispatched via SMS",
    )
    assert state.state == RecoveryStateEnum.nudged

    # 3. nudged -> promised
    state = await transition_state(
        db=db_session,
        recovery_state=state,
        target_state=RecoveryStateEnum.promised,
        reason="Customer promised to pay on Friday",
    )
    assert state.state == RecoveryStateEnum.promised

    # 4. promised -> recovered
    state = await transition_state(
        db=db_session,
        recovery_state=state,
        target_state=RecoveryStateEnum.recovered,
        reason="Payment link completed",
    )
    assert state.state == RecoveryStateEnum.recovered

    # Verify audit logs created for all 4 transitions
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.recovery_state_id == state.id)
    )
    logs = audit_res.scalars().all()
    assert len(logs) >= 4
    for log in logs:
        assert log.actor == "orchestrator"
        assert len(log.reason) > 0


@pytest.mark.asyncio
async def test_promised_to_escalated_and_direct_recovered(db_session):
    """Test promised -> escalated and nudged -> recovered transitions."""
    customer = Customer(email="escalate@example.com")
    db_session.add(customer)
    await db_session.flush()

    event = Event(
        razorpay_event_id="evt_sm_2",
        event_type=EventType.payment_failed,
        raw_payload={},
    )
    db_session.add(event)
    await db_session.flush()

    state = RecoveryState(
        customer_id=customer.id,
        event_id=event.id,
        amount=Decimal("500.00"),
        state=RecoveryStateEnum.nudged,
    )
    db_session.add(state)
    await db_session.flush()

    # nudged -> recovered directly
    state = await transition_state(
        db=db_session,
        recovery_state=state,
        target_state=RecoveryStateEnum.recovered,
        reason="Direct payment capture received",
    )
    assert state.state == RecoveryStateEnum.recovered


@pytest.mark.asyncio
async def test_illegal_state_transition_rejected(db_session):
    """Test that illegal transition (recovered -> nudged) raises InvalidStateTransitionError."""
    customer = Customer(email="terminal@example.com")
    db_session.add(customer)
    await db_session.flush()

    event = Event(
        razorpay_event_id="evt_sm_3",
        event_type=EventType.payment_failed,
        raw_payload={},
    )
    db_session.add(event)
    await db_session.flush()

    state = RecoveryState(
        customer_id=customer.id,
        event_id=event.id,
        amount=Decimal("200.00"),
        state=RecoveryStateEnum.recovered,  # Terminal state
    )
    db_session.add(state)
    await db_session.flush()

    with pytest.raises(InvalidStateTransitionError):
        await transition_state(
            db=db_session,
            recovery_state=state,
            target_state=RecoveryStateEnum.nudged,
            reason="Illegal attempt to re-nudge recovered state",
        )

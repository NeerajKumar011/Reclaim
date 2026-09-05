"""Unit tests for Recovery Memory update on outcome resolution."""

from decimal import Decimal
import pytest
from sqlalchemy import select

from reclaim.db.models import (
    Customer,
    Event,
    EventType,
    RecoveryMemory,
    RecoveryState,
    RecoveryStateEnum,
    SimulatedDispatchLog,
)
from reclaim.orchestrator.outcome_observer import handle_outcome_transition
from reclaim.orchestrator.state_machine import transition_state


@pytest.mark.asyncio
async def test_recovery_memory_updates_on_recovered_outcome(db_session):
    """Test that a recovered outcome updates historical_response_rate and preferred_channel."""
    customer = Customer(email="memory_test@example.com", name="Memory Customer")
    db_session.add(customer)
    await db_session.flush()

    event = Event(
        razorpay_event_id="evt_mem_1",
        event_type=EventType.payment_failed,
        raw_payload={},
    )
    db_session.add(event)
    await db_session.flush()

    state = RecoveryState(
        customer_id=customer.id,
        event_id=event.id,
        amount=Decimal("3000.00"),
        state=RecoveryStateEnum.nudged,
    )
    db_session.add(state)
    await db_session.flush()

    # Log dispatch
    dispatch = SimulatedDispatchLog(
        customer_id=customer.id,
        channel="whatsapp",
        message_body="Test recovery message",
    )
    db_session.add(dispatch)
    await db_session.flush()

    # Transition to recovered
    await transition_state(
        db=db_session,
        recovery_state=state,
        target_state=RecoveryStateEnum.recovered,
        reason="Payment recovered via WhatsApp link",
    )

    # Check recovery_memory
    mem_res = await db_session.execute(
        select(RecoveryMemory).where(RecoveryMemory.customer_id == customer.id)
    )
    memory = mem_res.scalar_one_or_none()

    assert memory is not None
    assert memory.historical_response_rate == 1.0
    assert memory.preferred_channel == "whatsapp"


@pytest.mark.asyncio
async def test_recovery_memory_rate_calculation(db_session):
    """Test response rate calculation with multiple states (1 recovered, 1 escalated)."""
    customer = Customer(email="memory_rate@example.com")
    db_session.add(customer)
    await db_session.flush()

    event1 = Event(razorpay_event_id="evt_mem_2a", event_type=EventType.payment_failed, raw_payload={})
    event2 = Event(razorpay_event_id="evt_mem_2b", event_type=EventType.payment_failed, raw_payload={})
    db_session.add_all([event1, event2])
    await db_session.flush()

    state1 = RecoveryState(
        customer_id=customer.id,
        event_id=event1.id,
        amount=Decimal("1000.00"),
        state=RecoveryStateEnum.promised,
    )
    state2 = RecoveryState(
        customer_id=customer.id,
        event_id=event2.id,
        amount=Decimal("2000.00"),
        state=RecoveryStateEnum.promised,
    )
    db_session.add_all([state1, state2])
    await db_session.flush()

    # Resolve state1 as escalated
    await transition_state(
        db=db_session,
        recovery_state=state1,
        target_state=RecoveryStateEnum.escalated,
        reason="Promised date passed without payment",
    )

    mem_res = await db_session.execute(
        select(RecoveryMemory).where(RecoveryMemory.customer_id == customer.id)
    )
    memory = mem_res.scalar_one_or_none()
    assert memory is not None
    assert memory.historical_response_rate == 0.0

    # Resolve state2 as recovered
    await transition_state(
        db=db_session,
        recovery_state=state2,
        target_state=RecoveryStateEnum.recovered,
        reason="Payment received",
    )

    await db_session.refresh(memory)
    assert memory.historical_response_rate == 0.5  # 1 out of 2 recovered

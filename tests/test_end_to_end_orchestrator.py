"""End-to-end simulation test for Recovery Orchestrator + Recovery Memory.

Walks a simulated failed payment event end-to-end:
diagnosis -> policy.evaluate() -> dispatcher -> state transition -> audit_log & recovery_memory update.
"""

from decimal import Decimal
import pytest
from sqlalchemy import select

from reclaim.db.models import (
    AuditLog,
    Customer,
    Event,
    EventType,
    ProcessingStatus,
    RecoveryMemory,
    RecoveryState,
    RecoveryStateEnum,
    SimulatedDispatchLog,
)
from reclaim.orchestrator.executors.dispatcher import dispatch_recovery_action
from reclaim.orchestrator.outcome_observer import handle_outcome_transition
from reclaim.orchestrator.state_machine import transition_state
from reclaim.policy.rules import evaluate as evaluate_policy


@pytest.mark.asyncio
async def test_end_to_end_simulated_failed_payment(db_session):
    """Walk a failed-payment event end-to-end."""

    # 1. Setup Customer & Event
    customer = Customer(
        email="e2e_user@example.com",
        name="E2E Customer",
        phone="+919876543210",
        preferred_language="en",
    )
    db_session.add(customer)
    await db_session.flush()

    event = Event(
        razorpay_event_id="evt_e2e_001",
        event_type=EventType.payment_failed,
        raw_payload={"payload": {"payment": {"entity": {"amount": 250000}}}},
        processing_status=ProcessingStatus.processed,
    )
    db_session.add(event)
    await db_session.flush()

    recovery_state = RecoveryState(
        customer_id=customer.id,
        event_id=event.id,
        amount=Decimal("2500.00"),
        state=RecoveryStateEnum.failed,
    )
    db_session.add(recovery_state)
    await db_session.flush()

    # Initial audit log
    audit_init = AuditLog(
        event_id=event.id,
        recovery_state_id=recovery_state.id,
        actor="system",
        action="recovery_state_created",
        reason="Payment failed event processed",
    )
    db_session.add(audit_init)
    await db_session.flush()

    # 2. Simulated Diagnosis
    diagnosis_cause = "OTP_TIMEOUT"

    # 3. Policy Evaluation
    verdict = evaluate_policy(
        diagnosis_cause=diagnosis_cause,
        customer=customer,
        amount_paise=250000,
    )
    assert verdict.decision.value == "ALLOW"

    # 4. Dispatch Action
    from unittest.mock import MagicMock
    mock_rz = MagicMock()
    mock_rz.create_payment_link.return_value = {
        "id": "plink_e2e_001",
        "short_url": "https://rzp.io/i/e2e001",
        "status": "created",
    }

    dispatch_res = await dispatch_recovery_action(
        db=db_session,
        verdict=verdict,
        recovery_state=recovery_state,
        customer=customer,
        event=event,
        razorpay_executor=mock_rz,
    )


    assert dispatch_res["status"] == "dispatched"
    assert recovery_state.state == RecoveryStateEnum.nudged

    # 5. Customer Promise simulation
    await transition_state(
        db=db_session,
        recovery_state=recovery_state,
        target_state=RecoveryStateEnum.promised,
        reason="Promise extracted: customer promised payment by tomorrow",
        actor="orchestrator",
        event=event,
    )
    assert recovery_state.state == RecoveryStateEnum.promised

    # 6. Customer Payment Success (Recovered)
    await transition_state(
        db=db_session,
        recovery_state=recovery_state,
        target_state=RecoveryStateEnum.recovered,
        reason="Payment link captured successfully",
        actor="orchestrator",
        event=event,
    )
    assert recovery_state.state == RecoveryStateEnum.recovered

    # 7. Verify Audit Log Trail
    logs_res = await db_session.execute(
        select(AuditLog)
        .where(AuditLog.recovery_state_id == recovery_state.id)
        .order_by(AuditLog.created_at.asc())
    )
    logs = logs_res.scalars().all()
    assert len(logs) >= 4  # Creation + Dispatch + Nudged->Promised + Promised->Recovered
    for log in logs:
        assert len(log.reason) > 0

    # 8. Verify Recovery Memory Update
    mem_res = await db_session.execute(
        select(RecoveryMemory).where(RecoveryMemory.customer_id == customer.id)
    )
    memory = mem_res.scalar_one_or_none()
    assert memory is not None
    assert memory.historical_response_rate == 1.0

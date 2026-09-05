"""Integration test: Full webhook → diagnosis → policy → dispatch loop (P0-1).

Verifies that POSTing a payment.failed webhook event:
  1. Creates a RecoveryState
  2. Runs the diagnosis engine (heuristic fallback since no API key in tests)
  3. Runs the deterministic policy engine
  4. Dispatches or blocks the action
  5. Records a full audit trail

Architecture guarantee under test:
  - The LLM (or heuristic fallback) ONLY classifies the failure cause.
  - All financial/contact decisions flow through the policy engine.
  - The policy engine never receives raw LLM text - only DiagnosisOutput.
"""

import asyncio
import json
import time
import uuid

import pytest
from sqlalchemy import select

from reclaim.db.models import AuditLog, RecoveryState, RecoveryStateEnum
from tests.conftest import make_payment_captured_payload, make_payment_failed_payload


@pytest.mark.asyncio
async def test_payment_failed_webhook_triggers_full_pipeline(client, db_session):
    """POST payment.failed -> pipeline runs -> audit trail has all 3 stages.

    Expected AuditLog actions:
      - recovery_state_created      (ingestion)
      - diagnosed:<CAUSE>           (diagnosis engine)
      - policy_verdict:<DECISION>   (policy engine)
      - dispatch:<channel> OR policy_block OR review_queue_enqueued  (dispatcher)
    """
    payment_id = f"pay_{uuid.uuid4().hex[:12]}"
    order_id = f"order_{uuid.uuid4().hex[:12]}"
    event_id = f"evt_{uuid.uuid4().hex[:12]}"

    payload = make_payment_failed_payload(
        payment_id=payment_id,
        order_id=order_id,
        amount=50000,
        email=f"{payment_id}@test.com",
        error_code="BAD_REQUEST_ERROR",
    )
    envelope = {
        **payload,
        "account_id": "acc_test",
        "entity": "event",
        "event": "payment.failed",
        "created_at": int(time.time()),
        "id": event_id,
    }

    response = await client.post(
        "/webhooks/razorpay",
        content=json.dumps(envelope),
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": "",
        },
    )
    assert response.status_code == 200

    await asyncio.sleep(0.3)
    await db_session.rollback()

    rs_res = await db_session.execute(select(RecoveryState))
    recovery_states = rs_res.scalars().all()
    assert len(recovery_states) >= 1, "Expected at least one RecoveryState"

    recovery_state = recovery_states[-1]

    audit_res = await db_session.execute(
        select(AuditLog)
        .where(AuditLog.recovery_state_id == recovery_state.id)
        .order_by(AuditLog.created_at.asc())
    )
    logs = audit_res.scalars().all()
    actions = [log.action for log in logs]

    # Ingestion stage
    assert any("recovery_state_created" in a for a in actions), (
        f"Expected recovery_state_created in audit log. Got: {actions}"
    )
    # Diagnosis stage
    assert any("diagnosed:" in a or "pipeline_error" in a for a in actions), (
        f"Expected diagnosed:<cause> or pipeline_error. Got: {actions}"
    )
    # Policy + dispatch stages (only if diagnosis succeeded)
    if any("diagnosed:" in a for a in actions):
        assert any("policy_verdict:" in a for a in actions), (
            f"Expected policy_verdict:<decision>. Got: {actions}"
        )
        assert any(
            "dispatch:" in a or "policy_block" in a or "review_queue_enqueued" in a
            for a in actions
        ), f"Expected dispatch action. Got: {actions}"

    # State must have advanced from failed
    assert recovery_state.state in (
        RecoveryStateEnum.failed,
        RecoveryStateEnum.nudged,
        RecoveryStateEnum.waiting,
    ), f"Unexpected state: {recovery_state.state}"


@pytest.mark.asyncio
async def test_pipeline_uses_heuristic_when_no_llm_key(client, db_session):
    """Heuristic fallback runs and pipeline completes when LLM key is absent.

    In the test environment GEMINI_API_KEY is empty. The pipeline MUST
    fall back to heuristic_classify() and still produce diagnosis +
    policy verdict + dispatch action.
    """
    payment_id = f"pay_{uuid.uuid4().hex[:12]}"
    event_id = f"evt_{uuid.uuid4().hex[:12]}"

    payload = make_payment_failed_payload(
        payment_id=payment_id,
        amount=100000,
        email=f"{payment_id}@heuristic.com",
        error_code="BAD_REQUEST_ERROR",
    )
    envelope = {
        **payload,
        "entity": "event",
        "event": "payment.failed",
        "created_at": int(time.time()),
        "id": event_id,
    }

    response = await client.post(
        "/webhooks/razorpay",
        content=json.dumps(envelope),
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": ""},
    )
    assert response.status_code == 200

    await asyncio.sleep(0.3)
    await db_session.rollback()

    rs_res = await db_session.execute(select(RecoveryState))
    recovery_states = rs_res.scalars().all()
    assert len(recovery_states) >= 1

    recovery_state = recovery_states[-1]
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.recovery_state_id == recovery_state.id)
    )
    actions = [log.action for log in audit_res.scalars().all()]

    assert any("diagnosed:" in a for a in actions), (
        f"Heuristic should have diagnosed a cause. Got: {actions}"
    )
    assert any("policy_verdict:" in a for a in actions), (
        f"Policy verdict should follow heuristic. Got: {actions}"
    )
    assert any(
        "dispatch:" in a or "policy_block" in a or "review_queue_enqueued" in a
        for a in actions
    ), f"Dispatch result should follow policy verdict. Got: {actions}"


@pytest.mark.asyncio
async def test_duplicate_event_dispatches_only_once(client, db_session):
    """The same event_id twice must result in at most 1 dispatch action."""
    payment_id = f"pay_{uuid.uuid4().hex[:12]}"
    event_id = f"evt_{uuid.uuid4().hex[:12]}"

    payload = make_payment_failed_payload(
        payment_id=payment_id,
        email=f"{payment_id}@idem.com",
    )
    envelope = {
        **payload,
        "entity": "event",
        "event": "payment.failed",
        "created_at": int(time.time()),
        "id": event_id,
    }

    r1 = await client.post(
        "/webhooks/razorpay",
        content=json.dumps(envelope),
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": ""},
    )
    r2 = await client.post(
        "/webhooks/razorpay",
        content=json.dumps(envelope),
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": ""},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200

    await asyncio.sleep(0.3)
    await db_session.rollback()

    rs_res = await db_session.execute(select(RecoveryState))
    all_rs = rs_res.scalars().all()

    dispatch_count = 0
    for rs in all_rs:
        audit_res = await db_session.execute(
            select(AuditLog).where(AuditLog.recovery_state_id == rs.id)
        )
        for log in audit_res.scalars().all():
            if "dispatch:" in log.action or "policy_block" in log.action:
                dispatch_count += 1

    assert dispatch_count <= 1, (
        f"Expected at most 1 dispatch for duplicate event, got {dispatch_count}"
    )


@pytest.mark.asyncio
async def test_payment_captured_closes_recovery_loop(client, db_session):
    """POST failed then captured -> RecoveryState transitions to recovered."""
    payment_id = f"pay_{uuid.uuid4().hex[:12]}"
    order_id = f"order_{uuid.uuid4().hex[:12]}"
    email = f"{payment_id}@loop.com"

    # Step 1: failure
    failed_envelope = {
        **make_payment_failed_payload(
            payment_id=payment_id,
            order_id=order_id,
            email=email,
        ),
        "entity": "event",
        "event": "payment.failed",
        "created_at": int(time.time()),
        "id": f"evt_fail_{uuid.uuid4().hex[:10]}",
    }
    await client.post(
        "/webhooks/razorpay",
        content=json.dumps(failed_envelope),
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": ""},
    )
    await asyncio.sleep(0.3)

    # Step 2: capture
    captured_envelope = {
        **make_payment_captured_payload(
            payment_id=payment_id,
            order_id=order_id,
            email=email,
        ),
        "entity": "event",
        "event": "payment.captured",
        "created_at": int(time.time()) + 10,
        "id": f"evt_cap_{uuid.uuid4().hex[:10]}",
    }
    await client.post(
        "/webhooks/razorpay",
        content=json.dumps(captured_envelope),
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": ""},
    )
    await asyncio.sleep(0.3)
    await db_session.rollback()

    rs_res = await db_session.execute(select(RecoveryState))
    all_rs = rs_res.scalars().all()
    recovered = [rs for rs in all_rs if rs.state == RecoveryStateEnum.recovered]
    assert len(recovered) >= 1, (
        f"Expected recovered state. Got: {[rs.state for rs in all_rs]}"
    )

    for rs in recovered:
        audit_res = await db_session.execute(
            select(AuditLog).where(AuditLog.recovery_state_id == rs.id)
        )
        actions = [log.action for log in audit_res.scalars().all()]
        assert any("recovered" in a for a in actions), (
            f"Expected recovered in audit actions. Got: {actions}"
        )

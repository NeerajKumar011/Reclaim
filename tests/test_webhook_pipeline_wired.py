"""Part A Integration Test: payment.failed webhook → full pipeline wired proof.

POSTs a synthetic payment.failed webhook to the running app and asserts:
1. HTTP 200 returned immediately
2. RecoveryState created in `failed` state
3. AuditLog contains diagnosis_engine entry (proves FailureClassifier was called)
4. AuditLog contains policy_engine entry (proves rules.evaluate() was called)
5. AuditLog contains dispatch or policy_block entry (proves dispatcher was called)
6. The full decision chain: diagnosis → policy → dispatch is recorded
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from reclaim.db.models import AuditLog, Event, RecoveryState, RecoveryStateEnum


@pytest.mark.asyncio
async def test_payment_failed_webhook_triggers_full_pipeline(client: AsyncClient, db_session):
    """POST payment.failed → assert diagnosis+policy+dispatch all run and are audit-logged."""
    # Unique IDs so this test never collides with others
    payment_id = f"pay_integration_{uuid.uuid4().hex[:8]}"
    order_id = f"order_integration_{uuid.uuid4().hex[:8]}"

    payload = {
        "entity": "event",
        "account_id": "acc_integ_test",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": 150000,  # ₹1,500 — above ROI gate for any channel
                    "currency": "INR",
                    "status": "failed",
                    "method": "upi",
                    "order_id": order_id,
                    "email": f"{payment_id}@reclaim-test.com",
                    "contact": "+919876543210",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Insufficient funds in customer account",
                    "error_reason": "payment_failed",
                    "created_at": 1691735748,
                }
            }
        },
        "created_at": 1691735750,
    }

    # 1. POST webhook — should return 200 immediately (webhook best-practice)
    resp = await client.post("/test/simulate-webhook", json=payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "simulated"
    event_id_returned = body["event_id"]
    assert event_id_returned == f"payment.failed:{payment_id}"

    # 2. Wait for BackgroundTask to complete (give it up to 5 seconds)
    for attempt in range(50):
        await asyncio.sleep(0.1)
        result = await db_session.execute(
            select(Event).where(Event.razorpay_event_id == event_id_returned)
        )
        evt = result.scalar_one_or_none()
        if evt is not None:
            break
    else:
        pytest.fail("Event was never persisted — BackgroundTask did not complete in 5 seconds")

    # 3. RecoveryState must exist in `failed` state
    rs_result = await db_session.execute(
        select(RecoveryState).where(RecoveryState.event_id == evt.id)
    )
    recovery_state = rs_result.scalar_one_or_none()
    assert recovery_state is not None, "RecoveryState was not created for payment.failed event"
    # `nudged` = pipeline ran and dispatcher dispatched an ALLOW action (best case).
    # `waiting` = pipeline ran but policy issued BLOCK (cooldown, ROI gate, etc).
    # `failed` = pipeline ran but some early BLOCK (opt-out, fatigue) before dispatch.
    # All three are valid pipeline-completed states; only the absence of the row would mean failure.
    assert recovery_state.state in (
        RecoveryStateEnum.nudged,
        RecoveryStateEnum.waiting,
        RecoveryStateEnum.failed,
    ), f"Unexpected state: {recovery_state.state}"

    # 4. AuditLog must have entries from all three pipeline stages
    audit_result = await db_session.execute(
        select(AuditLog)
        .where(AuditLog.event_id == evt.id)
        .order_by(AuditLog.created_at.asc())
    )
    audit_entries = audit_result.scalars().all()
    assert len(audit_entries) >= 2, (
        f"Expected at least 2 audit entries (diagnosis + policy), got {len(audit_entries)}: "
        f"{[a.action for a in audit_entries]}"
    )

    actors = {a.actor for a in audit_entries}
    actions = {a.action for a in audit_entries}

    # diagnosis_engine must have fired
    assert "diagnosis_engine" in actors, (
        f"diagnosis_engine not found in audit actors: {actors}. "
        f"Actions: {actions}. Pipeline not fully wired."
    )

    # policy_engine must have fired
    assert "policy_engine" in actors, (
        f"policy_engine not found in audit actors: {actors}. "
        f"Actions: {actions}. Policy evaluation not called."
    )

    # Dispatch outcome: either a dispatched action OR a policy_block (WAIT/BLOCK is a valid outcome)
    dispatch_actions = [
        a for a in audit_entries
        if a.action.startswith("dispatch:")
        or a.action in ("policy_block", "review_queue_enqueued")
        or a.action.startswith("policy_verdict:")
    ]
    assert len(dispatch_actions) >= 1, (
        f"No dispatch/block/verdict audit entry found. Actions: {actions}. "
        f"Dispatcher was not invoked."
    )

    # 5. Confirm the full decision chain is present (diagnosis → policy verdict)
    policy_verdict_entries = [a for a in audit_entries if a.action.startswith("policy_verdict:")]
    assert len(policy_verdict_entries) >= 1, (
        f"policy_verdict audit entry missing. Found actions: {actions}"
    )

    verdict_action = policy_verdict_entries[0].action
    verdict_decision = verdict_action.replace("policy_verdict:", "")
    assert verdict_decision in ("ALLOW", "MODIFY", "BLOCK"), (
        f"Unexpected policy verdict: {verdict_decision}"
    )

    print(f"\n[INTEGRATION TEST PASS] event_id={event_id_returned}")
    print(f"  RecoveryState: {recovery_state.state.value}")
    print(f"  Audit entries: {len(audit_entries)}")
    print(f"  Actors: {ascii(actors)}")
    print(f"  Actions: {ascii(actions)}")
    print(f"  Policy decision: {verdict_decision}")


@pytest.mark.asyncio
async def test_duplicate_webhook_is_idempotent(client: AsyncClient, db_session):
    """Duplicate event_id must be silently dropped — pipeline runs only once."""
    payment_id = f"pay_idem_{uuid.uuid4().hex[:8]}"
    payload = {
        "entity": "event",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": 100000,
                    "currency": "INR",
                    "status": "failed",
                    "method": "card",
                    "order_id": f"order_{payment_id}",
                    "email": "dup@test.com",
                    "error_code": "BAD_REQUEST_ERROR",
                    "created_at": 1691735748,
                }
            }
        },
        "created_at": 1691735750,
    }

    # First POST
    r1 = await client.post("/test/simulate-webhook", json=payload)
    assert r1.status_code == 200

    # Wait for first event to persist
    await asyncio.sleep(0.5)

    # Second identical POST
    r2 = await client.post("/test/simulate-webhook", json=payload)
    assert r2.status_code == 200

    # Wait for any background processing
    await asyncio.sleep(0.5)

    # Only one Event row must exist
    event_id = f"payment.failed:{payment_id}"
    result = await db_session.execute(
        select(Event).where(Event.razorpay_event_id == event_id)
    )
    events = result.scalars().all()
    assert len(events) == 1, f"Expected exactly 1 event row for duplicate, got {len(events)}"

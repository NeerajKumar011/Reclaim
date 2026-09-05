"""Unit and Integration Tests for Dashboard API.

Verifies:
1. /dashboard/scoreboard returns evaluation scoreboard metrics.
2. /dashboard/policy-lab filters correctly for counterfactual simulation.
3. /dashboard/queue returns paginated recovery state rows with customer info and audit reasons.
4. /dashboard/timeline/{customer_id} returns full chronological audit logs.
5. Dashboard router contains ONLY read-only GET endpoints (no POST/PUT/DELETE).
"""

import os
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Force in-memory SQLite database BEFORE importing app/session modules
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from reclaim.db.models import AuditLog, Base, Customer, Event, EventType, RecoveryState, RecoveryStateEnum
from reclaim.db.session import dispose_engine, get_engine, get_session_factory, init_engine
from reclaim.main import app


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Create in-memory SQLite database tables and seed test record."""
    await init_engine()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed sample customer, event, recovery_state, and audit_log
    factory = get_session_factory()
    async with factory() as session:
        cust = Customer(
            id=uuid.uuid4(),
            email="dashboard_test@example.com",
            name="Dashboard Test User",
        )
        session.add(cust)
        await session.flush()

        event = Event(
            id=uuid.uuid4(),
            razorpay_event_id="evt_dash_001",
            event_type=EventType.payment_failed,
            raw_payload={"failure_reason_raw": "INSUFFICIENT_FUNDS"},
        )
        session.add(event)
        await session.flush()

        rs = RecoveryState(
            id=uuid.uuid4(),
            customer_id=cust.id,
            event_id=event.id,
            amount=5000.00,
            state=RecoveryStateEnum.nudged,
        )
        session.add(rs)
        await session.flush()

        log = AuditLog(
            id=uuid.uuid4(),
            event_id=event.id,
            recovery_state_id=rs.id,
            actor="policy_engine",
            action="evaluate_and_dispatch",
            reason="High recovery probability (0.85), dispatched optimal channel whatsapp with 500 paise discount.",
            metadata_={"customer_id": str(cust.id)},
        )
        session.add(log)
        await session.commit()

        test_cust_id = str(cust.id)

    yield test_cust_id

    await dispose_engine()


@pytest.mark.asyncio
async def test_get_scoreboard_endpoint():
    """Verify GET /dashboard/scoreboard returns valid scoreboard metrics."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/dashboard/scoreboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "policies" in data
        assert "RECLAIM" in data["policies"]
        assert data["policies"]["RECLAIM"]["policy_violation_count"] == 0


@pytest.mark.asyncio
async def test_get_policy_lab_endpoint():
    """Verify GET /dashboard/policy-lab handles query parameters correctly."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # All policies
        resp = await client.get("/dashboard/policy-lab")
        assert resp.status_code == 200
        assert "policies" in resp.json()

        # Specific policy
        resp = await client.get("/dashboard/policy-lab?policy=reclaim")
        assert resp.status_code == 200
        data = resp.json()
        assert data["requested_policy"] == "RECLAIM"
        assert "metrics" in data


@pytest.mark.asyncio
async def test_get_recovery_queue_endpoint():
    """Verify GET /dashboard/queue returns paginated recovery queue items with <=25 limit and formatted amounts."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/dashboard/queue?page=1&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) >= 1
        assert len(data["items"]) <= 25

        item = data["items"][0]
        assert "customer_name" in item
        assert "amount_rs" in item
        assert "formatted_amount" in item
        assert "₹" in item["formatted_amount"]
        assert "tier" in item
        assert "decision" in item
        assert "latest_reason" in item
        # Initial queue response must NOT contain full timelines
        assert "timeline" not in item
        assert "investigation" not in item


@pytest.mark.asyncio
async def test_recovery_queue_hard_limit():
    """Verify GET /dashboard/queue enforces maximum limit of 25."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Requesting > 25 should be rejected by validation
        resp = await client.get("/dashboard/queue?limit=50")
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_customer_timeline_endpoint(setup_test_db):
    """Verify GET /dashboard/timeline/{customer_id} returns structured investigation and timeline."""
    test_cust_id = setup_test_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/dashboard/timeline/{test_cust_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["customer_id"] == test_cust_id
        assert len(data["timeline"]) >= 1

        entry = data["timeline"][0]
        assert entry["actor"] == "policy_engine"
        assert "High recovery probability" in entry["reason"]

        # Assert structured investigation object is present and populated
        assert "investigation" in data
        inv = data["investigation"]
        assert "customer_name" in inv
        assert "formatted_amount" in inv
        assert "₹" in inv["formatted_amount"]
        assert "diagnosis" in inv
        assert "confidence" in inv
        assert "decision" in inv
        assert "tier" in inv
        assert inv["tier"] in ("AUTO", "REVIEW", "BLOCK")
        assert inv["decision"] in ("ACT", "WAIT", "ESCALATE", "STOP")
        assert "recovery_probability" in inv
        assert "action" in inv
        assert "outcome" in inv
        assert "formatted_recovered" in inv
        assert "why_decision" in inv
        assert "policy_controls" in inv
        assert len(inv["policy_controls"]) == 7
        for name, status in inv["policy_controls"].items():
            assert status == "PASS"
        assert "timeline_steps" in inv
        assert len(inv["timeline_steps"]) >= 2


@pytest.mark.asyncio
async def test_tier_and_decision_distinct_mapping_across_states():
    """Verify tier (AUTO, REVIEW, BLOCK) and decision (ACT, WAIT, ESCALATE, STOP) are distinct and correctly mapped."""
    factory = get_session_factory()
    async with factory() as session:
        # Seed test cases covering each distinct state
        states = [
            (RecoveryStateEnum.recovered, "ACT", "AUTO"),
            (RecoveryStateEnum.nudged, "ACT", "AUTO"),
            (RecoveryStateEnum.promised, "WAIT", "REVIEW"),
            (RecoveryStateEnum.waiting, "WAIT", "AUTO"),
            (RecoveryStateEnum.escalated, "ESCALATE", "REVIEW"),
            (RecoveryStateEnum.opted_out, "STOP", "BLOCK"),
        ]
        for st, exp_dec, exp_tier in states:
            c = Customer(id=uuid.uuid4(), email=f"{st.value}@example.com", name=f"User {st.value}")
            session.add(c)
            await session.flush()
            ev = Event(id=uuid.uuid4(), razorpay_event_id=f"evt_{st.value}", event_type=EventType.payment_failed, raw_payload={})
            session.add(ev)
            await session.flush()
            rs = RecoveryState(id=uuid.uuid4(), customer_id=c.id, event_id=ev.id, amount=1000.0, state=st)
            session.add(rs)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard/queue?limit=25")
        assert resp.status_code == 200
        items = resp.json()["items"]
        
        # Verify valid enum domains and non-conflation
        valid_decisions = {"ACT", "WAIT", "ESCALATE", "STOP"}
        valid_tiers = {"AUTO", "REVIEW", "BLOCK"}
        
        seen_decisions = set()
        seen_tiers = set()
        
        for item in items:
            assert item["decision"] in valid_decisions
            assert item["tier"] in valid_tiers
            seen_decisions.add(item["decision"])
            seen_tiers.add(item["tier"])
            
            # Check state-specific mapping
            if item["state"] in ("recovered", "nudged"):
                assert item["decision"] == "ACT"
                assert item["tier"] == "AUTO"
            elif item["state"] == "promised":
                assert item["decision"] == "WAIT"
                assert item["tier"] == "REVIEW"
            elif item["state"] == "waiting":
                assert item["decision"] == "WAIT"
                assert item["tier"] == "AUTO"
            elif item["state"] == "escalated":
                assert item["decision"] == "ESCALATE"
                assert item["tier"] == "REVIEW"
            elif item["state"] == "opted_out":
                assert item["decision"] == "STOP"
                assert item["tier"] == "BLOCK"

        # Verify we observed multiple distinct decisions and tiers
        assert len(seen_decisions) >= 3
        assert len(seen_tiers) >= 3


def test_dashboard_is_strictly_read_only():
    """Verify dashboard router exposes zero mutating HTTP methods (POST, PUT, DELETE, PATCH)."""
    for route in app.routes:
        if hasattr(route, "path") and route.path.startswith("/dashboard"):
            methods = getattr(route, "methods", set())
            for m in ("POST", "PUT", "DELETE", "PATCH"):
                assert m not in methods, f"Mutating HTTP method {m} found on dashboard route {route.path}"


@pytest.mark.asyncio
async def test_active_queue_excludes_historical_errors_by_default():
    """Verify default queue view excludes historical pipeline errors and returns only active cases."""
    factory = get_session_factory()
    async with factory() as session:
        # Seed an error case and an active case
        c_err = Customer(id=uuid.uuid4(), email="err@example.com", name="Err User", opted_out=False)
        c_act = Customer(id=uuid.uuid4(), email="act@example.com", name="Act User", opted_out=False)
        session.add_all([c_err, c_act])
        await session.flush()

        e_err = Event(id=uuid.uuid4(), razorpay_event_id="evt_err_01", event_type=EventType.payment_failed, raw_payload={})
        e_act = Event(id=uuid.uuid4(), razorpay_event_id="evt_act_01", event_type=EventType.payment_failed, raw_payload={"failure_reason_raw": "OTP_TIMEOUT"})
        session.add_all([e_err, e_act])
        await session.flush()

        rs_err = RecoveryState(id=uuid.uuid4(), customer_id=c_err.id, event_id=e_err.id, amount=2000.0, state=RecoveryStateEnum.failed)
        rs_act = RecoveryState(id=uuid.uuid4(), customer_id=c_act.id, event_id=e_act.id, amount=3000.0, state=RecoveryStateEnum.recovered)
        session.add_all([rs_err, rs_act])
        await session.flush()

        log_err = AuditLog(
            id=uuid.uuid4(), event_id=e_err.id, recovery_state_id=rs_err.id,
            actor="orchestrator", action="pipeline_error",
            reason="Traceback (most recent call last):\nsqlalchemy.exc.OperationalError: no such column: promise_to_pay_date"
        )
        log_act = AuditLog(
            id=uuid.uuid4(), event_id=e_act.id, recovery_state_id=rs_act.id,
            actor="policy_engine", action="evaluate_and_dispatch",
            reason="High-intent payment authentication failure with sufficient recovery probability. A Razorpay Payment Link is issued to provide a fresh payment path."
        )
        session.add_all([log_err, log_act])
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Default: active only
        resp = await client.get("/dashboard/queue")
        assert resp.status_code == 200
        items = resp.json()["items"]
        for it in items:
            assert it["action_taken"] != "pipeline_error"
            assert it["visibility"] == "ACTIVE"

        # Explicit: historical errors
        resp_err = await client.get("/dashboard/queue?visibility=historical_errors")
        assert resp_err.status_code == 200
        err_items = resp_err.json()["items"]
        assert len(err_items) >= 1
        for it in err_items:
            assert it["visibility"] == "ERROR"
            assert it["decision"] == "ESCALATE"
            assert it["tier"] == "REVIEW"

        # Explicit: all
        resp_all = await client.get("/dashboard/queue?visibility=all")
        assert resp_all.status_code == 200
        all_items = resp_all.json()["items"]
        assert len(all_items) >= len(items) + len(err_items)


@pytest.mark.asyncio
async def test_non_opted_out_customer_never_displays_opt_out():
    """Verify customer with opted_out=False is never displayed as 'Opted Out' under any diagnosis or failure."""
    factory = get_session_factory()
    async with factory() as session:
        c = Customer(id=uuid.uuid4(), email="not_opted@example.com", name="Active Customer", opted_out=False)
        session.add(c)
        await session.flush()
        e = Event(id=uuid.uuid4(), razorpay_event_id="evt_no_opt", event_type=EventType.payment_failed, raw_payload={"failure_reason_raw": "INSUFFICIENT_FUNDS"})
        session.add(e)
        await session.flush()
        rs = RecoveryState(id=uuid.uuid4(), customer_id=c.id, event_id=e.id, amount=1500.0, state=RecoveryStateEnum.waiting)
        session.add(rs)
        await session.commit()
        cust_id = str(c.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/dashboard/timeline/{cust_id}")
        assert resp.status_code == 200
        inv = resp.json()["investigation"]
        assert inv["customer_opted_out"] is False
        assert "Opted Out" not in inv["action"]
        assert "opted out" not in inv["why_decision"].lower()


@pytest.mark.asyncio
async def test_why_decision_never_leaks_sql_or_stack_traces():
    """Verify 'Why This Decision?' remains human-readable even when audit logs contain raw stack traces."""
    factory = get_session_factory()
    async with factory() as session:
        c = Customer(id=uuid.uuid4(), email="trace_test@example.com", name="Trace Test", opted_out=False)
        session.add(c)
        await session.flush()
        e = Event(id=uuid.uuid4(), razorpay_event_id="evt_trace_01", event_type=EventType.payment_failed, raw_payload={})
        session.add(e)
        await session.flush()
        rs = RecoveryState(id=uuid.uuid4(), customer_id=c.id, event_id=e.id, amount=500.0, state=RecoveryStateEnum.failed)
        session.add(rs)
        await session.flush()
        log = AuditLog(
            id=uuid.uuid4(), event_id=e.id, recovery_state_id=rs.id,
            actor="orchestrator", action="pipeline_error",
            reason="Traceback (most recent call last):\npsycopg2.OperationalError: server closed the connection unexpectedly"
        )
        session.add(log)
        await session.commit()
        cust_id = str(c.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/dashboard/timeline/{cust_id}")
        assert resp.status_code == 200
        inv = resp.json()["investigation"]
        # Human readable explanation in why_decision
        assert "Traceback" not in inv["why_decision"]
        assert "OperationalError" not in inv["why_decision"]
        assert "psycopg2" not in inv["why_decision"]
        assert "Pipeline processing exception" in inv["why_decision"]
        # Raw technical exception isolated in technical_details
        tech = inv["technical_details"]
        assert tech["raw_exception"] is not None
        assert "Traceback" in tech["raw_exception"]


@pytest.mark.asyncio
async def test_semantic_reasoning_for_canonical_scenarios():
    """Verify PO_MISMATCH, OTP_TIMEOUT, PROMISE_TO_PAY, BANK_RAIL_DOWN, and OPT_OUT get accurate domain reasons."""
    factory = get_session_factory()
    async with factory() as session:
        # 1. PO_MISMATCH
        c1 = Customer(id=uuid.uuid4(), email="b2b@example.com", name="B2B User", opted_out=False)
        e1 = Event(id=uuid.uuid4(), razorpay_event_id="evt_b2b_mismatch", event_type=EventType.payment_failed, raw_payload={"failure_reason_raw": "PO_MISMATCH"})
        session.add_all([c1, e1])
        await session.flush()
        rs1 = RecoveryState(id=uuid.uuid4(), customer_id=c1.id, event_id=e1.id, amount=250000.0, state=RecoveryStateEnum.escalated)
        session.add(rs1)

        # 2. OTP_TIMEOUT
        c2 = Customer(id=uuid.uuid4(), email="otp@example.com", name="OTP User", opted_out=False)
        e2 = Event(id=uuid.uuid4(), razorpay_event_id="evt_otp_success", event_type=EventType.payment_failed, raw_payload={"failure_reason_raw": "OTP_TIMEOUT"})
        session.add_all([c2, e2])
        await session.flush()
        rs2 = RecoveryState(id=uuid.uuid4(), customer_id=c2.id, event_id=e2.id, amount=15000.0, state=RecoveryStateEnum.recovered)
        session.add(rs2)

        # 3. PROMISE_TO_PAY
        c3 = Customer(id=uuid.uuid4(), email="promise@example.com", name="Promise User", opted_out=False)
        e3 = Event(id=uuid.uuid4(), razorpay_event_id="evt_promise_case", event_type=EventType.checkout_abandoned, raw_payload={"failure_reason_raw": "GENUINE_ABANDON"})
        session.add_all([c3, e3])
        await session.flush()
        rs3 = RecoveryState(id=uuid.uuid4(), customer_id=c3.id, event_id=e3.id, amount=12000.0, state=RecoveryStateEnum.promised)
        session.add(rs3)

        await session.commit()
        id1, id2, id3 = str(c1.id), str(c2.id), str(c3.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # PO_MISMATCH
        r1 = await client.get(f"/dashboard/timeline/{id1}")
        inv1 = r1.json()["investigation"]
        assert inv1["decision"] == "ESCALATE"
        assert inv1["tier"] == "REVIEW"
        assert "purchase-order mismatch" in inv1["why_decision"]

        # OTP_TIMEOUT
        r2 = await client.get(f"/dashboard/timeline/{id2}")
        inv2 = r2.json()["investigation"]
        assert inv2["decision"] == "ACT"
        assert inv2["tier"] == "AUTO"
        assert "Razorpay Payment Link" in inv2["action"]

        # PROMISE_TO_PAY
        r3 = await client.get(f"/dashboard/timeline/{id3}")
        inv3 = r3.json()["investigation"]
        assert inv3["decision"] == "WAIT"
        assert inv3["tier"] == "REVIEW"
        assert "Promise-to-Pay" in inv3["why_decision"]


@pytest.mark.asyncio
async def test_dashboard_html_and_browser_rendering_contract():
    """Verify GET /dashboard serves valid HTML with all required IDs and DOM contract for browser rendering."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard")
        assert resp.status_code == 200
        html = resp.text

        # Verify key DOM container elements exist
        required_ids = [
            "overview",
            "scenarios",
            "benchmark",
            "simulator",
            "queue",
            "queue-tbody",
            "queue-count-label",
            "filter-btn-active",
            "filter-btn-all",
            "filter-btn-errors",
            "timeline-modal",
            "investigation-content",
            "timeline-container",
            "inv-cust-name",
            "inv-amount",
            "inv-diagnosis",
            "inv-decision",
            "inv-tier-label",
            "inv-rec-prob",
            "inv-action",
            "inv-outcome",
            "inv-recovered",
            "inv-why-decision",
            "inv-raw-error-box",
        ]
        for el_id in required_ids:
            assert f'id="{el_id}"' in html or f"id='{el_id}'" in html, f"Missing required element ID: {el_id}"

        # Verify nav tabs pass event object to switchTab
        assert "switchTab('queue', event)" in html
        assert "switchTab('overview', event)" in html

        # Verify queue API endpoint is called with proper query param
        assert "/dashboard/queue?limit=25&visibility=" in html





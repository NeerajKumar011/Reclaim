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
    """Verify GET /dashboard/queue returns paginated recovery queue items."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/dashboard/queue?page=1&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) >= 1

        item = data["items"][0]
        assert "customer_name" in item
        assert "amount_rs" in item
        assert "tier" in item
        assert "latest_reason" in item


@pytest.mark.asyncio
async def test_get_customer_timeline_endpoint(setup_test_db):
    """Verify GET /dashboard/timeline/{customer_id} returns full audit log history."""
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


def test_dashboard_is_strictly_read_only():
    """Verify dashboard router exposes zero mutating HTTP methods (POST, PUT, DELETE, PATCH)."""
    for route in app.routes:
        if hasattr(route, "path") and route.path.startswith("/dashboard"):
            methods = getattr(route, "methods", set())
            for m in ("POST", "PUT", "DELETE", "PATCH"):
                assert m not in methods, f"Mutating HTTP method {m} found on dashboard route {route.path}"

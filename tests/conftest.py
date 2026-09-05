"""Shared test fixtures for RECLAIM tests.

Uses an in-memory SQLite database for fast, isolated tests.
PostgreSQL-specific features (JSONB) are handled via type adaptation.
"""

import asyncio
import os
import uuid
from typing import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from reclaim.db.models import Base

# Force dev mode for tests
os.environ["APP_ENV"] = "dev"
os.environ["RAZORPAY_WEBHOOK_SECRET"] = ""
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["GEMINI_API_KEY"] = ""  # Unit tests use fast deterministic offline classifier



@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create a fresh in-memory SQLite engine per test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean database session for each test."""
    factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTP test client with a patched DB session.

    Patches the session factory so the FastAPI app uses our test DB.
    Waits briefly after each request to let BackgroundTasks complete.
    """
    factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    with patch("reclaim.ingestion.router.get_session_factory", return_value=factory):
        from reclaim.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ---------------------------------------------------------------------------
# Sample payload factories
# ---------------------------------------------------------------------------

def make_payment_failed_payload(
    payment_id: str = "pay_test123",
    order_id: str = "order_test456",
    amount: int = 50000,
    email: str = "test@example.com",
    error_code: str = "BAD_REQUEST_ERROR",
) -> dict:
    """Create a realistic Razorpay payment.failed webhook payload."""
    return {
        "entity": "event",
        "account_id": "acc_test",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": amount,
                    "currency": "INR",
                    "status": "failed",
                    "method": "upi",
                    "order_id": order_id,
                    "email": email,
                    "contact": "+919876543210",
                    "error_code": error_code,
                    "error_description": "Payment failed due to incorrect OTP",
                    "error_reason": "payment_failed",
                    "created_at": 1691735748,
                }
            }
        },
        "created_at": 1691735750,
    }


def make_payment_captured_payload(
    payment_id: str = "pay_test123",
    order_id: str = "order_test456",
    amount: int = 50000,
    email: str = "test@example.com",
) -> dict:
    """Create a realistic Razorpay payment.captured webhook payload."""
    return {
        "entity": "event",
        "account_id": "acc_test",
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": amount,
                    "currency": "INR",
                    "status": "captured",
                    "method": "upi",
                    "order_id": order_id,
                    "email": email,
                    "contact": "+919876543210",
                    "captured": True,
                    "created_at": 1691735800,
                }
            }
        },
        "created_at": 1691735802,
    }

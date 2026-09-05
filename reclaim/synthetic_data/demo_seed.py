"""Curated Demo Dataset Seeding Script.

Seeds 5 fixed, repeatable scenarios into the RECLAIM database for live presentation:
  1. INSUFFICIENT_FUNDS case blocked on first pass (the "why we didn't act" demo beat).
  2. Customer reply ("salary parso aayegi bhai, tab kar dunga") triggering promise-to-pay extraction.
  3. BANK_RAIL_DOWN case demonstrating low recovery probability and an explicit BLOCK reason.
  4. End-to-end recovered case with full audit trail for the Customer Timeline view.
  5. Opted-out customer whose event is blocked immediately.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
import uuid

from reclaim.db.models import (
    AuditLog,
    Base,
    Customer,
    Event,
    EventType,
    ProcessingStatus,
    RecoveryMemory,
    RecoveryState,
    RecoveryStateEnum,
)
from reclaim.db.session import dispose_engine, get_engine, get_session_factory, init_engine

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def seed_curated_demo_dataset() -> int:
    """Seed exactly 5 curated, deterministic demo scenarios into the database."""
    await init_engine()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    now = _utc_now()

    async with factory() as session:
        # Scenario 1: INSUFFICIENT_FUNDS — BLOCKED on first pass (High Fatigue)
        c1 = Customer(
            id=uuid.UUID("10000000-0000-0000-0000-000000000001"),
            razorpay_customer_id="cust_demo_funds_001",
            name="Aarav Sharma",
            email="aarav.sharma@example.com",
            phone="+919876543210",
            preferred_language="en",
            opted_out=False,
        )
        e1 = Event(
            id=uuid.UUID("20000000-0000-0000-0000-000000000001"),
            razorpay_event_id="evt_demo_funds_001",
            event_type=EventType.payment_failed,
            raw_payload={"failure_reason_raw": "INSUFFICIENT_FUNDS", "amount": 750000},
            processing_status=ProcessingStatus.processed,
            received_at=now - timedelta(minutes=45),
        )
        rs1 = RecoveryState(
            id=uuid.UUID("30000000-0000-0000-0000-000000000001"),
            customer_id=c1.id,
            event_id=e1.id,
            amount=7500.00,
            state=RecoveryStateEnum.waiting,
            updated_at=now - timedelta(minutes=40),
        )
        m1 = RecoveryMemory(
            customer_id=c1.id,
            fatigue_score_last_computed=0.88,
            historical_response_rate=0.15,
            preferred_channel="sms",
        )
        log1 = AuditLog(
            id=uuid.UUID("40000000-0000-0000-0000-000000000001"),
            event_id=e1.id,
            recovery_state_id=rs1.id,
            actor="policy_engine",
            action="evaluate_and_block",
            reason="Diagnosed cause INSUFFICIENT_FUNDS under high fatigue score (0.88) and low response rate (0.15). Decision: BLOCK to prevent customer annoyance.",
            metadata_={"customer_id": str(c1.id), "tier": "BLOCK"},
            created_at=now - timedelta(minutes=40),
        )

        # Scenario 2: Hinglish Promise-to-Pay Extraction ("salary parso aayegi bhai")
        c2 = Customer(
            id=uuid.UUID("10000000-0000-0000-0000-000000000002"),
            razorpay_customer_id="cust_demo_hinglish_002",
            name="Vikram Patel",
            email="vikram.patel@example.com",
            phone="+919876543211",
            preferred_language="hi",
            opted_out=False,
        )
        e2 = Event(
            id=uuid.UUID("20000000-0000-0000-0000-000000000002"),
            razorpay_event_id="evt_demo_hinglish_002",
            event_type=EventType.checkout_abandoned,
            raw_payload={"failure_reason_raw": "GENUINE_ABANDON", "amount": 1200000},
            processing_status=ProcessingStatus.processed,
            received_at=now - timedelta(hours=3),
        )
        rs2 = RecoveryState(
            id=uuid.UUID("30000000-0000-0000-0000-000000000002"),
            customer_id=c2.id,
            event_id=e2.id,
            amount=12000.00,
            state=RecoveryStateEnum.promised,
            updated_at=now - timedelta(hours=1),
        )
        m2 = RecoveryMemory(
            customer_id=c2.id,
            fatigue_score_last_computed=0.10,
            historical_response_rate=0.85,
            preferred_channel="whatsapp",
        )
        log2_init = AuditLog(
            id=uuid.UUID("40000000-0000-0000-0000-000000000002"),
            event_id=e2.id,
            recovery_state_id=rs2.id,
            actor="orchestrator",
            action="dispatch_whatsapp",
            reason="Authorized channel whatsapp with max discount 0 paise.",
            metadata_={"customer_id": str(c2.id)},
            created_at=now - timedelta(hours=2, minutes=30),
        )
        log2_promise = AuditLog(
            id=uuid.UUID("40000000-0000-0000-0000-000000000022"),
            event_id=e2.id,
            recovery_state_id=rs2.id,
            actor="promise_extractor",
            action="extract_promise",
            reason="Customer replied in Hinglish: 'salary parso aayegi bhai, tab kar dunga'. Extracted promised payment date: 2026-08-31. Reminders suppressed until 2026-09-01.",
            metadata_={"customer_id": str(c2.id), "promised_date": "2026-08-31"},
            created_at=now - timedelta(hours=1),
        )

        # Scenario 3: BANK_RAIL_DOWN — Infrastructure Outage BLOCK
        c3 = Customer(
            id=uuid.UUID("10000000-0000-0000-0000-000000000003"),
            razorpay_customer_id="cust_demo_bankdown_003",
            name="Priya Nair",
            email="priya.nair@example.com",
            phone="+919876543212",
            preferred_language="en",
            opted_out=False,
        )
        e3 = Event(
            id=uuid.UUID("20000000-0000-0000-0000-000000000003"),
            razorpay_event_id="evt_demo_bankdown_003",
            event_type=EventType.payment_failed,
            raw_payload={"failure_reason_raw": "BANK_RAIL_DOWN", "amount": 499900},
            processing_status=ProcessingStatus.processed,
            received_at=now - timedelta(minutes=20),
        )
        rs3 = RecoveryState(
            id=uuid.UUID("30000000-0000-0000-0000-000000000003"),
            customer_id=c3.id,
            event_id=e3.id,
            amount=4999.00,
            state=RecoveryStateEnum.waiting,
            updated_at=now - timedelta(minutes=18),
        )
        log3 = AuditLog(
            id=uuid.UUID("40000000-0000-0000-0000-000000000003"),
            event_id=e3.id,
            recovery_state_id=rs3.id,
            actor="policy_engine",
            action="evaluate_and_block",
            reason="Bank rail downtime detected for HDFC UPI gateway. Recovery probability is low during infrastructure outages. Decision: BLOCK to avoid sending useless nudges.",
            metadata_={"customer_id": str(c3.id), "tier": "BLOCK"},
            created_at=now - timedelta(minutes=18),
        )

        # Scenario 4: End-to-End Recovered Case with Full Audit Trail
        c4 = Customer(
            id=uuid.UUID("10000000-0000-0000-0000-000000000004"),
            razorpay_customer_id="cust_demo_recovered_004",
            name="Rahul Verma",
            email="rahul.verma@example.com",
            phone="+919876543213",
            preferred_language="en",
            opted_out=False,
        )
        e4 = Event(
            id=uuid.UUID("20000000-0000-0000-0000-000000000004"),
            razorpay_event_id="evt_demo_recovered_004",
            event_type=EventType.payment_failed,
            raw_payload={"failure_reason_raw": "OTP_TIMEOUT", "amount": 1500000},
            processing_status=ProcessingStatus.processed,
            received_at=now - timedelta(hours=5),
        )
        rs4 = RecoveryState(
            id=uuid.UUID("30000000-0000-0000-0000-000000000004"),
            customer_id=c4.id,
            event_id=e4.id,
            amount=15000.00,
            state=RecoveryStateEnum.recovered,
            updated_at=now - timedelta(hours=4),
        )
        log4_1 = AuditLog(
            id=uuid.UUID("40000000-0000-0000-0000-000000000004"),
            event_id=e4.id,
            recovery_state_id=rs4.id,
            actor="ingestion",
            action="payment_failed",
            reason="Payment failed due to OTP timeout for amount ₹15,000.00.",
            metadata_={"customer_id": str(c4.id)},
            created_at=now - timedelta(hours=5),
        )
        log4_2 = AuditLog(
            id=uuid.UUID("40000000-0000-0000-0000-000000000044"),
            event_id=e4.id,
            recovery_state_id=rs4.id,
            actor="policy_engine",
            action="evaluate_and_dispatch",
            reason="High recovery probability (0.92) for OTP_TIMEOUT. Authorized channel razorpay_payment_link with 0 paise discount.",
            metadata_={"customer_id": str(c4.id), "tier": "AUTO"},
            created_at=now - timedelta(hours=4, minutes=50),
        )
        log4_3 = AuditLog(
            id=uuid.UUID("40000000-0000-0000-0000-000000000444"),
            event_id=e4.id,
            recovery_state_id=rs4.id,
            actor="orchestrator",
            action="payment_captured",
            reason="Customer completed payment via Razorpay Payment Link plink_demo_99. Revenue recovered successfully!",
            metadata_={"customer_id": str(c4.id)},
            created_at=now - timedelta(hours=4),
        )

        # Scenario 5: Customer Opt-Out (Immediate BLOCK)
        c5 = Customer(
            id=uuid.UUID("10000000-0000-0000-0000-000000000005"),
            razorpay_customer_id="cust_demo_optout_005",
            name="Neha Gupta",
            email="neha.gupta@example.com",
            phone="+919876543214",
            preferred_language="en",
            opted_out=True,
        )
        e5 = Event(
            id=uuid.UUID("20000000-0000-0000-0000-000000000005"),
            razorpay_event_id="evt_demo_optout_005",
            event_type=EventType.payment_failed,
            raw_payload={"failure_reason_raw": "INSUFFICIENT_FUNDS", "amount": 250000},
            processing_status=ProcessingStatus.processed,
            received_at=now - timedelta(minutes=10),
        )
        rs5 = RecoveryState(
            id=uuid.UUID("30000000-0000-0000-0000-000000000005"),
            customer_id=c5.id,
            event_id=e5.id,
            amount=2500.00,
            state=RecoveryStateEnum.opted_out,
            updated_at=now - timedelta(minutes=9),
        )
        log5 = AuditLog(
            id=uuid.UUID("40000000-0000-0000-0000-000000000005"),
            event_id=e5.id,
            recovery_state_id=rs5.id,
            actor="policy_engine",
            action="evaluate_and_block",
            reason="Customer has explicitly opted out of recovery communications. Unconditional BLOCK enforced.",
            metadata_={"customer_id": str(c5.id), "tier": "BLOCK"},
            created_at=now - timedelta(minutes=9),
        )

        session.add_all([c1, c2, c3, c4, c5])
        session.add_all([e1, e2, e3, e4, e5])
        session.add_all([rs1, rs2, rs3, rs4, rs5])
        session.add_all([m1, m2])
        session.add_all([log1, log2_init, log2_promise, log3, log4_1, log4_2, log4_3, log5])

        await session.commit()

    await dispose_engine()
    logger.info("Successfully seeded 5 curated demo scenarios into database.")
    return 5


def main():
    asyncio.run(seed_curated_demo_dataset())


if __name__ == "__main__":
    main()

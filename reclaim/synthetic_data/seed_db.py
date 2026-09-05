"""Database seeding script.

Loads train.jsonl into the database (events, customers, recovery_state tables)
by reusing the existing ingestion processor pipeline (process_webhook_event).
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any

from reclaim.db.models import Base
from reclaim.db.session import get_engine, get_session_factory, init_engine, dispose_engine

from reclaim.ingestion.processor import process_webhook_event

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

TRAIN_JSONL_PATH = Path(__file__).parent / "output" / "train.jsonl"


def _record_to_raw_webhook(record: Dict[str, Any]) -> tuple[dict, str, str]:
    """Convert a synthetic RevenueEvent record into a raw webhook payload, event_id, and event_type_str."""
    event_id = record["event_id"]
    category = record["event_category"]
    meta = record.get("source_metadata", {})
    payment_id = meta.get("payment_id", "pay_synth_000")
    order_id = meta.get("order_id", "order_synth_000")

    if category == "payment_failure":
        event_type_str = "payment_failed"
        event_name = "payment.failed"
        raw_payload = {
            "entity": "event",
            "account_id": "acc_synth",
            "event": event_name,
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "amount": int(record["amount"]),
                        "currency": record.get("currency", "INR"),
                        "status": "failed",
                        "method": meta.get("method", "upi"),
                        "order_id": order_id,
                        "customer_id": f"cust_{record['customer_id'][:8]}",
                        "email": f"user_{record['customer_id'][:8]}@example.com",
                        "contact": "+919876543210",
                        "error_code": record.get("failure_reason_raw", "BAD_REQUEST_ERROR"),
                        "error_description": f"Synthetic failure: {record.get('failure_reason_raw')}",
                        "created_at": 1691735748,
                    }
                }
            },
            "created_at": 1691735750,
        }

    elif category == "cart_abandonment":
        event_type_str = "checkout_abandoned"
        event_name = "checkout.abandoned"
        raw_payload = {
            "event_id": event_id,
            "event": event_name,
            "amount": int(record["amount"]),
            "currency": record.get("currency", "INR"),
            "customer_id": record["customer_id"],
            "failure_reason_raw": record.get("failure_reason_raw"),
            "created_at": 1691735748,
            "source_metadata": meta,
        }

    else:  # invoice_overdue
        event_type_str = "invoice_overdue"
        event_name = "invoice.overdue"
        raw_payload = {
            "event_id": event_id,
            "event": event_name,
            "amount": int(record["amount"]),
            "currency": record.get("currency", "INR"),
            "customer_id": record["customer_id"],
            "failure_reason_raw": record.get("failure_reason_raw"),
            "created_at": 1691735748,
            "source_metadata": meta,
        }

    return raw_payload, event_id, event_type_str


async def seed_database(jsonl_path: Path = TRAIN_JSONL_PATH, limit: int = 500) -> int:
    """Read records from train.jsonl and seed them into the database."""
    if not jsonl_path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {jsonl_path}. Run generator.py first!"
        )

    await init_engine()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()

    records_count = 0
    old_heuristic_flag = os.environ.get("RECLAIM_FORCE_HEURISTIC_DIAGNOSIS")
    os.environ["RECLAIM_FORCE_HEURISTIC_DIAGNOSIS"] = "1"

    try:
        async with factory() as db:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    if limit and records_count >= limit:
                        break
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    raw_payload, event_id, event_type_str = _record_to_raw_webhook(record)

                    try:
                        await process_webhook_event(
                            db=db,
                            raw_payload=raw_payload,
                            razorpay_event_id=event_id,
                            event_type_str=event_type_str,
                        )
                        records_count += 1
                    except Exception as err:
                        await db.rollback()
                        logger.warning(f"Error seeding event {event_id}: {err}")

                    if records_count > 0 and records_count % 100 == 0:
                        logger.info(f"Seeded {records_count} records...")
    finally:
        if old_heuristic_flag is None:
            os.environ.pop("RECLAIM_FORCE_HEURISTIC_DIAGNOSIS", None)
        else:
            os.environ["RECLAIM_FORCE_HEURISTIC_DIAGNOSIS"] = old_heuristic_flag

    await dispose_engine()
    logger.info(f"Successfully seeded {records_count} synthetic events into database.")
    return records_count


def main():
    asyncio.run(seed_database())


if __name__ == "__main__":
    main()


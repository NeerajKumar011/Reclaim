"""API router for webhook ingestion.

Endpoints:
  POST /webhooks/razorpay  — Production webhook receiver (HMAC-verified)
  POST /test/simulate-webhook — Dev-only test endpoint (skips signature)
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from reclaim.config import get_settings
from reclaim.db.session import get_db, get_session_factory
from reclaim.ingestion.normalizer import razorpay_event_to_internal
from reclaim.ingestion.processor import process_webhook_event
from reclaim.ingestion.signature import verify_razorpay_signature

logger = logging.getLogger(__name__)

router = APIRouter()


async def _process_in_background(
    raw_payload: dict,
    razorpay_event_id: str,
    event_type_str: str,
) -> None:
    """Background task wrapper — creates its own DB session."""
    factory = get_session_factory()
    async with factory() as db:
        try:
            await process_webhook_event(
                db=db,
                raw_payload=raw_payload,
                razorpay_event_id=razorpay_event_id,
                event_type_str=event_type_str,
            )
        except Exception:
            await db.rollback()
            logger.exception(
                f"Error processing webhook event {razorpay_event_id}"
            )
            raise


@router.post("/webhooks/razorpay", status_code=200)
async def receive_razorpay_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Receive a Razorpay webhook.

    - Verifies HMAC-SHA256 signature
    - Returns 200 immediately (webhook best practice)
    - Processes the event asynchronously via BackgroundTasks
    """
    settings = get_settings()

    # Read raw body for signature verification
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # Verify signature
    if settings.RAZORPAY_WEBHOOK_SECRET:
        if not verify_razorpay_signature(raw_body, signature, settings.RAZORPAY_WEBHOOK_SECRET):
            logger.warning("Webhook signature verification failed")
            raise HTTPException(status_code=400, detail="Invalid signature")

    # Parse payload
    payload = await request.json()
    event_name = payload.get("event", "")

    # Map to internal event type
    event_type_str = razorpay_event_to_internal(event_name)
    if not event_type_str:
        logger.info(f"Ignoring unhandled event type: {event_name}")
        return {"status": "ignored", "reason": f"unhandled event type: {event_name}"}

    # Generate a stable event ID for idempotency
    # Razorpay doesn't always include a top-level event ID, so we derive one
    razorpay_event_id = _derive_event_id(payload, event_name)

    # Enqueue background processing
    background_tasks.add_task(
        _process_in_background,
        raw_payload=payload,
        razorpay_event_id=razorpay_event_id,
        event_type_str=event_type_str,
    )

    return {"status": "received", "event_id": razorpay_event_id}


@router.post("/test/simulate-webhook", status_code=200)
async def simulate_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Dev-only endpoint to simulate a Razorpay webhook without signature verification.

    Accepts the same payload shape as /webhooks/razorpay.
    """
    settings = get_settings()
    if not settings.is_dev:
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only available in dev mode (APP_ENV=dev)",
        )

    payload = await request.json()
    event_name = payload.get("event", "")

    event_type_str = razorpay_event_to_internal(event_name)
    if not event_type_str:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown event type: {event_name}. "
                   f"Use one of: payment.failed, payment.captured, order.paid, etc.",
        )

    razorpay_event_id = _derive_event_id(payload, event_name)

    background_tasks.add_task(
        _process_in_background,
        raw_payload=payload,
        razorpay_event_id=razorpay_event_id,
        event_type_str=event_type_str,
    )

    return {"status": "simulated", "event_id": razorpay_event_id}


def _derive_event_id(payload: dict, event_name: str) -> str:
    """Derive a deterministic event ID for idempotency.

    Uses the payment/order entity ID + event name to create a stable key.
    Falls back to account_id + created_at if no entity ID found.
    """
    # Try to get a payment ID
    payment_id = (
        payload.get("payload", {})
        .get("payment", {})
        .get("entity", {})
        .get("id", "")
    )
    if payment_id:
        return f"{event_name}:{payment_id}"

    # Try order ID
    order_id = (
        payload.get("payload", {})
        .get("order", {})
        .get("entity", {})
        .get("id", "")
    )
    if order_id:
        return f"{event_name}:{order_id}"

    # Fallback
    account = payload.get("account_id", "unknown")
    created = payload.get("created_at", "0")
    return f"{event_name}:{account}:{created}"

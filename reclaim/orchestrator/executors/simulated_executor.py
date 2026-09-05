"""Simulated Executor for SMS, WhatsApp, Voice Call, and Human Escalation.

Logs dispatches to simulated_dispatch_log and audit_log without making external API calls.
Generates message body using LLMClient pattern.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession

from reclaim.db.models import AuditLog, Customer, Event, SimulatedDispatchLog
from reclaim.diagnosis.llm_client import LLMClient

logger = logging.getLogger(__name__)


def generate_simulated_message(
    customer: Customer,
    channel: str,
    reason: str,
    max_discount_paise: int = 0,
) -> str:
    """Generate communication message body using LLMClient or fallback template."""
    language = getattr(customer, "preferred_language", "en")
    discount_str = f" (Discount offer: Rs. {max_discount_paise // 100})" if max_discount_paise > 0 else ""

    prompt = (
        f"Generate a brief, friendly payment recovery message for a customer via {channel}.\n"
        f"Language requirement: {language}.\n"
        f"Context/Reason: {reason}.\n"
        f"{discount_str}\n"
        f"Keep the message concise and polite."
    )

    try:
        llm = LLMClient()
        if llm.api_key and llm.client:
            raw_msg = llm._call_llm(prompt, system_prompt="You are a helpful customer payment support assistant.")
            if raw_msg and raw_msg.strip():
                return raw_msg.strip()
    except Exception as err:
        logger.warning(f"LLM message generation skipped/failed ({err}). Using fallback template.")

    # Standard fallback templates per channel/language
    if channel == "whatsapp":
        return f"Hi {customer.name or 'there'}, your recent payment was incomplete. Please complete it here{discount_str}. Need help? Reply to this message."
    elif channel == "sms":
        return f"Reclaim Alert: Your payment attempt failed. Click to retry{discount_str}."
    elif channel == "voice_call":
        return f"Hello {customer.name or 'Customer'}, this is an automated courtesy call regarding your recent payment."
    elif channel == "human_escalation":
        return f"INTERNAL ESCALATION NOTICE: Account {customer.id} requires manual outreach for reason: {reason}."
    else:
        return f"Payment recovery notification for customer {customer.id}{discount_str}."


class SimulatedExecutor:
    """Executor for simulated channels (SMS, WhatsApp, Voice Call, Human Escalation)."""

    async def dispatch(
        self,
        db: AsyncSession,
        customer: Customer,
        channel: str,
        reason: str,
        max_discount_paise: int = 0,
        event: Optional[Event] = None,
        recovery_state_id: Optional[Any] = None,
    ) -> SimulatedDispatchLog:
        """Simulate sending a message, write simulated_dispatch_log, and add audit_log."""

        message_body = generate_simulated_message(
            customer=customer,
            channel=channel,
            reason=reason,
            max_discount_paise=max_discount_paise,
        )

        now = datetime.now(timezone.utc)

        # 1. Insert simulated_dispatch_log row
        dispatch_log = SimulatedDispatchLog(
            customer_id=customer.id,
            channel=channel,
            message_body=message_body,
            sent_at=now,
        )
        db.add(dispatch_log)
        await db.flush()

        # 2. Write audit_log entry
        audit_entry = AuditLog(
            event_id=event.id if event else None,
            recovery_state_id=recovery_state_id,
            actor="orchestrator",
            action=f"dispatch:{channel}",
            reason=f"Dispatched simulated message via {channel}: '{message_body[:60]}...'",
            metadata_={
                "channel": channel,
                "dispatch_id": str(dispatch_log.id),
                "customer_id": str(customer.id),
                "max_discount_paise": max_discount_paise,
            },
            created_at=now,
        )
        db.add(audit_entry)
        await db.flush()

        logger.info(f"Simulated dispatch via {channel} for customer {customer.id}")
        return dispatch_log

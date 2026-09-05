"""Outcome Observer — updates Recovery Memory upon terminal recovery outcomes.

Recomputes historical_response_rate, avg_response_latency_hours, and preferred_channel
when a recovery state transitions to recovered or escalated.
Do NOT let the LLM write to recovery_memory directly — only structured pipeline code updates it.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reclaim.db.models import (
    AuditLog,
    RecoveryMemory,
    RecoveryState,
    RecoveryStateEnum,
    SimulatedDispatchLog,
)

logger = logging.getLogger(__name__)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def handle_outcome_transition(
    db: AsyncSession, recovery_state: RecoveryState
) -> RecoveryMemory:
    """Update RecoveryMemory for a customer after a recovered or escalated outcome.

    Args:
        db: AsyncSession database session.
        recovery_state: The updated RecoveryState object.

    Returns:
        Updated RecoveryMemory object.
    """
    customer_id = recovery_state.customer_id
    now = datetime.now(timezone.utc)

    # 1. Fetch or create RecoveryMemory row
    result = await db.execute(
        select(RecoveryMemory).where(RecoveryMemory.customer_id == customer_id)
    )
    memory = result.scalar_one_or_none()

    if memory is None:
        memory = RecoveryMemory(
            customer_id=customer_id,
            preferred_language="en",
            historical_response_rate=0.0,
            fatigue_score_last_computed=0.0,
            last_updated=now,
        )
        db.add(memory)
        await db.flush()

    # 2. Query all RecoveryStates for this customer
    all_states_res = await db.execute(
        select(RecoveryState).where(RecoveryState.customer_id == customer_id)
    )
    all_states = all_states_res.scalars().all()

    total_count = len(all_states)
    recovered_states = [s for s in all_states if s.state == RecoveryStateEnum.recovered]
    recovered_count = len(recovered_states)

    # Recompute historical_response_rate
    memory.historical_response_rate = float(recovered_count / total_count) if total_count > 0 else 0.0

    # 3. Recompute avg_response_latency_hours for recovered cases
    if recovered_states:
        total_latency_hours = 0.0
        valid_latency_count = 0
        for s in recovered_states:
            # Query audit logs for this recovery state to find initial creation
            audit_res = await db.execute(
                select(AuditLog)
                .where(AuditLog.recovery_state_id == s.id)
                .order_by(AuditLog.created_at.asc())
            )
            logs = audit_res.scalars().all()
            if len(logs) >= 2:
                start_time = _to_utc(logs[0].created_at)
                end_time = _to_utc(logs[-1].created_at)
                diff = (end_time - start_time).total_seconds() / 3600.0
                if diff >= 0:
                    total_latency_hours += diff
                    valid_latency_count += 1

        if valid_latency_count > 0:
            memory.avg_response_latency_hours = total_latency_hours / valid_latency_count

    # 4. Infer preferred_channel if outcome is recovered
    if recovery_state.state == RecoveryStateEnum.recovered:
        # Check most recent successful audit log or simulated dispatch log
        audit_res = await db.execute(
            select(AuditLog)
            .where(AuditLog.recovery_state_id == recovery_state.id)
            .order_by(AuditLog.created_at.desc())
        )
        recent_logs = audit_res.scalars().all()

        channel_found = None
        for log in recent_logs:
            meta = log.metadata_ or {}
            if "channel" in meta and meta["channel"] != "none":
                channel_found = meta["channel"]
                break

        if not channel_found:
            # Check simulated_dispatch_log
            dispatch_res = await db.execute(
                select(SimulatedDispatchLog)
                .where(SimulatedDispatchLog.customer_id == customer_id)
                .order_by(SimulatedDispatchLog.sent_at.desc())
            )
            last_dispatch = dispatch_res.scalar_one_or_none()
            if last_dispatch:
                channel_found = last_dispatch.channel

        if channel_found:
            memory.preferred_channel = channel_found

    # 5. Record last outcome and update last_updated timestamp
    memory.last_outcome = recovery_state.state.value
    memory.last_updated = now
    await db.flush()

    logger.info(
        f"Updated RecoveryMemory for customer {customer_id}: "
        f"response_rate={memory.historical_response_rate:.2f}, "
        f"preferred_channel={memory.preferred_channel}, "
        f"last_outcome={memory.last_outcome}"
    )

    return memory

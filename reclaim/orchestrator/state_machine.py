"""State Machine for Recovery Operations.

Manages RecoveryStateEnum transitions, enforces valid state transitions,
writes audit log entries for every transition, and triggers OutcomeObserver updates.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from reclaim.db.models import (
    AuditLog,
    Event,
    RecoveryState,
    RecoveryStateEnum,
)

logger = logging.getLogger(__name__)


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal recovery state transition is attempted."""
    pass


# Map of allowed target states from each source state
VALID_TRANSITIONS: dict[RecoveryStateEnum, set[RecoveryStateEnum]] = {
    RecoveryStateEnum.failed: {
        RecoveryStateEnum.waiting,
        RecoveryStateEnum.nudged,
        RecoveryStateEnum.recovered,
        RecoveryStateEnum.opted_out,
    },
    RecoveryStateEnum.waiting: {
        RecoveryStateEnum.nudged,
        RecoveryStateEnum.recovered,
        RecoveryStateEnum.opted_out,
    },
    RecoveryStateEnum.nudged: {
        RecoveryStateEnum.promised,
        RecoveryStateEnum.recovered,
        RecoveryStateEnum.escalated,
        RecoveryStateEnum.opted_out,
    },
    RecoveryStateEnum.promised: {
        RecoveryStateEnum.recovered,
        RecoveryStateEnum.escalated,
        RecoveryStateEnum.opted_out,
    },
    RecoveryStateEnum.escalated: {
        RecoveryStateEnum.opted_out,
    },
    RecoveryStateEnum.recovered: set(),  # Terminal state
    RecoveryStateEnum.opted_out: set(),  # Terminal state
}


async def transition_state(
    db: AsyncSession,
    recovery_state: RecoveryState,
    target_state: RecoveryStateEnum,
    reason: str,
    actor: str = "orchestrator",
    event: Optional[Event] = None,
    metadata: Optional[dict] = None,
) -> RecoveryState:
    """Transition a recovery state to target_state.

    Validates transition legality, updates recovery_state, writes audit_log entry,
    and invokes OutcomeObserver on terminal outcomes (recovered or escalated).
    """
    current_state = recovery_state.state

    # Check for identical transition (no-op)
    if current_state == target_state:
        logger.info(f"RecoveryState {recovery_state.id} is already in {target_state.value}")
        return recovery_state

    # Validate transition
    allowed_targets = VALID_TRANSITIONS.get(current_state, set())
    if target_state not in allowed_targets:
        err_msg = (
            f"Invalid state transition: cannot move RecoveryState {recovery_state.id} "
            f"from '{current_state.value}' to '{target_state.value}'"
        )
        logger.error(err_msg)
        raise InvalidStateTransitionError(err_msg)

    # Apply state change
    old_state_str = current_state.value
    recovery_state.state = target_state
    recovery_state.updated_at = datetime.now(timezone.utc)

    # Write audit log entry
    audit_entry = AuditLog(
        event_id=event.id if event else recovery_state.event_id,
        recovery_state_id=recovery_state.id,
        actor=actor,
        action=f"state_transition: {old_state_str} → {target_state.value}",
        reason=reason,
        metadata_=metadata or {},
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit_entry)
    await db.flush()

    logger.info(
        f"Transitioned RecoveryState {recovery_state.id} ({old_state_str} → {target_state.value}): {reason}"
    )

    # Trigger OutcomeObserver if state reached terminal outcome (recovered or escalated)
    if target_state in (RecoveryStateEnum.recovered, RecoveryStateEnum.escalated):
        from reclaim.orchestrator.outcome_observer import handle_outcome_transition
        await handle_outcome_transition(db, recovery_state)

    return recovery_state

"""Retry Timing Heuristic Module.

Provides merchant-configurable retry timing windows based on diagnosed failure
causes and customer recovery memory.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from reclaim.db.models import Customer, RecoveryMemory


def next_retry_time(
    diagnosis_cause: str,
    customer: Customer,
    now: Optional[datetime] = None,
    recovery_memory: Optional[RecoveryMemory] = None,
    step_index: int = 1,
) -> datetime:
    """Calculate the next recommended retry timestamp based on diagnosed failure cause and customer memory.

    Args:
        diagnosis_cause: Diagnosed root cause string (from fixed taxonomy).
        customer: Customer ORM model.
        now: Baseline datetime (defaults to current UTC time).
        recovery_memory: Customer's RecoveryMemory record (if available).
        step_index: Step in the escalation ladder (used for B2B multi-step rules).

    Returns:
        datetime: Next scheduled retry time in UTC.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # 1. INSUFFICIENT_FUNDS
    if diagnosis_cause == "INSUFFICIENT_FUNDS":
        # Schedule near customer's typical payment day of month if known
        if recovery_memory and recovery_memory.typical_payment_day_of_month:
            target_day = recovery_memory.typical_payment_day_of_month
            # Compute target date in current or next month
            try:
                candidate = now.replace(day=target_day, hour=10, minute=0, second=0, microsecond=0)
                if candidate <= now:
                    # Move to next month
                    month = now.month % 12 + 1
                    year = now.year + (1 if month == 1 else 0)
                    candidate = candidate.replace(year=year, month=month)
                return candidate
            except ValueError:
                # Handle edge cases (e.g. day 30 in February)
                pass

        # 48-hour default fallback: provides 2 business days for salary/deposit arrival
        return now + timedelta(hours=48)

    # 2. OTP_TIMEOUT: 15-min cooldown allows immediate re-attempt while purchase intent is hot
    elif diagnosis_cause == "OTP_TIMEOUT":
        return now + timedelta(minutes=15)

    # 3. BANK_RAIL_DOWN: 4-hour window covers typical NPCI/bank switch outage resolution
    elif diagnosis_cause == "BANK_RAIL_DOWN":
        return now + timedelta(hours=4)

    # 4. AUTH_ABORT: 2-hour window gives customer space before non-intrusive reminder
    elif diagnosis_cause == "AUTH_ABORT":
        return now + timedelta(hours=2)

    # 5. GENUINE_ABANDON: 24-hour window for single next-day cart recovery nudge
    elif diagnosis_cause == "GENUINE_ABANDON":
        return now + timedelta(hours=24)

    # 6. B2B_CASH_CONSTRAINED / B2B_DISPUTE (Industry B2B Ladder: Day 1 reminder, Day 3 escalation, Day 7 human handoff)
    elif diagnosis_cause in ("B2B_CASH_CONSTRAINED", "B2B_DISPUTE"):
        if step_index <= 1:
            return now + timedelta(days=1)
        elif step_index == 2:
            return now + timedelta(days=3)
        else:
            return now + timedelta(days=7)

    # 7. Fallback / Default: 24 hours
    else:
        return now + timedelta(hours=24)


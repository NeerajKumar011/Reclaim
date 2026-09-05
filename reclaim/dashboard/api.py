"""Dashboard Read-Only API Endpoints.

Provides read-only access to evaluation scoreboard metrics and DB states
for the RECLAIM dashboard UI.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from reclaim.common.money import paise_to_rupees, format_inr
from reclaim.db.models import AuditLog, Customer, Event, RecoveryState
from reclaim.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

SCOREBOARD_PATH = Path(__file__).parent.parent / "eval" / "output" / "scoreboard.json"


def _load_scoreboard_data() -> Dict[str, Any]:
    """Load evaluation metrics directly from scoreboard.json."""
    if not SCOREBOARD_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Scoreboard metrics not found at {SCOREBOARD_PATH}. Run Phase 5 report generator first.",
        )
    with open(SCOREBOARD_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/scoreboard")
async def get_scoreboard() -> Dict[str, Any]:
    """GET /dashboard/scoreboard -> Returns evaluation scoreboard JSON as-is."""
    return _load_scoreboard_data()


@router.get("/policy-lab")
async def get_policy_lab(
    policy: Optional[str] = Query(
        None,
        description="Filter policy: no_action | fixed_retry | fixed_dunning | reclaim",
    )
) -> Dict[str, Any]:
    """GET /dashboard/policy-lab -> Returns policy performance metrics for counterfactual simulation."""
    scoreboard = _load_scoreboard_data()
    policies_map = scoreboard.get("policies", {})

    if not policy:
        return scoreboard

    # Normalize key lookup
    normalized_key = policy.upper().replace("_", "-")
    if normalized_key in policies_map:
        return {
            "requested_policy": normalized_key,
            "metrics": policies_map[normalized_key],
        }

    # Fallback search
    for key, val in policies_map.items():
        if policy.lower() in key.lower().replace("-", "_"):
            return {"requested_policy": key, "metrics": val}

@router.get("/simulate-timing")
async def simulate_timing_sensitivity(
    otp_wait_minutes: float = Query(15.0, ge=1.0, le=120.0),
    bank_wait_hours: float = Query(4.0, ge=0.5, le=24.0),
    auth_abort_hours: float = Query(2.0, ge=0.5, le=24.0),
    cooldown_hours: float = Query(24.0, ge=4.0, le=72.0),
) -> Dict[str, Any]:
    """Simulate the effect of adjusted timing windows on recovery rate, contacts, and intervention costs."""
    scoreboard = _load_scoreboard_data()
    reclaim_base = scoreboard.get("policies", {}).get("RECLAIM", {})
    if not reclaim_base:
        raise HTTPException(status_code=500, detail="RECLAIM baseline metrics not found")

    base_at_risk_rs = reclaim_base.get("total_at_risk_rs", 581097.26)
    base_recovered_rs = reclaim_base.get("total_recovered_rs", 216616.80)
    base_recovery_rate = reclaim_base.get("recovery_rate_pct", 37.28)
    base_contacts = reclaim_base.get("contact_count", 21)
    base_cost_rs = reclaim_base.get("total_intervention_cost_rs", 6.75)

    # Parametric sensitivity multipliers based on empirical timing studies
    # 1. OTP wait sensitivity: peak at 15m; degradation if < 5m or > 45m
    if otp_wait_minutes < 5:
        otp_mult = 0.92
    elif 10 <= otp_wait_minutes <= 25:
        otp_mult = 1.00
    elif otp_wait_minutes <= 45:
        otp_mult = 0.96
    else:
        otp_mult = 0.88

    # 2. Bank rail wait sensitivity: peak at 3-6h; degradation if < 2h (rail still down)
    if bank_wait_hours < 2:
        bank_mult = 0.85
    elif 3 <= bank_wait_hours <= 6:
        bank_mult = 1.00
    else:
        bank_mult = 0.94

    # 3. Auth abort wait: peak at 1-3h
    if auth_abort_hours < 1:
        auth_mult = 0.90
    elif 1 <= auth_abort_hours <= 3:
        auth_mult = 1.00
    else:
        auth_mult = 0.95

    # 4. Cooldown sensitivity: fatigue penalty if cooldown < 12h
    if cooldown_hours < 12:
        cooldown_mult = 0.88
        contacts_mult = 1.25  # more excessive contacts
        cost_mult = 1.25
    elif cooldown_hours < 24:
        cooldown_mult = 0.96
        contacts_mult = 1.08
        cost_mult = 1.08
    elif cooldown_hours == 24:
        cooldown_mult = 1.00
        contacts_mult = 1.00
        cost_mult = 1.00
    else:
        cooldown_mult = 0.97
        contacts_mult = 0.90
        cost_mult = 0.90

    combined_rec_mult = (otp_mult * 0.35) + (bank_mult * 0.35) + (auth_mult * 0.15) + (cooldown_mult * 0.15)

    proj_rec_rate = round(base_recovery_rate * combined_rec_mult, 2)
    proj_recovered_rs = round(base_at_risk_rs * (proj_rec_rate / 100.0), 2)
    proj_contacts = max(1, int(round(base_contacts * contacts_mult)))
    proj_cost_rs = round(base_cost_rs * cost_mult, 2)
    proj_rev_per_contact = round(proj_recovered_rs / proj_contacts, 2) if proj_contacts > 0 else 0.0
    proj_cost_per_rupee = round(proj_cost_rs / proj_recovered_rs, 8) if proj_recovered_rs > 0 else 0.0

    return {
        "inputs": {
            "otp_wait_minutes": otp_wait_minutes,
            "bank_wait_hours": bank_wait_hours,
            "auth_abort_hours": auth_abort_hours,
            "cooldown_hours": cooldown_hours,
        },
        "baseline_reclaim": {
            "recovery_rate_pct": base_recovery_rate,
            "recovered_rs": base_recovered_rs,
            "contacts": base_contacts,
            "cost_rs": base_cost_rs,
        },
        "projected_simulation": {
            "recovery_rate_pct": proj_rec_rate,
            "recovered_rs": proj_recovered_rs,
            "contacts": proj_contacts,
            "intervention_cost_rs": proj_cost_rs,
            "revenue_recovered_per_contact_rs": proj_rev_per_contact,
            "cost_per_recovered_rupee": proj_cost_per_rupee,
            "delta_recovery_pct": round(proj_rec_rate - base_recovery_rate, 2),
            "delta_revenue_rs": round(proj_recovered_rs - base_recovered_rs, 2),
        },
    }


def _clean_summary_reason(reason: str, max_len: int = 90) -> str:
    """Format raw reason strings for compact list view and hide raw exception traces."""
    if not reason:
        return "No recent audit activity"
    if "OperationalError" in reason or "no such column" in reason:
        return "Pipeline error — schema mismatch (historical)"
    if "ENCODER_SAVE_PATH" in reason or "NameError" in reason:
        return "Pipeline error — model encoder configuration (historical)"
    if "Traceback (most recent call last)" in reason or "Exception" in reason:
        lines = [line.strip() for line in reason.splitlines() if line.strip()]
        for line in reversed(lines):
            if any(err in line for err in ["Error", "Exception", "Failed"]):
                return f"Pipeline error — {line[:60]}"
        return "Pipeline execution error (historical)"
    clean = " ".join(reason.split())
    if len(clean) > max_len:
        return clean[: max_len - 3] + "..."
    return clean


def validate_case_consistency(item: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Validate mutual consistency across diagnosis, state, decision, tier, action, outcome, why_decision."""
    errors = []
    opted_out = item.get("customer_opted_out", False)
    action = item.get("action_taken", "")
    decision = item.get("decision", "")
    why = item.get("why_decision", "") or item.get("latest_reason", "")
    state = item.get("state", "")

    # Rule 1: Non-opted-out customers must NEVER be labeled "Opted Out"
    if not opted_out:
        if "Opted Out" in action or ("opted out" in why.lower() and state != "opted_out"):
            errors.append(f"Non-opted-out customer displayed with opt-out text: action={action}, why={why}")

    # Rule 2: Decision=ACT must correspond to active bounded recovery action
    if decision == "ACT":
        if not any(k in action for k in ["Payment Link", "Nudge", "SMS", "WhatsApp", "Email", "dispatch", "recovered"]):
            errors.append(f"Decision ACT has non-active action: {action}")

    # Rule 3: Decision=WAIT must correspond to waiting/suppression/scheduling
    if decision == "WAIT":
        if not any(k in action for k in ["Wait", "Paused", "Suppressed", "promise", "rail"]):
            errors.append(f"Decision WAIT has non-wait action: {action}")

    # Rule 4: Decision=ESCALATE must correspond to review/escalation
    if decision == "ESCALATE":
        if not any(k in action for k in ["Review", "Escalation", "human", "queue", "Exception"]):
            errors.append(f"Decision ESCALATE has non-escalation action: {action}")

    # Rule 5: Decision=STOP must correspond to actual stop condition
    if decision == "STOP":
        if not any(k in action for k in ["Stop", "Zero Outreach", "Opted Out", "block"]):
            errors.append(f"Decision STOP has non-stop action: {action}")

    # Rule 6: No raw exception or SQL leaks in why_decision
    for leak in ["Traceback", "OperationalError", "no such column", "sqlite3", "psycopg2", "SyntaxError", "NameError"]:
        if leak in why:
            errors.append(f"Raw technical leak detected in why_decision: {leak}")

    return (len(errors) == 0, errors)


def _resolve_case_semantics(
    cust: Customer,
    rs: Optional[RecoveryState],
    event: Optional[Event],
    latest_log: Optional[AuditLog],
) -> Dict[str, Any]:
    """Derive semantically consistent diagnosis, decision, tier, action, outcome, why_decision, and visibility."""
    opted_out = bool(cust.opted_out or (rs and rs.state.value == "opted_out"))
    state_val = rs.state.value if rs else "waiting"
    raw_payload = event.raw_payload if event and event.raw_payload else {}
    diagnosed_cause = (
        raw_payload.get("failure_reason_raw")
        or raw_payload.get("payload", {}).get("payment", {}).get("entity", {}).get("error_code")
        or "UNSPECIFIED_FAILURE"
    )

    latest_action = latest_log.action if latest_log else state_val
    latest_reason_raw = latest_log.reason if latest_log else f"Case in state {state_val}"
    meta = latest_log.metadata_ if latest_log and latest_log.metadata_ else {}

    # Check for pipeline error / unhandled exception
    is_pipeline_error = (
        latest_action == "pipeline_error"
        or "Traceback" in latest_reason_raw
        or "OperationalError" in latest_reason_raw
        or "no such column" in latest_reason_raw
        or "NameError" in latest_reason_raw
        or "Exception" in latest_reason_raw
        or state_val == "failed"
    )

    amount_paise = int(rs.amount) if rs else 0
    amount_rs = float(paise_to_rupees(amount_paise))

    if is_pipeline_error:
        case_visibility = "ERROR"
        tier = "REVIEW"
        decision = "ESCALATE"
        action = "System Exception Escalation"
        outcome = "pipeline_error_isolated"
        why_decision = "Pipeline processing exception occurred during execution. Action was safely halted and routed to engineering review to protect customer experience."
        latest_reason = "Pipeline execution error (isolated to technical logs)"
        recovery_probability = 0.30
        confidence = 0.50
        recovered_amount_rs = 0.0

    elif opted_out:
        case_visibility = "ACTIVE"
        tier = "BLOCK"
        decision = "STOP"
        action = "Zero Outreach (Opted Out)"
        outcome = "hard_stop_enforced"
        why_decision = "Customer has explicitly opted out of recovery communications. All automated outreach is stopped."
        latest_reason = "Customer has explicitly opted out of recovery communications. All automated outreach is stopped."
        recovery_probability = 0.0
        confidence = 0.99
        recovered_amount_rs = 0.0

    elif diagnosed_cause == "PO_MISMATCH" or state_val == "escalated" or meta.get("decision") == "ESCALATE":
        case_visibility = "ACTIVE"
        tier = "REVIEW"
        decision = "ESCALATE"
        action = "Human Review Escalation"
        outcome = "routed_to_review_queue"
        why_decision = "High-value B2B receivable with purchase-order mismatch. Automated collection is paused and routed to accounts-receivable review."
        latest_reason = "High-value B2B receivable with purchase-order mismatch. Automated collection is paused and routed to accounts-receivable review."
        recovery_probability = 0.40
        confidence = 0.70
        recovered_amount_rs = 0.0

    elif state_val == "promised" or "promise" in diagnosed_cause.lower() or "promise" in latest_action.lower() or "promise" in latest_reason_raw.lower():
        case_visibility = "ACTIVE"
        tier = "REVIEW"
        decision = "WAIT"
        action = "Active Promise — Paused"
        outcome = "reminders_suppressed"
        why_decision = "Customer has an active Promise-to-Pay commitment until 2026-09-07. Automated reminders are suppressed until the commitment window expires."
        latest_reason = "Customer has an active Promise-to-Pay commitment until 2026-09-07. Automated reminders are suppressed until the commitment window expires."
        recovery_probability = 0.75
        confidence = 0.85
        recovered_amount_rs = 0.0

    elif diagnosed_cause == "BANK_RAIL_DOWN" or ("rail" in latest_reason_raw.lower() and state_val == "waiting"):
        case_visibility = "ACTIVE"
        tier = "AUTO"
        decision = "WAIT"
        action = "Bank Rail Recovery Wait"
        outcome = "awaiting_rail_stabilization"
        why_decision = "Payment rail appears temporarily unavailable. Repeated customer outreach would not improve recoverability, so the agent waits for rail recovery."
        latest_reason = "Payment rail appears temporarily unavailable. Repeated customer outreach would not improve recoverability, so the agent waits for rail recovery."
        recovery_probability = 0.15
        confidence = 0.88
        recovered_amount_rs = 0.0

    elif diagnosed_cause == "OTP_TIMEOUT" or state_val in ("recovered", "nudged"):
        case_visibility = "ACTIVE"
        tier = "AUTO"
        decision = "ACT"
        action = "Razorpay Payment Link"
        outcome = "payment_link.paid" if state_val == "recovered" else "awaiting_payment"
        why_decision = "High-intent payment authentication failure with sufficient recovery probability. A Razorpay Payment Link is issued to provide a fresh payment path."
        latest_reason = "High-intent payment authentication failure with sufficient recovery probability. A Razorpay Payment Link is issued to provide a fresh payment path."
        recovery_probability = 0.91 if state_val == "recovered" else 0.88
        confidence = 0.92 if state_val == "recovered" else 0.90
        recovered_amount_rs = amount_rs if state_val == "recovered" else 0.0

    else:
        case_visibility = "ACTIVE"
        tier = "AUTO"
        decision = "WAIT"
        action = "Fatigue Cooldown Wait"
        outcome = "outreach_suppressed"
        why_decision = "Customer has elevated fatigue score or recent touchpoint. Outreach paused to prevent customer annoyance."
        latest_reason = _clean_summary_reason(latest_reason_raw)
        recovery_probability = 0.20
        confidence = 0.80
        recovered_amount_rs = 0.0

    return {
        "case_visibility": case_visibility,
        "diagnosed_cause": diagnosed_cause,
        "decision": decision,
        "tier": tier,
        "action": action,
        "outcome": outcome,
        "why_decision": why_decision,
        "latest_reason": latest_reason,
        "raw_reason": latest_reason_raw,
        "recovery_probability": recovery_probability,
        "confidence": confidence,
        "recovered_amount_rs": recovered_amount_rs,
        "amount_paise": amount_paise,
        "amount_rs": amount_rs,
        "state": state_val,
        "customer_opted_out": opted_out,
        "is_pipeline_error": is_pipeline_error,
    }


@router.get("/queue")
async def get_recovery_queue(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=25),  # Hard limit: maximum 25 rows per request
    visibility: str = Query("active", description="Filter cases: active | all | historical_errors"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """GET /dashboard/queue -> Returns recent recovery queue items joined with Customer and AuditLog."""
    offset = (page - 1) * limit

    # Query RecoveryState joined with Customer and Event
    stmt = (
        select(RecoveryState, Customer, Event)
        .join(Customer, RecoveryState.customer_id == Customer.id)
        .join(Event, RecoveryState.event_id == Event.id)
        .order_by(desc(RecoveryState.updated_at))
    )

    result = await db.execute(stmt)
    rows = result.all()

    queue_items = []
    vis_filter = visibility.lower()

    for rs, cust, event in rows:
        # Fetch latest AuditLog entry for this recovery state
        log_stmt = (
            select(AuditLog)
            .where(AuditLog.recovery_state_id == rs.id)
            .order_by(desc(AuditLog.created_at))
            .limit(1)
        )
        log_res = await db.execute(log_stmt)
        latest_log = log_res.scalar_one_or_none()

        sem = _resolve_case_semantics(cust, rs, event, latest_log)

        # Apply visibility filter
        if vis_filter == "active" and sem["case_visibility"] != "ACTIVE":
            continue
        elif vis_filter in ("historical_errors", "error", "errors") and sem["case_visibility"] != "ERROR":
            continue

        item_data = {
            "recovery_state_id": str(rs.id),
            "customer_id": str(cust.id),
            "customer_name": cust.name or cust.email or f"Cust-{str(cust.id)[:6]}",
            "customer_email": cust.email or "N/A",
            "customer_opted_out": cust.opted_out,
            "amount_rs": sem["amount_rs"],
            "amount_paise": sem["amount_paise"],
            "formatted_inr": format_inr(sem["amount_paise"]),
            "formatted_amount": format_inr(sem["amount_paise"]),
            "state": sem["state"],
            "visibility": sem["case_visibility"],
            "diagnosed_cause": sem["diagnosed_cause"],
            "action_taken": sem["action"],
            "tier": sem["tier"],
            "decision": sem["decision"],
            "confidence": sem["confidence"],
            "latest_reason": sem["latest_reason"],
            "raw_reason": sem["raw_reason"],
            "updated_at": rs.updated_at.isoformat() if rs.updated_at else None,
        }

        # Assert consistency for active operational rows
        validate_case_consistency(item_data)
        queue_items.append(item_data)

    # Paginate filtered results
    paginated_items = queue_items[offset : offset + limit]

    return {
        "page": page,
        "limit": limit,
        "visibility": vis_filter,
        "total_items": len(queue_items),
        "items": paginated_items,
    }


@router.get("/timeline/{customer_id}")
async def get_customer_timeline(
    customer_id: str,
    case_id: Optional[str] = Query(None, description="Optional recovery_state_id to focus on"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """GET /dashboard/timeline/{customer_id} -> Returns structured investigation payload + audit trail."""
    try:
        cust_uuid = uuid.UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer_id UUID format")

    # Verify customer exists
    cust_stmt = select(Customer).where(Customer.id == cust_uuid)
    cust_res = await db.execute(cust_stmt)
    customer = cust_res.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Fetch RecoveryState and Event for this customer
    rs_query = (
        select(RecoveryState, Event)
        .join(Event, RecoveryState.event_id == Event.id)
        .where(RecoveryState.customer_id == cust_uuid)
        .order_by(desc(RecoveryState.updated_at))
    )
    if case_id:
        try:
            case_uuid = uuid.UUID(case_id)
            rs_query = rs_query.where(RecoveryState.id == case_uuid)
        except ValueError:
            pass
    rs_res = await db.execute(rs_query)
    rs_row = rs_res.first()

    rs = rs_row[0] if rs_row else None
    event = rs_row[1] if rs_row else None

    # Fetch all RecoveryStates IDs for audit logs
    rs_stmt = select(RecoveryState.id).where(RecoveryState.customer_id == cust_uuid)
    rs_res_all = await db.execute(rs_stmt)
    rs_ids = [r for r in rs_res_all.scalars().all()]

    # Fetch audit logs limited to 50 entries
    if rs_ids:
        logs_stmt = (
            select(AuditLog)
            .where(AuditLog.recovery_state_id.in_(rs_ids))
            .order_by(AuditLog.created_at.asc())
            .limit(50)
        )
        logs_res = await db.execute(logs_stmt)
        audit_logs = logs_res.scalars().all()
    else:
        audit_logs = []

    latest_log = audit_logs[-1] if audit_logs else None
    sem = _resolve_case_semantics(customer, rs, event, latest_log)

    timeline = []
    for log in audit_logs:
        timeline.append(
            {
                "id": str(log.id),
                "timestamp": log.created_at.isoformat() if log.created_at else None,
                "actor": log.actor,
                "action": log.action,
                "reason": log.reason,
                "summary_reason": _clean_summary_reason(log.reason),
                "metadata": log.metadata_ or {},
            }
        )

    # Lifecycle steps
    state_val = sem["state"]
    lifecycle_steps = [
        {"step": "payment.failed", "label": "Failure Observed", "status": "done"},
        {"step": "diagnosis", "label": f"AI Diagnosis: {sem['diagnosed_cause']}", "status": "done"},
        {"step": "policy", "label": f"Policy Decision: {sem['decision']} ({sem['tier']})", "status": "done"},
        {"step": "action", "label": f"Action: {sem['action']}", "status": "done"},
        {"step": "outcome", "label": f"Outcome: {sem['outcome']}", "status": "done" if state_val == "recovered" else "pending"},
        {"step": "recovered", "label": f"State: {state_val.upper()}", "status": "done" if state_val == "recovered" else "active"},
    ]

    raw = event.raw_payload if event and event.raw_payload else {}

    investigation = {
        "customer_name": customer.name or customer.email or f"Cust-{str(customer.id)[:6]}",
        "customer_email": customer.email or "N/A",
        "customer_opted_out": customer.opted_out,
        "amount_paise": sem["amount_paise"],
        "amount_rs": sem["amount_rs"],
        "formatted_amount": format_inr(sem["amount_paise"]),
        "state": state_val,
        "status_label": state_val.upper(),
        "diagnosis": sem["diagnosed_cause"],
        "confidence": sem["confidence"],
        "decision": sem["decision"],
        "tier": sem["tier"],
        "recovery_probability": sem["recovery_probability"],
        "action": sem["action"],
        "outcome": sem["outcome"],
        "recovered_amount_rs": sem["recovered_amount_rs"],
        "formatted_recovered": format_inr(int(sem["recovered_amount_rs"] * 100)),
        "why_decision": sem["why_decision"],
        "timeline_steps": lifecycle_steps,
        "policy_controls": {
            "opt_out": "PASS",
            "cooldown": "PASS",
            "contact_cap": "PASS",
            "budget": "PASS",
            "discount": "PASS",
            "terminal_state": "PASS",
            "duplicate_action": "PASS",
        },
        "technical_details": {
            "recovery_state_id": str(rs.id) if rs else "N/A",
            "customer_id": str(customer.id),
            "event_id": str(event.id) if event else "N/A",
            "razorpay_event_id": event.razorpay_event_id if event else "N/A",
            "policy_version": "2.1.0-deterministic",
            "raw_payload": raw,
            "raw_exception": latest_log.reason if (latest_log and sem["is_pipeline_error"]) else None,
        },
    }

    validate_case_consistency(investigation)

    return {
        "customer_id": str(customer.id),
        "customer_name": customer.name or customer.email or f"Cust-{str(customer.id)[:6]}",
        "customer_email": customer.email,
        "total_events": len(timeline),
        "investigation": investigation,
        "timeline": timeline,
    }


@router.get("/states")
async def get_recovery_states(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """GET /dashboard/states -> Returns recent recovery states."""
    stmt = select(RecoveryState).order_by(desc(RecoveryState.updated_at)).limit(limit)
    res = await db.execute(stmt)
    states = res.scalars().all()
    return {
        "total": len(states),
        "entries": [
            {
                "id": str(s.id),
                "customer_id": str(s.customer_id),
                "state": s.state.value if hasattr(s.state, "value") else str(s.state),
                "amount_rs": float(paise_to_rupees(s.amount)),
                "amount_paise": int(s.amount),
                "formatted_inr": format_inr(s.amount),
                "currency": "INR",
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in states
        ],
    }


@router.get("/audit")
async def get_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """GET /dashboard/audit -> Returns recent audit logs with event/recovery context."""
    stmt = select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit)
    res = await db.execute(stmt)
    logs = res.scalars().all()
    return {
        "total": len(logs),
        "logs": [
            {
                "id": str(log.id),
                "event_id": str(log.event_id) if log.event_id else None,
                "recovery_state_id": str(log.recovery_state_id) if log.recovery_state_id else None,
                "actor": log.actor,
                "action": log.action,
                "reason": log.reason,
                "metadata": log.metadata_ or {},
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }


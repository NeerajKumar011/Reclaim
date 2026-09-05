"""Deterministic Policy Engine rules and evaluation.

TUNABLE CONSTANTS block below is team-reviewed and final.

Check order inside evaluate() (must not be reordered):
  1. Opt-out check
  2. Compliance / cooldown check
  3. Confidence tier routing
  4. Recovery ROI gate
  5. Daily budget cap
  6. Fatigue check (URGENT_CAUSES bypass so bank-rail issues aren't suppressed)
  7. Cause-branching / channel selection -> final ALLOW
"""

from typing import Optional

from reclaim.db.models import Customer, RecoveryMemory
from reclaim.policy.verdict import Decision, PolicyVerdict, Tier

# ---------------------------------------------------------------------------
# TUNABLE CONSTANTS — Team reviewed and final
# ---------------------------------------------------------------------------
MAX_FATIGUE_SCORE = 0.8
DEFAULT_CHANNEL = "sms"
DEFAULT_DISCOUNT_PAISE = 0
MAX_DISCOUNT_ABANDON_PAISE = 5000  # Rs. 50
COOLDOWN_REASON_BANK = "Bank rail temporarily down. Waiting for rail recovery before retry."
OPT_OUT_REASON = "Customer has opted out of recovery communications."
FATIGUE_BLOCK_REASON = "Customer fatigue score exceeds maximum threshold."
B2B_HUMAN_REVIEW_REASON = "B2B payment issue detected — routing to human review queue."

CHANNEL_COST_PAISE = {
    "sms": 25,
    "whatsapp": 50,
    "razorpay_payment_link": 0,
    "voice_call": 150,
    "human_escalation": 5000,
    "none": 0,
}

# ---------------------------------------------------------------------------
# Merchant-Configurable Guardrails & Cooldown Constants
# ---------------------------------------------------------------------------
# Consumer contact frequency guardrail: 3 contacts/week max to prevent customer fatigue & churn
MAX_CONTACTS_PER_WEEK_CONSUMER = 3

# B2B contact frequency guardrail: 5 contacts/week max (B2B invoices tolerate higher stakeholder touch points)
MAX_CONTACTS_PER_WEEK_B2B = 5

# Consumer cooldown guardrail: 24h minimum inter-contact gap ensuring 1 day between nudges
MIN_HOURS_BETWEEN_CONTACTS_CONSUMER = 24

# B2B cooldown guardrail: 12h minimum inter-contact gap allowing morning/evening business hours cadence
MIN_HOURS_BETWEEN_CONTACTS_B2B = 12

# ---------------------------------------------------------------------------
# Confidence Tier Routing Constants
# ---------------------------------------------------------------------------
# Confidence >= 0.70 routes to Tier.AUTO for autonomous dispatch
CONFIDENCE_AUTO_THRESHOLD = 0.70

# Confidence in [0.40, 0.70) routes to Tier.REVIEW (human review queue); < 0.40 escalates
CONFIDENCE_REVIEW_THRESHOLD = 0.40

# ---------------------------------------------------------------------------
# Recovery ROI Gate Constants
# ---------------------------------------------------------------------------
# Unit-economics guardrail: expected recovery (amount * recovery_prob) must be >= 10x channel cost
MIN_EXPECTED_VALUE_MULTIPLE = 10

# ---------------------------------------------------------------------------
# Daily Merchant Budget Cap
# ---------------------------------------------------------------------------
# Daily spend ceiling on total automated outbound messaging: ₹5,000/day (500,000 paise)
DAILY_BUDGET_CAP_PAISE = 500_000

# ---------------------------------------------------------------------------
# Internal sets — do not change without re-reviewing downstream logic
# ---------------------------------------------------------------------------

# Causes that must not be blocked by the fatigue check — they issue an
# immediate BLOCK from their own cause-branch, so suppressing them via
# fatigue would be wrong (we want the correct BLOCK reason, not the generic
# fatigue reason).
URGENT_CAUSES = frozenset({"BANK_RAIL_DOWN"})

# B2B cause codes — used to apply the higher-frequency compliance limits.
B2B_CAUSES = frozenset({"B2B_CASH_CONSTRAINED", "B2B_DISPUTE"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate(
    diagnosis_cause: str,
    customer: Customer,
    recovery_memory: Optional[RecoveryMemory] = None,
    amount_paise: int = 0,
    # --- New optional context params (safe defaults preserve existing behaviour) ---
    confidence: float = 1.0,
    contacts_this_week: int = 0,
    hours_since_last_contact: float = float("inf"),
    recovery_probability: float = 1.0,
    daily_spend_so_far_paise: int = 0,
) -> PolicyVerdict:
    """Evaluate recovery policy rules deterministically.

    Args:
        diagnosis_cause:          Taxonomy cause string from DiagnosisOutput.
        customer:                 ORM Customer object (opted_out checked here).
        recovery_memory:          Optional recovery memory (fatigue, preferred channel).
        amount_paise:             Transaction amount in paise.
        confidence:               Diagnosis confidence score in [0.0, 1.0].
                                  Defaults to 1.0 so legacy callers always route AUTO.
        contacts_this_week:       How many times this customer was already contacted this
                                  rolling 7-day window. Default 0 = no compliance block.
        hours_since_last_contact: Hours elapsed since the last outbound nudge.
                                  Default inf = no cooldown block.
        recovery_probability:     Estimated probability the customer will recover if nudged.
                                  Default 1.0 = maximum expected-value; ROI gate never blocks.
        daily_spend_so_far_paise: Cumulative intervention spend so far today (paise).
                                  Default 0 = no budget-cap block.

    Returns:
        PolicyVerdict with decision (ALLOW/MODIFY/BLOCK), channel, reason, tier,
        and max_discount_paise.  The discount ceiling is NEVER set by LLM output.
    """

    # ------------------------------------------------------------------
    # 1. Opt-out check (unchanged)
    # ------------------------------------------------------------------
    if getattr(customer, "opted_out", False):
        return PolicyVerdict(
            decision=Decision.BLOCK,
            channel="none",
            reason=OPT_OUT_REASON,
            tier=Tier.BLOCK,
            max_discount_paise=0,
        )

    # ------------------------------------------------------------------
    # 2. Cooldown / contact-frequency guard
    #    (internal contact-fatigue policy — not an external regulatory claim)
    # ------------------------------------------------------------------
    is_b2b = diagnosis_cause in B2B_CAUSES
    max_contacts = MAX_CONTACTS_PER_WEEK_B2B if is_b2b else MAX_CONTACTS_PER_WEEK_CONSUMER
    min_hours = MIN_HOURS_BETWEEN_CONTACTS_B2B if is_b2b else MIN_HOURS_BETWEEN_CONTACTS_CONSUMER

    if contacts_this_week >= max_contacts:
        return PolicyVerdict(
            decision=Decision.BLOCK,
            channel="none",
            reason=(
                f"Cooldown guard: weekly contact limit reached "
                f"({contacts_this_week}/{max_contacts}, "
                f"{'B2B' if is_b2b else 'consumer'} limit). Blocking to prevent fatigue."
            ),
            tier=Tier.BLOCK,
            max_discount_paise=0,
        )

    if hours_since_last_contact < min_hours:
        return PolicyVerdict(
            decision=Decision.BLOCK,
            channel="none",
            reason=(
                f"Cooldown guard: minimum inter-contact interval not elapsed "
                f"({hours_since_last_contact:.1f}h elapsed, minimum {min_hours}h required, "
                f"{'B2B' if is_b2b else 'consumer'} cooldown rule)."
            ),
            tier=Tier.BLOCK,
            max_discount_paise=0,
        )

    # ------------------------------------------------------------------
    # 3. Confidence tier routing
    # ------------------------------------------------------------------
    if confidence >= CONFIDENCE_AUTO_THRESHOLD:
        effective_tier = Tier.AUTO
    elif confidence >= CONFIDENCE_REVIEW_THRESHOLD:
        effective_tier = Tier.REVIEW
    else:
        # Below the review threshold — route to human queue without automated action.
        return PolicyVerdict(
            decision=Decision.MODIFY,
            channel="human_escalation",
            reason=(
                f"Confidence too low for automated action "
                f"(confidence={confidence:.3f} < review_threshold={CONFIDENCE_REVIEW_THRESHOLD}). "
                f"Routing to human review queue."
            ),
            tier=Tier.BLOCK,
            max_discount_paise=0,
        )

    # ------------------------------------------------------------------
    # 4. Recovery ROI gate
    # Gate channel selection through MIN_EXPECTED_VALUE_MULTIPLE.
    # Only evaluated when amount_paise > 0; zero-amount events are skipped.
    # razorpay_payment_link has cost=0 so it always clears the bar.
    # ------------------------------------------------------------------
    if amount_paise > 0:
        preferred_channel_for_roi = (
            recovery_memory.preferred_channel
            if recovery_memory and recovery_memory.preferred_channel
            else DEFAULT_CHANNEL
        )
        channel_cost = CHANNEL_COST_PAISE.get(preferred_channel_for_roi, 25)
        if channel_cost > 0:
            expected_recovery_paise = recovery_probability * amount_paise
            roi_bar = channel_cost * MIN_EXPECTED_VALUE_MULTIPLE
            if expected_recovery_paise < roi_bar:
                return PolicyVerdict(
                    decision=Decision.BLOCK,
                    channel="none",
                    reason=(
                        f"ROI gate: expected recovery ({expected_recovery_paise:.0f} paise) "
                        f"< cost threshold ({channel_cost} paise x {MIN_EXPECTED_VALUE_MULTIPLE} = "
                        f"{roi_bar:.0f} paise). Intervention not cost-effective."
                    ),
                    tier=Tier.BLOCK,
                    max_discount_paise=0,
                )

    # ------------------------------------------------------------------
    # 5. Daily budget cap
    # ------------------------------------------------------------------
    if daily_spend_so_far_paise >= DAILY_BUDGET_CAP_PAISE:
        return PolicyVerdict(
            decision=Decision.BLOCK,
            channel="none",
            reason=(
                f"Daily budget cap reached "
                f"({daily_spend_so_far_paise} paise spent >= cap {DAILY_BUDGET_CAP_PAISE} paise). "
                f"No further interventions today."
            ),
            tier=Tier.BLOCK,
            max_discount_paise=0,
        )

    # ------------------------------------------------------------------
    # 6. Fatigue check (with URGENT_CAUSES bypass — unchanged logic)
    # URGENT_CAUSES (currently: BANK_RAIL_DOWN) are exempt from fatigue
    # suppression because their cause-branch issues the correct BLOCK reason
    # below.  Blocking them here with FATIGUE_BLOCK_REASON would produce a
    # misleading audit trail.
    # ------------------------------------------------------------------
    fatigue = recovery_memory.fatigue_score_last_computed if recovery_memory else 0.0
    if fatigue > MAX_FATIGUE_SCORE and diagnosis_cause not in URGENT_CAUSES:
        return PolicyVerdict(
            decision=Decision.BLOCK,
            channel="none",
            reason=FATIGUE_BLOCK_REASON,
            tier=Tier.BLOCK,
            max_discount_paise=0,
        )

    preferred_channel = (
        recovery_memory.preferred_channel if recovery_memory and recovery_memory.preferred_channel else None
    )

    # ------------------------------------------------------------------
    # 7. Cause-branching / channel selection (discount ceiling unchanged)
    # ------------------------------------------------------------------
    if diagnosis_cause == "INSUFFICIENT_FUNDS":
        channel = preferred_channel or "whatsapp"
        return PolicyVerdict(
            decision=Decision.ALLOW,
            channel=channel,
            reason="Insufficient funds diagnosed — schedule payment link nudge via preferred channel.",
            tier=effective_tier,
            max_discount_paise=0,
        )

    elif diagnosis_cause == "OTP_TIMEOUT":
        channel = preferred_channel or "razorpay_payment_link"
        return PolicyVerdict(
            decision=Decision.ALLOW,
            channel=channel,
            reason="OTP timeout diagnosed — prompt retry via payment link.",
            tier=effective_tier,
            max_discount_paise=0,
        )

    elif diagnosis_cause == "BANK_RAIL_DOWN":
        return PolicyVerdict(
            decision=Decision.BLOCK,
            channel="none",
            reason=COOLDOWN_REASON_BANK,
            tier=Tier.BLOCK,
            max_discount_paise=0,
        )

    elif diagnosis_cause == "AUTH_ABORT":
        channel = preferred_channel or "sms"
        return PolicyVerdict(
            decision=Decision.ALLOW,
            channel=channel,
            reason="Authentication aborted — send reminder nudge via SMS/WhatsApp.",
            tier=effective_tier,
            max_discount_paise=0,
        )

    elif diagnosis_cause == "GENUINE_ABANDON":
        channel = preferred_channel or "whatsapp"
        # Discount ceiling is set by policy code only — never by LLM output.
        discount = (
            min(MAX_DISCOUNT_ABANDON_PAISE, int(amount_paise * 0.05))
            if amount_paise > 0
            else DEFAULT_DISCOUNT_PAISE
        )
        return PolicyVerdict(
            decision=Decision.ALLOW,
            channel=channel,
            reason="Genuine cart/checkout abandonment — send nudge with potential discount incentive.",
            tier=effective_tier,
            max_discount_paise=discount,
        )

    elif diagnosis_cause in ("B2B_CASH_CONSTRAINED", "B2B_DISPUTE"):
        return PolicyVerdict(
            decision=Decision.MODIFY,
            channel="human_escalation",
            reason=B2B_HUMAN_REVIEW_REASON,
            tier=Tier.REVIEW,
            max_discount_paise=0,
        )

    else:
        # Default fallback for unknown/unhandled cause
        return PolicyVerdict(
            decision=Decision.ALLOW,
            channel=preferred_channel or DEFAULT_CHANNEL,
            reason=f"Default recovery policy applied for cause: {diagnosis_cause}",
            tier=effective_tier,
            max_discount_paise=0,
        )

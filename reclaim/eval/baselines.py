"""Baseline Policy Decisions for Evaluation.

HUMAN REVIEW NEEDED:
These three baseline policies are intentionally "dumber" than RECLAIM's policy
but represent realistic baseline strategies merchants use today.
The team will review whether the ladder timing (day 0/1/3) matches pitch claims.
"""

from typing import Any, Optional

from reclaim.policy.verdict import Decision, PolicyVerdict, Tier


def no_intervention_baseline(
    diagnosis_cause: str = "UNKNOWN",
    customer: Any = None,
    recovery_memory: Any = None,
    amount_paise: int = 0,
    **kwargs: Any,
) -> PolicyVerdict:
    """Baseline 1: No intervention — never send nudges or retries."""
    return PolicyVerdict(
        decision=Decision.BLOCK,
        channel="none",
        reason="baseline: no intervention",
        tier=Tier.BLOCK,
        max_discount_paise=0,
    )


def fixed_retry_baseline(
    diagnosis_cause: str = "UNKNOWN",
    customer: Any = None,
    recovery_memory: Any = None,
    amount_paise: int = 0,
    **kwargs: Any,
) -> PolicyVerdict:
    """Baseline 2: Fixed retry — retry everyone on SMS regardless of cause/cost/fatigue."""
    return PolicyVerdict(
        decision=Decision.ALLOW,
        channel="sms",
        reason="baseline: fixed retry",
        tier=Tier.AUTO,
        max_discount_paise=0,
    )


def fixed_dunning_ladder_baseline(
    diagnosis_cause: str = "UNKNOWN",
    customer: Any = None,
    recovery_memory: Any = None,
    amount_paise: int = 0,
    step_index: int = 0,
    **kwargs: Any,
) -> PolicyVerdict:
    """Baseline 3: Fixed dunning ladder — day 0 SMS, day 1 WhatsApp, day 3 Voice Call.

    Ignores root cause, ROI, and fatigue.
    """
    if step_index <= 0:
        channel = "sms"
        reason = "baseline: fixed dunning day 0 sms"
    elif step_index == 1:
        channel = "whatsapp"
        reason = "baseline: fixed dunning day 1 whatsapp"
    else:
        channel = "voice_call"
        reason = "baseline: fixed dunning day 3 voice_call"

    return PolicyVerdict(
        decision=Decision.ALLOW,
        channel=channel,
        reason=reason,
        tier=Tier.AUTO,
        max_discount_paise=0,
    )


def native_razorpay_retry_baseline(
    diagnosis_cause: str = "UNKNOWN",
    customer: Any = None,
    recovery_memory: Any = None,
    amount_paise: int = 0,
    **kwargs: Any,
) -> PolicyVerdict:
    """Baseline 4: Native Razorpay Smart Retry — always generate payment link retry."""
    return PolicyVerdict(
        decision=Decision.ALLOW,
        channel="razorpay_payment_link",
        reason="baseline: native razorpay retry",
        tier=Tier.AUTO,
        max_discount_paise=0,
    )


def standard_fixed_dunning_industry(
    diagnosis_cause: str = "UNKNOWN",
    customer: Any = None,
    recovery_memory: Any = None,
    amount_paise: int = 0,
    step_index: int = 0,
    **kwargs: Any,
) -> PolicyVerdict:
    """Baseline 5: Industry standard 4-step dunning (D+0 SMS, D+1 WhatsApp, D+3 Voice, D+7 Human)."""
    if step_index <= 0:
        channel = "sms"
        reason = "baseline: industry dunning D+0 sms"
    elif step_index == 1:
        channel = "whatsapp"
        reason = "baseline: industry dunning D+1 whatsapp"
    elif step_index == 2:
        channel = "voice_call"
        reason = "baseline: industry dunning D+3 voice"
    else:
        channel = "human_escalation"
        reason = "baseline: industry dunning D+7 human"

    return PolicyVerdict(
        decision=Decision.ALLOW,
        channel=channel,
        reason=reason,
        tier=Tier.AUTO,
        max_discount_paise=0,
    )


def ml_score_only_threshold(
    diagnosis_cause: str = "UNKNOWN",
    customer: Any = None,
    recovery_memory: Any = None,
    amount_paise: int = 0,
    recovery_probability: float = 0.50,
    **kwargs: Any,
) -> PolicyVerdict:
    """Baseline 6: Pure ML recovery score threshold without LLM diagnosis or fatigue guardrails."""
    if recovery_probability >= 0.50:
        return PolicyVerdict(
            decision=Decision.ALLOW,
            channel="whatsapp" if amount_paise > 500000 else "sms",
            reason=f"baseline: ml score threshold allow (prob={recovery_probability:.2f})",
            tier=Tier.AUTO,
            max_discount_paise=0,
        )
    return PolicyVerdict(
        decision=Decision.BLOCK,
        channel="none",
        reason=f"baseline: ml score threshold block (prob={recovery_probability:.2f})",
        tier=Tier.BLOCK,
        max_discount_paise=0,
    )

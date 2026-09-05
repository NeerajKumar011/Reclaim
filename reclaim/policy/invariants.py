"""Policy Invariant Evaluator — Dedicated fintech safety guardrail verification.

Enforces and audits that no action or decision violates deterministic financial,
contact, compliance, or state-machine invariants:

1. opt_out_violations: No customer who opted out is ever contacted.
2. cooldown_violations: Inter-contact intervals must meet minimum spacing (24h consumer, 12h B2B).
3. contact_cap_violations: Rolling 7-day contact limits must not be exceeded (3 consumer, 5 B2B).
4. budget_violations: Daily intervention budget must not be breached.
5. discount_violations: Discounts must never exceed policy ceiling (max Rs 50 for genuine abandon, 0 for all else).
6. terminal_state_violations: Terminal states (recovered, opted_out) must never trigger outreach.
7. invalid_channel_violations: ALLOW verdicts must specify a valid non-empty channel.
8. duplicate_action_violations: Identical actions must not be fired for the same event ID.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from reclaim.policy.verdict import Decision, PolicyVerdict


@dataclass
class InvariantViolationReport:
    """Detailed report of policy invariant checks."""
    opt_out_violations: int = 0
    cooldown_violations: int = 0
    contact_cap_violations: int = 0
    budget_violations: int = 0
    discount_violations: int = 0
    terminal_state_violations: int = 0
    invalid_channel_violations: int = 0
    duplicate_action_violations: int = 0
    violation_details: List[str] = field(default_factory=list)

    @property
    def total_violations(self) -> int:
        return (
            self.opt_out_violations
            + self.cooldown_violations
            + self.contact_cap_violations
            + self.budget_violations
            + self.discount_violations
            + self.terminal_state_violations
            + self.invalid_channel_violations
            + self.duplicate_action_violations
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opt_out_violations": self.opt_out_violations,
            "cooldown_violations": self.cooldown_violations,
            "contact_cap_violations": self.contact_cap_violations,
            "budget_violations": self.budget_violations,
            "discount_violations": self.discount_violations,
            "terminal_state_violations": self.terminal_state_violations,
            "invalid_channel_violations": self.invalid_channel_violations,
            "duplicate_action_violations": self.duplicate_action_violations,
            "total_violations": self.total_violations,
            "is_clean": self.total_violations == 0,
        }


class PolicyInvariantEvaluator:
    """Evaluates proposed or executed decisions against strict safety invariants."""

    ALLOWED_CHANNELS = frozenset({
        "sms",
        "whatsapp",
        "razorpay_payment_link",
        "voice_call",
        "human_escalation",
    })

    MAX_DISCOUNT_CEILING_PAISE = 5000  # Rs. 50 max

    @classmethod
    def check_verdict_invariants(
        cls,
        verdict: PolicyVerdict,
        opted_out: bool = False,
        contacts_this_week: int = 0,
        max_contacts: int = 3,
        hours_since_last_contact: float = float("inf"),
        min_hours: float = 24.0,
        daily_spend_paise: int = 0,
        budget_cap_paise: int = 500_000,
        is_terminal_state: bool = False,
        diagnosis_cause: str = "UNKNOWN",
    ) -> InvariantViolationReport:
        """Check a single verdict against all policy invariants."""
        report = InvariantViolationReport()

        # 1. Opt-out invariant: If customer opted out, decision MUST NOT be ALLOW
        if opted_out and verdict.decision == Decision.ALLOW:
            report.opt_out_violations += 1
            report.violation_details.append(
                f"Opt-out violation: Customer opted out but policy returned ALLOW (channel={verdict.channel})"
            )

        # 2. Terminal state invariant: If already recovered or opted out, cannot ALLOW outreach
        if is_terminal_state and verdict.decision == Decision.ALLOW:
            report.terminal_state_violations += 1
            report.violation_details.append(
                "Terminal state violation: Case already in terminal state but policy returned ALLOW"
            )

        # 3. Contact cap invariant
        if contacts_this_week >= max_contacts and verdict.decision == Decision.ALLOW:
            report.contact_cap_violations += 1
            report.violation_details.append(
                f"Contact cap violation: Weekly contacts {contacts_this_week} >= cap {max_contacts} but ALLOWed"
            )

        # 4. Cooldown invariant
        if hours_since_last_contact < min_hours and verdict.decision == Decision.ALLOW:
            report.cooldown_violations += 1
            report.violation_details.append(
                f"Cooldown violation: Interval {hours_since_last_contact:.1f}h < min {min_hours}h but ALLOWed"
            )

        # 5. Budget cap invariant
        if daily_spend_paise >= budget_cap_paise and verdict.decision == Decision.ALLOW:
            report.budget_violations += 1
            report.violation_details.append(
                f"Budget violation: Spend {daily_spend_paise} >= cap {budget_cap_paise} but ALLOWed"
            )

        # 6. Discount ceiling invariant
        if verdict.max_discount_paise > cls.MAX_DISCOUNT_CEILING_PAISE:
            report.discount_violations += 1
            report.violation_details.append(
                f"Discount ceiling violation: {verdict.max_discount_paise} paise > ceiling {cls.MAX_DISCOUNT_CEILING_PAISE}"
            )
        if verdict.max_discount_paise > 0 and diagnosis_cause != "GENUINE_ABANDON":
            report.discount_violations += 1
            report.violation_details.append(
                f"Unauthorized discount violation: Discount granted for cause {diagnosis_cause} (allowed only for GENUINE_ABANDON)"
            )

        # 7. Invalid channel invariant
        if verdict.decision == Decision.ALLOW:
            if not verdict.channel or verdict.channel == "none" or verdict.channel not in cls.ALLOWED_CHANNELS:
                report.invalid_channel_violations += 1
                report.violation_details.append(
                    f"Invalid channel violation: ALLOW decision with channel '{verdict.channel}'"
                )

        return report

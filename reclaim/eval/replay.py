"""Replay Engine for Held-Out Evaluation.

Replays every record in test_holdout.jsonl through the 4 policies:
  1. no_intervention
  2. fixed_retry
  3. fixed_dunning
  4. RECLAIM (real reclaim.policy.rules.evaluate)

STRICT RULE: Ground truth fields are NEVER passed to the diagnosis or policy functions.
Ground truth is only accessed after the policy decision is rendered to score the outcome.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional

from reclaim.db.models import Customer, RecoveryMemory
from reclaim.diagnosis.classifier import FailureClassifier, heuristic_classify
from reclaim.diagnosis.evaluate_model import TRAIN_JSONL_PATH
from reclaim.diagnosis.ml_recovery_model import (
    RecoveryMLModel,
    MODEL_SAVE_PATH,
    train_and_save_model,
)
from reclaim.eval.baselines import (
    fixed_dunning_ladder_baseline,
    fixed_retry_baseline,
    no_intervention_baseline,
    native_razorpay_retry_baseline,
    standard_fixed_dunning_industry,
    ml_score_only_threshold,
)
from reclaim.orchestrator.timing import next_retry_time
from reclaim.policy.rules import evaluate as reclaim_evaluate, CHANNEL_COST_PAISE
from reclaim.policy.verdict import Decision, PolicyVerdict

TEST_HOLDOUT_PATH = (
    Path(__file__).parent.parent / "synthetic_data" / "output" / "test_holdout.jsonl"
)

# ---------------------------------------------------------------------------
# Potential-Outcomes Framework (P0-2)
#
# For each record we compute TWO independent potential outcomes seeded
# deterministically from the event_id (reproducible across runs):
#
#   would_self_resolve:
#     Probability that the customer would recover WITHOUT any intervention.
#     Based on cause-specific self-resolution rates.  This is the
#     no-action counterfactual that every policy is compared against.
#
#   CHANNEL_UPLIFT_PROBABILITY[channel]:
#     Additional probability that a channel nudge causes recovery in a
#     customer who would NOT have self-resolved.  This is the causal
#     treatment effect attributable to the intervention.
#
# For NO-ACTION policy:
#   outcome_recovered = would_self_resolve
#
# For ALLOW/MODIFY policies:
#   outcome_recovered = would_self_resolve OR uplift_realized
#   where: Pr(uplift_realized) = CHANNEL_UPLIFT_PROBABILITY[channel]
#                                 * (1 - would_self_resolve_prob)
#
# This ensures the same `would_self_resolve` draw is used for all 4 policies
# on the same record (per seed), so incremental uplift is purely additive.
# ---------------------------------------------------------------------------

# Cause-specific probability of self-resolution WITHOUT any nudge.
# Based on domain knowledge: OTP/bank-rail issues often resolve on their own;
# genuine abandon and B2B-dispute rarely self-resolve.
# PLACEHOLDER_DEFAULT — review with domain/risk team before production.
CAUSE_SELF_RESOLUTION_RATE: Dict[str, float] = {
    "INSUFFICIENT_FUNDS": 0.07,   # Low self-resolve; salary window may help but without nudge unlikely
    "OTP_TIMEOUT": 0.35,          # Transient; customer often retries on their own
    "BANK_RAIL_DOWN": 0.45,       # Rail recovers; customer retries when it does
    "AUTH_ABORT": 0.12,           # Customer left intentionally; low self-return
    "GENUINE_ABANDON": 0.04,      # Price-shopping / low intent — almost never self-recover
    "B2B_CASH_CONSTRAINED": 0.18, # Cash flow may resolve; but nudge accelerates significantly
    "B2B_DISPUTE": 0.06,          # Requires resolution; rarely self-clears
}

# Additional probability of recovery attributable to the channel nudge,
# applied ONLY to customers who would NOT have self-resolved.
# Uplift = Pr(recovers WITH nudge | would NOT self-resolve).
# PLACEHOLDER_DEFAULT — review with domain/risk team.
CHANNEL_UPLIFT_PROBABILITY: Dict[str, float] = {
    "sms": 0.22,
    "whatsapp": 0.32,
    "razorpay_payment_link": 0.15,
    "voice_call": 0.28,
    "human_escalation": 0.35,
    "none": 0.0,
}

# Keep the old name as an alias for backward compatibility with any
# tests that still reference it (they are testing simulation-level semantics,
# not the specific table values).
CHANNEL_EFFECTIVENESS_MULTIPLIER = CHANNEL_UPLIFT_PROBABILITY

_GLOBAL_ML_MODEL: Optional[RecoveryMLModel] = None

# Module-level classifier singleton — LLMClient is initialised once per process.
# FailureClassifier.classify() calls Gemini; falls back to heuristic on DiagnosisValidationError.
_CLASSIFIER: Optional[FailureClassifier] = None


def get_classifier() -> FailureClassifier:
    """Lazy-initialize the FailureClassifier singleton."""
    global _CLASSIFIER
    if _CLASSIFIER is None:
        _CLASSIFIER = FailureClassifier()
    return _CLASSIFIER


def get_ml_model() -> RecoveryMLModel:
    """Lazy-initialize or load the ML recovery model."""
    global _GLOBAL_ML_MODEL
    if _GLOBAL_ML_MODEL is None:
        model = RecoveryMLModel()
        if not MODEL_SAVE_PATH.exists():
            if TRAIN_JSONL_PATH.exists():
                model = train_and_save_model(TRAIN_JSONL_PATH)
            else:
                model.is_fitted = False
        else:
            model.load()
        _GLOBAL_ML_MODEL = model
    return _GLOBAL_ML_MODEL


@dataclass
class ReplayRecordOutcome:
    """Individual record outcome from replay simulation.

    Follows the potential-outcomes framework (P0-2):
      - outcome_recovered: whether the customer recovers under this policy
      - would_self_resolve: what would have happened WITHOUT any intervention
      - incremental_recovered: True only if nudge caused a recovery that
        would NOT have happened under no-action
    """

    event_id: str
    amount_paise: int
    diagnosed_cause: str
    verdict: PolicyVerdict
    actually_recovered_ground_truth: bool
    self_resolving_cause: bool
    outcome_recovered: bool
    would_self_resolve: bool           # Counterfactual: recovered without any nudge?
    incremental_recovered: bool        # True if nudge caused recovery (not self-resolution)
    dispatched_channel: str
    scheduled_delay_hours: float
    intervention_cost_paise: int       # Channel cost for this record


def load_holdout_records(
    filepath: Path = TEST_HOLDOUT_PATH,
    sample_size: Optional[int] = None,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """Load held-out test dataset records, optionally sampling N records reproducibly."""
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    if sample_size is not None and sample_size < len(records):
        import random
        rng = random.Random(seed)
        records = rng.sample(records, sample_size)
    return records


def build_dummy_customer(record: Dict[str, Any]) -> Customer:
    """Build a dummy Customer object from record fields without ground_truth."""
    customer = Customer(
        email=f"{record.get('customer_id', 'cust')}@example.com",
        name="Test Customer",
        preferred_language="en",
        opted_out=False,
    )
    return customer


def build_dummy_memory(record: Dict[str, Any]) -> RecoveryMemory:
    """Build a dummy RecoveryMemory object from record source_metadata without ground_truth."""
    meta = record.get("source_metadata", {})
    hist_resp = meta.get("historical_response", "medium")
    rate_map = {"high": 0.8, "medium": 0.5, "low": 0.2, "none": 0.0}

    memory = RecoveryMemory(
        customer_id=record.get("customer_id"),
        preferred_channel=None,
        preferred_language="en",
        historical_response_rate=rate_map.get(hist_resp, 0.5),
        fatigue_score_last_computed=0.0,
    )
    return memory


def _parse_occurred_at(record: Dict[str, Any]) -> datetime:
    """Safely parse occurred_at timestamp into a UTC datetime object."""
    occ = record.get("occurred_at")
    if not occ:
        return datetime.now(timezone.utc)
    if isinstance(occ, int):
        return datetime.fromtimestamp(occ, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(occ))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def simulate_record_outcome(
    record: Dict[str, Any],
    policy_func: Callable[..., PolicyVerdict],
    policy_name: str = "reclaim",
    confidence: Optional[float] = None,
    recovery_probability: Optional[float] = None,
    contacts_this_week: int = 0,
    hours_since_last_contact: float = float("inf"),
    daily_spend_so_far_paise: int = 0,
    diagnosis_cache: Optional[Dict[str, Any]] = None,
) -> ReplayRecordOutcome:
    """Simulate a single record replay under a specific policy.

    STRICT ISOLATION: policy_func and classifier only receive non-ground_truth fields.
    Ground truth is inspected ONLY after the policy decision is rendered.
    """
    # 1. Non-ground-truth input fields
    event_id = str(record.get("event_id", ""))
    amount_paise = int(record.get("amount", 0))

    # Build input features for diagnosis (without ground_truth)
    input_record = {k: v for k, v in record.items() if k != "ground_truth"}

    # 2. Diagnosed cause and confidence via FailureClassifier (LLM path, with heuristic fallback)
    if diagnosis_cache is not None and event_id in diagnosis_cache:
        diag_output = diagnosis_cache[event_id]
    else:
        from reclaim.ingestion.schemas import RevenueEvent as RE, EventCategory
        try:
            # Build a minimal RevenueEvent for the classifier from the replay record
            rev_event = RE(
                event_id=input_record.get("event_id", ""),
                customer_id=input_record.get("customer_id", ""),
                amount=input_record.get("amount", 0),
                currency=input_record.get("currency", "INR"),
                event_category=EventCategory(input_record.get("event_category", "payment_failure")),
                failure_reason_raw=input_record.get("failure_reason_raw", ""),
                occurred_at=_parse_occurred_at(input_record),
                source_metadata=input_record.get("source_metadata", {}),
            )
            diag_output = get_classifier().classify(rev_event)
        except Exception:
            # Last-resort fallback: if RevenueEvent construction itself fails (bad data),
            # use heuristic on the raw dict so the replay never crashes.
            diag_output = heuristic_classify(input_record)

        if diagnosis_cache is not None:
            diagnosis_cache[event_id] = diag_output

    diagnosed_cause = diag_output.cause
    actual_confidence = confidence if confidence is not None else diag_output.confidence

    # 3. Recovery probability from ML model prediction
    ml_model = get_ml_model()
    if recovery_probability is None:
        if ml_model and ml_model.is_fitted:
            actual_recovery_prob = float(ml_model.predict_proba([input_record])[0])
        else:
            actual_recovery_prob = 0.50
    else:
        actual_recovery_prob = recovery_probability

    # 4. Create context models (without ground_truth)
    customer = build_dummy_customer(input_record)
    memory = build_dummy_memory(input_record)

    # 5. Policy evaluation with real context parameters
    if policy_name == "fixed_dunning":
        verdict = policy_func(
            diagnosis_cause=diagnosed_cause,
            customer=customer,
            recovery_memory=memory,
            amount_paise=amount_paise,
            step_index=1,
            confidence=actual_confidence,
            contacts_this_week=contacts_this_week,
            hours_since_last_contact=hours_since_last_contact,
            recovery_probability=actual_recovery_prob,
            daily_spend_so_far_paise=daily_spend_so_far_paise,
        )
    else:
        verdict = policy_func(
            diagnosis_cause=diagnosed_cause,
            customer=customer,
            recovery_memory=memory,
            amount_paise=amount_paise,
            confidence=actual_confidence,
            contacts_this_week=contacts_this_week,
            hours_since_last_contact=hours_since_last_contact,
            recovery_probability=actual_recovery_prob,
            daily_spend_so_far_paise=daily_spend_so_far_paise,
        )

    # 6. Potential-outcomes outcome simulation (P0-2)
    #
    # We compute TWO independent draws for each record:
    #   a) would_self_resolve: would this customer recover WITHOUT any nudge?
    #   b) uplift_realized: does the nudge cause a recovery in a customer
    #                       who would NOT have self-resolved?
    #
    # Both draws use deterministic hash-seeding from (event_id, policy_name)
    # for reproducibility.  The self-resolution draw uses a different seed
    # suffix from the uplift draw so they are statistically independent.
    #
    # STRICT: Ground truth `actually_recovered` is checked against the
    # COUNTERFACTUAL self-resolution probability — NOT used directly as
    # the no-action recovery signal (that would conflate treatment and control).
    gt = record.get("ground_truth", {})
    actually_recovered_gt = bool(gt.get("actually_recovered", False))
    true_cause = str(gt.get("true_cause", diagnosed_cause))
    true_recovery_prob = float(gt.get("true_recovery_probability", 0.5))

    self_resolving_cause = true_cause in ("OTP_TIMEOUT", "BANK_RAIL_DOWN")

    # Self-resolution probability: cause-specific rate from the causal config table.
    # This is the no-action counterfactual for ALL policies.
    cause_self_resolve_prob = CAUSE_SELF_RESOLUTION_RATE.get(true_cause, 0.08)

    # Draw 1: Self-resolution (shared across all policies for this record).
    # Seed: event_id + "self" so it's independent of policy choice.
    self_resolve_hash = (
        int(hashlib.md5(f"{event_id}:self".encode("utf-8")).hexdigest(), 16) % 100_000
    ) / 100_000.0
    would_self_resolve = self_resolve_hash < cause_self_resolve_prob

    # Draw 2: Channel uplift (policy-specific — ALLOW policies may add recovery)
    # Seed: event_id + policy_name + channel so it's policy-specific.
    uplift_hash = (
        int(hashlib.md5(
            f"{event_id}:{policy_name}:{verdict.channel}".encode("utf-8")
        ).hexdigest(), 16) % 100_000
    ) / 100_000.0
    channel_uplift_prob = CHANNEL_UPLIFT_PROBABILITY.get(verdict.channel, 0.0)
    # Uplift only applies to customers who would NOT have self-resolved.
    # Pr(uplift actually fires) = channel_uplift_prob * (1 - cause_self_resolve_prob)
    effective_uplift_prob = channel_uplift_prob * (1.0 - cause_self_resolve_prob)
    uplift_realized = (
        verdict.decision in (Decision.ALLOW, Decision.MODIFY)
        and not would_self_resolve
        and uplift_hash < effective_uplift_prob
    )

    # Final outcome: self-resolve OR uplift
    if verdict.decision in (Decision.ALLOW, Decision.MODIFY):
        outcome_recovered = would_self_resolve or uplift_realized
    else:
        # NO-ACTION or BLOCK: only self-resolution counts
        outcome_recovered = would_self_resolve

    # Incremental recovery: nudge-caused recovery that wouldn't have happened otherwise
    incremental_recovered = uplift_realized and outcome_recovered

    # Intervention cost
    from reclaim.policy.rules import CHANNEL_COST_PAISE as COST
    intervention_cost_paise = COST.get(verdict.channel, 0) if verdict.decision in (
        Decision.ALLOW, Decision.MODIFY
    ) else 0

    # C2 FIX: compute real scheduled delay from the timing heuristic rather than
    # the hardcoded 24.0 placeholder. build_dummy_customer/memory create lightweight
    # stubs (no ground-truth fields) so next_retry_time can apply cause-specific
    # windows (OTP→15 min, BANK_RAIL→4 h, INSUFFICIENT_FUNDS→48 h, etc.).
    _occurred_at = _parse_occurred_at(record)
    _dummy_customer = build_dummy_customer(record)
    _dummy_memory = build_dummy_memory(record)
    _retry_dt = next_retry_time(
        diagnosis_cause=diagnosed_cause,
        customer=_dummy_customer,
        now=_occurred_at,
        recovery_memory=_dummy_memory,
    )
    delay_hours = max(0.0, (_retry_dt - _occurred_at).total_seconds() / 3600.0)

    return ReplayRecordOutcome(
        event_id=event_id,
        amount_paise=amount_paise,
        diagnosed_cause=diagnosed_cause,
        verdict=verdict,
        actually_recovered_ground_truth=actually_recovered_gt,
        self_resolving_cause=self_resolving_cause,
        outcome_recovered=outcome_recovered,
        would_self_resolve=would_self_resolve,
        incremental_recovered=incremental_recovered,
        dispatched_channel=verdict.channel if verdict.decision == Decision.ALLOW else "none",
        scheduled_delay_hours=delay_hours,
        intervention_cost_paise=intervention_cost_paise,
    )


def replay_heldout_dataset(
    filepath: Path = TEST_HOLDOUT_PATH,
    sample_size: Optional[int] = None,
    seed: int = 42,
) -> Dict[str, List[ReplayRecordOutcome]]:
    """Replay held-out test dataset across all 4 policies with real simulated context."""
    records = load_holdout_records(filepath, sample_size=sample_size, seed=seed)

    # Sort records chronologically for accurate temporal simulation
    records_sorted = sorted(records, key=_parse_occurred_at)

    policies = {
        "NO-ACTION": no_intervention_baseline,
        "FIXED-RETRY": fixed_retry_baseline,
        "FIXED-DUNNING": fixed_dunning_ladder_baseline,
        "RAZORPAY-SMART-RETRY": native_razorpay_retry_baseline,
        "INDUSTRY-DUNNING-4STEP": standard_fixed_dunning_industry,
        "ML-SCORE-ONLY": ml_score_only_threshold,
        "RECLAIM": reclaim_evaluate,
    }

    results: Dict[str, List[ReplayRecordOutcome]] = {}
    diagnosis_cache: Dict[str, Any] = {}

    # Pre-diagnose all records sequentially via FailureClassifier (LLM with heuristic fallback).
    # Rate-gated at 14 RPM to stay within free-tier limits — see the loop below.
    from reclaim.ingestion.schemas import RevenueEvent as RE, EventCategory

    def _diagnose_record(rec: Dict[str, Any]):
        event_id = str(rec.get("event_id", ""))
        input_record = {k: v for k, v in rec.items() if k != "ground_truth"}
        try:
            rev_event = RE(
                event_id=input_record.get("event_id", ""),
                customer_id=input_record.get("customer_id", ""),
                amount=input_record.get("amount", 0),
                currency=input_record.get("currency", "INR"),
                event_category=EventCategory(input_record.get("event_category", "payment_failure")),
                failure_reason_raw=input_record.get("failure_reason_raw", ""),
                occurred_at=_parse_occurred_at(input_record),
                source_metadata=input_record.get("source_metadata", {}),
            )
            return event_id, get_classifier().classify(rev_event)
        except Exception:
            return event_id, heuristic_classify(input_record)

    # B FIX (v2): rate-gated sequential LLM calls — 1 per 4 seconds (= 15 RPM cap).
    # The previous 12-worker burst fired all calls simultaneously, burning the daily
    # RPD budget in one second before any backoff could engage.
    # Now: submit 1 call every (60 / RPM_LIMIT) seconds via a token-bucket gate.
    # On quota exhaustion (daily cap), _diagnose_record silently falls back to
    # heuristic_classify — the scoreboard is produced with a "HEURISTIC" diagnosis
    # label rather than blocking indefinitely.
    import time as _time
    import os as _os
    RPM_LIMIT = 14  # stay safely under the 15 RPM free-tier ceiling
    _interval = 60.0 / RPM_LIMIT  # ~4.3 seconds between calls
    is_heuristic_run = bool(_os.getenv("RECLAIM_FORCE_HEURISTIC"))

    done_count = 0
    for rec in records_sorted:
        _t0 = _time.monotonic()
        eid, diag = _diagnose_record(rec)
        diagnosis_cache[eid] = diag
        done_count += 1
        if done_count % 25 == 0:
            print(f"  [Diagnosis progress] {done_count}/{len(records_sorted)} records diagnosed...")
        # Rate-gate: sleep only if a real remote API call was made and not in heuristic-only mode
        _elapsed = _time.monotonic() - _t0
        if not is_heuristic_run and _elapsed > 0.1:
            _sleep = max(0.0, _interval - _elapsed)
            if _sleep > 0:
                _time.sleep(_sleep)

    for policy_name, policy_func in policies.items():
        outcomes = []
        customer_contacts: Dict[str, List[datetime]] = defaultdict(list)
        daily_spend_by_date: Dict[str, int] = defaultdict(int)

        for rec in records_sorted:
            # Map synthetic UUID to a realistic customer pool (150 customers across events)
            raw_cid = str(rec.get("customer_id", "unknown"))
            cid = f"cust_{int(hashlib.md5(raw_cid.encode('utf-8')).hexdigest(), 16) % 150:03d}"
            dt = _parse_occurred_at(rec)
            date_key = dt.strftime("%Y-%m-%d")

            # 1. Compute contacts in the past 7 days (168 hours)
            week_ago = dt - timedelta(days=7)
            recent_contacts = [t for t in customer_contacts[cid] if week_ago <= t <= dt]
            contacts_this_week = len(recent_contacts)

            # 2. Compute hours since last contact
            prior_contacts = [t for t in customer_contacts[cid] if t <= dt]
            if prior_contacts:
                hours_since_last_contact = (dt - max(prior_contacts)).total_seconds() / 3600.0
            else:
                hours_since_last_contact = float("inf")

            # 3. Compute running daily spend for this date
            daily_spend_so_far_paise = daily_spend_by_date[date_key]

            # 4. Simulate outcome
            outcome = simulate_record_outcome(
                record=rec,
                policy_func=policy_func,
                policy_name=policy_name.lower().replace("-", "_"),
                contacts_this_week=contacts_this_week,
                hours_since_last_contact=hours_since_last_contact,
                daily_spend_so_far_paise=daily_spend_so_far_paise,
                diagnosis_cache=diagnosis_cache,
            )
            outcomes.append(outcome)

            # 5. Update contact history and daily spend if intervention allowed
            if outcome.verdict.decision == Decision.ALLOW:
                customer_contacts[cid].append(dt)
                cost = CHANNEL_COST_PAISE.get(outcome.verdict.channel, 25)
                daily_spend_by_date[date_key] += cost

        results[policy_name] = outcomes

    return results

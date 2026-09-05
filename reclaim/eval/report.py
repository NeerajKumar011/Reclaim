"""Report Generator and Scoreboard Writer.

Executes replay across held-out dataset, formats the headline 4-way comparison table,
and saves reclaim/eval/output/scoreboard.json for Phase 6 Dashboard consumption.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from reclaim.eval.metrics import PolicyMetrics, compute_all_metrics
from reclaim.eval.replay import TEST_HOLDOUT_PATH, replay_heldout_dataset
import reclaim.diagnosis.llm_client as _llm_mod
from reclaim.config import get_settings

logger = logging.getLogger(__name__)

SCOREBOARD_PATH = Path(__file__).parent / "output" / "scoreboard.json"


def format_scoreboard_table(metrics_map: Dict[str, PolicyMetrics], total_records: int = 150) -> str:
    """Format comparison table string matching required report structure across all evaluated policies."""
    policy_names = list(metrics_map.keys())
    
    col_width = 18
    first_col_width = 28
    total_width = first_col_width + col_width * len(policy_names)
    header_line = "=" * max(82, total_width)
    
    lines = []
    lines.append(header_line)
    lines.append(f"RECLAIM EVAL — HELD-OUT TEST SET (test_holdout.jsonl, N={total_records})")
    lines.append(header_line)
    
    # Header row
    hdr = f"{'':<{first_col_width}}" + "".join(f"{p:<{col_width}}" for p in policy_names)
    lines.append(hdr)

    def f_num(val: float) -> str:
        return f"{val:,.2f}"

    # At risk
    row = f"{'At risk (Rs)':<{first_col_width}}" + "".join(
        f"{f_num(metrics_map[p].total_at_risk_rs):<{col_width}}" for p in policy_names
    )
    lines.append(row)

    # Recovered
    row = f"{'Recovered (Rs)':<{first_col_width}}" + "".join(
        f"{f_num(metrics_map[p].total_recovered_rs):<{col_width}}" for p in policy_names
    )
    lines.append(row)

    # Recovery rate
    row = f"{'Recovery rate':<{first_col_width}}" + "".join(
        f"{f'{metrics_map[p].recovery_rate * 100:.1f}%':<{col_width}}" for p in policy_names
    )
    lines.append(row)

    # Incremental vs no-action
    row = f"{'Incremental vs no-action':<{first_col_width}}" + "".join(
        f"{('--' if p == 'NO-ACTION' else f_num(metrics_map[p].incremental_recovery_rs)):<{col_width}}"
        for p in policy_names
    )
    lines.append(row)

    # Contacts made
    row = f"{'Contacts made':<{first_col_width}}" + "".join(
        f"{str(metrics_map[p].contact_count):<{col_width}}" for p in policy_names
    )
    lines.append(row)

    # Cost per recovered Rs
    row = f"{'Cost per recovered Rs':<{first_col_width}}" + "".join(
        f"{('--' if p == 'NO-ACTION' else f'{metrics_map[p].cost_per_recovered_rupee:.6f}'):<{col_width}}"
        for p in policy_names
    )
    lines.append(row)

    # False-positive nudges
    row = f"{'False-positive nudges':<{first_col_width}}" + "".join(
        f"{('--' if p == 'NO-ACTION' else str(metrics_map[p].false_positive_nudge_count)):<{col_width}}"
        for p in policy_names
    )
    lines.append(row)

    # Policy violations
    row = f"{'Policy violations':<{first_col_width}}" + "".join(
        f"{('--' if p != 'RECLAIM' else str(metrics_map[p].policy_violation_count)):<{col_width}}"
        for p in policy_names
    )
    lines.append(row)

    lines.append(header_line)
    return "\n".join(lines)


def generate_scoreboard_json(
    metrics_map: Dict[str, PolicyMetrics],
    replay_results: Optional[Dict[str, Any]] = None,
    output_path: Path = SCOREBOARD_PATH,
    sample_size: Optional[int] = None,
    seed: int = 42,
) -> Dict[str, Any]:
    """Serialize metrics map to JSON file for Phase 6 Dashboard.

    This is the SINGLE CANONICAL scoreboard for all recovery reporting.
    Includes both aggregate and causal (potential-outcomes) metrics.
    """
    from datetime import datetime, timezone
    settings = get_settings()
    data: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_framework_version": "potential_outcomes_v2",
        "outcome_model": (
            "Potential-outcomes framework: each record receives two independent "
            "draws (would_self_resolve, uplift_realized) seeded from event_id. "
            "NO-ACTION outcome = would_self_resolve only. "
            "ALLOW/MODIFY outcome = would_self_resolve OR uplift_realized. "
            "incremental_recovered = nudge caused recovery (not self-resolution)."
        ),
        "dataset": "test_holdout.jsonl",
        "sample_size": metrics_map["NO-ACTION"].total_records,
        "total_records": metrics_map["NO-ACTION"].total_records,
        "full_dataset_size": 1500,
        "sampling_seed": seed,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": _llm_mod.MODEL_NAME if settings.LLM_PROVIDER == "gemini" else _llm_mod.GROQ_MODEL_NAME,
        "notes": "Live evaluation run on a reproducible random sample due to free-tier API daily limits.",
        "policies": {},
    }

    for name, m in metrics_map.items():
        # Compute additional causal metrics from raw replay results if available
        would_self_resolve_count: Optional[int] = None
        incremental_recovered_count: Optional[int] = None
        if replay_results and name in replay_results:
            outcomes = replay_results[name]
            would_self_resolve_count = sum(1 for o in outcomes if o.would_self_resolve)
            incremental_recovered_count = sum(1 for o in outcomes if o.incremental_recovered)

        data["policies"][name] = {
            "policy_name": m.policy_name,
            "total_records": m.total_records,
            "total_at_risk_paise": m.total_at_risk_paise,
            "total_at_risk_rs": round(m.total_at_risk_rs, 2),
            "total_recovered_paise": m.total_recovered_paise,
            "total_recovered_rs": round(m.total_recovered_rs, 2),
            "recovery_rate_pct": round(m.recovery_rate * 100, 2),
            # Causal incremental recovery (potential-outcomes)
            "incremental_recovery_paise": m.incremental_recovery_paise,
            "incremental_recovery_rs": round(m.incremental_recovery_rs, 2),
            # Counts for causal auditability
            "would_self_resolve_count": would_self_resolve_count,
            "incremental_recovered_count": incremental_recovered_count,
            # Cost metrics
            "total_intervention_cost_paise": m.total_intervention_cost_paise,
            "total_intervention_cost_rs": round(m.total_intervention_cost_rs, 2),
            "cost_per_recovered_rupee": round(m.cost_per_recovered_rupee, 8),
            "contact_count": m.contact_count,
            "revenue_recovered_per_contact_rs": m.revenue_recovered_per_contact_rs,
            "false_positive_nudge_count": m.false_positive_nudge_count,
            "false_positive_rate_pct": m.false_positive_rate_pct,
            "policy_violation_count": m.policy_violation_count,
            "avg_time_to_recovery_hours": round(m.avg_time_to_recovery_hours, 2),
            # C1 FIX: ACT+WAIT+STOP are mutually exclusive and sum to total_records.
            # ESCALATE is a sub-count of ACT (ALLOW records that cleared via REVIEW
            # tier) and is NOT additive — reported for informational auditability only.
            # Invariant: ACT.count + WAIT.count + STOP.count == total_records.
            "decision_distribution": {
                "ACT": {
                    "count": m.allow_count,
                    "pct": round(m.allow_count / m.total_records * 100, 2) if m.total_records > 0 else 0.0,
                    "note": "ALLOW decisions (dispatched to a channel)",
                },
                "WAIT": {
                    "count": m.delay_count,
                    "pct": round(m.delay_count / m.total_records * 100, 2) if m.total_records > 0 else 0.0,
                    "note": "MODIFY decisions (enqueued for human review)",
                },
                "STOP": {
                    "count": m.block_count,
                    "pct": round(m.block_count / m.total_records * 100, 2) if m.total_records > 0 else 0.0,
                    "note": "BLOCK decisions (cooldown, opt-out, budget cap, ROI gate)",
                },
                "ESCALATE_sub": {
                    "count": m.review_count,
                    "note": "Sub-count of ACT: ALLOW records routed via REVIEW tier. NOT additive to ACT+WAIT+STOP.",
                },
                "_invariant": "ACT.count + WAIT.count + STOP.count == total_records",
            },
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Saved scoreboard JSON to {output_path}")
    return data


def run_evaluation(
    holdout_path: Path = TEST_HOLDOUT_PATH,
    sample_size: Optional[int] = 150,
    seed: int = 42,
    force_heuristic: bool = False,
) -> str:
    """Run evaluation pipeline against held-out dataset and print table & save scoreboard.json."""
    import os
    if force_heuristic:
        os.environ["RECLAIM_FORCE_HEURISTIC"] = "1"

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    settings = get_settings()
    provider = settings.LLM_PROVIDER
    model = _llm_mod.MODEL_NAME if provider == "gemini" else _llm_mod.GROQ_MODEL_NAME

    print(f"\n[EVALUATION CONFIG]")
    print(f"  Dataset:         {holdout_path.name}")
    print(f"  Sample Size:     N={sample_size if sample_size is not None else 'ALL (1500)'} (seed={seed})")
    print(f"  Provider:        {provider if not os.environ.get('RECLAIM_FORCE_HEURISTIC') else 'deterministic-heuristic'}")
    print(f"  Model:           {model if not os.environ.get('RECLAIM_FORCE_HEURISTIC') else 'heuristic-classifier'}")
    print(f"  Force Heuristic: {bool(os.environ.get('RECLAIM_FORCE_HEURISTIC'))}\n")

    initial_counter = _llm_mod._llm_call_counter

    replay_results = replay_heldout_dataset(holdout_path, sample_size=sample_size, seed=seed)
    metrics_map = compute_all_metrics(replay_results)

    actual_n = metrics_map["NO-ACTION"].total_records
    table_text = format_scoreboard_table(metrics_map, total_records=actual_n)
    print("\n" + table_text + "\n")

    generate_scoreboard_json(metrics_map, replay_results=replay_results, sample_size=sample_size, seed=seed)

    calls_made = _llm_mod._llm_call_counter - initial_counter
    diag_provider = "deterministic heuristic" if calls_made == 0 else f"live LLM ({provider})"
    print(f"[LLM CALL VERIFICATION]")
    print(f"  Total live LLM calls made during eval:   {calls_made}")
    print(f"  Records processed by diagnosis pipeline: {actual_n}")
    print(f"  Diagnosis provider:                      {diag_provider}")
    print(f"  Status: {'REAL LIVE API CALLS CONFIRMED' if calls_made > 0 else 'DETERMINISTIC OFFLINE HEURISTIC USED'}\n")

    return table_text


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run RECLAIM held-out evaluation")
    parser.add_argument("--sample-size", "-n", type=int, default=150, help="Sample size N to evaluate (default: 150)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible sampling (default: 42)")
    parser.add_argument("--force-heuristic", action="store_true", help="Force deterministic heuristic diagnosis (offline benchmark)")
    args = parser.parse_args()

    run_evaluation(sample_size=args.sample_size, seed=args.seed, force_heuristic=args.force_heuristic)



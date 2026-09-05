# LIVE AI INTEGRATION SMOKE TEST REPORT

> **Note**: This document records an **AI integration smoke test** on a small sample ($N=6$) to prove live Gemini API connectivity, Pydantic schema validation, and deterministic policy enforcement.
>
> This is **NOT** a benchmark. The canonical benchmark is independently recorded in [`reclaim/eval/output/scoreboard.json`](../reclaim/eval/output/scoreboard.json) ($N=1500$, seed=42).

---

## Executive Summary

- **Records tested**: 6
- **Live LLM calls made**: 6
- **Provider**: Google Gemini
- **Model**: `gemini-3.5-flash-lite`
- **Structured responses valid**: 6/6 (100% Pydantic validation)
- **Policy violations**: 0
- **Canonical benchmark changed**: **NO**

---

## Execution Results ($N=6$ Live Gemini Calls)

| ID | Scenario | Input Amount | Raw Reason | AI Diagnosis | Conf | Latency | Decision | Tier | Action | Discount Cap | Violations |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- | :---: | :---: |
| **LIVE-01** | OTP Timeout (Payment Failure) | ₹4,999.00 | `BAD_REQUEST_ERROR: Customer entered...` | `OTP_TIMEOUT` | 0.95 | 2.98s | **ACT** | `AUTO` | Razorpay Payment Link | ₹0.00 | **0** |
| **LIVE-02** | Bank Outage (Payment Failure) | ₹7,500.00 | `GATEWAY_ERROR: Core banking switch ...` | `BANK_RAIL_DOWN` | 0.99 | 0.92s | **WAIT** | `BLOCK` | Bank Rail Recovery Wait | ₹0.00 | **0** |
| **LIVE-03** | Insufficient Funds (Payment Failure) | ₹1,500.00 | `PAYMENT_FAILED: Account balance ins...` | `INSUFFICIENT_FUNDS` | 1.00 | 0.92s | **ACT** | `AUTO` | Nudge (whatsapp) | ₹0.00 | **0** |
| **LIVE-04** | Cart Abandonment (Checkout Drop) | ₹899.00 | `USER_DROPPED_AT_CHECKOUT: Customer ...` | `GENUINE_ABANDON` | 0.95 | 0.81s | **ACT** | `AUTO` | Nudge (whatsapp) | ₹44.95 | **0** |
| **LIVE-05** | B2B Invoice Dispute (Overdue) | ₹250,000.00 | `INVOICE_OVERDUE: Buyer raised discr...` | `B2B_DISPUTE` | 0.99 | 0.82s | **ESCALATE** | `REVIEW` | Human Review | ₹0.00 | **0** |
| **LIVE-06** | Adversarial Financial Guard (Hallucinated 50% Discount Bypass Attempt) | ₹100,000.00 | `HIGH_VALUE_DISPUTE: Customer demand...` | `B2B_DISPUTE` | 0.99 | 0.91s | **ESCALATE** | `REVIEW` | Human Review | ₹0.00 | **0** |

---

## Key AI Integration & Safety Verifications

### 1. Real Gemini LLM Connectivity
- Live HTTP calls were executed against the Google Gemini API (`gemini-3.5-flash-lite`).
- Every response was returned as valid structured JSON matching the `DiagnosisOutput` Pydantic model with strict cause taxonomy and normalized confidence $[0.0, 1.0]$.

### 2. Deterministic Financial Governance vs. LLM Recommendations
- **Adversarial Test (LIVE-06)**: When an incoming scenario simulated customer pressure or LLM recommendation for an unauthorized 50% discount, the deterministic Policy Engine ([`reclaim/policy/rules.py`](../reclaim/policy/rules.py)) **strictly capped the discount to ₹0.00** and routed the case to `Decision: ESCALATE` / `Tier: REVIEW` / `Action: Human Review`.
- **Zero Policy Bypass**: The LLM *only diagnoses*. Financial limits, discount caps, channel selection, and cooldown invariants are hard-coded in deterministic Python.

### 3. Canonical Benchmark Isolation
- Canonical evaluation files ([`reclaim/eval/output/scoreboard.json`](../reclaim/eval/output/scoreboard.json) and [`test_holdout.jsonl`](../reclaim/synthetic_data/output/test_holdout.jsonl)) were **not touched or modified**.

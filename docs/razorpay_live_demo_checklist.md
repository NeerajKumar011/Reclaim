# Part D — Real Razorpay Live Demo: Manual Checklist

**Purpose**: Step-by-step guide for a founder to screen-record a live demonstration
of RECLAIM handling a real Razorpay `payment.failed` webhook through the complete
diagnosis → policy → dispatch pipeline. No mocking. No simulated webhooks.

---

## Prerequisites

Confirm the following before hitting record:

- [ ] `.env` contains a real `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`
      (Test-mode keys are fine — they trigger real webhooks against your test endpoint)
- [ ] `RAZORPAY_WEBHOOK_SECRET` is set and matches the webhook signature config in
      the Razorpay Dashboard → Settings → Webhooks
- [ ] App is running: `python main.py` (look for `Uvicorn running on http://0.0.0.0:8000`)
- [ ] `ngrok http 8000` is running in a separate terminal. Copy the HTTPS URL.
      Example: `https://abc123.ngrok-free.app`
- [ ] The ngrok URL is saved as your **Webhook URL** in Razorpay Dashboard:
      `https://abc123.ngrok-free.app/webhooks/razorpay`
- [ ] Events subscribed in Razorpay: `payment.failed` AND `payment.captured`
- [ ] Dashboard is open in browser: `http://localhost:8000/dashboard`
- [ ] `reclaim/eval/output/scoreboard.json` exists (run eval first if not)

---

## Demo Flow (7 steps, ~5 minutes)

### Step 1 — Show the dashboard (30 seconds)
1. Open `http://localhost:8000/dashboard`
2. Walk through the header metrics:
   - "At-Risk Revenue" card
   - "Recovery Rate" card
   - "Policy Violations: 0"
3. Say: *"Every number here comes from a real causal evaluation — not a simulation."*

---

### Step 2 — Trigger a real payment failure via Razorpay Test API (1 minute)

Open a second terminal and run:

```bash
python scripts/trigger_test_payment.py
```

This script uses the real Razorpay Test API to create a payment order and
**intentionally** use a failing test card (card number `4111111111111111`,
which Razorpay's test mode guarantees will fail with `INSUFFICIENT_FUNDS`).

Expected terminal output:
```
[Razorpay] Created order: order_XXXXXXXXXXXX
[Razorpay] Payment attempt: pay_XXXXXXXXXXXX
[Razorpay] Payment status: failed
[Razorpay] Webhook will be dispatched by Razorpay in ~5-30 seconds...
```

---

### Step 3 — Observe the webhook arrive (30 seconds)

Watch the application terminal (where `python main.py` is running).
You will see live log lines within 5-30 seconds of step 2:

```
INFO  reclaim.ingestion.router  Received payment.failed webhook event_id=payment.failed:pay_XXXXXXXXXXXX
INFO  reclaim.ingestion.processor  Processing event_id=payment.failed:pay_XXXXXXXXXXXX
INFO  reclaim.diagnosis.classifier  Heuristic classify: cause=INSUFFICIENT_FUNDS confidence=0.82
INFO  reclaim.policy.rules  Policy verdict: ALLOW channel=whatsapp tier=AUTO
INFO  reclaim.orchestrator.executors.dispatcher  Dispatching ALLOW → whatsapp for pay_XXXXXXXXXXXX
INFO  reclaim.ingestion.processor  Pipeline complete: state_transition failed → nudged
```

**This proves**: The live Razorpay webhook hit the real endpoint, not a simulator.

---

### Step 4 — Show the audit log in the dashboard (30 seconds)

1. Click the **Events** tab in the dashboard
2. Find the `pay_XXXXXXXXXXXX` row — it will show:
   - Status: `nudged` (green)
   - Diagnosed cause: `INSUFFICIENT_FUNDS`
   - Policy decision: `ALLOW`
   - Channel dispatched: `whatsapp`
3. Click the row to expand the audit trail. You will see 5 entries:
   ```
   system         recovery_state_created
   diagnosis_engine  diagnosed:INSUFFICIENT_FUNDS
   policy_engine  policy_verdict:ALLOW
   orchestrator   dispatch:whatsapp
   system         state_transition: failed → nudged
   ```

**Say**: *"Five stages, all real, all audit-logged with timestamps."*

---

### Step 5 — Trigger a recovery (payment.captured) (1 minute)

Run in terminal:
```bash
python scripts/trigger_test_capture.py --payment-id pay_XXXXXXXXXXXX
```

Replace `pay_XXXXXXXXXXXX` with the ID from Step 2.

Expected app log:
```
INFO  reclaim.ingestion.router  Received payment.captured for pay_XXXXXXXXXXXX
INFO  reclaim.outcome_observer  Recovery confirmed: revenue recovered = ₹1500
INFO  reclaim.ingestion.processor  state_transition: nudged → recovered
```

---

### Step 6 — Show recovery in dashboard (30 seconds)

1. Refresh the Events tab. The row now shows status: `recovered` (gold/green)
2. The "Recovered Revenue" card at the top has incremented by ₹1,500
3. Click "Policy Lab" tab — the scoreboard now shows 1 additional recovered event

**Say**: *"The outcome observer closed the loop — from failure to recovery,
zero manual intervention."*

---

### Step 7 — Show policy violation count (15 seconds)

Return to the dashboard home. "Policy Violations" counter still reads **0**.

**Say**: *"Even with live transactions, the policy engine's hard-coded guardrails
guarantee zero violations — no opt-out contacts, no discount ceiling breaches,
no budget overruns."*

---

## What to Say if Asked "Is This Real?"

Point to:
1. The ngrok URL in the Razorpay Dashboard showing the exact HTTPS endpoint
2. The `pay_` ID — look it up live at `dashboard.razorpay.com/app/payments`
   in test mode. The status will show `failed`.
3. The application terminal logs showing the real timestamp of the webhook arrival

---

## If the Webhook Doesn't Arrive

**Most likely cause**: ngrok URL expired or webhook URL in Razorpay Dashboard
is stale.

Fix:
```bash
# Restart ngrok and update Razorpay Dashboard webhook URL
ngrok http 8000
# Then paste the new URL into Razorpay Dashboard → Settings → Webhooks
```

Alternatively: use the `/test/simulate-webhook` endpoint to show the pipeline
without the live network dependency — but be transparent: *"This is the same
pipeline wired to the live endpoint; ngrok is having a connectivity issue."*

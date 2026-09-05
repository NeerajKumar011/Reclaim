# RECLAIM — 5-Minute Presentation Script & Live Demo Playbook

**Target Presentation Time**: Exactly 5:00 minutes  
**Presenter**: Live demo presenter with RECLAIM Dashboard open at `http://localhost:8000/dashboard`

---

## Pitch Timeline Breakdown

```
[0:00 - 1:00] Minute 1: The Multi-Million Rupee Leak & Problem
[1:00 - 2:00] Minute 2: Intelligent Restraint — The Power of BLOCKing Nudges
[2:00 - 3:00] Minute 3: Conversational Intelligence & Promise-to-Pay Extraction
[3:00 - 4:00] Minute 4: Counterfactual Simulation & Policy Lab Demo
[4:00 - 5:00] Minute 5: Scoreboard Verification & Closing Statement
```

---

## Minute 1: The Problem (0:00 – 1:00)

**[Screen: Show RECLAIM Command Center — Headline KPI Cards]**

> *"Good morning, judges. Every single day, Indian D2C brands and SaaS platforms lose 15% to 25% of their top-line revenue to failed payments and cart abandonments.
> 
> Most tools solve this with brute-force spam: sending 5 automated SMS messages and 3 WhatsApp blasts to every customer who drops off. The result? High customer fatigue, damaged brand reputation, and high channel costs for money that would have recovered on its own anyway.
> 
> In our canonical held-out evaluation of 1,500 real-world payment events from `test_holdout.jsonl`, merchants faced **₹1.91 Crores (₹1,91,47,346.23)** in revenue at risk.
> 
> Meet **RECLAIM** — an Autonomous Revenue Recovery Engine that treats revenue recovery not as a spam campaign, but as a dynamic decision problem."*

---

## Minute 2: Live Failure & Intelligent Restraint (1:00 – 2:00)

**[Screen: Switch to Recovery Queue Tab -> Click on a BLOCK row]**

> *"Let’s look at a live failure event happening right now.
> 
> Customer `cust_bank_down` just experienced a payment failure of ₹7,500. A standard dunning tool would immediately fire off an SMS nudge. 
> 
> But look at what RECLAIM did: our diagnosis engine identified the root cause as `BANK_RAIL_DOWN` (an HDFC bank gateway downtime). Because this is a transient infrastructure issue, our deterministic policy engine rendered a decision of **BLOCK** with zero contact.
> 
> Why? Because sending an SMS when the bank rail is down confuses the customer and wastes money. The policy log explicitly states: *'Bank rail downtime detected; transient issue will self-resolve. Intervention blocked to prevent customer fatigue.'*
> 
> RECLAIM knows when NOT to act. That is intelligent restraint."*

---

## Minute 3: Promise-to-Pay Extraction (2:00 – 3:00)

**[Screen: Open Customer Timeline Modal for `cust_hinglish_042`]**

> *"Now let's see what happens when we DO interact with a customer.
> 
> When a customer responds in natural Hinglish—for example: *'Haan bhai, salary parso aayegi tab pay kar dunga'* ('Yes brother, salary comes day after tomorrow, will pay then')—standard bots fail or keep sending daily reminders.
> 
> RECLAIM’s Promise Extractor parses the intent, extracts the target payment date, updates `RecoveryMemory`, and transitions the state to `promised`.
> 
> All automated nudges are immediately suppressed until 24 hours after the promised date. Look at the vertical audit log timeline: every action, reason, and state transition is 100% transparent and traceable."*

---

## Minute 4: Recovery & Counterfactual Policy Lab (3:00 – 4:00)

**[Screen: Switch to Policy Lab Simulator Tab]**

> *"Now, how do we prove RECLAIM actually performs better than industry standards?
> 
> We built a **Counterfactual Policy Simulator** that replays our held-out evaluation dataset (recorded in `reclaim/eval/output/scoreboard.json`, N=1500, seed=42) across the full policy benchmark:
> 
> 1. **NO-ACTION**: Recovers ₹33,76,575.13 (17.63% natural self-resolution).
> 2. **FIXED-RETRY (SMS Blast)**: Recovers ₹70,96,752.83 (37.06%), contacting all 1,500 customers indiscriminately.
> 3. **FIXED-DUNNING (Escalation Ladder)**: Recovers ₹77,63,251.45 (40.54%), but with highest intervention costs (₹750.00).
> 4. **RAZORPAY-SMART-RETRY**: Recovers ₹53,18,906.07 (27.78% native payment link retry with 0 telecom cost, but lacking omnichannel coordination or timing intelligence).
> 5. **RECLAIM (Autonomous Engine)**: Recovers **₹72,22,091.33 (37.72% Recovery Rate)** with **₹38,45,516.20 incremental uplift**, while contacting **only 852 customers (43.2% fewer contacts than brute-force 1,500)** and achieving the **highest revenue yield per contact (₹8,476.63/contact)** and **lowest cost per recovered rupee (₹0.000033)**.
> 
> By skipping unnecessary contacts and selecting the optimal channel per failure cause, RECLAIM maximizes recovery yield and achieves the lowest intervention cost per rupee recovered among active outreach policies."*

---

## Minute 5: Scoreboard & Closing (4:00 – 5:00)

**[Screen: Return to Full Scoreboard Comparison Table]**

> *"Let’s look at the headline numbers on our scoreboard:
> 
> - **At-Risk Revenue**: ₹1,91,47,346.23 (N=1,500 held-out test events)
> - **Revenue Recovered**: **₹72,22,091.33** (37.72% recovery rate)
> - **Incremental Recovery Uplift**: **₹38,45,516.20**
> - **Contacts Made**: 852 (43.2% reduction vs brute-force 1,500)
> - **Policy Violations**: **EXACTLY ZERO**.
> 
> Because financial authorization (`max_discount_paise`, payment link generation) is strictly separated from generative copy synthesis, RECLAIM guarantees 0 discount hallucinations and 0 policy violations.
> 
> We don't optimize for messages sent. We optimize for **rupees recovered per intervention**—and we can prove it against industry baselines on a held-out dataset the model never saw.
> 
> Thank you."*

---

## Presenter Rehearsal Checklist

- [x] Tested timing with stopwatch (Target: 4:45 to 5:00 min).
- [x] Verified dashboard URLs load instantly at `http://localhost:8000/dashboard`.
- [x] Verified `scoreboard.json` numbers match `test_holdout.jsonl` (N=1500, seed=42).
- [x] Verified Customer Timeline displays full untruncated reason strings.



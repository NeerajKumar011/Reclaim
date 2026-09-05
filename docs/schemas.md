# RECLAIM — Data Schemas

> This document describes all database tables and the normalized event contract.
> A teammate building Phase 2 (diagnosis) should be able to work from this
> document without reading the code.

---

## Database Tables

### 1. `events`

Stores every webhook event received. The **single source of truth** for what happened.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Auto-generated primary key |
| `razorpay_event_id` | VARCHAR(255) | UNIQUE, NOT NULL, INDEXED | **Idempotency key** — derived from the event name + payment/order entity ID. If a webhook is delivered twice, the second insert is rejected. |
| `event_type` | ENUM | NOT NULL | One of: `payment_failed`, `payment_captured`, `order_paid`, `subscription_charged`, `subscription_halted`, `payment_link_paid`, `checkout_abandoned`, `invoice_overdue` |
| `raw_payload` | JSONB | NOT NULL | Full original webhook body, stored verbatim for auditability |
| `normalized_payload` | JSONB | NULLABLE | Normalized to the `RevenueEvent` contract (see below). Null if normalization failed. |
| `received_at` | TIMESTAMP WITH TZ | NOT NULL | When we received the webhook (UTC) |
| `processed_at` | TIMESTAMP WITH TZ | NULLABLE | When processing completed (null if not yet processed) |
| `processing_status` | ENUM | NOT NULL, DEFAULT `pending` | One of: `pending`, `processed`, `ignored_duplicate`, `error` |

---

### 2. `customers`

Stores customer contact information. Created or updated when processing webhooks.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Auto-generated primary key (this is the **internal** customer ID) |
| `razorpay_customer_id` | VARCHAR(255) | NULLABLE, INDEXED | Razorpay's `cust_xxx` ID, if available |
| `name` | VARCHAR(255) | NULLABLE | Customer name |
| `email` | VARCHAR(255) | NULLABLE, INDEXED | Email address (used as fallback lookup key) |
| `phone` | VARCHAR(50) | NULLABLE | Phone number |
| `preferred_language` | VARCHAR(10) | NOT NULL, DEFAULT `"en"` | Language for communications |
| `opted_out` | BOOLEAN | NOT NULL, DEFAULT `false` | If true, **do not send** any recovery communications |
| `created_at` | TIMESTAMP WITH TZ | NOT NULL | When the customer record was created |

---

### 3. `recovery_state`

Tracks the recovery lifecycle for a failed payment. One row per failure event.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Auto-generated primary key |
| `customer_id` | UUID | FK → `customers.id`, NOT NULL | The customer this recovery case belongs to |
| `event_id` | UUID | FK → `events.id`, NOT NULL | The originating event that created this case |
| `amount` | NUMERIC(12,2) | NOT NULL | Amount in **paise** (100 paise = ₹1) |
| `state` | ENUM | NOT NULL | Current state (see state machine below) |
| `updated_at` | TIMESTAMP WITH TZ | NOT NULL | Last state change timestamp |

#### State machine

```
                    ┌──────────┐
                    │  failed  │ ← initial state (payment_failed / checkout_abandoned / invoice_overdue)
                    └────┬─────┘
                         │
                    ┌────▼─────┐
                    │ waiting  │ ← queued for recovery action (set by policy engine)
                    └────┬─────┘
                         │
                    ┌────▼─────┐
                    │  nudged  │ ← recovery message sent (set by orchestrator)
                    └────┬─────┘
                         │
                    ┌────▼──────┐
                    │ promised  │ ← customer acknowledged they'll pay (optional)
                    └────┬──────┘
                         │
              ┌──────────▼──────────┐
              │     recovered       │ ← payment captured! (terminal success state)
              └─────────────────────┘

              ┌─────────────────────┐
              │     escalated       │ ← all automated recovery exhausted (terminal)
              └─────────────────────┘

              ┌─────────────────────┐
              │     opted_out       │ ← customer opted out of communications (terminal)
              └─────────────────────┘
```

**Out-of-order handling rules:**
- If a `payment_captured` arrives for a state in `{failed, waiting, nudged, promised}` → transition to `recovered`
- If a `payment_failed` arrives AFTER a `payment_captured` (state is `recovered`) → **do NOT reopen**. Log to `audit_log` with reason `"stale event ignored, payment already captured"`.

---

### 4. `audit_log`

**Every** state transition, decision, and notable event is recorded here with an explanation.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Auto-generated primary key |
| `event_id` | UUID | FK → `events.id`, NULLABLE | The event that triggered this log entry |
| `recovery_state_id` | UUID | FK → `recovery_state.id`, NULLABLE | The recovery case affected |
| `actor` | VARCHAR(50) | NOT NULL | Who did this: `system`, `diagnosis_engine`, `policy_engine`, `orchestrator`, `human` |
| `action` | TEXT | NOT NULL | What happened (e.g. `state_transition: failed → recovered`) |
| `reason` | TEXT | NOT NULL | **WHY** it happened — this field is critical for debugging and required on every entry |
| `metadata` | JSONB | NULLABLE | Any additional structured context |
| `created_at` | TIMESTAMP WITH TZ | NOT NULL | When this log entry was created |

---

### 5. `recovery_memory`

Stores persistent behavioral profiles and response memory per customer.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | Auto-generated primary key |
| `customer_id` | UUID | FK → `customers.id`, UNIQUE, NOT NULL | Customer profile reference |
| `typical_payment_day_of_month` | INT | NULLABLE | Day of month (1..31) when customer typically pays |
| `preferred_channel` | VARCHAR(50) | NULLABLE | Best-converting recovery channel (`whatsapp`, `sms`, `voice_call`) |
| `preferred_language` | VARCHAR(10) | NOT NULL, DEFAULT `"en"` | Language preference |
| `historical_response_rate` | FLOAT | NOT NULL, DEFAULT `0.0` | Ratio of past recovered cases vs total cases (0.0 to 1.0) |
| `avg_response_latency_hours` | FLOAT | NULLABLE | Mean elapsed hours from failure to recovery capture |
| `fatigue_score_last_computed` | FLOAT | NOT NULL, DEFAULT `0.0` | Exponentially-decayed communication fatigue score (0.0 to 1.0) |
| `last_updated` | TIMESTAMP WITH TZ | NOT NULL | Last memory update timestamp |

> **DATA PROVENANCE GUARANTEE**:
> All fields in `recovery_memory` are derived strictly from structured historical payment events (via `outcome_observer.py`) and explicit customer promise intents (via `promise_extractor.py`). The LLM is NEVER permitted to hallucinate or directly write to `recovery_memory`.

---

## RevenueEvent — Normalized Payload Contract

Every event type (Razorpay-native and synthetic) is normalized to this shape before storage in `events.normalized_payload`. Validated by Pydantic.

```json
{
  "event_id": "string — matches razorpay_event_id on the events table",
  "event_category": "payment_failure | cart_abandonment | invoice_overdue | payment_success",
  "customer_id": "string — internal customer UUID (from the customers table)",
  "amount": "decimal — amount in PAISE (100 paise = ₹1)",
  "currency": "string — ISO 4217 currency code, default 'INR'",
  "failure_reason_raw": "string | null — raw Razorpay error code (e.g. 'BAD_REQUEST_ERROR')",
  "occurred_at": "ISO 8601 timestamp — when the event occurred (UTC)",
  "source_metadata": {
    "payment_id": "string | null",
    "order_id": "string | null",
    "invoice_id": "string | null",
    "subscription_id": "string | null",
    "method": "string | null — payment method (upi, card, netbanking, etc.)",
    "error_code": "string | null",
    "error_description": "string | null",
    "error_reason": "string | null"
  }
}
```

### Field details

| Field | Type | Required | Description |
|---|---|---|---|
| `event_id` | string | ✅ | Unique event identifier, used as idempotency key |
| `event_category` | enum | ✅ | High-level classification. `payment_failure` for failed payments, `cart_abandonment` for abandoned checkouts, `invoice_overdue` for unpaid invoices, `payment_success` for captured/paid events |
| `customer_id` | string | ✅ | Internal UUID from the `customers` table (NOT the Razorpay customer ID) |
| `amount` | decimal | ✅ | Amount in **paise**. Example: ₹500.00 = `50000` |
| `currency` | string | ✅ | ISO 4217 code. Default: `INR` |
| `failure_reason_raw` | string | ❌ | Raw error code from Razorpay. Null for success events and synthetic events without errors |
| `occurred_at` | ISO 8601 | ✅ | UTC timestamp of when the original event happened |
| `source_metadata` | object | ✅ | Bag of additional context. Keys vary by event type. Always present (may be `{}`) |

---

## Event Types and Their Sources

| Event Type | Source | Normalizer | Notes |
|---|---|---|---|
| `payment_failed` | Razorpay webhook | `normalize_payment_failed` | Core recovery trigger |
| `payment_captured` | Razorpay webhook | `normalize_payment_captured` | Signals recovery success |
| `order_paid` | Razorpay webhook | `normalize_order_paid` | Alternative success signal |
| `subscription_charged` | Razorpay webhook | Generic normalizer | Subscription payment success |
| `subscription_halted` | Razorpay webhook | Generic normalizer | Subscription failure trigger |
| `payment_link_paid` | Razorpay webhook | Generic normalizer | Recovery link was paid |
| `checkout_abandoned` | **Synthetic** (our system) | `normalize_synthetic` | Not a native Razorpay event |
| `invoice_overdue` | **Synthetic** (our system) | `normalize_synthetic` | Not a native Razorpay event |

---

## Example Payloads

### Razorpay `payment.failed` webhook

```json
{
  "entity": "event",
  "account_id": "acc_test123",
  "event": "payment.failed",
  "contains": ["payment"],
  "payload": {
    "payment": {
      "entity": {
        "id": "pay_ABCDEFGHIJ",
        "amount": 50000,
        "currency": "INR",
        "status": "failed",
        "method": "upi",
        "order_id": "order_XYZ123",
        "email": "customer@example.com",
        "contact": "+919876543210",
        "error_code": "BAD_REQUEST_ERROR",
        "error_description": "Payment processing failed because of incorrect OTP",
        "error_reason": "payment_failed",
        "created_at": 1691735748
      }
    }
  },
  "created_at": 1691735750
}
```

### Resulting normalized `RevenueEvent`

```json
{
  "event_id": "payment.failed:pay_ABCDEFGHIJ",
  "event_category": "payment_failure",
  "customer_id": "550e8400-e29b-41d4-a716-446655440000",
  "amount": 50000,
  "currency": "INR",
  "failure_reason_raw": "BAD_REQUEST_ERROR",
  "occurred_at": "2023-08-11T06:55:50+00:00",
  "source_metadata": {
    "payment_id": "pay_ABCDEFGHIJ",
    "order_id": "order_XYZ123",
    "method": "upi",
    "error_code": "BAD_REQUEST_ERROR",
    "error_description": "Payment processing failed because of incorrect OTP",
    "error_reason": "payment_failed"
  }
}
```

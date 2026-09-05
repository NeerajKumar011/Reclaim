"""Causal Configuration for RECLAIM Synthetic Data Generation.

This file contains all probability curves, causal weights, and adjustment factors
used by the synthetic data generator.

IMPORTANT: All values here are PLACEHOLDERS intended for initial testing.
They must be reviewed and justified by the domain/risk team before Phase 5 evaluation.
"""

from typing import Dict

# ---------------------------------------------------------------------------
# 1. Base recovery probability by root cause
# ---------------------------------------------------------------------------
# Recovery probability by cause, before customer-history adjustment.
BASE_RECOVERY_PROBABILITY: Dict[str, float] = {
    "INSUFFICIENT_FUNDS": 0.55,   # High re-attempt likelihood when customer adds funds or on payday
    "OTP_TIMEOUT": 0.80,          # Transient session friction with high underlying purchase intent
    "BANK_RAIL_DOWN": 0.15,       # Infrastructure downtime; often self-resolves or customer changes instrument
    "AUTH_ABORT": 0.40,           # Customer hesitation or auth friction during checkout
    "GENUINE_ABANDON": 0.10,      # Low purchase intent window-shopping
    "B2B_CASH_CONSTRAINED": 0.65, # Working capital delay; recovers when buyer cash flow clears
    "B2B_DISPUTE": 0.20,          # Commercial discrepancy requiring invoice amendment
}

# ---------------------------------------------------------------------------
# 2. Cause probability distribution by event category
# ---------------------------------------------------------------------------
# Probability of each root cause given an event category.
# Values in each inner dict sum to 1.0.
EVENT_CATEGORY_CAUSE_PROBABILITIES: Dict[str, Dict[str, float]] = {
    "payment_failure": {
        "INSUFFICIENT_FUNDS": 0.40,  # Leading cause of retail card/UPI payment failure
        "OTP_TIMEOUT": 0.30,         # SMS/network latency and OTP expiry
        "BANK_RAIL_DOWN": 0.15,      # NPCI/core banking gateway outages
        "AUTH_ABORT": 0.15,          # Customer aborted 3DS/biometric screen
    },
    "cart_abandonment": {
        "GENUINE_ABANDON": 0.60,     # Price comparison / browsing drop-off
        "AUTH_ABORT": 0.25,          # Dropped at payment instrument selection
        "OTP_TIMEOUT": 0.15,         # Failed or delayed OTP during checkout
    },
    "invoice_overdue": {
        "B2B_CASH_CONSTRAINED": 0.50, # Standard 30/60-day enterprise billing delay
        "B2B_DISPUTE": 0.30,          # Purchase order or line-item dispute
        "INSUFFICIENT_FUNDS": 0.20,   # Account balance shortfall on direct debit
    },
}

# ---------------------------------------------------------------------------
# 3. Factor: Amount Buckets (in paise)
# ---------------------------------------------------------------------------
# Recovery likelihood multiplier based on transaction size.
AMOUNT_BUCKET_FACTORS: Dict[str, float] = {
    "micro": 1.15,     # < ₹500 (50,000 paise): low ticket size, high impulse recovery
    "small": 1.05,     # ₹500 - ₹2,000 (50,000 - 200,000 paise): standard retail
    "medium": 1.00,    # ₹2,000 - ₹10,000 (200,000 - 1,000,000 paise): baseline
    "large": 0.85,     # ₹10,000 - ₹50,000 (1,000,000 - 5,000,000 paise): higher scrutiny
    "enterprise": 0.70,# > ₹50,000 (> 5,000,000 paise): multi-level approval needed
}

def get_amount_bucket(amount_paise: int) -> str:
    """Classify an amount in paise into a size bucket."""
    if amount_paise < 50_000:
        return "micro"
    elif amount_paise < 200_000:
        return "small"
    elif amount_paise < 1_000_000:
        return "medium"
    elif amount_paise < 5_000_000:
        return "large"
    else:
        return "enterprise"

# ---------------------------------------------------------------------------
# 4. Factor: Day of Month (Salary Window)
# ---------------------------------------------------------------------------
# Salary window: 28th to 5th of each month sees significant liquidity surge.
DAY_OF_MONTH_FACTORS: Dict[str, float] = {
    "salary_window": 1.25,   # Days 28..31 and 1..5: increased liquidity for funds-related failures
    "mid_month": 0.90,       # Days 6..27: standard liquidity
}

def get_day_of_month_factor(day: int, cause: str) -> float:
    """Return multiplier for day of month, applied only to INSUFFICIENT_FUNDS."""
    if cause == "INSUFFICIENT_FUNDS":
        if day >= 28 or day <= 5:
            return DAY_OF_MONTH_FACTORS["salary_window"]
        else:
            return DAY_OF_MONTH_FACTORS["mid_month"]
    return 1.0

# ---------------------------------------------------------------------------
# 5. Factor: Prior Retry Count
# ---------------------------------------------------------------------------
# Each failed prior attempt degrades recovery probability.
PRIOR_RETRY_FACTORS: Dict[int, float] = {
    0: 1.00,  # Initial failure (fresh attempt)
    1: 0.80,  # 1st failed retry
    2: 0.55,  # 2nd failed retry
    3: 0.30,  # 3rd failed retry or more
}

def get_prior_retry_factor(retry_count: int) -> float:
    """Return multiplier for number of prior failed retries."""
    return PRIOR_RETRY_FACTORS.get(retry_count, 0.20)


get_retry_factor = get_prior_retry_factor


# ---------------------------------------------------------------------------
# 6. Factor: Customer Segment
# ---------------------------------------------------------------------------
CUSTOMER_SEGMENT_FACTORS: Dict[str, float] = {
    "new": 0.85,        # First-time customer: lower brand loyalty
    "returning": 1.15,  # Repeat customer: proven purchase intent
    "vip": 1.30,        # High-LTV customer: high willingness to complete
}

# ---------------------------------------------------------------------------
# 7. Factor: Historical Response Rate
# ---------------------------------------------------------------------------
HISTORICAL_RESPONSE_FACTORS: Dict[str, float] = {
    "high": 1.25,    # Active clicker/responder
    "medium": 1.00,  # Average engagement
    "low": 0.60,     # Frequent non-responder
    "none": 0.80,    # No communication history available
}

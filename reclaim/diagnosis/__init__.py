"""Diagnosis engine — classifies failures and determines recovery strategy.

TODO: Phase 2 — Implement:
  - LLM-powered failure classification (categorize Razorpay error codes into
    actionable buckets: card_issue, bank_issue, insufficient_funds, etc.)
  - Root cause analysis using payment history and customer context
  - Recovery recommendation engine (suggest: retry, nudge, escalate, give up)
  - Confidence scoring on diagnosis
  - Integration with the policy engine to feed recommendations
"""

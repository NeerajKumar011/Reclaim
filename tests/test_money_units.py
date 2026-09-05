"""Tests for Money Unit Correctness across RECLAIM.

Verifies:
1. Smallest unit representation (paise: integer).
2. Formatted Indian Rupee (INR) representation with Lakh/Crore grouping.
3. Conversions: paise <-> rupees.
4. Specific test fixtures: ₹1, ₹10, ₹299, ₹6,914.53, ₹35,000, ₹35,00,000, ₹4,999, ₹7,500, zero, large amounts.
"""

from decimal import Decimal
import pytest
from reclaim.common.money import paise_to_rupees, rupees_to_paise, format_inr, format_audit_case_reason


def test_paise_to_rupees():
    assert paise_to_rupees(100) == Decimal("1.00")
    assert paise_to_rupees(1000) == Decimal("10.00")
    assert paise_to_rupees(29900) == Decimal("299.00")
    assert paise_to_rupees(499900) == Decimal("4999.00")
    assert paise_to_rupees(750000) == Decimal("7500.00")
    assert paise_to_rupees(691453) == Decimal("6914.53")
    assert paise_to_rupees(3500000) == Decimal("35000.00")
    assert paise_to_rupees(350000000) == Decimal("3500000.00")
    assert paise_to_rupees(0) == Decimal("0.00")


def test_rupees_to_paise():
    assert rupees_to_paise(1) == 100
    assert rupees_to_paise(10) == 1000
    assert rupees_to_paise(299) == 29900
    assert rupees_to_paise(4999) == 499900
    assert rupees_to_paise(7500) == 750000
    assert rupees_to_paise(Decimal("6914.53")) == 691453
    assert rupees_to_paise(35000) == 3500000
    assert rupees_to_paise(3500000) == 350000000
    assert rupees_to_paise(0) == 0


def test_format_inr_canonical_cases():
    # 1. Re. 1
    assert format_inr(100) == "₹1.00"
    
    # 2. Rs. 10
    assert format_inr(1000) == "₹10.00"
    
    # 3. Rs. 299
    assert format_inr(29900) == "₹299.00"
    
    # 4. Rs. 4,999 (Golden Demo OTP recovery)
    assert format_inr(499900) == "₹4,999.00"
    
    # 5. Rs. 7,500 (Golden Demo Bank rail down)
    assert format_inr(750000) == "₹7,500.00"
    
    # 6. Rs. 6,914.53 (Audit queue merchant display)
    assert format_inr(691453) == "₹6,914.53"
    
    # 7. Rs. 35,000 (Invoice standard)
    assert format_inr(3500000) == "₹35,000.00"
    
    # 8. Rs. 35,00,000 (35 Lakhs Enterprise B2B invoice)
    assert format_inr(350000000) == "₹35,00,000.00"
    
    # 9. Zero
    assert format_inr(0) == "₹0.00"
    
    # 10. Large amount (Benchmark total at risk ~ Rs. 1.91 Cr)
    assert format_inr(1914734623) == "₹1,91,47,346.23"


def test_format_audit_case_reason():
    assert format_audit_case_reason("payment_failed", 691453) == "Payment failed — recovery case created for ₹6,914.53"
    assert format_audit_case_reason("invoice_overdue", 350000000) == "Invoice overdue — recovery case created for ₹35,00,000.00"
    assert format_audit_case_reason("checkout_abandoned", 499900) == "Checkout abandoned — recovery case created for ₹4,999.00"

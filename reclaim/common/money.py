"""Money unit utilities for RECLAIM.

RECLAIM follows the Razorpay monetary convention:
- INTERNAL: integer smallest-unit representation (paise, where 100 paise = ₹1).
- USER-FACING: formatted Indian Rupee (INR) string using Indian numbering (Lakhs, Crores).
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Union

MoneyAmount = Union[int, float, Decimal, str]


def paise_to_rupees(paise: MoneyAmount) -> Decimal:
    """Convert amount in paise to Decimal rupees."""
    if paise is None:
        return Decimal("0.00")
    d = Decimal(str(paise))
    return (d / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def rupees_to_paise(rupees: MoneyAmount) -> int:
    """Convert amount in rupees to integer paise."""
    if rupees is None:
        return 0
    d = Decimal(str(rupees))
    return int((d * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_inr(
    paise: MoneyAmount,
    include_symbol: bool = True,
    always_show_decimals: bool = True,
) -> str:
    """Format an amount in paise into an Indian Rupee string with proper Lakh/Crore grouping.

    Examples:
        format_inr(100) -> "₹1.00"
        format_inr(1000) -> "₹10.00"
        format_inr(29900) -> "₹299.00"
        format_inr(499900) -> "₹4,999.00"
        format_inr(750000) -> "₹7,500.00"
        format_inr(691453) -> "₹6,914.53"
        format_inr(3500000) -> "₹35,000.00"
        format_inr(350000000) -> "₹35,00,000.00"
        format_inr(1914734623) -> "₹1,91,47,346.23"
        format_inr(0) -> "₹0.00"
    """
    if paise is None:
        paise = 0
    
    val_paise = Decimal(str(paise))
    is_negative = val_paise < 0
    val_paise = abs(val_paise)
    
    rupees_dec = val_paise / Decimal("100")
    int_part = int(rupees_dec)
    fractional_part = int((val_paise % Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    
    # Format integer part with Indian grouping: last 3 digits, then groups of 2
    s_int = str(int_part)
    if len(s_int) <= 3:
        formatted_int = s_int
    else:
        last3 = s_int[-3:]
        rest = s_int[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted_int = ",".join(groups) + "," + last3
    
    if always_show_decimals or fractional_part > 0:
        formatted_num = f"{formatted_int}.{fractional_part:02d}"
    else:
        formatted_num = formatted_int
        
    prefix = "-" if is_negative else ""
    symbol = "₹" if include_symbol else ""
    return f"{prefix}{symbol}{formatted_num}"


def format_audit_case_reason(event_name: str, amount_paise: MoneyAmount) -> str:
    """Create standard merchant-facing audit reason for case creation.

    Example:
        format_audit_case_reason("Payment failed", 691453)
        -> "Payment failed — recovery case created for ₹6,914.53"
    """
    formatted = format_inr(amount_paise)
    clean_event = event_name.replace("_", " ").strip().capitalize()
    return f"{clean_event} — recovery case created for {formatted}"

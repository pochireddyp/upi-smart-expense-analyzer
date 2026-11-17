"""Money handling module for UPI Smart Expense Analyzer.

This module provides exact financial calculations using Python's built-in
`decimal.Decimal`. It enforces strict rules against floating-point arithmetic
to eliminate rounding errors and reconciliation discrepancies.

Key Invariants:
1. All amounts are represented as `Decimal` in memory.
2. Amounts are stored as integer minor units (paise: ₹1 = 100 paise) in SQLite.
3. Rounding uses `ROUND_HALF_UP` to two decimal places.
4. Float values are strictly rejected at boundaries.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Iterable, Union

# Constant representing two decimal places (1 paisa = ₹0.01)
PAISA_EXPONENT = Decimal("0.01")
PAISE_PER_RUPEE = Decimal("100")

# Valid input types for money conversion (strictly excluding float)
MoneyInput = Union[str, int, Decimal]


def to_money(value: MoneyInput) -> Decimal:
    """Convert a string, integer, or Decimal to a normalized 2-decimal Money Decimal.

    Floating-point numbers (`float`) are explicitly rejected to prevent
    hidden inaccuracies before they enter the system.

    Args:
        value: Amount as a string (e.g., "499.50"), integer (e.g., 500), or Decimal.

    Returns:
        Decimal: Normalized Decimal quantized to two decimal places.

    Raises:
        TypeError: If a `float` is passed.
        ValueError: If a string cannot be parsed into a valid financial number.

    Examples:
        >>> to_money("499.5")
        Decimal('499.50')
        >>> to_money(100)
        Decimal('100.00')
    """
    if isinstance(value, float):
        raise TypeError(
            f"Float values ({value}) are strictly prohibited in financial calculations. "
            "Pass amounts as strings (e.g., '199.50') or integers to preserve precision."
        )

    try:
        dec = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"Cannot parse '{value}' as a valid monetary amount.") from exc

    if not dec.is_finite():
        raise ValueError(f"Amount must be a finite number, got '{value}'.")

    return quantize(dec)


def quantize(amount: Decimal) -> Decimal:
    """Round a Decimal amount to 2 decimal places using ROUND_HALF_UP.

    Args:
        amount: Raw Decimal value.

    Returns:
        Decimal: Value rounded to two decimal places.
    """
    return amount.quantize(PAISA_EXPONENT, rounding=ROUND_HALF_UP)


def to_paise(amount: MoneyInput) -> int:
    """Convert a rupee amount to integer paise for safe database storage.

    Example: ₹499.50 -> 49950 paise.

    Args:
        amount: Rupees as Decimal, string, or int.

    Returns:
        int: Value in paise (integer).
    """
    dec_amount = to_money(amount)
    paise_value = (dec_amount * PAISE_PER_RUPEE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(paise_value)


def from_paise(paise: int) -> Decimal:
    """Convert an integer paise value from the database back to a Decimal rupee amount.

    Example: 49950 paise -> Decimal('499.50').

    Args:
        paise: Amount in paise (e.g., from SQLite storage).

    Returns:
        Decimal: Rupee amount rounded to two decimal places.

    Raises:
        TypeError: If paise is not an integer.
    """
    if not isinstance(paise, int):
        raise TypeError(f"Paise must be an integer, got {type(paise).__name__}.")

    dec_paise = Decimal(paise)
    return quantize(dec_paise / PAISE_PER_RUPEE)


def sum_money(amounts: Iterable[MoneyInput]) -> Decimal:
    """Sum an iterable of monetary amounts with zero floating-point loss.

    Args:
        amounts: Iterable of amounts (strings, ints, or Decimals).

    Returns:
        Decimal: Total sum quantized to 2 decimal places.
    """
    total = Decimal("0.00")
    for item in amounts:
        total += to_money(item)
    return quantize(total)


def pct(part: MoneyInput, whole: MoneyInput) -> Decimal:
    """Calculate the percentage share (part / whole * 100) rounded to 2 decimal places.

    Safely handles division by zero by returning 0.00%.

    Args:
        part: The numerator amount.
        whole: The denominator (total) amount.

    Returns:
        Decimal: Percentage value (e.g., Decimal('34.50') for 34.5%).
    """
    dec_part = to_money(part)
    dec_whole = to_money(whole)

    if dec_whole == Decimal("0.00"):
        return Decimal("0.00")

    percentage = (dec_part / dec_whole) * Decimal("100")
    return quantize(percentage)


def format_inr(amount: MoneyInput, include_symbol: bool = True) -> str:
    """Format a monetary amount in Indian numbering format (lakhs and crores).

    Standard Indian grouping format:
    - Last 3 digits grouped together: hundreds.
    - Subsequent digits grouped in pairs of 2: thousands, lakhs, crores.
    Example: 1234567.89 -> '12,34,567.89' (or '₹ 12,34,567.89').

    Args:
        amount: Rupee amount as Decimal, string, or int.
        include_symbol: If True, prefixes with the Rupee symbol ('₹ ').

    Returns:
        str: Formatted currency string.

    Examples:
        >>> format_inr("1234567.89")
        '₹ 12,34,567.89'
        >>> format_inr("-450.00")
        '-₹ 450.00'
    """
    dec = to_money(amount)
    is_negative = dec < Decimal("0.00")
    abs_dec = abs(dec)

    # Split into integer and decimal string parts
    quantized_str = f"{abs_dec:.2f}"
    int_part, frac_part = quantized_str.split(".")

    # Format integer part with Indian comma groupings
    if len(int_part) <= 3:
        formatted_int = int_part
    else:
        # Take the last 3 digits
        last_three = int_part[-3:]
        remaining = int_part[:-3]
        
        # Group the remaining digits into pairs of 2 from right to left
        groups = []
        while len(remaining) > 2:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            groups.insert(0, remaining)
        
        formatted_int = ",".join(groups) + "," + last_three

    result = f"{formatted_int}.{frac_part}"

    if include_symbol:
        if is_negative:
            return f"-₹ {result}"
        return f"₹ {result}"

    if is_negative:
        return f"-{result}"
    return result

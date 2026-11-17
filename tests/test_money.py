"""Unit tests for modules/money.py.

Verifies that all money calculations, conversions, and formatters follow
strict decimal accuracy and reject floating-point inputs.
"""

from decimal import Decimal
import pytest

from modules.money import (
    to_money,
    to_paise,
    from_paise,
    quantize,
    sum_money,
    pct,
    format_inr,
)


class TestToMoney:
    """Tests for the to_money conversion helper."""

    def test_valid_string_conversion(self):
        """Test parsing valid strings into 2-decimal Decimals."""
        assert to_money("499.5") == Decimal("499.50")
        assert to_money("0") == Decimal("0.00")
        assert to_money("  1250.75  ") == Decimal("1250.75")
        assert to_money("1,250.75") == Decimal("1250.75")

    def test_valid_int_conversion(self):
        """Test parsing integers into 2-decimal Decimals."""
        assert to_money(500) == Decimal("500.00")
        assert to_money(0) == Decimal("0.00")
        assert to_money(-50) == Decimal("-50.00")

    def test_valid_decimal_conversion(self):
        """Test quantizing existing Decimals."""
        assert to_money(Decimal("10.5")) == Decimal("10.50")
        assert to_money(Decimal("10.555")) == Decimal("10.56")

    def test_rejects_float_inputs(self):
        """Ensure float inputs raise TypeError to prevent precision loss."""
        with pytest.raises(TypeError, match="Float values .* are strictly prohibited"):
            to_money(499.50)

        with pytest.raises(TypeError, match="Float values .* are strictly prohibited"):
            to_money(0.1 + 0.2)

    def test_invalid_string_raises_value_error(self):
        """Ensure malformed string inputs raise ValueError."""
        with pytest.raises(ValueError, match="Cannot parse 'abc'"):
            to_money("abc")

        with pytest.raises(ValueError):
            to_money("NaN")


class TestPaiseConversion:
    """Tests for SQLite paise <-> rupee conversions."""

    def test_to_paise_conversion(self):
        """Verify rupee to paise integer conversion."""
        assert to_paise("499.50") == 49950
        assert to_paise("0.00") == 0
        assert to_paise(100) == 10000
        assert to_paise("-25.50") == -2550

    def test_from_paise_conversion(self):
        """Verify paise integer to rupee Decimal conversion."""
        assert from_paise(49950) == Decimal("499.50")
        assert from_paise(0) == Decimal("0.00")
        assert from_paise(10000) == Decimal("100.00")
        assert from_paise(-2550) == Decimal("-25.50")

    def test_from_paise_rejects_non_integer(self):
        """Ensure from_paise enforces integer inputs."""
        with pytest.raises(TypeError, match="Paise must be an integer"):
            from_paise("49950")  # type: ignore


class TestRoundingAndSum:
    """Tests for precision math and rounding."""

    def test_quantize_round_half_up(self):
        """Verify ROUND_HALF_UP rounding rules."""
        assert quantize(Decimal("1.255")) == Decimal("1.26")
        assert quantize(Decimal("1.254")) == Decimal("1.25")
        assert quantize(Decimal("1.2550")) == Decimal("1.26")

    def test_sum_money_exact(self):
        """Verify exact summation eliminating floating-point drift."""
        # 0.1 + 0.2 in floats equals 0.30000000000000004
        # In Decimal money, it must be exact:
        amounts = ["0.10", "0.20", "0.30", "0.40"]
        assert sum_money(amounts) == Decimal("1.00")

    def test_sum_money_empty(self):
        """Verify empty iterable returns Decimal('0.00')."""
        assert sum_money([]) == Decimal("0.00")


class TestPercentages:
    """Tests for the pct percentage helper."""

    def test_pct_normal(self):
        """Verify valid percentage calculations."""
        assert pct("50", "100") == Decimal("50.00")
        assert pct("33.33", "100") == Decimal("33.33")
        assert pct("1", "3") == Decimal("33.33")

    def test_pct_zero_whole(self):
        """Verify safety against division by zero."""
        assert pct("50", "0") == Decimal("0.00")


class TestFormatINR:
    """Tests for Indian numbering format presentation."""

    def test_format_under_thousand(self):
        """Verify formatting for amounts under 1,000."""
        assert format_inr("499.50") == "₹ 499.50"
        assert format_inr("5") == "₹ 5.00"

    def test_format_thousands(self):
        """Verify formatting for thousands."""
        assert format_inr("1000") == "₹ 1,000.00"
        assert format_inr("52150.75") == "₹ 52,150.75"

    def test_format_lakhs_and_crores(self):
        """Verify Indian comma groupings for Lakhs and Crores."""
        assert format_inr("100000") == "₹ 1,00,000.00"
        assert format_inr("1234567.89") == "₹ 12,34,567.89"
        assert format_inr("10000000") == "₹ 1,00,00,000.00"

    def test_format_negative(self):
        """Verify formatting for negative amounts."""
        assert format_inr("-450.00") == "-₹ 450.00"
        assert format_inr("-1234567.89") == "-₹ 12,34,567.89"

    def test_format_without_symbol(self):
        """Verify formatting when include_symbol=False."""
        assert format_inr("1234567.89", include_symbol=False) == "12,34,567.89"
        assert format_inr("-450.00", include_symbol=False) == "-450.00"

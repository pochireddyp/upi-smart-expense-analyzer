"""Unit tests for Phase 9 recurring transaction and subscription detection."""

from datetime import date
from decimal import Decimal
import pandas as pd
import pytest

from modules.recurring import detect_recurring_transactions


class TestRecurringDetection:
    """Test suite for recurring subscription and mandate discovery."""

    def test_monthly_subscription_detection(self):
        """Verify monthly recurring charges with regular intervals are discovered."""
        rows = [
            {"date": date(2025, 11, 5), "merchant": "Netflix", "narration": "UPI/NETFLIX", "category": "Entertainment & Subs", "mode": "UPI", "type": "DEBIT", "amount": Decimal("649.00")},
            {"date": date(2025, 12, 5), "merchant": "Netflix", "narration": "UPI/NETFLIX", "category": "Entertainment & Subs", "mode": "UPI", "type": "DEBIT", "amount": Decimal("649.00")},
            {"date": date(2026, 1, 5), "merchant": "Netflix", "narration": "UPI/NETFLIX", "category": "Entertainment & Subs", "mode": "UPI", "type": "DEBIT", "amount": Decimal("649.00")},
        ]
        df = pd.DataFrame(rows)
        items = detect_recurring_transactions(df)

        assert len(items) == 1
        sub = items[0]
        assert sub.merchant == "Netflix"
        assert sub.cadence == "Monthly"
        assert sub.average_amount == Decimal("649.00")
        assert sub.estimated_annual_cost == Decimal("7788.00")
        assert sub.occurrences == 3

    def test_amount_variance_tolerance(self):
        """Verify recurring charges with minor price fluctuation (e.g. ₹1) are accepted."""
        rows = [
            {"date": date(2025, 11, 10), "merchant": "Spotify", "narration": "UPI/SPOTIFY", "category": "Entertainment & Subs", "mode": "UPI", "type": "DEBIT", "amount": Decimal("119.00")},
            {"date": date(2025, 12, 10), "merchant": "Spotify", "narration": "UPI/SPOTIFY", "category": "Entertainment & Subs", "mode": "UPI", "type": "DEBIT", "amount": Decimal("119.50")},
            {"date": date(2026, 1, 10), "merchant": "Spotify", "narration": "UPI/SPOTIFY", "category": "Entertainment & Subs", "mode": "UPI", "type": "DEBIT", "amount": Decimal("119.00")},
        ]
        df = pd.DataFrame(rows)
        items = detect_recurring_transactions(df)

        assert len(items) == 1
        assert items[0].merchant == "Spotify"
        assert items[0].cadence == "Monthly"

    def test_autopay_mandate_single_occurrence(self):
        """Verify a single debit with explicit AUTOPAY marker is cataloged."""
        rows = [
            {"date": date(2026, 1, 15), "merchant": "Cult.fit", "narration": "ACH D- CULT.FIT MANDATE 1029", "category": "Health & Medical", "mode": "Autopay", "type": "DEBIT", "amount": Decimal("1500.00")},
        ]
        df = pd.DataFrame(rows)
        items = detect_recurring_transactions(df)

        assert len(items) == 1
        assert items[0].merchant == "Cult.fit"
        assert items[0].is_autopay is True
        assert items[0].estimated_annual_cost == Decimal("18000.00")

    def test_irregular_transactions_rejected(self):
        """Verify non-recurring, random purchases are not flagged as subscriptions."""
        rows = [
            {"date": date(2026, 1, 1), "merchant": "Swiggy", "narration": "UPI/SWIGGY/1", "category": "Food & Dining", "mode": "UPI", "type": "DEBIT", "amount": Decimal("450.00")},
            {"date": date(2026, 1, 3), "merchant": "Swiggy", "narration": "UPI/SWIGGY/2", "category": "Food & Dining", "mode": "UPI", "type": "DEBIT", "amount": Decimal("850.00")},
            {"date": date(2026, 1, 20), "merchant": "Swiggy", "narration": "UPI/SWIGGY/3", "category": "Food & Dining", "mode": "UPI", "type": "DEBIT", "amount": Decimal("320.00")},
        ]
        df = pd.DataFrame(rows)
        items = detect_recurring_transactions(df)
        assert len(items) == 0

    def test_empty_dataframe_safety(self):
        """Verify safe handling of empty input."""
        empty_df = pd.DataFrame(columns=["date", "merchant", "narration", "category", "mode", "type", "amount"])
        assert detect_recurring_transactions(empty_df) == []

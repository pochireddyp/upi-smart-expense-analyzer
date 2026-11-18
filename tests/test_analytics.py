"""Unit tests for Phase 9 financial analytics and spend modeling.

Verifies strict Decimal precision, refund offsetting, monthly bucketing,
and behavioral profile calculations.
"""

from datetime import date
from decimal import Decimal
import pandas as pd
import pytest

from modules.analytics import (
    calculate_category_breakdown,
    calculate_macro_buckets,
    calculate_micro_spend_profile,
    calculate_monthly_summary,
    calculate_top_merchants,
    calculate_weekday_weekend_profile,
)


@pytest.fixture
def sample_analytics_df() -> pd.DataFrame:
    """Synthetic dataset spanning Jan and Feb 2026 with known figures."""
    rows = [
        # Jan 2026
        {"date": date(2026, 1, 1), "merchant": "Techcorp", "narration": "SALARY JAN 2026", "category": "Salary & Income", "mode": "NEFT", "type": "CREDIT", "amount": Decimal("50000.00")},
        {"date": date(2026, 1, 2), "merchant": "Swiggy", "narration": "UPI/SWIGGY/1", "category": "Food & Dining", "mode": "UPI", "type": "DEBIT", "amount": Decimal("500.00")},
        {"date": date(2026, 1, 3), "merchant": "Swiggy", "narration": "UPI/REFUND SWIGGY", "category": "Food & Dining", "mode": "UPI", "type": "CREDIT", "amount": Decimal("100.00")},
        {"date": date(2026, 1, 4), "merchant": "Zepto", "narration": "UPI/ZEPTO/GROCERY", "category": "Groceries & Essentials", "mode": "UPI", "type": "DEBIT", "amount": Decimal("1200.00")},
        {"date": date(2026, 1, 5), "merchant": "Chai Point", "narration": "UPI/TEA", "category": "Food & Dining", "mode": "UPI", "type": "DEBIT", "amount": Decimal("40.00")},
        {"date": date(2026, 1, 10), "merchant": "Chai Point", "narration": "UPI/TEA", "category": "Food & Dining", "mode": "UPI", "type": "DEBIT", "amount": Decimal("60.00")},
        {"date": date(2026, 1, 11), "merchant": "Self", "narration": "SELF TRANSFER", "category": "Peer Transfers", "mode": "UPI", "type": "DEBIT", "amount": Decimal("5000.00")},
        # Feb 2026
        {"date": date(2026, 2, 1), "merchant": "Techcorp", "narration": "SALARY FEB 2026", "category": "Salary & Income", "mode": "NEFT", "type": "CREDIT", "amount": Decimal("50000.00")},
        {"date": date(2026, 2, 5), "merchant": "Swiggy", "narration": "UPI/SWIGGY/2", "category": "Food & Dining", "mode": "UPI", "type": "DEBIT", "amount": Decimal("2500.00")},
        {"date": date(2026, 2, 8), "merchant": "BESCOM", "narration": "ELECTRICITY BILL", "category": "Utilities & Bills", "mode": "UPI", "type": "DEBIT", "amount": Decimal("1800.00")},
    ]
    return pd.DataFrame(rows)


class TestFinancialAnalytics:
    """Tests for monthly summaries, categories, and Decimal arithmetic."""

    def test_monthly_summary(self, sample_analytics_df):
        """Verify monthly summaries calculate net spend and savings rate correctly."""
        summaries = calculate_monthly_summary(sample_analytics_df)
        assert len(summaries) == 2

        jan = summaries[0]
        assert jan["month"] == "2026-01"
        assert jan["income"] == Decimal("50000.00")
        # Jan routine spend: 500 (Swiggy) + 1200 (Zepto) + 40 (Chai) + 60 (Chai) = 1800. Less 100 refund = 1700.00
        # (Peer transfer of 5000 is excluded from routine spend)
        assert jan["routine_spend"] == Decimal("1700.00")
        assert jan["net_cash_flow"] == Decimal("48300.00")
        assert jan["savings_rate"] == Decimal("96.60")

        feb = summaries[1]
        assert feb["month"] == "2026-02"
        assert feb["income"] == Decimal("50000.00")
        # Feb routine spend: 2500 + 1800 = 4300.00
        assert feb["routine_spend"] == Decimal("4300.00")
        assert feb["net_cash_flow"] == Decimal("45700.00")

    def test_category_breakdown(self, sample_analytics_df):
        """Verify category breakdown calculates spend and share percentages."""
        breakdown = calculate_category_breakdown(sample_analytics_df)
        assert len(breakdown) >= 3

        # Highest spend category
        top_cat = breakdown[0]
        assert isinstance(top_cat["total_spend"], Decimal)
        assert isinstance(top_cat["share_pct"], Decimal)
        assert top_cat["txn_count"] > 0

        # Verify shares sum to ~100%
        total_share = sum(item["share_pct"] for item in breakdown)
        assert Decimal("99.00") <= total_share <= Decimal("101.00")

    def test_macro_buckets(self, sample_analytics_df):
        """Verify Needs vs Wants aggregation in 50/30/20 framework."""
        buckets = calculate_macro_buckets(sample_analytics_df)
        assert "needs" in buckets
        assert "wants" in buckets
        # Zepto (1200) + BESCOM (1800) are Needs = 3000.00
        assert buckets["needs"] == Decimal("3000.00")
        assert buckets["wants"] > Decimal("0.00")

    def test_micro_spend_profile(self, sample_analytics_df):
        """Verify micro-spend detection under ₹150 threshold."""
        prof = calculate_micro_spend_profile(sample_analytics_df, threshold=Decimal("150.00"))
        # 2 Chai Point debits of 40 and 60
        assert prof["micro_count"] == 2
        assert prof["micro_total"] == Decimal("100.00")
        assert len(prof["top_merchants"]) == 1
        assert prof["top_merchants"][0]["merchant"] == "Chai Point"

    def test_weekday_weekend_profile(self, sample_analytics_df):
        """Verify weekday and weekend profile calculations."""
        prof = calculate_weekday_weekend_profile(sample_analytics_df)
        assert "weekday_daily_avg" in prof
        assert "weekend_daily_avg" in prof
        assert "surge_factor" in prof
        assert isinstance(prof["surge_factor"], Decimal)

    def test_top_merchants(self, sample_analytics_df):
        """Verify top merchants list sorted by spend."""
        top_m = calculate_top_merchants(sample_analytics_df, n=3)
        assert len(top_m) <= 3
        # Swiggy total spend: 500 + 2500 = 3000
        assert top_m[0]["merchant"] == "Swiggy"
        assert top_m[0]["total_spend"] == Decimal("3000.00")

    def test_empty_dataframe_safety(self):
        """Verify analytics functions handle empty DataFrames safely."""
        empty_df = pd.DataFrame(columns=["date", "merchant", "narration", "category", "mode", "type", "amount"])
        assert calculate_monthly_summary(empty_df) == []
        assert calculate_category_breakdown(empty_df) == []
        assert calculate_top_merchants(empty_df) == []
        assert calculate_micro_spend_profile(empty_df)["micro_count"] == 0

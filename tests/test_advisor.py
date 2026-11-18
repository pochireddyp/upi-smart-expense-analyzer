"""Unit tests for Phase 9 explainable spending insights and advisory rules."""

from datetime import date
from decimal import Decimal
import pandas as pd
import pytest

from modules.advisor import generate_spending_insights


class TestAdvisorRules:
    """Test suite for grounded recommendation generation and safety guardrails."""

    def test_recurring_subscription_rule(self):
        """Verify recurring subscription rule attaches evidence and quantified impact."""
        rows = [
            {"date": date(2025, 11, 5), "merchant": "Netflix", "narration": "UPI/NETFLIX", "category": "Entertainment & Subs", "mode": "UPI", "type": "DEBIT", "amount": Decimal("649.00")},
            {"date": date(2025, 12, 5), "merchant": "Netflix", "narration": "UPI/NETFLIX", "category": "Entertainment & Subs", "mode": "UPI", "type": "DEBIT", "amount": Decimal("649.00")},
            {"date": date(2026, 1, 5), "merchant": "Netflix", "narration": "UPI/NETFLIX", "category": "Entertainment & Subs", "mode": "UPI", "type": "DEBIT", "amount": Decimal("649.00")},
        ]
        df = pd.DataFrame(rows)
        recs = generate_spending_insights(df)

        sub_recs = [r for r in recs if r.rule_key == "recurring_subscription"]
        assert len(sub_recs) == 1
        rec = sub_recs[0]
        assert "Netflix" in rec.title or "Netflix" in rec.summary
        assert rec.confidence == "High"
        assert rec.action_type == "review"
        assert len(rec.evidence_txns) == 3

    def test_duplicate_charge_rule(self):
        """Verify duplicate charges within 24 hours are detected."""
        rows = [
            {"date": date(2026, 1, 10), "merchant": "Swiggy", "narration": "UPI/SWIGGY/1", "category": "Food & Dining", "mode": "UPI", "type": "DEBIT", "amount": Decimal("499.00")},
            {"date": date(2026, 1, 10), "merchant": "Swiggy", "narration": "UPI/SWIGGY/2", "category": "Food & Dining", "mode": "UPI", "type": "DEBIT", "amount": Decimal("499.00")},
            {"date": date(2026, 1, 15), "merchant": "Uber", "narration": "UPI/UBER", "category": "Commute & Travel", "mode": "UPI", "type": "DEBIT", "amount": Decimal("250.00")},
        ]
        df = pd.DataFrame(rows)
        recs = generate_spending_insights(df)

        dup_recs = [r for r in recs if r.rule_key == "duplicate_charge"]
        assert len(dup_recs) == 1
        assert dup_recs[0].action_type == "verify"
        assert dup_recs[0].estimated_saving == Decimal("499.00")

    def test_category_spike_multi_month_guard(self):
        """Verify category spike fires when >= 2 months exist and current month exceeds baseline."""
        rows = [
            # Jan 2026: Food = 2000
            {"date": date(2026, 1, 5), "merchant": "Swiggy", "narration": "UPI/SWIGGY", "category": "Food & Dining", "mode": "UPI", "type": "DEBIT", "amount": Decimal("2000.00")},
            {"date": date(2026, 1, 15), "merchant": "Bescom", "narration": "BILL", "category": "Utilities & Bills", "mode": "UPI", "type": "DEBIT", "amount": Decimal("1000.00")},
            # Feb 2026: Food = 4500 (+125% spike)
            {"date": date(2026, 2, 5), "merchant": "Swiggy", "narration": "UPI/SWIGGY", "category": "Food & Dining", "mode": "UPI", "type": "DEBIT", "amount": Decimal("4500.00")},
            {"date": date(2026, 2, 10), "merchant": "Bescom", "narration": "BILL", "category": "Utilities & Bills", "mode": "UPI", "type": "DEBIT", "amount": Decimal("1000.00")},
        ]
        df = pd.DataFrame(rows)
        recs = generate_spending_insights(df)

        spike_recs = [r for r in recs if r.rule_key == "category_spike"]
        assert len(spike_recs) == 1
        assert "Food & Dining" in spike_recs[0].title

    def test_category_spike_suppressed_single_month(self):
        """Verify category spike is suppressed if statement only spans 1 calendar month."""
        rows = [
            {"date": date(2026, 1, 5), "merchant": "Swiggy", "narration": "UPI/SWIGGY", "category": "Food & Dining", "mode": "UPI", "type": "DEBIT", "amount": Decimal("15000.00")},
            {"date": date(2026, 1, 10), "merchant": "Zepto", "narration": "UPI/ZEPTO", "category": "Groceries & Essentials", "mode": "UPI", "type": "DEBIT", "amount": Decimal("8000.00")},
            {"date": date(2026, 1, 15), "merchant": "Bescom", "narration": "BILL", "category": "Utilities & Bills", "mode": "UPI", "type": "DEBIT", "amount": Decimal("2000.00")},
        ]
        df = pd.DataFrame(rows)
        recs = generate_spending_insights(df)

        # Must not generate category spike on single month
        spike_recs = [r for r in recs if r.rule_key == "category_spike"]
        assert len(spike_recs) == 0

    def test_fee_leakage_rule(self):
        """Verify bank surcharge and penalty detection."""
        rows = [
            {"date": date(2026, 1, 5), "merchant": "HDFC Bank", "narration": "SMS CHG Q3", "category": "Utilities & Bills", "mode": "Online", "type": "DEBIT", "amount": Decimal("59.00")},
            {"date": date(2026, 1, 10), "merchant": "HDFC Bank", "narration": "MIN BAL PENALTY", "category": "Utilities & Bills", "mode": "Online", "type": "DEBIT", "amount": Decimal("350.00")},
            {"date": date(2026, 1, 15), "merchant": "Uber", "narration": "UPI/UBER", "category": "Commute & Travel", "mode": "UPI", "type": "DEBIT", "amount": Decimal("200.00")},
        ]
        df = pd.DataFrame(rows)
        recs = generate_spending_insights(df)

        fee_recs = [r for r in recs if r.rule_key == "fee_leakage"]
        assert len(fee_recs) == 1
        assert fee_recs[0].estimated_saving == Decimal("409.00")

    def test_empty_dataframe_safety(self):
        """Verify safe handling of empty data."""
        empty_df = pd.DataFrame(columns=["date", "merchant", "narration", "category", "mode", "type", "amount"])
        assert generate_spending_insights(empty_df) == []

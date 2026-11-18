"""Tests for Phase 5 dashboard modules, charts, and sample data generator."""

from decimal import Decimal
import pandas as pd
import pytest

from dashboard.charts import build_expense_trend_chart, build_category_donut_chart
from sample_data.generator import get_sample_transactions, calculate_sample_kpis


class TestSampleDataGenerator:
    """Test suite for the synthetic sample transactions generator."""

    def test_sample_transactions_structure(self):
        """Verify that sample transactions DataFrame contains required columns and rows."""
        df = get_sample_transactions()
        assert not df.empty
        assert len(df) >= 100

        required_columns = {"date", "merchant", "narration", "category", "mode", "type", "amount"}
        assert required_columns.issubset(set(df.columns))

    def test_sample_amounts_are_decimals(self):
        """Ensure all amounts in sample data are Decimal instances, not floats."""
        df = get_sample_transactions()
        for amt in df["amount"]:
            assert isinstance(amt, Decimal), f"Amount {amt} is not a Decimal!"

    def test_kpi_calculations(self):
        """Verify summary KPI calculations over sample transactions."""
        df = get_sample_transactions()
        kpis = calculate_sample_kpis(df)

        assert kpis["total_credits"] > Decimal("0.00")
        assert kpis["total_debits"] > Decimal("0.00")
        assert kpis["txn_count"] == len(df)
        assert kpis["debit_count"] + kpis["credit_count"] == len(df)
        assert isinstance(kpis["net_savings"], Decimal)


class TestDashboardCharts:
    """Test suite for Plotly chart builders."""

    def test_expense_trend_chart_renders(self):
        """Verify that the daily expense trend chart builds valid Plotly figure."""
        df = get_sample_transactions()
        fig = build_expense_trend_chart(df)
        assert fig is not None
        # Must have bar and scatter traces
        assert len(fig.data) >= 2

    def test_category_donut_chart_renders(self):
        """Verify that the category donut chart builds valid Plotly figure."""
        df = get_sample_transactions()
        fig = build_category_donut_chart(df)
        assert fig is not None
        assert len(fig.data) >= 1
        assert fig.data[0].type == "pie"

    def test_charts_empty_dataframe_safety(self):
        """Verify that charts handle empty DataFrames gracefully without crashing."""
        empty_df = pd.DataFrame(columns=["date", "merchant", "category", "mode", "type", "amount"])
        fig_trend = build_expense_trend_chart(empty_df)
        fig_donut = build_category_donut_chart(empty_df)

        assert fig_trend is not None
        assert fig_donut is not None

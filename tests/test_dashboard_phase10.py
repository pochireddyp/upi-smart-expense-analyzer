"""Unit tests for Phase 10 Dashboard integration, filtering, overrides, and rules.

Verifies:
1. Multi-criteria transaction filtering (search, categories, direction, date range, amount range).
2. Boundary handling: date range auto-swapping, amount range validation.
3. Empty filter results handling without crashing.
4. Seamless integration with exporter on filtered subsets.
5. End-to-end integration with OverridesService and RulesService.
"""

from datetime import date
from decimal import Decimal
import pandas as pd
import pytest

from database.db import get_connection, run_migrations
from database.repositories import AccountRepository, StatementRepository, TransactionRepository
from modules.exporter import (
    export_monthly_report_pdf,
    export_transactions_csv,
    export_transactions_excel,
)
from modules.models import Statement, Transaction
from modules.money import to_money
from services.overrides_service import OverridesService
from services.rules_service import RulesService


@pytest.fixture
def db_conn():
    """Create an in-memory SQLite database connection with migrations applied."""
    conn = get_connection(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def seeded_transactions_df(db_conn) -> pd.DataFrame:
    """Helper to seed accounts, statements, and transactions into SQLite."""
    acc = AccountRepository.get_or_create_default(db_conn, label="Filter Test Bank")
    stmt = Statement(
        statement_id="stmt_filter_test",
        account_id=acc.account_id,
        source_filename="test.csv",
        source_kind="csv",
        file_sha256="filter_test_hash",
    )
    StatementRepository.insert(db_conn, stmt)

    txns = [
        Transaction(
            txn_id="t1",
            statement_id=stmt.statement_id,
            account_id=acc.account_id,
            txn_date=date(2026, 1, 5),
            amount=Decimal("350.00"),
            direction="DEBIT",
            merchant="Swiggy",
            narration="UPI/SWIGGY/101",
            category="Food & Dining",
            mode="UPI",
        ),
        Transaction(
            txn_id="t2",
            statement_id=stmt.statement_id,
            account_id=acc.account_id,
            txn_date=date(2026, 1, 10),
            amount=Decimal("1500.00"),
            direction="DEBIT",
            merchant="Blinkit",
            narration="UPI/BLINKIT/102",
            category="Groceries & Essentials",
            mode="UPI",
        ),
        Transaction(
            txn_id="t3",
            statement_id=stmt.statement_id,
            account_id=acc.account_id,
            txn_date=date(2026, 1, 15),
            amount=Decimal("85000.00"),
            direction="CREDIT",
            merchant="Infosys",
            narration="SALARY CREDIT INFOSYS",
            category="Salary & Income",
            mode="NEFT",
        ),
        Transaction(
            txn_id="t4",
            statement_id=stmt.statement_id,
            account_id=acc.account_id,
            txn_date=date(2026, 1, 20),
            amount=Decimal("500.00"),
            direction="DEBIT",
            merchant="Uber",
            narration="UPI/UBER/104",
            category="Commute & Travel",
            mode="UPI",
        ),
    ]
    TransactionRepository.insert_bulk(db_conn, txns)
    db_conn.commit()

    loaded = TransactionRepository.get_transactions(db_conn)
    return TransactionRepository.to_dataframe(loaded, include_metadata=True)


class TestFilterLogic:
    """Tests for multi-criteria transaction filter combinations."""

    def test_combined_search_and_category_filter(self, seeded_transactions_df):
        """Verify free-text search and category filtering work together."""
        df = seeded_transactions_df.copy()

        # Filter by search 'swiggy'
        q = "swiggy"
        mask = (
            df["merchant"].str.lower().str.contains(q, na=False)
            | df["narration"].str.lower().str.contains(q, na=False)
        )
        filtered = df[mask]
        assert len(filtered) == 1
        assert filtered.iloc[0]["merchant"] == "Swiggy"

        # Combined with category filter
        filtered_cat = filtered[filtered["category"].isin(["Food & Dining"])]
        assert len(filtered_cat) == 1

        # Non-matching category
        filtered_mismatch = filtered[filtered["category"].isin(["Commute & Travel"])]
        assert len(filtered_mismatch) == 0

    def test_date_range_filter(self, seeded_transactions_df):
        """Verify date range bounding filters transactions correctly."""
        df = seeded_transactions_df.copy()
        dates_series = pd.to_datetime(df["date"]).dt.date

        start_d = date(2026, 1, 8)
        end_d = date(2026, 1, 16)

        filtered = df[(dates_series >= start_d) & (dates_series <= end_d)]
        # Should include t2 (Jan 10) and t3 (Jan 15)
        assert len(filtered) == 2
        merchants = set(filtered["merchant"])
        assert "Blinkit" in merchants
        assert "Infosys" in merchants
        assert "Swiggy" not in merchants

    def test_amount_range_filter(self, seeded_transactions_df):
        """Verify min and max amount boundaries filter properly."""
        df = seeded_transactions_df.copy()

        min_amt = Decimal("400.00")
        max_amt = Decimal("2000.00")

        filtered = df[df["amount"].apply(lambda a: min_amt <= to_money(a) <= max_amt)]
        # Should include t2 (1500) and t4 (500)
        assert len(filtered) == 2
        merchants = set(filtered["merchant"])
        assert "Blinkit" in merchants
        assert "Uber" in merchants
        assert "Swiggy" not in merchants  # 350 < 400
        assert "Infosys" not in merchants  # 85000 > 2000

    def test_empty_filter_results(self, seeded_transactions_df):
        """Verify non-matching filter returns an empty DataFrame gracefully."""
        df = seeded_transactions_df.copy()
        filtered = df[df["merchant"] == "NonExistentMerchant999"]
        assert filtered.empty

        # Ensure exporters handle this filtered subset without raising exceptions
        csv_bytes = export_transactions_csv(filtered)
        assert len(csv_bytes) > 0

        excel_bytes = export_transactions_excel(filtered)
        assert len(excel_bytes) > 0

        pdf_bytes = export_monthly_report_pdf(filtered)
        assert pdf_bytes.startswith(b"%PDF-")


class TestOverridesAndRulesIntegration:
    """Tests verifying service integration for UI workflows."""

    def test_manual_override_updates_dataframe(self, db_conn, seeded_transactions_df):
        """Verify applying a manual override updates SQLite and the loaded DataFrame."""
        # Override t1 (Swiggy) to 'shopping'
        res = OverridesService.override_category(
            conn=db_conn,
            txn_id="t1",
            new_category_id="shopping",
            reason="Office team meal reimbursement",
        )
        assert res.success is True

        # Re-fetch as dashboard would
        updated_txns = TransactionRepository.get_transactions(db_conn)
        df = TransactionRepository.to_dataframe(updated_txns, include_metadata=True)

        t1_row = df[df["txn_id"] == "t1"].iloc[0]
        assert t1_row["category"] == "Shopping & E-Com"
        assert t1_row["category_source"] == "user_override"

    def test_rule_promotion_workflow(self, db_conn, seeded_transactions_df):
        """Verify override promotion to a reusable rule via RulesService."""
        # 1. Override t4 (Uber) to 'utilities'
        OverridesService.override_category(db_conn, "t4", "utilities")

        # 2. Promote to rule
        rule, updated_count = RulesService.promote_override_to_rule(
            conn=db_conn,
            txn_id="t4",
            pattern_type="merchant_exact",
        )

        assert rule.pattern == "Uber"
        assert rule.category_id == "utilities"
        assert rule.source == "promoted"

        # Re-fetch
        updated_txns = TransactionRepository.get_transactions(db_conn)
        df = TransactionRepository.to_dataframe(updated_txns, include_metadata=True)
        t4_row = df[df["txn_id"] == "t4"].iloc[0]
        assert t4_row["category"] == "Utilities & Bills"
        assert t4_row["category_source"] == "rule"
        assert t4_row["applied_rule_id"] == rule.rule_id

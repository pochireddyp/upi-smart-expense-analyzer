"""Stage 1 Application Testing & Verification Suite.

Systematically verifies:
1. Synthetic CSV statement ingestion (HDFC separate Dr/Cr, SBI with preamble).
2. Synthetic PDF statement ingestion (Multi-page digital PDF, password-encrypted PDF).
3. Rejection of scanned stub PDF.
4. Duplicate statement detection via SHA-256.
5. End-to-end category override and audit trail persistence.
6. Custom rule creation, matching, and promotion.
7. Full export pipeline (CSV, Excel, PDF) on imported statement data.
8. Dashboard view rendering functions smoke tests.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
import sqlite3
import pytest

from database.db import get_connection, run_migrations
from database.repositories import AccountRepository, StatementRepository, TransactionRepository
from modules.exporter import (
    export_monthly_report_pdf,
    export_transactions_csv,
    export_transactions_excel,
)
from modules.pdf_parser import parse_pdf_statement
from services.import_service import ImportService
from services.overrides_service import OverridesService
from services.rules_service import RulesService


@pytest.fixture
def db_conn():
    """Create an isolated in-memory SQLite database connection with migrations."""
    conn = get_connection(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


class TestStage1ApplicationIngestion:
    """Verifies ingestion of all synthetic bank statement files."""

    def test_import_synthetic_hdfc_csv(self, db_conn, synthetic_hdfc_csv):
        """Verify HDFC CSV statement imports into SQLite."""
        file_bytes = synthetic_hdfc_csv.read_bytes()

        res = ImportService.import_statement(
            file_bytes=file_bytes,
            filename="sample_hdfc_statement.csv",
            conn=db_conn,
        )

        assert res.success is True
        assert res.transactions_count > 0
        assert res.is_duplicate is False

        # Verify duplicate detection
        res_dup = ImportService.import_statement(
            file_bytes=file_bytes,
            filename="sample_hdfc_statement.csv",
            conn=db_conn,
        )
        assert res_dup.is_duplicate is True

    def test_import_synthetic_sbi_csv(self, db_conn, synthetic_sbi_csv):
        """Verify SBI CSV with metadata preamble imports into SQLite."""
        file_bytes = synthetic_sbi_csv.read_bytes()

        res = ImportService.import_statement(
            file_bytes=file_bytes,
            filename="sample_sbi_statement.csv",
            conn=db_conn,
        )

        assert res.success is True
        assert res.transactions_count > 0

    def test_import_synthetic_digital_pdf(self, db_conn, synthetic_hdfc_pdf):
        """Verify digital multi-page PDF imports into SQLite."""
        file_bytes = synthetic_hdfc_pdf.read_bytes()

        res = ImportService.import_statement(
            file_bytes=file_bytes,
            filename="sample_hdfc_statement.pdf",
            conn=db_conn,
        )

        assert res.success is True
        assert res.transactions_count > 0

    def test_import_synthetic_encrypted_pdf(self, db_conn, synthetic_locked_pdf):
        """Verify password-protected PDF requires password and unlocks with password123."""
        file_bytes = synthetic_locked_pdf.read_bytes()

        # Fails without password
        res_locked = ImportService.import_statement(
            file_bytes=file_bytes,
            filename="sample_locked_statement.pdf",
            conn=db_conn,
        )
        assert res_locked.success is False

        # Succeeds with correct password
        res_unlocked = ImportService.import_statement(
            file_bytes=file_bytes,
            filename="sample_locked_statement.pdf",
            password="password123",
            conn=db_conn,
        )
        assert res_unlocked.success is True
        assert res_unlocked.transactions_count > 0

    def test_scanned_stub_pdf_rejected(self, synthetic_scanned_pdf):
        """Verify scanned stub PDF is detected and returns clear error message."""
        file_bytes = synthetic_scanned_pdf.read_bytes()

        result = parse_pdf_statement(file_bytes)
        assert result.success is False
        assert "scanned document detected" in result.error_message.lower()


class TestStage1OverridesRulesAndExports:
    """Verifies end-to-end overrides, rules, and export generation on live statement data."""

    def test_end_to_end_override_rule_and_export_flow(self, db_conn, synthetic_hdfc_csv):
        """Full end-to-end flow: Ingest -> Override -> Promote Rule -> Export CSV/Excel/PDF."""
        # 1. Ingest statement
        res = ImportService.import_statement(
            file_bytes=synthetic_hdfc_csv.read_bytes(),
            filename="sample_hdfc_statement.csv",
            conn=db_conn,
        )
        assert res.success is True

        # 2. Fetch imported transactions
        txns = TransactionRepository.get_transactions(db_conn)
        assert len(txns) > 0
        df = TransactionRepository.to_dataframe(txns, include_metadata=True)

        # 3. Apply manual override on first transaction
        target_txn = txns[0]
        initial_cat = target_txn.category_id or "food_dining"
        new_cat = "shopping" if initial_cat != "shopping" else "groceries"

        ov_res = OverridesService.override_category(
            conn=db_conn,
            txn_id=target_txn.txn_id,
            new_category_id=new_cat,
            reason="Stage 1 Verification Override",
        )
        assert ov_res.success is True

        # Verify audit history
        audit = OverridesService.get_audit_history(db_conn, txn_id=target_txn.txn_id)
        assert len(audit) >= 1
        assert audit[0].reason == "Stage 1 Verification Override"

        # 4. Promote override to rule
        p_rule, count = RulesService.promote_override_to_rule(
            conn=db_conn,
            txn_id=target_txn.txn_id,
            pattern_type="merchant_exact",
        )
        assert p_rule.source == "promoted"

        # 5. Export to CSV, Excel, and PDF
        reloaded_txns = TransactionRepository.get_transactions(db_conn)
        reloaded_df = TransactionRepository.to_dataframe(reloaded_txns, include_metadata=True)

        csv_out = export_transactions_csv(reloaded_df)
        assert len(csv_out) > 0
        assert csv_out.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM

        excel_out = export_transactions_excel(reloaded_df)
        assert len(excel_out) > 0

        pdf_out = export_monthly_report_pdf(reloaded_df)
        assert pdf_out.startswith(b"%PDF-")


class TestStage1DashboardViewsSmoke:
    """Verifies that all dashboard view modules import and compile cleanly."""

    def test_view_modules_importable(self):
        """Verify that all UI views can be imported without syntax or attribute errors."""
        import dashboard.overview as overview_mod
        import dashboard.upload as upload_mod
        import dashboard.transactions as txns_mod
        import dashboard.insights as insights_mod
        import app as app_mod

        assert hasattr(overview_mod, "render_overview")
        assert hasattr(upload_mod, "render_upload")
        assert hasattr(txns_mod, "render_transactions")
        assert hasattr(insights_mod, "render_insights")
        assert hasattr(app_mod, "render_about_page")

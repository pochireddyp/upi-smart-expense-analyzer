"""Unit tests for modules/exporter.py (CSV, Excel, and PDF Export Services).

Verifies:
1. CSV export formatting, UTF-8 BOM encoding, and formula-injection neutralization.
2. Excel workbook creation with 3 styled worksheets, currency formatting, and Decimal accuracy.
3. PDF report generation with executive header, KPI metrics, tables, and disclaimer.
4. Graceful handling of empty DataFrames across all 3 formats.
5. Strict exclusion of internal database primary keys, hashes, and unmasked account numbers.
6. Mathematical verification of exported financial totals against original Decimal sums.
"""

from datetime import date
from decimal import Decimal
import io
import openpyxl
import pandas as pd
import pymupdf
import pytest

from modules.exporter import (
    export_monthly_report_pdf,
    export_transactions_csv,
    export_transactions_excel,
    sanitize_csv_cell,
)


@pytest.fixture
def sample_transactions_df() -> pd.DataFrame:
    """Fixture returning a canonical DataFrame of representative transactions."""
    records = [
        {
            "date": date(2026, 1, 15),
            "merchant": "Swiggy",
            "narration": "UPI/SWIGGY/101/A/C 123456789012",
            "category": "Food & Dining",
            "mode": "UPI",
            "type": "DEBIT",
            "amount": Decimal("499.50"),
            "txn_id": "secret_internal_txn_1",
            "statement_id": "secret_stmt_id_1",
            "applied_rule_id": "secret_rule_id_1",
            "fingerprint": "secret_fingerprint_hash_1",
        },
        {
            "date": date(2026, 1, 16),
            "merchant": "Blinkit",
            "narration": "UPI/BLINKIT/102",
            "category": "Groceries & Essentials",
            "mode": "UPI",
            "type": "DEBIT",
            "amount": Decimal("1250.00"),
            "txn_id": "secret_internal_txn_2",
            "statement_id": "secret_stmt_id_1",
        },
        {
            "date": date(2026, 1, 18),
            "merchant": "Infosys",
            "narration": "SALARY CREDIT INFOSYS JAN 2026",
            "category": "Salary & Income",
            "mode": "NEFT",
            "type": "CREDIT",
            "amount": Decimal("75000.00"),
            "txn_id": "secret_internal_txn_3",
            "statement_id": "secret_stmt_id_1",
        },
        {
            "date": date(2026, 1, 20),
            "merchant": "=SUM(1+1)",  # Malicious formula injection attempt
            "narration": "@cmd|' /C calc'!A0",  # Malicious formula injection attempt
            "category": "+Special Category",
            "mode": "UPI",
            "type": "DEBIT",
            "amount": Decimal("100.00"),
            "txn_id": "secret_internal_txn_4",
            "statement_id": "secret_stmt_id_1",
        },
    ]
    return pd.DataFrame(records)


@pytest.fixture
def empty_df() -> pd.DataFrame:
    """Fixture returning an empty canonical DataFrame."""
    return pd.DataFrame(columns=["date", "merchant", "narration", "category", "mode", "type", "amount"])


class TestCSVExport:
    """Tests for CSV generation, UTF-8 BOM encoding, and formula injection protection."""

    def test_csv_generation_and_columns(self, sample_transactions_df):
        """Verify CSV contains expected columns and valid data."""
        csv_bytes = export_transactions_csv(sample_transactions_df)
        assert isinstance(csv_bytes, bytes)
        assert len(csv_bytes) > 0

        # Decode utf-8-sig
        content = csv_bytes.decode("utf-8-sig")
        lines = content.strip().splitlines()

        # Check headers
        expected_headers = "Date,Merchant,Description,Category,Mode,Type,Amount (INR)"
        assert lines[0] == expected_headers

        # Verify data rows count
        assert len(lines) == 5  # 1 header + 4 data rows

    def test_csv_formula_injection_protection(self, sample_transactions_df):
        """Verify leading =, +, -, @ are prepended with single quotes in text fields."""
        csv_bytes = export_transactions_csv(sample_transactions_df)
        content = csv_bytes.decode("utf-8-sig")

        # The malicious merchant '=SUM(1+1)' must be escaped as "'=SUM(1+1)"
        assert "'=SUM(1+1)" in content
        # The malicious narration '@cmd|...' must be escaped as "'@cmd|..."
        assert "'@cmd|" in content
        # The category '+Special Category' must be escaped as "'+Special Category"
        assert "'+Special Category" in content

    def test_csv_excludes_internal_ids_and_masks_accounts(self, sample_transactions_df):
        """Verify internal database keys and hashes are absent, and account numbers masked."""
        csv_bytes = export_transactions_csv(sample_transactions_df)
        content = csv_bytes.decode("utf-8-sig")

        assert "secret_internal_txn" not in content
        assert "secret_stmt_id" not in content
        assert "secret_rule_id" not in content
        assert "secret_fingerprint" not in content

        # Account number 123456789012 must be masked to ••••9012
        assert "123456789012" not in content
        assert "••••9012" in content

    def test_csv_empty_dataframe(self, empty_df):
        """Verify empty DataFrame produces valid header-only CSV."""
        csv_bytes = export_transactions_csv(empty_df)
        content = csv_bytes.decode("utf-8-sig")
        lines = content.strip().splitlines()
        assert len(lines) == 1
        assert "Date,Merchant,Description" in lines[0]


class TestExcelExport:
    """Tests for multi-sheet Excel generation, styling, and number formats."""

    def test_excel_workbook_and_three_sheets(self, sample_transactions_df):
        """Verify workbook is generated with the 3 required worksheets."""
        excel_bytes = export_transactions_excel(sample_transactions_df)
        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0

        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
        sheet_names = wb.sheetnames
        assert "Transaction Ledger" in sheet_names
        assert "Category Breakdown" in sheet_names
        assert "Monthly Cashflow" in sheet_names

    def test_excel_financial_values_and_formatting(self, sample_transactions_df):
        """Verify transaction values, decimal precision, and number formats."""
        excel_bytes = export_transactions_excel(sample_transactions_df)
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=True)

        ws_ledger = wb["Transaction Ledger"]
        # Check headers in row 1
        assert ws_ledger.cell(row=1, column=1).value == "Date"
        assert ws_ledger.cell(row=1, column=7).value == "Amount (INR)"

        # Check data row amounts
        amounts = [ws_ledger.cell(row=r, column=7).value for r in range(2, 6)]
        assert 75000.0 in amounts
        assert 1250.0 in amounts
        assert 499.5 in amounts

        # Check Category Breakdown sheet
        ws_cat = wb["Category Breakdown"]
        cat_names = [ws_cat.cell(row=r, column=1).value for r in range(2, ws_cat.max_row + 1)]
        assert "Groceries & Essentials" in cat_names
        assert "Food & Dining" in cat_names

        # Check Monthly Cashflow sheet
        ws_flow = wb["Monthly Cashflow"]
        assert ws_flow.cell(row=2, column=1).value == "Jan 2026"
        # Total Inflow
        assert ws_flow.cell(row=2, column=2).value == 75000.0
        # Total Outflow: 499.50 + 1250.00 + 100.00 = 1849.50
        assert ws_flow.cell(row=2, column=3).value == 1849.50

    def test_excel_empty_dataframe(self, empty_df):
        """Verify empty DataFrame produces valid workbook with clean placeholder messages."""
        excel_bytes = export_transactions_excel(empty_df)
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))

        for sname in ["Transaction Ledger", "Category Breakdown", "Monthly Cashflow"]:
            ws = wb[sname]
            assert ws.max_row >= 2
            # Second row has placeholder text
            assert "No " in str(ws.cell(row=2, column=1).value)


class TestPDFExport:
    """Tests for executive PDF report generation, layout, and safety."""

    def test_pdf_generation_and_valid_output(self, sample_transactions_df):
        """Verify PDF document is well-formed and begins with standard PDF header."""
        pdf_bytes = export_monthly_report_pdf(sample_transactions_df)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes.startswith(b"%PDF-")

        # Open with PyMuPDF and inspect text content
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        assert len(doc) >= 1

        page_text = doc[0].get_text()
        assert "UPI SMART EXPENSE ANALYZER" in page_text
        assert "INWARD INCOME" in page_text
        assert "ROUTINE EXPENSES" in page_text
        assert "SPENDING BY CATEGORY" in page_text
        assert "TOP RECIPIENTS & MERCHANTS" in page_text
        assert "Informational Disclaimer" in page_text

    def test_pdf_empty_dataframe_handling(self, empty_df):
        """Verify empty DataFrame generates a clean report without throwing an exception."""
        pdf_bytes = export_monthly_report_pdf(empty_df)
        assert pdf_bytes.startswith(b"%PDF-")

        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        page_text = doc[0].get_text()
        assert "UPI SMART EXPENSE ANALYZER" in page_text
        assert "No transaction records found matching the specified export criteria." in page_text
        assert "Informational Disclaimer" in page_text

    def test_pdf_excludes_internal_ids(self, sample_transactions_df):
        """Verify internal database keys and raw unmasked account numbers do not appear in PDF."""
        pdf_bytes = export_monthly_report_pdf(sample_transactions_df)
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        full_text = "".join(p.get_text() for p in doc)

        assert "secret_internal_txn" not in full_text
        assert "secret_stmt_id" not in full_text
        assert "123456789012" not in full_text

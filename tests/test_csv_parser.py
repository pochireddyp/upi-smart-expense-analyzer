"""Unit tests for modules/schema_detector.py and modules/csv_parser.py."""

from decimal import Decimal
from pathlib import Path
import pytest

from modules.csv_parser import parse_csv_statement, _mask_sensitive_account_numbers
from modules.schema_detector import detect_column_mapping, find_header_row


class TestSchemaDetector:
    """Tests for header discovery and column mapping."""

    def test_find_header_row_with_preamble(self):
        """Verify that find_header_row skips metadata and locates the actual headers."""
        sample_rows = [
            ["Account Name : Test Customer"],
            ["Account Number : 123456789012"],
            ["Branch : Bangalore Main"],
            [],
            ["Txn Date", "Description", "Debit", "Credit", "Balance"],
            ["01/01/2026", "Swiggy", "450.00", "", "10000.00"],
        ]
        header_idx, headers = find_header_row(sample_rows)
        assert header_idx == 4
        assert "Txn Date" in headers
        assert "Debit" in headers

    def test_detect_column_mapping_hdfc(self):
        """Verify column mapping for standard HDFC layout."""
        headers = ["Date", "Narration", "Chq/Ref No", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]
        mapping = detect_column_mapping(headers)

        assert mapping.is_valid
        assert mapping.date_col == "Date"
        assert mapping.desc_col == "Narration"
        assert mapping.debit_col == "Withdrawal Amt."
        assert mapping.credit_col == "Deposit Amt."
        assert mapping.balance_col == "Closing Balance"
        assert mapping.confidence_score >= 0.75

    def test_detect_column_mapping_single_amount(self):
        """Verify column mapping for statements with Amount + Type columns."""
        headers = ["Transaction Date", "Transaction Remarks", "Amount", "Type (Dr/Cr)"]
        mapping = detect_column_mapping(headers)

        assert mapping.is_valid
        assert mapping.date_col == "Transaction Date"
        assert mapping.desc_col == "Transaction Remarks"
        assert mapping.amount_col == "Amount"
        assert mapping.direction_col == "Type (Dr/Cr)"


class TestCSVParser:
    """Tests for the CSV parser, normalizer, and validator."""

    def test_parse_hdfc_statement_file(self, synthetic_hdfc_csv):
        """Verify parsing a standard HDFC statement CSV."""
        hdfc_file = synthetic_hdfc_csv
        assert hdfc_file.is_file()

        result = parse_csv_statement(str(hdfc_file))
        assert result.success is True
        assert result.df is not None
        assert result.valid_rows == 15
        assert result.skipped_rows == 0

        # Check required columns exist
        expected_cols = {"date", "merchant", "narration", "category", "mode", "type", "amount"}
        assert expected_cols.issubset(set(result.df.columns))

        # Check amounts are strictly Decimal instances
        for amt in result.df["amount"]:
            assert isinstance(amt, Decimal)

    def test_parse_sbi_statement_with_preamble(self, synthetic_sbi_csv):
        """Verify parsing an SBI statement containing metadata preamble lines."""
        sbi_file = synthetic_sbi_csv
        assert sbi_file.is_file()

        result = parse_csv_statement(str(sbi_file))
        assert result.success is True
        assert result.df is not None
        assert result.valid_rows == 10
        assert result.mapping.header_row_index == 8

        # Check category heuristics
        categories = set(result.df["category"].unique())
        assert "Food & Dining" in categories or "Commute & Travel" in categories

    def test_parse_bytes_input(self):
        """Verify parsing directly from raw bytes (as provided by Streamlit uploader)."""
        csv_bytes = (
            b"Date,Description,Debit,Credit\n"
            b"01/01/2026,Swiggy Food,450.00,\n"
            b"02/01/2026,Client Payment,,25000.00\n"
        )
        result = parse_csv_statement(csv_bytes)
        assert result.success is True
        assert result.valid_rows == 2
        # Data is sorted by date descending, so Jan 2 is first, Jan 1 is second
        assert result.df.iloc[0]["merchant"] == "Client Payment"
        assert result.df.iloc[1]["merchant"] == "Swiggy"

    def test_empty_csv_handling(self):
        """Verify that empty files return a graceful error."""
        result = parse_csv_statement(b"")
        assert result.success is False
        assert "empty" in result.error_message.lower()

    def test_missing_required_columns(self):
        """Verify error when required columns cannot be found."""
        unrecognized_csv = b"ColA,ColB,ColC\n1,2,3\n4,5,6\n"
        result = parse_csv_statement(unrecognized_csv)
        assert result.success is False
        assert "could not automatically identify" in result.error_message.lower()

    def test_mask_sensitive_account_numbers(self):
        """Verify masking of long bank account numbers in narrations."""
        sample_narr = "TRANSFER TO 0000003291029381 VIA UPI"
        masked = _mask_sensitive_account_numbers(sample_narr)
        assert "3291029381" not in masked
        assert "••••9381" in masked

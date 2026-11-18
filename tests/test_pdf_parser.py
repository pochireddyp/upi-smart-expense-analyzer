"""Unit tests for modules/pdf_parser.py using synthetic PDF statements."""

from decimal import Decimal
from pathlib import Path
import pytest

from modules.pdf_parser import parse_pdf_statement


class TestPDFParser:
    """Test suite for PDF statement extraction, decryption, and validation."""

    def test_parse_digital_hdfc_pdf(self, synthetic_hdfc_pdf):
        """Verify parsing a multi-page digital bank PDF statement."""
        hdfc_pdf = synthetic_hdfc_pdf
        assert hdfc_pdf.is_file(), "sample_hdfc_statement.pdf fixture missing"

        result = parse_pdf_statement(str(hdfc_pdf))
        assert result.success is True, f"Parsing failed: {result.error_message}"
        assert result.page_count == 2
        assert result.valid_rows == 15
        assert result.df is not None

        # Check canonical columns
        expected_cols = {"date", "merchant", "narration", "category", "mode", "type", "amount"}
        assert expected_cols.issubset(set(result.df.columns))

        # Check Decimal precision
        for amt in result.df["amount"]:
            assert isinstance(amt, Decimal), f"Amount {amt} is not a Decimal!"

        # Check sorting by date descending
        dates = list(result.df["date"])
        assert dates == sorted(dates, reverse=True)

    def test_password_encrypted_pdf_without_password(self, synthetic_locked_pdf):
        """Verify that locked PDFs without password return prompt error."""
        locked_pdf = synthetic_locked_pdf
        assert locked_pdf.is_file()

        result = parse_pdf_statement(str(locked_pdf))
        assert result.success is False
        assert result.is_encrypted is True
        assert "password-protected" in result.error_message.lower()

    def test_password_encrypted_pdf_with_wrong_password(self, synthetic_locked_pdf):
        """Verify that incorrect password returns friendly error."""
        locked_pdf = synthetic_locked_pdf
        result = parse_pdf_statement(str(locked_pdf), password="wrongpassword")

        assert result.success is False
        assert result.is_encrypted is True
        assert "incorrect password" in result.error_message.lower()

    def test_password_encrypted_pdf_with_correct_password(self, synthetic_locked_pdf):
        """Verify successful unlock and parsing with valid password."""
        locked_pdf = synthetic_locked_pdf
        result = parse_pdf_statement(str(locked_pdf), password="password123")

        assert result.success is True, f"Failed with valid password: {result.error_message}"
        assert result.valid_rows == 4
        assert result.df is not None

        # Check salary credit
        merchants = list(result.df["merchant"])
        assert any("Salary" in m or "Techcorp" in m for m in merchants)

    def test_scanned_stub_pdf_detection(self, synthetic_scanned_pdf):
        """Verify that image-only / text-less PDFs are detected as scanned."""
        scanned_pdf = synthetic_scanned_pdf
        assert scanned_pdf.is_file()

        result = parse_pdf_statement(str(scanned_pdf))
        assert result.success is False
        assert "scanned document detected" in result.error_message.lower()

    def test_empty_pdf_input(self):
        """Verify handling of empty PDF input."""
        result = parse_pdf_statement(b"")
        assert result.success is False
        assert "empty" in result.error_message.lower()

    def test_corrupted_pdf_input(self):
        """Verify handling of invalid non-PDF file data."""
        result = parse_pdf_statement(b"This is completely invalid PDF header data.")
        assert result.success is False
        assert "failed to open pdf" in result.error_message.lower()

    def test_sensitive_account_number_masking(self, synthetic_hdfc_pdf):
        """Verify masking of account numbers extracted from PDF text."""
        hdfc_pdf = synthetic_hdfc_pdf
        result = parse_pdf_statement(str(hdfc_pdf))

        assert result.success is True
        narrations = " ".join(result.df["narration"])
        assert "3291029381" not in narrations

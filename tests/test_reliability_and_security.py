"""Stage 3: Reliability and Security Hardening Unit & Integration Tests.

Validates:
1. File upload boundary safety: 0-byte files, oversized files (> 10 MB), corrupted CSV/PDF,
   unsupported extensions, and password-protected PDFs.
2. Database atomicity: Transaction rollback on import failure, lock/operational error handling,
   and zero orphaned records.
3. Privacy & security: Account number masking (8-18 digits), CSV formula injection protection,
   and exclusion of internal DB identifiers from all exports.
4. Configuration and cross-platform readiness: UTF-8 encoding of requirements.txt.
"""

from decimal import Decimal
import io
from pathlib import Path
import sqlite3
import pytest
import pandas as pd

from database.db import get_connection, run_migrations, transaction_scope
from database.repositories import AccountRepository, StatementRepository, TransactionRepository
from database.rules_repository import RulesRepository
from modules.categorizer import mask_sensitive_account_numbers
from modules.csv_parser import parse_csv_statement
from modules.exporter import (
    export_monthly_report_pdf,
    export_transactions_csv,
    export_transactions_excel,
    sanitize_csv_cell,
)
from modules.pdf_parser import parse_pdf_statement
from services.import_service import (
    ImportResult,
    ImportService,
    MAX_UPLOAD_SIZE_BYTES,
    MAX_UPLOAD_SIZE_MB,
)
from services.overrides_service import OverridesService
from services.rules_service import RulesService


# ==============================================================================
# 1. File Upload Reliability & Boundary Tests
# ==============================================================================
class TestFileUploadReliability:
    """Tests for upload reliability, size limits, empty/corrupted files, and extensions."""

    def test_empty_file_rejected(self):
        """Verify that 0-byte files and whitespace-only files are cleanly rejected."""
        # Service level
        res_empty = ImportService.import_statement(file_bytes=b"", filename="empty.csv")
        assert res_empty.success is False
        assert "empty" in res_empty.error_message.lower()

        res_whitespace = ImportService.import_statement(file_bytes=b"   \n\t  \r\n", filename="whitespace.csv")
        assert res_whitespace.success is False
        assert "empty" in res_whitespace.error_message.lower()

        # Parser level
        csv_res = parse_csv_statement(b"")
        assert csv_res.success is False
        assert "empty" in csv_res.error_message.lower()

        pdf_res = parse_pdf_statement(b"")
        assert pdf_res.success is False
        assert "empty" in pdf_res.error_message.lower()

    def test_oversized_file_rejected(self):
        """Verify that files exceeding MAX_UPLOAD_SIZE_BYTES (10 MB) are rejected immediately."""
        oversized_bytes = b"X" * (MAX_UPLOAD_SIZE_BYTES + 1024)  # 10 MB + 1 KB
        res = ImportService.import_statement(file_bytes=oversized_bytes, filename="huge.csv")
        assert res.success is False
        assert "exceeds the maximum allowed upload limit" in res.error_message
        assert f"{MAX_UPLOAD_SIZE_MB} MB" in res.error_message

    def test_accepted_file_size_boundary(self, synthetic_hdfc_csv):
        """Verify that files within the 10 MB limit proceed to parsing."""
        valid_bytes = synthetic_hdfc_csv.read_bytes()
        assert len(valid_bytes) < MAX_UPLOAD_SIZE_BYTES

        # Verify it parses successfully
        res = parse_csv_statement(valid_bytes)
        assert res.success is True
        assert res.valid_rows > 0

    def test_unsupported_file_extension(self):
        """Verify that unsupported extensions are rejected before parsing."""
        fake_payload = b"Sample text payload"
        for ext in ["statement.exe", "statement.txt", "data.json", "image.png", "statement"]:
            res = ImportService.import_statement(file_bytes=fake_payload, filename=ext)
            assert res.success is False
            assert "unsupported file extension" in res.error_message.lower()

    def test_corrupted_csv_payload(self):
        """Verify that binary garbage or corrupted text disguised as CSV fails gracefully."""
        # Random binary bytes
        corrupt_bytes = b"\x00\x01\x02\x03\xff\xfe\x00\x12binary_junk_data"
        res = parse_csv_statement(corrupt_bytes)
        assert res.success is False
        assert res.error_message is not None

        # Text without identifiable banking columns
        nonsense_csv = b"ColumnA,ColumnB,ColumnC\nfoo,bar,baz\n1,2,3\n"
        res_nonsense = parse_csv_statement(nonsense_csv)
        assert res_nonsense.success is False
        assert "could not automatically identify required transaction columns" in res_nonsense.error_message.lower()

    def test_corrupted_pdf_payload(self):
        """Verify that invalid PDF data returns a user-friendly error without crashing."""
        corrupt_pdf = b"This is definitely not a PDF file header."
        res = parse_pdf_statement(corrupt_pdf)
        assert res.success is False
        assert "failed to open pdf document" in res.error_message.lower()

    def test_password_protected_pdf_behaviors(self, synthetic_locked_pdf):
        """Verify that password protected PDFs handle missing and incorrect passwords gracefully."""
        assert synthetic_locked_pdf.is_file()
        pdf_bytes = synthetic_locked_pdf.read_bytes()

        # Missing password
        res_no_pw = parse_pdf_statement(pdf_bytes, password=None)
        assert res_no_pw.success is False
        assert res_no_pw.is_encrypted is True
        assert "password-protected" in res_no_pw.error_message.lower()

        # Wrong password
        res_wrong_pw = parse_pdf_statement(pdf_bytes, password="wrongpassword123")
        assert res_wrong_pw.success is False
        assert res_wrong_pw.is_encrypted is True
        assert "incorrect password" in res_wrong_pw.error_message.lower()

        # Correct password
        res_correct_pw = parse_pdf_statement(pdf_bytes, password="password123")
        assert res_correct_pw.success is True
        assert res_correct_pw.valid_rows > 0


# ==============================================================================
# 2. Database Reliability & Transaction Rollback Tests
# ==============================================================================
class TestDatabaseReliability:
    """Tests ensuring database transaction rollback and error resilience."""

    @pytest.fixture
    def test_db(self):
        conn = get_connection(":memory:")
        run_migrations(conn)
        AccountRepository.get_or_create_default(conn, label="Test Account")
        yield conn
        conn.close()

    def test_failed_import_leaves_zero_orphaned_records(self, test_db, synthetic_hdfc_csv):
        """Verify that if an error occurs during statement insertion, all changes rollback."""
        csv_bytes = synthetic_hdfc_csv.read_bytes()

        # Count initial rows
        initial_stmts = test_db.execute("SELECT COUNT(*) as c FROM statements;").fetchone()["c"]
        initial_txns = test_db.execute("SELECT COUNT(*) as c FROM transactions;").fetchone()["c"]
        assert initial_stmts == 0
        assert initial_txns == 0

        # Simulate a database failure by dropping the transactions table before calling import
        test_db.execute("DROP TABLE transactions;")

        res = ImportService.import_statement(
            file_bytes=csv_bytes,
            filename="hdfc_test.csv",
            conn=test_db,
        )

        assert res.success is False
        assert "database error" in res.error_message.lower()

        # Verify statements table has 0 records (rolled back completely)
        final_stmts = test_db.execute("SELECT COUNT(*) as c FROM statements;").fetchone()["c"]
        assert final_stmts == 0

    def test_failed_category_override_rollback(self, test_db, synthetic_hdfc_csv):
        """Verify that category override failures do not leave partial audit records."""
        # Insert a valid transaction
        import_res = ImportService.import_statement(
            file_bytes=synthetic_hdfc_csv.read_bytes(),
            filename="hdfc_test.csv",
            conn=test_db,
        )
        assert import_res.success is True

        txn = test_db.execute("SELECT txn_id, category_id FROM transactions LIMIT 1;").fetchone()
        orig_cat = txn["category_id"]

        # Attempt override with invalid category
        with pytest.raises(ValueError, match="does not exist"):
            OverridesService.override_category(
                conn=test_db,
                txn_id=txn["txn_id"],
                new_category_id="non_existent_category_xyz",
            )

        # Verify transaction category is unchanged
        recheck = test_db.execute("SELECT category_id FROM transactions WHERE txn_id = ?;", (txn["txn_id"],)).fetchone()
        assert recheck["category_id"] == orig_cat

        # Verify 0 audit records were created
        audits = test_db.execute("SELECT COUNT(*) as c FROM category_overrides_audit;").fetchone()["c"]
        assert audits == 0

    def test_failed_rule_creation_rollback(self, test_db):
        """Verify that invalid rule patterns raise ValueError without modifying rules table."""
        initial_rules = test_db.execute("SELECT COUNT(*) as c FROM categorization_rules;").fetchone()["c"]

        # Attempt to create rule with invalid regex
        with pytest.raises(ValueError, match="Invalid regular expression"):
            RulesService.create_rule(
                conn=test_db,
                pattern="[unclosed_bracket",
                pattern_type="regex",
                category_id="food_dining",
            )

        final_rules = test_db.execute("SELECT COUNT(*) as c FROM categorization_rules;").fetchone()["c"]
        assert final_rules == initial_rules


# ==============================================================================
# 3. Privacy, Masking & Export Sanitization Tests
# ==============================================================================
class TestPrivacyAndSecurityAudit:
    """Tests ensuring financial confidentiality, account masking, and formula injection protection."""

    def test_account_masking_short_and_long_numbers(self):
        """Verify 8 to 18-digit account numbers and card numbers are masked."""
        # 8-digit account number
        assert mask_sensitive_account_numbers("Account 12345678") == "Account ••••5678"

        # 12-digit standard Indian bank account
        assert mask_sensitive_account_numbers("A/c 501002345678 at HDFC") == "A/c ••••5678 at HDFC"

        # 16-digit debit card
        assert mask_sensitive_account_numbers("POS card swipe 4111222233334444") == "POS card swipe ••••4444"

        # 18-digit virtual account
        assert mask_sensitive_account_numbers("NEFT to 123456789012345678") == "NEFT to ••••5678"

        # Preserves short numbers (PINs, dates, amounts)
        assert mask_sensitive_account_numbers("PIN 1234") == "PIN 1234"
        assert mask_sensitive_account_numbers("OTP 56789") == "OTP 56789"

    def test_csv_formula_injection_sanitization(self):
        """Verify that formula triggers (=, +, -, @, tabs, newlines) are prefixed with '."""
        assert sanitize_csv_cell("=CMD|' /C calc'!A0") == "'=CMD|' /C calc'!A0"
        assert sanitize_csv_cell("+123456") == "'+123456"
        assert sanitize_csv_cell("-500.00") == "'-500.00"
        assert sanitize_csv_cell("@SUM(A1:A10)") == "'@SUM(A1:A10)"
        assert sanitize_csv_cell("\tTabLeading") == "'\tTabLeading"
        assert sanitize_csv_cell("Normal Text") == "Normal Text"

    def test_exports_exclude_internal_database_identifiers(self):
        """Verify that CSV, Excel, and PDF exports exclude primary keys and file hashes."""
        df = pd.DataFrame([{
            "txn_id": "txn_secret_pk_12345",
            "statement_id": "stmt_internal_uuid_67890",
            "account_id": 999,
            "file_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "fingerprint": "fp_secret_hash",
            "date": "2026-03-15",
            "merchant": "Swiggy",
            "narration": "UPI/401029381/SWIGGY/A/C 123456789012",
            "category": "Food & Dining",
            "mode": "UPI",
            "type": "DEBIT",
            "amount": Decimal("499.50"),
        }])

        # 1. Check CSV Export
        csv_bytes = export_transactions_csv(df)
        csv_text = csv_bytes.decode("utf-8-sig")
        assert "txn_secret_pk_12345" not in csv_text
        assert "stmt_internal_uuid_67890" not in csv_text
        assert "e3b0c44298fc" not in csv_text
        assert "123456789012" not in csv_text
        assert "••••9012" in csv_text

        # 2. Check Excel Export
        excel_bytes = export_transactions_excel(df)
        # Search bytes for raw ID strings
        assert b"txn_secret_pk_12345" not in excel_bytes
        assert b"stmt_internal_uuid_67890" not in excel_bytes
        assert b"123456789012" not in excel_bytes

        # 3. Check PDF Export
        pdf_bytes = export_monthly_report_pdf(df, metadata={"account_label": "Account 987654321098"})
        assert b"txn_secret_pk_12345" not in pdf_bytes
        assert b"stmt_internal_uuid_67890" not in pdf_bytes
        assert b"987654321098" not in pdf_bytes

    def test_gitignore_protects_confidential_files(self):
        """Verify that .gitignore excludes database files, uploaded statements, and secrets."""
        gitignore_path = Path(__file__).resolve().parent.parent / ".gitignore"
        assert gitignore_path.is_file()
        content = gitignore_path.read_text(encoding="utf-8")

        assert "*.db" in content
        assert "*.csv" in content
        assert "*.pdf" in content
        assert ".env" in content
        assert "data/uploads/*" in content

    def test_requirements_txt_is_valid_utf8(self):
        """Verify that requirements.txt is encoded in clean UTF-8 without UTF-16 BOM."""
        req_path = Path(__file__).resolve().parent.parent / "requirements.txt"
        assert req_path.is_file()

        raw_bytes = req_path.read_bytes()
        # Verify no UTF-16 BOM (0xFF 0xFE or 0xFE 0xFF)
        assert not raw_bytes.startswith(b"\xff\xfe")
        assert not raw_bytes.startswith(b"\xfe\xff")

        # Verify decodable as utf-8
        text = raw_bytes.decode("utf-8")
        assert "streamlit==" in text
        assert "pandas==" in text
        assert "pymupdf==" in text

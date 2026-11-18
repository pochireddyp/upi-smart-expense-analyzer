"""Unit tests for SQLite database persistence, repositories, and ImportService.

Tests all database operations using in-memory SQLite (:memory:) to guarantee
isolation and protect production/user data.
"""

import concurrent.futures
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3
import uuid

import pytest

from database.db import get_connection, init_db, run_migrations, transaction_scope
from database.repositories import AccountRepository, StatementRepository, TransactionRepository
from modules.models import Statement, Transaction
from services.import_service import ImportService


@pytest.fixture
def db_conn():
    """Create an in-memory SQLite database connection with migrations applied."""
    conn = get_connection(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


class TestDatabasePragmasAndMigrations:
    """Tests SQLite connection configuration and migration management."""

    def test_foreign_keys_enabled(self, db_conn):
        """Verify foreign key enforcement is active."""
        cursor = db_conn.execute("PRAGMA foreign_keys;")
        assert cursor.fetchone()[0] == 1

    def test_migrations_idempotent(self, db_conn):
        """Verify migrations can run repeatedly without error."""
        # Already run in fixture; running again should apply 0
        newly_applied = run_migrations(db_conn)
        assert newly_applied == 0

    def test_concurrent_init_db(self, tmp_path):
        """Verify multiple concurrent threads calling init_db() on a fresh database succeed without error."""
        db_file = tmp_path / "concurrent_app.db"

        def worker(thread_idx: int):
            return init_db(db_file)

        # Execute 8 concurrent threads calling init_db simultaneously
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, i) for i in range(8)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 8

        # Verify migrations 001 and 002 were applied exactly once
        conn = get_connection(db_file)
        try:
            rows = conn.execute(
                "SELECT version, name FROM schema_migrations ORDER BY version ASC;"
            ).fetchall()
            assert len(rows) == 2
            assert rows[0]["version"] == 1
            assert rows[0]["name"] == "001_initial_schema.sql"
            assert rows[1]["version"] == 2
            assert rows[1]["name"] == "002_user_rules_and_overrides.sql"

            # Verify tables exist
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
            assert {"accounts", "statements", "categories", "transactions", "categorization_rules", "category_overrides_audit"}.issubset(tables)
        finally:
            conn.close()

    def test_repeated_init_db_calls(self, tmp_path):
        """Verify repeated sequential init_db calls on the same file succeed without error."""
        db_file = tmp_path / "repeated_app.db"

        for _ in range(5):
            path = init_db(db_file)
            assert path == db_file

        conn = get_connection(db_file)
        try:
            count = conn.execute("SELECT COUNT(*) FROM schema_migrations;").fetchone()[0]
            assert count == 2
        finally:
            conn.close()


class TestAccountRepository:
    """Tests for bank account management."""

    def test_get_or_create_default(self, db_conn):
        """Verify default account creation and retrieval."""
        acc1 = AccountRepository.get_or_create_default(db_conn, label="Test Account", bank_name="HDFC")
        assert acc1.account_id.startswith("acc_")
        assert acc1.label == "Test Account"
        assert acc1.bank_name == "HDFC"

        # Calling again should return the exact same account
        acc2 = AccountRepository.get_or_create_default(db_conn, label="Different Label")
        assert acc2.account_id == acc1.account_id
        assert acc2.label == "Test Account"

    def test_list_accounts(self, db_conn):
        """Verify listing all registered accounts."""
        AccountRepository.get_or_create_default(db_conn, label="Primary Account")
        accounts = AccountRepository.list_accounts(db_conn)
        assert len(accounts) == 1
        assert accounts[0].label == "Primary Account"


class TestStatementRepository:
    """Tests for statement tracking and duplicate detection."""

    def test_insert_and_find_by_sha256(self, db_conn):
        """Verify statement insertion and SHA-256 retrieval."""
        acc = AccountRepository.get_or_create_default(db_conn)
        stmt = Statement(
            statement_id="stmt_test1",
            account_id=acc.account_id,
            source_filename="test.csv",
            source_kind="csv",
            file_sha256="abc123hash",
            row_count=10,
            imported_count=10,
            skipped_count=0,
            imported_at=datetime.now(timezone.utc),
        )
        StatementRepository.insert(db_conn, stmt)

        found = StatementRepository.find_by_sha256(db_conn, "abc123hash")
        assert found is not None
        assert found.statement_id == "stmt_test1"
        assert found.source_filename == "test.csv"

        # Non-existent hash
        assert StatementRepository.find_by_sha256(db_conn, "nonexistent") is None

    def test_unique_sha256_constraint(self, db_conn):
        """Verify duplicate SHA-256 inserts raise an integrity error."""
        acc = AccountRepository.get_or_create_default(db_conn)
        stmt1 = Statement(
            statement_id="stmt_1",
            account_id=acc.account_id,
            source_filename="file1.csv",
            source_kind="csv",
            file_sha256="same_hash",
        )
        StatementRepository.insert(db_conn, stmt1)

        stmt2 = Statement(
            statement_id="stmt_2",
            account_id=acc.account_id,
            source_filename="file2.csv",
            source_kind="csv",
            file_sha256="same_hash",
        )
        with pytest.raises(sqlite3.IntegrityError):
            StatementRepository.insert(db_conn, stmt2)


class TestTransactionRepository:
    """Tests for transaction persistence and monetary precision."""

    def test_paise_accuracy_in_storage(self, db_conn):
        """Verify amounts are stored as integer paise and returned as exact Decimals."""
        acc = AccountRepository.get_or_create_default(db_conn)
        stmt = Statement(
            statement_id="stmt_precision",
            account_id=acc.account_id,
            source_filename="sample.csv",
            source_kind="csv",
            file_sha256="precision_hash",
        )
        StatementRepository.insert(db_conn, stmt)

        txn = Transaction(
            txn_id="txn_101",
            statement_id=stmt.statement_id,
            account_id=acc.account_id,
            txn_date=date(2026, 1, 15),
            amount=Decimal("499.50"),
            direction="DEBIT",
            merchant="Swiggy",
            narration="UPI/SWIGGY/123",
            category="Food & Dining",
        )
        TransactionRepository.insert_bulk(db_conn, [txn])

        # Verify directly in SQLite that amount_minor is stored as integer 49950
        cursor = db_conn.execute("SELECT amount_minor FROM transactions WHERE txn_id = 'txn_101';")
        stored_paise = cursor.fetchone()[0]
        assert stored_paise == 49950
        assert isinstance(stored_paise, int)

        # Verify repository returns exact Decimal
        loaded_txns = TransactionRepository.get_transactions(db_conn, statement_id=stmt.statement_id)
        assert len(loaded_txns) == 1
        assert loaded_txns[0].amount == Decimal("499.50")
        assert loaded_txns[0].category == "Food & Dining"

    def test_atomic_rollback_on_error(self, db_conn):
        """Verify transaction rollback if an error occurs mid-operation."""
        acc = AccountRepository.get_or_create_default(db_conn)

        with pytest.raises(RuntimeError):
            with transaction_scope(db_conn):
                stmt = Statement(
                    statement_id="stmt_rollback",
                    account_id=acc.account_id,
                    source_filename="error.csv",
                    source_kind="csv",
                    file_sha256="rollback_hash",
                )
                StatementRepository.insert(db_conn, stmt)
                raise RuntimeError("Simulated failure after inserting statement")

        # Statement should not exist due to rollback
        found = StatementRepository.find_by_sha256(db_conn, "rollback_hash")
        assert found is None

    def test_cascade_delete_statement(self, db_conn):
        """Verify deleting a statement deletes all linked transactions via CASCADE."""
        acc = AccountRepository.get_or_create_default(db_conn)
        stmt = Statement(
            statement_id="stmt_cascade",
            account_id=acc.account_id,
            source_filename="del.csv",
            source_kind="csv",
            file_sha256="cascade_hash",
        )
        StatementRepository.insert(db_conn, stmt)

        txn = Transaction(
            txn_id="txn_cascade_1",
            statement_id=stmt.statement_id,
            account_id=acc.account_id,
            txn_date=date(2026, 1, 10),
            amount=Decimal("150.00"),
            direction="DEBIT",
            merchant="Uber",
            narration="UPI/UBER/123",
            category="Commute & Travel",
        )
        TransactionRepository.insert_bulk(db_conn, [txn])

        # Delete statement
        deleted = StatementRepository.delete_by_id(db_conn, stmt.statement_id)
        assert deleted is True

        # Transactions should also be gone
        txns = TransactionRepository.get_transactions(db_conn, statement_id=stmt.statement_id)
        assert len(txns) == 0

    def test_to_dataframe(self, db_conn):
        """Verify conversion to canonical DataFrame preserves types and columns."""
        acc = AccountRepository.get_or_create_default(db_conn)
        stmt = Statement(
            statement_id="stmt_df",
            account_id=acc.account_id,
            source_filename="df.csv",
            source_kind="csv",
            file_sha256="df_hash",
        )
        StatementRepository.insert(db_conn, stmt)

        txns = [
            Transaction(
                txn_id=f"txn_{i}",
                statement_id=stmt.statement_id,
                account_id=acc.account_id,
                txn_date=date(2026, 1, i + 1),
                amount=Decimal(f"{i * 100}.50"),
                direction="DEBIT",
                merchant=f"Merchant {i}",
                narration=f"Narration {i}",
                category="Food & Dining",
            )
            for i in range(1, 4)
        ]
        TransactionRepository.insert_bulk(db_conn, txns)
        loaded = TransactionRepository.get_transactions(db_conn)
        df = TransactionRepository.to_dataframe(loaded)

        expected_cols = ["date", "merchant", "narration", "category", "mode", "type", "amount"]
        assert list(df.columns) == expected_cols
        assert len(df) == 3
        assert isinstance(df.iloc[0]["amount"], Decimal)


class TestImportService:
    """Tests for end-to-end import service orchestration."""

    def test_import_csv_statement(self, db_conn, synthetic_hdfc_csv):
        """Verify importing a sample CSV statement into SQLite."""
        file_bytes = synthetic_hdfc_csv.read_bytes()

        result = ImportService.import_statement(
            file_bytes=file_bytes,
            filename="sample_hdfc_statement.csv",
            conn=db_conn,
        )

        assert result.success is True
        assert result.is_duplicate is False
        assert result.transactions_count > 0
        assert result.statement is not None

        # Re-importing same file should detect duplicate
        dup_result = ImportService.import_statement(
            file_bytes=file_bytes,
            filename="sample_hdfc_statement.csv",
            conn=db_conn,
        )
        assert dup_result.success is True
        assert dup_result.is_duplicate is True
        assert dup_result.transactions_count == result.transactions_count

    def test_import_pdf_statement(self, db_conn, synthetic_hdfc_pdf):
        """Verify importing a digital PDF statement into SQLite."""
        file_bytes = synthetic_hdfc_pdf.read_bytes()

        result = ImportService.import_statement(
            file_bytes=file_bytes,
            filename="sample_hdfc_statement.pdf",
            conn=db_conn,
        )

        assert result.success is True
        assert result.is_duplicate is False
        assert result.transactions_count > 0

    def test_import_locked_pdf(self, db_conn, synthetic_locked_pdf):
        """Verify locked PDF handles passwords properly in ImportService."""
        file_bytes = synthetic_locked_pdf.read_bytes()

        # Without password -> fail
        fail_res = ImportService.import_statement(
            file_bytes=file_bytes,
            filename="locked.pdf",
            conn=db_conn,
        )
        assert fail_res.success is False

        # With correct password -> succeed
        ok_res = ImportService.import_statement(
            file_bytes=file_bytes,
            filename="locked.pdf",
            password="password123",
            conn=db_conn,
        )
        assert ok_res.success is True
        assert ok_res.transactions_count > 0

"""Unit tests for OverridesService and manual category overrides.

Verifies:
1. Non-destructive category overrides and permanent preservation of original_category_id.
2. Immutable audit history logging in category_overrides_audit.
3. Category source tracking and clearing of applied_rule_id.
4. Validation guards rejecting invalid transaction IDs, invalid categories, and redundant edits.
5. Atomic transaction rollback if an error occurs.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import sqlite3
import pytest

from database.db import get_connection, run_migrations
from database.repositories import AccountRepository, StatementRepository, TransactionRepository
from modules.models import Statement, Transaction
from services.overrides_service import OverridesService


@pytest.fixture
def db_conn():
    """Create an in-memory SQLite database connection with all migrations applied."""
    conn = get_connection(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def seed_transaction(db_conn) -> str:
    """Helper to seed an account, statement, and an initial transaction."""
    acc = AccountRepository.get_or_create_default(db_conn, label="Primary Bank")
    stmt = Statement(
        statement_id="stmt_override_test",
        account_id=acc.account_id,
        source_filename="test_statement.csv",
        source_kind="csv",
        file_sha256="override_test_hash_001",
    )
    StatementRepository.insert(db_conn, stmt)

    txn = Transaction(
        txn_id="txn_override_101",
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
    db_conn.commit()
    return txn.txn_id


class TestOverridesService:
    """Test suite for manual category overrides and audit trail management."""

    def test_successful_manual_override(self, db_conn, seed_transaction):
        """Verify successful category override, source update, and rule ID clearing."""
        # Initial transaction has category 'food_dining'
        res = OverridesService.override_category(
            conn=db_conn,
            txn_id=seed_transaction,
            new_category_id="groceries",
            reason="Purchased grocery items via Swiggy Instamart",
        )

        assert res.success is True
        assert res.txn_id == seed_transaction
        assert res.previous_category_id == "food_dining"
        assert res.new_category_id == "groceries"
        assert res.original_category_id == "food_dining"
        assert res.category_source == "user_override"
        assert res.audit_id is not None

        # Verify transaction state directly from database
        txn = TransactionRepository.get_by_id(db_conn, seed_transaction)
        assert txn is not None
        assert txn.category == "Groceries & Essentials"
        assert txn.original_category_id == "food_dining"
        assert txn.category_source == "user_override"
        assert txn.applied_rule_id is None

    def test_original_category_never_overwritten_on_subsequent_overrides(self, db_conn, seed_transaction):
        """Verify original_category_id is permanently retained across multiple changes."""
        # 1st Override: food_dining -> shopping
        OverridesService.override_category(db_conn, seed_transaction, "shopping", reason="First correction")

        txn_after_1 = TransactionRepository.get_by_id(db_conn, seed_transaction)
        assert txn_after_1.original_category_id == "food_dining"
        assert txn_after_1.category == "Shopping & E-Com"

        # 2nd Override: shopping -> health
        OverridesService.override_category(db_conn, seed_transaction, "health", reason="Second correction")

        txn_after_2 = TransactionRepository.get_by_id(db_conn, seed_transaction)
        # Original category must STILL be 'food_dining', NOT 'shopping'!
        assert txn_after_2.original_category_id == "food_dining"
        assert txn_after_2.category == "Health & Medical"

    def test_audit_records_created_and_retrieved(self, db_conn, seed_transaction):
        """Verify immutable audit records are created for each change."""
        OverridesService.override_category(db_conn, seed_transaction, "shopping", reason="First edit")
        OverridesService.override_category(db_conn, seed_transaction, "utilities", reason="Second edit")

        history = OverridesService.get_audit_history(db_conn, txn_id=seed_transaction)
        assert len(history) == 2

        # Most recent first
        latest = history[0]
        assert latest.previous_category_id == "shopping"
        assert latest.new_category_id == "utilities"
        assert latest.reason == "Second edit"

        earliest = history[1]
        assert earliest.previous_category_id == "food_dining"
        assert earliest.new_category_id == "shopping"
        assert earliest.reason == "First edit"

    def test_invalid_transaction_id_rejected(self, db_conn):
        """Verify non-existent txn_id raises ValueError."""
        with pytest.raises(ValueError, match="Transaction 'txn_nonexistent' not found"):
            OverridesService.override_category(db_conn, "txn_nonexistent", "food_dining")

    def test_invalid_category_id_rejected(self, db_conn, seed_transaction):
        """Verify non-existent category_id raises ValueError."""
        with pytest.raises(ValueError, match="Category 'invalid_category_123' does not exist"):
            OverridesService.override_category(db_conn, seed_transaction, "invalid_category_123")

    def test_redundant_category_assignment_rejected(self, db_conn, seed_transaction):
        """Verify attempting to assign the same category raises ValueError."""
        with pytest.raises(ValueError, match="already assigned to category 'food_dining'"):
            OverridesService.override_category(db_conn, seed_transaction, "food_dining")

    def test_atomic_rollback_on_failure(self, db_conn, seed_transaction):
        """Verify that if an error occurs mid-operation, both transaction and audit log roll back."""
        # Force a database failure by creating a trigger that fails on insert into category_overrides_audit
        db_conn.execute(
            """
            CREATE TRIGGER fail_audit_insert BEFORE INSERT ON category_overrides_audit
            BEGIN
                SELECT RAISE(FAIL, 'Simulated audit log insertion failure');
            END;
            """
        )

        with pytest.raises(
            (sqlite3.IntegrityError, sqlite3.OperationalError),
            match="Simulated audit log insertion failure",
        ):
            OverridesService.override_category(db_conn, seed_transaction, "groceries")

        # Verify transaction was NOT updated (remains Food & Dining)
        txn = TransactionRepository.get_by_id(db_conn, seed_transaction)
        assert txn.category == "Food & Dining"
        assert txn.category_source == "auto"

        # Verify zero audit records were inserted
        history = OverridesService.get_audit_history(db_conn, seed_transaction)
        assert len(history) == 0

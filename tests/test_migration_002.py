"""Unit tests for Database Migration 002 and RulesRepository.

Verifies:
1. Migration 002 succeeds on top of an existing Phase 8 database without data loss.
2. Deterministic priority and tie-breaking for custom rules.
3. Regex validation and protection against malformed/vulnerable patterns.
4. CRUD operations on custom categorization rules.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3
import pytest

from database.db import get_connection, run_migrations
from database.repositories import AccountRepository, StatementRepository, TransactionRepository
from database.rules_repository import RulesRepository, validate_rule_pattern
from modules.models import CategorizationRule, Statement, Transaction


class TestMigration002OnPhase8Database:
    """Verifies that migration 002 safely upgrades an existing Phase 8 database."""

    def test_upgrade_from_phase8_database(self):
        """Simulate a Phase 8 database with existing records and apply migration 002."""
        conn = get_connection(":memory:")

        # 1. Manually apply ONLY migration 001 (Phase 8 state)
        m1_path = Path(__file__).resolve().parent.parent / "database" / "migrations" / "001_initial_schema.sql"
        conn.executescript(m1_path.read_text(encoding="utf-8"))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """
        )
        conn.execute("INSERT INTO schema_migrations VALUES (1, '001_initial_schema.sql', ?);", (datetime.now(timezone.utc).isoformat(),))
        conn.commit()

        # 2. Insert Phase 8 Account, Statement, and Transaction
        acc = AccountRepository.get_or_create_default(conn, label="Phase 8 Test Bank")
        stmt = Statement(
            statement_id="stmt_p8",
            account_id=acc.account_id,
            source_filename="p8_statement.csv",
            source_kind="csv",
            file_sha256="p8_hash_123",
        )
        StatementRepository.insert(conn, stmt)

        txn = Transaction(
            txn_id="txn_p8_1",
            statement_id=stmt.statement_id,
            account_id=acc.account_id,
            txn_date=date(2026, 1, 10),
            amount=Decimal("499.00"),
            direction="DEBIT",
            merchant="Swiggy",
            narration="UPI/SWIGGY/123",
            category="Food & Dining",
        )
        TransactionRepository.insert_bulk(conn, [txn])

        # 3. Apply pending migrations (should discover and run 002)
        applied = run_migrations(conn)
        assert applied == 1

        # 4. Verify migration tracking
        cursor = conn.execute("SELECT version, name FROM schema_migrations ORDER BY version ASC;")
        versions = cursor.fetchall()
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2

        # 5. Verify existing transaction record is intact and has new columns
        cursor = conn.execute("SELECT txn_id, amount_minor, original_category_id, category_source, applied_rule_id FROM transactions WHERE txn_id = 'txn_p8_1';")
        row = cursor.fetchone()
        assert row is not None
        assert row["txn_id"] == "txn_p8_1"
        assert row["amount_minor"] == 49900
        assert row["original_category_id"] is None
        assert row["category_source"] == "auto"
        assert row["applied_rule_id"] is None

        # 6. Verify categorization_rules and category_overrides_audit tables exist
        conn.execute("SELECT COUNT(*) FROM categorization_rules;").fetchone()
        conn.execute("SELECT COUNT(*) FROM category_overrides_audit;").fetchone()

        conn.close()


class TestRulesRepository:
    """Tests for custom categorization rule persistence and deterministic ordering."""

    @pytest.fixture
    def conn(self):
        c = get_connection(":memory:")
        run_migrations(c)
        yield c
        c.close()

    def test_create_and_get_rule(self, conn):
        """Verify creating and retrieving a custom rule."""
        rule = CategorizationRule(
            rule_id="rule_blue_tokai",
            pattern="Blue Tokai",
            pattern_type="merchant_exact",
            category_id="food_dining",
            priority=100,
            source="user",
        )
        RulesRepository.create_rule(conn, rule)

        fetched = RulesRepository.get_rule(conn, "rule_blue_tokai")
        assert fetched is not None
        assert fetched.pattern == "Blue Tokai"
        assert fetched.category_id == "food_dining"
        assert fetched.priority == 100
        assert fetched.source == "user"
        assert fetched.hit_count == 0
        assert fetched.is_active is True

    def test_deterministic_priority_and_tie_breaking(self, conn):
        """Verify rules are ordered strictly: priority DESC, pattern length DESC, created_at ASC."""
        # Rule 1: Normal priority 100
        r1 = CategorizationRule(rule_id="r1", pattern="Cafe", pattern_type="merchant_contains", category_id="food_dining", priority=100)
        # Rule 2: High priority 200 (should win over 100)
        r2 = CategorizationRule(rule_id="r2", pattern="Cafe", pattern_type="merchant_contains", category_id="others", priority=200)
        # Rule 3: Priority 100, longer pattern (should beat r1 in tie-break)
        r3 = CategorizationRule(rule_id="r3", pattern="Blue Tokai Cafe", pattern_type="merchant_contains", category_id="food_dining", priority=100)

        RulesRepository.create_rule(conn, r1)
        RulesRepository.create_rule(conn, r2)
        RulesRepository.create_rule(conn, r3)

        rules = RulesRepository.list_rules(conn, active_only=True)
        assert len(rules) == 3

        # 1st: r2 (priority 200)
        assert rules[0].rule_id == "r2"
        # 2nd: r3 (priority 100, pattern length 15 > 4)
        assert rules[1].rule_id == "r3"
        # 3rd: r1 (priority 100, pattern length 4)
        assert rules[2].rule_id == "r1"

    def test_update_and_delete_rule(self, conn):
        """Verify modifying and removing custom rules."""
        rule = CategorizationRule(
            rule_id="rule_temp",
            pattern="Old Pattern",
            pattern_type="merchant_contains",
            category_id="others",
        )
        RulesRepository.create_rule(conn, rule)

        # Update pattern and category
        updated = RulesRepository.update_rule(
            conn,
            rule_id="rule_temp",
            pattern="New Pattern",
            category_id="shopping",
            priority=150,
        )
        assert updated is True

        refetched = RulesRepository.get_rule(conn, "rule_temp")
        assert refetched.pattern == "New Pattern"
        assert refetched.category_id == "shopping"
        assert refetched.priority == 150

        # Delete rule
        deleted = RulesRepository.delete_rule(conn, "rule_temp")
        assert deleted is True
        assert RulesRepository.get_rule(conn, "rule_temp") is None

    def test_increment_hit_count(self, conn):
        """Verify incrementing match hit count."""
        rule = CategorizationRule(
            rule_id="rule_hit",
            pattern="Uber",
            pattern_type="merchant_exact",
            category_id="commute",
        )
        RulesRepository.create_rule(conn, rule)
        RulesRepository.increment_hit_count(conn, "rule_hit", count=3)

        refetched = RulesRepository.get_rule(conn, "rule_hit")
        assert refetched.hit_count == 3


class TestPatternValidation:
    """Tests for regex syntax validation and catastrophic backtracking protection."""

    def test_valid_patterns(self):
        """Verify normal patterns and valid regexes pass validation."""
        validate_rule_pattern("Swiggy", "merchant_exact")
        validate_rule_pattern("chai", "merchant_contains")
        validate_rule_pattern(r"^UPI.*SWIGGY.*$", "regex")

    def test_empty_pattern_rejected(self):
        """Verify empty patterns raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_rule_pattern("   ", "merchant_exact")

    def test_excessive_length_rejected(self):
        """Verify patterns over 200 chars raise ValueError."""
        with pytest.raises(ValueError, match="exceeds maximum allowed length"):
            validate_rule_pattern("a" * 201, "merchant_contains")

    def test_invalid_regex_syntax_rejected(self):
        """Verify broken regex raises ValueError."""
        with pytest.raises(ValueError, match="Invalid regular expression"):
            validate_rule_pattern("[unclosed_bracket", "regex")

    def test_catastrophic_backtracking_regex_rejected(self):
        """Verify dangerous nested quantifier regexes are rejected."""
        with pytest.raises(ValueError, match="nested quantifiers are not allowed"):
            validate_rule_pattern(r"(a+)+", "regex")

        with pytest.raises(ValueError, match="nested quantifiers are not allowed"):
            validate_rule_pattern(r"([0-9]*)*", "regex")

"""Unit tests for RulesService, rule evaluation, promotion, and persistence.

Verifies:
1. Deterministic rule evaluation across all 4 pattern types.
2. Tie-breaking rules: priority DESC, pattern length DESC, created_at ASC, rule_id ASC.
3. Creation and promotion of rules into SQLite.
4. Protection invariant: category_source == 'user_override' is NEVER overwritten.
5. Reversal invariant: deleting/inactivating a rule reverts transactions to original_category_id.
6. Integration with ImportService during statement ingestion.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import sqlite3
import pytest

from database.db import get_connection, run_migrations
from database.repositories import AccountRepository, StatementRepository, TransactionRepository
from database.rules_repository import RulesRepository
from modules.models import CategorizationRule, Statement, Transaction
from services.import_service import ImportService
from services.overrides_service import OverridesService
from services.rules_service import RulesService


@pytest.fixture
def db_conn():
    """Create an in-memory SQLite database connection with all migrations applied."""
    conn = get_connection(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def seed_account(db_conn) -> str:
    """Helper to seed a test bank account."""
    acc = AccountRepository.get_or_create_default(db_conn, label="Rules Test Bank")
    db_conn.commit()
    return acc.account_id


class TestRulesMatching:
    """Tests for pure pattern matching and deterministic priority."""

    def test_match_transaction_all_pattern_types(self):
        """Verify matching against merchant_exact, merchant_contains, narration_contains, and regex."""
        rules = [
            CategorizationRule(
                rule_id="r1",
                pattern="Blue Tokai Coffee",
                pattern_type="merchant_exact",
                category_id="food_dining",
                priority=100,
            ),
            CategorizationRule(
                rule_id="r2",
                pattern="metro",
                pattern_type="merchant_contains",
                category_id="commute",
                priority=100,
            ),
            CategorizationRule(
                rule_id="r3",
                pattern="electricity bill",
                pattern_type="narration_contains",
                category_id="utilities",
                priority=100,
            ),
            CategorizationRule(
                rule_id="r4",
                pattern=r"LIC\s*PREMIUM",
                pattern_type="regex",
                category_id="health",
                priority=100,
            ),
        ]

        # 1. Exact match (case-insensitive)
        m1 = RulesService.match_transaction("UPI/123/Blue Tokai", "blue tokai coffee", rules)
        assert m1 is not None and m1.rule_id == "r1"

        # 2. Substring in merchant
        m2 = RulesService.match_transaction("UPI/456/Maha Metro Rail", "Maha Metro Pune", rules)
        assert m2 is not None and m2.rule_id == "r2"

        # 3. Substring in narration
        m3 = RulesService.match_transaction("BESCOM Electricity Bill Payment", "Bescom", rules)
        assert m3 is not None and m3.rule_id == "r3"

        # 4. Regex in narration
        m4 = RulesService.match_transaction("NACH LIC PREMIUM PAYMENT 001", "Life Insurance", rules)
        assert m4 is not None and m4.rule_id == "r4"

        # 5. Unmatched
        m5 = RulesService.match_transaction("UPI/999/Unknown", "Random Store", rules)
        assert m5 is None

    def test_deterministic_priority_and_tie_breaking(self):
        """Verify higher priority wins, and pattern length breaks ties."""
        rules = [
            # Low priority broad rule
            CategorizationRule(
                rule_id="r_low",
                pattern="coffee",
                pattern_type="merchant_contains",
                category_id="others",
                priority=50,
            ),
            # High priority specific rule
            CategorizationRule(
                rule_id="r_high",
                pattern="Starbucks",
                pattern_type="merchant_exact",
                category_id="food_dining",
                priority=150,
            ),
            # Equal priority but longer pattern
            CategorizationRule(
                rule_id="r_long",
                pattern="Specialty Coffee Roasters",
                pattern_type="merchant_contains",
                category_id="shopping",
                priority=100,
            ),
            CategorizationRule(
                rule_id="r_short",
                pattern="Coffee",
                pattern_type="merchant_contains",
                category_id="food_dining",
                priority=100,
            ),
        ]

        # Sort deterministically
        sorted_rules = sorted(
            rules,
            key=lambda r: (-r.priority, -len(r.pattern), r.rule_id),
        )

        # 1. Priority 150 wins over 50
        match = RulesService.match_transaction("UPI/123", "Starbucks", sorted_rules)
        assert match.rule_id == "r_high"

        # 2. Longer pattern wins tie at priority 100
        match_tie = RulesService.match_transaction("UPI/456", "Specialty Coffee Roasters Indiranagar", sorted_rules)
        assert match_tie.rule_id == "r_long"


class TestRulesServiceWorkflow:
    """Tests for database persistence, application to transactions, and rollback."""

    def test_create_user_rule_and_apply_to_historical(self, db_conn, seed_account):
        """Verify creating a rule recategorizes matching historical transactions and updates hit count."""
        stmt = Statement(
            statement_id="stmt_rules_1",
            account_id=seed_account,
            source_filename="test.csv",
            source_kind="csv",
            file_sha256="hash_rules_1",
        )
        StatementRepository.insert(db_conn, stmt)

        txn1 = Transaction(
            txn_id="txn_rh_1",
            statement_id=stmt.statement_id,
            account_id=seed_account,
            txn_date=date(2026, 1, 10),
            amount=Decimal("150.00"),
            direction="DEBIT",
            merchant="Chai Point",
            narration="UPI/CHAIPOINT/01",
            category="Others & Misc",
            category_id="others",
        )
        txn2 = Transaction(
            txn_id="txn_rh_2",
            statement_id=stmt.statement_id,
            account_id=seed_account,
            txn_date=date(2026, 1, 11),
            amount=Decimal("200.00"),
            direction="DEBIT",
            merchant="Chai Point",
            narration="UPI/CHAIPOINT/02",
            category="Others & Misc",
            category_id="others",
        )
        TransactionRepository.insert_bulk(db_conn, [txn1, txn2])
        db_conn.commit()

        # Create rule for Chai Point -> Food & Dining
        rule, count = RulesService.create_rule(
            conn=db_conn,
            pattern="Chai Point",
            pattern_type="merchant_exact",
            category_id="food_dining",
            priority=100,
            apply_to_historical=True,
        )

        assert count == 2
        assert rule.rule_id is not None

        # Verify transaction 1 updated
        t1_after = TransactionRepository.get_by_id(db_conn, "txn_rh_1")
        assert t1_after.category == "Food & Dining"
        assert t1_after.category_id == "food_dining"
        assert t1_after.original_category_id == "others"
        assert t1_after.category_source == "rule"
        assert t1_after.applied_rule_id == rule.rule_id

        # Verify rule hit count
        persisted_rule = RulesRepository.get_rule(db_conn, rule.rule_id)
        assert persisted_rule.hit_count == 2

    def test_manual_overrides_never_overwritten_by_rules(self, db_conn, seed_account):
        """CRITICAL INVARIANT: Transactions with category_source == 'user_override' are NEVER touched by rules."""
        stmt = Statement(
            statement_id="stmt_rules_2",
            account_id=seed_account,
            source_filename="test.csv",
            source_kind="csv",
            file_sha256="hash_rules_2",
        )
        StatementRepository.insert(db_conn, stmt)

        # Transaction 1: Manual override by user
        txn_manual = Transaction(
            txn_id="txn_override_safe",
            statement_id=stmt.statement_id,
            account_id=seed_account,
            txn_date=date(2026, 1, 12),
            amount=Decimal("350.00"),
            direction="DEBIT",
            merchant="Specialty Store",
            narration="UPI/SPECIALTY/01",
            category="Food & Dining",
            category_id="food_dining",
        )
        # Transaction 2: Normal auto transaction
        txn_auto = Transaction(
            txn_id="txn_auto_normal",
            statement_id=stmt.statement_id,
            account_id=seed_account,
            txn_date=date(2026, 1, 13),
            amount=Decimal("450.00"),
            direction="DEBIT",
            merchant="Specialty Store",
            narration="UPI/SPECIALTY/02",
            category="Food & Dining",
            category_id="food_dining",
        )
        TransactionRepository.insert_bulk(db_conn, [txn_manual, txn_auto])
        db_conn.commit()

        # Apply manual override on txn_manual to 'shopping'
        OverridesService.override_category(db_conn, "txn_override_safe", "shopping", reason="User preference")

        # Now create an aggressive rule matching 'Specialty Store' -> 'groceries' with high priority
        rule, _ = RulesService.create_rule(
            conn=db_conn,
            pattern="Specialty Store",
            pattern_type="merchant_exact",
            category_id="groceries",
            priority=200,
            apply_to_historical=True,
        )

        # 1. Verify txn_auto WAS updated to groceries
        t_auto_after = TransactionRepository.get_by_id(db_conn, "txn_auto_normal")
        assert t_auto_after.category == "Groceries & Essentials"
        assert t_auto_after.category_source == "rule"
        assert t_auto_after.applied_rule_id == rule.rule_id

        # 2. Verify txn_manual was NOT updated, remains shopping with category_source = 'user_override'
        t_manual_after = TransactionRepository.get_by_id(db_conn, "txn_override_safe")
        assert t_manual_after.category == "Shopping & E-Com"
        assert t_manual_after.category_id == "shopping"
        assert t_manual_after.category_source == "user_override"
        assert t_manual_after.applied_rule_id is None

    def test_promote_override_to_rule(self, db_conn, seed_account):
        """Verify promoting a transaction into a rule converts it and recategorizes other matching rows."""
        stmt = Statement(
            statement_id="stmt_rules_3",
            account_id=seed_account,
            source_filename="test.csv",
            source_kind="csv",
            file_sha256="hash_rules_3",
        )
        StatementRepository.insert(db_conn, stmt)

        txn1 = Transaction(
            txn_id="txn_promo_1",
            statement_id=stmt.statement_id,
            account_id=seed_account,
            txn_date=date(2026, 1, 14),
            amount=Decimal("1200.00"),
            direction="DEBIT",
            merchant="Decathlon Sports",
            narration="UPI/DECATHLON/01",
            category="Others & Misc",
            category_id="others",
        )
        txn2 = Transaction(
            txn_id="txn_promo_2",
            statement_id=stmt.statement_id,
            account_id=seed_account,
            txn_date=date(2026, 1, 15),
            amount=Decimal("800.00"),
            direction="DEBIT",
            merchant="Decathlon Sports",
            narration="UPI/DECATHLON/02",
            category="Others & Misc",
            category_id="others",
        )
        TransactionRepository.insert_bulk(db_conn, [txn1, txn2])
        db_conn.commit()

        # Manually override txn1 to shopping
        OverridesService.override_category(db_conn, "txn_promo_1", "shopping")

        # Promote txn1 to reusable rule
        rule, count = RulesService.promote_override_to_rule(
            conn=db_conn,
            txn_id="txn_promo_1",
            pattern_type="merchant_exact",
        )

        assert rule.source == "promoted"
        assert rule.pattern == "Decathlon Sports"
        assert rule.category_id == "shopping"

        # Verify txn1 is now linked to rule
        t1 = TransactionRepository.get_by_id(db_conn, "txn_promo_1")
        assert t1.category_source == "rule"
        assert t1.applied_rule_id == rule.rule_id

        # Verify txn2 was also updated by the promoted rule
        t2 = TransactionRepository.get_by_id(db_conn, "txn_promo_2")
        assert t2.category == "Shopping & E-Com"
        assert t2.category_source == "rule"
        assert t2.applied_rule_id == rule.rule_id

    def test_delete_rule_reverts_transactions(self, db_conn, seed_account):
        """Verify deleting a rule reverts affected transactions to their original_category_id."""
        stmt = Statement(
            statement_id="stmt_rules_4",
            account_id=seed_account,
            source_filename="test.csv",
            source_kind="csv",
            file_sha256="hash_rules_4",
        )
        StatementRepository.insert(db_conn, stmt)

        txn = Transaction(
            txn_id="txn_revert_1",
            statement_id=stmt.statement_id,
            account_id=seed_account,
            txn_date=date(2026, 1, 16),
            amount=Decimal("500.00"),
            direction="DEBIT",
            merchant="Organic Mandi",
            narration="UPI/ORGANICMANDI/01",
            category="Others & Misc",
            category_id="others",
        )
        TransactionRepository.insert_bulk(db_conn, [txn])
        db_conn.commit()

        rule, _ = RulesService.create_rule(
            db_conn,
            pattern="Organic Mandi",
            pattern_type="merchant_exact",
            category_id="groceries",
            apply_to_historical=True,
        )

        t_applied = TransactionRepository.get_by_id(db_conn, "txn_revert_1")
        assert t_applied.category == "Groceries & Essentials"
        assert t_applied.original_category_id == "others"

        # Delete rule
        RulesService.delete_rule(db_conn, rule.rule_id, reapply=True)

        t_reverted = TransactionRepository.get_by_id(db_conn, "txn_revert_1")
        assert t_reverted.category == "Others & Misc"
        assert t_reverted.category_source == "auto"
        assert t_reverted.original_category_id is None
        assert t_reverted.applied_rule_id is None

    def test_toggle_rule_inactive_reverts_transactions(self, db_conn, seed_account):
        """Verify toggling is_active=False reverts transactions, and is_active=True reapplies."""
        stmt = Statement(
            statement_id="stmt_rules_5",
            account_id=seed_account,
            source_filename="test.csv",
            source_kind="csv",
            file_sha256="hash_rules_5",
        )
        StatementRepository.insert(db_conn, stmt)

        txn = Transaction(
            txn_id="txn_toggle_1",
            statement_id=stmt.statement_id,
            account_id=seed_account,
            txn_date=date(2026, 1, 17),
            amount=Decimal("1500.00"),
            direction="DEBIT",
            merchant="Cult Fit",
            narration="UPI/CULTFIT/01",
            category="Others & Misc",
            category_id="others",
        )
        TransactionRepository.insert_bulk(db_conn, [txn])
        db_conn.commit()

        rule, _ = RulesService.create_rule(
            db_conn,
            pattern="Cult Fit",
            pattern_type="merchant_exact",
            category_id="health",
            apply_to_historical=True,
        )

        t1 = TransactionRepository.get_by_id(db_conn, "txn_toggle_1")
        assert t1.category == "Health & Medical"

        # Inactivate rule
        RulesService.toggle_rule_active(db_conn, rule.rule_id, is_active=False, reapply=True)
        t_inactive = TransactionRepository.get_by_id(db_conn, "txn_toggle_1")
        assert t_inactive.category == "Others & Misc"
        assert t_inactive.category_source == "auto"

        # Reactivate rule
        RulesService.toggle_rule_active(db_conn, rule.rule_id, is_active=True, reapply=True)
        t_active = TransactionRepository.get_by_id(db_conn, "txn_toggle_1")
        assert t_active.category == "Health & Medical"
        assert t_active.category_source == "rule"

    def test_import_service_applies_active_rules(self, db_conn):
        """Verify statement import applies active custom rules during ingestion."""
        # Create an active rule for 'Fit Gym' -> Health
        rule, _ = RulesService.create_rule(
            db_conn,
            pattern="Fit Gym",
            pattern_type="merchant_contains",
            category_id="health",
            priority=100,
            apply_to_historical=False,
        )

        csv_content = (
            "Date,Narration,Debit,Credit\n"
            "18/01/2026,UPI/FIT GYM BANGALORE/987,2500.00,\n"
            "19/01/2026,UPI/SWIGGY/123,350.00,\n"
        ).encode("utf-8")

        res = ImportService.import_statement(
            file_bytes=csv_content,
            filename="gym_test.csv",
            conn=db_conn,
        )

        assert res.success is True
        assert res.transactions_count == 2

        txns = TransactionRepository.get_transactions(db_conn, statement_id=res.statement.statement_id)
        gym_txn = next(t for t in txns if "FIT GYM" in t.narration)
        assert gym_txn.category == "Health & Medical"
        assert gym_txn.category_source == "rule"
        assert gym_txn.applied_rule_id == rule.rule_id

        # Verify rule hit count was updated
        r_after = RulesRepository.get_rule(db_conn, rule.rule_id)
        assert r_after.hit_count >= 1

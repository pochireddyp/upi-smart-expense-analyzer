"""Service for custom categorization rules, deterministic matching, and rule promotion.

Orchestrates user-defined rule lifecycle:
1. Pattern validation and ReDoS safeguards.
2. Deterministic priority and tie-breaking resolution.
3. Promotion of manual overrides into persistent reusable rules.
4. Batch rule re-evaluation preserving manual overrides (category_source == 'user_override').
5. Bidirectional reversal upon rule deletion or inactivation.
"""

from datetime import datetime, timezone
import sqlite3
from typing import List, Optional, Tuple

from database.db import transaction_scope
from database.repositories import CATEGORY_ID_TO_NAME, CATEGORY_NAME_TO_ID, TransactionRepository
from database.rules_repository import RulesRepository, validate_rule_pattern
from modules.categorizer import clean_merchant_advanced, match_rules
from modules.models import CategorizationRule, Transaction


class RulesService:
    """Service orchestrating categorization rules, rule evaluation, and promotion."""

    @staticmethod
    def match_transaction(
        narration: str,
        merchant: str,
        active_rules: List[CategorizationRule],
    ) -> Optional[CategorizationRule]:
        """Evaluate a transaction against an ordered list of active rules.

        Rules are tested in deterministic priority order:
        - priority DESC
        - LENGTH(pattern) DESC
        - created_at ASC
        - rule_id ASC

        Pattern types supported:
        - 'merchant_exact': case-insensitive exact match of merchant name.
        - 'merchant_contains': case-insensitive substring of merchant name.
        - 'narration_contains': case-insensitive substring of narration.
        - 'regex': safe regular expression search on narration.

        Args:
            narration: Raw bank narration string.
            merchant: Cleaned merchant or payee name.
            active_rules: Pre-sorted list of active CategorizationRule entities.

        Returns:
            Optional[CategorizationRule]: First matching rule or None.
        """
        return match_rules(narration, merchant, active_rules)

    @classmethod
    def create_rule(
        cls,
        conn: sqlite3.Connection,
        pattern: str,
        pattern_type: str,
        category_id: str,
        priority: int = 100,
        source: str = "user",
        apply_to_historical: bool = True,
    ) -> Tuple[CategorizationRule, int]:
        """Create a new custom categorization rule and optionally reapply to existing records.

        Invariants:
        1. Pattern is validated against syntax errors and ReDoS vulnerabilities.
        2. Category ID must exist in categories table.
        3. Never overwrites transactions with category_source == 'user_override'.
        4. Preserves original_category_id permanently.

        Args:
            conn: Active SQLite connection.
            pattern: Match string or regex.
            pattern_type: One of ('merchant_exact', 'merchant_contains', 'narration_contains', 'regex').
            category_id: Target category_id.
            priority: Priority weighting (defaults to 100).
            source: Rule source ('user' or 'promoted').
            apply_to_historical: Whether to reapply rules across existing transactions.

        Returns:
            Tuple[CategorizationRule, int]: Persisted rule and number of modified transactions.

        Raises:
            ValueError: If pattern is invalid or category does not exist.
        """
        # Validate category exists
        cat_cur = conn.execute("SELECT category_id FROM categories WHERE category_id = ? LIMIT 1;", (category_id,))
        if not cat_cur.fetchone():
            raise ValueError(f"Category '{category_id}' does not exist.")

        # Validate pattern
        validate_rule_pattern(pattern, pattern_type)

        rule = CategorizationRule(
            rule_id="",
            pattern=pattern.strip(),
            pattern_type=pattern_type,
            category_id=category_id,
            priority=priority,
            source=source,
            hit_count=0,
            is_active=True,
        )

        with transaction_scope(conn):
            persisted_rule = RulesRepository.create_rule(conn, rule)

        updated_count = 0
        if apply_to_historical:
            updated_count = cls.reapply_all_rules(conn)

        return persisted_rule, updated_count

    @classmethod
    def promote_override_to_rule(
        cls,
        conn: sqlite3.Connection,
        txn_id: str,
        pattern: Optional[str] = None,
        pattern_type: str = "merchant_exact",
        category_id: Optional[str] = None,
        priority: int = 100,
    ) -> Tuple[CategorizationRule, int]:
        """Promote a transaction into a reusable categorization rule.

        Derives the pattern from the transaction if not explicitly supplied, creates
        a rule with source='promoted', and re-evaluates all historical records.

        Invariants:
        1. Strictly protects existing manual overrides from being modified.
        2. Converts the initiating transaction's category_source to 'rule' and links applied_rule_id.
        3. Re-applies all active rules to all non-manual transactions.

        Args:
            conn: Active SQLite connection.
            txn_id: Unique transaction ID being promoted.
            pattern: Optional explicit pattern. If None, derived from txn.merchant.
            pattern_type: Rule match type.
            category_id: Target category_id. If None, uses txn.category_id.
            priority: Priority weighting (defaults to 100).

        Returns:
            Tuple[CategorizationRule, int]: The newly created rule and total modified transactions.

        Raises:
            ValueError: If transaction is not found or pattern cannot be derived.
        """
        txn = TransactionRepository.get_by_id(conn, txn_id)
        if not txn:
            raise ValueError(f"Transaction '{txn_id}' not found.")

        # Determine pattern
        target_pattern = pattern.strip() if pattern else None
        if not target_pattern:
            if pattern_type in ("merchant_exact", "merchant_contains"):
                target_pattern = txn.merchant.strip() if txn.merchant else clean_merchant_advanced(txn.narration)
                if not target_pattern:
                    raise ValueError(f"Cannot derive a valid merchant pattern from transaction '{txn_id}'.")
            elif pattern_type in ("narration_contains", "regex"):
                raise ValueError(f"Pattern string must be explicitly provided for pattern_type '{pattern_type}'.")

        # Determine target category
        target_cat = category_id or getattr(txn, "category_id", None) or CATEGORY_NAME_TO_ID.get(txn.category, "others")

        # Validate category exists
        cat_cur = conn.execute("SELECT category_id FROM categories WHERE category_id = ? LIMIT 1;", (target_cat,))
        if not cat_cur.fetchone():
            raise ValueError(f"Category '{target_cat}' does not exist.")

        # Validate pattern
        validate_rule_pattern(target_pattern, pattern_type)

        rule = CategorizationRule(
            rule_id="",
            pattern=target_pattern,
            pattern_type=pattern_type,
            category_id=target_cat,
            priority=priority,
            source="promoted",
            hit_count=0,
            is_active=True,
        )

        with transaction_scope(conn):
            persisted_rule = RulesRepository.create_rule(conn, rule)
            # If the initiating transaction had category_source == 'user_override', update it to 'rule'
            conn.execute(
                """
                UPDATE transactions
                SET category_id = ?,
                    category_source = 'rule',
                    applied_rule_id = ?
                WHERE txn_id = ?;
                """,
                (target_cat, persisted_rule.rule_id, txn_id),
            )

        updated_count = cls.reapply_all_rules(conn)
        return persisted_rule, updated_count

    @classmethod
    def reapply_all_rules(cls, conn: sqlite3.Connection) -> int:
        """Re-evaluate all active categorization rules across non-overridden transactions.

        Invariants:
        1. CRITICAL: Transactions with category_source == 'user_override' are NEVER touched.
        2. Preserves original_category_id permanently when applying a rule for the first time.
        3. If an existing rule is deleted or no longer matches, reverts the transaction
           to original_category_id and resets category_source to 'auto'.
        4. Updates hit_count on all categorization rules to reflect live database state.

        Args:
            conn: Active SQLite connection.

        Returns:
            int: Total count of modified transactions.
        """
        active_rules = RulesRepository.list_rules(conn, active_only=True)

        cursor = conn.execute(
            """
            SELECT txn_id, narration, merchant, direction, category_id, original_category_id,
                   category_source, applied_rule_id
            FROM transactions
            WHERE category_source != 'user_override';
            """
        )
        rows = cursor.fetchall()
        updated_count = 0

        with transaction_scope(conn):
            for row in rows:
                txn_id = row["txn_id"]
                narration = row["narration"]
                merchant = row["merchant"]
                curr_cat = row["category_id"]
                orig_cat = row["original_category_id"]
                curr_source = row["category_source"]
                curr_rule_id = row["applied_rule_id"]

                matched_rule = cls.match_transaction(narration, merchant, active_rules)

                if matched_rule is not None:
                    # A rule matches
                    target_cat = matched_rule.category_id
                    target_rule_id = matched_rule.rule_id

                    # Only update if category, rule, or source is changing
                    if curr_cat != target_cat or curr_rule_id != target_rule_id or curr_source != "rule":
                        # Preserve original auto category if not already recorded
                        preserved_orig = orig_cat if orig_cat else curr_cat

                        conn.execute(
                            """
                            UPDATE transactions
                            SET category_id = ?,
                                original_category_id = ?,
                                category_source = 'rule',
                                applied_rule_id = ?
                            WHERE txn_id = ?;
                            """,
                            (target_cat, preserved_orig, target_rule_id, txn_id),
                        )
                        updated_count += 1
                else:
                    # No active rule matches
                    if curr_source == "rule":
                        # Transaction was previously modified by a rule that is no longer active
                        # Revert back to original category
                        restored_cat = orig_cat if orig_cat else curr_cat

                        conn.execute(
                            """
                            UPDATE transactions
                            SET category_id = ?,
                                original_category_id = NULL,
                                category_source = 'auto',
                                applied_rule_id = NULL
                            WHERE txn_id = ?;
                            """,
                            (restored_cat, txn_id),
                        )
                        updated_count += 1

            # Recalculate hit_count for all rules based on live transaction state
            conn.execute(
                """
                UPDATE categorization_rules
                SET hit_count = (
                    SELECT COUNT(*)
                    FROM transactions
                    WHERE transactions.applied_rule_id = categorization_rules.rule_id
                );
                """
            )

        return updated_count

    @classmethod
    def delete_rule(cls, conn: sqlite3.Connection, rule_id: str, reapply: bool = True) -> int:
        """Delete a rule and optionally reapply rules to revert affected transactions.

        Args:
            conn: Active SQLite connection.
            rule_id: Rule ID to delete.
            reapply: Whether to reapply remaining active rules immediately.

        Returns:
            int: Number of transactions updated during reapplication.
        """
        with transaction_scope(conn):
            # 1. Safely revert transactions governed by this rule
            conn.execute(
                """
                UPDATE transactions
                SET category_id = COALESCE(original_category_id, category_id),
                    original_category_id = NULL,
                    category_source = 'auto',
                    applied_rule_id = NULL
                WHERE applied_rule_id = ?;
                """,
                (rule_id,),
            )
            # 2. Delete the rule record
            RulesRepository.delete_rule(conn, rule_id)

        if reapply:
            return cls.reapply_all_rules(conn)
        return 0

    @classmethod
    def toggle_rule_active(cls, conn: sqlite3.Connection, rule_id: str, is_active: bool, reapply: bool = True) -> int:
        """Enable or disable a rule and optionally re-evaluate transactions.

        Args:
            conn: Active SQLite connection.
            rule_id: Rule ID to update.
            is_active: Target active state.
            reapply: Whether to reapply rules immediately.

        Returns:
            int: Number of transactions updated during reapplication.
        """
        with transaction_scope(conn):
            RulesRepository.update_rule(conn, rule_id, is_active=is_active)

        if reapply:
            return cls.reapply_all_rules(conn)
        return 0

    @classmethod
    def list_rules(cls, conn: sqlite3.Connection, active_only: bool = False) -> List[CategorizationRule]:
        """List rules with deterministic ordering."""
        return RulesRepository.list_rules(conn, active_only=active_only)

"""Repository for managing custom and promoted categorization rules.

Provides CRUD operations, safe regex validation, and deterministic rule
ordering (by priority DESC, pattern length DESC, and created_at ASC).
"""

from datetime import datetime, timezone
import re
import sqlite3
from typing import List, Optional
import uuid

from modules.models import CategorizationRule


def validate_rule_pattern(pattern: str, pattern_type: str) -> None:
    """Validate pattern string for correctness and regex safety.

    Args:
        pattern: Pattern text or regex.
        pattern_type: One of 'merchant_exact', 'merchant_contains', 'narration_contains', 'regex'.

    Raises:
        ValueError: If pattern is empty, too long, or an invalid/vulnerable regex.
    """
    if not pattern or not pattern.strip():
        raise ValueError("Rule pattern cannot be empty.")

    clean_pattern = pattern.strip()
    if len(clean_pattern) > 200:
        raise ValueError("Rule pattern exceeds maximum allowed length of 200 characters.")

    if pattern_type == "regex":
        try:
            re.compile(clean_pattern)
        except re.error as e:
            raise ValueError(f"Invalid regular expression syntax: {e}")

        # Protect against nested quantifiers that cause catastrophic backtracking (e.g. (a+)+ or (.*)+)
        if re.search(r"\([^)]*[\*\+\?]\)[\*\+\{]", clean_pattern):
            raise ValueError("Unsafe regex pattern: nested quantifiers are not allowed.")


class RulesRepository:
    """Data access repository for custom categorization rules."""

    @staticmethod
    def create_rule(conn: sqlite3.Connection, rule: CategorizationRule) -> CategorizationRule:
        """Insert a new categorization rule into SQLite.

        Args:
            conn: Active SQLite connection.
            rule: CategorizationRule instance.

        Returns:
            CategorizationRule: Persisted rule.
        """
        validate_rule_pattern(rule.pattern, rule.pattern_type)
        now_iso = rule.created_at.isoformat() if rule.created_at else datetime.now(timezone.utc).isoformat()
        rule_id = rule.rule_id or f"rule_{uuid.uuid4().hex[:12]}"

        conn.execute(
            """
            INSERT INTO categorization_rules (
                rule_id, pattern, pattern_type, category_id, priority,
                source, hit_count, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                rule_id,
                rule.pattern.strip(),
                rule.pattern_type,
                rule.category_id,
                rule.priority,
                rule.source,
                rule.hit_count,
                1 if rule.is_active else 0,
                now_iso,
                now_iso,
            ),
        )
        rule.rule_id = rule_id
        rule.created_at = datetime.fromisoformat(now_iso)
        rule.updated_at = datetime.fromisoformat(now_iso)
        return rule

    @staticmethod
    def get_rule(conn: sqlite3.Connection, rule_id: str) -> Optional[CategorizationRule]:
        """Fetch a single rule by rule_id."""
        cursor = conn.execute("SELECT * FROM categorization_rules WHERE rule_id = ? LIMIT 1;", (rule_id,))
        row = cursor.fetchone()
        if not row:
            return None

        return CategorizationRule(
            rule_id=row["rule_id"],
            pattern=row["pattern"],
            pattern_type=row["pattern_type"],
            category_id=row["category_id"],
            priority=row["priority"],
            source=row["source"],
            hit_count=row["hit_count"],
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    @staticmethod
    def list_rules(conn: sqlite3.Connection, active_only: bool = True) -> List[CategorizationRule]:
        """List rules with deterministic priority and tie-breaking.

        Rules are ordered by:
        1. priority DESC (higher priority evaluated first)
        2. LENGTH(pattern) DESC (longer, more specific patterns win in tie)
        3. created_at ASC (earlier rules win in tie)
        4. rule_id ASC (strict deterministic tie-breaker)
        """
        query = "SELECT * FROM categorization_rules"
        params = []
        if active_only:
            query += " WHERE is_active = 1"

        query += " ORDER BY priority DESC, LENGTH(pattern) DESC, created_at ASC, rule_id ASC;"

        cursor = conn.execute(query, params)
        rules = []
        for row in cursor.fetchall():
            rules.append(
                CategorizationRule(
                    rule_id=row["rule_id"],
                    pattern=row["pattern"],
                    pattern_type=row["pattern_type"],
                    category_id=row["category_id"],
                    priority=row["priority"],
                    source=row["source"],
                    hit_count=row["hit_count"],
                    is_active=bool(row["is_active"]),
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                    updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
                )
            )
        return rules

    @staticmethod
    def update_rule(
        conn: sqlite3.Connection,
        rule_id: str,
        pattern: Optional[str] = None,
        pattern_type: Optional[str] = None,
        category_id: Optional[str] = None,
        priority: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        """Update an existing categorization rule."""
        existing = RulesRepository.get_rule(conn, rule_id)
        if not existing:
            return False

        new_pattern = pattern.strip() if pattern is not None else existing.pattern
        new_type = pattern_type if pattern_type is not None else existing.pattern_type
        validate_rule_pattern(new_pattern, new_type)

        new_cat = category_id if category_id is not None else existing.category_id
        new_prio = priority if priority is not None else existing.priority
        new_active = 1 if (is_active if is_active is not None else existing.is_active) else 0
        now_iso = datetime.now(timezone.utc).isoformat()

        cursor = conn.execute(
            """
            UPDATE categorization_rules
            SET pattern = ?, pattern_type = ?, category_id = ?, priority = ?, is_active = ?, updated_at = ?
            WHERE rule_id = ?;
            """,
            (new_pattern, new_type, new_cat, new_prio, new_active, now_iso, rule_id),
        )
        return cursor.rowcount > 0

    @staticmethod
    def delete_rule(conn: sqlite3.Connection, rule_id: str) -> bool:
        """Permanently delete a categorization rule."""
        conn.execute("UPDATE transactions SET applied_rule_id = NULL WHERE applied_rule_id = ?;", (rule_id,))
        cursor = conn.execute("DELETE FROM categorization_rules WHERE rule_id = ?;", (rule_id,))
        return cursor.rowcount > 0

    @staticmethod
    def increment_hit_count(conn: sqlite3.Connection, rule_id: str, count: int = 1) -> None:
        """Increment hit count for a rule upon being matched."""
        conn.execute(
            "UPDATE categorization_rules SET hit_count = hit_count + ? WHERE rule_id = ?;",
            (count, rule_id),
        )

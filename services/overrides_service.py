"""Service for manual category overrides and audit logging.

Provides atomic, non-destructive category modifications with permanent
preservation of the original auto-detected category and an immutable audit trail.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from typing import List, Optional
import uuid

from database.db import transaction_scope


@dataclass
class OverrideResult:
    """Encapsulates the result of a manual category override."""

    success: bool
    txn_id: str
    previous_category_id: str
    new_category_id: str
    original_category_id: str
    category_source: str = "user_override"
    audit_id: Optional[str] = None
    reason: Optional[str] = None
    changed_at: Optional[datetime] = None


@dataclass
class CategoryOverrideAudit:
    """Represents an immutable audit log record for a category modification."""

    audit_id: str
    txn_id: str
    previous_category_id: Optional[str]
    new_category_id: str
    reason: Optional[str]
    changed_at: datetime


class OverridesService:
    """Service orchestrating manual category overrides and audit log persistence."""

    @classmethod
    def override_category(
        cls,
        conn: sqlite3.Connection,
        txn_id: str,
        new_category_id: str,
        reason: Optional[str] = None,
    ) -> OverrideResult:
        """Manually override a transaction's category with full audit preservation.

        Invariants:
        1. original_category_id is permanently preserved and never overwritten.
        2. category_source is set to 'user_override'.
        3. applied_rule_id is reset to NULL.
        4. Transaction update and audit record insertion occur atomically.
        5. Validates existence of both transaction and target category.
        6. Rejects redundant / identical category updates.

        Args:
            conn: Active SQLite connection.
            txn_id: Unique transaction ID to recategorize.
            new_category_id: Target category_id (e.g. 'food_dining', 'groceries').
            reason: Optional user explanation for the change.

        Returns:
            OverrideResult: Details of the applied override.

        Raises:
            ValueError: If transaction or category does not exist, or if change is redundant.
        """
        # 1. Validate transaction exists
        txn_cursor = conn.execute(
            """
            SELECT txn_id, category_id, original_category_id, category_source
            FROM transactions
            WHERE txn_id = ?
            LIMIT 1;
            """,
            (txn_id,),
        )
        txn_row = txn_cursor.fetchone()
        if not txn_row:
            raise ValueError(f"Transaction '{txn_id}' not found.")

        current_cat = txn_row["category_id"]
        existing_orig_cat = txn_row["original_category_id"]

        # 2. Validate target category exists
        cat_cursor = conn.execute(
            "SELECT category_id, name FROM categories WHERE category_id = ? LIMIT 1;",
            (new_category_id,),
        )
        cat_row = cat_cursor.fetchone()
        if not cat_row:
            raise ValueError(f"Category '{new_category_id}' does not exist.")

        # 3. Prevent redundant category assignment
        if current_cat == new_category_id:
            raise ValueError(
                f"Transaction '{txn_id}' is already assigned to category '{new_category_id}'."
            )

        # 4. Preserve original_category_id permanently
        # If original_category_id is not yet set, record current_cat as the original.
        # If it is already set from a previous override, keep it intact forever.
        orig_to_preserve = existing_orig_cat if existing_orig_cat else current_cat

        audit_id = f"aud_{uuid.uuid4().hex[:12]}"
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        # 5. Atomic transaction scope for update + audit log
        with transaction_scope(conn):
            # Update transaction record
            conn.execute(
                """
                UPDATE transactions
                SET category_id = ?,
                    original_category_id = ?,
                    category_source = 'user_override',
                    applied_rule_id = NULL
                WHERE txn_id = ?;
                """,
                (new_category_id, orig_to_preserve, txn_id),
            )

            # Insert immutable audit record
            conn.execute(
                """
                INSERT INTO category_overrides_audit (
                    audit_id, txn_id, previous_category_id, new_category_id, reason, changed_at
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (audit_id, txn_id, current_cat, new_category_id, reason, now_iso),
            )

        return OverrideResult(
            success=True,
            txn_id=txn_id,
            previous_category_id=current_cat,
            new_category_id=new_category_id,
            original_category_id=orig_to_preserve,
            category_source="user_override",
            audit_id=audit_id,
            reason=reason,
            changed_at=now_dt,
        )

    @classmethod
    def get_audit_history(
        cls,
        conn: sqlite3.Connection,
        txn_id: Optional[str] = None,
    ) -> List[CategoryOverrideAudit]:
        """Fetch audit log records, optionally filtered by txn_id.

        Args:
            conn: Active SQLite connection.
            txn_id: Optional transaction ID filter.

        Returns:
            List[CategoryOverrideAudit]: Audit log entries ordered chronologically descending.
        """
        query = "SELECT * FROM category_overrides_audit"
        params = []
        if txn_id:
            query += " WHERE txn_id = ?"
            params.append(txn_id)

        query += " ORDER BY changed_at DESC, rowid DESC;"

        cursor = conn.execute(query, params)
        records = []
        for row in cursor.fetchall():
            records.append(
                CategoryOverrideAudit(
                    audit_id=row["audit_id"],
                    txn_id=row["txn_id"],
                    previous_category_id=row["previous_category_id"],
                    new_category_id=row["new_category_id"],
                    reason=row["reason"],
                    changed_at=datetime.fromisoformat(row["changed_at"]),
                )
            )
        return records

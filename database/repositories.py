"""Data access repositories for Accounts, Statements, and Transactions.

Provides strictly parameterized SQL queries, integer paise monetary conversions,
and seamless mapping between SQLite rows, domain models, and canonical DataFrames.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import sqlite3
from typing import List, Optional
import uuid

import pandas as pd

from modules.models import Account, Statement, Transaction
from modules.money import from_paise, to_paise


class AccountRepository:
    """Repository for managing bank accounts."""

    @staticmethod
    def get_or_create_default(
        conn: sqlite3.Connection,
        label: str = "Primary Bank Account",
        bank_name: Optional[str] = None,
        account_last4: Optional[str] = None,
    ) -> Account:
        """Fetch the primary default account, or create one if none exists."""
        cursor = conn.execute("SELECT * FROM accounts ORDER BY created_at ASC LIMIT 1;")
        row = cursor.fetchone()
        if row:
            return Account(
                account_id=row["account_id"],
                label=row["label"],
                bank_name=row["bank_name"],
                account_last4=row["account_last4"],
                account_type=row["account_type"],
                currency=row["currency"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            )

        # Create new default account
        acc_id = f"acc_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO accounts (account_id, label, bank_name, account_last4, account_type, currency, created_at)
            VALUES (?, ?, ?, ?, 'savings', 'INR', ?);
            """,
            (acc_id, label, bank_name, account_last4, now_iso),
        )
        return Account(
            account_id=acc_id,
            label=label,
            bank_name=bank_name,
            account_last4=account_last4,
            account_type="savings",
            currency="INR",
            created_at=datetime.fromisoformat(now_iso),
        )

    @staticmethod
    def list_accounts(conn: sqlite3.Connection) -> List[Account]:
        """List all registered bank accounts."""
        cursor = conn.execute("SELECT * FROM accounts ORDER BY label ASC;")
        accounts = []
        for row in cursor.fetchall():
            accounts.append(
                Account(
                    account_id=row["account_id"],
                    label=row["label"],
                    bank_name=row["bank_name"],
                    account_last4=row["account_last4"],
                    account_type=row["account_type"],
                    currency=row["currency"],
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                )
            )
        return accounts


class StatementRepository:
    """Repository for managing imported statement records and duplicate detection."""

    @staticmethod
    def find_by_sha256(conn: sqlite3.Connection, file_sha256: str) -> Optional[Statement]:
        """Check if a file with this exact SHA-256 hash has already been imported."""
        cursor = conn.execute(
            "SELECT * FROM statements WHERE file_sha256 = ? LIMIT 1;",
            (file_sha256,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return Statement(
            statement_id=row["statement_id"],
            account_id=row["account_id"],
            source_filename=row["source_filename"],
            source_kind=row["source_kind"],
            file_sha256=row["file_sha256"],
            period_start=date.fromisoformat(row["period_start"]) if row["period_start"] else None,
            period_end=date.fromisoformat(row["period_end"]) if row["period_end"] else None,
            row_count=row["row_count"],
            imported_count=row["imported_count"],
            skipped_count=row["skipped_count"],
            imported_at=datetime.fromisoformat(row["imported_at"]) if row["imported_at"] else None,
        )

    @staticmethod
    def insert(conn: sqlite3.Connection, stmt: Statement) -> Statement:
        """Insert a statement record into the database."""
        now_iso = stmt.imported_at.isoformat() if stmt.imported_at else datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO statements (
                statement_id, account_id, source_filename, source_kind, file_sha256,
                period_start, period_end, row_count, imported_count, skipped_count, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                stmt.statement_id,
                stmt.account_id,
                stmt.source_filename,
                stmt.source_kind,
                stmt.file_sha256,
                stmt.period_start.isoformat() if stmt.period_start else None,
                stmt.period_end.isoformat() if stmt.period_end else None,
                stmt.row_count,
                stmt.imported_count,
                stmt.skipped_count,
                now_iso,
            ),
        )
        stmt.imported_at = datetime.fromisoformat(now_iso)
        return stmt

    @staticmethod
    def list_statements(conn: sqlite3.Connection) -> List[Statement]:
        """List all statements ordered by import date descending."""
        cursor = conn.execute("SELECT * FROM statements ORDER BY imported_at DESC;")
        statements = []
        for row in cursor.fetchall():
            statements.append(
                Statement(
                    statement_id=row["statement_id"],
                    account_id=row["account_id"],
                    source_filename=row["source_filename"],
                    source_kind=row["source_kind"],
                    file_sha256=row["file_sha256"],
                    period_start=date.fromisoformat(row["period_start"]) if row["period_start"] else None,
                    period_end=date.fromisoformat(row["period_end"]) if row["period_end"] else None,
                    row_count=row["row_count"],
                    imported_count=row["imported_count"],
                    skipped_count=row["skipped_count"],
                    imported_at=datetime.fromisoformat(row["imported_at"]) if row["imported_at"] else None,
                )
            )
        return statements

    @staticmethod
    def delete_by_id(conn: sqlite3.Connection, statement_id: str) -> bool:
        """Delete a statement and cascade-delete all its transactions."""
        cursor = conn.execute("DELETE FROM statements WHERE statement_id = ?;", (statement_id,))
        return cursor.rowcount > 0


CATEGORY_NAME_TO_ID = {
    "Food & Dining": "food_dining",
    "Groceries & Essentials": "groceries",
    "Shopping & E-Com": "shopping",
    "Utilities & Bills": "utilities",
    "Commute & Travel": "commute",
    "Entertainment & Subs": "entertainment",
    "Health & Medical": "health",
    "Rent & Housing": "housing",
    "Salary & Income": "salary",
    "Peer Transfers": "transfers",
    "Others & Misc": "others",
}

CATEGORY_ID_TO_NAME = {v: k for k, v in CATEGORY_NAME_TO_ID.items()}


class TransactionRepository:
    """Repository for managing financial transactions with paise precision."""

    @staticmethod
    def insert_bulk(conn: sqlite3.Connection, transactions: List[Transaction]) -> int:
        """Bulk insert transactions within a single atomic batch."""
        if not transactions:
            return 0

        rows_to_insert = []
        now_iso = datetime.now(timezone.utc).isoformat()

        # Check if migration 002 tracking columns exist in transactions table
        cursor = conn.execute("PRAGMA table_info(transactions);")
        col_names = {row["name"] for row in cursor.fetchall()}
        has_v2_cols = "original_category_id" in col_names

        for t in transactions:
            # Convert Decimal amount to integer minor units (paise)
            paise_amount = to_paise(t.amount)
            # Map human-readable category name or ID
            cat_id = getattr(t, "category_id", None) or CATEGORY_NAME_TO_ID.get(
                t.category, t.category if t.category in CATEGORY_ID_TO_NAME else "others"
            )
            base_row = [
                t.txn_id,
                t.statement_id,
                t.account_id,
                t.txn_date.isoformat(),
                paise_amount,
                "INR",
                t.direction,
                t.merchant,
                t.narration,
                cat_id,
                t.mode,
                t.txn_type,
                t.status,
                t.fingerprint or t.txn_id,
                t.created_at.isoformat() if t.created_at else now_iso,
            ]
            if has_v2_cols:
                base_row.extend([
                    t.original_category_id,
                    t.category_source if t.category_source else "auto",
                    t.applied_rule_id,
                ])
            rows_to_insert.append(tuple(base_row))

        if has_v2_cols:
            conn.executemany(
                """
                INSERT INTO transactions (
                    txn_id, statement_id, account_id, txn_date, amount_minor, currency,
                    direction, merchant, narration, category_id, mode, txn_type,
                    status, fingerprint, created_at, original_category_id, category_source, applied_rule_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                rows_to_insert,
            )
        else:
            conn.executemany(
                """
                INSERT INTO transactions (
                    txn_id, statement_id, account_id, txn_date, amount_minor, currency,
                    direction, merchant, narration, category_id, mode, txn_type,
                    status, fingerprint, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                rows_to_insert,
            )
        return len(rows_to_insert)

    @staticmethod
    def get_transactions(
        conn: sqlite3.Connection,
        account_id: Optional[str] = None,
        statement_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Transaction]:
        """Query transactions with optional filtering and joined category names."""
        query = """
            SELECT t.*, c.name AS category_name
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.category_id
            WHERE 1=1
        """
        params = []

        if account_id:
            query += " AND t.account_id = ?"
            params.append(account_id)
        if statement_id:
            query += " AND t.statement_id = ?"
            params.append(statement_id)
        if start_date:
            query += " AND t.txn_date >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND t.txn_date <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY t.txn_date DESC, t.created_at DESC;"

        cursor = conn.execute(query, params)
        transactions = []

        for row in cursor.fetchall():
            # Convert integer paise back to Decimal amount
            rupee_amount = from_paise(row["amount_minor"])
            txn_date = date.fromisoformat(row["txn_date"])
            category = row["category_name"] or CATEGORY_ID_TO_NAME.get(row["category_id"], "Others & Misc")

            transactions.append(
                Transaction(
                    txn_id=row["txn_id"],
                    statement_id=row["statement_id"],
                    account_id=row["account_id"],
                    txn_date=txn_date,
                    amount=rupee_amount,
                    direction=row["direction"],
                    merchant=row["merchant"],
                    narration=row["narration"],
                    category=category,
                    mode=row["mode"],
                    txn_type=row["txn_type"],
                    status=row["status"],
                    fingerprint=row["fingerprint"],
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                    original_category_id=row["original_category_id"] if "original_category_id" in row.keys() else None,
                    category_source=row["category_source"] if "category_source" in row.keys() else "auto",
                    applied_rule_id=row["applied_rule_id"] if "applied_rule_id" in row.keys() else None,
                    category_id=row["category_id"],
                )
            )
        return transactions

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, txn_id: str) -> Optional[Transaction]:
        """Fetch a single transaction domain entity by txn_id."""
        query = """
            SELECT t.*, c.name AS category_name
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.category_id
            WHERE t.txn_id = ?
            LIMIT 1;
        """
        cursor = conn.execute(query, (txn_id,))
        row = cursor.fetchone()
        if not row:
            return None

        rupee_amount = from_paise(row["amount_minor"])
        txn_date = date.fromisoformat(row["txn_date"])
        category = row["category_name"] or CATEGORY_ID_TO_NAME.get(row["category_id"], "Others & Misc")

        return Transaction(
            txn_id=row["txn_id"],
            statement_id=row["statement_id"],
            account_id=row["account_id"],
            txn_date=txn_date,
            amount=rupee_amount,
            direction=row["direction"],
            merchant=row["merchant"],
            narration=row["narration"],
            category=category,
            mode=row["mode"],
            txn_type=row["txn_type"],
            status=row["status"],
            fingerprint=row["fingerprint"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            original_category_id=row["original_category_id"] if "original_category_id" in row.keys() else None,
            category_source=row["category_source"] if "category_source" in row.keys() else "auto",
            applied_rule_id=row["applied_rule_id"] if "applied_rule_id" in row.keys() else None,
            category_id=row["category_id"],
        )

    @staticmethod
    def to_dataframe(transactions: List[Transaction], include_metadata: bool = False) -> pd.DataFrame:
        """Convert a list of Transaction domain entities into the canonical DataFrame.

        Args:
            transactions: List of Transaction domain models.
            include_metadata: If True, includes internal columns (txn_id, account_id,
                category_source, applied_rule_id, original_category_id, category_id)
                needed by UI management workflows. If False, returns the canonical
                7 public financial columns.
        """
        if not transactions:
            cols = ["date", "merchant", "narration", "category", "mode", "type", "amount"]
            if include_metadata:
                cols.extend(["txn_id", "account_id", "category_source", "applied_rule_id", "original_category_id", "category_id"])
            return pd.DataFrame(columns=cols)

        records = []
        for t in transactions:
            row_dict = {
                "date": t.txn_date,
                "merchant": t.merchant,
                "narration": t.narration,
                "category": t.category,
                "mode": t.mode,
                "type": t.direction,
                "amount": t.amount,  # Decimal
            }
            if include_metadata:
                row_dict["txn_id"] = t.txn_id
                row_dict["account_id"] = t.account_id
                row_dict["category_source"] = t.category_source
                row_dict["applied_rule_id"] = t.applied_rule_id
                row_dict["original_category_id"] = t.original_category_id
                row_dict["category_id"] = getattr(t, "category_id", None)
            records.append(row_dict)

        df = pd.DataFrame(records)
        return df.sort_values(by="date", ascending=False).reset_index(drop=True)

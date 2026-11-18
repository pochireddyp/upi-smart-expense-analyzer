"""Statement Import and Ingestion Service.

Orchestrates statement parsing (CSV/PDF), SHA-256 duplicate detection,
account resolution, and atomic database persistence inside SQLite.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
from typing import Any, Optional
import uuid

import pandas as pd

from database.db import get_connection, transaction_scope
from database.repositories import AccountRepository, CATEGORY_ID_TO_NAME, StatementRepository, TransactionRepository
from database.rules_repository import RulesRepository
from modules.categorizer import categorize_transaction
from modules.csv_parser import parse_csv_statement
from modules.models import Statement, Transaction
from modules.pdf_parser import parse_pdf_statement
from services.rules_service import RulesService


# Maximum allowed statement upload size (10 MB)
MAX_UPLOAD_SIZE_MB: int = 10
MAX_UPLOAD_SIZE_BYTES: int = MAX_UPLOAD_SIZE_MB * 1024 * 1024


@dataclass
class ImportResult:
    """Encapsulates the result of a statement import operation."""

    success: bool
    statement: Optional[Statement] = None
    transactions_count: int = 0
    is_duplicate: bool = False
    error_message: Optional[str] = None
    parse_result: Optional[Any] = None


class ImportService:
    """Service orchestrating statement parsing and atomic SQLite persistence."""

    @staticmethod
    def compute_file_sha256(file_bytes: bytes) -> str:
        """Compute the SHA-256 cryptographic digest of a file's byte contents."""
        return hashlib.sha256(file_bytes).hexdigest()

    @classmethod
    def check_duplicate(cls, file_bytes: bytes, conn: sqlite3.Connection) -> Optional[Statement]:
        """Check whether a statement with the given file content was previously imported.

        Args:
            file_bytes: Raw binary bytes of the statement file.
            conn: Active SQLite connection.

        Returns:
            Optional[Statement]: Existing Statement record if found, else None.
        """
        digest = cls.compute_file_sha256(file_bytes)
        return StatementRepository.find_by_sha256(conn, digest)

    @classmethod
    def import_statement(
        cls,
        file_bytes: bytes,
        filename: str,
        password: Optional[str] = None,
        account_label: str = "Primary Bank Account",
        conn: Optional[sqlite3.Connection] = None,
    ) -> ImportResult:
        """Parse, validate, and atomically persist a bank statement.

        Args:
            file_bytes: Binary contents of the uploaded statement.
            filename: Original name of the uploaded file (e.g. 'hdfc_july.csv').
            password: Optional decryption password for locked PDFs.
            account_label: Bank account display label.
            conn: Optional existing SQLite connection. If None, a new connection is used.

        Returns:
            ImportResult: Outcome of the import including duplicate status and counts.
        """
        owns_conn = conn is None
        active_conn = conn if conn is not None else get_connection()

        # Pre-flight check: File emptiness
        if not file_bytes or len(file_bytes.strip()) == 0:
            return ImportResult(
                success=False,
                error_message="The uploaded statement file is completely empty (0 bytes).",
            )

        # Pre-flight check: File size boundary (10 MB maximum)
        if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
            size_mb = len(file_bytes) / (1024 * 1024)
            return ImportResult(
                success=False,
                error_message=f"File size ({size_mb:.1f} MB) exceeds the maximum allowed upload limit of {MAX_UPLOAD_SIZE_MB} MB.",
            )

        # Pre-flight check: Supported file extension
        lower_name = filename.lower()
        if lower_name.endswith(".csv"):
            source_kind = "csv"
        elif lower_name.endswith(".pdf"):
            source_kind = "pdf"
        else:
            return ImportResult(
                success=False,
                error_message=f"Unsupported file extension for '{filename}'. Only CSV and PDF files are supported.",
            )

        try:
            # 1. Compute file hash and check for duplicate statement
            file_hash = cls.compute_file_sha256(file_bytes)
            existing_stmt = StatementRepository.find_by_sha256(active_conn, file_hash)
            if existing_stmt is not None:
                return ImportResult(
                    success=True,
                    statement=existing_stmt,
                    transactions_count=existing_stmt.imported_count,
                    is_duplicate=True,
                    error_message=f"Statement was already imported on {existing_stmt.imported_at:%d-%b-%Y %H:%M} UTC.",
                )

            # 2. Parse statement depending on extension
            if source_kind == "csv":
                parse_result = parse_csv_statement(file_bytes)
            else:
                parse_result = parse_pdf_statement(file_bytes, password=password)

            # 3. Check parsing outcome
            if not parse_result.success:
                return ImportResult(
                    success=False,
                    error_message=parse_result.error_message,
                    parse_result=parse_result,
                )

            df = parse_result.df
            if df.empty:
                return ImportResult(
                    success=False,
                    error_message="Parsed statement contains 0 transactions.",
                    parse_result=parse_result,
                )

            # 4. Resolve default or active account
            account = AccountRepository.get_or_create_default(active_conn, label=account_label)

            # 5. Build Statement model
            stmt_id = f"stmt_{uuid.uuid4().hex[:12]}"
            min_date = df["date"].min()
            max_date = df["date"].max()

            statement = Statement(
                statement_id=stmt_id,
                account_id=account.account_id,
                source_filename=filename,
                source_kind=source_kind,
                file_sha256=file_hash,
                period_start=min_date,
                period_end=max_date,
                row_count=parse_result.total_rows if hasattr(parse_result, "total_rows") else len(df),
                imported_count=len(df),
                skipped_count=parse_result.skipped_rows if hasattr(parse_result, "skipped_rows") else 0,
                imported_at=datetime.now(timezone.utc),
            )

            # 6. Check for active custom rules
            active_rules = []
            has_rules_table = active_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='categorization_rules';"
            ).fetchone()
            if has_rules_table:
                active_rules = RulesRepository.list_rules(active_conn, active_only=True)

            # 7. Build Transaction models
            transactions = []
            rule_hits = {}

            for _, row in df.iterrows():
                txn_id = f"txn_{uuid.uuid4().hex[:12]}"
                cat_res = categorize_transaction(str(row["narration"]), str(row["type"]), amount=row["amount"])

                matched_rule = RulesService.match_transaction(
                    narration=str(row["narration"]),
                    merchant=cat_res.merchant or row["merchant"],
                    active_rules=active_rules,
                ) if active_rules else None

                if matched_rule:
                    final_cat_id = matched_rule.category_id
                    final_cat_name = CATEGORY_ID_TO_NAME.get(final_cat_id, cat_res.category)
                    orig_cat_id = cat_res.category_id
                    cat_source = "rule"
                    applied_rule_id = matched_rule.rule_id
                    rule_hits[matched_rule.rule_id] = rule_hits.get(matched_rule.rule_id, 0) + 1
                else:
                    final_cat_id = cat_res.category_id
                    final_cat_name = cat_res.category or row["category"]
                    orig_cat_id = None
                    cat_source = "auto"
                    applied_rule_id = None

                # Create a deterministic fingerprint for transaction deduplication
                fingerprint = hashlib.sha256(
                    f"{row['date']}_{row['amount']}_{row['narration']}_{row['type']}".encode("utf-8")
                ).hexdigest()

                transactions.append(
                    Transaction(
                        txn_id=txn_id,
                        statement_id=stmt_id,
                        account_id=account.account_id,
                        txn_date=row["date"],
                        amount=row["amount"],  # Decimal preserved
                        direction=row["type"],  # "DEBIT" or "CREDIT"
                        merchant=cat_res.merchant or row["merchant"],
                        narration=row["narration"],
                        category=final_cat_name,
                        mode=cat_res.mode or row.get("mode", "UPI"),
                        txn_type=cat_res.nature,
                        status="active",
                        fingerprint=fingerprint,
                        created_at=datetime.now(timezone.utc),
                        original_category_id=orig_cat_id,
                        category_source=cat_source,
                        applied_rule_id=applied_rule_id,
                        category_id=final_cat_id,
                    )
                )

            # 8. Atomic database transaction scope
            try:
                with transaction_scope(active_conn):
                    StatementRepository.insert(active_conn, statement)
                    TransactionRepository.insert_bulk(active_conn, transactions)
                    for r_id, count in rule_hits.items():
                        RulesRepository.increment_hit_count(active_conn, r_id, count)
            except sqlite3.Error as db_err:
                return ImportResult(
                    success=False,
                    error_message=f"Database error during statement import: {type(db_err).__name__}. Any partial modifications have been safely rolled back.",
                    parse_result=parse_result,
                )

            return ImportResult(
                success=True,
                statement=statement,
                transactions_count=len(transactions),
                is_duplicate=False,
                parse_result=parse_result,
            )

        finally:
            if owns_conn:
                active_conn.close()

    @classmethod
    def delete_statement(cls, statement_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
        """Delete an imported statement and cascade-delete all its transactions.

        Args:
            statement_id: Unique statement ID.
            conn: Optional SQLite connection.

        Returns:
            bool: True if statement was deleted, False otherwise.
        """
        owns_conn = conn is None
        active_conn = conn if conn is not None else get_connection()
        try:
            with transaction_scope(active_conn):
                return StatementRepository.delete_by_id(active_conn, statement_id)
        finally:
            if owns_conn:
                active_conn.close()

    @classmethod
    def get_active_transactions_df(
        cls,
        conn: Optional[sqlite3.Connection] = None,
        account_id: Optional[str] = None,
        statement_id: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch transactions from database and return as canonical DataFrame.

        Args:
            conn: Optional SQLite connection.
            account_id: Optional account filter.
            statement_id: Optional statement filter.

        Returns:
            pd.DataFrame: Canonical DataFrame matching ['date', 'merchant', 'narration', 'category', 'mode', 'type', 'amount'].
        """
        owns_conn = conn is None
        active_conn = conn if conn is not None else get_connection()
        try:
            txns = TransactionRepository.get_transactions(
                active_conn,
                account_id=account_id,
                statement_id=statement_id,
            )
            return TransactionRepository.to_dataframe(txns)
        finally:
            if owns_conn:
                active_conn.close()

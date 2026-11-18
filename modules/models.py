"""Domain data models for UPI Smart Expense Analyzer.

Defines strongly-typed dataclasses for Account, Statement, and Transaction
entities, adhering to strict financial precision rules (using Decimal for money).
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional


@dataclass
class Account:
    """Represents a bank or card account."""

    account_id: str
    label: str
    bank_name: Optional[str] = None
    account_last4: Optional[str] = None
    account_type: str = "savings"
    currency: str = "INR"
    created_at: Optional[datetime] = None


@dataclass
class Statement:
    """Represents an imported bank statement file."""

    statement_id: str
    account_id: str
    source_filename: str
    source_kind: str  # "csv" or "pdf"
    file_sha256: str
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    row_count: int = 0
    imported_count: int = 0
    skipped_count: int = 0
    imported_at: Optional[datetime] = None


@dataclass
class Transaction:
    """Represents a normalized financial transaction."""

    txn_id: str
    statement_id: str
    account_id: str
    txn_date: date
    amount: Decimal  # In Python, exact Rupee Decimal. Stored as integer paise in SQLite.
    direction: str  # "DEBIT" or "CREDIT"
    merchant: str
    narration: str
    category: str
    mode: str = "UPI"
    txn_type: str = "payment"
    status: str = "active"
    fingerprint: Optional[str] = None
    created_at: Optional[datetime] = None
    original_category_id: Optional[str] = None
    category_source: str = "auto"  # "auto", "user_override", "rule"
    applied_rule_id: Optional[str] = None
    category_id: Optional[str] = None


@dataclass
class CategorizationRule:
    """Represents a custom or promoted categorization rule."""

    rule_id: str
    pattern: str
    pattern_type: str  # "merchant_exact", "merchant_contains", "narration_contains", "regex"
    category_id: str
    priority: int = 100
    source: str = "user"  # "user", "promoted", "builtin"
    hit_count: int = 0
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

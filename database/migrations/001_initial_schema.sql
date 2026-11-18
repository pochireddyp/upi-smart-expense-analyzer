-- ==============================================================================
-- Migration 001: Initial Schema for UPI Smart Expense Analyzer
-- Sets up accounts, statements, categories, transactions, and performance indexes.
-- ==============================================================================

-- 1. Migration History
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

-- 2. Bank Accounts
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    bank_name TEXT,
    account_last4 TEXT CHECK(length(account_last4) <= 4),
    account_type TEXT DEFAULT 'savings',
    currency TEXT NOT NULL DEFAULT 'INR',
    created_at TEXT NOT NULL
);

-- 3. Imported Statements (with file_sha256 for idempotency)
CREATE TABLE IF NOT EXISTS statements (
    statement_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    source_filename TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK(source_kind IN ('csv', 'pdf')),
    file_sha256 TEXT NOT NULL UNIQUE,
    period_start TEXT,
    period_end TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    imported_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT NOT NULL
);

-- 4. Standard Categories Taxonomy
CREATE TABLE IF NOT EXISTS categories (
    category_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('need', 'want', 'saving', 'income', 'internal')),
    is_system INTEGER NOT NULL DEFAULT 1
);

-- 5. Transactions Table (amount stored in minor units: integer paise)
CREATE TABLE IF NOT EXISTS transactions (
    txn_id TEXT PRIMARY KEY,
    statement_id TEXT NOT NULL REFERENCES statements(statement_id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    txn_date TEXT NOT NULL,
    amount_minor INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    direction TEXT NOT NULL CHECK(direction IN ('DEBIT', 'CREDIT')),
    merchant TEXT NOT NULL,
    narration TEXT NOT NULL,
    category_id TEXT REFERENCES categories(category_id),
    mode TEXT NOT NULL DEFAULT 'UPI',
    txn_type TEXT NOT NULL DEFAULT 'payment',
    status TEXT NOT NULL DEFAULT 'active',
    fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 6. Performance Indexes
CREATE INDEX IF NOT EXISTS idx_txns_account_date ON transactions(account_id, txn_date);
CREATE INDEX IF NOT EXISTS idx_txns_category ON transactions(category_id, txn_date);
CREATE INDEX IF NOT EXISTS idx_txns_statement ON transactions(statement_id);
CREATE INDEX IF NOT EXISTS idx_txns_fingerprint ON transactions(fingerprint);
CREATE INDEX IF NOT EXISTS idx_statements_sha256 ON statements(file_sha256);

-- 7. Seed Standard Categories
INSERT OR IGNORE INTO categories (category_id, name, kind, is_system) VALUES
    ('food_dining', 'Food & Dining', 'want', 1),
    ('groceries', 'Groceries & Essentials', 'need', 1),
    ('shopping', 'Shopping & E-Com', 'want', 1),
    ('utilities', 'Utilities & Bills', 'need', 1),
    ('commute', 'Commute & Travel', 'need', 1),
    ('entertainment', 'Entertainment & Subs', 'want', 1),
    ('health', 'Health & Medical', 'need', 1),
    ('housing', 'Rent & Housing', 'need', 1),
    ('salary', 'Salary & Income', 'income', 1),
    ('transfers', 'Peer Transfers', 'internal', 1),
    ('others', 'Others & Misc', 'want', 1);

-- ==============================================================================
-- Migration 002: User Categorization Rules, Overrides, and Audit History
-- ==============================================================================

-- 1. Custom and Promoted Categorization Rules Table
CREATE TABLE IF NOT EXISTS categorization_rules (
    rule_id TEXT PRIMARY KEY,
    pattern TEXT NOT NULL,
    pattern_type TEXT NOT NULL CHECK(pattern_type IN ('merchant_exact', 'merchant_contains', 'narration_contains', 'regex')),
    category_id TEXT NOT NULL REFERENCES categories(category_id),
    priority INTEGER NOT NULL DEFAULT 100,  -- User rules default to 100 (built-in default is 10)
    source TEXT NOT NULL DEFAULT 'user' CHECK(source IN ('user', 'promoted', 'builtin')),
    hit_count INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Index for high-speed rule lookups
CREATE INDEX IF NOT EXISTS idx_rules_lookup ON categorization_rules(is_active, priority DESC);

-- 2. Non-Destructive Category Tracking Columns on Transactions
ALTER TABLE transactions ADD COLUMN original_category_id TEXT REFERENCES categories(category_id);
ALTER TABLE transactions ADD COLUMN category_source TEXT NOT NULL DEFAULT 'auto';
ALTER TABLE transactions ADD COLUMN applied_rule_id TEXT REFERENCES categorization_rules(rule_id);

-- 3. Audit Log for Manual Category Overrides
CREATE TABLE IF NOT EXISTS category_overrides_audit (
    audit_id TEXT PRIMARY KEY,
    txn_id TEXT NOT NULL REFERENCES transactions(txn_id) ON DELETE CASCADE,
    previous_category_id TEXT REFERENCES categories(category_id),
    new_category_id TEXT NOT NULL REFERENCES categories(category_id),
    reason TEXT,
    changed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_overrides_txn ON category_overrides_audit(txn_id);

"""SQLite schema definition and default seed data."""
from __future__ import annotations

SCHEMA_VERSION = 1

# All monetary columns are INTEGER minor units (e.g. poisha) – never floats.
SCHEMA_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS categories (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL COLLATE NOCASE,
        type        TEXT    NOT NULL CHECK (type IN ('income', 'expense')),
        color       TEXT    NOT NULL DEFAULT '#6366F1',
        icon        TEXT    NOT NULL DEFAULT 'tag',
        is_default  INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
        UNIQUE (name, type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transactions (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        type             TEXT    NOT NULL CHECK (type IN ('income', 'expense')),
        amount_minor     INTEGER NOT NULL CHECK (amount_minor > 0),
        category_id      INTEGER NOT NULL REFERENCES categories (id) ON DELETE RESTRICT,
        description      TEXT    NOT NULL DEFAULT '',
        payment_method   TEXT    NOT NULL DEFAULT 'Cash',
        transaction_date TEXT    NOT NULL
            CHECK (transaction_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
        created_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_tx_date ON transactions (transaction_date)",
    "CREATE INDEX IF NOT EXISTS ix_tx_type_date ON transactions (type, transaction_date)",
    "CREATE INDEX IF NOT EXISTS ix_tx_category ON transactions (category_id)",
    """
    CREATE TABLE IF NOT EXISTS budgets (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        month        TEXT    NOT NULL CHECK (month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
        category_id  INTEGER REFERENCES categories (id) ON DELETE CASCADE,
        limit_minor  INTEGER NOT NULL CHECK (limit_minor > 0),
        created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
    )
    """,
    # category_id NULL == overall monthly limit; one row per (month, scope).
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_budget_scope ON budgets (month, IFNULL(category_id, 0))",
    """
    CREATE TABLE IF NOT EXISTS savings_goals (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        name           TEXT    NOT NULL,
        target_minor   INTEGER NOT NULL CHECK (target_minor > 0),
        current_minor  INTEGER NOT NULL DEFAULT 0 CHECK (current_minor >= 0),
        start_date     TEXT    NOT NULL,
        target_date    TEXT,
        description    TEXT    NOT NULL DEFAULT '',
        icon           TEXT    NOT NULL DEFAULT 'savings',
        created_at     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS savings_contributions (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        goal_id            INTEGER NOT NULL REFERENCES savings_goals (id) ON DELETE CASCADE,
        amount_minor       INTEGER NOT NULL CHECK (amount_minor <> 0),
        contribution_date  TEXT    NOT NULL,
        note               TEXT    NOT NULL DEFAULT '',
        created_at         TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_contrib_goal ON savings_contributions (goal_id)",
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        key         TEXT PRIMARY KEY,
        value       TEXT NOT NULL,
        updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    )
    """,
]

# (name, type, colour, icon-key)
DEFAULT_CATEGORIES: list[tuple[str, str, str, str]] = [
    ("Salary", "income", "#22C55E", "briefcase"),
    ("Freelancing", "income", "#14B8A6", "laptop"),
    ("Business", "income", "#06B6D4", "store"),
    ("Investments", "income", "#8B5CF6", "trending-up"),
    ("Gifts", "income", "#EC4899", "gift"),
    ("Other Income", "income", "#84CC16", "plus-circle"),
    ("Food", "expense", "#F97316", "utensils"),
    ("Transportation", "expense", "#3B82F6", "bus"),
    ("Shopping", "expense", "#EC4899", "shopping-bag"),
    ("Housing", "expense", "#8B5CF6", "home"),
    ("Education", "expense", "#06B6D4", "book"),
    ("Healthcare", "expense", "#EF4444", "heart"),
    ("Entertainment", "expense", "#EAB308", "film"),
    ("Utilities", "expense", "#14B8A6", "zap"),
    ("Travel", "expense", "#6366F1", "plane"),
    ("Subscriptions", "expense", "#A855F7", "repeat"),
    ("Other Expenses", "expense", "#64748B", "more-horizontal"),
]

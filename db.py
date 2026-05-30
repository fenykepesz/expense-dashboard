import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "expenses.db"

BUILTIN_CATEGORIES = [
    "Banking Fees",
    "Banking Services",
    "Entertainment",
    "Food Delivery",
    "General Services",
    "Groceries",
    "Healthcare",
    "Insurance",
    "Other",
    "Photography",
    "Restaurants",
    "Shopping",
    "Technology",
    "Telecommunications",
    "Transportation",
    "Uncategorized",
    "Utilities",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT    NOT NULL,
    merchant    TEXT    NOT NULL,
    amount      REAL    NOT NULL,
    category    TEXT    NOT NULL,
    month       TEXT    NOT NULL,
    year        INTEGER NOT NULL,
    card        TEXT    NOT NULL,
    imported_at TEXT    NOT NULL DEFAULT '',
    excluded    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS categories (
    name       TEXT    PRIMARY KEY,
    is_builtin INTEGER NOT NULL DEFAULT 0,
    is_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _connect(db_path=None):
    path = str(db_path or DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)
        # Migrate old transaction columns
        for col, definition in [
            ("imported_at", "TEXT NOT NULL DEFAULT ''"),
            ("excluded",    "INTEGER NOT NULL DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE transactions ADD COLUMN {col} {definition}")
            except sqlite3.OperationalError:
                pass
        # Seed categories if the table is empty
        if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            conn.executemany(
                "INSERT OR IGNORE INTO categories (name, is_builtin, is_deleted) VALUES (?, ?, 0)",
                [(name, 1) for name in BUILTIN_CATEGORIES],
            )
    # One-time migration from legacy JSON files
    _migrate_categories_from_json(db_path)


def _migrate_categories_from_json(db_path=None):
    tools_dir = Path(__file__).parent / "tools"
    categories_json = tools_dir / "categories.json"
    deleted_json = tools_dir / "deleted_builtins.json"

    if categories_json.exists():
        try:
            custom = json.loads(categories_json.read_text(encoding="utf-8"))
            with _connect(db_path) as conn:
                for name in custom:
                    conn.execute(
                        "INSERT OR IGNORE INTO categories (name, is_builtin, is_deleted) VALUES (?, 0, 0)",
                        (name,),
                    )
        except Exception:
            pass

    if deleted_json.exists():
        try:
            deleted = json.loads(deleted_json.read_text(encoding="utf-8"))
            with _connect(db_path) as conn:
                for name in deleted:
                    conn.execute(
                        "UPDATE categories SET is_deleted = 1 WHERE name = ?", (name,)
                    )
        except Exception:
            pass


# ── Category CRUD ─────────────────────────────────────────────────────────────

def get_categories(db_path=None):
    """Return active (non-deleted) categories sorted alphabetically."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name, is_builtin FROM categories WHERE is_deleted = 0 ORDER BY name"
        ).fetchall()
    return [dict(row) for row in rows]


def get_category_details(db_path=None):
    """Return categories with merchant counts."""
    cats = get_categories(db_path)
    counts = {r["category"]: r["count"] for r in _category_merchant_counts(db_path)}
    return [
        {"name": c["name"], "is_builtin": bool(c["is_builtin"]), "count": counts.get(c["name"], 0)}
        for c in cats
    ]


def _category_merchant_counts(db_path=None):
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT category, COUNT(DISTINCT merchant) as count FROM transactions GROUP BY category"
        ).fetchall()
    return [dict(row) for row in rows]


def add_category(name, db_path=None):
    """Add a new category or restore a soft-deleted one. Returns updated list."""
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT is_builtin, is_deleted FROM categories WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            if existing["is_deleted"]:
                conn.execute("UPDATE categories SET is_deleted = 0 WHERE name = ?", (name,))
        else:
            conn.execute(
                "INSERT INTO categories (name, is_builtin, is_deleted) VALUES (?, 0, 0)", (name,)
            )
    return [c["name"] for c in get_categories(db_path)]


def delete_category(name, db_path=None):
    """Delete a category. Builtins are soft-deleted; customs are removed. Protects Uncategorized."""
    if name == "Uncategorized":
        raise ValueError('"Uncategorized" cannot be deleted.')
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT is_builtin FROM categories WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise ValueError(f'Category "{name}" not found.')
        if row["is_builtin"]:
            conn.execute("UPDATE categories SET is_deleted = 1 WHERE name = ?", (name,))
        else:
            conn.execute("DELETE FROM categories WHERE name = ?", (name,))
    return [c["name"] for c in get_categories(db_path)]


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key, db_path=None):
    with _connect(db_path) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key, value, db_path=None):
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# ── Transactions ──────────────────────────────────────────────────────────────

def insert_transactions(expenses, db_path=None, imported_at=None):
    ts = imported_at or datetime.now().isoformat(timespec="seconds")
    rows = [
        (e["date"], e["merchant"], e["amount"], e["category"],
         e["month"], e["year"], e["card"], ts)
        for e in expenses
    ]
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO transactions "
            "(date, merchant, amount, category, month, year, card, imported_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    return len(rows)


def get_all_transactions(db_path=None):
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, date, merchant, amount, category, month, year, card, excluded "
            "FROM transactions ORDER BY date DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def set_transaction_excluded(transaction_id, excluded, db_path=None):
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE transactions SET excluded = ? WHERE id = ?",
            (1 if excluded else 0, transaction_id),
        )


def delete_transaction(transaction_id, db_path=None):
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))


def get_merchants(db_path=None):
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT merchant, category, COUNT(*) as count "
            "FROM transactions GROUP BY merchant ORDER BY count DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def update_merchant_category_by_category(old_category, new_category, db_path=None):
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE transactions SET category = ? WHERE category = ?",
            (new_category, old_category),
        )


def update_merchant_category(merchant, new_category, db_path=None):
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE transactions SET category = ? WHERE merchant = ?",
            (new_category, merchant),
        )


def check_duplicates(transactions, db_path=None):
    count = 0
    with _connect(db_path) as conn:
        for t in transactions:
            row = conn.execute(
                "SELECT 1 FROM transactions "
                "WHERE date=? AND merchant=? AND amount=? AND card=? LIMIT 1",
                (t["date"], t["merchant"], t["amount"], t["card"]),
            ).fetchone()
            if row:
                count += 1
    return count

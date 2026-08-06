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

CREATE TABLE IF NOT EXISTS household_members (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    is_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS funds (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    fund_type  TEXT    NOT NULL,
    owner_id   INTEGER REFERENCES household_members(id),
    is_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fund_balances (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id      INTEGER NOT NULL REFERENCES funds(id),
    date         TEXT    NOT NULL,
    balance      REAL    NOT NULL,
    contribution REAL    NOT NULL DEFAULT 0,
    UNIQUE(fund_id, date)
);

CREATE TABLE IF NOT EXISTS bank_accounts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    account_number TEXT    NOT NULL DEFAULT '',
    owner_id       INTEGER REFERENCES household_members(id),
    is_deleted     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bank_transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL REFERENCES bank_accounts(id),
    date          TEXT    NOT NULL,
    description   TEXT    NOT NULL,
    reference     TEXT    NOT NULL DEFAULT '',
    amount        REAL    NOT NULL,
    balance_after REAL,
    type          TEXT    NOT NULL,
    category      TEXT    NOT NULL DEFAULT 'Uncategorized',
    month         TEXT    NOT NULL,
    year          INTEGER NOT NULL,
    imported_at   TEXT    NOT NULL DEFAULT '',
    excluded      INTEGER NOT NULL DEFAULT 0,
    notes         TEXT    NOT NULL DEFAULT ''
);
"""

FUND_TYPES = ["pension", "study_fund", "investment", "other"]


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
            ("notes",       "TEXT NOT NULL DEFAULT ''"),
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


# ── Household members ─────────────────────────────────────────────────────────

def get_household_members(db_path=None):
    """Return active (non-deleted) household members sorted alphabetically."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, name FROM household_members WHERE is_deleted = 0 ORDER BY name"
        ).fetchall()
    return [dict(row) for row in rows]


def add_household_member(name, db_path=None):
    """Add a new household member or restore a soft-deleted one. Returns updated list."""
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id, is_deleted FROM household_members WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            if existing["is_deleted"]:
                conn.execute(
                    "UPDATE household_members SET is_deleted = 0 WHERE id = ?", (existing["id"],)
                )
        else:
            conn.execute("INSERT INTO household_members (name) VALUES (?)", (name,))
    return get_household_members(db_path)


def delete_household_member(member_id, db_path=None):
    """Soft-delete a household member. Returns updated list.

    Blocked if the member still owns any active fund or bank account —
    avoids orphaning that history.
    """
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM household_members WHERE id = ?", (member_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Household member {member_id} not found.")
        owns_fund = conn.execute(
            "SELECT COUNT(*) FROM funds WHERE owner_id = ? AND is_deleted = 0", (member_id,)
        ).fetchone()[0]
        if owns_fund:
            raise ValueError("Cannot remove a household member who still owns a fund.")
        owns_account = conn.execute(
            "SELECT COUNT(*) FROM bank_accounts WHERE owner_id = ? AND is_deleted = 0", (member_id,)
        ).fetchone()[0]
        if owns_account:
            raise ValueError("Cannot remove a household member who still owns a bank account.")
        conn.execute("UPDATE household_members SET is_deleted = 1 WHERE id = ?", (member_id,))
    return get_household_members(db_path)


# ── Funds ─────────────────────────────────────────────────────────────────────

def get_funds(db_path=None):
    """Return active (non-deleted) funds, with owner name joined, sorted by name."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT f.id, f.name, f.fund_type, f.owner_id, m.name AS owner_name
            FROM funds f
            LEFT JOIN household_members m ON m.id = f.owner_id
            WHERE f.is_deleted = 0
            ORDER BY f.name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def add_fund(name, fund_type, owner_id=None, db_path=None):
    """Add a new fund. Returns updated list."""
    if fund_type not in FUND_TYPES:
        raise ValueError(f'Invalid fund_type "{fund_type}". Must be one of {FUND_TYPES}.')
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO funds (name, fund_type, owner_id) VALUES (?, ?, ?)",
            (name, fund_type, owner_id),
        )
    return get_funds(db_path)


def delete_fund(fund_id, db_path=None):
    """Soft-delete a fund. Returns updated list."""
    with _connect(db_path) as conn:
        row = conn.execute("SELECT id FROM funds WHERE id = ?", (fund_id,)).fetchone()
        if row is None:
            raise ValueError(f"Fund {fund_id} not found.")
        conn.execute("UPDATE funds SET is_deleted = 1 WHERE id = ?", (fund_id,))
    return get_funds(db_path)


# ── Fund balances ─────────────────────────────────────────────────────────────

def get_fund_balances(fund_id=None, db_path=None):
    """Return balance entries, optionally filtered to one fund, newest first."""
    with _connect(db_path) as conn:
        if fund_id is None:
            rows = conn.execute(
                "SELECT id, fund_id, date, balance, contribution FROM fund_balances ORDER BY date DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, fund_id, date, balance, contribution FROM fund_balances "
                "WHERE fund_id = ? ORDER BY date DESC",
                (fund_id,),
            ).fetchall()
    return [dict(row) for row in rows]


def add_fund_balance(fund_id, date, balance, contribution=0, db_path=None):
    """Add or update a fund's balance for a given date (upsert on fund_id+date)."""
    with _connect(db_path) as conn:
        fund = conn.execute("SELECT id FROM funds WHERE id = ?", (fund_id,)).fetchone()
        if fund is None:
            raise ValueError(f"Fund {fund_id} not found.")
        conn.execute(
            """
            INSERT INTO fund_balances (fund_id, date, balance, contribution)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(fund_id, date) DO UPDATE SET
                balance = excluded.balance,
                contribution = excluded.contribution
            """,
            (fund_id, date, balance, contribution),
        )
    return get_fund_balances(fund_id, db_path)


def delete_fund_balance(balance_id, db_path=None):
    with _connect(db_path) as conn:
        row = conn.execute("SELECT fund_id FROM fund_balances WHERE id = ?", (balance_id,)).fetchone()
        if row is None:
            raise ValueError(f"Fund balance {balance_id} not found.")
        fund_id = row["fund_id"]
        conn.execute("DELETE FROM fund_balances WHERE id = ?", (balance_id,))
    return get_fund_balances(fund_id, db_path)


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
            "SELECT id, date, merchant, amount, category, month, year, card, excluded, notes "
            "FROM transactions ORDER BY date DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def set_transaction_excluded(transaction_id, excluded, db_path=None):
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE transactions SET excluded = ? WHERE id = ?",
            (1 if excluded else 0, transaction_id),
        )


def set_transaction_note(transaction_id, note, db_path=None):
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE transactions SET notes = ? WHERE id = ?",
            (note.strip(), transaction_id),
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


# ── Bank accounts ─────────────────────────────────────────────────────────────

def get_bank_accounts(db_path=None):
    """Return active (non-deleted) bank accounts, with owner name joined."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.name, a.account_number, a.owner_id, m.name AS owner_name
            FROM bank_accounts a
            LEFT JOIN household_members m ON m.id = a.owner_id
            WHERE a.is_deleted = 0
            ORDER BY a.name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def add_bank_account(name, owner_id=None, account_number="", db_path=None):
    """Add a new bank account. Returns updated list."""
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO bank_accounts (name, account_number, owner_id) VALUES (?, ?, ?)",
            (name, account_number, owner_id),
        )
    return get_bank_accounts(db_path)


def delete_bank_account(account_id, db_path=None):
    """Soft-delete a bank account. Returns updated list."""
    with _connect(db_path) as conn:
        row = conn.execute("SELECT id FROM bank_accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None:
            raise ValueError(f"Bank account {account_id} not found.")
        conn.execute("UPDATE bank_accounts SET is_deleted = 1 WHERE id = ?", (account_id,))
    return get_bank_accounts(db_path)


# ── Bank transactions ─────────────────────────────────────────────────────────

def insert_bank_transactions(rows, account_id, db_path=None, imported_at=None):
    """Insert one or more bank transactions for an account.

    Each row needs: date (YYYY-MM-DD), description, amount (signed), type
    ('income' | 'expense'). category/reference/balance_after/notes are optional.
    month/year are derived from date.
    """
    ts = imported_at or datetime.now().isoformat(timespec="seconds")
    prepared = []
    for r in rows:
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        prepared.append((
            account_id, r["date"], r["description"], r.get("reference", ""),
            r["amount"], r.get("balance_after"), r["type"],
            r.get("category", "Uncategorized"), dt.strftime("%B"), dt.year, ts,
        ))
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO bank_transactions "
            "(account_id, date, description, reference, amount, balance_after, type, "
            " category, month, year, imported_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            prepared,
        )
    return len(prepared)


def get_bank_transactions(account_id=None, db_path=None):
    with _connect(db_path) as conn:
        if account_id is None:
            rows = conn.execute(
                "SELECT id, account_id, date, description, reference, amount, balance_after, "
                "type, category, month, year, excluded, notes "
                "FROM bank_transactions ORDER BY date DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, account_id, date, description, reference, amount, balance_after, "
                "type, category, month, year, excluded, notes "
                "FROM bank_transactions WHERE account_id = ? ORDER BY date DESC",
                (account_id,),
            ).fetchall()
    return [dict(row) for row in rows]


def set_bank_transaction_excluded(transaction_id, excluded, db_path=None):
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE bank_transactions SET excluded = ? WHERE id = ?",
            (1 if excluded else 0, transaction_id),
        )


def set_bank_transaction_note(transaction_id, note, db_path=None):
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE bank_transactions SET notes = ? WHERE id = ?",
            (note.strip(), transaction_id),
        )


def delete_bank_transaction(transaction_id, db_path=None):
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM bank_transactions WHERE id = ?", (transaction_id,))


# ── Net worth ─────────────────────────────────────────────────────────────────

def _month_range(first, last):
    """Inclusive list of YYYY-MM strings from first to last."""
    y, m = int(first[:4]), int(first[5:7])
    ly, lm = int(last[:4]), int(last[5:7])
    months = []
    while (y, m) <= (ly, lm):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def get_net_worth_series(db_path=None):
    """Monthly net-worth series across all active funds and bank accounts.

    Funds: the last recorded balance within each month, carried forward
    through months without an entry. Bank accounts: cumulative sum of
    non-excluded transaction amounts (manual entry never sets balance_after,
    so the running total is the best available signal until the importer
    lands). Months before an item's first data point are None.
    """
    with _connect(db_path) as conn:
        funds = conn.execute(
            """
            SELECT f.id, f.name, f.fund_type, m.name AS owner_name
            FROM funds f LEFT JOIN household_members m ON m.id = f.owner_id
            WHERE f.is_deleted = 0 ORDER BY f.name
            """
        ).fetchall()
        accounts = conn.execute(
            """
            SELECT a.id, a.name, m.name AS owner_name
            FROM bank_accounts a LEFT JOIN household_members m ON m.id = a.owner_id
            WHERE a.is_deleted = 0 ORDER BY a.name
            """
        ).fetchall()
        fund_rows = conn.execute(
            "SELECT fund_id, date, balance FROM fund_balances ORDER BY date"
        ).fetchall()
        bank_rows = conn.execute(
            "SELECT account_id, date, amount FROM bank_transactions "
            "WHERE excluded = 0 ORDER BY date"
        ).fetchall()

    active_funds = {f["id"] for f in funds}
    active_accounts = {a["id"] for a in accounts}
    fund_rows = [r for r in fund_rows if r["fund_id"] in active_funds]
    bank_rows = [r for r in bank_rows if r["account_id"] in active_accounts]

    data_months = {r["date"][:7] for r in fund_rows} | {r["date"][:7] for r in bank_rows}
    if not data_months:
        return {"months": [], "series": []}
    months = _month_range(min(data_months), max(data_months))

    series = []
    for f in funds:
        # Rows are date-ordered, so the last entry in a month wins
        by_month = {}
        for r in fund_rows:
            if r["fund_id"] == f["id"]:
                by_month[r["date"][:7]] = r["balance"]
        balances, last = [], None
        for month in months:
            last = by_month.get(month, last)
            balances.append(last)
        series.append({
            "key": f"fund-{f['id']}", "kind": "fund", "name": f["name"],
            "fund_type": f["fund_type"], "owner_name": f["owner_name"],
            "balances": balances,
        })

    for a in accounts:
        monthly_sum = {}
        for r in bank_rows:
            if r["account_id"] == a["id"]:
                month = r["date"][:7]
                monthly_sum[month] = monthly_sum.get(month, 0) + r["amount"]
        balances, running, started = [], 0, False
        for month in months:
            if month in monthly_sum:
                running += monthly_sum[month]
                started = True
            balances.append(round(running, 2) if started else None)
        series.append({
            "key": f"bank-{a['id']}", "kind": "bank", "name": a["name"],
            "fund_type": None, "owner_name": a["owner_name"],
            "balances": balances,
        })

    return {"months": months, "series": series}

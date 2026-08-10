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
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    name                   TEXT    NOT NULL,
    company_name           TEXT    NOT NULL DEFAULT '',
    fund_number            TEXT    NOT NULL DEFAULT '',
    fund_type              TEXT    NOT NULL,
    owner_id               INTEGER REFERENCES household_members(id),
    is_deleted             INTEGER NOT NULL DEFAULT 0,
    excluded_from_net_worth INTEGER NOT NULL DEFAULT 0,
    is_liquid              INTEGER NOT NULL DEFAULT 0,
    risk_level             INTEGER NOT NULL DEFAULT 0,
    risk_note              TEXT    NOT NULL DEFAULT ''
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
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    name                    TEXT    NOT NULL,
    account_number          TEXT    NOT NULL DEFAULT '',
    owner_id                INTEGER REFERENCES household_members(id),
    is_deleted              INTEGER NOT NULL DEFAULT 0,
    excluded_from_net_worth INTEGER NOT NULL DEFAULT 0,
    risk_level              INTEGER NOT NULL DEFAULT 0,
    risk_note               TEXT    NOT NULL DEFAULT ''
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

CREATE TABLE IF NOT EXISTS stock_holdings (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol                  TEXT    NOT NULL,
    brokerage_firm          TEXT    NOT NULL DEFAULT '',
    holding_type            TEXT    NOT NULL DEFAULT 'stock',
    owner_id                INTEGER REFERENCES household_members(id),
    cost_basis              REAL, -- intentionally nullable: 0 is a valid cost basis,
                                  -- NULL means "not entered yet" (see _compute_stock_value)
    is_deleted              INTEGER NOT NULL DEFAULT 0,
    excluded_from_net_worth INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stock_values (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    holding_id     INTEGER NOT NULL REFERENCES stock_holdings(id),
    date           TEXT    NOT NULL,
    quantity       REAL    NOT NULL,
    price_per_unit REAL    NOT NULL,
    UNIQUE(holding_id, date)
);
"""

FUND_TYPES = [
    "pension", "study_fund", "provident_fund", "investment_provident_fund",
    "money_market_fund", "savings_policy", "investment", "real_estate", "other",
]

# Label only — never branches the tax math. Cost basis already captures what
# differs between them (purchase price for stock/ESPP, vesting-date fair
# market value for RSU); see the "Stock/brokerage holdings" IDEAS.md entry.
STOCK_HOLDING_TYPES = ["stock", "espp", "rsu"]

# Flat capital-gains rate applied to gains only (value above cost basis),
# never to the full value. Approximate — not tax advice.
STOCK_TAX_RATE = 0.25

# Self-declared risk scale. 0 = Not Rated (default); not a member of this dict,
# validated separately wherever risk_level is accepted.
RISK_LEVELS = {
    1: "Capital Guaranteed",
    2: "Low Risk",
    3: "Moderate Risk",
    4: "High Risk",
    5: "Very High Risk",
}


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
        # Migrate old fund columns
        for col, definition in [
            ("company_name",            "TEXT NOT NULL DEFAULT ''"),
            ("fund_number",             "TEXT NOT NULL DEFAULT ''"),
            ("excluded_from_net_worth", "INTEGER NOT NULL DEFAULT 0"),
            ("is_liquid",               "INTEGER NOT NULL DEFAULT 0"),
            ("risk_level",              "INTEGER NOT NULL DEFAULT 0"),
            ("risk_note",               "TEXT NOT NULL DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE funds ADD COLUMN {col} {definition}")
            except sqlite3.OperationalError:
                pass
        # Migrate old bank_accounts columns
        for col, definition in [
            ("excluded_from_net_worth", "INTEGER NOT NULL DEFAULT 0"),
            ("risk_level",              "INTEGER NOT NULL DEFAULT 0"),
            ("risk_note",               "TEXT NOT NULL DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE bank_accounts ADD COLUMN {col} {definition}")
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

    Blocked if the member still owns any active fund, bank account, or
    stock holding — avoids orphaning that history.
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
        owns_stock = conn.execute(
            "SELECT COUNT(*) FROM stock_holdings WHERE owner_id = ? AND is_deleted = 0", (member_id,)
        ).fetchone()[0]
        if owns_stock:
            raise ValueError("Cannot remove a household member who still owns a stock holding.")
        conn.execute("UPDATE household_members SET is_deleted = 1 WHERE id = ?", (member_id,))
    return get_household_members(db_path)


# ── Funds ─────────────────────────────────────────────────────────────────────

def get_funds(db_path=None):
    """Return active (non-deleted) funds, with owner name and latest balance
    joined, sorted by name.

    Includes funds excluded from Net Worth — that flag only affects
    get_net_worth_series, not this listing. latest_balance/latest_balance_date
    are None for a fund with no recorded balance entries yet.
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT f.id, f.name, f.company_name, f.fund_number, f.fund_type, f.owner_id,
                   f.excluded_from_net_worth, f.is_liquid, f.risk_level, f.risk_note,
                   m.name AS owner_name,
                   fb.balance AS latest_balance, fb.date AS latest_balance_date
            FROM funds f
            LEFT JOIN household_members m ON m.id = f.owner_id
            LEFT JOIN fund_balances fb ON fb.id = (
                SELECT id FROM fund_balances WHERE fund_id = f.id ORDER BY date DESC LIMIT 1
            )
            WHERE f.is_deleted = 0
            ORDER BY f.name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _validate_risk_level(fields):
    """Shared by update_fund/update_bank_account: 0 (Not Rated) or a real level."""
    if "risk_level" in fields and fields["risk_level"] not in (0, *RISK_LEVELS):
        raise ValueError(f'Invalid risk_level "{fields["risk_level"]}". Must be 0 or one of {list(RISK_LEVELS)}.')


def add_fund(name, fund_type, company_name="", owner_id=None, fund_number="",
             is_liquid=False, risk_level=0, risk_note="", db_path=None):
    """Add a new fund. Returns updated list."""
    if fund_type not in FUND_TYPES:
        raise ValueError(f'Invalid fund_type "{fund_type}". Must be one of {FUND_TYPES}.')
    _validate_risk_level({"risk_level": risk_level})
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO funds (name, company_name, fund_number, fund_type, owner_id, "
            "is_liquid, risk_level, risk_note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, company_name, fund_number, fund_type, owner_id,
             1 if is_liquid else 0, risk_level, risk_note),
        )
    return get_funds(db_path)


FUND_EDITABLE_FIELDS = {
    "name", "company_name", "fund_number", "fund_type", "owner_id",
    "excluded_from_net_worth", "is_liquid", "risk_level", "risk_note",
}


def update_fund(fund_id, fields, db_path=None):
    """Partially update a fund. `fields` is a dict of column -> new value;
    only keys present are changed. Returns updated list."""
    cols = [c for c in fields if c in FUND_EDITABLE_FIELDS]
    if not cols:
        return get_funds(db_path)
    if "fund_type" in fields and fields["fund_type"] not in FUND_TYPES:
        raise ValueError(f'Invalid fund_type "{fields["fund_type"]}". Must be one of {FUND_TYPES}.')
    _validate_risk_level(fields)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT id FROM funds WHERE id = ?", (fund_id,)).fetchone()
        if row is None:
            raise ValueError(f"Fund {fund_id} not found.")
        set_clause = ", ".join(f"{c} = ?" for c in cols)
        conn.execute(
            f"UPDATE funds SET {set_clause} WHERE id = ?",
            [fields[c] for c in cols] + [fund_id],
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


# ── Stock holdings ────────────────────────────────────────────────────────────
#
# A separate entity from `funds` (own table, own API, own UI panel), not a
# fund_type — the fields (Symbol, Quantity, Cost Basis) and their derived
# Total/Net Value don't fit the generic Company/Fund Name/Fund # shape.

def _compute_stock_value(quantity, price_per_unit, cost_basis):
    """(total_value, net_value). net_value is None — a warning state, not a
    guess — when cost_basis is unknown, since "gain" is undefined without it.
    Tax applies only to the gain (value above cost basis), never the total."""
    total_value = round(quantity * price_per_unit, 2)
    if cost_basis is None:
        return total_value, None
    gain = max(0.0, total_value - cost_basis * quantity)
    return total_value, round(total_value - STOCK_TAX_RATE * gain, 2)


def get_stock_holdings(db_path=None):
    """Active stock holdings with owner name and latest recorded quantity/
    price/date joined, plus derived total_value/net_value for that latest
    entry. All four latest_* and derived fields are None for a holding with
    no value entries yet."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT h.id, h.symbol, h.brokerage_firm, h.holding_type, h.owner_id,
                   h.cost_basis, h.excluded_from_net_worth, m.name AS owner_name,
                   sv.date AS latest_date, sv.quantity AS latest_quantity,
                   sv.price_per_unit AS latest_price
            FROM stock_holdings h
            LEFT JOIN household_members m ON m.id = h.owner_id
            LEFT JOIN stock_values sv ON sv.id = (
                SELECT id FROM stock_values WHERE holding_id = h.id ORDER BY date DESC LIMIT 1
            )
            WHERE h.is_deleted = 0
            ORDER BY h.symbol
            """
        ).fetchall()
    holdings = []
    for row in rows:
        d = dict(row)
        if d["latest_quantity"] is not None:
            d["latest_total_value"], d["latest_net_value"] = _compute_stock_value(
                d["latest_quantity"], d["latest_price"], d["cost_basis"]
            )
        else:
            d["latest_total_value"], d["latest_net_value"] = None, None
        holdings.append(d)
    return holdings


def add_stock_holding(symbol, brokerage_firm="", holding_type="stock", owner_id=None,
                       cost_basis=None, db_path=None):
    """Add a new stock holding. Returns updated list."""
    if holding_type not in STOCK_HOLDING_TYPES:
        raise ValueError(f'Invalid holding_type "{holding_type}". Must be one of {STOCK_HOLDING_TYPES}.')
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO stock_holdings (symbol, brokerage_firm, holding_type, owner_id, cost_basis) "
            "VALUES (?, ?, ?, ?, ?)",
            (symbol, brokerage_firm, holding_type, owner_id, cost_basis),
        )
    return get_stock_holdings(db_path)


STOCK_HOLDING_EDITABLE_FIELDS = {
    "symbol", "brokerage_firm", "holding_type", "owner_id", "cost_basis", "excluded_from_net_worth",
}


def update_stock_holding(holding_id, fields, db_path=None):
    """Partially update a stock holding. `fields` is a dict of column -> new
    value; only keys present are changed. Returns updated list."""
    cols = [c for c in fields if c in STOCK_HOLDING_EDITABLE_FIELDS]
    if not cols:
        return get_stock_holdings(db_path)
    if "holding_type" in fields and fields["holding_type"] not in STOCK_HOLDING_TYPES:
        raise ValueError(
            f'Invalid holding_type "{fields["holding_type"]}". Must be one of {STOCK_HOLDING_TYPES}.'
        )
    with _connect(db_path) as conn:
        row = conn.execute("SELECT id FROM stock_holdings WHERE id = ?", (holding_id,)).fetchone()
        if row is None:
            raise ValueError(f"Stock holding {holding_id} not found.")
        set_clause = ", ".join(f"{c} = ?" for c in cols)
        conn.execute(
            f"UPDATE stock_holdings SET {set_clause} WHERE id = ?",
            [fields[c] for c in cols] + [holding_id],
        )
    return get_stock_holdings(db_path)


def delete_stock_holding(holding_id, db_path=None):
    """Soft-delete a stock holding. Returns updated list."""
    with _connect(db_path) as conn:
        row = conn.execute("SELECT id FROM stock_holdings WHERE id = ?", (holding_id,)).fetchone()
        if row is None:
            raise ValueError(f"Stock holding {holding_id} not found.")
        conn.execute("UPDATE stock_holdings SET is_deleted = 1 WHERE id = ?", (holding_id,))
    return get_stock_holdings(db_path)


# ── Stock values ──────────────────────────────────────────────────────────────

def get_stock_values(holding_id=None, db_path=None):
    """Return value entries, optionally filtered to one holding, newest first."""
    with _connect(db_path) as conn:
        if holding_id is None:
            rows = conn.execute(
                "SELECT id, holding_id, date, quantity, price_per_unit FROM stock_values "
                "ORDER BY date DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, holding_id, date, quantity, price_per_unit FROM stock_values "
                "WHERE holding_id = ? ORDER BY date DESC",
                (holding_id,),
            ).fetchall()
    return [dict(row) for row in rows]


def add_stock_value(holding_id, date, quantity, price_per_unit, db_path=None):
    """Add or update a holding's quantity/price for a given date (upsert on
    holding_id+date, same pattern as fund balances)."""
    with _connect(db_path) as conn:
        holding = conn.execute(
            "SELECT id FROM stock_holdings WHERE id = ?", (holding_id,)
        ).fetchone()
        if holding is None:
            raise ValueError(f"Stock holding {holding_id} not found.")
        conn.execute(
            """
            INSERT INTO stock_values (holding_id, date, quantity, price_per_unit)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(holding_id, date) DO UPDATE SET
                quantity = excluded.quantity,
                price_per_unit = excluded.price_per_unit
            """,
            (holding_id, date, quantity, price_per_unit),
        )
    return get_stock_values(holding_id, db_path)


def delete_stock_value(value_id, db_path=None):
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT holding_id FROM stock_values WHERE id = ?", (value_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Stock value {value_id} not found.")
        holding_id = row["holding_id"]
        conn.execute("DELETE FROM stock_values WHERE id = ?", (value_id,))
    return get_stock_values(holding_id, db_path)


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
    """Return active (non-deleted) bank accounts, with owner name joined.

    Includes accounts excluded from Net Worth — that flag only affects
    get_net_worth_series, not this listing.
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.name, a.account_number, a.owner_id,
                   a.excluded_from_net_worth, a.risk_level, a.risk_note, m.name AS owner_name
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


BANK_ACCOUNT_EDITABLE_FIELDS = {"excluded_from_net_worth", "risk_level", "risk_note"}


def update_bank_account(account_id, fields, db_path=None):
    """Partially update a bank account. `fields` is a dict of column -> new
    value; only keys present are changed. Returns updated list."""
    cols = [c for c in fields if c in BANK_ACCOUNT_EDITABLE_FIELDS]
    if not cols:
        return get_bank_accounts(db_path)
    _validate_risk_level(fields)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT id FROM bank_accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None:
            raise ValueError(f"Bank account {account_id} not found.")
        set_clause = ", ".join(f"{c} = ?" for c in cols)
        conn.execute(
            f"UPDATE bank_accounts SET {set_clause} WHERE id = ?",
            [fields[c] for c in cols] + [account_id],
        )
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
            r.get("notes", ""),
        ))
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO bank_transactions "
            "(account_id, date, description, reference, amount, balance_after, type, "
            " category, month, year, imported_at, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            prepared,
        )
    return len(prepared)


def filter_new_bank_transactions(rows, account_id, db_path=None):
    """Split rows into (new, duplicates) for an account.

    A row is a duplicate if a transaction with the same date, reference,
    and amount already exists — this is what makes overlapping monthly
    exports safe to re-import.
    """
    new, duplicates = [], []
    with _connect(db_path) as conn:
        for r in rows:
            hit = conn.execute(
                "SELECT 1 FROM bank_transactions "
                "WHERE account_id = ? AND date = ? AND reference = ? AND amount = ? LIMIT 1",
                (account_id, r["date"], r.get("reference", ""), r["amount"]),
            ).fetchone()
            (duplicates if hit else new).append(r)
    return new, duplicates


def get_bank_transactions(account_id=None, db_path=None):
    """Transactions with account name joined; the all-accounts listing
    omits transactions of soft-deleted accounts."""
    base = (
        "SELECT t.id, t.account_id, a.name AS account_name, t.date, t.description, "
        "t.reference, t.amount, t.balance_after, t.type, t.category, t.month, t.year, "
        "t.excluded, t.notes "
        "FROM bank_transactions t JOIN bank_accounts a ON a.id = t.account_id "
    )
    with _connect(db_path) as conn:
        if account_id is None:
            rows = conn.execute(base + "WHERE a.is_deleted = 0 ORDER BY t.date DESC").fetchall()
        else:
            rows = conn.execute(
                base + "WHERE t.account_id = ? ORDER BY t.date DESC", (account_id,)
            ).fetchall()
    return [dict(row) for row in rows]


def set_bank_transaction_excluded(transaction_id, excluded, db_path=None):
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE bank_transactions SET excluded = ? WHERE id = ?",
            (1 if excluded else 0, transaction_id),
        )


def set_bank_transaction_category(transaction_id, category, db_path=None):
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE bank_transactions SET category = ? WHERE id = ?",
            (category, transaction_id),
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
    """Monthly net-worth series across all active funds, bank accounts, and
    stock holdings.

    Funds: the last recorded balance within each month, carried forward
    through months without an entry. Bank accounts: walk transactions
    chronologically — a row with balance_after (imported) anchors the
    running balance to the bank's real figure, rows without it (manual
    entry) add their amount. Stock holdings: last recorded quantity/price
    within each month (same carry-forward as funds), contributing net value
    when cost basis is known, else total value — a holding is never silently
    dropped from the total just because cost basis hasn't been entered yet.
    Months before an item's first data point are None.
    """
    with _connect(db_path) as conn:
        funds = conn.execute(
            """
            SELECT f.id, f.name, f.fund_type, m.name AS owner_name
            FROM funds f LEFT JOIN household_members m ON m.id = f.owner_id
            WHERE f.is_deleted = 0 AND f.excluded_from_net_worth = 0 ORDER BY f.name
            """
        ).fetchall()
        accounts = conn.execute(
            """
            SELECT a.id, a.name, m.name AS owner_name
            FROM bank_accounts a LEFT JOIN household_members m ON m.id = a.owner_id
            WHERE a.is_deleted = 0 AND a.excluded_from_net_worth = 0 ORDER BY a.name
            """
        ).fetchall()
        stocks = conn.execute(
            """
            SELECT h.id, h.symbol, h.cost_basis, h.holding_type, m.name AS owner_name
            FROM stock_holdings h LEFT JOIN household_members m ON m.id = h.owner_id
            WHERE h.is_deleted = 0 AND h.excluded_from_net_worth = 0 ORDER BY h.symbol
            """
        ).fetchall()
        fund_rows = conn.execute(
            "SELECT fund_id, date, balance FROM fund_balances ORDER BY date"
        ).fetchall()
        bank_rows = conn.execute(
            "SELECT account_id, date, amount, balance_after FROM bank_transactions "
            "WHERE excluded = 0 ORDER BY date, id"
        ).fetchall()
        stock_value_rows = conn.execute(
            "SELECT holding_id, date, quantity, price_per_unit FROM stock_values ORDER BY date"
        ).fetchall()

    active_funds = {f["id"] for f in funds}
    active_accounts = {a["id"] for a in accounts}
    active_stocks = {s["id"] for s in stocks}
    fund_rows = [r for r in fund_rows if r["fund_id"] in active_funds]
    bank_rows = [r for r in bank_rows if r["account_id"] in active_accounts]
    stock_value_rows = [r for r in stock_value_rows if r["holding_id"] in active_stocks]

    data_months = (
        {r["date"][:7] for r in fund_rows}
        | {r["date"][:7] for r in bank_rows}
        | {r["date"][:7] for r in stock_value_rows}
    )
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
        month_end = {}
        running = 0.0
        for r in bank_rows:
            if r["account_id"] == a["id"]:
                if r["balance_after"] is not None:
                    running = r["balance_after"]
                else:
                    running += r["amount"]
                month_end[r["date"][:7]] = round(running, 2)
        balances, last = [], None
        for month in months:
            last = month_end.get(month, last)
            balances.append(last)
        series.append({
            "key": f"bank-{a['id']}", "kind": "bank", "name": a["name"],
            "fund_type": None, "owner_name": a["owner_name"],
            "balances": balances,
        })

    for s in stocks:
        by_month = {}
        for r in stock_value_rows:
            if r["holding_id"] == s["id"]:
                by_month[r["date"][:7]] = (r["quantity"], r["price_per_unit"])
        balances, last = [], None
        for month in months:
            last = by_month.get(month, last)
            if last is None:
                balances.append(None)
            else:
                quantity, price_per_unit = last
                total_value, net_value = _compute_stock_value(quantity, price_per_unit, s["cost_basis"])
                balances.append(net_value if net_value is not None else total_value)
        series.append({
            "key": f"stock-{s['id']}", "kind": "stock", "name": s["symbol"],
            "fund_type": None, "owner_name": s["owner_name"], "holding_type": s["holding_type"],
            "balances": balances,
        })

    return {"months": months, "series": series}

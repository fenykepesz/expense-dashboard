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
    risk_note              TEXT    NOT NULL DEFAULT '',
    track_number           TEXT    NOT NULL DEFAULT '',
    institution_reg_number TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fund_balances (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id      INTEGER NOT NULL REFERENCES funds(id),
    date         TEXT    NOT NULL,
    balance      REAL    NOT NULL,
    contribution REAL    NOT NULL DEFAULT 0,
    UNIQUE(fund_id, date)
);

CREATE TABLE IF NOT EXISTS fund_fees (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id     INTEGER NOT NULL REFERENCES funds(id),
    fee_basis   TEXT    NOT NULL,
    fee_percent REAL    NOT NULL,
    UNIQUE(fund_id, fee_basis)
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
    excluded_from_net_worth INTEGER NOT NULL DEFAULT 0,
    isin                    TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS stock_values (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    holding_id     INTEGER NOT NULL REFERENCES stock_holdings(id),
    date           TEXT    NOT NULL,
    quantity       REAL    NOT NULL,
    price_per_unit REAL    NOT NULL,
    UNIQUE(holding_id, date)
);

CREATE TABLE IF NOT EXISTS holdings_filings (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_reg_number TEXT    NOT NULL,
    institution_name       TEXT    NOT NULL DEFAULT '',
    period_year            INTEGER NOT NULL,
    period_quarter         INTEGER NOT NULL,
    source_filename        TEXT    NOT NULL DEFAULT '',
    imported_at            TEXT    NOT NULL DEFAULT '',
    is_deleted             INTEGER NOT NULL DEFAULT 0,
    UNIQUE(institution_reg_number, period_year, period_quarter)
);

CREATE TABLE IF NOT EXISTS fund_holdings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filing_id       INTEGER NOT NULL REFERENCES holdings_filings(id),
    fund_id         INTEGER NOT NULL REFERENCES funds(id),
    instrument_type TEXT    NOT NULL,
    issuer_name     TEXT    NOT NULL DEFAULT '',
    issuer_number   TEXT    NOT NULL DEFAULT '',
    security_name   TEXT    NOT NULL DEFAULT '',
    security_number TEXT    NOT NULL DEFAULT '',
    pct_of_track    REAL    NOT NULL DEFAULT 0,
    fair_value_ils  REAL    NOT NULL DEFAULT 0,
    country         TEXT    NOT NULL DEFAULT '',
    sector          TEXT    NOT NULL DEFAULT '',
    currency        TEXT    NOT NULL DEFAULT ''
);
"""

FUND_TYPES = [
    "pension", "study_fund", "provident_fund", "investment_provident_fund",
    "money_market_fund", "savings_policy", "investment", "real_estate", "other",
]

# A fund can charge more than one of these at once (e.g. a deposit fee AND a
# separate balance fee) — hence a UNIQUE(fund_id, fee_basis) row per basis,
# not a single fee column on `funds`.
FEE_BASIS_OPTIONS = ["deposits", "earnings", "total"]

# Kept granular (tradable/non-tradable variants stay distinct) rather than
# collapsed, matching the look-through feature's "full precision, no cutoffs"
# design — see IDEAS.md.
INSTRUMENT_TYPES = [
    "cash", "govt_bond", "corp_bond", "equity_traded", "equity_nontraded",
    "etf", "mutual_fund", "warrant", "option", "future", "structured_product",
    "investment_fund", "loan", "deposit", "real_estate",
    "fx_swap", "interest_rate_swap", "equity_swap", "inflation_swap",
    "other",
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
            ("track_number",            "TEXT NOT NULL DEFAULT ''"),
            ("institution_reg_number",  "TEXT NOT NULL DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE funds ADD COLUMN {col} {definition}")
            except sqlite3.OperationalError:
                pass
        # Drop removed fund columns
        for col in ["official_fund_number"]:
            try:
                conn.execute(f"ALTER TABLE funds DROP COLUMN {col}")
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
        # Migrate old stock_holdings columns
        for col, definition in [
            ("isin", "TEXT NOT NULL DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE stock_holdings ADD COLUMN {col} {definition}")
            except sqlite3.OperationalError:
                pass
        # Migrate old fund_holdings columns
        for col, definition in [
            ("fair_value_ils", "REAL NOT NULL DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE fund_holdings ADD COLUMN {col} {definition}")
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
    """Return active (non-deleted) funds, with owner name, latest balance,
    and management fees joined, sorted by name.

    Includes funds excluded from Net Worth — that flag only affects
    get_net_worth_series, not this listing. latest_balance/latest_balance_date
    are None for a fund with no recorded balance entries yet. `fees` is a
    list of {id, fee_basis, fee_percent} — empty if none are set.
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT f.id, f.name, f.company_name, f.fund_number,
                   f.track_number, f.institution_reg_number,
                   f.fund_type, f.owner_id,
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
        fee_rows = conn.execute(
            "SELECT id, fund_id, fee_basis, fee_percent FROM fund_fees ORDER BY fee_basis"
        ).fetchall()

    fees_by_fund = {}
    for fr in fee_rows:
        fees_by_fund.setdefault(fr["fund_id"], []).append(
            {"id": fr["id"], "fee_basis": fr["fee_basis"], "fee_percent": fr["fee_percent"]}
        )

    funds = [dict(row) for row in rows]
    for f in funds:
        f["fees"] = fees_by_fund.get(f["id"], [])
    return funds


def _validate_risk_level(fields):
    """Shared by update_fund/update_bank_account: 0 (Not Rated) or a real level."""
    if "risk_level" in fields and fields["risk_level"] not in (0, *RISK_LEVELS):
        raise ValueError(f'Invalid risk_level "{fields["risk_level"]}". Must be 0 or one of {list(RISK_LEVELS)}.')


def _validate_unique_track_key(conn, institution_reg_number, track_number, exclude_fund_id=None):
    """A fund's (institution_reg_number, track_number) pair, when both are
    set, must be unique among active funds — two of the user's own funds
    resolving to the same look-through filing rows would make aggregation
    ambiguous (which fund's balance does a matched row actually belong to?).
    """
    if not institution_reg_number or not track_number:
        return
    query = (
        "SELECT id FROM funds WHERE is_deleted = 0 "
        "AND institution_reg_number = ? AND track_number = ?"
    )
    params = [institution_reg_number, track_number]
    if exclude_fund_id is not None:
        query += " AND id != ?"
        params.append(exclude_fund_id)
    if conn.execute(query, params).fetchone():
        raise ValueError(
            f'Another fund already uses institution "{institution_reg_number}" '
            f'+ track "{track_number}".'
        )


def add_fund(name, fund_type, company_name="", owner_id=None, fund_number="",
             is_liquid=False, risk_level=0, risk_note="",
             track_number="", institution_reg_number="", db_path=None):
    """Add a new fund. Returns updated list."""
    if fund_type not in FUND_TYPES:
        raise ValueError(f'Invalid fund_type "{fund_type}". Must be one of {FUND_TYPES}.')
    _validate_risk_level({"risk_level": risk_level})
    with _connect(db_path) as conn:
        _validate_unique_track_key(conn, institution_reg_number, track_number)
        conn.execute(
            "INSERT INTO funds (name, company_name, fund_number, "
            "track_number, institution_reg_number, fund_type, owner_id, is_liquid, "
            "risk_level, risk_note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, company_name, fund_number, track_number,
             institution_reg_number, fund_type, owner_id, 1 if is_liquid else 0,
             risk_level, risk_note),
        )
    return get_funds(db_path)


FUND_EDITABLE_FIELDS = {
    "name", "company_name", "fund_number", "track_number",
    "institution_reg_number", "fund_type", "owner_id",
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
        row = conn.execute(
            "SELECT institution_reg_number, track_number FROM funds WHERE id = ?", (fund_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Fund {fund_id} not found.")
        if "institution_reg_number" in fields or "track_number" in fields:
            resolved_inst = fields.get("institution_reg_number", row["institution_reg_number"])
            resolved_track = fields.get("track_number", row["track_number"])
            _validate_unique_track_key(conn, resolved_inst, resolved_track, exclude_fund_id=fund_id)
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


# ── Fund management fees ─────────────────────────────────────────────────────
#
# A fund can charge more than one fee at once (e.g. a deposit fee AND a
# separate balance fee), so this is a one-to-few related table, not columns
# on `funds` — at most one row per (fund, basis) via the UNIQUE constraint.

def get_fund_fees(fund_id=None, db_path=None):
    """Return fee entries, optionally filtered to one fund."""
    with _connect(db_path) as conn:
        if fund_id is None:
            rows = conn.execute(
                "SELECT id, fund_id, fee_basis, fee_percent FROM fund_fees ORDER BY fund_id, fee_basis"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, fund_id, fee_basis, fee_percent FROM fund_fees "
                "WHERE fund_id = ? ORDER BY fee_basis",
                (fund_id,),
            ).fetchall()
    return [dict(row) for row in rows]


def add_fund_fee(fund_id, fee_basis, fee_percent, db_path=None):
    """Add or update a fund's fee for a given basis (upsert on fund_id+fee_basis
    — a fund has at most one fee per basis, but can have one per basis at
    once). Returns the updated funds list, since fees render inline there."""
    if fee_basis not in FEE_BASIS_OPTIONS:
        raise ValueError(f'Invalid fee_basis "{fee_basis}". Must be one of {FEE_BASIS_OPTIONS}.')
    with _connect(db_path) as conn:
        fund = conn.execute("SELECT id FROM funds WHERE id = ?", (fund_id,)).fetchone()
        if fund is None:
            raise ValueError(f"Fund {fund_id} not found.")
        conn.execute(
            """
            INSERT INTO fund_fees (fund_id, fee_basis, fee_percent)
            VALUES (?, ?, ?)
            ON CONFLICT(fund_id, fee_basis) DO UPDATE SET
                fee_percent = excluded.fee_percent
            """,
            (fund_id, fee_basis, fee_percent),
        )
    return get_funds(db_path)


def delete_fund_fee(fee_id, db_path=None):
    """Remove one fee entry. Returns the updated funds list."""
    with _connect(db_path) as conn:
        row = conn.execute("SELECT id FROM fund_fees WHERE id = ?", (fee_id,)).fetchone()
        if row is None:
            raise ValueError(f"Fund fee {fee_id} not found.")
        conn.execute("DELETE FROM fund_fees WHERE id = ?", (fee_id,))
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
                   h.cost_basis, h.excluded_from_net_worth, h.isin, m.name AS owner_name,
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
                       cost_basis=None, isin="", db_path=None):
    """Add a new stock holding. Returns updated list."""
    if holding_type not in STOCK_HOLDING_TYPES:
        raise ValueError(f'Invalid holding_type "{holding_type}". Must be one of {STOCK_HOLDING_TYPES}.')
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO stock_holdings (symbol, brokerage_firm, holding_type, owner_id, "
            "cost_basis, isin) VALUES (?, ?, ?, ?, ?, ?)",
            (symbol, brokerage_firm, holding_type, owner_id, cost_basis, isin),
        )
    return get_stock_holdings(db_path)


STOCK_HOLDING_EDITABLE_FIELDS = {
    "symbol", "brokerage_firm", "holding_type", "owner_id", "cost_basis",
    "excluded_from_net_worth", "isin",
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


# ── Look-through holdings ────────────────────────────────────────────────────
#
# One quarterly regulatory filing (holdings_filings) per institution, each
# holding a snapshot of security-level rows (fund_holdings) already resolved
# to a specific fund_id and scoped to the user's own tracks at parse time —
# aggregation here never needs to re-derive which fund a row belongs to.

def replace_fund_holdings_filing(institution_reg_number, institution_name, period_year,
                                  period_quarter, rows, source_filename="", db_path=None):
    """Upsert one institution-quarter filing and replace all of its holdings
    rows. `rows` is a list of dicts: fund_id, instrument_type, issuer_name,
    issuer_number, security_name, security_number, pct_of_track,
    fair_value_ils, country, sector, currency. Re-uploading the SAME
    (institution, year, quarter) is a
    full replace, not an append — a filing is a point-in-time snapshot, and
    companies do file corrected re-submissions. Uploading a genuinely new
    quarter is a separate filing (new row), so history isn't lost."""
    imported_at = datetime.now().isoformat(timespec="seconds")
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO holdings_filings
                (institution_reg_number, institution_name, period_year, period_quarter,
                 source_filename, imported_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(institution_reg_number, period_year, period_quarter) DO UPDATE SET
                institution_name = excluded.institution_name,
                source_filename = excluded.source_filename,
                imported_at = excluded.imported_at,
                is_deleted = 0
            """,
            (institution_reg_number, institution_name, period_year, period_quarter,
             source_filename, imported_at),
        )
        filing_id = conn.execute(
            "SELECT id FROM holdings_filings WHERE institution_reg_number = ? "
            "AND period_year = ? AND period_quarter = ?",
            (institution_reg_number, period_year, period_quarter),
        ).fetchone()["id"]
        conn.execute("DELETE FROM fund_holdings WHERE filing_id = ?", (filing_id,))
        conn.executemany(
            """
            INSERT INTO fund_holdings
                (filing_id, fund_id, instrument_type, issuer_name, issuer_number,
                 security_name, security_number, pct_of_track, fair_value_ils,
                 country, sector, currency)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (filing_id, r["fund_id"], r["instrument_type"], r.get("issuer_name", ""),
                 r.get("issuer_number", ""), r.get("security_name", ""),
                 r.get("security_number", ""), r.get("pct_of_track", 0),
                 r.get("fair_value_ils", 0), r.get("country", ""),
                 r.get("sector", ""), r.get("currency", ""))
                for r in rows
            ],
        )
    return {"filing_id": filing_id, "inserted": len(rows)}


def get_holdings_filings(db_path=None):
    """Return active filings, newest period first."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, institution_reg_number, institution_name, period_year, "
            "period_quarter, source_filename, imported_at FROM holdings_filings "
            "WHERE is_deleted = 0 ORDER BY period_year DESC, period_quarter DESC, institution_name"
        ).fetchall()
    return [dict(row) for row in rows]


def delete_holdings_filing(filing_id, db_path=None):
    """Soft-delete a filing. Returns updated list."""
    with _connect(db_path) as conn:
        row = conn.execute("SELECT id FROM holdings_filings WHERE id = ?", (filing_id,)).fetchone()
        if row is None:
            raise ValueError(f"Holdings filing {filing_id} not found.")
        conn.execute("UPDATE holdings_filings SET is_deleted = 1 WHERE id = ?", (filing_id,))
    return get_holdings_filings(db_path)


def _latest_filing_ids(conn):
    """Among active filings, the id of the latest (period_year, period_quarter)
    per institution — the "current state" rule every look-through aggregation
    read uses. A stale filing for an institution that's since been
    superseded never contributes once a newer one for that same institution
    exists."""
    rows = conn.execute(
        "SELECT id, institution_reg_number, period_year, period_quarter "
        "FROM holdings_filings WHERE is_deleted = 0"
    ).fetchall()
    latest = {}
    for r in rows:
        key = r["institution_reg_number"]
        period = (r["period_year"], r["period_quarter"])
        if key not in latest or period > latest[key][0]:
            latest[key] = (period, r["id"])
    return {v[1] for v in latest.values()}


def get_security_holdings(db_path=None):
    """Per-security look-through exposure across every active fund's own
    money, using the latest filing per institution. Grouped by
    (issuer_number, security_number) — falling back to (issuer_number,
    security_name) for rows that structurally lack a security number (cash,
    loans, deposits), then (instrument_type, issuer_name) as a last resort —
    never by name alone when an ID exists, per the look-through feature's
    core matching decision.

    Dollar value: `fair_value_ils` on each row is the filing's own absolute
    fair-value figure for that security — but it's the INSTITUTIONAL total
    for that whole track (every policyholder invested in it combined), not
    this user's personal share. Confirmed against real data: summing every
    row for one fund came to ~1,500x-8,750x the user's own recorded
    fund_balances for that same fund. To get a personally-meaningful number,
    each row is converted to a WEIGHT within its own fund's track
    (`row.fair_value_ils / sum of fair_value_ils across that whole fund`),
    then that weight is applied to the user's own `fund_balances` entry for
    that fund. A fund with holdings rows but no recorded balance yet can't
    have its personal weight computed at all — flagged via
    `has_unbalanced_fund` and contributes 0, never a guessed number.

    (Earlier attempts, in order: `fund_balance × pct_of_track` — wrong,
    since "% of track" sums to ~100% within each instrument-category sheet,
    not across the track. Then raw `fair_value_ils` directly — wrong, since
    it's the whole track's institutional total, not this user's share. This
    weighted version is the corrected formula.)

    Divergent sector/country/currency across rows grouped as "the same
    security" (independent filers can classify identically-keyed securities
    differently) sets `classification_conflict` and leaves that field None
    rather than silently picking one — see `*_values` for what was seen.
    """
    with _connect(db_path) as conn:
        latest_ids = _latest_filing_ids(conn)
        if not latest_ids:
            return {"securities": [], "active_funds": []}
        placeholders = ",".join(["?"] * len(latest_ids))
        holding_rows = conn.execute(
            f"""
            SELECT fh.fund_id, fh.instrument_type, fh.issuer_name, fh.issuer_number,
                   fh.security_name, fh.security_number, fh.pct_of_track,
                   fh.fair_value_ils, fh.country, fh.sector, fh.currency,
                   f.name AS fund_name, f.fund_type, f.track_number,
                   fb.balance AS fund_balance
            FROM fund_holdings fh
            JOIN funds f ON f.id = fh.fund_id AND f.is_deleted = 0
            LEFT JOIN fund_balances fb ON fb.id = (
                SELECT id FROM fund_balances WHERE fund_id = f.id ORDER BY date DESC LIMIT 1
            )
            WHERE fh.filing_id IN ({placeholders})
            """,
            list(latest_ids),
        ).fetchall()

    # Each fund's track-wide institutional total — the denominator that
    # turns one row's institutional fair value into this user's personal
    # weight within that fund.
    fund_totals = {}
    for r in holding_rows:
        fund_totals[r["fund_id"]] = fund_totals.get(r["fund_id"], 0.0) + r["fair_value_ils"]

    groups = {}
    active_funds = {}
    for r in holding_rows:
        # track_number is included since two of the user's own funds can
        # share an identical display name (confirmed real case: two tracks
        # under one savings policy) — callers need it to tell them apart.
        active_funds[r["fund_id"]] = {
            "id": r["fund_id"], "name": r["fund_name"], "fund_type": r["fund_type"],
            "track_number": r["track_number"],
        }

        if r["security_number"]:
            key = ("id", r["issuer_number"], r["security_number"])
        elif r["security_name"]:
            key = ("name", r["issuer_number"], r["security_name"])
        else:
            key = ("type", r["instrument_type"], r["issuer_name"])

        g = groups.setdefault(key, {
            "issuer_name": r["issuer_name"], "issuer_number": r["issuer_number"],
            "security_name": r["security_name"] or r["issuer_name"],
            "security_number": r["security_number"], "instrument_type": r["instrument_type"],
            "combined_value": 0.0, "by_fund": {}, "has_unbalanced_fund": False,
            "_countries": set(), "_sectors": set(), "_currencies": set(),
        })

        fund_total = fund_totals.get(r["fund_id"], 0.0)
        if r["fund_balance"] is None or not fund_total:
            g["has_unbalanced_fund"] = True
            value = 0.0
        else:
            weight = r["fair_value_ils"] / fund_total
            value = weight * r["fund_balance"]

        g["combined_value"] += value
        g["by_fund"][r["fund_id"]] = g["by_fund"].get(r["fund_id"], 0.0) + value
        if r["country"]:
            g["_countries"].add(r["country"])
        if r["sector"]:
            g["_sectors"].add(r["sector"])
        if r["currency"]:
            g["_currencies"].add(r["currency"])

    securities = []
    for g in groups.values():
        g["fund_count"] = len(g["by_fund"])
        g["country_values"] = sorted(g.pop("_countries"))
        g["sector_values"] = sorted(g.pop("_sectors"))
        g["currency_values"] = sorted(g.pop("_currencies"))
        g["classification_conflict"] = (
            len(g["country_values"]) > 1 or len(g["sector_values"]) > 1 or len(g["currency_values"]) > 1
        )
        g["country"] = g["country_values"][0] if len(g["country_values"]) == 1 else None
        g["sector"] = g["sector_values"][0] if len(g["sector_values"]) == 1 else None
        g["currency"] = g["currency_values"][0] if len(g["currency_values"]) == 1 else None
        g["combined_value"] = round(g["combined_value"], 2)
        g["by_fund"] = {k: round(v, 2) for k, v in g["by_fund"].items()}
        securities.append(g)

    securities.sort(key=lambda s: s["combined_value"], reverse=True)
    return {"securities": securities, "active_funds": list(active_funds.values())}


def get_all_securities(db_path=None):
    """THE primary Look-Through view: every security the user personally
    holds, fund-derived (indirect) and directly-held combined into one
    number per security — e.g. a directly-held MSFT position and MSFT
    exposure inside a fund both count toward the same row and the same
    `pct_of_total`. Matched strictly on security_number == stock_holdings.isin
    (both non-blank) — no name-based fallback, per the feature's ID-only
    matching decision. A direct holding with no ISIN can't be merged at all
    and is reported separately in `unmatched_direct`.

    `pct_of_total` is each security's share of the sum of EVERY entry here —
    the user's whole personally-held-security universe, direct and indirect
    together (not just the fund-derived subset `get_security_holdings`
    covers on its own).

    IMPORTANT: a security_number is NOT guaranteed unique across instrument
    types — confirmed against real data where a written equity option's
    security_number was the SAME as its underlying stock's ISIN, but with a
    different issuer_number (the option's counterparty vs. the equity's
    issuer). get_security_holdings correctly keeps those as separate
    entries (its own key includes issuer_number). This function must NOT
    re-key on security_number alone when merging — an earlier version of
    this code did exactly that and silently overwrote one entry with
    another, losing real money (confirmed: 8 collisions, ~₪62,000 vanished
    on the real Fenix data). Every indirect entry keeps its own identity
    here; a direct holding's ISIN is matched to AT MOST ONE of possibly
    several same-security_number entries (preferring an equity-shaped
    instrument_type, since a direct stock holding is never meant to merge
    into a derivative's exposure) — the rest stay indirect-only, correct
    but simply not merge targets for that ISIN.
    """
    indirect_result = get_security_holdings(db_path)
    indirect = indirect_result["securities"]
    direct = get_stock_holdings(db_path)

    by_key = {}
    isin_candidates = {}  # security_number -> [key, ...], for matching direct holdings
    for i, s in enumerate(indirect):
        entry = {
            "issuer_name": s["issuer_name"], "issuer_number": s["issuer_number"],
            "security_name": s["security_name"], "security_number": s["security_number"],
            "instrument_type": s["instrument_type"],
            "indirect_value": s["combined_value"], "direct_value": 0.0,
            "by_fund": s["by_fund"], "has_unbalanced_fund": s["has_unbalanced_fund"],
            "country": s["country"], "sector": s["sector"], "currency": s["currency"],
            "classification_conflict": s["classification_conflict"],
            "country_values": s["country_values"], "sector_values": s["sector_values"],
            "currency_values": s["currency_values"],
        }
        # Full identity, mirroring get_security_holdings' own grouping —
        # never collapse two things it kept separate.
        key = ("indirect", i)
        by_key[key] = entry
        if s["security_number"]:
            isin_candidates.setdefault(s["security_number"], []).append(key)

    # A direct holding is always an equity-shaped instrument — prefer
    # merging into an equity-typed candidate over a derivative that happens
    # to share the same security_number.
    _EQUITY_LIKE = ("equity_traded", "equity_nontraded", "etf", "mutual_fund")

    def _best_match(isin):
        candidates = isin_candidates.get(isin)
        if not candidates:
            return None
        for pref in _EQUITY_LIKE:
            for key in candidates:
                if by_key[key]["instrument_type"] == pref:
                    return key
        return candidates[0]

    unmatched_direct = []
    for h in direct:
        direct_value = h["latest_net_value"] if h["latest_net_value"] is not None else (h["latest_total_value"] or 0)
        if not h["isin"]:
            unmatched_direct.append({
                "holding_id": h["id"], "symbol": h["symbol"], "value": round(direct_value, 2),
            })
            continue
        key = _best_match(h["isin"]) or ("direct", h["isin"])
        entry = by_key.get(key)
        if entry is None:
            entry = by_key[key] = {
                "issuer_name": "", "issuer_number": "",
                "security_name": h["symbol"], "security_number": h["isin"],
                "instrument_type": None,
                "indirect_value": 0.0, "direct_value": 0.0,
                "by_fund": {}, "has_unbalanced_fund": False,
                "country": "", "sector": "", "currency": "",
                "classification_conflict": False,
                "country_values": [], "sector_values": [], "currency_values": [],
            }
        entry["direct_value"] += direct_value

    securities = []
    grand_total = 0.0
    for entry in by_key.values():
        entry["combined_value"] = round(entry["indirect_value"] + entry["direct_value"], 2)
        entry["indirect_value"] = round(entry["indirect_value"], 2)
        entry["direct_value"] = round(entry["direct_value"], 2)
        entry["fund_count"] = len(entry["by_fund"])
        grand_total += entry["combined_value"]
        securities.append(entry)
    for entry in securities:
        entry["pct_of_total"] = round(entry["combined_value"] / grand_total, 4) if grand_total else 0.0

    securities.sort(key=lambda e: e["combined_value"], reverse=True)
    return {
        "securities": securities,
        "active_funds": indirect_result["active_funds"],
        "unmatched_direct": unmatched_direct,
        "total_value": round(grand_total, 2),
    }


def get_overlap_holdings(db_path=None):
    """Securities held in 2+ of the user's funds (fund-side overlap
    specifically — a security also held directly is a single direct
    position by definition, it doesn't add a second "fund"), pulled from
    the merged All Securities set so every number shown here matches what's
    shown there. The largest single fund's share of the combined value is
    a concentration signal."""
    result = get_all_securities(db_path)
    overlap = []
    for s in result["securities"]:
        if s["fund_count"] < 2:
            continue
        s = dict(s)
        s["max_single_fund_share"] = (
            round(max(s["by_fund"].values()) / s["combined_value"], 4) if s["combined_value"] else None
        )
        overlap.append(s)
    return {"securities": overlap, "active_funds": result["active_funds"]}


def get_concentration_rollups(db_path=None):
    """Sector/Country/Currency rollups, each with a dual denominator:
    pct_of_portfolio (of every security) and pct_of_named (excluding blank
    or classification_conflict rows) — so unclassified holdings can't
    silently dilute the categorized breakdown, and can't silently vanish
    from the overall total either. Plus same_issuer_cross_type: exposure to
    the same issuer summed across every instrument type it appears as (e.g.
    a bank's stock + that bank's bonds = one counterparty exposure), with a
    `type_breakdown` showing how much of that issuer's total sits in each
    type (e.g. מדינת ישראל: 500K total = 100K bonds + 400K loans).

    Runs on the merged All Securities set (direct + fund-derived together),
    same as Overlap."""
    securities = get_all_securities(db_path)["securities"]
    total_portfolio = sum(s["combined_value"] for s in securities)

    def rollup(field):
        named_total = sum(
            s["combined_value"] for s in securities
            if s[field] and not s["classification_conflict"]
        )
        buckets = {}
        unclassified = 0.0
        conflicting = 0.0
        for s in securities:
            if s["classification_conflict"]:
                conflicting += s["combined_value"]
            elif not s[field]:
                unclassified += s["combined_value"]
            else:
                buckets[s[field]] = buckets.get(s[field], 0.0) + s["combined_value"]
        rows = [
            {
                "label": label, "value": round(value, 2),
                "pct_of_portfolio": round(value / total_portfolio, 4) if total_portfolio else 0,
                "pct_of_named": round(value / named_total, 4) if named_total else 0,
            }
            for label, value in sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)
        ]
        for label, value in (("Unclassified", unclassified), ("Conflicting", conflicting)):
            if value:
                rows.append({
                    "label": label, "value": round(value, 2),
                    "pct_of_portfolio": round(value / total_portfolio, 4) if total_portfolio else 0,
                    "pct_of_named": None,
                })
        return rows

    issuer_groups = {}
    for s in securities:
        # Direct-only holdings (no fund match) carry no issuer info at all
        # — fall back to security_name so each still gets its own bucket
        # instead of colliding together under one blank "issuer" key.
        key = s["issuer_number"] or s["issuer_name"] or s["security_name"]
        g = issuer_groups.setdefault(key, {
            "issuer_name": s["issuer_name"] or s["security_name"], "issuer_number": s["issuer_number"],
            "combined_value": 0.0, "instrument_types": set(), "type_breakdown": {}, "fund_ids": set(),
        })
        g["combined_value"] += s["combined_value"]
        # instrument_type is None for a direct-only holding with no fund
        # match — that's not a "type" to cross-reference against, skip it.
        if s["instrument_type"]:
            g["instrument_types"].add(s["instrument_type"])
            g["type_breakdown"][s["instrument_type"]] = (
                g["type_breakdown"].get(s["instrument_type"], 0.0) + s["combined_value"]
            )
        g["fund_ids"].update(s["by_fund"].keys())
    same_issuer_cross_type = sorted(
        (
            {
                "issuer_name": g["issuer_name"], "issuer_number": g["issuer_number"],
                "combined_value": round(g["combined_value"], 2),
                "instrument_types": sorted(g["instrument_types"]),
                "type_breakdown": {k: round(v, 2) for k, v in g["type_breakdown"].items()},
                "fund_count": len(g["fund_ids"]),
            }
            for g in issuer_groups.values() if len(g["instrument_types"]) > 1
        ),
        key=lambda g: g["combined_value"], reverse=True,
    )

    return {
        "by_sector": rollup("sector"),
        "by_country": rollup("country"),
        "by_currency": rollup("currency"),
        "same_issuer_cross_type": same_issuer_cross_type,
        "total_portfolio": round(total_portfolio, 2),
    }


def get_direct_fund_overlap(db_path=None):
    """The "what do I hold directly, and does it also show up inside my
    funds" breakdown — anchored on each individual direct stock_holding
    (not every security overall; that's what get_all_securities covers).
    For every direct holding: its own value, the matching fund-derived
    value for the same ISIN (0, not omitted, when there's no fund-side
    match — a real "no overlap" answer), and which fund(s) contribute that
    fund-side amount. Matched strictly on security_number == isin (both
    non-blank) — no name-based fallback. A direct holding with no ISIN
    can't be matched at all and is reported separately in `unmatched_direct`.

    Two holdings can legitimately share an ISIN (e.g. an RSU grant and a
    separate ESPP purchase of the same company) — each still gets its own
    row here, so the same fund-side amount can appear twice; that's
    intentional (each row explains one direct position's own context), not
    a double-count to be summed down the indirect_value column."""
    indirect_result = get_security_holdings(db_path)
    indirect = indirect_result["securities"]
    by_isin = {s["security_number"]: s for s in indirect if s["security_number"]}
    direct = get_stock_holdings(db_path)

    breakdown = []
    unmatched_direct = []
    for h in direct:
        direct_value = h["latest_net_value"] if h["latest_net_value"] is not None else (h["latest_total_value"] or 0)
        if not h["isin"]:
            unmatched_direct.append({
                "holding_id": h["id"], "symbol": h["symbol"], "value": round(direct_value, 2),
            })
            continue
        match = by_isin.get(h["isin"])
        breakdown.append({
            "holding_id": h["id"], "symbol": h["symbol"], "isin": h["isin"],
            "direct_value": round(direct_value, 2),
            "indirect_value": round(match["combined_value"], 2) if match else 0.0,
            "by_fund": match["by_fund"] if match else {},
        })
    breakdown.sort(key=lambda e: e["direct_value"] + e["indirect_value"], reverse=True)
    return {
        "breakdown": breakdown, "unmatched_direct": unmatched_direct,
        "active_funds": indirect_result["active_funds"],
    }


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

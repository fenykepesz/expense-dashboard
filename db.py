import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "expenses.db"

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
    imported_at TEXT    NOT NULL DEFAULT ''
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
        # Add imported_at to existing DBs that predate this column
        try:
            conn.execute("ALTER TABLE transactions ADD COLUMN imported_at TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Column already exists


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
            "SELECT id, date, merchant, amount, category, month, year, card "
            "FROM transactions ORDER BY date DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def delete_transaction(transaction_id, db_path=None):
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))


def get_merchants(db_path=None):
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT merchant, category, COUNT(*) as count "
            "FROM transactions "
            "GROUP BY merchant "
            "ORDER BY count DESC"
        ).fetchall()
    return [dict(row) for row in rows]


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

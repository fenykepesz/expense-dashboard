import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "expenses.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    date     TEXT    NOT NULL,
    merchant TEXT    NOT NULL,
    amount   REAL    NOT NULL,
    category TEXT    NOT NULL,
    month    TEXT    NOT NULL,
    year     INTEGER NOT NULL,
    card     TEXT    NOT NULL
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


def insert_transactions(expenses, db_path=None):
    rows = [
        (e["date"], e["merchant"], e["amount"], e["category"], e["month"], e["year"], e["card"])
        for e in expenses
    ]
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO transactions (date, merchant, amount, category, month, year, card) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
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

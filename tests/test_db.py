import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import db

SAMPLE = [
    {"date": "2024-01-15", "merchant": "Coffee Shop", "amount": 45.50,
     "category": "Food & Dining", "month": "January", "year": 2024, "card": "1234"},
    {"date": "2024-02-10", "merchant": "Supermarket", "amount": 320.00,
     "category": "Groceries", "month": "February", "year": 2024, "card": "5678"},
    {"date": "2023-11-05", "merchant": "Gas Station", "amount": 180.00,
     "category": "Transportation", "month": "November", "year": 2023, "card": "1234"},
]


@pytest.fixture
def tmp_db(tmp_path):
    path = tmp_path / "test.db"
    db.init_db(path)
    return path


def test_init_db_creates_table(tmp_db):
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'"
    ).fetchone()
    conn.close()
    assert tables is not None


def test_empty_db_returns_empty_list(tmp_db):
    assert db.get_all_transactions(tmp_db) == []


def test_insert_and_retrieve(tmp_db):
    db.insert_transactions(SAMPLE, tmp_db)
    rows = db.get_all_transactions(tmp_db)
    assert len(rows) == 3


def test_retrieved_rows_have_all_fields(tmp_db):
    db.insert_transactions(SAMPLE[:1], tmp_db)
    row = db.get_all_transactions(tmp_db)[0]
    for field in ("id", "date", "merchant", "amount", "category", "month", "year", "card"):
        assert field in row


def test_insert_preserves_values(tmp_db):
    db.insert_transactions(SAMPLE[:1], tmp_db)
    row = db.get_all_transactions(tmp_db)[0]
    assert row["merchant"] == "Coffee Shop"
    assert row["amount"] == 45.50
    assert row["card"] == "1234"


def test_multiple_inserts_append(tmp_db):
    db.insert_transactions(SAMPLE[:1], tmp_db)
    db.insert_transactions(SAMPLE[1:], tmp_db)
    assert len(db.get_all_transactions(tmp_db)) == 3


def test_delete_transaction(tmp_db):
    db.insert_transactions(SAMPLE, tmp_db)
    rows = db.get_all_transactions(tmp_db)
    target_id = rows[0]["id"]
    db.delete_transaction(target_id, tmp_db)
    remaining = db.get_all_transactions(tmp_db)
    assert len(remaining) == 2
    assert all(r["id"] != target_id for r in remaining)


def test_results_ordered_by_date_desc(tmp_db):
    db.insert_transactions(SAMPLE, tmp_db)
    rows = db.get_all_transactions(tmp_db)
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates, reverse=True)

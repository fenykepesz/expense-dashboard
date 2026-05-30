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


def test_imported_at_is_set(tmp_db):
    db.insert_transactions(SAMPLE[:1], tmp_db)
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT imported_at FROM transactions").fetchone()
    conn.close()
    assert row[0] and row[0] != ''


def test_imported_at_custom_value(tmp_db):
    db.insert_transactions(SAMPLE[:1], tmp_db, imported_at="migrated")
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT imported_at FROM transactions").fetchone()
    conn.close()
    assert row[0] == "migrated"


def test_get_merchants_groups_correctly(tmp_db):
    db.insert_transactions(SAMPLE, tmp_db)
    merchants = db.get_merchants(tmp_db)
    assert len(merchants) == 3
    names = {m["merchant"] for m in merchants}
    assert "Coffee Shop" in names
    assert all("count" in m for m in merchants)


def test_get_merchants_ordered_by_count(tmp_db):
    # Insert Coffee Shop twice, others once
    db.insert_transactions(SAMPLE, tmp_db)
    db.insert_transactions(SAMPLE[:1], tmp_db)  # extra Coffee Shop
    merchants = db.get_merchants(tmp_db)
    assert merchants[0]["merchant"] == "Coffee Shop"
    assert merchants[0]["count"] == 2


def test_update_merchant_category(tmp_db):
    db.insert_transactions(SAMPLE, tmp_db)
    db.update_merchant_category("Coffee Shop", "Entertainment", tmp_db)
    rows = db.get_all_transactions(tmp_db)
    coffee = [r for r in rows if r["merchant"] == "Coffee Shop"]
    assert all(r["category"] == "Entertainment" for r in coffee)


def test_check_duplicates_exact_match(tmp_db):
    db.insert_transactions(SAMPLE[:1], tmp_db)
    count = db.check_duplicates(SAMPLE[:1], tmp_db)
    assert count == 1


def test_check_duplicates_no_match(tmp_db):
    db.insert_transactions(SAMPLE[:1], tmp_db)
    different = [{"date": "2025-06-01", "merchant": "New Shop", "amount": 99.0, "card": "9999"}]
    assert db.check_duplicates(different, tmp_db) == 0


def test_check_duplicates_partial(tmp_db):
    db.insert_transactions(SAMPLE, tmp_db)
    # First two match, last is new
    new_txn = [{"date": "2025-01-01", "merchant": "Brand New", "amount": 1.0, "card": "0000"}]
    assert db.check_duplicates(SAMPLE[:2] + new_txn, tmp_db) == 2


# ── Category tests ────────────────────────────────────────────────────────────

def test_init_db_seeds_builtin_categories(tmp_db):
    cats = db.get_categories(tmp_db)
    names = [c["name"] for c in cats]
    # All builtins must be present; extra custom ones from migration are fine
    for builtin in db.BUILTIN_CATEGORIES:
        assert builtin in names


def test_get_categories_excludes_deleted(tmp_db):
    db.delete_category("Photography", tmp_db)
    names = [c["name"] for c in db.get_categories(tmp_db)]
    assert "Photography" not in names


def test_add_custom_category(tmp_db):
    db.add_category("Pet Care", tmp_db)
    names = [c["name"] for c in db.get_categories(tmp_db)]
    assert "Pet Care" in names


def test_add_category_returns_sorted_list(tmp_db):
    result = db.add_category("Zzz Last", tmp_db)
    assert result == sorted(result)


def test_delete_builtin_soft_deletes(tmp_db):
    db.delete_category("Photography", tmp_db)
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT is_deleted FROM categories WHERE name = 'Photography'"
    ).fetchone()
    conn.close()
    assert row[0] == 1


def test_delete_custom_hard_deletes(tmp_db):
    db.add_category("Temp Cat", tmp_db)
    db.delete_category("Temp Cat", tmp_db)
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT * FROM categories WHERE name = 'Temp Cat'"
    ).fetchone()
    conn.close()
    assert row is None


def test_delete_uncategorized_raises(tmp_db):
    with pytest.raises(ValueError):
        db.delete_category("Uncategorized", tmp_db)


def test_restore_deleted_builtin(tmp_db):
    db.delete_category("Photography", tmp_db)
    db.add_category("Photography", tmp_db)
    names = [c["name"] for c in db.get_categories(tmp_db)]
    assert "Photography" in names


def test_get_categories_is_builtin_flag(tmp_db):
    db.add_category("Custom One", tmp_db)
    cats = {c["name"]: c["is_builtin"] for c in db.get_categories(tmp_db)}
    assert cats["Groceries"] == 1
    assert cats["Custom One"] == 0


# ── Settings tests ────────────────────────────────────────────────────────────

def test_set_and_get_setting(tmp_db):
    db.set_setting("test_key", "hello", tmp_db)
    assert db.get_setting("test_key", tmp_db) == "hello"


def test_get_missing_setting_returns_none(tmp_db):
    assert db.get_setting("nonexistent", tmp_db) is None


def test_set_setting_overwrites(tmp_db):
    db.set_setting("k", "v1", tmp_db)
    db.set_setting("k", "v2", tmp_db)
    assert db.get_setting("k", tmp_db) == "v2"

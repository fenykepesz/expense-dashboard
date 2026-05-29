import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import db
import app as flask_app

SAMPLE = [
    {"date": "2024-01-15", "merchant": "Coffee Shop", "amount": 45.50,
     "category": "Food & Dining", "month": "January", "year": 2024, "card": "1234"},
    {"date": "2024-02-10", "merchant": "Supermarket", "amount": 320.00,
     "category": "Groceries", "month": "February", "year": 2024, "card": "5678"},
]

REQUIRED_FIELDS = {"id", "date", "merchant", "amount", "category", "month", "year", "card"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db(test_db)
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


@pytest.fixture
def client_with_data(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db(test_db)
    db.insert_transactions(SAMPLE, test_db)
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


def test_get_transactions_returns_200(client_with_data):
    resp = client_with_data.get("/api/transactions")
    assert resp.status_code == 200


def test_get_transactions_returns_list(client_with_data):
    resp = client_with_data.get("/api/transactions")
    data = resp.get_json()
    assert isinstance(data, list)


def test_get_transactions_count(client_with_data):
    resp = client_with_data.get("/api/transactions")
    assert len(resp.get_json()) == 2


def test_transaction_schema(client_with_data):
    resp = client_with_data.get("/api/transactions")
    for row in resp.get_json():
        assert REQUIRED_FIELDS.issubset(row.keys())


def test_get_transactions_empty_db(client):
    resp = client.get("/api/transactions")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_delete_transaction(client_with_data):
    rows = client_with_data.get("/api/transactions").get_json()
    target_id = rows[0]["id"]
    resp = client_with_data.delete(f"/api/transactions/{target_id}")
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == target_id
    remaining = client_with_data.get("/api/transactions").get_json()
    assert len(remaining) == 1
    assert all(r["id"] != target_id for r in remaining)


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<!DOCTYPE html>" in resp.data or b"<html" in resp.data

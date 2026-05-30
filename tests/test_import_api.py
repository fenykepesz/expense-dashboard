import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import db
import app as flask_app

SAMPLE = [
    {"date": "2024-01-15", "merchant": "Coffee Shop", "amount": 45.50,
     "category": "Food & Dining", "month": "January", "year": 2024, "card": "1234"},
    {"date": "2024-02-10", "merchant": "Supermarket", "amount": 320.00,
     "category": "Groceries", "month": "February", "year": 2024, "card": "5678"},
]


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


# ---- /api/import/confirm ----

def test_import_confirm_inserts_transactions(client):
    resp = client.post('/api/import/confirm',
                       data=json.dumps({'transactions': SAMPLE}),
                       content_type='application/json')
    assert resp.status_code == 201
    assert resp.get_json()['inserted'] == 2


def test_import_confirm_empty_body_returns_400(client):
    resp = client.post('/api/import/confirm',
                       data=json.dumps({}),
                       content_type='application/json')
    assert resp.status_code == 400


def test_import_confirm_data_in_db(client):
    client.post('/api/import/confirm',
                data=json.dumps({'transactions': SAMPLE}),
                content_type='application/json')
    rows = client.get('/api/transactions').get_json()
    assert len(rows) == 2


# ---- duplicate detection ----

def test_check_duplicates_via_db(client_with_data, tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db(test_db)
    db.insert_transactions(SAMPLE, test_db)
    count = db.check_duplicates(SAMPLE, test_db)
    assert count == 2


def test_no_duplicates_on_fresh_db(client):
    test_db = flask_app.db.DB_PATH
    count = db.check_duplicates(SAMPLE, test_db)
    assert count == 0


# ---- /api/import with bad file type ----

def test_import_unsupported_file_type(client):
    data = {'file': (io.BytesIO(b'hello'), 'data.csv')}
    resp = client.post('/api/import', data=data, content_type='multipart/form-data')
    assert resp.status_code == 400


def test_import_no_file_returns_400(client):
    resp = client.post('/api/import', data={}, content_type='multipart/form-data')
    assert resp.status_code == 400


# ---- /api/merchants ----

def test_get_merchants_returns_list(client_with_data):
    resp = client_with_data.get('/api/merchants')
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


def test_get_merchants_has_required_fields(client_with_data):
    merchants = client_with_data.get('/api/merchants').get_json()
    for m in merchants:
        assert 'merchant' in m and 'category' in m and 'count' in m


def test_update_merchant_category(client_with_data):
    resp = client_with_data.put('/api/merchants',
                                data=json.dumps({'merchant': 'Coffee Shop',
                                                 'new_category': 'Entertainment',
                                                 'save_rule': False}),
                                content_type='application/json')
    assert resp.status_code == 200
    assert resp.get_json()['category'] == 'Entertainment'


def test_update_merchant_missing_fields_returns_400(client):
    resp = client.put('/api/merchants',
                      data=json.dumps({'merchant': 'Someone'}),
                      content_type='application/json')
    assert resp.status_code == 400


# ---- /api/categories ----

def test_get_categories_returns_list(client):
    resp = client.get('/api/categories')
    assert resp.status_code == 200
    cats = resp.get_json()
    assert isinstance(cats, list)
    assert len(cats) > 0

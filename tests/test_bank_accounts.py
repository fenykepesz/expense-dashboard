import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import db
import app as flask_app


@pytest.fixture
def tmp_db(tmp_path):
    path = tmp_path / "test.db"
    db.init_db(path)
    return path


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db(test_db)
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


# ── DB-level: bank accounts ──────────────────────────────────────────────────

def test_get_bank_accounts_empty_by_default(tmp_db):
    assert db.get_bank_accounts(tmp_db) == []


def test_add_bank_account(tmp_db):
    accounts = db.add_bank_account("Checking", db_path=tmp_db)
    names = [a["name"] for a in accounts]
    assert "Checking" in names


def test_add_bank_account_with_owner_and_number(tmp_db):
    members = db.add_household_member("Dad", tmp_db)
    owner_id = members[0]["id"]
    accounts = db.add_bank_account("Checking", owner_id=owner_id, account_number="688-23692/92", db_path=tmp_db)
    assert accounts[0]["owner_id"] == owner_id
    assert accounts[0]["owner_name"] == "Dad"
    assert accounts[0]["account_number"] == "688-23692/92"


def test_delete_bank_account_soft_deletes(tmp_db):
    accounts = db.add_bank_account("Temp Account", db_path=tmp_db)
    account_id = accounts[0]["id"]
    db.delete_bank_account(account_id, tmp_db)
    names = [a["name"] for a in db.get_bank_accounts(tmp_db)]
    assert "Temp Account" not in names


def test_delete_nonexistent_bank_account_raises(tmp_db):
    with pytest.raises(ValueError):
        db.delete_bank_account(9999, tmp_db)


def test_add_bank_account_excluded_from_net_worth_defaults_false(tmp_db):
    accounts = db.add_bank_account("Checking", db_path=tmp_db)
    assert accounts[0]["excluded_from_net_worth"] == 0


def test_toggle_bank_account_excluded_from_net_worth(tmp_db):
    accounts = db.add_bank_account("Checking", db_path=tmp_db)
    account_id = accounts[0]["id"]
    updated = db.set_bank_account_excluded_from_net_worth(account_id, True, tmp_db)
    assert updated[0]["excluded_from_net_worth"] == 1
    # Still appears in get_bank_accounts — exclusion only affects net worth
    restored = db.set_bank_account_excluded_from_net_worth(account_id, False, tmp_db)
    assert restored[0]["excluded_from_net_worth"] == 0


def test_set_excluded_from_net_worth_nonexistent_account_raises(tmp_db):
    with pytest.raises(ValueError):
        db.set_bank_account_excluded_from_net_worth(9999, True, tmp_db)


def test_household_member_delete_blocked_when_owns_bank_account(tmp_db):
    members = db.add_household_member("Mom", tmp_db)
    owner_id = members[0]["id"]
    db.add_bank_account("Mom's Checking", owner_id=owner_id, db_path=tmp_db)
    with pytest.raises(ValueError):
        db.delete_household_member(owner_id, tmp_db)


# ── DB-level: bank transactions ──────────────────────────────────────────────

def test_insert_bank_transaction_expense(tmp_db):
    account_id = db.add_bank_account("Checking", db_path=tmp_db)[0]["id"]
    count = db.insert_bank_transactions(
        [{"date": "2026-01-15", "description": "Groceries", "amount": -150.0, "type": "expense"}],
        account_id, tmp_db,
    )
    assert count == 1
    rows = db.get_bank_transactions(account_id, tmp_db)
    assert rows[0]["amount"] == -150.0
    assert rows[0]["type"] == "expense"
    assert rows[0]["month"] == "January"
    assert rows[0]["year"] == 2026


def test_insert_bank_transaction_income(tmp_db):
    account_id = db.add_bank_account("Checking", db_path=tmp_db)[0]["id"]
    db.insert_bank_transactions(
        [{"date": "2026-01-01", "description": "Salary", "amount": 15000.0, "type": "income"}],
        account_id, tmp_db,
    )
    rows = db.get_bank_transactions(account_id, tmp_db)
    assert rows[0]["amount"] == 15000.0
    assert rows[0]["type"] == "income"


def test_insert_bank_transaction_optional_fields_default(tmp_db):
    account_id = db.add_bank_account("Checking", db_path=tmp_db)[0]["id"]
    db.insert_bank_transactions(
        [{"date": "2026-01-01", "description": "Misc", "amount": -10.0, "type": "expense"}],
        account_id, tmp_db,
    )
    rows = db.get_bank_transactions(account_id, tmp_db)
    assert rows[0]["category"] == "Uncategorized"
    assert rows[0]["reference"] == ""
    assert rows[0]["balance_after"] is None
    assert rows[0]["excluded"] == 0
    assert rows[0]["notes"] == ""


def test_get_bank_transactions_filtered_by_account(tmp_db):
    db.add_bank_account("Checking", db_path=tmp_db)
    accounts = db.add_bank_account("Savings", db_path=tmp_db)
    a1 = next(a["id"] for a in accounts if a["name"] == "Checking")
    a2 = next(a["id"] for a in accounts if a["name"] == "Savings")
    db.insert_bank_transactions([{"date": "2026-01-01", "description": "X", "amount": -1, "type": "expense"}], a1, tmp_db)
    db.insert_bank_transactions([{"date": "2026-01-01", "description": "Y", "amount": -2, "type": "expense"}], a2, tmp_db)
    assert len(db.get_bank_transactions(a1, tmp_db)) == 1
    assert len(db.get_bank_transactions(a2, tmp_db)) == 1
    assert len(db.get_bank_transactions(db_path=tmp_db)) == 2


def test_set_bank_transaction_excluded(tmp_db):
    account_id = db.add_bank_account("Checking", db_path=tmp_db)[0]["id"]
    db.insert_bank_transactions([{"date": "2026-01-01", "description": "X", "amount": -1, "type": "expense"}], account_id, tmp_db)
    txn_id = db.get_bank_transactions(account_id, tmp_db)[0]["id"]
    db.set_bank_transaction_excluded(txn_id, True, tmp_db)
    assert db.get_bank_transactions(account_id, tmp_db)[0]["excluded"] == 1


def test_set_bank_transaction_note(tmp_db):
    account_id = db.add_bank_account("Checking", db_path=tmp_db)[0]["id"]
    db.insert_bank_transactions([{"date": "2026-01-01", "description": "X", "amount": -1, "type": "expense"}], account_id, tmp_db)
    txn_id = db.get_bank_transactions(account_id, tmp_db)[0]["id"]
    db.set_bank_transaction_note(txn_id, "  some note  ", tmp_db)
    assert db.get_bank_transactions(account_id, tmp_db)[0]["notes"] == "some note"


def test_delete_bank_transaction(tmp_db):
    account_id = db.add_bank_account("Checking", db_path=tmp_db)[0]["id"]
    db.insert_bank_transactions([{"date": "2026-01-01", "description": "X", "amount": -1, "type": "expense"}], account_id, tmp_db)
    txn_id = db.get_bank_transactions(account_id, tmp_db)[0]["id"]
    db.delete_bank_transaction(txn_id, tmp_db)
    assert db.get_bank_transactions(account_id, tmp_db) == []


# ── Route-level ──────────────────────────────────────────────────────────────

def test_get_bank_accounts_route_empty(client):
    resp = client.get("/api/bank-accounts")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_create_bank_account_route(client):
    resp = client.post("/api/bank-accounts", json={"name": "Checking"})
    assert resp.status_code == 201
    names = [a["name"] for a in resp.get_json()["accounts"]]
    assert "Checking" in names


def test_create_bank_account_missing_name_returns_400(client):
    resp = client.post("/api/bank-accounts", json={})
    assert resp.status_code == 400


def test_delete_bank_account_route(client):
    create_resp = client.post("/api/bank-accounts", json={"name": "Checking"})
    account_id = create_resp.get_json()["accounts"][0]["id"]
    resp = client.delete(f"/api/bank-accounts/{account_id}")
    assert resp.status_code == 200
    assert resp.get_json()["accounts"] == []


def test_patch_bank_account_route_toggles_net_worth_exclude(client):
    create_resp = client.post("/api/bank-accounts", json={"name": "Checking"})
    account_id = create_resp.get_json()["accounts"][0]["id"]
    resp = client.patch(f"/api/bank-accounts/{account_id}", json={"excluded_from_net_worth": True})
    assert resp.status_code == 200
    account = next(a for a in resp.get_json()["accounts"] if a["id"] == account_id)
    assert account["excluded_from_net_worth"] == 1


def test_patch_bank_account_route_missing_field_returns_400(client):
    create_resp = client.post("/api/bank-accounts", json={"name": "Checking"})
    account_id = create_resp.get_json()["accounts"][0]["id"]
    resp = client.patch(f"/api/bank-accounts/{account_id}", json={})
    assert resp.status_code == 400


def test_patch_nonexistent_bank_account_route_returns_400(client):
    resp = client.patch("/api/bank-accounts/9999", json={"excluded_from_net_worth": True})
    assert resp.status_code == 400


def test_create_bank_transaction_route_expense_sign(client):
    create_resp = client.post("/api/bank-accounts", json={"name": "Checking"})
    account_id = create_resp.get_json()["accounts"][0]["id"]
    resp = client.post(f"/api/bank-accounts/{account_id}/transactions", json={
        "date": "2026-01-01", "description": "Groceries", "type": "expense", "amount": 150,
    })
    assert resp.status_code == 201
    txns = resp.get_json()["transactions"]
    assert txns[0]["amount"] == -150.0


def test_create_bank_transaction_route_income_sign(client):
    create_resp = client.post("/api/bank-accounts", json={"name": "Checking"})
    account_id = create_resp.get_json()["accounts"][0]["id"]
    resp = client.post(f"/api/bank-accounts/{account_id}/transactions", json={
        "date": "2026-01-01", "description": "Salary", "type": "income", "amount": 15000,
    })
    assert resp.status_code == 201
    txns = resp.get_json()["transactions"]
    assert txns[0]["amount"] == 15000.0


def test_create_bank_transaction_missing_fields_returns_400(client):
    create_resp = client.post("/api/bank-accounts", json={"name": "Checking"})
    account_id = create_resp.get_json()["accounts"][0]["id"]
    resp = client.post(f"/api/bank-accounts/{account_id}/transactions", json={"date": "2026-01-01"})
    assert resp.status_code == 400


def test_create_bank_transaction_invalid_type_returns_400(client):
    create_resp = client.post("/api/bank-accounts", json={"name": "Checking"})
    account_id = create_resp.get_json()["accounts"][0]["id"]
    resp = client.post(f"/api/bank-accounts/{account_id}/transactions", json={
        "date": "2026-01-01", "description": "X", "type": "bogus", "amount": 1,
    })
    assert resp.status_code == 400


def test_get_bank_account_transactions_route(client):
    create_resp = client.post("/api/bank-accounts", json={"name": "Checking"})
    account_id = create_resp.get_json()["accounts"][0]["id"]
    client.post(f"/api/bank-accounts/{account_id}/transactions", json={
        "date": "2026-01-01", "description": "X", "type": "expense", "amount": 1,
    })
    resp = client.get(f"/api/bank-accounts/{account_id}/transactions")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1


def test_patch_bank_transaction_excluded_route(client):
    create_resp = client.post("/api/bank-accounts", json={"name": "Checking"})
    account_id = create_resp.get_json()["accounts"][0]["id"]
    txn_resp = client.post(f"/api/bank-accounts/{account_id}/transactions", json={
        "date": "2026-01-01", "description": "X", "type": "expense", "amount": 1,
    })
    txn_id = txn_resp.get_json()["transactions"][0]["id"]
    resp = client.patch(f"/api/bank-transactions/{txn_id}", json={"excluded": True})
    assert resp.status_code == 200
    rows = client.get(f"/api/bank-accounts/{account_id}/transactions").get_json()
    assert rows[0]["excluded"] == 1


def test_delete_bank_transaction_route(client):
    create_resp = client.post("/api/bank-accounts", json={"name": "Checking"})
    account_id = create_resp.get_json()["accounts"][0]["id"]
    txn_resp = client.post(f"/api/bank-accounts/{account_id}/transactions", json={
        "date": "2026-01-01", "description": "X", "type": "expense", "amount": 1,
    })
    txn_id = txn_resp.get_json()["transactions"][0]["id"]
    resp = client.delete(f"/api/bank-transactions/{txn_id}")
    assert resp.status_code == 200
    rows = client.get(f"/api/bank-accounts/{account_id}/transactions").get_json()
    assert rows == []

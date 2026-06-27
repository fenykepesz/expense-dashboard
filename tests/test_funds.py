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


# ── DB-level: funds ─────────────────────────────────────────────────────────

def test_get_funds_empty_by_default(tmp_db):
    assert db.get_funds(tmp_db) == []


def test_add_fund(tmp_db):
    funds = db.add_fund("Pension Fund", "pension", db_path=tmp_db)
    names = [f["name"] for f in funds]
    assert "Pension Fund" in names


def test_add_fund_invalid_type_raises(tmp_db):
    with pytest.raises(ValueError):
        db.add_fund("Bad Fund", "not_a_real_type", db_path=tmp_db)


def test_add_fund_with_owner(tmp_db):
    members = db.add_household_member("Dad", tmp_db)
    owner_id = members[0]["id"]
    funds = db.add_fund("Study Fund", "study_fund", owner_id=owner_id, db_path=tmp_db)
    assert funds[0]["owner_id"] == owner_id
    assert funds[0]["owner_name"] == "Dad"


def test_add_fund_no_owner(tmp_db):
    funds = db.add_fund("Investment", "investment", db_path=tmp_db)
    assert funds[0]["owner_id"] is None
    assert funds[0]["owner_name"] is None


def test_delete_fund_soft_deletes(tmp_db):
    funds = db.add_fund("Temp Fund", "other", db_path=tmp_db)
    fund_id = funds[0]["id"]
    db.delete_fund(fund_id, tmp_db)
    names = [f["name"] for f in db.get_funds(tmp_db)]
    assert "Temp Fund" not in names


def test_delete_nonexistent_fund_raises(tmp_db):
    with pytest.raises(ValueError):
        db.delete_fund(9999, tmp_db)


def test_household_member_delete_blocked_when_owns_fund(tmp_db):
    members = db.add_household_member("Mom", tmp_db)
    owner_id = members[0]["id"]
    db.add_fund("Mom's Pension", "pension", owner_id=owner_id, db_path=tmp_db)
    with pytest.raises(ValueError):
        db.delete_household_member(owner_id, tmp_db)


def test_household_member_delete_allowed_after_fund_removed(tmp_db):
    members = db.add_household_member("Sam", tmp_db)
    owner_id = members[0]["id"]
    funds = db.add_fund("Sam's Fund", "investment", owner_id=owner_id, db_path=tmp_db)
    db.delete_fund(funds[0]["id"], tmp_db)
    db.delete_household_member(owner_id, tmp_db)  # should not raise
    names = [m["name"] for m in db.get_household_members(tmp_db)]
    assert "Sam" not in names


# ── DB-level: fund balances ─────────────────────────────────────────────────

def test_get_fund_balances_empty_by_default(tmp_db):
    funds = db.add_fund("Fund A", "pension", db_path=tmp_db)
    assert db.get_fund_balances(funds[0]["id"], tmp_db) == []


def test_add_fund_balance(tmp_db):
    funds = db.add_fund("Fund A", "pension", db_path=tmp_db)
    fund_id = funds[0]["id"]
    balances = db.add_fund_balance(fund_id, "2026-01-01", 10000, 500, tmp_db)
    assert len(balances) == 1
    assert balances[0]["balance"] == 10000
    assert balances[0]["contribution"] == 500


def test_add_fund_balance_unknown_fund_raises(tmp_db):
    with pytest.raises(ValueError):
        db.add_fund_balance(9999, "2026-01-01", 1000, db_path=tmp_db)


def test_add_fund_balance_upserts_same_month(tmp_db):
    funds = db.add_fund("Fund A", "pension", db_path=tmp_db)
    fund_id = funds[0]["id"]
    db.add_fund_balance(fund_id, "2026-01-01", 10000, 0, tmp_db)
    balances = db.add_fund_balance(fund_id, "2026-01-01", 10500, 200, tmp_db)
    assert len(balances) == 1
    assert balances[0]["balance"] == 10500
    assert balances[0]["contribution"] == 200


def test_fund_balances_ordered_newest_first(tmp_db):
    funds = db.add_fund("Fund A", "pension", db_path=tmp_db)
    fund_id = funds[0]["id"]
    db.add_fund_balance(fund_id, "2026-01-01", 1000, db_path=tmp_db)
    db.add_fund_balance(fund_id, "2026-03-01", 1200, db_path=tmp_db)
    db.add_fund_balance(fund_id, "2026-02-01", 1100, db_path=tmp_db)
    balances = db.get_fund_balances(fund_id, tmp_db)
    dates = [b["date"] for b in balances]
    assert dates == sorted(dates, reverse=True)


def test_delete_fund_balance(tmp_db):
    funds = db.add_fund("Fund A", "pension", db_path=tmp_db)
    fund_id = funds[0]["id"]
    db.add_fund_balance(fund_id, "2026-01-01", 1000, db_path=tmp_db)
    balances = db.get_fund_balances(fund_id, tmp_db)
    balance_id = balances[0]["id"]
    remaining = db.delete_fund_balance(balance_id, tmp_db)
    assert remaining == []


def test_delete_nonexistent_fund_balance_raises(tmp_db):
    with pytest.raises(ValueError):
        db.delete_fund_balance(9999, tmp_db)


def test_get_all_fund_balances_no_filter(tmp_db):
    db.add_fund("Fund A", "pension", db_path=tmp_db)
    funds = db.add_fund("Fund B", "investment", db_path=tmp_db)
    f1 = next(f["id"] for f in funds if f["name"] == "Fund A")
    f2 = next(f["id"] for f in funds if f["name"] == "Fund B")
    db.add_fund_balance(f1, "2026-01-01", 1000, db_path=tmp_db)
    db.add_fund_balance(f2, "2026-01-01", 2000, db_path=tmp_db)
    assert len(db.get_fund_balances(db_path=tmp_db)) == 2


# ── Route-level ──────────────────────────────────────────────────────────────

def test_get_funds_route_empty(client):
    resp = client.get("/api/funds")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_create_fund_route(client):
    resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension"})
    assert resp.status_code == 201
    names = [f["name"] for f in resp.get_json()["funds"]]
    assert "Pension" in names


def test_create_fund_missing_fields_returns_400(client):
    resp = client.post("/api/funds", json={"name": "Pension"})
    assert resp.status_code == 400


def test_create_fund_invalid_type_returns_400(client):
    resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "bogus"})
    assert resp.status_code == 400


def test_delete_fund_route(client):
    create_resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.delete(f"/api/funds/{fund_id}")
    assert resp.status_code == 200
    assert resp.get_json()["funds"] == []


def test_create_fund_balance_route(client):
    create_resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.post(f"/api/funds/{fund_id}/balances", json={"date": "2026-01-01", "balance": 5000})
    assert resp.status_code == 201
    assert resp.get_json()["balances"][0]["balance"] == 5000


def test_create_fund_balance_missing_fields_returns_400(client):
    create_resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.post(f"/api/funds/{fund_id}/balances", json={"date": "2026-01-01"})
    assert resp.status_code == 400


def test_get_fund_balances_route(client):
    create_resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    client.post(f"/api/funds/{fund_id}/balances", json={"date": "2026-01-01", "balance": 5000})
    resp = client.get(f"/api/funds/{fund_id}/balances")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1


def test_delete_fund_balance_route(client):
    create_resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    bal_resp = client.post(f"/api/funds/{fund_id}/balances", json={"date": "2026-01-01", "balance": 5000})
    balance_id = bal_resp.get_json()["balances"][0]["id"]
    resp = client.delete(f"/api/fund-balances/{balance_id}")
    assert resp.status_code == 200
    assert resp.get_json()["balances"] == []

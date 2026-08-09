import pytest
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import db
import app as flask_app


def test_init_db_migrates_old_funds_table(tmp_path):
    """A fund created under the pre-company_name/fund_number schema must
    survive init_db() being re-run and gain the new columns with defaults."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE funds (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "fund_type TEXT NOT NULL, owner_id INTEGER, is_deleted INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO funds (name, fund_type) VALUES ('Legacy Fund', 'pension')")
    conn.commit()
    conn.close()

    db.init_db(path)  # should not raise, should add the missing columns
    funds = db.get_funds(path)
    assert len(funds) == 1
    assert funds[0]["name"] == "Legacy Fund"
    assert funds[0]["company_name"] == ""
    assert funds[0]["fund_number"] == ""
    assert funds[0]["excluded_from_net_worth"] == 0
    assert funds[0]["is_liquid"] == 0
    assert funds[0]["risk_level"] == 0
    assert funds[0]["risk_note"] == ""


def test_init_db_migrates_old_bank_accounts_table(tmp_path):
    """A bank account created before excluded_from_net_worth existed must
    survive init_db() being re-run and default to not-excluded."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE bank_accounts (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "account_number TEXT NOT NULL DEFAULT '', owner_id INTEGER, "
        "is_deleted INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO bank_accounts (name) VALUES ('Legacy Account')")
    conn.commit()
    conn.close()

    db.init_db(path)
    accounts = db.get_bank_accounts(path)
    assert len(accounts) == 1
    assert accounts[0]["name"] == "Legacy Account"
    assert accounts[0]["excluded_from_net_worth"] == 0
    assert accounts[0]["risk_level"] == 0
    assert accounts[0]["risk_note"] == ""


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


def test_add_fund_provident_fund_type(tmp_db):
    funds = db.add_fund("Kupat Gemel", "provident_fund", company_name="Menora", db_path=tmp_db)
    assert funds[0]["fund_type"] == "provident_fund"


def test_add_fund_money_market_fund_type(tmp_db):
    funds = db.add_fund("Keren Kaspit", "money_market_fund", company_name="Harel", db_path=tmp_db)
    assert funds[0]["fund_type"] == "money_market_fund"


def test_add_fund_savings_policy_type(tmp_db):
    funds = db.add_fund("Polisat Chisachon", "savings_policy", company_name="Clal", db_path=tmp_db)
    assert funds[0]["fund_type"] == "savings_policy"


def test_add_fund_investment_provident_fund_type(tmp_db):
    funds = db.add_fund("Gemel Lehaskaa", "investment_provident_fund", company_name="Meitav", db_path=tmp_db)
    assert funds[0]["fund_type"] == "investment_provident_fund"


def test_add_fund_real_estate_type(tmp_db):
    funds = db.add_fund("Primary Residence", "real_estate", company_name="N/A", is_liquid=False, db_path=tmp_db)
    assert funds[0]["fund_type"] == "real_estate"
    assert funds[0]["is_liquid"] == 0


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


def test_add_fund_with_company_and_number(tmp_db):
    funds = db.add_fund("Pension Fund", "pension", company_name="Harel", fund_number="12345", db_path=tmp_db)
    assert funds[0]["company_name"] == "Harel"
    assert funds[0]["fund_number"] == "12345"


def test_add_fund_company_and_number_default_empty(tmp_db):
    funds = db.add_fund("Pension Fund", "pension", db_path=tmp_db)
    assert funds[0]["company_name"] == ""
    assert funds[0]["fund_number"] == ""


def test_update_fund_renames(tmp_db):
    funds = db.add_fund("Old Name", "pension", company_name="Harel", db_path=tmp_db)
    fund_id = funds[0]["id"]
    updated = db.update_fund(fund_id, {"name": "New Name"}, db_path=tmp_db)
    assert updated[0]["name"] == "New Name"
    assert updated[0]["company_name"] == "Harel"  # untouched


def test_update_fund_partial_only_changes_given_fields(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel", fund_number="1", db_path=tmp_db)
    fund_id = funds[0]["id"]
    updated = db.update_fund(fund_id, {"fund_number": "2"}, db_path=tmp_db)
    assert updated[0]["fund_number"] == "2"
    assert updated[0]["name"] == "Fund A"
    assert updated[0]["company_name"] == "Harel"
    assert updated[0]["fund_type"] == "pension"


def test_update_fund_invalid_type_raises(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel", db_path=tmp_db)
    fund_id = funds[0]["id"]
    with pytest.raises(ValueError):
        db.update_fund(fund_id, {"fund_type": "not_a_real_type"}, db_path=tmp_db)


def test_update_nonexistent_fund_raises(tmp_db):
    with pytest.raises(ValueError):
        db.update_fund(9999, {"name": "X"}, db_path=tmp_db)


def test_update_fund_empty_fields_is_noop(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel", db_path=tmp_db)
    fund_id = funds[0]["id"]
    updated = db.update_fund(fund_id, {}, db_path=tmp_db)
    assert updated[0]["name"] == "Fund A"


def test_add_fund_excluded_from_net_worth_defaults_false(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel", db_path=tmp_db)
    assert funds[0]["excluded_from_net_worth"] == 0


def test_add_fund_is_liquid(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel", is_liquid=True, db_path=tmp_db)
    assert funds[0]["is_liquid"] == 1


def test_add_fund_is_liquid_defaults_false(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel", db_path=tmp_db)
    assert funds[0]["is_liquid"] == 0


def test_update_fund_is_liquid(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel", db_path=tmp_db)
    fund_id = funds[0]["id"]
    updated = db.update_fund(fund_id, {"is_liquid": 1}, db_path=tmp_db)
    assert updated[0]["is_liquid"] == 1
    restored = db.update_fund(fund_id, {"is_liquid": 0}, db_path=tmp_db)
    assert restored[0]["is_liquid"] == 0


def test_toggle_fund_excluded_from_net_worth(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel", db_path=tmp_db)
    fund_id = funds[0]["id"]
    updated = db.update_fund(fund_id, {"excluded_from_net_worth": 1}, db_path=tmp_db)
    assert updated[0]["excluded_from_net_worth"] == 1
    # Fund still appears in get_funds — exclusion only affects net worth, not this listing
    restored = db.update_fund(fund_id, {"excluded_from_net_worth": 0}, db_path=tmp_db)
    assert restored[0]["excluded_from_net_worth"] == 0


def test_add_fund_risk_level_defaults_unrated(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel", db_path=tmp_db)
    assert funds[0]["risk_level"] == 0
    assert funds[0]["risk_note"] == ""


def test_add_fund_with_risk_level_and_note(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel",
                         risk_level=3, risk_note="mixed track", db_path=tmp_db)
    assert funds[0]["risk_level"] == 3
    assert funds[0]["risk_note"] == "mixed track"


def test_add_fund_invalid_risk_level_raises(tmp_db):
    with pytest.raises(ValueError):
        db.add_fund("Fund A", "pension", company_name="Harel", risk_level=6, db_path=tmp_db)


def test_update_fund_risk_level(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel", db_path=tmp_db)
    fund_id = funds[0]["id"]
    updated = db.update_fund(fund_id, {"risk_level": 4, "risk_note": "equity track"}, db_path=tmp_db)
    assert updated[0]["risk_level"] == 4
    assert updated[0]["risk_note"] == "equity track"
    cleared = db.update_fund(fund_id, {"risk_level": 0}, db_path=tmp_db)
    assert cleared[0]["risk_level"] == 0


def test_update_fund_invalid_risk_level_raises(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel", db_path=tmp_db)
    with pytest.raises(ValueError):
        db.update_fund(funds[0]["id"], {"risk_level": 99}, db_path=tmp_db)


def test_get_funds_latest_balance_none_when_no_entries(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel", db_path=tmp_db)
    assert funds[0]["latest_balance"] is None
    assert funds[0]["latest_balance_date"] is None


def test_get_funds_latest_balance_picks_most_recent_date(tmp_db):
    funds = db.add_fund("Fund A", "pension", company_name="Harel", db_path=tmp_db)
    fund_id = funds[0]["id"]
    db.add_fund_balance(fund_id, "2026-01-01", 10000, db_path=tmp_db)
    db.add_fund_balance(fund_id, "2026-03-01", 12000, db_path=tmp_db)
    db.add_fund_balance(fund_id, "2026-02-01", 11000, db_path=tmp_db)
    updated = db.get_funds(tmp_db)
    assert updated[0]["latest_balance"] == 12000
    assert updated[0]["latest_balance_date"] == "2026-03-01"


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
    resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension", "company_name": "Harel"})
    assert resp.status_code == 201
    names = [f["name"] for f in resp.get_json()["funds"]]
    assert "Pension" in names


def test_create_fund_missing_fields_returns_400(client):
    resp = client.post("/api/funds", json={"name": "Pension"})
    assert resp.status_code == 400


def test_create_fund_missing_company_name_returns_400(client):
    resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension"})
    assert resp.status_code == 400


def test_create_fund_invalid_type_returns_400(client):
    resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "bogus", "company_name": "Harel"})
    assert resp.status_code == 400


def test_create_fund_with_company_and_number_route(client):
    resp = client.post("/api/funds", json={
        "name": "Pension", "fund_type": "pension", "company_name": "Harel", "fund_number": "12345",
    })
    assert resp.status_code == 201
    fund = resp.get_json()["funds"][0]
    assert fund["company_name"] == "Harel"
    assert fund["fund_number"] == "12345"


def test_delete_fund_route(client):
    create_resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.delete(f"/api/funds/{fund_id}")
    assert resp.status_code == 200
    assert resp.get_json()["funds"] == []


def test_create_fund_balance_route(client):
    create_resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.post(f"/api/funds/{fund_id}/balances", json={"date": "2026-01-01", "balance": 5000})
    assert resp.status_code == 201
    assert resp.get_json()["balances"][0]["balance"] == 5000


def test_create_fund_balance_missing_fields_returns_400(client):
    create_resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.post(f"/api/funds/{fund_id}/balances", json={"date": "2026-01-01"})
    assert resp.status_code == 400


def test_get_fund_balances_route(client):
    create_resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    client.post(f"/api/funds/{fund_id}/balances", json={"date": "2026-01-01", "balance": 5000})
    resp = client.get(f"/api/funds/{fund_id}/balances")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1


def test_delete_fund_balance_route(client):
    create_resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    bal_resp = client.post(f"/api/funds/{fund_id}/balances", json={"date": "2026-01-01", "balance": 5000})
    balance_id = bal_resp.get_json()["balances"][0]["id"]
    resp = client.delete(f"/api/fund-balances/{balance_id}")
    assert resp.status_code == 200
    assert resp.get_json()["balances"] == []


# ── Route-level: fund editing ────────────────────────────────────────────────

def test_update_fund_route_renames(client):
    create_resp = client.post("/api/funds", json={"name": "Old Name", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.patch(f"/api/funds/{fund_id}", json={"name": "New Name"})
    assert resp.status_code == 200
    fund = next(f for f in resp.get_json()["funds"] if f["id"] == fund_id)
    assert fund["name"] == "New Name"
    assert fund["company_name"] == "Harel"  # untouched fields survive


def test_update_fund_route_all_fields(client):
    members = client.post("/api/household-members", json={"name": "Dad"}).get_json()["members"]
    owner_id = members[0]["id"]
    create_resp = client.post("/api/funds", json={"name": "Fund", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.patch(f"/api/funds/{fund_id}", json={
        "name": "Renamed", "company_name": "Menora", "fund_number": "999",
        "fund_type": "investment", "owner_id": owner_id,
    })
    assert resp.status_code == 200
    fund = next(f for f in resp.get_json()["funds"] if f["id"] == fund_id)
    assert fund["name"] == "Renamed"
    assert fund["company_name"] == "Menora"
    assert fund["fund_number"] == "999"
    assert fund["fund_type"] == "investment"
    assert fund["owner_id"] == owner_id


def test_update_fund_route_blank_name_returns_400(client):
    create_resp = client.post("/api/funds", json={"name": "Fund", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.patch(f"/api/funds/{fund_id}", json={"name": "  "})
    assert resp.status_code == 400


def test_update_fund_route_blank_company_name_returns_400(client):
    create_resp = client.post("/api/funds", json={"name": "Fund", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.patch(f"/api/funds/{fund_id}", json={"company_name": ""})
    assert resp.status_code == 400


def test_update_fund_route_invalid_type_returns_400(client):
    create_resp = client.post("/api/funds", json={"name": "Fund", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.patch(f"/api/funds/{fund_id}", json={"fund_type": "bogus"})
    assert resp.status_code == 400


def test_update_nonexistent_fund_route_returns_400(client):
    resp = client.patch("/api/funds/9999", json={"name": "X"})
    assert resp.status_code == 400


def test_create_fund_route_with_is_liquid(client):
    resp = client.post("/api/funds", json={
        "name": "Cash Fund", "fund_type": "other", "company_name": "Harel", "is_liquid": True,
    })
    assert resp.status_code == 201
    fund = resp.get_json()["funds"][0]
    assert fund["is_liquid"] == 1


def test_patch_fund_route_toggles_is_liquid(client):
    create_resp = client.post("/api/funds", json={"name": "Fund", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.patch(f"/api/funds/{fund_id}", json={"is_liquid": True})
    assert resp.status_code == 200
    fund = next(f for f in resp.get_json()["funds"] if f["id"] == fund_id)
    assert fund["is_liquid"] == 1


def test_create_fund_route_with_risk_level(client):
    resp = client.post("/api/funds", json={
        "name": "Fund", "fund_type": "pension", "company_name": "Harel",
        "risk_level": 2, "risk_note": "bond-heavy",
    })
    assert resp.status_code == 201
    fund = resp.get_json()["funds"][0]
    assert fund["risk_level"] == 2
    assert fund["risk_note"] == "bond-heavy"


def test_patch_fund_route_updates_risk_level(client):
    create_resp = client.post("/api/funds", json={"name": "Fund", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.patch(f"/api/funds/{fund_id}", json={"risk_level": 5, "risk_note": "crypto"})
    assert resp.status_code == 200
    fund = next(f for f in resp.get_json()["funds"] if f["id"] == fund_id)
    assert fund["risk_level"] == 5
    assert fund["risk_note"] == "crypto"


def test_patch_fund_route_invalid_risk_level_returns_400(client):
    create_resp = client.post("/api/funds", json={"name": "Fund", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.patch(f"/api/funds/{fund_id}", json={"risk_level": -1})
    assert resp.status_code == 400


def test_patch_fund_route_toggles_net_worth_exclude(client):
    create_resp = client.post("/api/funds", json={"name": "Fund", "fund_type": "pension", "company_name": "Harel"})
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.patch(f"/api/funds/{fund_id}", json={"excluded_from_net_worth": True})
    assert resp.status_code == 200
    fund = next(f for f in resp.get_json()["funds"] if f["id"] == fund_id)
    assert fund["excluded_from_net_worth"] == 1


def test_update_fund_route_clears_owner(client):
    members = client.post("/api/household-members", json={"name": "Dad"}).get_json()["members"]
    owner_id = members[0]["id"]
    create_resp = client.post("/api/funds", json={
        "name": "Fund", "fund_type": "pension", "company_name": "Harel", "owner_id": owner_id,
    })
    fund_id = create_resp.get_json()["funds"][0]["id"]
    resp = client.patch(f"/api/funds/{fund_id}", json={"owner_id": None})
    assert resp.status_code == 200
    fund = next(f for f in resp.get_json()["funds"] if f["id"] == fund_id)
    assert fund["owner_id"] is None

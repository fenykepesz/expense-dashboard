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


# ── DB-level: stock holdings ─────────────────────────────────────────────────

def test_get_stock_holdings_empty_by_default(tmp_db):
    assert db.get_stock_holdings(tmp_db) == []


def test_add_stock_holding(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    assert holdings[0]["symbol"] == "AAPL"
    assert holdings[0]["holding_type"] == "stock"
    assert holdings[0]["brokerage_firm"] == ""
    assert holdings[0]["cost_basis"] is None
    assert holdings[0]["excluded_from_net_worth"] == 0


def test_add_stock_holding_invalid_type_raises(tmp_db):
    with pytest.raises(ValueError):
        db.add_stock_holding("AAPL", holding_type="not_a_real_type", db_path=tmp_db)


def test_add_stock_holding_espp_and_rsu_types(tmp_db):
    holdings = db.add_stock_holding("MSFT", holding_type="espp", db_path=tmp_db)
    assert holdings[0]["holding_type"] == "espp"
    holdings = db.add_stock_holding("GOOG", holding_type="rsu", db_path=tmp_db)
    rsu = next(h for h in holdings if h["symbol"] == "GOOG")
    assert rsu["holding_type"] == "rsu"


def test_add_stock_holding_with_brokerage_and_cost_basis(tmp_db):
    holdings = db.add_stock_holding(
        "AAPL", brokerage_firm="Interactive Brokers", cost_basis=145.20, db_path=tmp_db
    )
    assert holdings[0]["brokerage_firm"] == "Interactive Brokers"
    assert holdings[0]["cost_basis"] == 145.20


def test_add_stock_holding_with_owner(tmp_db):
    members = db.add_household_member("Erik", tmp_db)
    owner_id = members[0]["id"]
    holdings = db.add_stock_holding("AAPL", owner_id=owner_id, db_path=tmp_db)
    assert holdings[0]["owner_id"] == owner_id
    assert holdings[0]["owner_name"] == "Erik"


def test_add_stock_holding_no_owner(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    assert holdings[0]["owner_id"] is None
    assert holdings[0]["owner_name"] is None


def test_update_stock_holding_fields(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    holding_id = holdings[0]["id"]
    updated = db.update_stock_holding(
        holding_id, {"symbol": "MSFT", "brokerage_firm": "Fidelity"}, db_path=tmp_db
    )
    assert updated[0]["symbol"] == "MSFT"
    assert updated[0]["brokerage_firm"] == "Fidelity"


def test_update_stock_holding_partial_only_changes_given_fields(tmp_db):
    holdings = db.add_stock_holding("AAPL", brokerage_firm="Fidelity", db_path=tmp_db)
    holding_id = holdings[0]["id"]
    updated = db.update_stock_holding(holding_id, {"symbol": "MSFT"}, db_path=tmp_db)
    assert updated[0]["symbol"] == "MSFT"
    assert updated[0]["brokerage_firm"] == "Fidelity"


def test_update_stock_holding_invalid_type_raises(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    with pytest.raises(ValueError):
        db.update_stock_holding(holdings[0]["id"], {"holding_type": "bogus"}, db_path=tmp_db)


def test_update_nonexistent_stock_holding_raises(tmp_db):
    with pytest.raises(ValueError):
        db.update_stock_holding(9999, {"symbol": "X"}, db_path=tmp_db)


def test_update_stock_holding_empty_fields_is_noop(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    updated = db.update_stock_holding(holdings[0]["id"], {}, db_path=tmp_db)
    assert updated[0]["symbol"] == "AAPL"


def test_update_stock_holding_sets_and_clears_cost_basis(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    holding_id = holdings[0]["id"]
    updated = db.update_stock_holding(holding_id, {"cost_basis": 100.0}, db_path=tmp_db)
    assert updated[0]["cost_basis"] == 100.0
    cleared = db.update_stock_holding(holding_id, {"cost_basis": None}, db_path=tmp_db)
    assert cleared[0]["cost_basis"] is None


def test_toggle_stock_holding_excluded_from_net_worth(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    holding_id = holdings[0]["id"]
    updated = db.update_stock_holding(holding_id, {"excluded_from_net_worth": 1}, db_path=tmp_db)
    assert updated[0]["excluded_from_net_worth"] == 1
    restored = db.update_stock_holding(holding_id, {"excluded_from_net_worth": 0}, db_path=tmp_db)
    assert restored[0]["excluded_from_net_worth"] == 0


def test_delete_stock_holding_soft_deletes(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    holding_id = holdings[0]["id"]
    db.delete_stock_holding(holding_id, tmp_db)
    symbols = [h["symbol"] for h in db.get_stock_holdings(tmp_db)]
    assert "AAPL" not in symbols


def test_delete_nonexistent_stock_holding_raises(tmp_db):
    with pytest.raises(ValueError):
        db.delete_stock_holding(9999, tmp_db)


def test_household_member_delete_blocked_when_owns_stock_holding(tmp_db):
    members = db.add_household_member("Erik", tmp_db)
    owner_id = members[0]["id"]
    db.add_stock_holding("AAPL", owner_id=owner_id, db_path=tmp_db)
    with pytest.raises(ValueError):
        db.delete_household_member(owner_id, tmp_db)


def test_household_member_delete_allowed_after_stock_holding_removed(tmp_db):
    members = db.add_household_member("Erik", tmp_db)
    owner_id = members[0]["id"]
    holdings = db.add_stock_holding("AAPL", owner_id=owner_id, db_path=tmp_db)
    db.delete_stock_holding(holdings[0]["id"], tmp_db)
    db.delete_household_member(owner_id, tmp_db)  # should not raise
    names = [m["name"] for m in db.get_household_members(tmp_db)]
    assert "Erik" not in names


# ── DB-level: latest value + tax computation ─────────────────────────────────

def test_get_stock_holdings_latest_none_when_no_entries(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    assert holdings[0]["latest_quantity"] is None
    assert holdings[0]["latest_total_value"] is None
    assert holdings[0]["latest_net_value"] is None


def test_get_stock_holdings_latest_picks_most_recent_date(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    holding_id = holdings[0]["id"]
    db.add_stock_value(holding_id, "2026-01-01", 10, 100, db_path=tmp_db)
    db.add_stock_value(holding_id, "2026-03-01", 12, 120, db_path=tmp_db)
    db.add_stock_value(holding_id, "2026-02-01", 11, 110, db_path=tmp_db)
    updated = db.get_stock_holdings(tmp_db)
    assert updated[0]["latest_date"] == "2026-03-01"
    assert updated[0]["latest_quantity"] == 12
    assert updated[0]["latest_price"] == 120
    assert updated[0]["latest_total_value"] == 1440


def test_net_value_none_without_cost_basis(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)  # no cost_basis
    holding_id = holdings[0]["id"]
    db.add_stock_value(holding_id, "2026-01-01", 10, 100, db_path=tmp_db)
    updated = db.get_stock_holdings(tmp_db)
    assert updated[0]["latest_total_value"] == 1000
    assert updated[0]["latest_net_value"] is None


def test_net_value_taxes_gain_only(tmp_db):
    holdings = db.add_stock_holding("AAPL", cost_basis=80, db_path=tmp_db)
    holding_id = holdings[0]["id"]
    db.add_stock_value(holding_id, "2026-01-01", 10, 100, db_path=tmp_db)  # total 1000, basis 800
    updated = db.get_stock_holdings(tmp_db)
    assert updated[0]["latest_total_value"] == 1000
    # gain = 1000 - 800 = 200; tax = 25% * 200 = 50; net = 950
    assert updated[0]["latest_net_value"] == 950


def test_net_value_no_tax_when_price_below_cost_basis(tmp_db):
    holdings = db.add_stock_holding("AAPL", cost_basis=150, db_path=tmp_db)
    holding_id = holdings[0]["id"]
    db.add_stock_value(holding_id, "2026-01-01", 10, 100, db_path=tmp_db)  # total 1000, basis 1500
    updated = db.get_stock_holdings(tmp_db)
    # no gain (value is below cost basis) — never taxed above total value
    assert updated[0]["latest_net_value"] == updated[0]["latest_total_value"] == 1000


def test_net_value_zero_cost_basis_is_not_treated_as_unknown(tmp_db):
    """cost_basis=0 is a real, distinct value from None ('not entered') —
    the entire value is gain, not a warning state."""
    holdings = db.add_stock_holding("RSU_CO", cost_basis=0, db_path=tmp_db)
    holding_id = holdings[0]["id"]
    db.add_stock_value(holding_id, "2026-01-01", 10, 100, db_path=tmp_db)
    updated = db.get_stock_holdings(tmp_db)
    assert updated[0]["latest_net_value"] == 750  # 1000 - 25%*1000


# ── DB-level: stock values ────────────────────────────────────────────────────

def test_get_stock_values_empty_by_default(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    assert db.get_stock_values(holdings[0]["id"], tmp_db) == []


def test_add_stock_value(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    holding_id = holdings[0]["id"]
    values = db.add_stock_value(holding_id, "2026-01-01", 10, 150.5, tmp_db)
    assert len(values) == 1
    assert values[0]["quantity"] == 10
    assert values[0]["price_per_unit"] == 150.5


def test_add_stock_value_unknown_holding_raises(tmp_db):
    with pytest.raises(ValueError):
        db.add_stock_value(9999, "2026-01-01", 10, 100, db_path=tmp_db)


def test_add_stock_value_upserts_same_date(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    holding_id = holdings[0]["id"]
    db.add_stock_value(holding_id, "2026-01-01", 10, 100, tmp_db)
    values = db.add_stock_value(holding_id, "2026-01-01", 12, 105, tmp_db)
    assert len(values) == 1
    assert values[0]["quantity"] == 12
    assert values[0]["price_per_unit"] == 105


def test_stock_values_ordered_newest_first(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    holding_id = holdings[0]["id"]
    db.add_stock_value(holding_id, "2026-01-01", 10, 100, db_path=tmp_db)
    db.add_stock_value(holding_id, "2026-03-01", 12, 120, db_path=tmp_db)
    db.add_stock_value(holding_id, "2026-02-01", 11, 110, db_path=tmp_db)
    values = db.get_stock_values(holding_id, tmp_db)
    dates = [v["date"] for v in values]
    assert dates == sorted(dates, reverse=True)


def test_delete_stock_value(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    holding_id = holdings[0]["id"]
    db.add_stock_value(holding_id, "2026-01-01", 10, 100, db_path=tmp_db)
    values = db.get_stock_values(holding_id, tmp_db)
    remaining = db.delete_stock_value(values[0]["id"], tmp_db)
    assert remaining == []


def test_delete_nonexistent_stock_value_raises(tmp_db):
    with pytest.raises(ValueError):
        db.delete_stock_value(9999, tmp_db)


def test_get_all_stock_values_no_filter(tmp_db):
    h1 = db.add_stock_holding("AAPL", db_path=tmp_db)[0]["id"]
    holdings = db.add_stock_holding("MSFT", db_path=tmp_db)
    h2 = next(h["id"] for h in holdings if h["symbol"] == "MSFT")
    db.add_stock_value(h1, "2026-01-01", 10, 100, db_path=tmp_db)
    db.add_stock_value(h2, "2026-01-01", 5, 200, db_path=tmp_db)
    assert len(db.get_stock_values(db_path=tmp_db)) == 2


# ── DB-level: net worth integration ──────────────────────────────────────────

def test_net_worth_series_includes_stock_with_net_value(tmp_db):
    holdings = db.add_stock_holding("AAPL", cost_basis=80, db_path=tmp_db)
    holding_id = holdings[0]["id"]
    db.add_stock_value(holding_id, "2026-01-01", 10, 100, db_path=tmp_db)
    result = db.get_net_worth_series(tmp_db)
    stock_series = next(s for s in result["series"] if s["kind"] == "stock")
    assert stock_series["name"] == "AAPL"
    assert stock_series["balances"][-1] == 950  # net value, not total


def test_net_worth_series_stock_falls_back_to_total_value_without_cost_basis(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)  # no cost_basis
    holding_id = holdings[0]["id"]
    db.add_stock_value(holding_id, "2026-01-01", 10, 100, db_path=tmp_db)
    result = db.get_net_worth_series(tmp_db)
    stock_series = next(s for s in result["series"] if s["kind"] == "stock")
    # never silently drops out of net worth just because cost basis is unknown
    assert stock_series["balances"][-1] == 1000


def test_net_worth_series_excludes_stock_when_flagged(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    holding_id = holdings[0]["id"]
    db.add_stock_value(holding_id, "2026-01-01", 10, 100, db_path=tmp_db)
    db.update_stock_holding(holding_id, {"excluded_from_net_worth": 1}, db_path=tmp_db)
    result = db.get_net_worth_series(tmp_db)
    assert not any(s["kind"] == "stock" for s in result["series"])


# ── Route-level ──────────────────────────────────────────────────────────────

def test_get_stock_holdings_route_empty(client):
    resp = client.get("/api/stock-holdings")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_create_stock_holding_route(client):
    resp = client.post("/api/stock-holdings", json={"symbol": "AAPL"})
    assert resp.status_code == 201
    symbols = [h["symbol"] for h in resp.get_json()["holdings"]]
    assert "AAPL" in symbols


def test_create_stock_holding_missing_symbol_returns_400(client):
    resp = client.post("/api/stock-holdings", json={"brokerage_firm": "Fidelity"})
    assert resp.status_code == 400


def test_create_stock_holding_invalid_type_returns_400(client):
    resp = client.post("/api/stock-holdings", json={"symbol": "AAPL", "holding_type": "bogus"})
    assert resp.status_code == 400


def test_create_stock_holding_symbol_uppercased(client):
    resp = client.post("/api/stock-holdings", json={"symbol": "aapl"})
    assert resp.status_code == 201
    assert resp.get_json()["holdings"][0]["symbol"] == "AAPL"


def test_create_stock_holding_with_cost_basis_route(client):
    resp = client.post("/api/stock-holdings", json={"symbol": "AAPL", "cost_basis": 145.2})
    assert resp.status_code == 201
    assert resp.get_json()["holdings"][0]["cost_basis"] == 145.2


def test_delete_stock_holding_route(client):
    create_resp = client.post("/api/stock-holdings", json={"symbol": "AAPL"})
    holding_id = create_resp.get_json()["holdings"][0]["id"]
    resp = client.delete(f"/api/stock-holdings/{holding_id}")
    assert resp.status_code == 200
    assert resp.get_json()["holdings"] == []


def test_patch_stock_holding_route_updates_fields(client):
    create_resp = client.post("/api/stock-holdings", json={"symbol": "AAPL"})
    holding_id = create_resp.get_json()["holdings"][0]["id"]
    resp = client.patch(f"/api/stock-holdings/{holding_id}", json={
        "brokerage_firm": "Fidelity", "holding_type": "rsu",
    })
    assert resp.status_code == 200
    holding = next(h for h in resp.get_json()["holdings"] if h["id"] == holding_id)
    assert holding["brokerage_firm"] == "Fidelity"
    assert holding["holding_type"] == "rsu"


def test_patch_stock_holding_route_clears_cost_basis(client):
    create_resp = client.post("/api/stock-holdings", json={"symbol": "AAPL", "cost_basis": 100})
    holding_id = create_resp.get_json()["holdings"][0]["id"]
    resp = client.patch(f"/api/stock-holdings/{holding_id}", json={"cost_basis": None})
    assert resp.status_code == 200
    holding = next(h for h in resp.get_json()["holdings"] if h["id"] == holding_id)
    assert holding["cost_basis"] is None


def test_patch_stock_holding_route_invalid_type_returns_400(client):
    create_resp = client.post("/api/stock-holdings", json={"symbol": "AAPL"})
    holding_id = create_resp.get_json()["holdings"][0]["id"]
    resp = client.patch(f"/api/stock-holdings/{holding_id}", json={"holding_type": "bogus"})
    assert resp.status_code == 400


def test_patch_stock_holding_route_blank_symbol_returns_400(client):
    create_resp = client.post("/api/stock-holdings", json={"symbol": "AAPL"})
    holding_id = create_resp.get_json()["holdings"][0]["id"]
    resp = client.patch(f"/api/stock-holdings/{holding_id}", json={"symbol": "  "})
    assert resp.status_code == 400


def test_update_nonexistent_stock_holding_route_returns_400(client):
    resp = client.patch("/api/stock-holdings/9999", json={"symbol": "X"})
    assert resp.status_code == 400


def test_patch_stock_holding_route_toggles_net_worth_exclude(client):
    create_resp = client.post("/api/stock-holdings", json={"symbol": "AAPL"})
    holding_id = create_resp.get_json()["holdings"][0]["id"]
    resp = client.patch(f"/api/stock-holdings/{holding_id}", json={"excluded_from_net_worth": True})
    assert resp.status_code == 200
    holding = next(h for h in resp.get_json()["holdings"] if h["id"] == holding_id)
    assert holding["excluded_from_net_worth"] == 1


def test_create_stock_value_route(client):
    create_resp = client.post("/api/stock-holdings", json={"symbol": "AAPL"})
    holding_id = create_resp.get_json()["holdings"][0]["id"]
    resp = client.post(f"/api/stock-holdings/{holding_id}/values", json={
        "date": "2026-01-01", "quantity": 10, "price_per_unit": 150,
    })
    assert resp.status_code == 201
    assert resp.get_json()["values"][0]["quantity"] == 10


def test_create_stock_value_missing_fields_returns_400(client):
    create_resp = client.post("/api/stock-holdings", json={"symbol": "AAPL"})
    holding_id = create_resp.get_json()["holdings"][0]["id"]
    resp = client.post(f"/api/stock-holdings/{holding_id}/values", json={"date": "2026-01-01"})
    assert resp.status_code == 400


def test_get_stock_values_route(client):
    create_resp = client.post("/api/stock-holdings", json={"symbol": "AAPL"})
    holding_id = create_resp.get_json()["holdings"][0]["id"]
    client.post(f"/api/stock-holdings/{holding_id}/values", json={
        "date": "2026-01-01", "quantity": 10, "price_per_unit": 150,
    })
    resp = client.get(f"/api/stock-holdings/{holding_id}/values")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1


def test_delete_stock_value_route(client):
    create_resp = client.post("/api/stock-holdings", json={"symbol": "AAPL"})
    holding_id = create_resp.get_json()["holdings"][0]["id"]
    val_resp = client.post(f"/api/stock-holdings/{holding_id}/values", json={
        "date": "2026-01-01", "quantity": 10, "price_per_unit": 150,
    })
    value_id = val_resp.get_json()["values"][0]["id"]
    resp = client.delete(f"/api/stock-values/{value_id}")
    assert resp.status_code == 200
    assert resp.get_json()["values"] == []

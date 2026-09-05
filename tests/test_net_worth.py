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


def _add_fund(tmp_db, name="Fund A", fund_type="pension"):
    funds = db.add_fund(name, fund_type, db_path=tmp_db)
    return next(f["id"] for f in funds if f["name"] == name)


def _add_account(tmp_db, name="Checking"):
    accounts = db.add_bank_account(name, db_path=tmp_db)
    return next(a["id"] for a in accounts if a["name"] == name)


# ── _month_range ─────────────────────────────────────────────────────────────

def test_month_range_single_month():
    assert db._month_range("2026-03", "2026-03") == ["2026-03"]


def test_month_range_crosses_year():
    assert db._month_range("2025-11", "2026-02") == [
        "2025-11", "2025-12", "2026-01", "2026-02"
    ]


# ── DB-level ─────────────────────────────────────────────────────────────────

def test_net_worth_empty(tmp_db):
    assert db.get_net_worth_series(tmp_db) == {"months": [], "series": []}


def test_net_worth_no_balances_yet(tmp_db):
    _add_fund(tmp_db)
    _add_account(tmp_db)
    assert db.get_net_worth_series(tmp_db) == {"months": [], "series": []}


def test_fund_balance_carried_forward(tmp_db):
    fund_id = _add_fund(tmp_db)
    db.add_fund_balance(fund_id, "2026-01-15", 1000, db_path=tmp_db)
    db.add_fund_balance(fund_id, "2026-03-15", 1200, db_path=tmp_db)
    result = db.get_net_worth_series(tmp_db)
    assert result["months"] == ["2026-01", "2026-02", "2026-03"]
    fund = result["series"][0]
    assert fund["kind"] == "fund"
    assert fund["balances"] == [1000, 1000, 1200]


def test_fund_last_entry_in_month_wins(tmp_db):
    fund_id = _add_fund(tmp_db)
    db.add_fund_balance(fund_id, "2026-01-05", 900, db_path=tmp_db)
    db.add_fund_balance(fund_id, "2026-01-25", 950, db_path=tmp_db)
    result = db.get_net_worth_series(tmp_db)
    assert result["series"][0]["balances"] == [950]


def test_fund_last_updated_is_its_own_real_entry_date(tmp_db):
    fund_id = _add_fund(tmp_db)
    db.add_fund_balance(fund_id, "2026-01-15", 1000, db_path=tmp_db)
    db.add_fund_balance(fund_id, "2026-03-15", 1200, db_path=tmp_db)
    result = db.get_net_worth_series(tmp_db)
    assert result["series"][0]["last_updated"] == "2026-03-15"


def test_fund_last_updated_can_be_stale_relative_to_the_series_range(tmp_db):
    """A fund with no recent entry still gets carried forward through
    months another item's data extends the series into — but its
    last_updated must keep pointing at its own real entry, not the
    series' shared right edge, so a caller can tell the carried-forward
    figure isn't a fresh confirmation."""
    fund_id = _add_fund(tmp_db, "Stale Fund")
    db.add_fund_balance(fund_id, "2026-01-15", 1000, db_path=tmp_db)
    account_id = db.add_bank_account("Checking", db_path=tmp_db)[0]["id"]
    db.insert_bank_transactions(
        [{"date": "2026-04-01", "description": "Keeps the series going", "amount": 500, "type": "income"}],
        account_id, db_path=tmp_db,
    )
    result = db.get_net_worth_series(tmp_db)
    assert result["months"][-1] == "2026-04"
    fund = next(s for s in result["series"] if s["kind"] == "fund")
    assert fund["last_updated"] == "2026-01-15"
    assert fund["balances"][-1] == 1000  # carried forward into April, not a fresh number


def test_bank_last_updated_uses_imported_at_not_transaction_date(tmp_db):
    account_id = db.add_bank_account("Checking", db_path=tmp_db)[0]["id"]
    db.insert_bank_transactions(
        [{"date": "2026-01-15", "description": "Old transaction", "amount": 100, "type": "income"}],
        account_id, db_path=tmp_db, imported_at="2026-03-01T09:00:00",
    )
    result = db.get_net_worth_series(tmp_db)
    bank = next(s for s in result["series"] if s["kind"] == "bank")
    assert bank["last_updated"] == "2026-03-01"


def test_stock_last_updated_is_its_own_real_entry_date(tmp_db):
    holding_id = db.add_stock_holding("AAPL", db_path=tmp_db)[0]["id"]
    db.add_stock_value(holding_id, "2026-02-10", 10, 100, db_path=tmp_db)
    result = db.get_net_worth_series(tmp_db)
    stock = next(s for s in result["series"] if s["kind"] == "stock")
    assert stock["last_updated"] == "2026-02-10"


def test_fund_null_before_first_entry(tmp_db):
    fund_a = _add_fund(tmp_db, "Fund A")
    fund_b = _add_fund(tmp_db, "Fund B", "investment")
    db.add_fund_balance(fund_a, "2026-01-01", 100, db_path=tmp_db)
    db.add_fund_balance(fund_b, "2026-02-01", 200, db_path=tmp_db)
    result = db.get_net_worth_series(tmp_db)
    by_name = {s["name"]: s for s in result["series"]}
    assert by_name["Fund B"]["balances"] == [None, 200]


def test_bank_cumulative_sum(tmp_db):
    account_id = _add_account(tmp_db)
    db.insert_bank_transactions([
        {"date": "2026-01-10", "description": "Salary", "amount": 5000, "type": "income"},
        {"date": "2026-01-20", "description": "Rent", "amount": -2000, "type": "expense"},
        {"date": "2026-03-10", "description": "Salary", "amount": 5000, "type": "income"},
    ], account_id, tmp_db)
    result = db.get_net_worth_series(tmp_db)
    bank = result["series"][0]
    assert bank["kind"] == "bank"
    # Jan: 5000-2000; Feb: carried; Mar: +5000
    assert bank["balances"] == [3000, 3000, 8000]


def test_bank_balance_after_anchors_running_balance(tmp_db):
    account_id = _add_account(tmp_db)
    db.insert_bank_transactions([
        # Imported row: bank says balance is 10000 after this (captures the
        # opening balance from before the export window)
        {"date": "2026-01-10", "description": "Salary", "amount": 5000,
         "type": "income", "balance_after": 10000.0},
        # Manual row afterwards: adds onto the anchored balance
        {"date": "2026-02-05", "description": "Rent", "amount": -2000, "type": "expense"},
    ], account_id, tmp_db)
    result = db.get_net_worth_series(tmp_db)
    assert result["series"][0]["balances"] == [10000.0, 8000.0]


def test_bank_excluded_transactions_ignored(tmp_db):
    account_id = _add_account(tmp_db)
    db.insert_bank_transactions([
        {"date": "2026-01-10", "description": "Salary", "amount": 5000, "type": "income"},
        {"date": "2026-01-20", "description": "Oops", "amount": -999, "type": "expense"},
    ], account_id, tmp_db)
    txns = db.get_bank_transactions(account_id, tmp_db)
    oops_id = next(t["id"] for t in txns if t["description"] == "Oops")
    db.set_bank_transaction_excluded(oops_id, True, tmp_db)
    result = db.get_net_worth_series(tmp_db)
    assert result["series"][0]["balances"] == [5000]


def test_deleted_items_excluded_from_series(tmp_db):
    fund_id = _add_fund(tmp_db)
    account_id = _add_account(tmp_db)
    db.add_fund_balance(fund_id, "2026-01-01", 100, db_path=tmp_db)
    db.insert_bank_transactions(
        [{"date": "2026-01-10", "description": "x", "amount": 50, "type": "income"}],
        account_id, tmp_db,
    )
    db.delete_fund(fund_id, tmp_db)
    result = db.get_net_worth_series(tmp_db)
    assert [s["kind"] for s in result["series"]] == ["bank"]
    assert result["months"] == ["2026-01"]


def test_fund_excluded_from_net_worth_omitted_from_series(tmp_db):
    fund_id = _add_fund(tmp_db)
    db.add_fund_balance(fund_id, "2026-01-01", 100, db_path=tmp_db)
    db.update_fund(fund_id, {"excluded_from_net_worth": 1}, db_path=tmp_db)
    result = db.get_net_worth_series(tmp_db)
    assert result["series"] == []


def test_bank_account_excluded_from_net_worth_omitted_from_series(tmp_db):
    account_id = _add_account(tmp_db)
    db.insert_bank_transactions(
        [{"date": "2026-01-10", "description": "x", "amount": 50, "type": "income"}],
        account_id, tmp_db,
    )
    db.update_bank_account(account_id, {"excluded_from_net_worth": 1}, tmp_db)
    result = db.get_net_worth_series(tmp_db)
    assert result["series"] == []


def test_excluded_from_net_worth_item_still_appears_in_its_own_listing(tmp_db):
    """Excluding from Net Worth must NOT hide the item from its own tab —
    only the Net Worth series is affected."""
    fund_id = _add_fund(tmp_db)
    account_id = _add_account(tmp_db)
    db.update_fund(fund_id, {"excluded_from_net_worth": 1}, db_path=tmp_db)
    db.update_bank_account(account_id, {"excluded_from_net_worth": 1}, tmp_db)
    assert len(db.get_funds(tmp_db)) == 1
    assert len(db.get_bank_accounts(tmp_db)) == 1


def test_restoring_excluded_fund_reappears_in_series(tmp_db):
    fund_id = _add_fund(tmp_db)
    db.add_fund_balance(fund_id, "2026-01-01", 100, db_path=tmp_db)
    db.update_fund(fund_id, {"excluded_from_net_worth": 1}, db_path=tmp_db)
    assert db.get_net_worth_series(tmp_db)["series"] == []
    db.update_fund(fund_id, {"excluded_from_net_worth": 0}, db_path=tmp_db)
    result = db.get_net_worth_series(tmp_db)
    assert len(result["series"]) == 1
    assert result["series"][0]["balances"] == [100]


def test_combined_months_span_both_sources(tmp_db):
    fund_id = _add_fund(tmp_db)
    account_id = _add_account(tmp_db)
    db.add_fund_balance(fund_id, "2025-11-01", 100, db_path=tmp_db)
    db.insert_bank_transactions(
        [{"date": "2026-02-10", "description": "x", "amount": 50, "type": "income"}],
        account_id, tmp_db,
    )
    result = db.get_net_worth_series(tmp_db)
    assert result["months"] == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_series_metadata_includes_owner_and_type(tmp_db):
    members = db.add_household_member("Dad", tmp_db)
    owner_id = members[0]["id"]
    db.add_fund("Dad's Pension", "pension", owner_id=owner_id, db_path=tmp_db)
    funds = db.get_funds(tmp_db)
    db.add_fund_balance(funds[0]["id"], "2026-01-01", 100, db_path=tmp_db)
    result = db.get_net_worth_series(tmp_db)
    fund = result["series"][0]
    assert fund["owner_name"] == "Dad"
    assert fund["fund_type"] == "pension"
    assert fund["key"] == f"fund-{funds[0]['id']}"


# ── Route-level ──────────────────────────────────────────────────────────────

def test_net_worth_route_empty(client):
    resp = client.get("/api/net-worth")
    assert resp.status_code == 200
    assert resp.get_json() == {"months": [], "series": []}


def test_net_worth_route_with_data(client):
    fund_resp = client.post("/api/funds", json={"name": "Pension", "fund_type": "pension", "company_name": "Harel"})
    fund_id = fund_resp.get_json()["funds"][0]["id"]
    client.post(f"/api/funds/{fund_id}/balances", json={"date": "2026-01-01", "balance": 5000})
    resp = client.get("/api/net-worth")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["months"] == ["2026-01"]
    assert data["series"][0]["balances"] == [5000]

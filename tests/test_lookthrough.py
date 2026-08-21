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


def _make_fund(db_path, fund_type, institution_reg_number, track_number, balance=None, name="Fund"):
    funds = db.add_fund(name, fund_type, company_name="Co", track_number=track_number,
                         institution_reg_number=institution_reg_number, db_path=db_path)
    fund_id = next(f["id"] for f in funds if f["name"] == name)
    if balance is not None:
        db.add_fund_balance(fund_id, "2026-01-01", balance, db_path=db_path)
    return fund_id


def _basic_row(fund_id, **overrides):
    # fair_value_ils (not pct_of_track) drives dollar math — pct_of_track is
    # kept only as an informational field the parser also captures. See
    # get_security_holdings's docstring for why: the filing's own "% of
    # track" column is normalized within each instrument-category sheet,
    # not against the track's total value, so it can't be used for money.
    row = {
        "fund_id": fund_id, "instrument_type": "equity_traded",
        "issuer_name": "Acme Corp", "issuer_number": "999",
        "security_name": "Acme Ord", "security_number": "IL0001",
        "pct_of_track": 0.1, "fair_value_ils": 0,
        "country": "Israel", "sector": "Tech", "currency": "ILS",
    }
    row.update(overrides)
    return row


# ── DB-level: funds' new fields ──────────────────────────────────────────────

def test_add_fund_with_track_fields(tmp_db):
    funds = db.add_fund("Fund A", "pension", track_number="5", institution_reg_number="1", db_path=tmp_db)
    assert funds[0]["track_number"] == "5"
    assert funds[0]["institution_reg_number"] == "1"


def test_add_fund_duplicate_track_key_raises(tmp_db):
    db.add_fund("Fund A", "pension", track_number="5", institution_reg_number="1", db_path=tmp_db)
    with pytest.raises(ValueError):
        db.add_fund("Fund B", "study_fund", track_number="5", institution_reg_number="1", db_path=tmp_db)


def test_update_fund_duplicate_track_key_raises(tmp_db):
    db.add_fund("Fund A", "pension", track_number="5", institution_reg_number="1", db_path=tmp_db)
    funds = db.add_fund("Fund B", "study_fund", track_number="6", institution_reg_number="1", db_path=tmp_db)
    fund_b = next(f["id"] for f in funds if f["name"] == "Fund B")
    with pytest.raises(ValueError):
        db.update_fund(fund_b, {"track_number": "5"}, db_path=tmp_db)


def test_update_fund_same_track_key_on_same_fund_is_a_noop(tmp_db):
    funds = db.add_fund("Fund A", "pension", track_number="5", institution_reg_number="1", db_path=tmp_db)
    fund_id = funds[0]["id"]
    updated = db.update_fund(fund_id, {"track_number": "5", "institution_reg_number": "1"}, db_path=tmp_db)
    assert updated[0]["track_number"] == "5"


def test_partial_track_key_does_not_trigger_uniqueness_check(tmp_db):
    """Only enforced once BOTH institution_reg_number and track_number are set."""
    db.add_fund("Fund A", "pension", track_number="5", db_path=tmp_db)  # no institution set
    updated = db.add_fund("Fund B", "study_fund", track_number="5", db_path=tmp_db)  # should not raise
    assert updated[-1]["track_number"] == "5"


# ── DB-level: stock_holdings.isin ────────────────────────────────────────────

def test_add_stock_holding_with_isin(tmp_db):
    holdings = db.add_stock_holding("AAPL", isin="US0378331005", db_path=tmp_db)
    assert holdings[0]["isin"] == "US0378331005"


def test_update_stock_holding_isin(tmp_db):
    holdings = db.add_stock_holding("AAPL", db_path=tmp_db)
    updated = db.update_stock_holding(holdings[0]["id"], {"isin": "US0378331005"}, db_path=tmp_db)
    assert updated[0]["isin"] == "US0378331005"


# ── DB-level: holdings filings ────────────────────────────────────────────────

def test_get_holdings_filings_empty_by_default(tmp_db):
    assert db.get_holdings_filings(tmp_db) == []


def test_replace_fund_holdings_filing_inserts(tmp_db):
    fund_id = _make_fund(tmp_db, "pension", "1", "5", balance=10000)
    result = db.replace_fund_holdings_filing("1", "Test Co", 2026, 1, [_basic_row(fund_id)], db_path=tmp_db)
    assert result["inserted"] == 1
    filings = db.get_holdings_filings(tmp_db)
    assert len(filings) == 1
    assert filings[0]["institution_name"] == "Test Co"


def test_replace_fund_holdings_filing_reimport_same_period_replaces(tmp_db):
    fund_id = _make_fund(tmp_db, "pension", "1", "5", balance=10000)
    r1 = db.replace_fund_holdings_filing("1", "Test Co", 2026, 1, [_basic_row(fund_id)], db_path=tmp_db)
    r2 = db.replace_fund_holdings_filing(
        "1", "Test Co", 2026, 1,
        [_basic_row(fund_id), _basic_row(fund_id, security_number="IL0002")],
        db_path=tmp_db,
    )
    assert r1["filing_id"] == r2["filing_id"]  # same filing, upserted not duplicated
    assert len(db.get_holdings_filings(tmp_db)) == 1
    securities = db.get_security_holdings(tmp_db)["securities"]
    assert len(securities) == 2  # old row set was replaced, not appended to


def test_replace_fund_holdings_filing_new_period_preserves_history(tmp_db):
    fund_id = _make_fund(tmp_db, "pension", "1", "5", balance=10000)
    db.replace_fund_holdings_filing("1", "Test Co", 2026, 1, [_basic_row(fund_id)], db_path=tmp_db)
    db.replace_fund_holdings_filing("1", "Test Co", 2026, 2, [_basic_row(fund_id)], db_path=tmp_db)
    assert len(db.get_holdings_filings(tmp_db)) == 2


def test_delete_holdings_filing_soft_deletes(tmp_db):
    fund_id = _make_fund(tmp_db, "pension", "1", "5", balance=10000)
    result = db.replace_fund_holdings_filing("1", "Test Co", 2026, 1, [_basic_row(fund_id)], db_path=tmp_db)
    db.delete_holdings_filing(result["filing_id"], tmp_db)
    assert db.get_holdings_filings(tmp_db) == []
    assert db.get_security_holdings(tmp_db)["securities"] == []


def test_delete_nonexistent_holdings_filing_raises(tmp_db):
    with pytest.raises(ValueError):
        db.delete_holdings_filing(9999, tmp_db)


# ── DB-level: get_security_holdings ──────────────────────────────────────────

def test_security_holdings_sums_across_different_fund_types(tmp_db):
    """The core requirement: pension + study_fund combine seamlessly."""
    pension_id = _make_fund(tmp_db, "pension", "1", "5", balance=10000, name="Pension")
    study_id = _make_fund(tmp_db, "study_fund", "1", "6", balance=20000, name="Study")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(pension_id, fair_value_ils=1000),
        _basic_row(study_id, fair_value_ils=1000),
    ], db_path=tmp_db)

    result = db.get_security_holdings(tmp_db)
    assert len(result["securities"]) == 1
    sec = result["securities"][0]
    assert sec["combined_value"] == 2000.0
    assert sec["fund_count"] == 2
    assert {f["fund_type"] for f in result["active_funds"]} == {"pension", "study_fund"}


def test_security_holdings_empty_when_no_filings(tmp_db):
    assert db.get_security_holdings(tmp_db) == {"securities": [], "active_funds": []}


def test_security_holdings_work_without_a_fund_balance(tmp_db):
    """fair_value_ils comes straight from the filing, so a fund with
    holdings rows but no fund_balances entry yet still contributes its full
    value — unlike the old (wrong) fund_balance * pct_of_track formula,
    there's no dependency on fund_balances being populated at all."""
    fund_id = _make_fund(tmp_db, "pension", "1", "5")  # no balance
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_id, fair_value_ils=1000),
    ], db_path=tmp_db)
    securities = db.get_security_holdings(tmp_db)["securities"]
    assert len(securities) == 1
    assert securities[0]["combined_value"] == 1000.0


def test_security_key_falls_back_to_issuer_and_name_without_a_number(tmp_db):
    """Cash/loans/deposits structurally lack a security_number."""
    fund_id = _make_fund(tmp_db, "pension", "1", "5", balance=10000)
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_id, instrument_type="cash", security_name="", security_number="",
                   issuer_name="Bank Leumi", issuer_number="10-800", pct_of_track=0.1),
    ], db_path=tmp_db)
    securities = db.get_security_holdings(tmp_db)["securities"]
    assert len(securities) == 1
    assert securities[0]["security_name"] == "Bank Leumi"  # falls back to issuer_name for display


def test_security_key_falls_back_to_instrument_type_and_issuer_as_last_resort(tmp_db):
    fund_id = _make_fund(tmp_db, "pension", "1", "5", balance=10000)
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_id, instrument_type="other", security_name="", security_number="",
                   issuer_name="", issuer_number="", pct_of_track=0.1),
    ], db_path=tmp_db)
    securities = db.get_security_holdings(tmp_db)["securities"]
    assert len(securities) == 1


def test_classification_conflict_flagged_when_sector_diverges(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=10000, name="A")
    fund_b = _make_fund(tmp_db, "pension", "1", "6", balance=10000, name="B")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, sector="Tech"),
        _basic_row(fund_b, sector="Finance"),
    ], db_path=tmp_db)
    securities = db.get_security_holdings(tmp_db)["securities"]
    assert len(securities) == 1
    assert securities[0]["classification_conflict"] is True
    assert securities[0]["sector"] is None
    assert set(securities[0]["sector_values"]) == {"Tech", "Finance"}


def test_no_conflict_when_sector_agrees(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=10000, name="A")
    fund_b = _make_fund(tmp_db, "pension", "1", "6", balance=10000, name="B")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, sector="Tech"),
        _basic_row(fund_b, sector="Tech"),
    ], db_path=tmp_db)
    securities = db.get_security_holdings(tmp_db)["securities"]
    assert securities[0]["classification_conflict"] is False
    assert securities[0]["sector"] == "Tech"


# ── DB-level: overlap ─────────────────────────────────────────────────────────

def test_overlap_excludes_single_fund_securities(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=10000, name="A")
    fund_b = _make_fund(tmp_db, "pension", "1", "6", balance=10000, name="B")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, security_number="IL0001"),
        _basic_row(fund_b, security_number="IL0001"),
        _basic_row(fund_a, security_number="IL0002"),  # only in fund A
    ], db_path=tmp_db)
    overlap = db.get_overlap_holdings(tmp_db)["securities"]
    assert len(overlap) == 1
    assert overlap[0]["security_number"] == "IL0001"


def test_overlap_max_single_fund_share(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", name="A")
    fund_b = _make_fund(tmp_db, "pension", "1", "6", name="B")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, fair_value_ils=8000),
        _basic_row(fund_b, fair_value_ils=2000),
    ], db_path=tmp_db)
    overlap = db.get_overlap_holdings(tmp_db)["securities"]
    assert overlap[0]["max_single_fund_share"] == pytest.approx(0.8)


# ── DB-level: concentration ───────────────────────────────────────────────────

def test_concentration_dual_denominator(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, security_number="IL0001", sector="Tech", fair_value_ils=5000),
        _basic_row(fund_a, security_number="IL0002", sector="", fair_value_ils=3000),  # unclassified
    ], db_path=tmp_db)
    rollups = db.get_concentration_rollups(tmp_db)
    assert rollups["total_portfolio"] == 8000.0
    tech = next(r for r in rollups["by_sector"] if r["label"] == "Tech")
    assert tech["pct_of_portfolio"] == pytest.approx(5000 / 8000)
    assert tech["pct_of_named"] == pytest.approx(1.0)  # only named sector present
    unclassified = next(r for r in rollups["by_sector"] if r["label"] == "Unclassified")
    assert unclassified["pct_of_portfolio"] == pytest.approx(3000 / 8000)
    assert unclassified["pct_of_named"] is None


def test_concentration_same_issuer_cross_type(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, instrument_type="equity_traded", issuer_number="10-800",
                   issuer_name="Bank Leumi", security_number="IL0001", fair_value_ils=1000),
        _basic_row(fund_a, instrument_type="corp_bond", issuer_number="10-800",
                   issuer_name="Bank Leumi", security_number="IL0099", fair_value_ils=1000),
    ], db_path=tmp_db)
    rollups = db.get_concentration_rollups(tmp_db)
    assert len(rollups["same_issuer_cross_type"]) == 1
    group = rollups["same_issuer_cross_type"][0]
    assert group["issuer_name"] == "Bank Leumi"
    assert set(group["instrument_types"]) == {"equity_traded", "corp_bond"}
    assert group["combined_value"] == 2000.0


def test_concentration_no_same_issuer_group_for_single_instrument_type(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=10000, name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [_basic_row(fund_a)], db_path=tmp_db)
    rollups = db.get_concentration_rollups(tmp_db)
    assert rollups["same_issuer_cross_type"] == []


# ── DB-level: merged direct/indirect ─────────────────────────────────────────

def test_merged_matches_on_isin(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, security_number="US0378331005", fair_value_ils=1000),  # indirect
    ], db_path=tmp_db)
    holding = db.add_stock_holding("AAPL", isin="US0378331005", cost_basis=0, db_path=tmp_db)[0]
    db.add_stock_value(holding["id"], "2026-01-01", 10, 100, db_path=tmp_db)  # 1000 total, net 750

    merged = db.get_merged_direct_indirect(tmp_db)
    assert len(merged["merged"]) == 1
    entry = merged["merged"][0]
    assert entry["indirect_value"] == 1000.0
    assert entry["direct_value"] == 750.0  # net value preferred over total
    assert entry["combined_value"] == 1750.0
    assert merged["unmatched_direct"] == []


def test_merged_direct_holding_without_isin_is_unmatched(tmp_db):
    db.add_stock_holding("AAPL", db_path=tmp_db)  # no isin
    merged = db.get_merged_direct_indirect(tmp_db)
    assert merged["merged"] == []
    assert len(merged["unmatched_direct"]) == 1
    assert merged["unmatched_direct"][0]["symbol"] == "AAPL"


def test_merged_direct_holding_with_isin_but_no_indirect_match_still_shown(tmp_db):
    holding = db.add_stock_holding("MSFT", isin="US5949181045", cost_basis=0, db_path=tmp_db)[0]
    db.add_stock_value(holding["id"], "2026-01-01", 5, 400, db_path=tmp_db)  # 2000 total, net 1500
    merged = db.get_merged_direct_indirect(tmp_db)
    assert len(merged["merged"]) == 1
    assert merged["merged"][0]["indirect_value"] == 0.0
    assert merged["merged"][0]["direct_value"] == 1500.0
    assert merged["unmatched_direct"] == []


# ── DB-level: soft-delete propagation ─────────────────────────────────────────

def test_soft_deleting_fund_removes_it_from_security_holdings(tmp_db):
    fund_id = _make_fund(tmp_db, "pension", "1", "5", balance=10000)
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [_basic_row(fund_id)], db_path=tmp_db)
    assert db.get_security_holdings(tmp_db)["securities"] != []
    db.delete_fund(fund_id, tmp_db)
    assert db.get_security_holdings(tmp_db)["securities"] == []


# ── Route-level ────────────────────────────────────────────────────────────────

def test_create_fund_route_with_track_fields(client):
    resp = client.post("/api/funds", json={
        "name": "Fund", "fund_type": "pension", "company_name": "Co",
        "track_number": "5", "institution_reg_number": "1",
    })
    assert resp.status_code == 201
    fund = resp.get_json()["funds"][0]
    assert fund["track_number"] == "5"
    assert fund["institution_reg_number"] == "1"


def test_create_fund_route_duplicate_track_key_returns_400(client):
    client.post("/api/funds", json={
        "name": "Fund A", "fund_type": "pension", "company_name": "Co",
        "track_number": "5", "institution_reg_number": "1",
    })
    resp = client.post("/api/funds", json={
        "name": "Fund B", "fund_type": "pension", "company_name": "Co",
        "track_number": "5", "institution_reg_number": "1",
    })
    assert resp.status_code == 400


def test_patch_stock_holding_route_isin(client):
    create_resp = client.post("/api/stock-holdings", json={"symbol": "AAPL"})
    holding_id = create_resp.get_json()["holdings"][0]["id"]
    resp = client.patch(f"/api/stock-holdings/{holding_id}", json={"isin": "us0378331005"})
    assert resp.status_code == 200
    holding = next(h for h in resp.get_json()["holdings"] if h["id"] == holding_id)
    assert holding["isin"] == "US0378331005"  # uppercased


def test_lookthrough_import_route_malformed_file_returns_400(client):
    import io
    data = {"file": (io.BytesIO(b"not a real xlsx file"), "bad.xlsx")}
    resp = client.post("/api/lookthrough/import", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_lookthrough_import_route_no_file_returns_400(client):
    resp = client.post("/api/lookthrough/import", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_lookthrough_import_confirm_and_read_back(client):
    client.post("/api/funds", json={
        "name": "Fund", "fund_type": "pension", "company_name": "Co",
        "track_number": "5", "institution_reg_number": "1",
    })
    fund_id = client.get("/api/funds").get_json()[0]["id"]

    confirm_resp = client.post("/api/lookthrough/import/confirm", json={
        "institution_reg_number": "1", "institution_name": "Co",
        "period_year": 2026, "period_quarter": 1,
        "rows": [_basic_row(fund_id, fair_value_ils=1000)],
    })
    assert confirm_resp.status_code == 201

    filings = client.get("/api/lookthrough/filings").get_json()
    assert len(filings) == 1

    securities = client.get("/api/lookthrough/securities").get_json()
    assert len(securities["securities"]) == 1
    assert securities["securities"][0]["combined_value"] == 1000.0


def test_lookthrough_import_confirm_missing_rows_returns_400(client):
    resp = client.post("/api/lookthrough/import/confirm", json={"institution_reg_number": "1"})
    assert resp.status_code == 400


def test_lookthrough_filings_delete_route(client):
    client.post("/api/funds", json={
        "name": "Fund", "fund_type": "pension", "company_name": "Co",
        "track_number": "5", "institution_reg_number": "1",
    })
    fund_id = client.get("/api/funds").get_json()[0]["id"]
    confirm_resp = client.post("/api/lookthrough/import/confirm", json={
        "institution_reg_number": "1", "institution_name": "Co",
        "period_year": 2026, "period_quarter": 1,
        "rows": [_basic_row(fund_id)],
    })
    filing_id = confirm_resp.get_json()["filing_id"]
    resp = client.delete(f"/api/lookthrough/filings/{filing_id}")
    assert resp.status_code == 200
    assert client.get("/api/lookthrough/filings").get_json() == []


def test_lookthrough_overlap_concentration_merged_routes_empty_by_default(client):
    assert client.get("/api/lookthrough/overlap").get_json() == {"securities": [], "active_funds": []}
    concentration = client.get("/api/lookthrough/concentration").get_json()
    assert concentration["total_portfolio"] == 0
    merged = client.get("/api/lookthrough/merged").get_json()
    assert merged == {"merged": [], "unmatched_direct": []}

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
    # fair_value_ils is the filing's own INSTITUTIONAL fair value for that
    # security within its track — not personal money by itself. db.py
    # converts it to a personal weight (this row's fair_value_ils / the sum
    # of every fair_value_ils row for that same fund) and multiplies that
    # weight by the fund's own recorded balance. So: when a fund has only
    # ONE row, its weight is always 1.0, and the resulting combined_value
    # equals the fund's balance exactly, regardless of the row's specific
    # fair_value_ils magnitude — most tests below lean on that. pct_of_track
    # is kept only as an informational field the parser also captures (see
    # get_security_holdings's docstring for why it can't be used for money).
    row = {
        "fund_id": fund_id, "instrument_type": "equity_traded",
        "issuer_name": "Acme Corp", "issuer_number": "999",
        "security_name": "Acme Ord", "security_number": "IL0001",
        "pct_of_track": 0.1, "fair_value_ils": 1000,
        "country": "Israel", "sector": "Tech", "currency": "ILS",
        "asset_class": "",
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
    """The core requirement: pension + study_fund combine seamlessly. Each
    fund has only one row, so its weight is 1.0 and its contribution equals
    its own recorded balance exactly."""
    pension_id = _make_fund(tmp_db, "pension", "1", "5", balance=10000, name="Pension")
    study_id = _make_fund(tmp_db, "study_fund", "1", "6", balance=20000, name="Study")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(pension_id),
        _basic_row(study_id),
    ], db_path=tmp_db)

    result = db.get_security_holdings(tmp_db)
    assert len(result["securities"]) == 1
    sec = result["securities"][0]
    assert sec["combined_value"] == 30000.0  # 10000 + 20000
    assert sec["by_fund"] == {pension_id: 10000.0, study_id: 20000.0}
    assert sec["fund_count"] == 2
    assert {f["fund_type"] for f in result["active_funds"]} == {"pension", "study_fund"}


def test_security_holdings_weights_rows_by_share_of_fund_total(tmp_db):
    """The core fix: fair_value_ils is the TRACK's institutional total, not
    personal money — confirmed against a real filing where it was
    1,500x-8,750x the user's own recorded balance. Each row must be
    converted to a weight (its own fair_value_ils / the sum of every
    fair_value_ils row for that fund) and applied to the fund's own
    balance, not used directly."""
    fund_id = _make_fund(tmp_db, "pension", "1", "5", balance=8000, name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_id, security_number="IL0001", fair_value_ils=6_000_000),  # 75% of track
        _basic_row(fund_id, security_number="IL0002", fair_value_ils=2_000_000),  # 25% of track
    ], db_path=tmp_db)
    securities = {s["security_number"]: s for s in db.get_security_holdings(tmp_db)["securities"]}
    assert securities["IL0001"]["combined_value"] == pytest.approx(6000.0)   # 75% of 8000
    assert securities["IL0002"]["combined_value"] == pytest.approx(2000.0)   # 25% of 8000


def test_security_holdings_empty_when_no_filings(tmp_db):
    assert db.get_security_holdings(tmp_db) == {"securities": [], "active_funds": []}


def test_security_holdings_flags_and_zeros_when_fund_has_no_balance(tmp_db):
    """A fund with holdings rows but no recorded balance yet can't have its
    personal weight applied to anything — flagged via has_unbalanced_fund
    and contributes 0, never a guessed number (this is the corrected
    behavior; an earlier version of this fix wrongly used fair_value_ils
    directly regardless of whether a balance existed, which is exactly the
    institutional-vs-personal bug being fixed here)."""
    fund_id = _make_fund(tmp_db, "pension", "1", "5")  # no balance
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [_basic_row(fund_id)], db_path=tmp_db)
    securities = db.get_security_holdings(tmp_db)["securities"]
    assert len(securities) == 1
    assert securities[0]["combined_value"] == 0.0
    assert securities[0]["has_unbalanced_fund"] is True


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
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=8000, name="A")
    fund_b = _make_fund(tmp_db, "pension", "1", "6", balance=2000, name="B")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a),
        _basic_row(fund_b),
    ], db_path=tmp_db)
    overlap = db.get_overlap_holdings(tmp_db)["securities"]
    assert overlap[0]["max_single_fund_share"] == pytest.approx(0.8)  # 8000 / 10000


# ── DB-level: concentration ───────────────────────────────────────────────────

def test_concentration_dual_denominator(tmp_db):
    # Fund balance == sum of the fund's fair_value_ils rows, so each row's
    # weighted personal value equals its own fair_value_ils exactly (5000
    # and 3000 respectively) — keeps this test's math simple to follow.
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=8000, name="A")
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


def test_concentration_rollup_includes_per_fund_and_direct_breakdown(tmp_db):
    """Each rollup row needs its own by_fund/direct split — "how much of
    this sector sits in THIS fund" — not just a portfolio-wide total, so a
    caller can show a per-fund % (e.g. "Energy is 15% of your Menora fund")."""
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=5000, name="A")
    fund_b = _make_fund(tmp_db, "pension", "1", "6", balance=2000, name="B")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, security_number="IL0001", sector="Tech"),  # 5000
        _basic_row(fund_b, security_number="IL0002", sector="Tech"),  # 2000
    ], db_path=tmp_db)
    holding = db.add_stock_holding("MSFT", isin="US5949181045", cost_basis=0, db_path=tmp_db)[0]
    db.add_stock_value(holding["id"], "2026-01-01", 10, 100, db_path=tmp_db)  # 1000 total, net 750, no sector

    rollups = db.get_concentration_rollups(tmp_db)
    tech = next(r for r in rollups["by_sector"] if r["label"] == "Tech")
    assert tech["by_fund"] == {fund_a: 5000.0, fund_b: 2000.0}
    assert tech["direct"] == 0.0
    unclassified = next(r for r in rollups["by_sector"] if r["label"] == "Unclassified")
    assert unclassified["direct"] == 750.0
    assert rollups["fund_totals"] == {fund_a: 5000.0, fund_b: 2000.0}
    assert rollups["direct_total"] == 750.0
    assert {f["id"] for f in rollups["active_funds"]} == {fund_a, fund_b}


def test_concentration_same_issuer_cross_type(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=2000, name="A")
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
    assert group["type_breakdown"] == {"equity_traded": 1000.0, "corp_bond": 1000.0}


def test_concentration_no_same_issuer_group_for_single_instrument_type(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=10000, name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [_basic_row(fund_a)], db_path=tmp_db)
    rollups = db.get_concentration_rollups(tmp_db)
    assert rollups["same_issuer_cross_type"] == []


def test_concentration_by_type_merges_derivatives(tmp_db):
    """A pie slice can't represent a negative value — decided with the user
    to merge all derivative/hedging types into one bucket rather than
    excluding or threshold-filtering them individually."""
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=1000, name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        # "loan" isn't touched by the separate equity/bond exposure merge
        # (test_concentration_by_type_merges_equity_and_bond_exposure covers
        # that one), so this test stays focused purely on the derivatives merge.
        _basic_row(fund_a, instrument_type="loan", security_number="EQ1", fair_value_ils=600),
        _basic_row(fund_a, instrument_type="option", security_number="OPT1", fair_value_ils=250),
        _basic_row(fund_a, instrument_type="future", security_number="FUT1", fair_value_ils=150),
    ], db_path=tmp_db)
    by_type = {r["label"]: r["value"] for r in db.get_concentration_rollups(tmp_db)["by_type"]}
    assert by_type["loan"] == 600.0
    assert by_type["Derivatives & Hedging"] == 400.0  # option 250 + future 150, one bucket
    assert "option" not in by_type
    assert "future" not in by_type


def test_concentration_by_type_includes_per_fund_and_direct_breakdown(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=600, name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, instrument_type="loan", security_number="LOAN1"),  # 600, not equity-merged
    ], db_path=tmp_db)
    holding = db.add_stock_holding("MSFT", isin="US5949181045", cost_basis=0, db_path=tmp_db)[0]
    db.add_stock_value(holding["id"], "2026-01-01", 10, 100, db_path=tmp_db)  # 1000 total, net 750, no fund match

    by_type = {r["label"]: r for r in db.get_concentration_rollups(tmp_db)["by_type"]}
    assert by_type["loan"]["by_fund"] == {fund_a: 600.0}
    assert by_type["loan"]["direct"] == 0.0
    # A direct holding is always equity (Manage Stock Holdings only tracks
    # Stock/ESPP/RSU) — it counts as Equity Exposure, not Unclassified, even
    # though it has no fund-derived instrument_type.
    assert by_type["Equity Exposure"]["direct"] == 750.0
    assert by_type["Equity Exposure"]["by_fund"] == {}
    assert "Unclassified" not in by_type


def test_concentration_by_type_merges_equity_and_bond_exposure(tmp_db):
    """Real finding: an ETF's economic exposure depends on what's inside it
    — found an actual Tel Bond (bond index) ETF sitting in the ETF sheet on
    real data, not equity. asset_class (from the filing's own Fund
    Classification field, never guessed from the ticker/name) is what
    correctly routes an equity-tracking ETF into Equity Exposure alongside
    direct stocks, and a bond-tracking one into Fixed Income Exposure
    alongside government/corporate bonds — an unresolved one stays under
    its own ETF/Mutual Fund bucket rather than being guessed either way."""
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=1000, name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, instrument_type="equity_traded", security_number="EQ1", fair_value_ils=300),
        _basic_row(fund_a, instrument_type="etf", security_number="ETF1", fair_value_ils=200, asset_class="equity"),
        _basic_row(fund_a, instrument_type="govt_bond", security_number="GB1", fair_value_ils=250),
        _basic_row(fund_a, instrument_type="etf", security_number="ETF2", fair_value_ils=150, asset_class="bond"),
        _basic_row(fund_a, instrument_type="etf", security_number="ETF3", fair_value_ils=100),  # asset_class unresolved
    ], db_path=tmp_db)
    by_type = {r["label"]: r for r in db.get_concentration_rollups(tmp_db)["by_type"]}
    assert by_type["Equity Exposure"]["value"] == 500.0   # 300 stock + 200 equity ETF
    assert by_type["Equity Exposure"]["type_breakdown"] == {"equity_traded": 300.0, "etf": 200.0}
    assert by_type["Fixed Income Exposure"]["value"] == 400.0  # 250 govt bond + 150 bond ETF
    assert by_type["Fixed Income Exposure"]["type_breakdown"] == {"govt_bond": 250.0, "etf": 150.0}
    assert by_type["etf"]["value"] == 100.0  # unresolved ETF stays its own bucket, not guessed either way


def test_concentration_by_fund_partitions_total_including_direct(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=3000, name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, security_number="IL0001"),  # weight 1.0 -> 3000 indirect
    ], db_path=tmp_db)
    holding = db.add_stock_holding("MSFT", isin="US5949181045", cost_basis=0, db_path=tmp_db)[0]
    db.add_stock_value(holding["id"], "2026-01-01", 10, 100, db_path=tmp_db)  # 1000 total, net 750

    by_fund = {r["label"]: r["value"] for r in db.get_concentration_rollups(tmp_db)["by_fund"]}
    assert by_fund["A (5)"] == 3000.0  # fund name + track number, since names can collide
    assert by_fund["Direct"] == 750.0
    assert sum(by_fund.values()) == pytest.approx(3750.0)


# ── DB-level: get_all_securities (merged direct + indirect) ─────────────────

def test_all_securities_merges_direct_and_indirect_by_isin(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=1000, name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, security_number="US0378331005"),  # weight 1.0 -> 1000 indirect
    ], db_path=tmp_db)
    holding = db.add_stock_holding("AAPL", isin="US0378331005", cost_basis=0, db_path=tmp_db)[0]
    db.add_stock_value(holding["id"], "2026-01-01", 10, 100, db_path=tmp_db)  # 1000 total, net 750

    result = db.get_all_securities(tmp_db)
    assert len(result["securities"]) == 1
    entry = result["securities"][0]
    assert entry["indirect_value"] == 1000.0
    assert entry["direct_value"] == 750.0  # net value preferred over total
    assert entry["combined_value"] == 1750.0
    assert entry["pct_of_total"] == 1.0  # the only security
    assert result["unmatched_direct"] == []


def test_all_securities_direct_holding_without_isin_is_unmatched(tmp_db):
    db.add_stock_holding("AAPL", db_path=tmp_db)  # no isin
    result = db.get_all_securities(tmp_db)
    assert result["securities"] == []
    assert len(result["unmatched_direct"]) == 1
    assert result["unmatched_direct"][0]["symbol"] == "AAPL"


def test_all_securities_direct_holding_with_isin_but_no_indirect_match_still_shown(tmp_db):
    holding = db.add_stock_holding("MSFT", isin="US5949181045", cost_basis=0, db_path=tmp_db)[0]
    db.add_stock_value(holding["id"], "2026-01-01", 5, 400, db_path=tmp_db)  # 2000 total, net 1500
    result = db.get_all_securities(tmp_db)
    assert len(result["securities"]) == 1
    assert result["securities"][0]["indirect_value"] == 0.0
    assert result["securities"][0]["direct_value"] == 1500.0
    assert result["unmatched_direct"] == []


def test_all_securities_pct_of_total_covers_direct_and_indirect_together(tmp_db):
    """The point of the merge: a directly-held security counts toward the
    same percentage denominator as fund-derived ones."""
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=3000, name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, security_number="IL0001"),  # 3000 indirect
    ], db_path=tmp_db)
    holding = db.add_stock_holding("MSFT", isin="US5949181045", cost_basis=0, db_path=tmp_db)[0]
    db.add_stock_value(holding["id"], "2026-01-01", 10, 100, db_path=tmp_db)  # 1000 total, net 750 (25% tax on the full gain since cost_basis=0)

    securities = {s["security_number"]: s for s in db.get_all_securities(tmp_db)["securities"]}
    assert securities["IL0001"]["pct_of_total"] == pytest.approx(0.8)          # 3000 / 3750
    assert securities["US5949181045"]["pct_of_total"] == pytest.approx(0.2)    # 750 / 3750


def test_all_securities_does_not_collide_rows_sharing_a_security_number(tmp_db):
    """Real bug found against actual data: a written equity option's
    security_number was the SAME as its underlying stock's ISIN, but with a
    DIFFERENT issuer_number (the option counterparty vs. the equity
    issuer) — get_security_holdings correctly keeps these as separate
    entries, but an earlier version of get_all_securities re-keyed on
    security_number alone for the direct-holding merge and silently
    overwrote one with the other, losing real money (confirmed ~₪62,000 on
    real data). Both must survive here with their own values intact, and a
    direct holding sharing that ISIN must merge into the equity-typed one,
    not the option."""
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=10000, name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, instrument_type="equity_traded", issuer_number="EQUITY-ISSUER",
                   security_number="IL0001", fair_value_ils=7000),
        _basic_row(fund_a, instrument_type="option", issuer_number="OPTION-COUNTERPARTY",
                   security_number="IL0001", fair_value_ils=3000),  # same security_number!
    ], db_path=tmp_db)

    securities = db.get_all_securities(tmp_db)["securities"]
    matching = [s for s in securities if s["security_number"] == "IL0001"]
    assert len(matching) == 2  # both survive, not collapsed into one
    assert {s["instrument_type"] for s in matching} == {"equity_traded", "option"}
    assert {round(s["indirect_value"], 2) for s in matching} == {7000.0, 3000.0}

    # A direct holding sharing that ISIN merges into the equity, not the option.
    holding = db.add_stock_holding("ACME", isin="IL0001", cost_basis=0, db_path=tmp_db)[0]
    db.add_stock_value(holding["id"], "2026-01-01", 1, 500, db_path=tmp_db)  # 500 total, net 375 (25% tax on the full gain since cost_basis=0)

    securities2 = db.get_all_securities(tmp_db)["securities"]
    equity_entry = next(s for s in securities2 if s["security_number"] == "IL0001" and s["instrument_type"] == "equity_traded")
    option_entry = next(s for s in securities2 if s["security_number"] == "IL0001" and s["instrument_type"] == "option")
    assert equity_entry["direct_value"] == 375.0
    assert option_entry["direct_value"] == 0.0


# ── DB-level: get_direct_fund_overlap ────────────────────────────────────────

def test_direct_fund_overlap_shows_fund_side_match(tmp_db):
    fund_a = _make_fund(tmp_db, "pension", "1", "5", balance=1000, name="A")
    db.replace_fund_holdings_filing("1", "Co", 2026, 1, [
        _basic_row(fund_a, security_number="US0378331005"),  # weight 1.0 -> 1000 indirect
    ], db_path=tmp_db)
    holding = db.add_stock_holding("AAPL", isin="US0378331005", cost_basis=0, db_path=tmp_db)[0]
    db.add_stock_value(holding["id"], "2026-01-01", 10, 100, db_path=tmp_db)  # 1000 total, net 750

    result = db.get_direct_fund_overlap(tmp_db)
    assert len(result["breakdown"]) == 1
    entry = result["breakdown"][0]
    assert entry["symbol"] == "AAPL"
    assert entry["direct_value"] == 750.0
    assert entry["indirect_value"] == 1000.0
    assert entry["by_fund"] == {fund_a: 1000.0}
    assert result["unmatched_direct"] == []


def test_direct_fund_overlap_shows_zero_not_omitted_when_no_fund_match(tmp_db):
    holding = db.add_stock_holding("MSFT", isin="US5949181045", cost_basis=0, db_path=tmp_db)[0]
    db.add_stock_value(holding["id"], "2026-01-01", 5, 400, db_path=tmp_db)  # 2000 total, net 1500
    result = db.get_direct_fund_overlap(tmp_db)
    assert len(result["breakdown"]) == 1
    assert result["breakdown"][0]["direct_value"] == 1500.0
    assert result["breakdown"][0]["indirect_value"] == 0.0
    assert result["breakdown"][0]["by_fund"] == {}


def test_direct_fund_overlap_holding_without_isin_is_unmatched(tmp_db):
    db.add_stock_holding("AAPL", db_path=tmp_db)  # no isin
    result = db.get_direct_fund_overlap(tmp_db)
    assert result["breakdown"] == []
    assert len(result["unmatched_direct"]) == 1
    assert result["unmatched_direct"][0]["symbol"] == "AAPL"


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
    # A recorded balance is required for get_security_holdings to compute a
    # personal weighted value at all — a fund with no balance is flagged
    # has_unbalanced_fund and contributes 0, see db.py.
    client.post(f"/api/funds/{fund_id}/balances", json={"date": "2026-01-01", "balance": 1000})

    confirm_resp = client.post("/api/lookthrough/import/confirm", json={
        "institution_reg_number": "1", "institution_name": "Co",
        "period_year": 2026, "period_quarter": 1,
        "rows": [_basic_row(fund_id)],  # single row -> weight 1.0 -> combined_value == balance
    })
    assert confirm_resp.status_code == 201

    filings = client.get("/api/lookthrough/filings").get_json()
    assert len(filings) == 1

    securities = client.get("/api/lookthrough/securities").get_json()
    assert len(securities["securities"]) == 1
    assert securities["securities"][0]["combined_value"] == 1000.0
    assert securities["securities"][0]["pct_of_total"] == 1.0


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
    assert merged == {"breakdown": [], "unmatched_direct": [], "active_funds": []}

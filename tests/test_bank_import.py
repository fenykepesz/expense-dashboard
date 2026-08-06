import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import pytest
import db
import app as flask_app
from bank_excel_to_json import parse_bank_export, verify_balance_chain


def make_export(rows, account_number="123-45678/90"):
    """Build a synthetic Bank Leumi account export (HTML-in-.xls).

    rows: list of 8-tuples (date, value_date, desc, ref, debit, credit, balance, note)
    """
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows
    )
    return f"""
    <HTML dir="RTL"><head><META http-equiv="Content-Type" content="text/html; charset=UTF-8"></head>
    <body>
    <table><tr><td>בנק לאומי |</td></tr>
    <tr><td>מס' חשבון: ‏{account_number}‎ תאריך</td></tr></table>
    <table class="xlTable">
    <tr><td>תנועות בחשבון</td></tr>
    <tr><td>תאריך</td><td>תאריך ערך</td><td>תיאור</td><td>אסמכתא</td><td>בחובה</td><td>בזכות</td><td>היתרה בש"ח</td><td>הערה</td></tr>
    {body}
    </table></body></HTML>
    """


STANDARD_ROWS = [
    # newest first, like the real file
    ("03/02/2026", "03/02/2026", "העברה עצמית", "555", "0.00", "5,000.00", "8,100.50", ""),
    ("15/01/2026", "15/01/2026", "שכר ינואר", "444", "0.00", "2,000.00", "3,100.50", "note!"),
    ("**\n  ", "10/01/2026", "הע. אינטרנט", "333", "1,234.56", "0.00", "1,100.50", ""),
]


@pytest.fixture
def export_file(tmp_path):
    path = tmp_path / "export.xls"
    path.write_text(make_export(STANDARD_ROWS), encoding="utf-8")
    return path


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db(test_db)
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


def _make_account(client, name="Checking", number="45678"):
    resp = client.post("/api/bank-accounts", json={"name": name, "account_number": number})
    return resp.get_json()["accounts"][0]["id"]


# ── Parser ───────────────────────────────────────────────────────────────────

def test_parse_returns_oldest_first_with_signed_amounts(export_file):
    txns, account_number, skipped = parse_bank_export(export_file)
    assert account_number == "123-45678/90"
    assert skipped == 0
    assert [t["date"] for t in txns] == ["2026-01-10", "2026-01-15", "2026-02-03"]
    assert txns[0]["amount"] == -1234.56 and txns[0]["type"] == "expense"
    assert txns[1]["amount"] == 2000.00 and txns[1]["type"] == "income"
    assert txns[2]["balance_after"] == 8100.50


def test_parse_footnote_date_falls_back_to_value_date(export_file):
    txns, _, _ = parse_bank_export(export_file)
    assert txns[0]["date"] == "2026-01-10"  # date cell was '**'


def test_parse_keeps_reference_and_note(export_file):
    txns, _, _ = parse_bank_export(export_file)
    assert txns[1]["reference"] == "444"
    assert txns[1]["notes"] == "note!"


def test_parse_skips_summary_rows(tmp_path):
    rows = STANDARD_ROWS + [("", "", 'סה"כ', "", "1,234.56", "7,000.00", "", "")]
    path = tmp_path / "with_total.xls"
    path.write_text(make_export(rows), encoding="utf-8")
    txns, _, _ = parse_bank_export(path)
    assert len(txns) == 3


def test_balance_chain_consistent(export_file):
    txns, _, _ = parse_bank_export(export_file)
    assert verify_balance_chain(txns) == []


# ── DB duplicate filter ──────────────────────────────────────────────────────

def test_filter_new_bank_transactions(tmp_path):
    test_db = tmp_path / "test.db"
    db.init_db(test_db)
    accounts = db.add_bank_account("Checking", db_path=test_db)
    account_id = accounts[0]["id"]
    rows = [
        {"date": "2026-01-10", "description": "a", "reference": "1", "amount": -10.0, "type": "expense"},
        {"date": "2026-01-11", "description": "b", "reference": "2", "amount": 20.0, "type": "income"},
    ]
    db.insert_bank_transactions(rows[:1], account_id, test_db)
    new, dupes = db.filter_new_bank_transactions(rows, account_id, test_db)
    assert [r["reference"] for r in new] == ["2"]
    assert [r["reference"] for r in dupes] == ["1"]


def test_insert_preserves_notes(tmp_path):
    test_db = tmp_path / "test.db"
    db.init_db(test_db)
    accounts = db.add_bank_account("Checking", db_path=test_db)
    account_id = accounts[0]["id"]
    db.insert_bank_transactions(
        [{"date": "2026-01-10", "description": "a", "amount": -10.0,
          "type": "expense", "notes": "hello"}],
        account_id, test_db,
    )
    assert db.get_bank_transactions(account_id, test_db)[0]["notes"] == "hello"


# ── API ──────────────────────────────────────────────────────────────────────

def _upload(client, account_id):
    data = make_export(STANDARD_ROWS).encode("utf-8")
    return client.post(
        f"/api/bank-accounts/{account_id}/import",
        data={"file": (io.BytesIO(data), "export.xls")},
        content_type="multipart/form-data",
    )


def test_import_preview(client):
    account_id = _make_account(client)
    resp = _upload(client, account_id)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["new_count"] == 3
    assert data["duplicate_count"] == 0
    assert data["file_account_number"] == "123-45678/90"
    assert all(t["duplicate"] is False for t in data["transactions"])


def test_import_confirm_and_reimport_skips_duplicates(client):
    account_id = _make_account(client)
    preview = _upload(client, account_id).get_json()
    confirm = client.post(
        f"/api/bank-accounts/{account_id}/import/confirm",
        json={"transactions": preview["transactions"]},
    )
    assert confirm.status_code == 201
    assert confirm.get_json()["inserted"] == 3

    # Same file again: everything is a duplicate, nothing gets inserted
    preview2 = _upload(client, account_id).get_json()
    assert preview2["new_count"] == 0
    assert preview2["duplicate_count"] == 3
    confirm2 = client.post(
        f"/api/bank-accounts/{account_id}/import/confirm",
        json={"transactions": preview2["transactions"]},
    )
    assert confirm2.get_json()["inserted"] == 0
    assert confirm2.get_json()["skipped_duplicates"] == 3
    assert len(client.get(f"/api/bank-accounts/{account_id}/transactions").get_json()) == 3


def test_import_rejects_non_excel(client):
    account_id = _make_account(client)
    resp = client.post(
        f"/api/bank-accounts/{account_id}/import",
        data={"file": (io.BytesIO(b"%PDF"), "statement.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_import_rejects_file_without_transactions(client):
    account_id = _make_account(client)
    resp = client.post(
        f"/api/bank-accounts/{account_id}/import",
        data={"file": (io.BytesIO(b"<html><body>nothing here</body></html>"), "empty.xls")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400

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


# ── DB-level tests ──────────────────────────────────────────────────────────

def test_get_household_members_empty_by_default(tmp_db):
    assert db.get_household_members(tmp_db) == []


def test_add_household_member(tmp_db):
    members = db.add_household_member("Dad", tmp_db)
    names = [m["name"] for m in members]
    assert "Dad" in names


def test_add_household_member_returns_sorted_list(tmp_db):
    db.add_household_member("Zoe", tmp_db)
    db.add_household_member("Amir", tmp_db)
    members = db.get_household_members(tmp_db)
    names = [m["name"] for m in members]
    assert names == sorted(names)


def test_household_member_has_id(tmp_db):
    members = db.add_household_member("Mom", tmp_db)
    assert all("id" in m for m in members)


def test_delete_household_member_soft_deletes(tmp_db):
    members = db.add_household_member("Kid1", tmp_db)
    member_id = members[0]["id"]
    db.delete_household_member(member_id, tmp_db)
    names = [m["name"] for m in db.get_household_members(tmp_db)]
    assert "Kid1" not in names


def test_delete_nonexistent_member_raises(tmp_db):
    with pytest.raises(ValueError):
        db.delete_household_member(9999, tmp_db)


def test_restore_deleted_member_by_readding(tmp_db):
    members = db.add_household_member("Sam", tmp_db)
    member_id = members[0]["id"]
    db.delete_household_member(member_id, tmp_db)
    db.add_household_member("Sam", tmp_db)
    names = [m["name"] for m in db.get_household_members(tmp_db)]
    assert "Sam" in names


def test_add_duplicate_name_does_not_create_second_row(tmp_db):
    db.add_household_member("Dana", tmp_db)
    members = db.add_household_member("Dana", tmp_db)
    names = [m["name"] for m in members]
    assert names.count("Dana") == 1


# ── Route-level tests ───────────────────────────────────────────────────────

def test_get_household_members_route_empty(client):
    resp = client.get("/api/household-members")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_create_household_member_route(client):
    resp = client.post("/api/household-members", json={"name": "Dad"})
    assert resp.status_code == 201
    names = [m["name"] for m in resp.get_json()["members"]]
    assert "Dad" in names


def test_create_household_member_missing_name_returns_400(client):
    resp = client.post("/api/household-members", json={})
    assert resp.status_code == 400


def test_delete_household_member_route(client):
    create_resp = client.post("/api/household-members", json={"name": "Mom"})
    member_id = create_resp.get_json()["members"][0]["id"]
    resp = client.delete(f"/api/household-members/{member_id}")
    assert resp.status_code == 200
    names = [m["name"] for m in resp.get_json()["members"]]
    assert "Mom" not in names


def test_delete_nonexistent_member_route_returns_400(client):
    resp = client.delete("/api/household-members/9999")
    assert resp.status_code == 400

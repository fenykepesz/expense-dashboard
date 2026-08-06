import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import pytest
import db
import app as flask_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db(test_db)
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


REAL_BACKUP_DIR = Path(flask_app.DEFAULT_BACKUP_PATH)


def _real_backups():
    return set(REAL_BACKUP_DIR.glob("*.zip")) if REAL_BACKUP_DIR.exists() else set()


def test_backup_dir_diverted_during_tests(client):
    """Under TESTING, _backup_dir must not point at the real backup folder."""
    assert flask_app._backup_dir() != REAL_BACKUP_DIR


def test_no_auto_backup_during_tests(client):
    """A TESTING client must never write into the real backup folder.

    Regression: every test hitting /api/transactions used to zip its
    throwaway DB into backups/, and the keep-10 pruning then evicted
    genuine backups.
    """
    before = _real_backups()
    resp = client.get("/api/transactions")
    assert resp.status_code == 200
    assert _real_backups() == before


def test_import_confirm_backup_diverted_during_tests(client):
    """/api/import/confirm auto-backups before inserting — that backup must
    also stay out of the real folder under TESTING."""
    before = _real_backups()
    resp = client.post("/api/import/confirm", json={"transactions": [{
        "date": "2026-01-01", "merchant": "Test", "amount": 10.0,
        "category": "Other", "month": "January", "year": 2026, "card": "0000",
    }]})
    assert resp.status_code == 201
    assert _real_backups() == before

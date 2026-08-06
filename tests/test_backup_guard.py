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


def test_no_auto_backup_during_tests(client):
    """A TESTING client must never write into the real backup folder.

    Regression: every test hitting /api/transactions used to zip its
    throwaway DB into backups/, and the keep-10 pruning then evicted
    genuine backups.
    """
    backup_dir = flask_app._backup_dir()
    before = set(backup_dir.glob("*.zip")) if backup_dir.exists() else set()
    resp = client.get("/api/transactions")
    assert resp.status_code == 200
    after = set(backup_dir.glob("*.zip")) if backup_dir.exists() else set()
    assert before == after

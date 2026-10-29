from fastapi.testclient import TestClient

from app import bff
from app.database import Database


def test_health_reports_sqlite_storage(tmp_path):
    with TestClient(bff.create_app(str(tmp_path / "health.sqlite3"))) as client:
        assert client.get("/health").json()["storage"] == "sqlite"


def test_health_reports_postgres_storage_flag(tmp_path, monkeypatch):
    class DatabaseWithPostgres:
        postgres = True

        def __init__(self):
            self.inner = Database(str(tmp_path / "health.sqlite3"))

        def connect(self, **kwargs):
            return self.inner.connect(**kwargs)

    database = DatabaseWithPostgres()
    monkeypatch.setattr(bff, "Database", lambda _: database)
    with TestClient(bff.create_app(str(tmp_path / "ignored.sqlite3"))) as client:
        assert client.get("/health").json()["storage"] == "postgres"

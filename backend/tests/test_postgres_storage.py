import os

import pytest

from app.database import Database, put


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is required for PostgreSQL integration")
def test_postgres_put_upsert_and_rows(tmp_path):
    db = Database(str(tmp_path / "unused.sqlite3"))
    assert db.postgres
    with db.connect() as connection:
        connection.execute("INSERT INTO owners VALUES(?) ON CONFLICT DO NOTHING", ("postgres-test",))
        put(connection, "trip", {"trip_id": "postgres-trip", "expires_at": None}, "postgres-test")
        assert connection.execute("SELECT payload FROM objects WHERE id=?", ("postgres-trip",)).fetchone()["payload"]

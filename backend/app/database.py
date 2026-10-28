"""Минимальное транзакционное хранилище каркаса BFF (SQLite)."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, path: str):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS owners(id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS sessions(
                    token_hash TEXT PRIMARY KEY, owner TEXT NOT NULL, expires TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS objects(
                    kind TEXT NOT NULL, id TEXT NOT NULL, owner TEXT NOT NULL,
                    payload TEXT NOT NULL, expires TEXT, PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS idempotency(
                    owner TEXT NOT NULL, operation TEXT NOT NULL, key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
                    expires TEXT NOT NULL, PRIMARY KEY(owner,operation,key));
                CREATE TABLE IF NOT EXISTS operation_claims(
                    owner TEXT NOT NULL, operation TEXT NOT NULL, key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, expires TEXT NOT NULL,
                    PRIMARY KEY(owner,operation,key));
                CREATE TABLE IF NOT EXISTS search_inputs(
                    search_id TEXT PRIMARY KEY, owner TEXT NOT NULL, query TEXT NOT NULL,
                    params TEXT NOT NULL, expires TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS quote_inputs(
                    search_id TEXT PRIMARY KEY, owner TEXT NOT NULL, trip_id TEXT NOT NULL,
                    payload TEXT NOT NULL, expires TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS search_runs(
                    search_id TEXT NOT NULL, owner TEXT NOT NULL, run_id TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'plan', state TEXT NOT NULL,
                    deadline_at TEXT NOT NULL,
                    expected_revision INTEGER NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(search_id,run_id));
                CREATE INDEX IF NOT EXISTS idx_search_runs_state
                    ON search_runs(state, deadline_at);
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(search_runs)")}
            if "kind" not in columns:
                db.execute(
                    "ALTER TABLE search_runs ADD COLUMN kind TEXT NOT NULL DEFAULT 'plan'"
                )

    @contextmanager
    def connect(self, *, write: bool = True):
        db = sqlite3.connect(self.path, timeout=0.25)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


def put(db, kind: str, value: dict, owner: str):
    id_fields = {
        "trip": "trip_id",
        "search": "search_id",
        "hotels": "trip_id",
        "flights": "trip_id",
    }
    try:
        object_id = value[id_fields[kind]]
    except KeyError:
        raise ValueError(f"Unsupported object kind: {kind}") from None
    cursor = db.execute(
        "INSERT INTO objects VALUES(?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload, expires=excluded.expires WHERE objects.owner=excluded.owner",
        (kind, object_id, owner, json.dumps(value, ensure_ascii=False), value.get("expires_at")),
    )
    if cursor.rowcount != 1:
        raise sqlite3.IntegrityError("Object owner cannot change")

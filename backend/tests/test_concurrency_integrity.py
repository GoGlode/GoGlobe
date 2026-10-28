"""Concurrency, idempotency and SQLite integrity audit with controlled gates."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sqlite3
from threading import Barrier, BrokenBarrierError, Event, Lock
import time
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.bff import create_app, digest, stamp
from app.contracts import examples
from app.planning import DemoPlanner


ORIGIN = "http://localhost:8000"
DEFAULT_HEADERS = {"Origin": ORIGIN}


def login(client):
    response = client.post("/api/v1/session", json={})
    assert response.status_code == 200
    return dict(client.cookies)


def search(client, key, body=None):
    return client.post(
        "/api/v1/searches",
        json=deepcopy(body or examples()["plan_request"]["value"]),
        headers={"Idempotency-Key": key},
    )


def counts(path):
    with sqlite3.connect(path) as db:
        objects = dict(db.execute("SELECT kind, count(*) FROM objects GROUP BY kind"))
        idempotency = db.execute("SELECT count(*) FROM idempotency").fetchone()[0]
    return objects, idempotency


def wait_snapshot(client, location, states, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(location)
        assert response.status_code == 200
        if response.json()["state"] in states:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(f"search did not reach {states}")


class GatedAgent:
    def __init__(self):
        self.started = Event()
        self.release = Event()
        self.calls = 0
        self._lock = Lock()

    async def plan(self, context):
        with self._lock:
            self.calls += 1
        self.started.set()
        await asyncio.to_thread(self.release.wait)
        return await DemoPlanner().plan(context)


def test_post_accepts_before_agent_finishes_and_persists_run_id(tmp_path):
    path = str(tmp_path / "durable-run.sqlite3")
    agent = GatedAgent()
    with TestClient(create_app(path, agent=agent), headers=DEFAULT_HEADERS) as client:
        login(client)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(search, client, str(uuid4()))
            assert agent.started.wait(timeout=5)
            response = future.result(timeout=1)
            assert response.status_code == 202
            with sqlite3.connect(path) as db:
                run = db.execute(
                    "SELECT run_id,state FROM search_runs WHERE search_id=?",
                    (response.json()["search_id"],),
                ).fetchone()
            assert run[0].startswith("r_")
            assert run[1] == "processing"
            snapshot = client.get(response.headers["location"]).json()
            assert snapshot["state"] == "processing"
            agent.release.set()
        completed = wait_snapshot(client, response.headers["location"], {"completed"})
        assert completed["revision"] > snapshot["revision"]


def test_draft_rejects_itinerary_mutations_and_keeps_saved_expiry(tmp_path):
    path = str(tmp_path / "draft-mutations.sqlite3")
    agent = GatedAgent()
    with TestClient(create_app(path, agent=agent), headers=DEFAULT_HEADERS) as client:
        login(client)
        response = search(client, str(uuid4()))
        assert response.status_code == 202
        assert agent.started.wait(timeout=5)
        trip_url = f"/api/v1/trips/{response.json()['trip_id']}"
        draft = client.get(trip_url).json()
        assert draft["itinerary"] is None

        schedule = client.put(
            trip_url + "/schedule",
            json={
                "expected_revision": draft["revision"],
                "start_date": "2026-11-10",
                "end_date": "2026-11-11",
                "timezone": "Europe/Rome",
            },
        )
        assert schedule.status_code == 409
        assert schedule.json()["error"]["code"] == "TRIP_NOT_READY"

        quote = deepcopy(examples()["quote_request"]["value"])
        quote["expected_revision"] = draft["revision"]
        quoted = client.post(
            trip_url + "/quote-searches",
            json=quote,
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert quoted.status_code == 409
        assert quoted.json()["error"]["code"] == "TRIP_NOT_READY"

        saved = client.put(trip_url + "/saved", json={})
        assert saved.status_code == 200
        assert saved.json()["expires_at"] is None
        agent.release.set()
        wait_snapshot(client, response.headers["location"], {"completed"})
        completed = client.get(trip_url).json()
        assert completed["saved_at"] is not None
        assert completed["expires_at"] is None


def test_restart_resumes_persisted_processing_run(tmp_path):
    path = str(tmp_path / "resume-run.sqlite3")

    class NeverFinishes:
        def __init__(self):
            self.started = Event()

        async def plan(self, context):
            self.started.set()
            await asyncio.Event().wait()

    blocked = NeverFinishes()
    with TestClient(create_app(path, agent=blocked), headers=DEFAULT_HEADERS) as first:
        cookies = login(first)
        accepted = search(first, str(uuid4()))
        assert accepted.status_code == 202
        assert blocked.started.wait(timeout=2)
        assert first.get(accepted.headers["location"]).json()["state"] == "processing"
        location = accepted.headers["location"]

    with TestClient(
        create_app(path), headers=DEFAULT_HEADERS, cookies=cookies,
    ) as restarted:
        snapshot = wait_snapshot(restarted, location, {"completed"})
        assert snapshot["state"] == "completed"
        with sqlite3.connect(path) as db:
            state = db.execute(
                "SELECT state FROM search_runs WHERE search_id=? ORDER BY updated_at DESC",
                (accepted.json()["search_id"],),
            ).fetchone()[0]
        assert state == "completed"


def test_session_creation_physically_purges_expired_private_rows(tmp_path):
    path = str(tmp_path / "purge.sqlite3")
    with TestClient(create_app(path), headers=DEFAULT_HEADERS) as client:
        login(client)
        accepted = search(
            client, str(uuid4()), {"query": "Хочу путешествие"},
        )
        assert accepted.status_code == 202
        wait_snapshot(client, accepted.headers["location"], {"needs_clarification"})
        expired = stamp(datetime.now(timezone.utc) - timedelta(days=1))
        with sqlite3.connect(path) as db:
            db.execute("UPDATE sessions SET expires=?", (expired,))
            db.execute("UPDATE objects SET expires=?", (expired,))
            db.execute("UPDATE idempotency SET expires=?", (expired,))
            db.execute("UPDATE search_inputs SET expires=?", (expired,))
        assert client.post("/api/v1/session", json={}).status_code == 200
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT count(*) FROM objects").fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM idempotency").fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM search_inputs").fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM search_runs").fetchone()[0] == 0


def test_same_process_simultaneous_same_key_creates_one_trip(tmp_path):
    path = str(tmp_path / "same-process.sqlite3")
    agent = GatedAgent()
    start = Barrier(3)
    with TestClient(create_app(path, agent=agent), headers=DEFAULT_HEADERS) as client:
        login(client)
        key = str(uuid4())

        def request():
            start.wait(timeout=5)
            return search(client, key)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(request) for _ in range(2)]
            start.wait(timeout=5)
            assert agent.started.wait(timeout=5)
            agent.release.set()
            responses = [future.result(timeout=5) for future in futures]

        assert [response.status_code for response in responses] == [202, 202]
        assert responses[0].json() == responses[1].json()
        assert agent.calls == 1
        assert counts(path) == ({"search": 1, "trip": 1}, 1)


def test_separate_app_instances_race_same_key_without_duplicate_write(tmp_path):
    """Separate app objects model processes: their Python locks are not shared."""
    path = str(tmp_path / "cross-process.sqlite3")
    plan_barrier = Barrier(2)
    calls = []
    calls_lock = Lock()

    class BarrierAgent:
        async def plan(self, context):
            with calls_lock:
                calls.append(context.query)
            try:
                await asyncio.to_thread(plan_barrier.wait, 5)
            except BrokenBarrierError:
                pytest.fail("both app instances did not reach the planning barrier")
            return await DemoPlanner().plan(context)

    with ExitStack() as stack:
        first = stack.enter_context(TestClient(create_app(path, agent=BarrierAgent()), headers=DEFAULT_HEADERS))
        cookies = login(first)
        second = stack.enter_context(TestClient(
            create_app(path, agent=BarrierAgent()), headers=DEFAULT_HEADERS, cookies=cookies,
        ))
        key = str(uuid4())
        start = Barrier(3)

        def request(client):
            start.wait(timeout=5)
            return search(client, key)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(request, client) for client in (first, second)]
            start.wait(timeout=5)
            responses = [future.result(timeout=10) for future in futures]

    assert len(calls) == 1  # durable acceptance prevents duplicate provider/agent work
    assert all(response.status_code == 202 for response in responses)
    assert responses[0].json() == responses[1].json()
    assert counts(path) == ({"search": 1, "trip": 1}, 1)


def test_separate_app_instances_race_same_key_different_bodies_one_wins(tmp_path):
    path = str(tmp_path / "cross-process-conflict.sqlite3")
    plan_barrier = Barrier(2)

    class BarrierAgent:
        async def plan(self, context):
            try:
                await asyncio.to_thread(plan_barrier.wait, 5)
            except BrokenBarrierError:
                pytest.fail("both conflicting requests did not reach the planning barrier")
            return await DemoPlanner().plan(context)

    with ExitStack() as stack:
        first = stack.enter_context(TestClient(create_app(path, agent=BarrierAgent()), headers=DEFAULT_HEADERS))
        cookies = login(first)
        second = stack.enter_context(TestClient(
            create_app(path, agent=BarrierAgent()), headers=DEFAULT_HEADERS, cookies=cookies,
        ))
        key = str(uuid4())
        bodies = [deepcopy(examples()["plan_request"]["value"]) for _ in range(2)]
        bodies[1]["query"] = "конкурирующее описание запроса"
        start = Barrier(3)

        def request(client, body):
            start.wait(timeout=5)
            return search(client, key, body)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(request, client, body) for client, body in zip((first, second), bodies)]
            start.wait(timeout=5)
            responses = [future.result(timeout=10) for future in futures]

        assert sorted(response.status_code for response in responses) == [202, 409]
        assert next(response for response in responses if response.status_code == 409).json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        accepted = next(response for response in responses if response.status_code == 202)
        assert first.get(f"/api/v1/trips/{accepted.json()['trip_id']}").status_code == 200
        assert counts(path) == ({"search": 1, "trip": 1}, 1)


def test_idempotency_conflict_preserves_original_result(tmp_path):
    path = str(tmp_path / "conflict.sqlite3")
    with TestClient(create_app(path), headers=DEFAULT_HEADERS) as client:
        login(client)
        key = str(uuid4())
        original = search(client, key)
        original_trip = client.get(f"/api/v1/trips/{original.json()['trip_id']}").json()
        original_snapshot = client.get(original.headers["location"]).json()
        changed = deepcopy(examples()["plan_request"]["value"])
        changed["query"] = "другое описание того же маршрута"

        conflict = search(client, key, changed)
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        assert client.get(f"/api/v1/trips/{original.json()['trip_id']}").json() == original_trip
        assert client.get(original.headers["location"]).json() == original_snapshot
        assert counts(path) == ({"search": 1, "trip": 1}, 1)


@pytest.mark.parametrize("failure", ["error", "timeout"])
def test_agent_failure_or_timeout_persists_terminal_snapshot(tmp_path, failure):
    path = str(tmp_path / f"agent-{failure}.sqlite3")

    class Agent:
        async def plan(self, context):
            if failure == "error":
                raise RuntimeError("controlled agent failure")
            await asyncio.Event().wait()

    timeout = 0.03 if failure == "timeout" else 1
    with TestClient(
        create_app(path, agent=Agent(), agent_timeout=timeout),
        headers=DEFAULT_HEADERS,
        raise_server_exceptions=False,
    ) as client:
        login(client)
        response = search(client, str(uuid4()))
        assert response.status_code == 202
        snapshot = wait_snapshot(client, response.headers["location"], {"failed"})
        assert snapshot["error"]["code"] == (
            "SEARCH_TIMEOUT" if failure == "timeout" else "AGENT_UNAVAILABLE"
        )
        assert counts(path) == ({"search": 1, "trip": 1}, 1)
        assert len(client.get("/api/v1/trips").json()["items"]) == 1


def test_api_cancellation_invalidates_run_and_blocks_late_write(tmp_path):
    path = str(tmp_path / "cancelled.sqlite3")

    class Agent:
        def __init__(self):
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()
            self.block = True

        async def plan(self, context):
            if self.block:
                self.started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    self.cancelled.set()
            return await DemoPlanner().plan(context)

    async def scenario():
        agent = Agent()
        app = create_app(path, agent=agent)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", headers=DEFAULT_HEADERS,
        ) as client:
            assert (await client.post("/api/v1/session", json={})).status_code == 200
            key = str(uuid4())
            response = await client.post(
                "/api/v1/searches",
                json=deepcopy(examples()["plan_request"]["value"]),
                headers={"Idempotency-Key": key},
            )
            assert response.status_code == 202
            await asyncio.wait_for(agent.started.wait(), timeout=5)
            cancelled = await client.put(response.headers["location"] + "/cancellation", json={})
            assert cancelled.status_code == 200
            assert cancelled.json()["state"] == "cancelled"
            await asyncio.wait_for(agent.cancelled.wait(), timeout=5)
            assert counts(path) == ({"search": 1, "trip": 1}, 1)
            agent.block = False
            replay = await client.post(
                "/api/v1/searches",
                json=deepcopy(examples()["plan_request"]["value"]),
                headers={"Idempotency-Key": key},
            )
            assert replay.status_code == 202
            assert replay.json() == response.json()
            assert (await client.get(response.headers["location"])).json()["state"] == "cancelled"

    asyncio.run(scenario())


def test_session_expiring_after_acceptance_does_not_orphan_run(tmp_path):
    path = str(tmp_path / "session-expires-during-plan.sqlite3")
    agent = GatedAgent()
    with TestClient(create_app(path, agent=agent), headers=DEFAULT_HEADERS) as client:
        cookies = login(client)
        key = str(uuid4())
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(search, client, key)
            assert agent.started.wait(timeout=5)
            with sqlite3.connect(path) as db:
                db.execute("UPDATE sessions SET expires=? WHERE token_hash=?", (
                    stamp(datetime.now(timezone.utc) - timedelta(seconds=1)),
                    digest(cookies["gg_session"]),
                ))
            agent.release.set()
            response = future.result(timeout=5)

        assert response.status_code == 202
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with sqlite3.connect(path) as db:
                payload = db.execute(
                    "SELECT payload FROM objects WHERE kind='search' AND id=?",
                    (response.json()["search_id"],),
                ).fetchone()
            if payload and '"state": "completed"' in payload[0]:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("accepted run was orphaned after session expiry")
        assert counts(path) == ({"search": 1, "trip": 1}, 1)


def test_simultaneous_save_unsave_and_schedule_are_serializable(tmp_path):
    path = str(tmp_path / "trip-updates.sqlite3")
    with TestClient(create_app(path), headers=DEFAULT_HEADERS) as client:
        login(client)
        accepted = search(client, str(uuid4())).json()
        url = f"/api/v1/trips/{accepted['trip_id']}"
        initial = client.get(url).json()
        schedule = {
            "expected_revision": initial["revision"],
            "start_date": "2026-11-10",
            "end_date": "2026-11-11",
            "timezone": "Europe/Rome",
        }
        start = Barrier(4)

        def change(name):
            start.wait(timeout=5)
            if name == "save":
                return name, client.put(url + "/saved", json={})
            if name == "unsave":
                return name, client.delete(url + "/saved")
            return name, client.put(url + "/schedule", json=schedule)

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(change, name) for name in ("save", "unsave", "schedule")]
            start.wait(timeout=5)
            results = dict(future.result(timeout=10) for future in futures)

        assert results["save"].status_code == 200
        assert results["unsave"].status_code == 204
        assert results["schedule"].status_code in {200, 409}
        assert all(response.status_code != 500 for response in results.values())

        final = client.get(url).json()
        save_revision = results["save"].json()["revision"]
        assert final["revision"] in {save_revision, save_revision + 1}
        assert (final["saved_at"] is not None) == (final["revision"] == save_revision)
        if results["schedule"].status_code == 200:
            assert final["schedule"]["start_date"] == schedule["start_date"]
        else:
            assert final["schedule"]["start_date"] is None
            retry = {**schedule, "expected_revision": final["revision"]}
            assert client.put(url + "/schedule", json=retry).status_code == 200


def test_revision_allows_exactly_one_concurrent_schedule(tmp_path):
    path = str(tmp_path / "revision.sqlite3")
    with TestClient(create_app(path), headers=DEFAULT_HEADERS) as client:
        login(client)
        trip_id = search(client, str(uuid4())).json()["trip_id"]
        url = f"/api/v1/trips/{trip_id}"
        revision = client.get(url).json()["revision"]
        requests = [
            {"expected_revision": revision, "start_date": "2026-11-10", "end_date": "2026-11-11", "timezone": "Europe/Rome"},
            {"expected_revision": revision, "start_date": "2026-12-01", "end_date": "2026-12-02", "timezone": "Europe/Rome"},
        ]
        start = Barrier(3)

        def schedule(body):
            start.wait(timeout=5)
            return client.put(url + "/schedule", json=body)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(schedule, body) for body in requests]
            start.wait(timeout=5)
            responses = [future.result(timeout=10) for future in futures]

        assert sorted(response.status_code for response in responses) == [200, 409]
        conflict = next(response for response in responses if response.status_code == 409)
        winner = next(response for response in responses if response.status_code == 200).json()
        assert conflict.json()["error"]["code"] == "REVISION_CONFLICT"
        assert client.get(url).json() == winner


def test_owner_cannot_read_or_mutate_foreign_identifiers(tmp_path):
    path = str(tmp_path / "owners.sqlite3")
    with ExitStack() as stack:
        owner = stack.enter_context(TestClient(create_app(path), headers=DEFAULT_HEADERS))
        stranger = stack.enter_context(TestClient(create_app(path), headers=DEFAULT_HEADERS))
        login(owner)
        login(stranger)
        accepted = search(owner, str(uuid4()))
        trip_id = accepted.json()["trip_id"]
        trip_url = f"/api/v1/trips/{trip_id}"
        search_url = accepted.headers["location"]
        original = owner.get(trip_url).json()
        schedule = {
            "expected_revision": original["revision"],
            "start_date": "2026-11-10",
            "end_date": "2026-11-11",
            "timezone": "Europe/Rome",
        }

        assert stranger.get(trip_url).status_code == 404
        assert stranger.get(search_url).status_code == 404
        assert stranger.get(search_url + "/events").status_code == 404
        assert stranger.put(trip_url + "/saved", json={}).status_code == 404
        assert stranger.put(trip_url + "/schedule", json=schedule).status_code == 404
        # Idempotent delete intentionally does not reveal whether the identifier exists.
        assert stranger.delete(trip_url + "/saved").status_code == 204
        assert owner.get(trip_url).json() == original


def test_expired_session_and_objects_are_unavailable_everywhere(tmp_path):
    path = str(tmp_path / "expiry.sqlite3")
    with TestClient(create_app(path), headers=DEFAULT_HEADERS) as client:
        cookies = login(client)
        accepted = search(client, str(uuid4()))
        trip_id = accepted.json()["trip_id"]
        trip_url = f"/api/v1/trips/{trip_id}"
        search_url = accepted.headers["location"]

        with sqlite3.connect(path) as db:
            db.execute("UPDATE sessions SET expires=? WHERE token_hash=?", (
                stamp(datetime.now(timezone.utc) - timedelta(seconds=1)),
                digest(cookies["gg_session"]),
            ))
        assert client.get(trip_url).status_code == 403
        assert client.get(search_url).status_code == 403
        assert client.get("/api/v1/trips").status_code == 403
        assert client.put(trip_url + "/saved", json={}).status_code == 403

    with TestClient(create_app(path), headers=DEFAULT_HEADERS) as current:
        login(current)
        accepted = search(current, str(uuid4()))
        trip_id = accepted.json()["trip_id"]
        trip_url = f"/api/v1/trips/{trip_id}"
        search_url = accepted.headers["location"]
        with sqlite3.connect(path) as db:
            db.execute("UPDATE objects SET expires=? WHERE id IN (?, ?)", (
                stamp(datetime.now(timezone.utc) - timedelta(seconds=1)),
                trip_id,
                accepted.json()["search_id"],
            ))
        assert current.get(trip_url).status_code == 404
        assert current.get(search_url).status_code == 404
        assert current.get(search_url + "/events").status_code == 404
        assert current.get("/api/v1/trips").json()["items"] == []
        assert current.put(trip_url + "/saved", json={}).status_code == 404
        assert current.put(trip_url + "/schedule", json={
            "expected_revision": 1,
            "start_date": "2026-11-10",
            "end_date": "2026-11-11",
            "timezone": "Europe/Rome",
        }).status_code == 404
        assert current.delete(trip_url + "/saved").status_code == 204


def test_restart_preserves_sqlite_idempotency(tmp_path):
    path = str(tmp_path / "restart-idempotency.sqlite3")
    key = str(uuid4())
    with TestClient(create_app(path), headers=DEFAULT_HEADERS) as first:
        cookies = login(first)
        original = search(first, key)
        accepted = original.json()
    with TestClient(create_app(path), headers=DEFAULT_HEADERS, cookies=cookies) as restarted:
        replay = search(restarted, key)
        assert replay.status_code == 202
        assert replay.json() == accepted
        assert replay.headers["location"] == original.headers["location"]
        assert counts(path) == ({"search": 1, "trip": 1}, 1)


def test_sqlite_failure_rolls_back_trip_snapshot_and_idempotency(tmp_path):
    path = str(tmp_path / "rollback.sqlite3")
    key = str(uuid4())
    with TestClient(create_app(path), headers=DEFAULT_HEADERS, raise_server_exceptions=False) as client:
        login(client)
        with sqlite3.connect(path) as db:
            db.execute("""
                CREATE TRIGGER fail_idempotency BEFORE INSERT ON idempotency
                BEGIN SELECT RAISE(ABORT, 'controlled write failure'); END
            """)
        failed = search(client, key)
        assert failed.status_code == 500
        assert failed.json()["error"]["code"] == "INTERNAL_ERROR"
        assert counts(path) == ({}, 0)

        with sqlite3.connect(path) as db:
            db.execute("DROP TRIGGER fail_idempotency")
        assert search(client, key).status_code == 202
        assert counts(path) == ({"search": 1, "trip": 1}, 1)


def test_parallel_reads_continue_while_an_uncommitted_writer_holds_reservation(tmp_path):
    path = str(tmp_path / "locked.sqlite3")
    with ExitStack() as stack:
        first = stack.enter_context(TestClient(create_app(path), headers=DEFAULT_HEADERS))
        cookies = login(first)
        clients = [first] + [
            stack.enter_context(TestClient(create_app(path), headers=DEFAULT_HEADERS, cookies=cookies))
            for _ in range(3)
        ]
        start = Barrier(len(clients) + 1)
        with sqlite3.connect(path, timeout=1) as locker:
            locker.execute("BEGIN IMMEDIATE")

            def request(client):
                start.wait(timeout=5)
                return client.get("/api/v1/trips")

            with ThreadPoolExecutor(max_workers=len(clients)) as pool:
                futures = [pool.submit(request, client) for client in clients]
                start.wait(timeout=5)
                responses = [future.result(timeout=10) for future in futures]

        assert all(response.status_code == 200 for response in responses)
        assert all(response.json()["items"] == [] for response in responses)
        assert first.get("/api/v1/trips").status_code == 200


def test_parallel_writes_from_separate_app_instances_commit_cleanly(tmp_path):
    path = str(tmp_path / "parallel-writes.sqlite3")
    count = 6
    plan_barrier = Barrier(count)

    class BarrierAgent:
        async def plan(self, context):
            try:
                await asyncio.to_thread(plan_barrier.wait, 5)
            except BrokenBarrierError:
                pytest.fail("all app instances did not reach the planning barrier")
            return await DemoPlanner().plan(context)

    with ExitStack() as stack:
        first = stack.enter_context(TestClient(create_app(path, agent=BarrierAgent()), headers=DEFAULT_HEADERS))
        cookies = login(first)
        clients = [first] + [
            stack.enter_context(TestClient(
                create_app(path, agent=BarrierAgent()), headers=DEFAULT_HEADERS, cookies=cookies,
            ))
            for _ in range(count - 1)
        ]
        start = Barrier(count + 1)

        def request(client):
            start.wait(timeout=5)
            return search(client, str(uuid4()))

        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(request, client) for client in clients]
            start.wait(timeout=5)
            responses = [future.result(timeout=10) for future in futures]

        assert all(response.status_code == 202 for response in responses)
        assert len({response.json()["trip_id"] for response in responses}) == count
        assert counts(path) == ({"search": count, "trip": count}, count)

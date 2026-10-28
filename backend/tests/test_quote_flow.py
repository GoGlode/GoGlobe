import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3
from threading import Event, Lock
import time
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.bff import create_app
from app.contracts import examples, validate
from app.integrations.ports import ToolResult
from app.integrations.service import IntegrationTools


ORIGIN = "http://localhost:8000"


def _login_and_plan(client):
    assert client.post("/api/v1/session", json={}).status_code == 200
    accepted = client.post(
        "/api/v1/searches",
        json=deepcopy(examples()["plan_request"]["value"]),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert accepted.status_code == 202, accepted.text
    trip_url = "/api/v1/trips/" + accepted.json()["trip_id"]
    return accepted, trip_url, client.get(trip_url).json()


def _quote_body(revision):
    body = deepcopy(examples()["quote_request"]["value"])
    body["expected_revision"] = revision
    return body


def _wait_snapshot(client, location, states, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(location)
        assert response.status_code == 200
        if response.json()["state"] in states:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(f"quote search did not reach {states}")


def test_quote_search_persists_lists_context_and_keeps_itinerary(tmp_path):
    with TestClient(
        create_app(str(tmp_path / "quotes.sqlite3")), headers={"Origin": ORIGIN}
    ) as client:
        _, trip_url, before = _login_and_plan(client)

        response = client.post(
            trip_url + "/quote-searches",
            json=_quote_body(before["revision"]),
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert response.status_code == 202, response.text
        validate("Accepted", response.json())
        snapshot = client.get(response.headers["location"])
        assert snapshot.status_code == 200
        assert snapshot.json()["kind"] == "quotes"
        assert snapshot.json()["state"] == "completed"

        after = client.get(trip_url).json()
        assert after["trip_id"] == before["trip_id"]
        assert after["itinerary"] == before["itinerary"]
        assert after["revision"] == before["revision"] + 1

        hotels = client.get(trip_url + "/hotels")
        flights = client.get(trip_url + "/flights")
        assert hotels.status_code == flights.status_code == 200
        validate("HotelList", hotels.json())
        validate("FlightList", flights.json())
        assert hotels.json()["state"] == "ready"
        assert flights.json()["state"] == "ready"
        assert hotels.json()["context"] == {
            "travelers": {"adults": 2, "children_ages": []},
            "stay": {"check_in": "2026-11-10", "check_out": "2026-11-11"},
        }
        assert flights.json()["context"]["origin"] == "Москва"
        assert all(item["booking_url"] is None for item in hotels.json()["items"])
        assert all(item["booking_url"] is None for item in flights.json()["items"])
        assert all(item["availability"] == "unknown" for item in hotels.json()["items"])
        assert all(item["availability"] == "unknown" for item in flights.json()["items"])


def test_quote_inputs_report_exact_missing_field(tmp_path):
    with TestClient(
        create_app(str(tmp_path / "missing.sqlite3")), headers={"Origin": ORIGIN}
    ) as client:
        _, trip_url, trip = _login_and_plan(client)
        body = _quote_body(trip["revision"])
        body.pop("travelers")

        response = client.post(
            trip_url + "/quote-searches",
            json=body,
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "QUOTE_INPUTS_REQUIRED"
        assert response.json()["error"]["details"] == [
            {"field": "travelers", "message": "Обязательное поле отсутствует"}
        ]
        assert client.get(trip_url).json()["revision"] == trip["revision"]


def test_quote_idempotency_replays_without_new_revision(tmp_path):
    with TestClient(
        create_app(str(tmp_path / "idempotent.sqlite3")), headers={"Origin": ORIGIN}
    ) as client:
        _, trip_url, trip = _login_and_plan(client)
        key = str(uuid4())
        body = _quote_body(trip["revision"])

        first = client.post(
            trip_url + "/quote-searches", json=body,
            headers={"Idempotency-Key": key},
        )
        revision = client.get(trip_url).json()["revision"]
        replay = client.post(
            trip_url + "/quote-searches", json=body,
            headers={"Idempotency-Key": key},
        )

        assert first.status_code == replay.status_code == 202
        assert replay.json() == first.json()
        assert client.get(trip_url).json()["revision"] == revision


def test_quote_idempotency_key_cannot_cross_trip_boundary(tmp_path):
    with TestClient(
        create_app(str(tmp_path / "cross-trip-idempotency.sqlite3")),
        headers={"Origin": ORIGIN},
    ) as client:
        _, first_url, first_trip = _login_and_plan(client)
        _, second_url, second_trip = _login_and_plan(client)
        assert first_trip["revision"] == second_trip["revision"]
        key = str(uuid4())
        body = _quote_body(first_trip["revision"])

        first = client.post(
            first_url + "/quote-searches", json=body,
            headers={"Idempotency-Key": key},
        )
        conflict = client.post(
            second_url + "/quote-searches", json=body,
            headers={"Idempotency-Key": key},
        )

        assert first.status_code == 202
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_concurrent_quote_replay_uses_one_provider_run(tmp_path):
    class SlowUnavailableProvider:
        data_mode = "live"

        def __init__(self):
            self.calls = 0
            self.started = Event()
            self.release = Event()
            self.lock = Lock()

        async def search(self, criteria):
            with self.lock:
                self.calls += 1
                if self.calls == 2:
                    self.started.set()
            await asyncio.to_thread(self.release.wait)
            return ToolResult(
                "unavailable", [], [],
                [{"code": "PROVIDER_TIMEOUT", "message": "timeout", "trip_id": None}],
                "live",
            )

    provider = SlowUnavailableProvider()
    path = str(tmp_path / "concurrent-quote.sqlite3")
    tools = IntegrationTools(hotels=provider, flights=provider)
    with TestClient(create_app(path, tools=tools), headers={"Origin": ORIGIN}) as client:
        _, trip_url, trip = _login_and_plan(client)
        key = str(uuid4())
        body = _quote_body(trip["revision"])

        def request():
            return client.post(
                trip_url + "/quote-searches", json=body,
                headers={"Idempotency-Key": key},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(request) for _ in range(2)]
            assert provider.started.wait(timeout=5)
            provider.release.set()
            responses = [future.result(timeout=5) for future in futures]

        assert all(response.status_code == 202 for response in responses)
        assert responses[0].json() == responses[1].json()
        assert provider.calls == 2  # one hotels call + one flights call
        assert client.get(trip_url).json()["revision"] == trip["revision"] + 1
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT count(*) FROM operation_claims").fetchone()[0] == 0


class _UnavailableProvider:
    data_mode = "live"

    async def search(self, criteria):
        return ToolResult(
            "unavailable", [], [],
            [{"code": "PROVIDER_TIMEOUT", "message": "Источник не ответил.", "trip_id": None}],
            "live",
        )


def test_provider_failure_is_separate_from_itinerary(tmp_path):
    tools = IntegrationTools(
        hotels=_UnavailableProvider(), flights=_UnavailableProvider(),
        destinations=_UnavailableProvider(),
    )
    with TestClient(
        create_app(str(tmp_path / "failure.sqlite3"), tools=tools),
        headers={"Origin": ORIGIN},
    ) as client:
        _, trip_url, before = _login_and_plan(client)

        response = client.post(
            trip_url + "/quote-searches",
            json=_quote_body(before["revision"]),
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert response.status_code == 202, response.text
        after = client.get(trip_url).json()
        assert after["itinerary"] == before["itinerary"]
        assert after["components"]["hotels"]["state"] == "failed"
        assert after["components"]["flights"]["state"] == "failed"
        assert client.get(trip_url + "/hotels").json()["error"]["code"] == "PROVIDER_TIMEOUT"
        assert client.get(trip_url + "/flights").json()["error"]["code"] == "PROVIDER_TIMEOUT"


class _GatedProvider:
    data_mode = "live"

    def __init__(self):
        self.calls = 0
        self.started = Event()
        self.release = Event()
        self.cancelled = Event()
        self.lock = Lock()

    async def search(self, criteria):
        with self.lock:
            self.calls += 1
            if self.calls == 2:
                self.started.set()
        try:
            await asyncio.to_thread(self.release.wait)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return ToolResult("ok", [], [], [], "live")


def test_quote_accepts_before_providers_finish_and_persists_run(tmp_path):
    provider = _GatedProvider()
    path = str(tmp_path / "quote-background.sqlite3")
    tools = IntegrationTools(hotels=provider, flights=provider)
    with TestClient(create_app(path, tools=tools), headers={"Origin": ORIGIN}) as client:
        _, trip_url, trip = _login_and_plan(client)
        response = client.post(
            trip_url + "/quote-searches",
            json=_quote_body(trip["revision"]),
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 202
        assert provider.started.wait(timeout=2)
        assert client.get(trip_url).json()["revision"] == trip["revision"]
        with sqlite3.connect(path) as db:
            run = db.execute(
                "SELECT kind,state FROM search_runs WHERE search_id=?",
                (response.json()["search_id"],),
            ).fetchone()
            assert run == ("quotes", "processing")
            assert db.execute(
                "SELECT count(*) FROM quote_inputs WHERE search_id=?",
                (response.json()["search_id"],),
            ).fetchone()[0] == 1
        provider.release.set()
        completed = _wait_snapshot(client, response.headers["location"], {"completed"})
        assert completed["kind"] == "quotes"
        with sqlite3.connect(path) as db:
            assert db.execute(
                "SELECT count(*) FROM quote_inputs WHERE search_id=?",
                (response.json()["search_id"],),
            ).fetchone()[0] == 0


def test_quote_cancellation_blocks_late_write_and_preserves_trip(tmp_path):
    provider = _GatedProvider()
    path = str(tmp_path / "quote-cancel.sqlite3")
    tools = IntegrationTools(hotels=provider, flights=provider)
    with TestClient(create_app(path, tools=tools), headers={"Origin": ORIGIN}) as client:
        _, trip_url, before = _login_and_plan(client)
        response = client.post(
            trip_url + "/quote-searches",
            json=_quote_body(before["revision"]),
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert provider.started.wait(timeout=2)
        cancelled = client.put(response.headers["location"] + "/cancellation", json={})
        assert cancelled.status_code == 200
        assert cancelled.json()["state"] == "cancelled"
        assert provider.cancelled.wait(timeout=2)
        provider.release.set()
        time.sleep(0.05)
        assert client.get(response.headers["location"]).json() == cancelled.json()
        assert client.get(trip_url).json() == before
        with sqlite3.connect(path) as db:
            assert db.execute(
                "SELECT count(*) FROM objects WHERE kind IN ('hotels','flights')"
            ).fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM quote_inputs").fetchone()[0] == 0


def test_quote_restart_resumes_same_run_and_replays_accepted(tmp_path):
    class NeverProvider:
        data_mode = "live"

        def __init__(self):
            self.calls = 0
            self.started = Event()

        async def search(self, criteria):
            self.calls += 1
            if self.calls == 2:
                self.started.set()
            await asyncio.Event().wait()

    path = str(tmp_path / "quote-restart.sqlite3")
    blocked = NeverProvider()
    key = str(uuid4())
    with TestClient(
        create_app(path, tools=IntegrationTools(hotels=blocked, flights=blocked)),
        headers={"Origin": ORIGIN},
    ) as first:
        _, trip_url, trip = _login_and_plan(first)
        body = _quote_body(trip["revision"])
        accepted = first.post(
            trip_url + "/quote-searches", json=body,
            headers={"Idempotency-Key": key},
        )
        assert accepted.status_code == 202
        assert blocked.started.wait(timeout=2)
        cookies = dict(first.cookies)

    with TestClient(
        create_app(path), headers={"Origin": ORIGIN}, cookies=cookies,
    ) as restarted:
        completed = _wait_snapshot(
            restarted, accepted.headers["location"], {"completed"},
        )
        assert completed["kind"] == "quotes"
        replay = restarted.post(
            trip_url + "/quote-searches", json=body,
            headers={"Idempotency-Key": key},
        )
        assert replay.status_code == 202
        assert replay.json() == accepted.json()
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT count(*) FROM quote_inputs").fetchone()[0] == 0


def test_quote_revision_conflict_is_terminal_and_non_destructive(tmp_path):
    provider = _GatedProvider()
    path = str(tmp_path / "quote-revision.sqlite3")
    with TestClient(
        create_app(path, tools=IntegrationTools(hotels=provider, flights=provider)),
        headers={"Origin": ORIGIN},
    ) as client:
        _, trip_url, before = _login_and_plan(client)
        response = client.post(
            trip_url + "/quote-searches",
            json=_quote_body(before["revision"]),
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert provider.started.wait(timeout=2)
        saved = client.put(trip_url + "/saved", json={})
        assert saved.status_code == 200
        provider.release.set()
        failed = _wait_snapshot(client, response.headers["location"], {"failed"})
        assert failed["error"]["code"] == "REVISION_CONFLICT"
        after = client.get(trip_url).json()
        assert after["saved_at"] is not None
        assert after["itinerary"] == before["itinerary"]
        assert after["revision"] == saved.json()["revision"]
        with sqlite3.connect(path) as db:
            assert db.execute(
                "SELECT count(*) FROM objects WHERE kind IN ('hotels','flights')"
            ).fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM quote_inputs").fetchone()[0] == 0


def test_quote_sse_follows_background_run_to_finished(tmp_path):
    async def scenario():
        class AsyncGate:
            data_mode = "live"

            def __init__(self):
                self.calls = 0
                self.started = asyncio.Event()
                self.release = asyncio.Event()

            async def search(self, criteria):
                self.calls += 1
                if self.calls == 2:
                    self.started.set()
                await self.release.wait()
                return ToolResult("ok", [], [], [], "live")

        provider = AsyncGate()
        app = create_app(
            str(tmp_path / "quote-sse.sqlite3"),
            tools=IntegrationTools(hotels=provider, flights=provider),
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver",
            headers={"Origin": ORIGIN},
        ) as client:
            assert (await client.post("/api/v1/session", json={})).status_code == 200
            plan = await client.post(
                "/api/v1/searches", json=deepcopy(examples()["plan_request"]["value"]),
                headers={"Idempotency-Key": str(uuid4())},
            )
            trip_url = "/api/v1/trips/" + plan.json()["trip_id"]
            trip = (await client.get(trip_url)).json()
            quote = await client.post(
                trip_url + "/quote-searches", json=_quote_body(trip["revision"]),
                headers={"Idempotency-Key": str(uuid4())},
            )
            await asyncio.wait_for(provider.started.wait(), timeout=2)
            stream = asyncio.create_task(client.get(quote.headers["location"] + "/events"))
            await asyncio.sleep(0.05)
            provider.release.set()
            events = await asyncio.wait_for(stream, timeout=3)
            assert "event: snapshot" in events.text
            assert "event: finished" in events.text
            assert events.text.index("event: snapshot") < events.text.index("event: finished")

    asyncio.run(scenario())

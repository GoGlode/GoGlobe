import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3
from threading import Event, Lock
from uuid import uuid4

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

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.bff import create_app
from app.contracts import examples
from app.database import Database, put
from app.integrations.ports import HotelCriteria, FlightCriteria, ToolResult
from app.integrations.service import IntegrationTools
from app.planning import AgentPlan, DemoPlanner

ORIGIN = {"Origin": "http://localhost:8000"}


def login(client):
    assert client.post("/api/v1/session", json={}).status_code == 200


def search(client, key=None):
    return client.post("/api/v1/searches", headers={"Idempotency-Key": key or str(uuid4())},
                       json=examples()["plan_request"]["value"])


def wait_terminal(client, response, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = client.get(response.headers["location"]).json()
        if snapshot["state"] in {"completed", "failed", "cancelled"}:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("search did not become terminal")


class CountingAgent:
    def __init__(self):
        self.calls = 0

    async def plan(self, context):
        self.calls += 1
        await asyncio.sleep(0.02)
        return await DemoPlanner().plan(context)


def test_same_key_concurrency_calls_agent_once(tmp_path):
    agent = CountingAgent()
    with TestClient(create_app(str(tmp_path / "concurrent.sqlite3"), agent=agent), headers=ORIGIN) as client:
        login(client)
        key = str(uuid4())
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: search(client, key), range(8)))
        assert all(response.status_code == 202 for response in responses)
        assert all(response.json() == responses[0].json() for response in responses)
        assert agent.calls == 1
        assert len(client.get("/api/v1/trips").json()["items"]) == 1


def test_independent_concurrent_searches(tmp_path):
    agent = CountingAgent()
    with TestClient(create_app(str(tmp_path / "independent.sqlite3"), agent=agent), headers=ORIGIN) as client:
        login(client)
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: search(client), range(8)))
        assert all(response.status_code == 202 for response in responses)
        assert len({response.json()["trip_id"] for response in responses}) == 8


def test_timeout_failure_is_persisted_and_idempotency_replays_acceptance(tmp_path):
    class Agent:
        fail = True
        async def plan(self, context):
            if self.fail:
                await asyncio.sleep(1)
            return await DemoPlanner().plan(context)
    agent = Agent()
    # Keep the deadline short enough to cancel the 1 s branch, but leave
    # headroom for the successful demo planner on loaded CI/Windows hosts.
    with TestClient(
        create_app(
            str(tmp_path / "timeout.sqlite3"), agent=agent,
            agent_timeout=0.2,
        ),
        headers=ORIGIN,
    ) as client:
        login(client)
        key = str(uuid4())
        response = search(client, key)
        assert response.status_code == 202
        snapshot = wait_terminal(client, response)
        assert snapshot["error"]["code"] == "SEARCH_TIMEOUT"
        assert snapshot["error"]["retryable"] is True
        agent.fail = False
        replay = search(client, key)
        assert replay.json() == response.json()
        assert client.get(response.headers["location"]).json() == snapshot
        fresh = search(client, str(uuid4()))
        assert wait_terminal(client, fresh)["state"] == "completed"


@pytest.mark.parametrize("fault", ["crash", "wrong_type", "wrong_days", "wrong_destination", "missing_source", "duplicate_item", "dated_days"])
def test_bad_agent_does_not_write_or_crash(tmp_path, fault):
    class BadAgent:
        async def plan(self, context):
            if fault == "crash":
                raise RuntimeError("private-provider-secret")
            if fault == "wrong_type":
                return {"looks": "plausible"}
            plan = await DemoPlanner().plan(context)
            if fault == "wrong_days":
                return AgentPlan(plan.destination, 3, plan.itinerary)
            if fault == "wrong_destination":
                return AgentPlan({**plan.destination, "name": "Берлин"}, 2, plan.itinerary)
            if fault == "missing_source":
                plan.itinerary["days"][0]["items"][0]["source_ids"] = ["unknown"]
            if fault == "duplicate_item":
                plan.itinerary["days"][1]["items"][0]["item_id"] = plan.itinerary["days"][0]["items"][0]["item_id"]
            if fault == "dated_days":
                plan.itinerary["days"][0]["date"] = "2026-11-10"
            return plan
    with TestClient(create_app(str(tmp_path / "bad.sqlite3"), agent=BadAgent()), headers=ORIGIN) as client:
        login(client)
        response = search(client)
        assert response.status_code == 202
        snapshot = wait_terminal(client, response)
        assert snapshot["state"] == "failed"
        assert snapshot["error"]["code"] == (
            "AGENT_UNAVAILABLE" if fault == "crash" else "AGENT_INVALID_RESPONSE"
        )
        assert "private-provider-secret" not in str(snapshot)
        assert client.get("/health").status_code == 200


def test_agent_to_both_tools_to_providers_to_bff(tmp_path):
    calls = []
    class HotelProvider:
        data_mode = "demo"
        async def search(self, criteria):
            calls.append(("hotels", criteria.travelers))
            fixture = deepcopy(examples()["hotel_offers"]["value"])
            return ToolResult("ok", fixture["items"], fixture["sources"], [], "demo")
    class FlightProvider:
        data_mode = "demo"
        async def search(self, criteria):
            calls.append(("flights", criteria.origin))
            fixture = deepcopy(examples()["flight_offers"]["value"])
            return ToolResult("ok", fixture["items"], fixture["sources"], [], "demo")
    class Agent:
        async def plan(self, context):
            travelers = {"adults": 2, "children_ages": []}
            hotel, flight = await asyncio.gather(
                context.tools.hotels(HotelCriteria("Рим", {"check_in": "2026-11-10", "check_out": "2026-11-11"}, travelers, None, [], context.deadline_at)),
                context.tools.flights(FlightCriteria("Рим", "Москва", {"outbound_date": "2026-11-10", "return_date": "2026-11-11"}, travelers, None, [], context.deadline_at)),
            )
            assert hotel.status == flight.status == "ok"
            return await DemoPlanner().plan(context)
    tools = IntegrationTools(HotelProvider(), FlightProvider())
    with TestClient(create_app(str(tmp_path / "pipeline.sqlite3"), agent=Agent(), tools=tools), headers=ORIGIN) as client:
        login(client)
        response = search(client)
        assert response.status_code == 202
        trip = client.get("/api/v1/trips/" + response.json()["trip_id"]).json()
        assert trip["itinerary"]["days"]
        assert len(calls) == 2
        # Цена инструментов не становится автоматически итоговой ценой поездки.
        assert trip["price_summary"]["money"] is None


@pytest.mark.parametrize("fault", ["crash", "timeout", "wrong_type", "wrong_dates", "wrong_source", "wrong_mode"])
def test_provider_failure_is_isolated(fault):
    class Provider:
        data_mode = "live"
        async def search(self, criteria):
            if fault == "crash":
                raise RuntimeError("provider-secret")
            if fault == "timeout":
                await asyncio.sleep(1)
            if fault == "wrong_type":
                return None
            fixture = deepcopy(examples()["hotel_offers"]["value"])
            if fault == "wrong_dates":
                fixture["items"][0]["check_in"] = "2026-11-09"
            if fault == "wrong_source":
                fixture["sources"] = []
            return ToolResult("ok", fixture["items"], fixture["sources"], [], "demo" if fault == "wrong_mode" else "live")
    async def run():
        deadline = datetime.now(timezone.utc) + timedelta(seconds=0.03 if fault == "timeout" else 1)
        criteria = HotelCriteria("Рим", {"check_in": "2026-11-10", "check_out": "2026-11-11"}, {"adults": 2, "children_ages": []}, None, [], deadline)
        result = await IntegrationTools(hotels=Provider()).hotels(criteria)
        assert result.status == "unavailable"
        assert result.items == []
        assert result.data_mode == "live"
        assert "provider-secret" not in str(result)
    asyncio.run(run())


def test_storage_cannot_overwrite_another_owner(tmp_path):
    import sqlite3
    database = Database(str(tmp_path / "owners.sqlite3"))
    trip = deepcopy(examples()["trip_relative"]["value"])
    with database.connect() as db:
        put(db, "trip", trip, "first-owner")
    with pytest.raises(sqlite3.IntegrityError):
        with database.connect() as db:
            put(db, "trip", {**trip, "title": "overwritten"}, "other-owner")
    with database.connect() as db:
        assert db.execute("SELECT owner FROM objects").fetchone()["owner"] == "first-owner"


def test_no_ui_and_reusable_contract_objects(tmp_path):
    fixture = examples()
    fixture["plan_request"]["value"]["query"] = "mutated"
    assert examples()["plan_request"]["value"]["query"] != "mutated"
    with TestClient(create_app(str(tmp_path / "no-ui.sqlite3"))) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404


def test_late_agent_result_is_not_committed(tmp_path):
    class LateAgent:
        async def plan(self, context):
            try:
                await asyncio.sleep(0.2)
            except asyncio.CancelledError:
                pass
            return await DemoPlanner().plan(context)
    with TestClient(create_app(str(tmp_path / "late.sqlite3"), agent=LateAgent(), agent_timeout=0.01), headers=ORIGIN) as client:
        login(client)
        response = search(client)
        assert response.status_code == 202
        snapshot = wait_terminal(client, response)
        assert snapshot["state"] == "failed"
        time.sleep(0.25)
        assert client.get(response.headers["location"]).json() == snapshot


def test_unauthenticated_request_never_calls_agent(tmp_path):
    agent = CountingAgent()
    with TestClient(create_app(str(tmp_path / "auth.sqlite3"), agent=agent), headers=ORIGIN) as client:
        assert search(client).status_code == 403
        assert agent.calls == 0


def test_large_and_malformed_json_are_controlled(tmp_path):
    with TestClient(create_app(str(tmp_path / "input.sqlite3")), headers=ORIGIN) as client:
        login(client)
        headers = {"Content-Type": "application/json", "Idempotency-Key": str(uuid4())}
        assert client.post("/api/v1/searches", content='{"query":', headers=headers).status_code == 400
        assert client.post("/api/v1/searches", content='{"query":"' + 'x' * 70000 + '"}', headers=headers).status_code == 413
        assert client.post("/api/v1/searches", content='{"query":"test","params":{"duration_days":2.0}}', headers=headers).status_code == 422


def test_storage_lock_is_temporary_and_does_not_crash(tmp_path):
    import sqlite3
    path = str(tmp_path / "locked.sqlite3")
    with TestClient(create_app(path), headers=ORIGIN) as client:
        login(client)
        with sqlite3.connect(path) as locker:
            locker.execute("BEGIN IMMEDIATE")
            response = client.get("/api/v1/trips")
            assert response.status_code == 200
            assert response.json()["items"] == []
            assert client.get("/health").status_code == 200
        assert client.get("/api/v1/trips").status_code == 200
        assert client.get("/health").status_code == 200


def test_corrupt_saved_object_does_not_stop_server(tmp_path):
    import sqlite3
    path = str(tmp_path / "corrupt.sqlite3")
    with TestClient(create_app(path), headers=ORIGIN, raise_server_exceptions=False) as client:
        login(client)
        accepted = search(client).json()
        with sqlite3.connect(path) as db:
            db.execute("UPDATE objects SET payload='invalid json' WHERE kind='trip'")
        assert client.get("/api/v1/trips/" + accepted["trip_id"]).status_code == 500
        assert client.get("/health").status_code == 200

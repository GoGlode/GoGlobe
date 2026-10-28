import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.bff import create_app
from app.contracts import validate
from app.planning import DemoPlanner


ORIGIN = "http://localhost:8000"


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "lifecycle.sqlite3")),
                    headers={"Origin": ORIGIN}) as value:
        assert value.post("/api/v1/session", json={}).status_code == 200
        yield value


def post_search(client, query):
    return client.post("/api/v1/searches", json={"query": query},
                       headers={"Idempotency-Key": str(uuid4())})


def answer(client, search_id, snapshot, value):
    return client.post(
        f"/api/v1/searches/{search_id}/clarifications",
        json={
            "question_id": snapshot["clarification"]["question_id"],
            "expected_revision": snapshot["revision"],
            "answer": value,
        },
        headers={"Idempotency-Key": str(uuid4())},
    )


def test_query_without_explicit_params_materializes_itinerary(client):
    accepted = post_search(client, "Хочу в Рим на 2 дня")
    assert accepted.status_code == 202
    snapshot = client.get(accepted.headers["location"]).json()
    assert snapshot["state"] == "completed"
    trip = client.get(f"/api/v1/trips/{accepted.json()['trip_id']}").json()
    validate("Trip", trip)
    assert trip["destination"]["name"] == "Рим"
    assert len(trip["itinerary"]["days"]) == 2
    assert trip["price_summary"]["status"] == "unknown"


def test_explicit_dates_survive_background_completion(client):
    response = client.post(
        "/api/v1/searches",
        json={
            "query": "Хочу в Рим на 2 дня",
            "params": {
                "destination": "Рим",
                "duration_days": 2,
                "dates": {
                    "start_date": "2026-11-10",
                    "end_date": "2026-11-11",
                },
            },
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202
    trip = client.get(f"/api/v1/trips/{response.json()['trip_id']}").json()
    assert trip["schedule"]["start_date"] == "2026-11-10"
    assert trip["schedule"]["end_date"] == "2026-11-11"
    assert [day["date"] for day in trip["itinerary"]["days"]] == [
        "2026-11-10", "2026-11-11",
    ]


def test_two_clarifications_keep_same_trip_and_complete(client):
    accepted = post_search(client, "Хочу путешествие")
    assert accepted.status_code == 202
    search_id = accepted.json()["search_id"]
    trip_id = accepted.json()["trip_id"]
    snapshot = client.get(accepted.headers["location"]).json()
    assert snapshot["state"] == "needs_clarification"
    assert snapshot["clarification"]["field"] == "destination"

    first = answer(client, search_id, snapshot, "Рим")
    assert first.status_code == 202
    assert first.json()["trip_id"] == trip_id
    snapshot = client.get(accepted.headers["location"]).json()
    assert snapshot["state"] == "needs_clarification"
    assert snapshot["clarification"]["field"] == "duration_days"

    stale = answer(client, search_id, {**snapshot, "revision": snapshot["revision"] - 1}, "2")
    assert stale.status_code == 409
    completed = answer(client, search_id, snapshot, "На два дня")
    assert completed.status_code == 202
    assert completed.json()["trip_id"] == trip_id
    final_snapshot = client.get(accepted.headers["location"]).json()
    assert final_snapshot["state"] == "completed"
    trip = client.get(f"/api/v1/trips/{trip_id}").json()
    assert trip["trip_id"] == trip_id
    assert len(trip["itinerary"]["days"]) == 2


def test_clarification_question_id_is_guarded(client):
    accepted = post_search(client, "Хочу путешествие")
    snapshot = client.get(accepted.headers["location"]).json()
    response = client.post(
        f"/api/v1/searches/{accepted.json()['search_id']}/clarifications",
        json={"question_id": "q_stale", "expected_revision": snapshot["revision"],
              "answer": "Рим"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "QUESTION_CONFLICT"


def test_nonterminal_sse_stays_open_until_cancellation(tmp_path):
    async def scenario():
        app = create_app(str(tmp_path / "sse-transition.sqlite3"))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Origin": ORIGIN},
        ) as async_client:
            assert (await async_client.post("/api/v1/session", json={})).status_code == 200
            accepted = await async_client.post(
                "/api/v1/searches",
                json={"query": "Хочу путешествие"},
                headers={"Idempotency-Key": str(uuid4())},
            )
            location = accepted.headers["location"]
            snapshot = (await async_client.get(location)).json()
            assert snapshot["state"] == "needs_clarification"

            stream = asyncio.create_task(async_client.get(location + "/events"))
            await asyncio.sleep(0.05)
            cancelled = await async_client.put(location + "/cancellation", json={})
            assert cancelled.status_code == 200
            assert cancelled.json()["state"] == "cancelled"
            assert cancelled.json()["components"]["itinerary"]["error"]["code"] == "SEARCH_CANCELLED"
            events = await asyncio.wait_for(stream, timeout=3)
            assert "event: snapshot" in events.text
            assert "event: finished" in events.text
            assert events.text.index("event: snapshot") < events.text.index("event: finished")
            repeated = await async_client.put(location + "/cancellation", json={})
            assert repeated.json() == cancelled.json()

    asyncio.run(scenario())


def test_logout_revokes_an_open_sse_stream(tmp_path):
    async def scenario():
        app = create_app(str(tmp_path / "sse-logout.sqlite3"))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Origin": ORIGIN},
        ) as async_client:
            await async_client.post("/api/v1/session", json={})
            accepted = await async_client.post(
                "/api/v1/searches", json={"query": "Хочу путешествие"},
                headers={"Idempotency-Key": str(uuid4())},
            )
            location = accepted.headers["location"]
            assert (await async_client.get(location)).json()["state"] == "needs_clarification"
            stream = asyncio.create_task(async_client.get(location + "/events"))
            await asyncio.sleep(0.05)
            assert (await async_client.delete("/api/v1/session")).status_code == 204
            events = await asyncio.wait_for(stream, timeout=3)
            assert "event: snapshot" in events.text
            assert "event: finished" not in events.text

    asyncio.run(scenario())


def test_sse_emits_update_when_run_revision_advances(tmp_path):
    class SecondRunGate:
        def __init__(self):
            self.calls = 0
            self.started = asyncio.Event()

        async def plan(self, context):
            self.calls += 1
            if self.calls == 2:
                self.started.set()
                await asyncio.Event().wait()
            return await DemoPlanner().plan(context)

    async def scenario():
        agent = SecondRunGate()
        app = create_app(str(tmp_path / "sse-update.sqlite3"), agent=agent)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Origin": ORIGIN},
        ) as async_client:
            await async_client.post("/api/v1/session", json={})
            accepted = await async_client.post(
                "/api/v1/searches", json={"query": "Хочу путешествие"},
                headers={"Idempotency-Key": str(uuid4())},
            )
            location = accepted.headers["location"]
            snapshot = (await async_client.get(location)).json()
            stream = asyncio.create_task(async_client.get(location + "/events"))
            await async_client.post(
                location + "/clarifications",
                json={
                    "question_id": snapshot["clarification"]["question_id"],
                    "expected_revision": snapshot["revision"],
                    "answer": "Рим",
                },
                headers={"Idempotency-Key": str(uuid4())},
            )
            await asyncio.wait_for(agent.started.wait(), timeout=2)
            await asyncio.sleep(0.3)
            await async_client.put(location + "/cancellation", json={})
            events = await asyncio.wait_for(stream, timeout=3)
            assert "event: snapshot" in events.text
            assert "event: update" in events.text
            assert "event: finished" in events.text

    asyncio.run(scenario())


def test_clarification_completion_is_idempotent(client):
    accepted = post_search(client, "Хочу в Рим")
    location = accepted.headers["location"]
    snapshot = client.get(location).json()
    key = str(uuid4())
    payload = {
        "question_id": snapshot["clarification"]["question_id"],
        "expected_revision": snapshot["revision"],
        "answer": "2",
    }
    first = client.post(location + "/clarifications", json=payload,
                        headers={"Idempotency-Key": key})
    second = client.post(location + "/clarifications", json=payload,
                         headers={"Idempotency-Key": key})
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()


def test_clarification_idempotency_key_cannot_cross_search_boundary(client):
    first = post_search(client, "Хочу путешествие")
    second = post_search(client, "Хочу путешествие")
    first_snapshot = client.get(first.headers["location"]).json()
    key = str(uuid4())
    payload = {
        "question_id": first_snapshot["clarification"]["question_id"],
        "expected_revision": first_snapshot["revision"],
        "answer": "Рим",
    }

    accepted = client.post(
        first.headers["location"] + "/clarifications", json=payload,
        headers={"Idempotency-Key": key},
    )
    conflict = client.post(
        second.headers["location"] + "/clarifications", json=payload,
        headers={"Idempotency-Key": key},
    )

    assert accepted.status_code == 202
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

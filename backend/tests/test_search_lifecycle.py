from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.bff import create_app
from app.contracts import validate


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


def test_nonterminal_sse_snapshot_and_cancellation(client):
    accepted = post_search(client, "Хочу путешествие")
    location = accepted.headers["location"]
    events = client.get(location + "/events")
    assert events.status_code == 200
    assert "event: snapshot" in events.text
    assert "event: finished" not in events.text

    cancelled = client.put(location + "/cancellation", json={})
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    assert cancelled.json()["components"]["itinerary"]["error"]["code"] == "SEARCH_CANCELLED"
    repeated = client.put(location + "/cancellation", json={})
    assert repeated.status_code == 200
    assert repeated.json() == cancelled.json()
    finished = client.get(location + "/events")
    assert "event: finished" in finished.text


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

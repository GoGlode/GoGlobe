import asyncio

import pytest
from fastapi.testclient import TestClient

from app.legacy_api import create_app
from app.mock_agent import MockAgent


@pytest.fixture
def client():
    with TestClient(create_app(agent=MockAgent(0))) as client:
        yield client


def finish(client, body=None, scenario="ok"):
    response = client.post("/api/search", json=body or {"query": "Хочу в Турцию"}, headers={"X-Mock-Scenario": scenario})
    assert response.status_code == 202
    accepted = response.json()
    assert response.headers["location"] == accepted["result_url"]
    events = client.get(accepted["events_url"])
    assert "event: done" in events.text
    return accepted, client.get(accepted["result_url"]).json(), events


@pytest.mark.parametrize("scenario,count", [("ok", 2), ("partial", 1), ("empty", 0), ("needs_clarification", 0), ("error", 0)])
def test_scenarios(client, scenario, count):
    accepted, result, events = finish(client, scenario=scenario)
    assert result["status"] == scenario
    assert len(result["offers"]) == count
    assert result["is_mock"] is True
    assert events.headers["content-type"].startswith("text/event-stream")
    assert events.text.count("event: stage") == 5
    if scenario == "needs_clarification":
        assert result["clarifying_question"]
    if scenario == "error":
        assert result["error"]["code"] == "MOCK_PROVIDER_UNAVAILABLE"
    for offer in result["offers"]:
        assert offer["total_price"]["amount"] == offer["hotel"]["price"]["amount"] + offer["flight"]["price"]["amount"]
        assert offer["booking_url"] is None
        assert offer["explanation"]["sources"][0]["kind"] == "mock"
        assert client.get(f"{accepted['result_url']}/offers/{offer['id']}").json() == offer


@pytest.mark.parametrize("body", [
    {}, {"query": "  "}, {"query": "a", "params": {"travelers": 0}},
    {"query": "a", "params": {"dates": {"from": "2026-11-15", "to": "2026-11-10"}}},
    {"query": "a", "params": {"budget": {"max": -1}}},
    {"query": "a", "params": {"budget": {"max": 100, "currency": "USD"}}},
    {"query": "a", "typo": True},
])
def test_validation(client, body):
    response = client.post("/api/search", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("params,count", [
    ({"budget": {"max": 115000}}, 1),
    ({"budget": {"max": 100}}, 0),
    ({"travelers": 3}, 0), ({"destination": "Япония"}, 0),
    ({"dates": {"from": "2027-01-01", "to": "2027-01-06"}}, 0),
])
def test_explicit_params(client, params, count):
    _, result, _ = finish(client, {"query": "demo", "params": params})
    assert len(result["offers"]) == count
    assert result["status"] == ("ok" if count else "empty")


def test_replay_and_missing(client):
    accepted, _, _ = finish(client)
    replay = client.get(accepted["events_url"], headers={"Last-Event-ID": "5"})
    assert "event: stage" not in replay.text
    assert "event: done" in replay.text
    assert client.get(accepted["events_url"], headers={"Last-Event-ID": "6"}).text == ""
    assert client.get("/api/search/missing").status_code == 404
    assert client.get("/api/search/missing/events").status_code == 404
    assert client.get(accepted["result_url"] + "/offers/missing").status_code == 404
    assert client.post("/api/search", json={"query": "a"}, headers={"X-Mock-Scenario": "invalid"}).status_code == 422


def test_agent_failure():
    class FailingAgent:
        async def search(self, *args):
            raise RuntimeError("provider failure")
    with TestClient(create_app(agent=FailingAgent())) as client:
        _, result, _ = finish(client)
        assert result["status"] == "error"
        assert result["error"]["code"] == "SEARCH_FAILED"


def test_retention():
    with TestClient(create_app(agent=MockAgent(0), capacity=1)) as client:
        first, _, _ = finish(client)
        finish(client)
        assert client.get(first["result_url"]).status_code == 404


def test_processing_and_capacity():
    class WaitingAgent:
        async def search(self, *args):
            await asyncio.Event().wait()
    with TestClient(create_app(agent=WaitingAgent(), capacity=1)) as client:
        accepted = client.post("/api/search", json={"query": "demo"}).json()
        assert client.get(accepted["result_url"]).json()["status"] == "processing"
        assert client.post("/api/search", json={"query": "demo"}).status_code == 503


def test_health_openapi_cors(client):
    assert client.get("/health").json()["mode"] == "mock"
    schema = client.get("/openapi.json").json()
    assert "/api/search" in schema["paths"]
    response = client.options("/api/search", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "X-Mock-Scenario"})
    assert response.status_code == 200

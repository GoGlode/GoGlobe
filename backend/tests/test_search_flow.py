"""Сквозной сценарий на моках: тот же запрос, что на демо (docs/demo-scenario.md)."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

DEMO = (
    "Хочу на 5 дней в Турцию с 5 по 10 ноября, на двоих, бюджет до 120 000 рублей. "
    "Нужен хороший отель рядом с морем и прямой перелёт"
)


@pytest.fixture(autouse=True)
def no_delay(monkeypatch):
    monkeypatch.setattr(get_settings(), "mock_stage_delay", 0)


client = TestClient(app)


def test_demo_query_returns_offers_within_budget():
    r = client.post("/api/search", json={"query": DEMO}).json()
    assert r["status"] in ("ok", "partial")
    assert r["offers"], "демо-запрос должен давать варианты"
    assert all(o["total_price"]["amount"] <= 120000 for o in r["offers"])
    assert all(o["flight"]["direct"] for o in r["offers"])
    assert r["offers"][0]["explanation"]["why"]


def test_missing_param_asks_instead_of_guessing():
    r = client.post("/api/search", json={"query": "хочу в Турцию"}).json()
    assert r["status"] == "needs_clarification"
    assert r["clarifying_question"] and not r["offers"]


def test_impossible_budget_is_honestly_empty():
    r = client.post("/api/search", json={"query": DEMO.replace("120 000", "10 000")}).json()
    assert r["status"] == "empty" and r["warnings"]


def test_events_stream_and_result_lookup():
    r = client.post("/api/search", json={"query": DEMO, "search_id": "t1"}).json()
    body = client.get("/api/search/t1/events").text
    assert '"stage": "parsing"' in body and '"stage": "done"' in body
    assert client.get(f"/api/search/{r['search_id']}").status_code == 200

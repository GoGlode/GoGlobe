import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from app.bff import create_app


ORIGIN = "http://localhost:8000"


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "preview.sqlite3")),
                    headers={"Origin": ORIGIN}) as value:
        assert value.post("/api/v1/session", json={}).status_code == 200
        yield value


def test_preview_returns_bounded_fallback_without_creating_trip(client):
    response = client.post("/api/v1/intent/preview", json={
        "query": "Хочу в Рим из Москвы на 3 дня, нужен завтрак",
        "params": {},
    })
    assert response.status_code == 200
    body = response.json()
    assert body["parsed"]["destination"] == "Рим"
    assert body["parsed"]["duration_days"] == 3
    assert body["parsed"]["origin"] == "Москва"
    assert body["analysis_mode"] == "fallback"
    assert len(body["questions"]) <= 3
    assert "query" not in body
    assert client.get("/api/v1/trips").json()["items"] == []


@pytest.mark.parametrize("payload", [
    {"query": ""},
    {"query": "   "},
    {"query": "x" * 2001},
    {"query": "Рим", "unexpected": True},
])
def test_preview_rejects_invalid_payload(client, payload):
    assert client.post("/api/v1/intent/preview", json=payload).status_code == 422


def test_preview_requires_session_origin_and_json(tmp_path):
    with TestClient(create_app(str(tmp_path / "preview-access.sqlite3"))) as client:
        assert client.post("/api/v1/intent/preview", json={"query": "Рим"},
                           headers={"Origin": ORIGIN}).status_code == 403
        assert client.post("/api/v1/session", json={}, headers={"Origin": ORIGIN}).status_code == 200
        assert client.post("/api/v1/intent/preview", json={"query": "Рим"}).status_code == 403
        assert client.post("/api/v1/intent/preview", content="{}",
                           headers={"Origin": ORIGIN, "Content-Type": "text/plain"}).status_code == 415


def test_preview_rate_limit_is_bounded_and_retryable(client):
    for _ in range(20):
        assert client.post("/api/v1/intent/preview", json={"query": "Рим"}).status_code == 200
    response = client.post("/api/v1/intent/preview", json={"query": "Рим"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "PREVIEW_RATE_LIMITED"
    assert response.json()["error"]["retryable"] is True
    assert 1 <= int(response.headers["Retry-After"]) <= 60


def test_runtime_openapi_describes_preview(client):
    schema = client.get("/openapi.json").json()
    assert client.app.version == "0.3.1"
    operation = schema["paths"]["/intent/preview"]["post"]
    assert operation["operationId"] == "post_intent_preview"
    assert operation["x-implementation-status"] == "demo"
    assert "IntentPreviewResponse" in schema["components"]["schemas"]


def test_v031_contract_and_fixtures_are_published_and_valid(client):
    root = Path(__file__).parents[1]
    packaged = json.loads((root / "app/contracts/openapi_v0.3.1.json").read_text(encoding="utf-8"))
    documented = json.loads((root.parent / "docs/api/v0.3/GoGlobe_openapi_v0.3.1.json").read_text(encoding="utf-8"))
    assert packaged == documented == client.get("/openapi.json").json()
    fixtures = json.loads((root / "app/contracts/examples_v0.3.1.json").read_text(encoding="utf-8"))
    assert fixtures == json.loads((root.parent / "docs/api/v0.3/GoGlobe_examples_v0.3.1.json").read_text(encoding="utf-8"))
    for fixture in fixtures.values():
        document = {
            "components": packaged["components"],
            "$ref": f"#/components/schemas/{fixture['schema']}",
        }
        Draft202012Validator(document, format_checker=FormatChecker()).validate(fixture["value"])

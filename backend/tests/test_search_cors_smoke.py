"""Production CORS and complete current API flow smoke tests."""

import json

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import app

PRODUCTION = "https://goglobe-demo.vercel.app"
LOCAL = "http://localhost:5173"
DEMO = (
    "Хочу на 5 дней в Турцию в ноябре, на двоих, бюджет до 120 000 рублей. "
    "Нужен хороший отель рядом с морем и прямой перелёт"
)
client = TestClient(app)


def _preflight(origin: str):
    return client.options(
        "/api/search",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )


def _stages(body: str) -> list[str]:
    return [
        json.loads(line.removeprefix("data: "))["stage"]
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def test_cors_setting_reads_environment_and_removes_duplicates(monkeypatch):
    monkeypatch.setenv("GOGLOBE_CORS_ORIGINS", f"{LOCAL},{PRODUCTION},{LOCAL}")

    settings = Settings(_env_file=None)

    assert settings.cors_list == [LOCAL, PRODUCTION]


@pytest.mark.parametrize(
    "origins",
    [
        "",
        "*",
        "ftp://example.com",
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com?query=1",
        "https://example.com#fragment",
        "https://example.com,",
    ],
)
def test_cors_setting_rejects_invalid_origins(origins):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=origins)


@pytest.mark.parametrize("origin", [PRODUCTION, LOCAL])
def test_allowed_origins_pass_preflight(origin):
    response = _preflight(origin)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_unknown_origin_gets_no_allow_origin_header():
    response = _preflight("https://unknown.example")

    assert "access-control-allow-origin" not in response.headers


def test_production_post_has_cors_header():
    response = client.post(
        "/api/search",
        headers={"Origin": PRODUCTION},
        json={"query": DEMO, "search_id": "cors-post"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == PRODUCTION


def test_complete_search_get_sse_and_cached_flow():
    first = client.post(
        "/api/search", json={"query": DEMO, "search_id": "smoke-first"}
    )
    assert first.status_code == 200
    assert client.get("/api/search/smoke-first").json() == first.json()
    first_stages = _stages(client.get("/api/search/smoke-first/events").text)
    assert first_stages[:3] == ["parsing", "flights", "hotels"]
    assert first_stages[-1] in {"done", "error"}

    cached = client.post(
        "/api/search", json={"query": DEMO, "search_id": "smoke-cached"}
    )
    assert cached.status_code == 200
    assert cached.json()["search_id"] == "smoke-cached"
    assert client.get("/api/search/smoke-cached").json() == cached.json()
    assert _stages(client.get("/api/search/smoke-cached/events").text) == ["done"]


def test_render_health_endpoint():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}

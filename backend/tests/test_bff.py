from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.bff import IMPLEMENTED, create_app
from app.contracts import examples, specification, validate

ORIGIN = "http://localhost:8000"


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "test.sqlite3")), headers={"Origin": ORIGIN}) as client:
        yield client


def login(client):
    response = client.post("/api/v1/session", json={})
    assert response.status_code == 200
    validate("Session", response.json())
    assert "HttpOnly" in response.headers["set-cookie"]
    return response


def plan(client, key=None, body=None):
    return client.post("/api/v1/searches", json=body or examples()["plan_request"]["value"],
                       headers={"Idempotency-Key": key or str(uuid4())})


def test_core_flow_persistence_and_independent_snapshot(client):
    login(client)
    response = plan(client)
    assert response.status_code == 202
    accepted = response.json()
    validate("Accepted", accepted)
    assert response.headers["location"].endswith(accepted["search_id"])
    snapshot = client.get(response.headers["location"]).json()
    validate("Snapshot", snapshot)
    assert snapshot["state"] == "completed"
    assert snapshot["result_status"] == "partial"
    events = client.get(response.headers["location"] + "/events")
    assert "event: finished" in events.text
    base = "/api/v1/trips/" + accepted["trip_id"]
    trip = client.get(base).json()
    validate("Trip", trip)
    assert trip["price_summary"]["money"] is None
    assert trip["data_mode"] == "demo"
    saved = client.put(base + "/saved", json={})
    assert saved.status_code == 200
    validate("TripFlags", saved.json())
    assert saved.json()["expires_at"] is None
    assert client.put(base + "/saved", json={}).json() == saved.json()
    listing = client.get("/api/v1/trips?saved=true").json()
    validate("TripList", listing)
    assert len(listing["items"]) == 1
    assert listing["items"][0]["start_date"] is None
    scheduled = client.put(base + "/schedule", json={
        "expected_revision": saved.json()["revision"], "start_date": "2026-11-10",
        "end_date": "2026-11-11", "timezone": "Europe/Rome",
    })
    assert scheduled.status_code == 200
    validate("Trip", scheduled.json())
    assert [day["date"] for day in scheduled.json()["itinerary"]["days"]] == ["2026-11-10", "2026-11-11"]
    assert client.get(response.headers["location"]).json() == snapshot
    assert len(client.get("/api/v1/trips?from=2026-11-11&to=2026-11-15").json()["items"]) == 1
    assert client.get("/api/v1/trips?from=2026-11-12&to=2026-11-15").json()["items"] == []
    assert client.delete(base + "/saved").status_code == 204
    unsaved = client.get(base).json()
    assert client.delete(base + "/saved").status_code == 204
    assert client.get(base).json() == unsaved


def test_search_post_then_sse_smoke_uses_primary_v1_route(client):
    login(client)

    response = plan(client)

    assert response.status_code == 202
    events_url = response.headers["location"] + "/events"
    with client.stream("GET", events_url) as events:
        assert events.status_code == 200
        assert events.headers["content-type"].startswith("text/event-stream")
        payload = "\n".join(events.iter_lines())
    assert "event: finished" in payload
    assert "data: " in payload

    # /api/search belongs to the separate legacy application, not app.main.
    legacy = client.post("/api/search", json={"query": "Rome for two days"})
    assert legacy.status_code == 404


def test_search_cors_preflight_allows_configured_origin_and_denies_unknown(client):
    headers = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,idempotency-key",
    }

    allowed = client.options(
        "/api/v1/searches",
        headers={**headers, "Origin": ORIGIN},
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "POST" in allowed.headers["access-control-allow-methods"]
    assert "idempotency-key" in allowed.headers["access-control-allow-headers"].lower()

    denied = client.options(
        "/api/v1/searches",
        headers={**headers, "Origin": "https://unknown.example"},
    )
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


def test_cross_site_cookie_mode_is_none_and_secure(tmp_path, monkeypatch):
    monkeypatch.setenv("GOGLOBE_COOKIE_SAMESITE", "none")
    with TestClient(create_app(str(tmp_path / "cookie.sqlite3")),
                    headers={"Origin": ORIGIN}) as isolated:
        response = isolated.post("/api/v1/session", json={})
    cookie = response.headers["set-cookie"].lower()
    assert "samesite=none" in cookie
    assert "secure" in cookie
    assert "httponly" in cookie


def test_idempotency_and_ownership(client):
    login(client)
    key = str(uuid4())
    first = plan(client, key)
    assert plan(client, key).json() == first.json()
    body = deepcopy(examples()["plan_request"]["value"])
    body["query"] = "изменённый текст"
    assert plan(client, key, body).status_code == 409
    old_trip = "/api/v1/trips/" + first.json()["trip_id"]
    old_search = first.headers["location"]
    client.delete("/api/v1/session")
    assert client.get(old_trip).status_code == 403
    login(client)
    assert client.get(old_trip).status_code == 404
    assert client.get(old_search).status_code == 404
    assert plan(client, key).json()["trip_id"] != first.json()["trip_id"]


def test_restart_preserves_saved(tmp_path):
    path = str(tmp_path / "durable.sqlite3")
    with TestClient(create_app(path), headers={"Origin": ORIGIN}) as first:
        login(first)
        trip_id = plan(first).json()["trip_id"]
        first.put(f"/api/v1/trips/{trip_id}/saved", json={})
        cookies = dict(first.cookies)
    with TestClient(create_app(path), cookies=cookies, headers={"Origin": ORIGIN}) as restarted:
        assert restarted.get(f"/api/v1/trips/{trip_id}").json()["saved_at"] is not None
        assert len(restarted.get("/api/v1/trips?saved=true").json()["items"]) == 1


def test_favorites_are_saved_idempotent_and_listed(client):
    login(client)
    trip_id = plan(client).json()["trip_id"]
    base = f"/api/v1/trips/{trip_id}"

    favorite = client.put(f"/api/v1/favorites/{trip_id}", json={})
    assert favorite.status_code == 200
    validate("TripFlags", favorite.json())
    assert favorite.json()["saved_at"] is not None
    assert favorite.json()["favorite_at"] is not None
    assert favorite.json()["expires_at"] is None
    assert client.put(f"/api/v1/favorites/{trip_id}", json={}).json() == favorite.json()

    listed = client.get("/api/v1/favorites?limit=50")
    assert listed.status_code == 200
    validate("TripList", listed.json())
    assert [item["trip_id"] for item in listed.json()["items"]] == [trip_id]

    assert client.delete(f"/api/v1/favorites/{trip_id}").status_code == 204
    assert client.delete(f"/api/v1/favorites/{trip_id}").status_code == 204
    assert client.delete("/api/v1/favorites/missing").status_code == 204
    assert client.get("/api/v1/favorites").json()["items"] == []
    trip = client.get(base).json()
    assert trip["saved_at"] is not None
    assert trip["favorite_at"] is None


def test_atomic_acceptance_rollback(tmp_path, monkeypatch):
    from app import bff
    original_put = bff.put
    def failing_put(db, kind, value, owner):
        if kind == "search":
            raise RuntimeError("simulated storage failure")
        return original_put(db, kind, value, owner)
    with TestClient(create_app(str(tmp_path / "atomic.sqlite3")), headers={"Origin": ORIGIN}, raise_server_exceptions=False) as client:
        login(client)
        key = str(uuid4())
        monkeypatch.setattr(bff, "put", failing_put)
        response = plan(client, key)
        assert response.status_code == 500
        validate("ErrorResponse", response.json())
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-request-id"] == response.json()["request_id"]
        assert client.get("/api/v1/trips").json()["items"] == []
        monkeypatch.setattr(bff, "put", original_put)
        assert plan(client, key).status_code == 202
        assert len(client.get("/api/v1/trips").json()["items"]) == 1


def test_validation_and_headers(client):
    login(client)
    assert client.post("/api/v1/session", json={}, headers={"Origin": "null"}).status_code == 403
    assert client.post("/api/v1/session", content="{}", headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.post("/api/v1/searches", json={"query": "   "}, headers={"Idempotency-Key": str(uuid4())}).status_code == 422
    assert client.post("/api/v1/searches", json=examples()["plan_request"]["value"]).status_code == 422
    clarification = plan(client, body={"query": "Хочу в путешествие"})
    assert clarification.status_code == 202
    assert client.get(clarification.headers["location"]).json()["state"] == "needs_clarification"
    assert client.get("/api/v1/trips?limit=true").status_code == 422
    assert client.get("/api/v1/trips?saved=false").status_code == 422
    assert client.get("/api/v1/trips?from=2026-11-10").status_code == 422
    assert client.delete("/api/v1/trips/missing/saved").status_code == 204
    for response in [client.get("/unknown"), client.post("/api/v1/trips", json={}), client.delete("/api/v1/session")]:
        assert response.headers["x-request-id"]
        assert response.headers["cache-control"] == "no-store"
        if response.status_code != 204:
            validate("ErrorResponse", response.json())
        else:
            assert response.content == b""


STUBS = [(path, method, operation) for path, methods in specification()["paths"].items()
         for method, operation in methods.items() if operation["operationId"] not in IMPLEMENTED]


@pytest.mark.parametrize("path,method,operation", STUBS, ids=[operation["operationId"] for _, _, operation in STUBS])
def test_scaffold_is_explicit(client, path, method, operation):
    login(client)
    url = "/api/v1" + path.replace("{trip_id}", "demo").replace("{search_id}", "demo").replace("{token}", "demo")
    headers = {"Idempotency-Key": str(uuid4())}
    kwargs = {}
    if operation.get("requestBody"):
        schema = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
        kwargs["json"] = next((deepcopy(e["value"]) for e in examples().values() if e["schema"] == schema), {})
    response = client.request(method.upper(), url, headers=headers, **kwargs)
    assert response.status_code == 501, response.text
    validate("ErrorResponse", response.json())
    assert response.json()["error"]["code"] == "NOT_IMPLEMENTED"


def test_schedule_conflict_and_explicit_context(client):
    login(client)
    request = deepcopy(examples()["plan_request"]["value"])
    request["params"]["travelers"] = {"adults": 2, "children_ages": []}
    accepted = plan(client, body=request).json()
    base = "/api/v1/trips/" + accepted["trip_id"]
    trip = client.get(base).json()
    assert trip["components"]["hotels"]["missing_fields"] == ["stay"]
    assert "travelers" not in trip["components"]["flights"]["missing_fields"]
    schedule = {"expected_revision": trip["revision"], "start_date": "2026-11-10", "end_date": "2026-11-12", "timezone": "Europe/Rome"}
    assert client.put(base + "/schedule", json=schedule).status_code == 422
    schedule["end_date"] = "2026-11-11"
    assert client.put(base + "/schedule", json=schedule).status_code == 200
    repeated = client.put(base + "/schedule", json=schedule)
    assert repeated.status_code == 200
    assert repeated.json()["revision"] == trip["revision"] + 1


def test_openapi_and_pagination(client):
    login(client)
    for _ in range(3):
        assert plan(client).status_code == 202
    page = client.get("/api/v1/trips?limit=2").json()
    assert len(page["items"]) == 2
    next_page = client.get("/api/v1/trips", params={"limit": 2, "cursor": page["next_cursor"]}).json()
    assert len(next_page["items"]) == 1
    assert next_page["next_cursor"] is None
    schema = client.get("/openapi.json").json()
    assert schema["info"]["version"] == "0.3.1"
    assert sum(len(methods) for methods in schema["paths"].values()) == 28
    assert schema["servers"] == [{"url": "/api/v1"}]


@pytest.mark.parametrize("name,value", [
    ("GOGLOBE_AGENT_TIMEOUT_SECONDS", "not-a-number"),
    ("GOGLOBE_ENABLE_DOCS", "sometimes"),
])
def test_invalid_main_settings_fail_with_variable_name(monkeypatch, tmp_path, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        create_app(str(tmp_path / "invalid-settings.sqlite3"))

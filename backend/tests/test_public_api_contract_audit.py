"""Final black-box compatibility checks against the approved v0.3 contract."""
import hashlib
import json
import sqlite3
import time
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.bff import IMPLEMENTED, create_app
from app.contracts import (
    FORMAT_CHECKER,
    StrictValidator,
    examples,
    specification,
    validate,
)
from app.integrations.http import HTTPDestinationProvider, JSONEndpoint
from app.integrations.ports import DestinationCriteria, ProviderError
from app.integrations.resilience import ResiliencePolicy, ResilientIntegrationTools

ORIGIN = "http://localhost:8000"
HEADERS = {"Origin": ORIGIN}
CONTRACT_HASHES = {
    "openapi_v0.3.json": "8f2dd3f62c1010a7b46dbfa5e11b507e231d5617f3d2f316ece97ca6e576b9c4",
    "examples_v0.3.json": "761686b9d91cbe2a94408f7ee9b291b40100ed32325e3bda085b191212f9666f",
}


def operation(operation_id):
    return next(
        value for methods in specification()["paths"].values() for value in methods.values()
        if value["operationId"] == operation_id
    )


def assert_contract_response(response, operation_id, status=None, mime="application/json"):
    status = str(status or response.status_code)
    response_spec = operation(operation_id)["responses"][status]
    for name, header in response_spec.get("headers", {}).items():
        assert name.lower() in response.headers
        StrictValidator(header["schema"], format_checker=FORMAT_CHECKER).validate(
            response.headers[name]
        )
    if response.status_code == 204:
        assert response.content == b""
        return
    schema = response_spec["content"][mime]["schema"]
    name = schema["$ref"].split("/")[-1]
    validate(name, response.json())


def login(client):
    response = client.post("/api/v1/session", json={})
    assert response.status_code == 200
    assert_contract_response(response, "post_session")
    assert client.cookies.get("gg_session")
    return response


def search(client, body=None, key=None):
    return client.post(
        "/api/v1/searches",
        json=deepcopy(body or examples()["plan_request"]["value"]),
        headers={"Idempotency-Key": key or str(uuid4())},
    )


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "contract.sqlite3")), headers=HEADERS,
                    raise_server_exceptions=False) as value:
        yield value


def test_approved_contract_hashes_are_unchanged():
    root = Path(__file__).parents[1]
    manifest = json.loads((root.parent / "docs/api/v0.3/manifest.json").read_text(encoding="utf-8"))
    documented_names = {
        "openapi_v0.3.json": "GoGlobe_openapi_v0.3.json",
        "examples_v0.3.json": "GoGlobe_examples_v0.3.json",
    }
    for name, expected in CONTRACT_HASHES.items():
        actual = hashlib.sha256((root / "app/contracts" / name).read_bytes()).hexdigest()
        assert actual == expected == manifest["sha256"][documented_names[name]]


def test_runtime_openapi_has_only_explicit_demo_scaffold_delta(tmp_path):
    approved = specification()
    runtime = create_app(str(tmp_path / "openapi.sqlite3")).openapi()
    assert approved["info"]["version"] == "0.3.0"
    assert runtime["info"]["version"] == "0.3.1"
    assert set(approved["paths"]) <= set(runtime["paths"])
    assert set(runtime["paths"]) - set(approved["paths"]) == {"/intent/preview"}
    assert runtime["paths"]["/intent/preview"]["post"]["operationId"] == "post_intent_preview"
    for schema in ("IntentPreviewRequest", "IntentPreviewParsed",
                   "IntentPreviewQuestion", "IntentPreviewResponse"):
        assert schema in runtime["components"]["schemas"]
    for path, methods in approved["paths"].items():
        for method, approved_operation in methods.items():
            operation = runtime["paths"][path][method]
            implemented = approved_operation["operationId"] in IMPLEMENTED
            assert operation["x-implementation-status"] == ("demo" if implemented else "scaffold")
            assert ("501" in operation["responses"]) is not implemented
    with TestClient(create_app(str(tmp_path / "openapi-http.sqlite3"))) as client:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert response.json() == runtime


def test_all_implemented_successes_validate_against_approved_schemas(client):
    login(client)
    accepted_response = search(client)
    assert accepted_response.status_code == 202
    assert_contract_response(accepted_response, "post_searches")
    accepted = accepted_response.json()

    snapshot = client.get("/api/v1/searches/" + accepted["search_id"])
    assert_contract_response(snapshot, "get_searches_search_id")
    trip_url = "/api/v1/trips/" + accepted["trip_id"]
    trip = client.get(trip_url)
    assert_contract_response(trip, "get_trips_trip_id")
    saved = client.put(trip_url + "/saved", json={})
    assert_contract_response(saved, "put_trips_trip_id_saved")
    listed = client.get("/api/v1/trips?saved=true")
    assert_contract_response(listed, "get_trips")
    favorite = client.put("/api/v1/favorites/" + accepted["trip_id"], json={})
    assert_contract_response(favorite, "put_favorites_trip_id")
    favorites = client.get("/api/v1/favorites")
    assert_contract_response(favorites, "get_favorites")
    unfavorite = client.delete("/api/v1/favorites/" + accepted["trip_id"])
    assert_contract_response(unfavorite, "delete_favorites_trip_id")
    schedule = client.put(trip_url + "/schedule", json={
        "expected_revision": favorite.json()["revision"] + 1,
        "start_date": "2026-11-10", "end_date": "2026-11-11",
        "timezone": "Europe/Rome",
    })
    assert_contract_response(schedule, "put_trips_trip_id_schedule")
    removed = client.delete(trip_url + "/saved")
    assert_contract_response(removed, "delete_trips_trip_id_saved")
    logout = client.delete("/api/v1/session")
    assert_contract_response(logout, "delete_session")


def test_headers_cookie_origin_and_idempotency_are_uniform(client):
    missing_origin = TestClient(client.app, raise_server_exceptions=False)
    try:
        for method, path, body in [
            ("POST", "/api/v1/session", {}),
            ("DELETE", "/api/v1/session", None),
            ("PUT", "/api/v1/trips/t_x/saved", {}),
            ("DELETE", "/api/v1/trips/t_x/saved", None),
        ]:
            response = missing_origin.request(method, path, json=body)
            assert response.status_code == 403
            validate("ErrorResponse", response.json())
    finally:
        missing_origin.close()

    session = login(client)
    assert "HttpOnly" in session.headers["set-cookie"]
    for bad_key in (None, "", "not-a-uuid", "x" * 37):
        headers = {} if bad_key is None else {"Idempotency-Key": bad_key}
        response = client.post("/api/v1/searches", json=examples()["plan_request"]["value"],
                               headers=headers)
        assert response.status_code == 422
        validate("ErrorResponse", response.json())
    key = str(uuid4())
    first = search(client, key=key)
    replay = search(client, key=key)
    assert first.status_code == replay.status_code == 202
    assert first.json() == replay.json()
    for response in (first, replay):
        assert response.headers["x-request-id"]
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["location"].endswith(response.json()["search_id"])


def _approved_body(item):
    if not item.get("requestBody"):
        return None
    schema_name = item["requestBody"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
    body = next((value["value"] for value in examples().values()
                 if value["schema"] == schema_name), {})
    validate(schema_name, body)
    return deepcopy(body)


def _operation_url(path):
    return "/api/v1" + path.replace("{search_id}", "s_demo_1").replace(
        "{trip_id}", "t_demo_1").replace("{token}", "demo-token")


def test_origin_idempotency_and_cookie_requirements_cover_every_operation(tmp_path):
    spec = specification()
    with TestClient(create_app(str(tmp_path / "uniform-requirements.sqlite3")),
                    raise_server_exceptions=False) as anonymous:
        # Every operation that declares Origin rejects its absence identically,
        # before parsing bodies or consulting authentication state.
        for path, methods in spec["paths"].items():
            for method, item in methods.items():
                parameters = item.get("parameters", [])
                if any(value["name"] == "Origin" for value in parameters):
                    response = anonymous.request(method.upper(), _operation_url(path))
                    assert response.status_code == 403, item["operationId"]
                    validate("ErrorResponse", response.json())

        # With a valid Origin/body, every cookie-secured operation denies an
        # anonymous caller with the same public envelope.
        for path, methods in spec["paths"].items():
            for method, item in methods.items():
                security = item.get("security", spec["security"])
                if not security:
                    continue
                headers = {"Origin": ORIGIN, "Idempotency-Key": str(uuid4())}
                response = anonymous.request(
                    method.upper(), _operation_url(path), json=_approved_body(item), headers=headers,
                )
                assert response.status_code == 403, (item["operationId"], response.text)
                validate("ErrorResponse", response.json())

        session = anonymous.post("/api/v1/session", json={}, headers=HEADERS)
        assert session.status_code == 200
        assert_contract_response(session, "post_session")
        for path, methods in spec["paths"].items():
            for method, item in methods.items():
                parameters = item.get("parameters", [])
                if not any(value["name"] == "Idempotency-Key" for value in parameters):
                    continue
                response = anonymous.request(
                    method.upper(), _operation_url(path), json=_approved_body(item),
                    headers={"Origin": ORIGIN},
                )
                assert response.status_code == 422, item["operationId"]
                validate("ErrorResponse", response.json())


@pytest.mark.parametrize("mutation", [
    lambda body: body.update(unexpected=True),
    lambda body: body.pop("query"),
    lambda body: body.update(query=42),
    lambda body: body.update(query="x" * 2001),
    lambda body: body["params"].update(duration_days=0),
    lambda body: body["params"].update(duration_days=31),
    lambda body: body["params"].update(duration_days=2.0),
    lambda body: body["params"].update(travelers={"adults": 1, "children_ages": [0] * 9}),
    lambda body: body["params"].update(wishes=["near_sea", "near_sea"]),
])
def test_invalid_body_boundaries_are_controlled_4xx(client, mutation):
    login(client)
    body = deepcopy(examples()["plan_request"]["value"])
    mutation(body)
    response = search(client, body=body)
    assert 400 <= response.status_code < 500
    validate("ErrorResponse", response.json())


def test_uuid_dates_timezone_money_and_revision_boundaries(client):
    login(client)
    for amount in (1, 9_000_000_000_000):
        body = deepcopy(examples()["plan_request"]["value"])
        body["params"]["budget"] = {"amount_minor": amount, "currency": "RUB"}
        assert search(client, body=body).status_code == 202
    for amount in (0, 9_000_000_000_001, 1.0, True):
        body = deepcopy(examples()["plan_request"]["value"])
        body["params"]["budget"] = {"amount_minor": amount, "currency": "RUB"}
        assert search(client, body=body).status_code == 422

    accepted = search(client).json()
    trip_url = "/api/v1/trips/" + accepted["trip_id"]
    revision = client.get(trip_url).json()["revision"]
    base = {"expected_revision": revision, "start_date": "2026-11-10",
            "end_date": "2026-11-11", "timezone": "Europe/Rome"}
    for field, value in [
        ("start_date", "2026-02-30"), ("start_date", "2026-1-01"),
        ("timezone", "Invalid/Zone"), ("expected_revision", 0),
        ("expected_revision", 1.0),
    ]:
        request = {**base, field: value}
        response = client.put(trip_url + "/schedule", json=request)
        assert response.status_code == 422
        validate("ErrorResponse", response.json())
    conflict = client.put(trip_url + "/schedule", json={**base, "expected_revision": 2**63})
    assert conflict.status_code == 409
    validate("ErrorResponse", conflict.json())


def test_501_is_exclusive_to_declared_scaffolds(client):
    login(client)
    runtime = client.app.openapi()
    statuses = {
        item["operationId"]: item["x-implementation-status"]
        for methods in runtime["paths"].values() for item in methods.values()
    }
    assert {name for name, status in statuses.items() if status == "demo"} == IMPLEMENTED
    for methods in runtime["paths"].values():
        for item in methods.values():
            assert ("501" in item["responses"]) == (item["operationId"] not in IMPLEMENTED)
            if item["operationId"] not in IMPLEMENTED:
                assert item["summary"].startswith("[ЗАГЛУШКА]")


def test_sse_wire_format_schema_and_disconnect_cleanup(client):
    login(client)
    accepted = search(client).json()
    url = "/api/v1/searches/" + accepted["search_id"] + "/events"
    with client.stream("GET", url) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-store"
        iterator = response.iter_lines()
        lines = [next(iterator) for _ in range(4)]
    assert lines[0].startswith("id: ")
    assert int(lines[0][4:]) >= 1
    assert lines[1] == "event: finished"
    assert lines[2].startswith("data: ")
    validate("Snapshot", json.loads(lines[2][6:]))
    assert lines[3] == ""
    # Closing a streaming context is the client-disconnect path. It must not
    # alter the completed snapshot or leave the application unusable.
    assert client.get("/api/v1/searches/" + accepted["search_id"]).status_code == 200
    assert client.get("/health").status_code == 200


def test_error_envelope_is_stable_across_agent_adapter_resilience_and_database(tmp_path):
    class RaisingAgent:
        def __init__(self, exc):
            self.exc = exc

        async def plan(self, context):
            raise self.exc

    responses = []
    snapshots = []

    def terminal(test_client, response):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            snapshot = test_client.get(response.headers["location"]).json()
            if snapshot["state"] == "failed":
                return snapshot
            time.sleep(0.01)
        raise AssertionError("background failure did not become terminal")

    for index, exc in enumerate((RuntimeError("agent"), ProviderError("PROVIDER_TRANSPORT_ERROR"))):
        with TestClient(create_app(str(tmp_path / f"layer-{index}.sqlite3"), agent=RaisingAgent(exc)),
                        headers=HEADERS, raise_server_exceptions=False) as test_client:
            login(test_client)
            response = search(test_client)
            responses.append(response)
            snapshots.append(terminal(test_client, response))

    class ResilienceAgent:
        async def plan(self, context):
            result = await context.tools.destinations(DestinationCriteria(
                "Рим", context.deadline_at,
            ))
            assert result.status == "unavailable"
            raise RuntimeError("resilience unavailable")

    async def failed(request):
        raise httpx.ConnectError("offline", request=request)

    endpoint = JSONEndpoint("https://provider.example/destinations", transport=httpx.MockTransport(failed))
    tools = ResilientIntegrationTools(
        destinations=HTTPDestinationProvider(endpoint),
        policy=ResiliencePolicy(max_attempts=1, backoff_seconds=0),
    )
    with TestClient(create_app(str(tmp_path / "resilience.sqlite3"), agent=ResilienceAgent(), tools=tools),
                    headers=HEADERS, raise_server_exceptions=False) as test_client:
        login(test_client)
        response = search(test_client)
        responses.append(response)
        snapshots.append(terminal(test_client, response))

    path = str(tmp_path / "locked.sqlite3")
    with TestClient(create_app(path), headers=HEADERS, raise_server_exceptions=False) as test_client:
        login(test_client)
        with sqlite3.connect(path) as locker:
            locker.execute("BEGIN IMMEDIATE")
            responses.append(test_client.get("/api/v1/trips"))

    assert [response.status_code for response in responses] == [202, 202, 202, 200]
    for response, snapshot in zip(responses[:3], snapshots):
        assert set(response.json()) == {
            "search_id", "trip_id", "state", "revision", "expires_at",
        }
        assert set(snapshot["error"]) == {
            "code", "message", "retryable", "details",
        }
    validate("TripList", responses[3].json())


def test_v03_request_fixtures_need_no_new_required_fields(client):
    login(client)
    # The approved PlanRequest fixture is accepted unchanged.
    assert search(client, examples()["plan_request"]["value"]).status_code == 202
    # Every request-body scaffold accepts the approved fixture for its schema
    # and reaches 501, proving runtime validation added no private requirement.
    for path, methods in specification()["paths"].items():
        for method, item in methods.items():
            if item["operationId"] in IMPLEMENTED or not item.get("requestBody"):
                continue
            fixture = _approved_body(item)
            url = _operation_url(path)
            headers = {"Idempotency-Key": str(uuid4())}
            response = client.request(method.upper(), url, json=deepcopy(fixture), headers=headers)
            assert response.status_code == 501, (item["operationId"], response.text)
            validate("ErrorResponse", response.json())

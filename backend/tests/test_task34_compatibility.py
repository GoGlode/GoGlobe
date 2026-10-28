"""Current task 3 + task 4 compatibility through the real BFF pipeline."""
import asyncio
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Lock, Thread
import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.bff import create_app
from app.contracts import examples, validate
from app.integrations.http import (
    HTTPDestinationProvider,
    HTTPFlightProvider,
    HTTPHotelProvider,
    JSONEndpoint,
)
from app.integrations.ports import DestinationCriteria, FlightCriteria, HotelCriteria, walk
from app.integrations.resilience import ResiliencePolicy, ResilientIntegrationTools
from app.planning import AgentPlan


ORIGIN = {"Origin": "http://localhost:8000"}
PROVIDERS = {
    "hotels": HTTPHotelProvider,
    "flights": HTTPFlightProvider,
    "destinations": HTTPDestinationProvider,
}


def _envelope(kind, request):
    now = datetime.now(timezone.utc)
    checked_at = now.isoformat().replace("+00:00", "Z")
    valid_until = (now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    source_id = f"live_{kind}"
    source = {
        "source_id": source_id,
        "name": f"Local {kind} gateway",
        "url": "https://provider.example/result",
        "checked_at": checked_at,
        "kind": "provider" if kind != "destinations" else "catalog",
    }
    if kind == "destinations":
        destination = deepcopy(examples()["trip_relative"]["value"]["destination"])
        place = {
            "place_id": "local_rome",
            "name": destination["name"],
            "latitude": None,
            "longitude": None,
            "timezone": destination["timezone"],
            "verification": "unknown",
            "source_ids": [source_id],
        }
        items = [{"destination": destination, "place": place, "source_ids": [source_id]}]
        context = {"query": request["query"]}
    else:
        fixture = deepcopy(examples()["hotel_offers" if kind == "hotels" else "flight_offers"]["value"])
        items = fixture["items"]
        for node in walk(items):
            if "source_ids" in node:
                node["source_ids"] = [source_id if value == "src_demo_1" else value for value in node["source_ids"]]
            if "checked_at" in node:
                node["checked_at"] = checked_at
            if node.get("valid_until") is not None:
                node["valid_until"] = valid_until
        fields = PROVIDERS[kind].context_fields
        context = {field: request[field] for field in fields}
    return {
        "status": "ok",
        "items": items,
        "sources": [source],
        "warnings": [],
        "data_mode": "live",
        "context": context,
    }


class GatewayState:
    def __init__(self):
        self.calls = {kind: 0 for kind in PROVIDERS}
        self.requests = {kind: [] for kind in PROVIDERS}
        self.responses = {kind: [] for kind in PROVIDERS}
        self.delays = {kind: 0.0 for kind in PROVIDERS}
        self.lock = Lock()

    def configure(self, kind, *statuses, delay=0.0):
        with self.lock:
            self.responses[kind] = list(statuses)
            self.delays[kind] = delay

    def next(self, kind, request):
        with self.lock:
            self.calls[kind] += 1
            self.requests[kind].append(request)
            status = self.responses[kind].pop(0) if self.responses[kind] else 200
            delay = self.delays[kind]
        return status, delay


@contextmanager
def local_gateway():
    state = GatewayState()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            kind = self.path.lstrip("/")
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            status, delay = state.next(kind, request)
            if delay:
                time.sleep(delay)
            body = json.dumps(_envelope(kind, request)).encode() if status == 200 else b"private upstream failure"
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _tools(port, policy):
    providers = {
        kind: provider(JSONEndpoint(
            f"http://127.0.0.1:{port}/{kind}", allow_local_http=True
        ))
        for kind, provider in PROVIDERS.items()
    }
    return ResilientIntegrationTools(**providers, policy=policy)


class ToolCallingAgent:
    def __init__(self, *, require_all=True):
        self.require_all = require_all
        self.results = []

    async def plan(self, context):
        travelers = {"adults": 2, "children_ages": []}
        results = await asyncio.gather(
            context.tools.hotels(HotelCriteria(
                "Рим", {"check_in": "2026-11-10", "check_out": "2026-11-11"},
                travelers, None, [], context.deadline_at,
            )),
            context.tools.flights(FlightCriteria(
                "Рим", "Москва", {"outbound_date": "2026-11-10", "return_date": "2026-11-11"},
                travelers, None, [], context.deadline_at,
            )),
            context.tools.destinations(DestinationCriteria("Рим", context.deadline_at)),
        )
        self.results.append(results)
        if self.require_all and any(result.status != "ok" or not result.items for result in results):
            raise RuntimeError("required provider result unavailable")
        # Build the relative itinerary fixture only after the explicit tool calls.
        # DemoPlanner is intentionally not used as evidence for this pipeline.
        fixture = deepcopy(examples()["trip_relative"]["value"])
        destination = results[2]
        if destination.status != "ok" or not destination.items:
            raise RuntimeError("required destination unavailable")
        warnings = [warning for result in results for warning in result.warnings]
        return AgentPlan(
            destination.items[0]["destination"], 2, fixture["itinerary"],
            destination.sources, warnings, "live",
        )


def _search(client):
    return client.post(
        "/api/v1/searches",
        json=examples()["plan_request"]["value"],
        headers={"Idempotency-Key": str(uuid4())},
    )


def _login(client):
    assert client.post("/api/v1/session", json={}).status_code == 200


def _wait_terminal(client, response, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = client.get(response.headers["location"]).json()
        if snapshot["state"] in {"completed", "failed", "cancelled"}:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("search did not become terminal")


def test_live_pipeline_normalizes_persists_retries_and_uses_cache(tmp_path):
    with local_gateway() as (gateway, port):
        gateway.configure("hotels", 503, 200)
        agent = ToolCallingAgent()
        tools = _tools(port, ResiliencePolicy(backoff_seconds=0, cache_ttl_seconds=60))
        with TestClient(create_app(str(tmp_path / "task34-live.sqlite3"), agent=agent, tools=tools),
                        headers=ORIGIN) as client:
            _login(client)
            first = _search(client)
            assert first.status_code == 202, first.text
            snapshot = _wait_terminal(client, first)
            trip = client.get("/api/v1/trips/" + first.json()["trip_id"]).json()
            validate("Snapshot", snapshot)
            validate("Trip", trip)
            assert snapshot["data_mode"] == trip["data_mode"] == "live"
            assert trip["sources"][0]["source_id"] == "live_destinations"
            assert trip["sources"][0]["url"] == "https://provider.example/result"

            hotel, flight, destination = agent.results[0]
            assert all(result.status == "ok" and result.data_mode == "live" for result in (hotel, flight, destination))
            assert hotel.items[0]["total_price"]["money"] == {"amount_minor": 1500000, "currency": "RUB"}
            assert hotel.items[0]["booking_url"] is None
            assert flight.items[0]["booking_url"] is None
            assert gateway.calls == {"hotels": 2, "flights": 1, "destinations": 1}

            second = _search(client)
            assert second.status_code == 202, second.text
            second_snapshot = _wait_terminal(client, second)
            assert gateway.calls == {"hotels": 2, "flights": 1, "destinations": 1}
            assert all(any(warning["code"] == "CACHE_HIT" for warning in result.warnings)
                       for result in agent.results[1])
            assert second_snapshot["data_mode"] == "live"


def test_permanent_http_error_is_not_retried_or_saved(tmp_path):
    with local_gateway() as (gateway, port):
        gateway.configure("hotels", 401)
        agent = ToolCallingAgent()
        tools = _tools(port, ResiliencePolicy(backoff_seconds=0, max_attempts=3))
        with TestClient(create_app(str(tmp_path / "task34-auth.sqlite3"), agent=agent, tools=tools),
                        headers=ORIGIN) as client:
            _login(client)
            response = _search(client)
            assert response.status_code == 202
            snapshot = _wait_terminal(client, response)
            assert snapshot["state"] == "failed"
            assert snapshot["error"]["code"] == "AGENT_UNAVAILABLE"
            assert gateway.calls["hotels"] == 1
            failed_hotel = agent.results[0][0]
            assert failed_hotel.data_mode == "live"
            assert {warning["code"] for warning in failed_hotel.warnings} == {"PROVIDER_AUTH_ERROR"}


def test_explicit_demo_fallback_reaches_snapshot_and_trip_without_leaking(tmp_path):
    with local_gateway() as (gateway, port):
        for kind in PROVIDERS:
            gateway.configure(kind, 503)
        agent = ToolCallingAgent()
        tools = _tools(port, ResiliencePolicy(
            backoff_seconds=0, max_attempts=1, demo_fallback=True, cache_ttl_seconds=60,
        ))
        with TestClient(create_app(str(tmp_path / "task34-fallback.sqlite3"), agent=agent, tools=tools),
                        headers=ORIGIN) as client:
            _login(client)
            fallback = _search(client)
            assert fallback.status_code == 202, fallback.text
            fallback_snapshot = _wait_terminal(client, fallback)
            fallback_trip = client.get("/api/v1/trips/" + fallback.json()["trip_id"]).json()
            assert fallback_snapshot["data_mode"] == fallback_trip["data_mode"] == "demo"
            assert "DEMO_FALLBACK" in {warning["code"] for warning in fallback_snapshot["warnings"]}
            assert all(result.data_mode == "demo" for result in agent.results[0])
            assert agent.results[0][0].items[0]["availability"] == "unknown"
            assert agent.results[0][0].items[0]["booking_url"] is None

            live = _search(client)
            assert live.status_code == 202, live.text
            live_snapshot = _wait_terminal(client, live)
            live_trip = client.get("/api/v1/trips/" + live.json()["trip_id"]).json()
            assert live_snapshot["data_mode"] == live_trip["data_mode"] == "live"
            assert not {"DEMO_FALLBACK", "DEMO_DATA"} & {
                warning["code"] for warning in live_snapshot["warnings"]
            }
            assert all(result.data_mode == "live" for result in agent.results[1])
            assert gateway.calls == {kind: 2 for kind in PROVIDERS}


def test_total_deadline_cancels_http_pipeline_without_partial_write(tmp_path):
    with local_gateway() as (gateway, port):
        gateway.configure("hotels", delay=1.0)
        agent = ToolCallingAgent()
        tools = _tools(port, ResiliencePolicy(
            attempt_timeout_seconds=1, max_attempts=3, backoff_seconds=0,
        ))
        with TestClient(create_app(
            str(tmp_path / "task34-deadline.sqlite3"), agent=agent, tools=tools, agent_timeout=0.3,
        ), headers=ORIGIN) as client:
            _login(client)
            started = time.monotonic()
            response = _search(client)
            elapsed = time.monotonic() - started
            assert response.status_code == 202
            assert elapsed < 0.8
            snapshot = _wait_terminal(client, response)
            assert snapshot["error"]["code"] == "SEARCH_TIMEOUT"
            assert gateway.calls["hotels"] == 1

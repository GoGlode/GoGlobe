"""Regression tests from the second task-3 audit."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import time
from uuid import uuid4

import httpx
import pytest
from jsonschema import ValidationError
from fastapi.testclient import TestClient

from app.bff import create_app
from app.contracts import examples, validate
from app.integrations.http import HTTPHotelProvider, JSONEndpoint
from app.integrations.ports import ToolResult
from app.integrations.service import IntegrationTools
from app.planning import AgentPlan, DemoPlanner
from tests.test_adapters import PROVIDERS, criteria, envelope


@pytest.mark.parametrize("url", ["https://example.com:bad/hotel", "https://example.com:99999/hotel"])
def test_bad_booking_port_only_drops_link(url):
    data = examples()["hotel_offers"]["value"]
    data["items"][0]["booking_url"] = url
    class Provider:
        data_mode = "demo"
        async def search(self, value):
            return ToolResult("ok", data["items"], data["sources"], [], "demo")
    async def run():
        result = await IntegrationTools(hotels=Provider(), allowed_booking_hosts={"example.com"}).hotels(criteria("hotels"))
        assert result.status == "ok"
        assert result.items[0]["booking_url"] is None
        assert result.warnings[0]["code"] == "BOOKING_URL_NOT_ALLOWED"
    asyncio.run(run())


def test_return_flight_cannot_start_before_outbound_lands():
    data = examples()["flight_offers"]["value"]
    segment = data["items"][0]["inbound_segments"][0]
    segment.update(departure_at="2026-11-10T06:00:00Z", arrival_at="2026-11-10T10:00:00Z")
    with pytest.raises(ValueError, match="return|Return"):
        ToolResult("ok", data["items"], data["sources"], [], "demo").validate_for("flights")


def test_quoted_nightly_price_requires_hotel_coverage():
    data = examples()["hotel_offers"]["value"]
    data["items"][0]["nightly_price"].update(coverage=["flights"], exclusions=[])
    with pytest.raises(ValueError, match="coverage|Nightly"):
        ToolResult("ok", data["items"], data["sources"], [], "demo").validate_for("hotels")


@pytest.mark.parametrize("timestamp", ["2026-10-20T09:00:00", "2026-10-20 09:00:00Z", "not-a-date"])
def test_source_requires_rfc3339_timestamp(timestamp):
    source = deepcopy(examples()["hotel_offers"]["value"]["sources"][0])
    source["checked_at"] = timestamp
    with pytest.raises(ValidationError):
        validate("Source", source)


@pytest.mark.parametrize("url", ["https://", "https://bad host/path", "https://example.com/%XX"])
def test_source_url_is_actually_validated(url):
    source = deepcopy(examples()["hotel_offers"]["value"]["sources"][0])
    source["url"] = url
    with pytest.raises(ValidationError):
        validate("Source", source)


def test_request_context_is_frozen_while_provider_waits():
    data = examples()["hotel_offers"]["value"]
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        class Provider:
            data_mode = "demo"
            async def search(self, value):
                started.set()
                await release.wait()
                return ToolResult("ok", data["items"], data["sources"], [], "demo")
        value = criteria("hotels")
        task = asyncio.create_task(IntegrationTools(hotels=Provider()).hotels(value))
        await started.wait()
        value.stay["check_in"] = "2026-11-09"
        release.set()
        result = await task
        assert result.status == "ok"
    asyncio.run(run())


@pytest.mark.parametrize("kind", PROVIDERS)
@pytest.mark.parametrize("fault", ["invalid_utf8", "deep_json", "wrong_context_type"])
def test_http_corrupt_data_is_isolated(kind, fault):
    body = envelope(kind)
    def handler(request):
        if fault == "invalid_utf8":
            return httpx.Response(200, content=b'\xff', headers={"content-type": "application/json"})
        if fault == "deep_json":
            return httpx.Response(200, content=b'{"x":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}',
                                  headers={"content-type": "application/json"})
        body["context"] = []
        return httpx.Response(200, json=body)
    async def run():
        endpoint = JSONEndpoint("https://provider.test/" + kind, transport=httpx.MockTransport(handler))
        result = await getattr(IntegrationTools(**{kind: PROVIDERS[kind](endpoint, data_mode="demo")}), kind)(criteria(kind))
        assert result.status == "unavailable" and result.items == []
        assert result.warnings[0]["code"] == "PROVIDER_INVALID_RESPONSE"
    asyncio.run(run())


@pytest.mark.parametrize("failure", ["deadline", "malformed", "body_limit"])
def test_http_stream_closes_on_failure(failure):
    closed = []
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            if failure == "deadline":
                yield b'{'
                await asyncio.sleep(10)
            elif failure == "body_limit":
                yield b'x' * (2 * 1024 * 1024 + 1)
            else:
                yield b'not json'
        async def aclose(self):
            closed.append(True)
    async def run():
        endpoint = JSONEndpoint("https://provider.test/hotels", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=Stream(), headers={"content-type": "application/json"})))
        value = replace(criteria("hotels"), deadline_at=datetime.now(timezone.utc) + timedelta(seconds=0.1))
        result = await IntegrationTools(hotels=HTTPHotelProvider(endpoint, data_mode="demo")).hotels(value)
        assert result.status == "unavailable"
        assert result.warnings[0]["code"] == {"deadline": "PROVIDER_TIMEOUT", "malformed": "PROVIDER_INVALID_RESPONSE",
                                             "body_limit": "PROVIDER_RESPONSE_TOO_LARGE"}[failure]
    asyncio.run(run())
    assert closed == [True]


def test_parallel_http_requests_keep_context_and_input_independent():
    body = envelope("hotels")
    async def run():
        active = 0
        peak = 0
        requests = []
        async def handler(request):
            nonlocal active, peak
            payload = json.loads(request.content)
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.01)
                requests.append(payload)
                value = deepcopy(body)
                value["context"] = {key: payload[key] for key in HTTPHotelProvider.context_fields}
                return httpx.Response(200, json=value)
            finally:
                active -= 1
        endpoint = JSONEndpoint("https://provider.test/hotels", transport=httpx.MockTransport(handler))
        tools = IntegrationTools(hotels=HTTPHotelProvider(endpoint, data_mode="demo"))
        values = [replace(criteria("hotels"), travelers={"adults": i % 8 + 1, "children_ages": []}) for i in range(32)]
        results = await asyncio.gather(*(tools.hotels(value) for value in values))
        assert len(requests) == 32
        assert all(result.status == "ok" for result in results)
        assert 1 < peak <= 8
        results[0].items.clear()
        assert all(result.items for result in results[1:])
        assert all(value.stay["check_in"] == "2026-11-10" for value in values)
    asyncio.run(run())


def test_external_cancellation_propagates_and_releases_provider_slot():
    async def run():
        started = asyncio.Event()
        cancelled = []
        class Provider:
            data_mode = "live"
            async def search(self, value):
                started.set()
                try:
                    await asyncio.sleep(10)
                finally:
                    cancelled.append(True)
        tools = IntegrationTools(hotels=Provider())
        task = asyncio.create_task(tools.hotels(criteria("hotels")))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled == [True]
        assert tools._slots._value == 8
    asyncio.run(run())


def test_lowercase_rfc3339_is_not_discarded():
    data = examples()["hotel_offers"]["value"]
    data["sources"][0]["checked_at"] = data["sources"][0]["checked_at"].lower()
    for name in ("total_price", "nightly_price"):
        data["items"][0][name]["checked_at"] = data["items"][0][name]["checked_at"].lower()
        data["items"][0][name]["valid_until"] = data["items"][0][name]["valid_until"].lower()
    class Provider:
        data_mode = "demo"
        async def search(self, value):
            return ToolResult("ok", data["items"], data["sources"], [], "demo")
    async def run():
        result = await IntegrationTools(hotels=Provider()).hotels(criteria("hotels"))
        assert result.status == "ok"
    asyncio.run(run())


@pytest.mark.parametrize("failed_kind", [None, "hotels", "flights", "destinations"])
def test_bff_gateway_failure_save_and_restart(tmp_path, failed_kind):
    responses = {kind: envelope(kind) for kind in PROVIDERS}
    failures = {failed_kind} if failed_kind else set()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            kind = self.path.lstrip("/")
            payload = b'private-upstream-body' if kind in failures else json.dumps(responses[kind]).encode()
            self.send_response(503 if kind in failures else 200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    tools = IntegrationTools(**{kind: provider(JSONEndpoint(
        f"http://127.0.0.1:{server.server_port}/{kind}", allow_local_http=True), data_mode="demo")
        for kind, provider in PROVIDERS.items()})
    class Agent:
        async def plan(self, context):
            results = await asyncio.gather(*(getattr(context.tools, kind)(
                replace(criteria(kind), deadline_at=context.deadline_at)) for kind in PROVIDERS))
            hotels, flights, destination = results
            if destination.status != "ok":
                raise RuntimeError("Required destination not available")
            plan = await DemoPlanner().plan(context)
            warnings = hotels.warnings + flights.warnings + destination.warnings
            return AgentPlan(destination.items[0]["destination"], plan.duration_days, plan.itinerary,
                             destination.sources, warnings, "demo")
    db_path = str(tmp_path / "gateway.sqlite3")
    try:
        with TestClient(create_app(db_path, agent=Agent(), tools=tools),
                        headers={"Origin": "http://localhost:8000"}) as client:
            assert client.post("/api/v1/session", json={}).status_code == 200
            key = {"Idempotency-Key": str(uuid4())}
            response = client.post("/api/v1/searches", json=examples()["plan_request"]["value"], headers=key)
            if failed_kind == "destinations":
                assert response.status_code == 202
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    failed = client.get(response.headers["location"]).json()
                    if failed["state"] == "failed":
                        break
                    time.sleep(0.01)
                assert failed["error"]["code"] == "AGENT_UNAVAILABLE"
                failures.clear()
                response = client.post(
                    "/api/v1/searches", json=examples()["plan_request"]["value"],
                    headers={"Idempotency-Key": str(uuid4())},
                )
            assert response.status_code == 202, response.text
            accepted = response.json()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                snapshot = client.get(response.headers["location"]).json()
                if snapshot["state"] == "completed":
                    break
                time.sleep(0.01)
            assert snapshot["state"] == "completed"
            trip_url = "/api/v1/trips/" + accepted["trip_id"]
            trip = client.get(trip_url).json()
            assert trip["sources"][0]["source_id"] == "demo_rome_catalog"
            assert trip["price_summary"]["money"] is None
            if failed_kind in {"hotels", "flights"}:
                assert "PROVIDER_HTTP_ERROR" in {warning["code"] for warning in snapshot["warnings"]}
            assert "private-upstream-body" not in json.dumps(snapshot)
            assert client.put(trip_url + "/saved", json={}).status_code == 200
            cookies = dict(client.cookies)
        with TestClient(create_app(db_path), cookies=cookies) as restarted:
            persisted = restarted.get(trip_url).json()
            assert persisted["saved_at"] is not None
            assert persisted["sources"] == trip["sources"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()

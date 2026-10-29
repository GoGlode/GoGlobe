"""Module 3: transport, normalization and all three tools through the BFF."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.bff import create_app
from app.contracts import examples
from app.integrations.http import (
    HTTPDestinationProvider, HTTPFlightProvider, HTTPHotelProvider, JSONEndpoint,
    MAX_RESPONSE_BYTES, criteria_payload, rub_to_minor,
)
from app.integrations.ports import DestinationCriteria, FlightCriteria, HotelCriteria, ProviderError, ToolResult
from app.integrations.service import DemoDestinationProvider, IntegrationTools
from app.planning import AgentPlan, DemoPlanner

PROVIDERS = {"hotels": HTTPHotelProvider, "flights": HTTPFlightProvider,
             "destinations": HTTPDestinationProvider}


def criteria(kind):
    deadline = datetime.now(timezone.utc) + timedelta(seconds=5)
    if kind == "destinations":
        return DestinationCriteria("Рим", deadline)
    travelers = {"adults": 2, "children_ages": []}
    if kind == "hotels":
        return HotelCriteria("Рим", {"check_in": "2026-11-10", "check_out": "2026-11-11"}, travelers, None, [], deadline)
    return FlightCriteria("Рим", "Москва", {"outbound_date": "2026-11-10", "return_date": "2026-11-11"}, travelers, None, [], deadline)


def envelope(kind, request=None):
    request = request or criteria_payload(criteria(kind))
    if kind == "destinations":
        result = asyncio.run(DemoDestinationProvider().search(criteria(kind)))
        fields = ("query",)
        value = {"items": result.items, "sources": result.sources, "warnings": result.warnings}
    else:
        value = deepcopy(examples()["hotel_offers" if kind == "hotels" else "flight_offers"]["value"])
        fields = PROVIDERS[kind].context_fields
    return {"status": "ok", "items": value["items"], "sources": value["sources"],
            "warnings": value["warnings"], "data_mode": "demo",
            "context": {key: request[key] for key in fields}}


def run_tool(kind, handler, *, mode="demo", **provider_kwargs):
    async def run():
        endpoint = JSONEndpoint("https://provider.test/" + kind, headers={"Authorization": "Bearer test-private-key"},
                                transport=httpx.MockTransport(handler))
        provider = PROVIDERS[kind](endpoint, data_mode=mode, **provider_kwargs)
        tools = IntegrationTools(**{kind: provider})
        return await getattr(tools, kind)(criteria(kind))
    return asyncio.run(run())


@pytest.mark.parametrize("kind", PROVIDERS)
def test_request_and_response_contract(kind):
    response = envelope(kind)
    def handler(request):
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer test-private-key"
        assert request.headers["accept"] == "application/json"
        payload = json.loads(request.content)
        assert payload == criteria_payload(criteria(kind))
        assert "deadline_at" not in payload
        return httpx.Response(200, json=response)
    result = run_tool(kind, handler)
    assert result.status == "ok"
    assert result.data_mode == "demo"
    assert len(result.items) == 1
    result.validate_for(kind)
    if kind != "destinations":
        assert result.items[0]["booking_url"] is None
        assert result.items[0]["total_price"]["money"] == response["items"][0]["total_price"]["money"]
    result.items.clear()
    assert response["items"]


@pytest.mark.parametrize("kind", PROVIDERS)
@pytest.mark.parametrize("fault", ["context", "mode", "source", "timezone", "duplicate", "shape", "partial", "unavailable"])
def test_invalid_upstream_is_not_returned(kind, fault):
    body = envelope(kind)
    if fault == "context":
        body["context"][next(iter(body["context"]))] = "wrong"
    elif fault == "mode":
        body["data_mode"] = "live"
    elif fault == "source":
        body["sources"] = []
    elif fault == "timezone":
        if kind == "destinations":
            body["items"][0]["place"]["timezone"] = "Invalid/Zone"
        elif kind == "flights":
            body["items"][0]["outbound_segments"][0]["origin"]["timezone"] = "Invalid/Zone"
        else:
            body["items"][0]["rating"] = 99
    elif fault == "duplicate":
        body["items"].append(deepcopy(body["items"][0]))
    elif fault == "shape":
        body["items"] = {}
    elif fault == "partial":
        body["status"], body["warnings"] = "partial", []
    else:
        body["status"] = "unavailable"
    result = run_tool(kind, lambda request: httpx.Response(200, json=body))
    assert result.status == "unavailable"
    assert result.items == []
    assert result.warnings[0]["code"] == "PROVIDER_INVALID_RESPONSE"


@pytest.mark.parametrize("kind", PROVIDERS)
def test_empty_is_valid_and_not_an_error(kind):
    body = envelope(kind)
    body.update(items=[], sources=[], warnings=[])
    assert run_tool(kind, lambda request: httpx.Response(200, json=body)).status == "ok"


@pytest.mark.parametrize("status,code", [(401, "PROVIDER_AUTH_ERROR"), (403, "PROVIDER_AUTH_ERROR"),
    (429, "PROVIDER_RATE_LIMITED"), (503, "PROVIDER_HTTP_ERROR"), (302, "PROVIDER_HTTP_ERROR")])
def test_http_failures_do_not_leak_or_retry(status, code):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, text="upstream-private-key", headers={"Location": "https://other.test"})
    result = run_tool("hotels", handler, mode="live")
    assert result.warnings[0]["code"] == code
    assert result.status == "unavailable" and result.data_mode == "live"
    assert len(requests) == 1
    assert "private-key" not in str(result)


@pytest.mark.parametrize("fault,code", [("json", "PROVIDER_INVALID_RESPONSE"),
    ("nan", "PROVIDER_INVALID_RESPONSE"), ("html", "PROVIDER_INVALID_RESPONSE"),
    ("large", "PROVIDER_RESPONSE_TOO_LARGE"), ("timeout", "PROVIDER_TIMEOUT"),
    ("network", "PROVIDER_TRANSPORT_ERROR")])
def test_transport_failures(fault, code):
    def handler(request):
        if fault == "timeout":
            raise httpx.ReadTimeout("private-key")
        if fault == "network":
            raise httpx.ConnectError("private-key")
        content = {"json": b"{", "nan": b'{"value": NaN}', "html": b"<html></html>",
                   "large": b"x" * (MAX_RESPONSE_BYTES + 1)}[fault]
        return httpx.Response(200, content=content, headers={"content-type": "text/html" if fault == "html" else "application/json"})
    result = run_tool("hotels", handler)
    assert result.warnings[0]["code"] == code
    assert "private-key" not in str(result)


@pytest.mark.parametrize("url", ["http://provider.test/x", "https://user:secret@provider.test/x",
    "https://provider.test/x#fragment", "https://provider.test/x?key=secret", "/relative"])
def test_endpoint_configuration_is_explicit(url):
    with pytest.raises(ValueError):
        JSONEndpoint(url)


@pytest.mark.parametrize("amount,expected", [("15000.50", 1500050), (0, 0), (Decimal("0.01"), 1), ("90000000000", 9000000000000)])
def test_exact_money_conversion(amount, expected):
    assert rub_to_minor(amount) == expected


@pytest.mark.parametrize("amount", [True, 0.1, "0.001", "-1", "NaN", "Infinity", "bad", "90000000000.01"])
def test_money_conversion_rejects_ambiguous_amounts(amount):
    with pytest.raises(ValueError):
        rub_to_minor(amount)


def test_money_conversion_never_rounds_long_decimal():
    with pytest.raises(ValueError):
        rub_to_minor("1.00000000000000000000000000000000001")


def test_json_duplicate_keys_are_rejected():
    result = run_tool("hotels", lambda request: httpx.Response(
        200, content=b'{"status":"ok","status":"unavailable"}',
        headers={"content-type": "application/json"}))
    assert result.warnings[0]["code"] == "PROVIDER_INVALID_RESPONSE"


@pytest.mark.parametrize("value", [2.0, True])
def test_context_requires_exact_integer_types(value):
    body = envelope("hotels")
    body["context"]["travelers"]["adults"] = value
    assert run_tool("hotels", lambda request: httpx.Response(200, json=body)).status == "unavailable"


def test_provider_error_code_cannot_contain_secrets():
    class BadProvider:
        data_mode = "live"
        async def search(self, value):
            raise ProviderError("private-key")
    async def run():
        result = await IntegrationTools(hotels=BadProvider()).hotels(criteria("hotels"))
        assert "private-key" not in str(result)
    asyncio.run(run())


def test_unknown_price_is_preserved_without_invented_coverage():
    body = envelope("hotels")
    for key in ("total_price", "nightly_price"):
        body["items"][0][key].update(status="unknown", money=None, coverage=[],
            source_ids=[], checked_at=None, valid_until=None, stale=False)
    result = run_tool("hotels", lambda request: httpx.Response(200, json=body))
    assert result.status == "ok"
    assert result.items[0]["total_price"]["money"] is None


def test_mutated_criteria_are_revalidated_before_http():
    calls = []
    # The public integration boundary translates all invalid criteria to unavailable.
    async def public_run():
        value = criteria("hotels")
        value.travelers["adults"] = 0
        tools = IntegrationTools(hotels=HTTPHotelProvider(JSONEndpoint("https://provider.test/hotels",
            transport=httpx.MockTransport(lambda request: calls.append(request)))))
        result = await tools.hotels(value)
        assert result.status == "unavailable"
    asyncio.run(public_run())
    assert calls == []


@pytest.mark.parametrize("fault", ["nan", "unverified", "iana", "duplicate_sources"])
def test_destination_integrity(fault):
    body = envelope("destinations")
    item = body["items"][0]
    if fault == "nan":
        item["place"].update(latitude=float("nan"), longitude=12.5)
    elif fault == "unverified":
        item["place"].update(verification="verified", source_ids=[])
    elif fault == "iana":
        item["place"]["timezone"] = item["destination"]["timezone"] = "Bad/Zone"
    else:
        body["sources"].append(deepcopy(body["sources"][0]))
    with pytest.raises(Exception):
        ToolResult(body["status"], body["items"], body["sources"], body["warnings"], "demo").validate_for("destinations")


def test_vendor_mapping_and_currency_units():
    canonical = envelope("hotels")
    def encode(value):
        return {"city": value.destination, "guests": value.travelers, **value.stay}
    def decode(raw, value):
        canonical["items"][0]["total_price"]["money"]["amount_minor"] = rub_to_minor(raw["rub_total"])
        return canonical
    def handler(request):
        assert json.loads(request.content)["city"] == "Рим"
        return httpx.Response(200, json={"rub_total": "1234.56"})
    result = run_tool("hotels", handler, encode=encode, decode=decode)
    assert result.items[0]["total_price"]["money"] == {"currency": "RUB", "amount_minor": 123456}


@pytest.mark.parametrize("fault", ["basis", "currency", "date", "guests"])
def test_hotel_context_and_price_basis(fault):
    body = envelope("hotels")
    if fault == "basis":
        body["items"][0]["total_price"]["basis"] = "person_total"
    elif fault == "currency":
        body["items"][0]["total_price"]["money"]["currency"] = "USD"
    elif fault == "date":
        body["items"][0]["check_in"] = "2026-11-09"
    else:
        body["context"]["travelers"] = {"adults": 1, "children_ages": []}
    result = run_tool("hotels", lambda request: httpx.Response(200, json=body))
    assert result.status == "unavailable"


def test_destination_demo_empty_and_no_guessed_coordinates():
    async def run():
        tools = IntegrationTools()
        result = await tools.destinations(criteria("destinations"))
        assert result.items[0]["place"]["latitude"] is None
        assert result.items[0]["place"]["verification"] == "unknown"
        assert result.data_mode == "demo"
        empty = await tools.destinations(DestinationCriteria("Unknown", criteria("destinations").deadline_at))
        assert empty.status == "ok" and empty.items == []
    asyncio.run(run())


def test_all_three_http_adapters_through_agent_and_bff(tmp_path):
    # Real local HTTP requests, not an ASGI/mock transport. No external supplier is claimed.
    responses = {kind: envelope(kind) for kind in PROVIDERS}
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            kind = self.path.lstrip("/")
            calls.append((kind, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            body = json.dumps(responses[kind]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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
            results = await asyncio.gather(*[
                getattr(context.tools, kind)(criteria(kind)) for kind in PROVIDERS])
            assert all(result.status == "ok" and result.items for result in results)
            plan = await DemoPlanner().plan(context)
            destination = results[2]
            return AgentPlan(destination.items[0]["destination"], plan.duration_days,
                             plan.itinerary, destination.sources, destination.warnings, "demo")
    try:
        with TestClient(create_app(str(tmp_path / "http.sqlite3"), agent=Agent(), tools=tools),
                        headers={"Origin": "http://localhost:8000"}) as client:
            assert client.post("/api/v1/session", json={}).status_code == 200
            response = client.post("/api/v1/searches", json=examples()["plan_request"]["value"],
                                   headers={"Idempotency-Key": str(uuid4())})
            assert response.status_code == 202, response.text
            trip = client.get("/api/v1/trips/" + response.json()["trip_id"]).json()
            assert trip["destination"]["name"] == "Рим"
            assert trip["sources"][0]["source_id"] == "demo_rome_catalog"
            assert trip["price_summary"]["money"] is None
            assert {kind for kind, payload in calls} == set(PROVIDERS)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()

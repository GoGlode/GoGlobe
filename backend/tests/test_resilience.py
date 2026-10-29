import asyncio
import time
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
import httpx
from fastapi.testclient import TestClient
from uuid import uuid4

from app.contracts import examples
from app.integrations.ports import HotelCriteria, ProviderError, ToolResult
from app.integrations.resilience import ResiliencePolicy, ResilientIntegrationTools, ResultCache
from app.integrations.ports import DestinationCriteria, FlightCriteria
from app.integrations.http import HTTPHotelProvider, JSONEndpoint, retry_after_seconds
from app.bff import create_app
from app.planning import DemoPlanner, PlanningService


def criteria(seconds=5, **changes):
    value = HotelCriteria("Рим", {"check_in": "2026-11-10", "check_out": "2026-11-11"},
                          {"adults": 2, "children_ages": []}, None, [],
                          datetime.now(timezone.utc) + timedelta(seconds=seconds))
    return replace(value, **changes)


def offers(mode="live"):
    fixture = deepcopy(examples()["hotel_offers"]["value"])
    stamp = datetime.now(timezone.utc).isoformat()
    for source in fixture["sources"]:
        source["checked_at"] = stamp
    for item in fixture["items"]:
        for name in ("total_price", "nightly_price"):
            item[name].update(checked_at=stamp, valid_until=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(), stale=False)
    return ToolResult("ok", fixture["items"], fixture["sources"], [], mode)


class Provider:
    data_mode = "live"

    def __init__(self, failures=(), result=None, delay=0):
        self.failures = list(failures)
        self.result = result if result is not None else offers()
        self.delay = delay
        self.calls = 0

    async def search(self, request):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.failures:
            raise ProviderError(self.failures.pop(0))
        return self.result


def test_cache_expiry_lru_and_copies():
    clock = [0]
    cache = ResultCache(ResiliencePolicy(cache_ttl_seconds=10, max_entries=2), clock=lambda: clock[0])
    value = offers()
    cache.put("one", value)
    value.items.clear()
    cached = cache.get("one")
    assert cached.items
    cached.items.clear()
    assert cache.get("one").items
    cache.put("two", offers())
    cache.get("one")
    cache.put("three", offers())
    assert cache.get("two") is None
    # Reading close to expiry may update LRU order, but must not slide TTL.
    clock[0] = 9
    assert cache.get("one") is not None
    clock[0] = 10
    assert cache.get("one") is None
    assert cache._bytes == 0


def test_cache_does_not_extend_quote_or_cache_failure():
    cache = ResultCache(ResiliencePolicy())
    value = offers()
    value.items[0]["total_price"]["valid_until"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    cache.put("expired", value)
    assert cache.get("expired") is None
    cache.put("error", ToolResult("unavailable", [], [], [], "live"))
    assert cache.get("error") is None
    cache = ResultCache(ResiliencePolicy(max_bytes=10))
    cache.put("large", offers())
    assert cache.get("large") is None


def test_cache_all_context_fields_deadline_and_provider_isolation():
    async def run():
        provider = Provider()
        tools = ResilientIntegrationTools(hotels=provider)
        original = criteria()
        assert (await tools.hotels(original)).status == "ok"
        cached = await tools.hotels(criteria())
        assert provider.calls == 1
        assert "CACHE_HIT" in {item["code"] for item in cached.warnings}
        assert cached.items[0]["total_price"]["checked_at"] == provider.result.items[0]["total_price"]["checked_at"]
        for changed in [criteria(travelers={"adults": 3, "children_ages": []}),
                        criteria(budget={"amount_minor": 100000, "currency": "RUB"}),
                        criteria(wishes=["sea_view"]), criteria(destination="Rome"),
                        criteria(stay={"check_in": "2026-11-11", "check_out": "2026-11-12"})]:
            await tools.hotels(changed)
        assert provider.calls == 6
        other = Provider()
        tools.hotel_provider = other
        await tools.hotels(criteria())
        assert other.calls == 1
    asyncio.run(run())


def test_cache_can_be_disabled_per_source():
    async def run():
        provider = Provider()
        tools = ResilientIntegrationTools(hotels=provider, policies={"hotels": ResiliencePolicy(cache_ttl_seconds=0)})
        await tools.hotels(criteria())
        await tools.hotels(criteria())
        assert provider.calls == 2
    asyncio.run(run())


@pytest.mark.parametrize("changes", [{"max_attempts": 0}, {"max_attempts": 4}, {"cache_ttl_seconds": float("nan")},
                                      {"attempt_timeout_seconds": 0}, {"max_entries": True}, {"demo_fallback": "yes"}])
def test_invalid_policy(changes):
    with pytest.raises(ValueError):
        ResiliencePolicy(**changes)


@pytest.mark.parametrize("code", ["PROVIDER_TIMEOUT", "PROVIDER_TRANSPORT_ERROR", "PROVIDER_RATE_LIMITED"])
def test_transient_failure_retries_then_succeeds(code):
    async def run():
        provider = Provider([code, code])
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(backoff_seconds=0))
        assert (await tools.hotels(criteria())).status == "ok"
        assert provider.calls == 3
    asyncio.run(run())


@pytest.mark.parametrize("code", ["PROVIDER_AUTH_ERROR", "PROVIDER_INVALID_RESPONSE", "PROVIDER_HTTP_ERROR"])
def test_permanent_failure_is_not_retried_or_cached(code):
    async def run():
        provider = Provider([code])
        tools = ResilientIntegrationTools(hotels=provider)
        assert (await tools.hotels(criteria())).status == "unavailable"
        assert provider.calls == 1
        assert (await tools.hotels(criteria())).status == "ok"
        assert provider.calls == 2
    asyncio.run(run())


def test_timeout_has_attempt_and_total_bounds():
    async def run():
        provider = Provider(delay=0.2)
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(attempt_timeout_seconds=0.01, backoff_seconds=0))
        result = await tools.hotels(criteria())
        assert result.status == "unavailable"
        assert provider.calls == 3
        provider.calls = 0
        start = asyncio.get_running_loop().time()
        result = await tools.hotels(criteria(seconds=0.025))
        assert result.status == "unavailable"
        assert asyncio.get_running_loop().time() - start < 0.15
        assert not tools._pending
    asyncio.run(run())


def test_concurrent_queries_and_short_waiter_deadline():
    async def run():
        provider = Provider(delay=0.08)
        tools = ResilientIntegrationTools(hotels=provider)
        leader = asyncio.create_task(tools.hotels(criteria()))
        await asyncio.sleep(0.01)
        short = asyncio.create_task(tools.hotels(criteria(seconds=0.015)))
        followers = [asyncio.create_task(tools.hotels(criteria())) for _ in range(10)]
        results = await asyncio.gather(leader, short, *followers)
        assert results[1].status == "unavailable"
        assert all(result.status == "ok" for i, result in enumerate(results) if i != 1)
        assert provider.calls == 1
        assert not tools._pending
    asyncio.run(run())


def test_cancel_propagates_and_does_not_poison_key():
    async def run():
        provider = Provider(delay=1)
        tools = ResilientIntegrationTools(hotels=provider)
        task = asyncio.create_task(tools.hotels(criteria()))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not tools._pending
        provider.delay = 0
        assert (await tools.hotels(criteria())).status == "ok"
    asyncio.run(run())


def test_empty_and_partial_are_not_retried():
    async def run():
        for value in [ToolResult("ok", [], [], [], "live"),
                      replace(offers(), status="partial", warnings=[{"code": "PARTIAL", "message": "Неполные данные", "trip_id": None}])]:
            provider = Provider(result=value)
            tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(demo_fallback=True))
            result = await tools.hotels(criteria())
            assert result.status == value.status
            assert result.data_mode == "live"
            assert provider.calls == 1
    asyncio.run(run())


def test_backoff_cannot_overrun_deadline():
    async def run():
        provider = Provider(["PROVIDER_TRANSPORT_ERROR"] * 3)
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(backoff_seconds=10))
        start = asyncio.get_running_loop().time()
        assert (await tools.hotels(criteria(seconds=0.1))).status == "unavailable"
        assert asyncio.get_running_loop().time() - start < 0.15
        assert provider.calls == 1
    asyncio.run(run())


def test_pending_keys_are_bounded():
    async def run():
        provider = Provider(delay=0.03)
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(max_pending_keys=1))
        leader = asyncio.create_task(tools.hotels(criteria()))
        await asyncio.sleep(0.005)
        result = await tools.hotels(criteria(wishes=["sea_view"]))
        assert result.warnings[0]["code"] == "PROVIDER_OVERLOADED"
        assert (await leader).status == "ok"
    asyncio.run(run())


@pytest.mark.parametrize("status,expected_calls", [(500, 3), (502, 3), (503, 3), (504, 3), (429, 3),
                                                  (400, 1), (401, 1), (403, 1), (404, 1), (501, 1)])
def test_http_status_controls_retries_without_secret_leaks(status, expected_calls):
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(status, text="upstream-private-token")
        provider = HTTPHotelProvider(JSONEndpoint("https://provider.test/hotels", transport=httpx.MockTransport(handler)))
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(backoff_seconds=0))
        result = await tools.hotels(criteria())
        assert result.status == "unavailable"
        assert len(calls) == expected_calls
        assert "upstream-private-token" not in str(result)
    asyncio.run(run())


def test_demo_fallback_explicit_context_and_not_cached_as_live():
    async def run():
        provider = Provider(["PROVIDER_AUTH_ERROR", "PROVIDER_AUTH_ERROR"])
        tools = ResilientIntegrationTools(hotels=provider)
        assert (await tools.hotels(criteria())).data_mode == "live"
        enabled = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(demo_fallback=True))
        result = await enabled.hotels(criteria())
        result.validate_for("hotels")
        assert result.data_mode == "demo"
        assert any(w["code"] == "DEMO_FALLBACK" for w in result.warnings)
        assert result.items[0]["availability"] == "unknown"
        assert result.items[0]["booking_url"] is None
        assert result.items[0]["total_price"]["checked_at"] == examples()["hotel_offers"]["value"]["items"][0]["total_price"]["checked_at"]
        assert (await enabled.hotels(criteria())).data_mode == "live"
        assert provider.calls == 3
        provider.failures = ["PROVIDER_AUTH_ERROR"]
        mismatch = await enabled.hotels(criteria(travelers={"adults": 3, "children_ages": []}))
        assert mismatch.status == "unavailable"
        assert mismatch.data_mode == "live"
    asyncio.run(run())


def test_demo_fallback_works_after_primary_timeout():
    async def run():
        tools = ResilientIntegrationTools(hotels=Provider(delay=1), policy=ResiliencePolicy(demo_fallback=True, backoff_seconds=0))
        result = await tools.hotels(criteria(seconds=0.3))
        assert result.data_mode == "demo"
        assert result.items
    asyncio.run(run())


def test_all_three_tools_support_fallback():
    async def run():
        tools = ResilientIntegrationTools(flights=Provider(["PROVIDER_AUTH_ERROR"]),
                                         destinations=Provider(["PROVIDER_AUTH_ERROR"]),
                                         policy=ResiliencePolicy(demo_fallback=True))
        deadline = datetime.now(timezone.utc) + timedelta(seconds=5)
        flight = await tools.flights(FlightCriteria("Рим", "Москва", {"outbound_date": "2026-11-10", "return_date": "2026-11-11"},
                                                  {"adults": 2, "children_ages": []}, None, [], deadline))
        destination = await tools.destinations(DestinationCriteria("Рим", deadline))
        for kind, result in [("flights", flight), ("destinations", destination)]:
            assert result.data_mode == "demo" and result.items
            result.validate_for(kind)
            assert any(w["code"] == "DEMO_FALLBACK" for w in result.warnings)
    asyncio.run(run())


def test_fallback_mode_is_carried_through_agent_and_bff(tmp_path):
    class Agent:
        async def plan(self, context):
            result, = await asyncio.gather(context.tools.hotels(criteria(deadline_at=context.deadline_at)))
            assert result.data_mode == "demo"
            # Even if an agent forgets to propagate the mode, PlanningService does.
            return replace(await DemoPlanner().plan(context), data_mode="live")
    tools = ResilientIntegrationTools(hotels=Provider(["PROVIDER_AUTH_ERROR"]), policy=ResiliencePolicy(demo_fallback=True))
    with TestClient(create_app(str(tmp_path / "fallback.sqlite3"), agent=Agent(), tools=tools),
                    headers={"Origin": "http://localhost:8000"}) as client:
        assert client.post("/api/v1/session", json={}).status_code == 200
        response = client.post("/api/v1/searches", json=examples()["plan_request"]["value"], headers={"Idempotency-Key": str(uuid4())})
        assert response.status_code == 202, response.text
        snapshot = client.get(response.headers["location"]).json()
        assert snapshot["data_mode"] == "demo"
        assert any(w["code"] == "DEMO_FALLBACK" for w in snapshot["warnings"])
        trip = client.get("/api/v1/trips/" + response.json()["trip_id"]).json()
        assert trip["data_mode"] == "demo"
        assert trip["price_summary"]["money"] is None


def test_default_server_tools_and_env(monkeypatch):
    monkeypatch.setenv("GOGLOBE_CACHE_TTL_SECONDS", "0")
    monkeypatch.setenv("GOGLOBE_DEMO_FALLBACK", "true")
    service = PlanningService()
    assert isinstance(service.tools, ResilientIntegrationTools)
    assert service.tools.policy.provider_mode == "snapshot"
    assert service.tools.policy.attempt_timeout_seconds == 8
    assert service.tools.policy.max_attempts == 3
    assert service.tools.policy.cache_ttl_seconds == 0
    assert service.tools.policy.demo_fallback is True
    monkeypatch.setenv("GOGLOBE_DEMO_FALLBACK", "sometimes")
    with pytest.raises(ValueError):
        PlanningService()


@pytest.mark.parametrize("mode", ["live", "snapshot"])
def test_provider_mode_env_accepts_only_supported_values(monkeypatch, mode):
    monkeypatch.setenv("GOGLOBE_PROVIDERS", mode)
    assert PlanningService().tools.policy.provider_mode == mode


@pytest.mark.parametrize("mode", ["", "demo", "LIVE", " snapshot", "snapshot "])
def test_provider_mode_env_is_strict(monkeypatch, mode):
    monkeypatch.setenv("GOGLOBE_PROVIDERS", mode)
    with pytest.raises(ValueError, match="GOGLOBE_PROVIDERS"):
        PlanningService()


@pytest.mark.parametrize("name", [
    "GOGLOBE_CACHE_TTL_SECONDS",
    "GOGLOBE_PROVIDER_TIMEOUT_SECONDS",
    "GOGLOBE_PROVIDER_MAX_ATTEMPTS",
])
def test_invalid_numeric_env_names_the_setting(monkeypatch, name):
    monkeypatch.setenv(name, "not-a-number")
    with pytest.raises(ValueError, match=name):
        PlanningService()


def test_late_provider_cannot_return_success_or_populate_cache():
    class LateProvider(Provider):
        async def search(self, request):
            self.calls += 1
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                return self.result
    async def run():
        provider = LateProvider()
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(max_attempts=1, attempt_timeout_seconds=0.01))
        assert (await tools.hotels(criteria())).status == "unavailable"
        assert not tools._caches["hotels"]._entries
    asyncio.run(run())


def test_cached_price_expires_even_if_monotonic_clock_stands_still():
    cache = ResultCache(ResiliencePolicy(), clock=lambda: 0)
    value = offers()
    value.items[0]["total_price"]["valid_until"] = (datetime.now(timezone.utc) + timedelta(seconds=0.02)).isoformat()
    cache.put("price", value)
    assert cache.get("price") is not None
    time.sleep(0.03)
    assert cache.get("price") is None


def test_retry_after_is_respected_within_total_deadline():
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(429, headers={"Retry-After": "60"})
        provider = HTTPHotelProvider(JSONEndpoint("https://provider.test/hotels", transport=httpx.MockTransport(handler)))
        tools = ResilientIntegrationTools(hotels=provider)
        result = await tools.hotels(criteria(seconds=0.1))
        assert result.status == "unavailable"
        assert len(calls) == 1
    asyncio.run(run())


def test_retry_after_parser():
    from email.utils import format_datetime
    assert retry_after_seconds("60") == 60
    assert 1 < retry_after_seconds(format_datetime(datetime.now(timezone.utc) + timedelta(seconds=3), usegmt=True)) <= 3
    for invalid in [None, "bad", "nan", "-1", "2026-11-10", "1.5"]:
        assert retry_after_seconds(invalid) is None


def test_plan_trace_does_not_leak_into_next_request():
    class Agent:
        demo = True
        async def plan(self, context):
            if self.demo:
                await context.tools.hotels(criteria(deadline_at=context.deadline_at))
            return replace(await DemoPlanner().plan(context), data_mode="live")
    async def run():
        agent = Agent()
        service = PlanningService(agent, ResilientIntegrationTools(hotels=Provider(["PROVIDER_AUTH_ERROR"]), policy=ResiliencePolicy(demo_fallback=True)))
        body = examples()["plan_request"]["value"]
        assert (await service.plan(body, criteria().deadline_at)).data_mode == "demo"
        agent.demo = False
        result = await service.plan(body, criteria().deadline_at)
        assert result.data_mode == "live"
        assert not result.warnings
    asyncio.run(run())


def test_real_http_retry_then_cache():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    import json
    state = {"calls": 0}
    value = offers()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            state["calls"] += 1
            if state["calls"] == 1:
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            payload = {"status": "ok", "items": value.items, "sources": value.sources,
                       "warnings": [], "data_mode": "live", "context": {
                           "destination": "Рим", "stay": {"check_in": "2026-11-10", "check_out": "2026-11-11"},
                           "travelers": {"adults": 2, "children_ages": []}}}
            content = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        async def run():
            provider = HTTPHotelProvider(JSONEndpoint(f"http://127.0.0.1:{server.server_port}/hotels", allow_local_http=True))
            tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(backoff_seconds=0))
            assert (await tools.hotels(criteria())).status == "ok"
            second = await tools.hotels(criteria())
            assert any(w["code"] == "CACHE_HIT" for w in second.warnings)
            assert state["calls"] == 2
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

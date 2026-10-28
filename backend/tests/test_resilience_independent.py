"""Independent scenario audit: events, controlled wall/TTL clocks, real counters."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest

from app.contracts import examples
from app.integrations import resilience
from app.integrations.http import HTTPHotelProvider, JSONEndpoint
from app.integrations.ports import HotelCriteria, ProviderError, ToolResult
from app.integrations.resilience import ResiliencePolicy, ResilientIntegrationTools, ResultCache
from app.planning import DemoPlanner, PlanningService


def request(*, seconds=3, **updates):
    value = HotelCriteria("Рим", {"check_in": "2026-11-10", "check_out": "2026-11-11"},
                          {"adults": 2, "children_ages": []}, None, [],
                          datetime.now(timezone.utc) + timedelta(seconds=seconds))
    return replace(value, **updates)


def fresh_result():
    fixture = deepcopy(examples()["hotel_offers"]["value"])
    now = datetime.now(timezone.utc)
    for source in fixture["sources"]:
        source["checked_at"] = now.isoformat()
    for item in fixture["items"]:
        item["booking_url"] = None
        for key in ("total_price", "nightly_price"):
            item[key].update(checked_at=now.isoformat(), valid_until=(now + timedelta(minutes=2)).isoformat(), stale=False)
    return ToolResult("ok", fixture["items"], fixture["sources"], [], "live")


class GateProvider:
    data_mode = "live"

    def __init__(self):
        self.calls = 0
        self.cancelled = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.value = fresh_result()

    async def search(self, criteria):
        self.calls += 1
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        return self.value


async def joined(tools, count):
    # Yield ready tasks, never sleep for an arbitrary wall duration.
    async def check():
        while not tools._pending or next(iter(tools._pending.values()))[1] != count:
            await asyncio.sleep(0)
    await asyncio.wait_for(check(), timeout=1)


def test_slow_provider_attempts_are_bounded_and_cancelled():
    async def run():
        provider = GateProvider()
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(
            max_attempts=2, attempt_timeout_seconds=0.02, backoff_seconds=0))
        start = asyncio.get_running_loop().time()
        value = await tools.hotels(request(seconds=1))
        assert value.status == "unavailable"
        assert provider.calls == provider.cancelled == 2
        assert asyncio.get_running_loop().time() - start < 0.5
        assert not tools._pending and not tools._caches["hotels"]._entries
    asyncio.run(run())


def test_total_deadline_cancels_active_provider_before_another_attempt():
    async def run():
        provider = GateProvider()
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(
            max_attempts=3, attempt_timeout_seconds=1, backoff_seconds=0))
        start = asyncio.get_running_loop().time()
        value = await tools.hotels(request(seconds=0.03))
        assert value.status == "unavailable"
        assert provider.calls == provider.cancelled == 1
        assert asyncio.get_running_loop().time() - start < 0.3
        assert not tools._pending and not tools._caches["hotels"]._entries
    asyncio.run(run())


@pytest.mark.parametrize("status,body,headers", [
    (429, None, {"Retry-After": "60"}),
    (401, None, {}), (403, None, {}),
    (200, {"unexpected": "invalid response"}, {}),
])
def test_retry_after_and_permanent_errors_make_one_http_request(status, body, headers):
    async def run():
        calls = []
        def handler(value):
            calls.append(value)
            return httpx.Response(status, json=body, headers=headers)
        tools = ResilientIntegrationTools(hotels=HTTPHotelProvider(JSONEndpoint(
            "https://provider.test/hotels", transport=httpx.MockTransport(handler))))
        start = asyncio.get_running_loop().time()
        result = await tools.hotels(request(seconds=0.5))
        assert result.status == "unavailable" and result.data_mode == "live"
        assert len(calls) == 1
        assert asyncio.get_running_loop().time() - start < 0.5
        assert not tools._pending and not tools._caches["hotels"]._entries
    asyncio.run(run())


def test_transient_http_failure_recovers_on_second_attempt():
    async def run():
        calls = []
        result = fresh_result()
        def handler(value):
            calls.append(value)
            if len(calls) == 1:
                return httpx.Response(503)
            payload = json.loads(value.content)
            context = {key: payload[key] for key in ("destination", "stay", "travelers")}
            return httpx.Response(200, json={"status": result.status, "items": result.items,
                "sources": result.sources, "warnings": [], "data_mode": "live", "context": context})
        tools = ResilientIntegrationTools(hotels=HTTPHotelProvider(JSONEndpoint(
            "https://provider.test/hotels", transport=httpx.MockTransport(handler))),
            policy=ResiliencePolicy(backoff_seconds=0))
        assert (await tools.hotels(request())).status == "ok"
        assert len(calls) == 2
        assert (await tools.hotels(request())).status == "ok"
        assert len(calls) == 2
    asyncio.run(run())


def test_same_key_clients_and_cancelled_waiter_are_isolated():
    async def run():
        provider = GateProvider()
        tools = ResilientIntegrationTools(hotels=provider)
        leader = asyncio.create_task(tools.hotels(request()))
        await provider.started.wait()
        followers = [asyncio.create_task(tools.hotels(request())) for _ in range(23)]
        await joined(tools, 24)
        followers[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await followers[0]
        assert provider.calls == 1 and provider.cancelled == 0
        provider.release.set()
        values = await asyncio.gather(leader, *followers[1:])
        assert all(value.status == "ok" for value in values)
        values[0].items.clear()
        assert all(value.items for value in values[1:])
        assert provider.calls == 1 and provider.cancelled == 0 and not tools._pending
    asyncio.run(run())


def test_short_waiter_does_not_shorten_leader_deadline():
    async def run():
        provider = GateProvider()
        tools = ResilientIntegrationTools(hotels=provider)
        leader = asyncio.create_task(tools.hotels(request()))
        await provider.started.wait()
        start = asyncio.get_running_loop().time()
        short = await tools.hotels(request(seconds=0.02))
        assert short.status == "unavailable"
        assert asyncio.get_running_loop().time() - start < 0.3
        assert not leader.done() and provider.cancelled == 0
        provider.release.set()
        assert (await leader).status == "ok"
        assert provider.calls == 1 and not tools._pending
    asyncio.run(run())


def test_queue_limits_bound_distinct_keys_and_identical_waiters():
    async def run():
        provider = GateProvider()
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(
            max_pending_keys=2, max_waiters_per_key=2))
        leader = asyncio.create_task(tools.hotels(request()))
        await provider.started.wait()
        follower = asyncio.create_task(tools.hotels(request()))
        await joined(tools, 2)
        other = asyncio.create_task(tools.hotels(request(wishes=["breakfast"])))
        async def second_started():
            while provider.calls < 2:
                await asyncio.sleep(0)
        await asyncio.wait_for(second_started(), timeout=1)
        by_key = await tools.hotels(request(wishes=["sea_view"]))
        by_waiters = await tools.hotels(request())
        assert by_key.warnings[0]["code"] == by_waiters.warnings[0]["code"] == "PROVIDER_OVERLOADED"
        assert len(tools._pending) == 2
        assert sum(value[1] for value in tools._pending.values()) == 3
        assert provider.calls == 2
        provider.release.set()
        assert all(value.status == "ok" for value in await asyncio.gather(leader, follower, other))
        assert not tools._pending
    asyncio.run(run())


def test_controlled_price_expiry_and_serialized_memory_bound(monkeypatch):
    now = datetime.now(timezone.utc)
    wall = [now]
    monotonic = [0.0]
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return wall[0].astimezone(tz) if tz is not None else wall[0].replace(tzinfo=None)
    monkeypatch.setattr(resilience, "datetime", Clock)
    value = fresh_result()
    value.items[0]["total_price"].update(checked_at=now.isoformat(), valid_until=(now + timedelta(seconds=10)).isoformat())
    size = len(json.dumps({"status": value.status, "items": value.items, "sources": value.sources,
                          "warnings": value.warnings, "data_mode": value.data_mode}, ensure_ascii=False).encode())
    cache = ResultCache(ResiliencePolicy(cache_ttl_seconds=60, max_entries=3, max_bytes=2 * size), clock=lambda: monotonic[0])
    for key in range(100):
        cache.put(key, value)
        assert len(cache._entries) <= 2 and cache._bytes <= 2 * size
    assert cache.get(99).items[0]["total_price"]["checked_at"] == now.isoformat()
    wall[0] += timedelta(seconds=10)
    # Even without monotonic advancing, the actual price has now expired.
    assert cache.get(99) is None
    monotonic[0] = 10
    assert cache.get(98) is None and cache._bytes == 0


@pytest.mark.parametrize("field", ["checked_at", "valid_until"])
def test_contract_valid_lowercase_rfc3339_does_not_crash_cache(field):
    async def run():
        provider = GateProvider()
        for item in provider.value.items:
            for price in ("total_price", "nightly_price"):
                item[price][field] = item[price][field].replace("+00:00", "Z").lower()
        provider.value.validate_for("hotels")  # This is valid in contract v0.3.
        provider.release.set()
        tools = ResilientIntegrationTools(hotels=provider)
        first = await tools.hotels(request())
        second = await tools.hotels(request())
        assert first.status == second.status == "ok"
        assert first.items[0]["total_price"][field] == second.items[0]["total_price"][field] == provider.value.items[0]["total_price"][field]
        assert provider.calls == 1
    asyncio.run(run())


@pytest.mark.parametrize("change", [
    {"stay": {"check_in": "2026-11-12", "check_out": "2026-11-13"}},
    {"travelers": {"adults": 3, "children_ages": []}},
])
def test_unsupported_reserve_preserves_live_failure(change):
    async def run():
        class Failed(GateProvider):
            async def search(self, criteria):
                self.calls += 1
                raise ProviderError("PROVIDER_AUTH_ERROR")
        provider = Failed()
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(demo_fallback=True))
        value = await tools.hotels(request(**change))
        assert value.status == "unavailable" and value.data_mode == "live" and not value.items
        assert provider.calls == 1 and not tools._caches["hotels"]._entries
    asyncio.run(run())


def test_recovery_and_concurrent_plan_traces_do_not_mix():
    async def run():
        ready = asyncio.Event()
        class Recovering(GateProvider):
            async def search(self, criteria):
                self.calls += 1
                if self.calls == 1:
                    raise ProviderError("PROVIDER_AUTH_ERROR")
                return self.value
        provider = Recovering()
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(demo_fallback=True))
        class Agent:
            async def plan(self, context):
                if context.query == "fallback":
                    value = await context.tools.hotels(request(deadline_at=context.deadline_at))
                    assert value.data_mode == "demo"
                    assert any(w["code"] == "DEMO_FALLBACK" for w in value.warnings)
                    assert all(item["booking_url"] is None and item["availability"] == "unknown" for item in value.items)
                    assert not tools._caches["hotels"]._entries
                    ready.set()
                    # Keep the demo plan alive while the independent live plan runs.
                    await live_finished.wait()
                else:
                    await ready.wait()
                    value = await context.tools.hotels(request(deadline_at=context.deadline_at))
                    assert value.data_mode == "live"
                    live_finished.set()
                return replace(await DemoPlanner().plan(context), data_mode="live")
        live_finished = asyncio.Event()
        planner = PlanningService(Agent(), tools)
        params = {"destination": "Рим", "duration_days": 2}
        deadline = request().deadline_at
        demo, live = await asyncio.wait_for(asyncio.gather(
            planner.plan({"query": "fallback", "params": params}, deadline),
            planner.plan({"query": "independent", "params": params}, deadline)), timeout=2)
        assert demo.data_mode == "demo" and any(w["code"] == "DEMO_FALLBACK" for w in demo.warnings)
        assert live.data_mode == "live" and not live.warnings
        cached = await tools.hotels(request())
        assert cached.data_mode == "live" and not any(w["code"] == "DEMO_FALLBACK" for w in cached.warnings)
        assert provider.calls == 2 and not tools._pending
    asyncio.run(run())

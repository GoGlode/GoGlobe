"""Second audit: adversarial boundaries, mutations and bounded contention."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import time

import pytest
from jsonschema.exceptions import ValidationError

from app.contracts import examples
from app.integrations.resilience import ResilientIntegrationTools, ResiliencePolicy
from app.planning import PlanningService, DemoPlanner
from tests.test_resilience import Provider, criteria, offers


@pytest.mark.parametrize("fault", ["none", "nan", "wrong_type", "circular"])
def test_bad_criteria_return_controlled_failure(fault):
    async def run():
        provider = Provider()
        tools = ResilientIntegrationTools(hotels=provider)
        value = criteria()
        if fault == "none":
            value = None
        elif fault == "nan":
            value.travelers["adults"] = float("nan")
        elif fault == "wrong_type":
            value = {"deadline_at": value.deadline_at}
        else:
            value.wishes.append(value.wishes)
        result = await tools.hotels(value)
        assert result.status == "unavailable"
        assert provider.calls == 0
        assert not tools._pending
    asyncio.run(run())


def test_criteria_snapshot_survives_mutation_while_waiting_for_slot():
    async def run():
        seen = []
        class CapturingProvider(Provider):
            async def search(self, request):
                seen.append(dict(request.stay))
                return await super().search(request)
        provider = CapturingProvider()
        tools = ResilientIntegrationTools(hotels=provider)
        tools._slots = asyncio.Semaphore(0)
        original = criteria()
        task = asyncio.create_task(tools.hotels(original))
        await asyncio.sleep(0.01)
        original.stay["check_in"] = "2026-11-09"
        tools._slots.release()
        result = await task
        assert result.status == "ok"
        assert seen == [{"check_in": "2026-11-10", "check_out": "2026-11-11"}]
        cached = await tools.hotels(criteria())
        assert cached.status == "ok" and provider.calls == 1
    asyncio.run(run())


@pytest.mark.parametrize("field", ["items", "sources", "warnings"])
def test_wrong_provider_array_type_never_reaches_cache(field):
    async def run():
        result = offers()
        for item in result.items:
            item["booking_url"] = None
        provider = Provider(result=replace(result, **{field: tuple(getattr(result, field))}))
        tools = ResilientIntegrationTools(hotels=provider)
        for _ in range(2):
            value = await tools.hotels(criteria())
            assert value.status == "unavailable"
        assert not tools._caches["hotels"]._entries
        assert provider.calls == 2
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["hidden_warning", "mode", "too_many_warnings"])
def test_demo_trace_does_not_launder_invalid_agent_output(fault):
    class Agent:
        async def plan(self, context):
            await context.tools.hotels(criteria(deadline_at=context.deadline_at))
            plan = await DemoPlanner().plan(context)
            if fault == "mode":
                return replace(plan, data_mode="broken")
            warnings = [{"code": "INFO", "message": "test", "trip_id": None} for _ in range(29)]
            if fault == "hidden_warning":
                warnings[-1] = {"secret": "invalid warning"}
            else:
                warnings.append(warnings[0])
            return replace(plan, warnings=warnings)
    async def run():
        service = PlanningService(Agent(), ResilientIntegrationTools())
        with pytest.raises((ValidationError, ValueError)):
            await service.plan(examples()["plan_request"]["value"], datetime.now(timezone.utc) + timedelta(seconds=5))
    asyncio.run(run())


def test_identical_key_waiters_are_bounded_and_cleanup_is_safe():
    async def run():
        provider = Provider(delay=0.04)
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(max_waiters_per_key=2))
        leader = asyncio.create_task(tools.hotels(criteria()))
        await asyncio.sleep(0.005)
        follower = asyncio.create_task(tools.hotels(criteria()))
        await asyncio.sleep(0.005)
        overloaded = await tools.hotels(criteria())
        assert overloaded.warnings[0]["code"] == "PROVIDER_OVERLOADED"
        assert all(result.status == "ok" for result in await asyncio.gather(leader, follower))
        assert provider.calls == 1 and not tools._pending
    asyncio.run(run())


def test_concurrent_stress_returns_copies_without_extra_provider_calls():
    async def run():
        provider = Provider(delay=0.03)
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(max_waiters_per_key=256))
        results = await asyncio.gather(*(tools.hotels(criteria()) for _ in range(200)))
        assert all(result.status == "ok" for result in results)
        assert provider.calls == 1 and not tools._pending
        results[0].items[0]["name"] = "changed by first client"
        assert all(result.items[0]["name"] != "changed by first client" for result in results[1:])
    asyncio.run(run())


def test_invalid_agent_via_bff_is_controlled_and_does_not_save(tmp_path):
    from fastapi.testclient import TestClient
    from uuid import uuid4
    from app.bff import create_app
    class Agent:
        async def plan(self, context):
            await context.tools.hotels(criteria(deadline_at=context.deadline_at))
            return replace(await DemoPlanner().plan(context), data_mode="broken")
    with TestClient(create_app(str(tmp_path / "invalid-agent.sqlite3"), agent=Agent()),
                    headers={"Origin": "http://localhost:8000"}) as client:
        assert client.post("/api/v1/session", json={}).status_code == 200
        result = client.post("/api/v1/searches", json=examples()["plan_request"]["value"], headers={"Idempotency-Key": str(uuid4())})
        assert result.status_code == 202
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            snapshot = client.get(result.headers["location"]).json()
            if snapshot["state"] == "failed":
                break
            time.sleep(0.01)
        assert snapshot["error"]["code"] == "AGENT_INVALID_RESPONSE"
        assert client.get("/health").status_code == 200


def test_demo_and_live_cache_entries_remain_separate():
    async def run():
        provider = Provider()
        tools = ResilientIntegrationTools(hotels=provider)
        live = await tools.hotels(criteria())
        provider.data_mode = "demo"
        provider.result = replace(offers(), data_mode="demo")
        provider.result.items[0]["name"] = "demo hotel"
        demo = await tools.hotels(criteria())
        assert demo.data_mode == "demo" and demo.items[0]["name"] == "demo hotel"
        provider.data_mode = "live"
        cached = await tools.hotels(criteria())
        assert cached.data_mode == "live"
        assert cached.items[0]["name"] == live.items[0]["name"]
        assert provider.calls == 2
    asyncio.run(run())


def test_cancelling_waiter_does_not_cancel_leader():
    async def run():
        provider = Provider(delay=0.04)
        tools = ResilientIntegrationTools(hotels=provider)
        leader = asyncio.create_task(tools.hotels(criteria()))
        await asyncio.sleep(0.005)
        waiter = asyncio.create_task(tools.hotels(criteria()))
        await asyncio.sleep(0.005)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert (await leader).status == "ok"
        assert provider.calls == 1 and not tools._pending
    asyncio.run(run())


def test_cache_write_after_deadline_does_not_store_or_evict():
    from app.integrations.resilience import ResultCache
    cache = ResultCache(ResiliencePolicy(max_entries=1))
    cache.put("existing", offers())
    with pytest.raises(TimeoutError):
        cache.put("late", offers(), deadline_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    assert cache.get("existing") is not None
    assert cache.get("late") is None


def test_invalid_provider_mode_is_rejected():
    async def run():
        provider = Provider()
        provider.data_mode = []
        tools = ResilientIntegrationTools(hotels=provider)
        result = await tools.hotels(criteria())
        assert result.status == "unavailable" and result.data_mode == "live"
        assert {warning["code"] for warning in result.warnings} == {
            "PROVIDER_INVALID_CONFIGURATION"
        }
    asyncio.run(run())


@pytest.mark.parametrize("kind", ["hotels", "flights"])
@pytest.mark.parametrize("extra", [{"wishes": ["sea_view"]}, {"budget": {"amount_minor": 100, "currency": "RUB"}}])
def test_fallback_does_not_claim_unsupported_budget_or_wishes(kind, extra):
    from app.integrations.ports import FlightCriteria
    async def run():
        provider = Provider(["PROVIDER_AUTH_ERROR"])
        tools = ResilientIntegrationTools(**{kind: provider}, policy=ResiliencePolicy(demo_fallback=True))
        request = criteria(**extra)
        if kind == "flights":
            request = FlightCriteria(request.destination, "Москва", {"outbound_date": "2026-11-10", "return_date": "2026-11-11"},
                                     request.travelers, request.budget, request.wishes, request.deadline_at)
        result = await getattr(tools, kind)(request)
        assert result.status == "unavailable"
        assert result.data_mode == "live" and not result.items
        assert provider.calls == 1
    asyncio.run(run())


def test_unsupported_fallback_does_not_take_primary_time_budget():
    async def run():
        provider = Provider(delay=0.32)
        tools = ResilientIntegrationTools(hotels=provider, policy=ResiliencePolicy(demo_fallback=True, max_attempts=1))
        result = await tools.hotels(criteria(seconds=0.4, wishes=["sea_view"]))
        assert result.status == "ok" and result.data_mode == "live"
        assert provider.calls == 1
    asyncio.run(run())

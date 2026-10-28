import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.bff import create_app
from app.contracts import examples
from app.integrations.ports import HotelCriteria, ToolResult
from app.integrations.service import IntegrationTools
from app.planning import DemoPlanner


@pytest.mark.parametrize("url,hosts,query_keys,allowed", [
    ("https://example.com/hotel", set(), set(), False),
    ("https://example.com/hotel", {"example.com"}, set(), True),
    ("https://example.com/hotel?redirect=bad", {"example.com"}, set(), False),
    ("https://example.com/hotel?id=1", {"example.com"}, {"id"}, True),
    ("https://example.com:8443/hotel", {"example.com"}, set(), False),
    ("https://user@example.com/hotel", {"example.com"}, set(), False),
])
def test_booking_links_are_explicitly_allowed(url, hosts, query_keys, allowed):
    class Provider:
        data_mode = "demo"
        async def search(self, criteria):
            fixture = deepcopy(examples()["hotel_offers"]["value"])
            fixture["items"][0]["booking_url"] = url
            return ToolResult("ok", fixture["items"], fixture["sources"], [], "demo")
    async def run():
        criteria = HotelCriteria("Рим", {"check_in": "2026-11-10", "check_out": "2026-11-11"}, {"adults": 2, "children_ages": []}, None, [], datetime.now(timezone.utc) + timedelta(seconds=5))
        result = await IntegrationTools(hotels=Provider(), allowed_booking_hosts=hosts, allowed_booking_query_keys=query_keys).hotels(criteria)
        assert result.status == "ok"
        assert result.items[0]["booking_url"] == (url if allowed else None)
    asyncio.run(run())


def test_price_freshness_is_not_extended():
    original = deepcopy(examples()["hotel_offers"]["value"])
    for key in ["total_price", "nightly_price"]:
        original["items"][0][key]["checked_at"] = "2000-01-01T00:00:00Z"
        original["items"][0][key]["valid_until"] = None
    class Provider:
        data_mode = "demo"
        async def search(self, criteria):
            return ToolResult("ok", original["items"], original["sources"], [], "demo")
    async def run():
        criteria = HotelCriteria("Рим", {"check_in": "2026-11-10", "check_out": "2026-11-11"}, {"adults": 2, "children_ages": []}, None, [], datetime.now(timezone.utc) + timedelta(seconds=5))
        result = await IntegrationTools(hotels=Provider()).hotels(criteria)
        assert result.status == "ok"
        price = result.items[0]["total_price"]
        assert price["stale"] is True
        assert price["checked_at"] == "2000-01-01T00:00:00Z"
        assert price["valid_until"] is None
        assert original["items"][0]["total_price"]["stale"] is False
    asyncio.run(run())


def test_db_transaction_is_not_held_while_agent_waits(tmp_path):
    class Agent:
        started = threading.Event()
        release = threading.Event()
        async def plan(self, context):
            self.started.set()
            while not self.release.is_set():
                await asyncio.sleep(0.01)
            return await DemoPlanner().plan(context)
    agent = Agent()
    with TestClient(create_app(str(tmp_path / "no-lock.sqlite3"), agent=agent), headers={"Origin": "http://localhost:8000"}) as client:
        assert client.post("/api/v1/session", json={}).status_code == 200
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(client.post, "/api/v1/searches", json=examples()["plan_request"]["value"], headers={"Idempotency-Key": str(uuid4())})
            try:
                assert agent.started.wait(timeout=2)
                assert client.get("/api/v1/trips").status_code == 200
                assert client.get("/health").status_code == 200
            finally:
                agent.release.set()
            assert future.result(timeout=5).status_code == 202

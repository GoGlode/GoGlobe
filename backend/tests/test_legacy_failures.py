import asyncio

import pytest
from fastapi.testclient import TestClient

from app.legacy_api import create_app
from app.models import SearchResult


@pytest.mark.parametrize("fault", ["wrong_id", "processing", "empty_success", "premature_done", "too_many_events", "timeout"])
def test_legacy_agent_fault_is_terminal(monkeypatch, fault):
    monkeypatch.setenv("GOGLOBE_LEGACY_TIMEOUT_SECONDS", "0.02")
    class Agent:
        async def search(self, search_id, request, scenario, emit):
            if fault == "premature_done":
                await emit("done", "premature")
            if fault == "too_many_events":
                for _ in range(102):
                    await emit("parsing", "example")
            if fault == "timeout":
                await asyncio.sleep(1)
            return SearchResult(id="wrong" if fault == "wrong_id" else search_id,
                                status="processing" if fault == "processing" else "ok", parsed=request.params)
    with TestClient(create_app(agent=Agent())) as client:
        accepted = client.post("/api/search", json={"query": "demo"}).json()
        stream = client.get(accepted["events_url"])
        assert "event: done" in stream.text
        result = client.get(accepted["result_url"]).json()
        assert result["status"] == "error"
        assert result["error"]["code"] == "SEARCH_FAILED"

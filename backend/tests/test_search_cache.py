"""TTL cache behavior and HTTP search-cache integration."""

from fastapi.testclient import TestClient
import pytest

from app.api import search as search_api
from app.cache.store import TTLCache, search_cache_key
from app.config import Settings
from app.main import app
from app.schemas.search import SearchRequest, SearchResponse, SearchStatus

DEMO = (
    "Хочу на 5 дней в Турцию в ноябре, на двоих, бюджет до 120 000 рублей. "
    "Нужен хороший отель рядом с морем и прямой перелёт"
)


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def test_ttl_expires_and_reads_do_not_extend_it():
    clock = Clock()
    cache = TTLCache(10, clock)
    cache.set("key", {"value": 1})

    clock.now = 9
    assert cache.get("key") == {"value": 1}
    clock.now = 10
    assert cache.get("key") is None
    assert "key" not in cache._d


def test_zero_ttl_disables_reads_and_writes():
    cache = TTLCache(0, Clock())
    cache.set("key", "value")

    assert cache.get("key") is None
    assert cache._d == {}
    assert Settings(_env_file=None, cache_ttl_seconds=0).cache_ttl_seconds == 0


def test_cached_values_are_independent_copies():
    cache = TTLCache(10, Clock())
    original = {"nested": [1]}
    cache.set("key", original)
    original["nested"].append(2)
    received = cache.get("key")
    received["nested"].append(3)

    assert cache.get("key") == {"nested": [1]}


def test_stable_key_normalizes_query_params_and_excludes_search_id():
    first = SearchRequest.model_validate(
        {
            "query": "  Хочу   В Турцию ",
            "search_id": "first",
            "params": {"travelers": 2, "wishes": ["sea_view", "direct_flight"]},
        }
    )
    same = SearchRequest.model_validate(
        {
            "params": {"wishes": ["direct_flight", "sea_view"], "travelers": 2},
            "search_id": "second",
            "query": "хочу в турцию",
        }
    )
    other_query = same.model_copy(update={"query": "хочу в Казань"})
    other_params = SearchRequest(query="хочу в турцию", params={"travelers": 1})

    assert search_cache_key(first) == search_cache_key(same)
    assert search_cache_key(first) != search_cache_key(other_query)
    assert search_cache_key(first) != search_cache_key(other_params)


def test_cache_hit_skips_search_and_uses_current_ids_with_terminal_sse(monkeypatch):
    calls = 0
    real_run_search = search_api.run_search

    async def counted(request, emit):
        nonlocal calls
        calls += 1
        return await real_run_search(request, emit)

    monkeypatch.setattr(search_api, "run_search", counted)
    client = TestClient(app)
    first = client.post("/api/search", json={"query": DEMO, "search_id": "first-id"})
    normalized = "  " + "   ".join(DEMO.lower().split())
    second = client.post(
        "/api/search", json={"query": normalized, "search_id": "second-id"}
    )
    generated = client.post("/api/search", json={"query": DEMO})

    assert calls == 1
    assert first.json()["search_id"] == "first-id"
    assert second.json()["search_id"] == "second-id"
    assert generated.json()["search_id"] not in {"first-id", "second-id"}
    assert first.json()["offers"][0]["data_freshness"] == (
        second.json()["offers"][0]["data_freshness"]
    )
    events = client.get("/api/search/second-id/events").text
    assert '"stage": "done"' in events
    assert '"stage": "parsing"' not in events


@pytest.mark.parametrize("status", [SearchStatus.error, SearchStatus.needs_clarification])
def test_errors_and_clarifications_are_not_cached(monkeypatch, status):
    calls = 0

    async def terminal(request, emit):
        nonlocal calls
        calls += 1
        return SearchResponse(search_id=request.search_id or "generated", status=status)

    monkeypatch.setattr(search_api, "run_search", terminal)
    client = TestClient(app)
    client.post("/api/search", json={"query": DEMO, "search_id": "one"})
    client.post("/api/search", json={"query": DEMO, "search_id": "two"})

    assert calls == 2

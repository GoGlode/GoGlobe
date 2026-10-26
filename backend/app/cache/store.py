"""Кэш, хранилище результатов и шина событий статусов. Владелец: Backend №1.

In-memory для старта; при необходимости заменить на SQLite/Redis за тем же интерфейсом.
"""
import asyncio
import hashlib
import json
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from copy import deepcopy
from time import monotonic
from typing import Any

from app.config import get_settings
from app.schemas.search import SearchEvent, SearchRequest, SearchResponse


class TTLCache:
    def __init__(self, ttl: float = 600, clock: Callable[[], float] = monotonic) -> None:
        if ttl < 0:
            raise ValueError("cache TTL cannot be negative")
        self.ttl = ttl
        self._clock = clock
        self._d: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        if self.ttl == 0:
            return None
        item = self._d.get(key)
        if not item or item[0] <= self._clock():
            self._d.pop(key, None)
            return None
        return deepcopy(item[1])

    def set(self, key: str, value: Any) -> None:
        if self.ttl == 0:
            self._d.pop(key, None)
            return
        self._d[key] = (self._clock() + self.ttl, deepcopy(value))

    def clear(self) -> None:
        self._d.clear()


def search_cache_key(request: SearchRequest) -> str:
    payload = request.model_dump(
        mode="json", by_alias=True, exclude={"search_id"}, exclude_none=True,
        exclude_defaults=True,
    )
    payload["query"] = " ".join(
        unicodedata.normalize("NFKC", request.query).casefold().split()
    )
    params = payload.get("params")
    if params and "wishes" in params:
        params["wishes"] = sorted(params["wishes"])
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


class SearchStore:
    def __init__(self) -> None:
        self.results: dict[str, SearchResponse] = {}
        self.events: dict[str, list[SearchEvent]] = defaultdict(list)
        self._cond: dict[str, asyncio.Condition] = {}

    def _c(self, sid: str) -> asyncio.Condition:
        return self._cond.setdefault(sid, asyncio.Condition())

    async def emit(self, sid: str, event: SearchEvent) -> None:
        async with self._c(sid):
            self.events[sid].append(event)
            self._c(sid).notify_all()

    async def stream(self, sid: str):
        """Отдаёт накопленные события и ждёт новые до стадии done/error."""
        i = 0
        while True:
            async with self._c(sid):
                await self._c(sid).wait_for(lambda i=i: len(self.events[sid]) > i)
                batch = self.events[sid][i:]
            for ev in batch:
                i += 1
                yield ev
                if ev.stage in ("done", "error"):
                    return

    def clear(self) -> None:
        self.results.clear()
        self.events.clear()
        self._cond.clear()


store = SearchStore()
cache = TTLCache(get_settings().cache_ttl_seconds)

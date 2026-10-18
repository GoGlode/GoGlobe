"""Кэш, хранилище результатов и шина событий статусов. Владелец: Backend №1.

In-memory для старта; при необходимости заменить на SQLite/Redis за тем же интерфейсом.
"""
import asyncio
import time
from collections import defaultdict
from typing import Any

from app.schemas.search import SearchEvent, SearchResponse


class TTLCache:
    def __init__(self, ttl: float = 600) -> None:
        self.ttl = ttl
        self._d: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._d.get(key)
        if not item or item[0] < time.time():
            self._d.pop(key, None)
            return None
        return item[1]

    def set(self, key: str, value: Any) -> None:
        self._d[key] = (time.time() + self.ttl, value)


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


store = SearchStore()
cache = TTLCache()

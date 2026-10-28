"""Кэш, хранилище результатов и шина событий статусов. Владелец: Backend №1.

In-memory для старта; при необходимости заменить на SQLite/Redis за тем же интерфейсом.

Жизненный цикл SSE (после прогона на падения 27.10.2026):
* `begin(search_id)` сбрасывает события прошлого прогона с тем же id (F-05);
* `stream()` не висит вечно: если событий нет `sse_idle_timeout` секунд —
  отдаётся `error`-событие и поток закрывается (F-06);
* результаты и события живут `ttl` секунд и ограничены `max_searches` (F-11).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

from app.config import get_settings
from app.schemas.search import SearchEvent, SearchResponse

logger = logging.getLogger(__name__)


class TTLCache:
    def __init__(self, ttl: float = 600) -> None:
        self.ttl = ttl
        self._d: dict[str, tuple[float, object]] = {}

    def get(self, key: str) -> object | None:
        item = self._d.get(key)
        if not item or item[0] < time.time():
            self._d.pop(key, None)
            return None
        return item[1]

    def set(self, key: str, value: object) -> None:
        self._d[key] = (time.time() + self.ttl, value)


class SearchStore:
    """Результаты поисков + шина событий. Один процесс, без внешнего хранилища."""

    def __init__(self, ttl: float = 900.0, max_searches: int = 200) -> None:
        self._ttl = ttl
        self._max_searches = max_searches
        self.results: dict[str, SearchResponse] = {}
        self.events: dict[str, list[SearchEvent]] = defaultdict(list)
        self._expires: dict[str, float] = {}
        self._cond: dict[str, asyncio.Condition] = {}

    # -- служебное ---------------------------------------------------------

    def _c(self, sid: str) -> asyncio.Condition:
        return self._cond.setdefault(sid, asyncio.Condition())

    def _touch(self, sid: str) -> None:
        self._expires[sid] = time.time() + self._ttl
        self._prune()

    def _prune(self) -> None:
        """Удаляет просроченные поиски и самые старые сверх лимита."""
        now = time.time()
        expired = [sid for sid, ts in self._expires.items() if ts < now]
        if not expired and len(self._expires) <= self._max_searches:
            return
        if not expired:
            ordered = sorted(self._expires, key=lambda s: self._expires[s])
            expired = ordered[: max(1, len(ordered) - self._max_searches)]
        for sid in expired:
            self._forget(sid)

    def _forget(self, sid: str) -> None:
        self.events.pop(sid, None)
        self.results.pop(sid, None)
        self._expires.pop(sid, None)
        self._cond.pop(sid, None)

    # -- запись ------------------------------------------------------------

    async def begin(self, sid: str) -> None:
        """Новый прогон поиска: старые события и результат по этому id не переиспользуются."""
        async with self._c(sid):
            self.events[sid] = []
            self.results.pop(sid, None)
            self._touch(sid)
            self._c(sid).notify_all()

    async def emit(self, sid: str, event: SearchEvent) -> None:
        async with self._c(sid):
            self.events[sid].append(event)
            self._touch(sid)
            self._c(sid).notify_all()

    def put_result(self, response: SearchResponse) -> None:
        self.results[response.search_id] = response
        self._touch(response.search_id)

    def get_result(self, sid: str) -> SearchResponse | None:
        self._prune()
        return self.results.get(sid)

    # -- чтение ------------------------------------------------------------

    async def stream(self, sid: str):
        """Отдаёт события поиска до стадии done/error или до таймаута ожидания."""
        idle_timeout = get_settings().sse_idle_timeout
        i = 0
        while True:
            timed_out = False
            async with self._c(sid):
                if len(self.events[sid]) <= i:
                    try:
                        await asyncio.wait_for(
                            self._c(sid).wait_for(lambda i=i: len(self.events[sid]) > i),
                            timeout=idle_timeout,
                        )
                    except TimeoutError:
                        timed_out = True
                batch = self.events[sid][i:]
            if timed_out and not batch:
                logger.info("SSE: события для search_id=%s не найдены, закрываю поток", sid)
                yield SearchEvent(
                    stage="error",
                    message=(
                        "События для этого поиска не найдены. "
                        "Проверьте search_id или запустите поиск заново."
                    ),
                )
                return
            for ev in batch:
                i += 1
                yield ev
                if ev.stage in ("done", "error"):
                    return


store = SearchStore()
cache = TTLCache()
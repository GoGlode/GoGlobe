"""Точка интеграции Backend №2. HTTP-слой не зависит от реализации агента."""
from collections.abc import Awaitable, Callable
from typing import Protocol

from app.models import Scenario, SearchRequest, SearchResult

Emit = Callable[[str, str], Awaitable[None]]


class SearchAgent(Protocol):
    async def search(
        self, search_id: str, request: SearchRequest, scenario: Scenario, emit: Emit
    ) -> SearchResult: ...


# После выдачи API здесь можно определить отдельные порты FlightSearch,
# HotelSearch и DestinationSearch; реальные DTO провайдеров остаются в адаптерах.

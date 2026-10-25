"""AI-агент (оркестратор): 6 шагов из архитектуры. Владелец: Backend №2.

  1 анализ запроса -> 2 план поиска -> 3 вызов инструментов ->
  4 проверка/валидация -> 5 ранжирование и объяснение -> 6 структурированный ответ

Статусы каждого шага уходят через `emit` в SSE (/api/search/{id}/events).

Модуль 1 (parse_mock / parse_llm) и Модуль 2 (build_search_plan) интегрированы
в единый пайплайн. Переключение GOGLOBE_PARSER=llm активирует LLM-парсер.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from app.config import get_settings
from app.integrations.registry import get_providers
from app.schemas.search import (
    Flight,
    Hotel,
    Offer,
    SearchEvent,
    SearchRequest,
    SearchResponse,
    SearchStatus,
)

from . import explain as ex
from . import ranking, validation
from .parser import missing_question, parse_llm, parse_mock
from .tools import build_search_plan, destination_search, flight_search, hotel_search

logger = logging.getLogger(__name__)


async def run_search(req: SearchRequest, emit) -> SearchResponse:
    sid = req.search_id or uuid.uuid4().hex[:12]
    settings = get_settings()
    delay = settings.mock_stage_delay if settings.providers == "mock" else 0
    warnings: list[str] = []

    async def stage(name: str, msg: str) -> None:
        await emit(sid, SearchEvent(stage=name, message=msg))
        if delay:
            await asyncio.sleep(delay)

    # 1. Анализ запроса (Модуль 1)
    await stage("parsing", "Разбираю запрос…")

    if settings.parser == "llm":
        parsed, clarifying = await parse_llm(req.query, req.params)
    else:
        parsed = parse_mock(req.query, req.params)
        clarifying = missing_question(parsed)

    # Предупреждения парсера (например, о неполных датах) пробрасываем вверх
    warnings.extend(parsed.warnings)

    # 2. Планирование поиска (Модуль 2)
    plan = build_search_plan(parsed, clarifying_question=clarifying)

    if not plan.can_proceed:
        q = plan.clarifying_question or "Уточните, пожалуйста, параметры запроса."
        await emit(sid, SearchEvent(stage="done", message=q))
        return SearchResponse(
            search_id=sid,
            status=SearchStatus.needs_clarification,
            parsed=parsed,
            clarifying_question=q,
        )

    # Публикуем сообщения из плана как SSE-статусы (шаг 2 → клиент)
    for step in plan.steps:
        await emit(sid, SearchEvent(stage=step.stage, message=step.message))

    # 3. Вызов инструментов (по плану)
    dest_info = await destination_search(parsed.destination, parsed.dates)
    if dest_info:
        if dest_info.season_status:
            warnings.append(f"Сезонность: {dest_info.season_status}")
        if dest_info.temperature_c is not None:
            warnings.append(f"Средняя температура в регионе: {dest_info.temperature_c}°C")
    flights_p, hotels_p = get_providers()
    await stage("flights", f"Ищу перелёты: {parsed.destination}…")
    flights = await flight_search(
        flights_p, parsed.destination, parsed.dates, parsed.travelers, warnings
    )
    await stage("hotels", "Ищу отели…")
    hotels = await hotel_search(
        hotels_p, parsed.destination, parsed.dates, parsed.travelers, warnings
    )

    # 4. Валидация
    await stage("validating", "Проверяю бюджет и даты…")
    if "direct_flight" in parsed.wishes:
        flights = [f for f in flights if f.direct] or flights
    combos = []
    for f in flights:
        for h in hotels:
            if not validation.is_available(h):
                continue
            total = validation.total_price(f, h)
            if validation.within_budget(total, parsed.budget):
                combos.append((f, h, total))
    if any(h.available is None for h in hotels):
        warnings.append("Нет данных о наличии для части вариантов")

    # 5. Ранжирование и объяснение
    await stage("ranking", "Ранжирую и объясняю варианты…")
    offers: list[Offer] = []
    for f, h, total in combos:
        offers.append(
            Offer(
                id=f"offer_{f.id}_{h.id}",
                destination=h.destination,
                hotel=Hotel(
                    name=h.name,
                    stars=h.stars,
                    rating=h.rating,
                    photos=h.photos,
                    price=h.price_per_night,
                    distance_to_sea_m=h.distance_to_sea_m,
                ),
                flight=Flight(direct=f.direct, dates=f.dates, price=f.price, carrier=f.carrier),
                total_price=total,
                explanation=ex.explain(
                    h, f, total, parsed.budget, parsed.wishes, dest_info=dest_info
                ),
                booking_url=h.booking_url,
                data_freshness=min(f.fetched_at, h.fetched_at)
                if f.fetched_at
                else datetime.now(UTC).isoformat(),
                score=ranking.score(h, f, total, parsed.budget, parsed.wishes),
            )
        )
    offers.sort(key=lambda o: o.score or 0, reverse=True)

    # 6. Ответ
    status = SearchStatus.ok if offers else SearchStatus.empty
    if offers and warnings:
        status = SearchStatus.partial
    if not offers:
        warnings.append("Ничего не найдено: попробуйте увеличить бюджет или изменить даты")
    await emit(sid, SearchEvent(stage="done", message="Готово"))
    return SearchResponse(
        search_id=sid, status=status, parsed=parsed, offers=offers[:10], warnings=warnings
    )

"""AI-агент (оркестратор): 6 шагов из архитектуры. Владелец: Backend №2.

  1 анализ запроса -> 2 план поиска -> 3 вызов инструментов ->
  4 проверка/валидация -> 5 ранжирование и объяснение -> 6 структурированный ответ

Статусы каждого шага уходят через `emit` в SSE (/api/search/{id}/events).

Модуль 1 (parse_mock / parse_llm) и Модуль 2 (build_search_plan) интегрированы
в единый пайплайн. Переключение GOGLOBE_PARSER=llm активирует LLM-парсер.

Правила статусов (после прогона на падения 27.10.2026):
* `ok` — есть варианты и нет предупреждений о деградации данных;
* `partial` — есть варианты, но какой-то источник/поле недоступны (F-04);
* сезонность и температура — это справка, она идёт в explanation.pros, а не в warnings.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from app.agent import explain as ex
from app.agent import ranking, validation
from app.agent.currency import convert, norm_currency, normalize_budget
from app.agent.parser import missing_question, parse_llm, parse_mock
from app.agent.tools import build_search_plan, destination_search, flight_search, hotel_search
from app.config import get_settings
from app.integrations.registry import get_providers
from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import (
    Flight,
    Hotel,
    Money,
    Offer,
    SearchEvent,
    SearchRequest,
    SearchResponse,
    SearchStatus,
)

logger = logging.getLogger(__name__)


def _effective_travelers(parsed_travelers: int | None) -> int:
    """Минимум один путешественник: None/0 не должны ронять провайдеров (F-01)."""
    if parsed_travelers is None or parsed_travelers < 1:
        return 1
    return parsed_travelers


def _combined_total(f: FlightOption, h: HotelOption) -> tuple[Money | None, str | None]:
    """Итоговая цена в одной валюте или None, если пересчитать нечем (F-09).

    Возвращает (итог, пояснение к предупреждению). Неподтверждённую сумму не
    показываем: лучше пропустить вариант, чем выдать «10000 + 100» за деньги.
    """
    try:
        return validation.total_price(f, h), None
    except validation.CurrencyMismatchError:
        flight_currency = norm_currency(f.price.currency)
        hotel_currency = norm_currency(h.price_per_night.currency)
        hotel_night = convert(h.price_per_night.amount, hotel_currency, flight_currency)
        if hotel_night is None:
            return None, (
                f"Отель «{h.name}»: цена в {hotel_currency}, перелёт в {flight_currency}, "
                "надёжного курса нет — итоговая сумма не подтверждена, вариант не показан"
            )
        total = Money(
            amount=f.price.amount + hotel_night * validation.nights(f.dates),
            currency=flight_currency,
        )
        return total, (
            f"Отель «{h.name}»: цена пересчитана из {hotel_currency} в {flight_currency} "
            "по демо-курсу, итог ориентировочный"
        )


def _dedupe(items: list[str]) -> list[str]:
    """Убирает повторы предупреждений (одна причина — одно сообщение)."""
    return list(dict.fromkeys(items))


def _data_freshness(*stamps: str) -> str:
    """Самая старая валидная ISO-метка; пустые строки не проходят (F-16)."""
    valid: list[str] = []
    for stamp in stamps:
        if not stamp:
            continue
        try:
            datetime.fromisoformat(stamp)
        except ValueError:
            continue
        valid.append(stamp)
    return min(valid) if valid else datetime.now(UTC).isoformat()


async def run_search(req: SearchRequest, emit) -> SearchResponse:
    sid = req.search_id or uuid.uuid4().hex[:12]
    settings = get_settings()
    delay = settings.mock_stage_delay if settings.providers == "mock" else 0
    warnings: list[str] = []

    # Сообщения стадий берём из плана (Модуль 2), чтобы клиент видел один поток
    # статусов, а не дубли: сначала «план», затем «выполнение».
    stage_messages: dict[str, str] = {}

    async def stage(name: str, default_msg: str) -> None:
        await emit(sid, SearchEvent(stage=name, message=stage_messages.get(name, default_msg)))
        if delay:
            await asyncio.sleep(delay)

    # 1. Анализ запроса (Модуль 1)
    await stage("parsing", "Разбираю запрос…")

    if settings.parser == "llm":
        parsed, clarifying = await parse_llm(req.query, req.params)
    else:
        parsed = parse_mock(req.query, req.params)
        clarifying = missing_question(parsed)

    # Предупреждения парсера (например, о неполных датах) пробрасываем вверх (F-14)
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
            warnings=warnings,
        )

    # Публикуем сообщения из плана как SSE-статусы (шаг 2 → клиент).
    # Не отправляем их сразу: иначе клиент видит по два события на каждую стадию
    # («план» и «выполнение»). Сообщение из плана уходит в момент реального шага.
    for step in plan.steps:
        stage_messages.setdefault(step.stage, step.message)

    # 3. Вызов инструментов (по плану)
    dest_info = await destination_search(parsed.destination, parsed.dates)
    travelers = _effective_travelers(parsed.travelers)

    # Сезонность/погода — справка для explanation.pros, а не деградация данных (F-04).
    if dest_info is not None and dest_info.temperature_c is None:
        warnings.append(
            f"Нет климатических данных для «{parsed.destination}»: сезонность не проверена"
        )

    flights_p, hotels_p = get_providers()
    await stage("flights", f"Ищу перелёты: {parsed.destination}…")
    flights = await flight_search(flights_p, parsed.destination, parsed.dates, travelers, warnings)
    await stage("hotels", "Ищу отели…")
    hotels = await hotel_search(hotels_p, parsed.destination, parsed.dates, travelers, warnings)

    if not flights and not hotels:
        warnings.append(
            f"Нет данных по направлению «{parsed.destination}»: "
            "подключённые источники его пока не покрывают"
        )

    # 4. Валидация
    await stage("validating", "Проверяю бюджет и даты…")

    # Бюджет пользователя может быть в другой валюте — приводим к валюте цен (F-09)
    price_currency = flights[0].price.currency if flights else "RUB"
    budget, budget_note = normalize_budget(parsed.budget, price_currency)
    if budget_note:
        warnings.append(budget_note)

    if "direct_flight" in parsed.wishes:
        # Требование прямого рейса — жёсткое ограничение: пересадки не подмешиваются
        # обратно, даже если прямых рейсов нет (F-20).
        direct_flights = [f for f in flights if f.direct]
        if flights and not direct_flights:
            warnings.append(
                f"Прямых рейсов в «{parsed.destination}» не найдено: "
                "варианты с пересадками не предлагаются"
            )
        flights = direct_flights

    combos = []
    for f in flights:
        for h in hotels:
            if not validation.is_available(h):
                continue
            total, total_note = _combined_total(f, h)
            if total_note:
                warnings.append(total_note)
            if total is None:
                continue  # валюты не сводятся — итоговую цену не показываем (F-09)
            if total.amount <= 0:
                continue  # отрицательная/нулевая цена — не предлагаем (F-07)
            if validation.within_budget(total, budget):
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
                explanation=ex.explain(h, f, total, budget, parsed.wishes, dest_info=dest_info),
                booking_url=h.booking_url,
                data_freshness=_data_freshness(f.fetched_at, h.fetched_at),
                score=ranking.score(h, f, total, budget, parsed.wishes),
            )
        )
    offers.sort(key=lambda o: o.score or 0, reverse=True)

    # 6. Ответ
    if offers:
        status = SearchStatus.partial if warnings else SearchStatus.ok
    else:
        status = SearchStatus.empty
        warnings.append("Ничего не найдено: попробуйте увеличить бюджет или изменить даты")

    warnings = _dedupe(warnings)

    await emit(sid, SearchEvent(stage="done", message="Готово"))
    return SearchResponse(
        search_id=sid, status=status, parsed=parsed, offers=offers[:10], warnings=warnings
    )

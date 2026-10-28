"""Модуль 2: Реестр инструментов агента (Tools) и планировщик поиска (Search Planner).

Владелец: Backend №2.

Соответствует слайдам 03, 05 и схеме архитектуры GoGlobe:
1. Destination Search Tool: сезонность, погода, локации, достопримечательности.
2. Flight Search Tool: перелёты, даты, прямой/пересадки, цены.
3. Hotel Search Tool: отели, звёзды, рейтинг, фото, расстояние до моря.
4. Validation Tool: проверка бюджета, дат, согласованности, статуса доступности.
5. Ranking Tool: расчёт прозрачного скоринга 0..1 по полезности.
6. Explain Tool: формирование объяснения выбора («почему подходит», плюсы, минусы).

Правило честности: все цены/наличие/характеристики берутся ТОЛЬКО из ответов инструментов.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum

from app.agent.currency import format_money
from app.agent.explain import explain as explain_tool
from app.agent.ranking import score as rank_score
from app.agent.validation import (
    CurrencyMismatchError,
    is_available,
    total_price,
    within_budget,
)
from app.integrations.base import FlightProvider, HotelProvider, ProviderError
from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange, Explanation, Money, ParsedQuery

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Реестр инструментов и стадии SSE
# ---------------------------------------------------------------------------


class AgentToolName(StrEnum):
    """Инструменты AI-агента согласно архитектурной схеме GoGlobe."""

    DESTINATION_SEARCH = "destination_search_tool"
    FLIGHT_SEARCH = "flight_search_tool"
    HOTEL_SEARCH = "hotel_search_tool"
    VALIDATION = "validation_tool"
    RANKING = "ranking_tool"
    EXPLAIN = "explain_tool"


class SearchStage(StrEnum):
    """Стадии SSE-стриминга по API-контракту v0 (GET /api/search/{id}/events)."""

    PARSING = "parsing"
    FLIGHTS = "flights"
    HOTELS = "hotels"
    VALIDATING = "validating"
    RANKING = "ranking"
    DONE = "done"


@dataclass(frozen=True)
class PlannedToolStep:
    """Один запланированный шаг вызова инструмента со статусом для SSE."""

    tool: AgentToolName
    stage: SearchStage
    message: str
    required: bool = True
    filters: dict[str, object] = field(default_factory=dict)


@dataclass
class SearchExecutionPlan:
    """План выполнения поиска, формируемый на Шаге 2 работы AI-агента."""

    can_proceed: bool
    clarifying_question: str | None
    steps: list[PlannedToolStep] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Инструмент 1: Destination Search Tool
# ---------------------------------------------------------------------------


@dataclass
class DestinationInfo:
    """Справочная информация о локации, погоде и сезонности.

    `is_reference=True` означает: это статическая справка MVP, а не прогноз и не
    данные провайдера. Такие сведения нельзя использовать как доказательство
    пригодности варианта — только как пояснение с пометкой «справочно».
    При интеграции заменяется destination-провайдером Backend №1.
    """

    destination: str
    season_status: str = "Рекомендуемый сезон"
    temperature_c: int | None = None
    highlights: list[str] = field(default_factory=list)
    is_reference: bool = True
    source: str = "static_reference"


_DESTINATION_KNOWLEDGE: dict[str, DestinationInfo] = {
    "турци": DestinationInfo(
        destination="Турция",
        season_status="Бархатный сезон / мягкая осень",
        temperature_c=22,
        highlights=["Анталийское побережье", "Старый город Калеичи", "Средиземное море"],
    ),
    "сочи": DestinationInfo(
        destination="Сочи, Россия",
        season_status="Осенний отдых у моря и горный кластер",
        temperature_c=16,
        highlights=["Олимпийский парк", "Красная Поляна", "Набережная"],
    ),
    "дубай": DestinationInfo(
        destination="Дубай, ОАЭ",
        season_status="Идеальный пляжный сезон",
        temperature_c=30,
        highlights=["Бурдж-Халифа", "Marina Beach", "Palm Jumeirah"],
    ),
    "египет": DestinationInfo(
        destination="Египет",
        season_status="Комфортный пляжный сезон",
        temperature_c=27,
        highlights=["Красное море", "Коралловые рифы", "Дайвинг"],
    ),
    "таиланд": DestinationInfo(
        destination="Таиланд",
        season_status="Старт сухого высокого сезона",
        temperature_c=31,
        highlights=["Пляжи Пхукета", "Тайская кухня", "Острова Пхи-Пхи"],
    ),
}


async def destination_search(
    destination: str | None, dates: DateRange | None = None
) -> DestinationInfo | None:
    """Инструмент проверки локаций, сезонности и погоды."""
    if not destination:
        return None
    d_lower = destination.lower()
    for stem, info in _DESTINATION_KNOWLEDGE.items():
        if stem in d_lower:
            return info
    return DestinationInfo(destination=destination, season_status="Информация по сезону доступна")


# ---------------------------------------------------------------------------
# Инструмент 2 и 3: Flight Search & Hotel Search Tools
# ---------------------------------------------------------------------------


async def flight_search(
    p: FlightProvider, dest: str, dates: DateRange, n: int, warnings: list[str]
) -> list[FlightOption]:
    """Flight Search Tool: вызов провайдера перелётов с изоляцией сбоев."""
    try:
        # Страховка от None/0: провайдеры умножают цену на число путешественников (F-01).
        return await p.search(dest, dates, max(1, int(n or 1)))
    except ProviderError as e:
        warnings.append(f"Перелёты временно недоступны: {e}")
        return []


async def hotel_search(
    p: HotelProvider, dest: str, dates: DateRange, n: int, warnings: list[str]
) -> list[HotelOption]:
    """Hotel Search Tool: вызов провайдера отелей с изоляцией сбоев."""
    try:
        return await p.search(dest, dates, max(1, int(n or 1)))
    except ProviderError as e:
        warnings.append(f"Отели временно недоступны: {e}")
        return []


# ---------------------------------------------------------------------------
# Инструмент 4: Validation Tool (проверка ограничений)
# ---------------------------------------------------------------------------


def validate_combo(
    flight: FlightOption,
    hotel: HotelOption,
    budget: Money | None,
    direct_only: bool = False,
) -> tuple[bool, Money | None]:
    """Validation Tool: проверяет соответствие пары перелёт+отель ограничениям.

    Если валюты перелёта и отеля не сводятся без пересчёта, вариант отклоняется
    (итоговая сумма не подтверждена) — см. `validation.CurrencyMismatchError`.
    """
    if direct_only and not flight.direct:
        return False, None
    if not is_available(hotel):
        return False, None

    try:
        total = total_price(flight, hotel)
    except CurrencyMismatchError:
        return False, None
    if not within_budget(total, budget):
        return False, total

    return True, total


# ---------------------------------------------------------------------------
# Инструмент 5 и 6: Ranking & Explain Tools
# ---------------------------------------------------------------------------


def ranking_tool(
    hotel: HotelOption,
    flight: FlightOption,
    total: Money,
    budget: Money | None,
    wishes: list[str],
) -> float:
    """Ranking Tool: расчёт прозрачного скоринга соответствия запросу (0..1)."""
    return rank_score(hotel, flight, total, budget, wishes)


def explain_option(
    hotel: HotelOption,
    flight: FlightOption,
    total: Money,
    budget: Money | None,
    wishes: list[str],
    dest_info: object | None = None,
) -> Explanation:
    """Explain Tool: понятное и честное объяснение выбора без выдумок."""
    return explain_tool(hotel, flight, total, budget, wishes, dest_info=dest_info)


# ---------------------------------------------------------------------------
# Планировщик поиска (Search Planner)
# ---------------------------------------------------------------------------


def build_search_plan(
    parsed: ParsedQuery, clarifying_question: str | None = None
) -> SearchExecutionPlan:
    """Формирует последовательность вызовов инструментов на основе разобранного запроса.

    Если есть уточняющий вопрос (missing_question или из LLM) — план блокирует дальнейший
    поиск и возвращает needs_clarification.
    """
    if clarifying_question is not None:
        return SearchExecutionPlan(
            can_proceed=False,
            clarifying_question=clarifying_question,
            steps=[],
        )

    dest_label = parsed.destination or "выбранному направлению"
    direct_only = "direct_flight" in parsed.wishes
    sea_view = "sea_view" in parsed.wishes

    flight_msg = (
        f"Ищу прямые перелёты: {dest_label}…" if direct_only else f"Ищу перелёты: {dest_label}…"
    )
    hotel_msg = (
        f"Подбираю отели у моря ({dest_label})…" if sea_view else f"Подбираю отели в {dest_label}…"
    )

    budget_max = parsed.budget.amount if parsed.budget else None
    budget_currency = parsed.budget.currency if parsed.budget else "RUB"
    travelers = parsed.travelers if parsed.travelers and parsed.travelers >= 1 else 1

    steps = [
        PlannedToolStep(
            tool=AgentToolName.DESTINATION_SEARCH,
            stage=SearchStage.PARSING,
            message=f"Проверяю локации и сезонность: {dest_label}…",
            required=False,
            filters={"destination": parsed.destination},
        ),
        PlannedToolStep(
            tool=AgentToolName.FLIGHT_SEARCH,
            stage=SearchStage.FLIGHTS,
            message=flight_msg,
            required=True,
            filters={
                "destination": parsed.destination,
                "direct_only": direct_only,
                "travelers": travelers,
            },
        ),
        PlannedToolStep(
            tool=AgentToolName.HOTEL_SEARCH,
            stage=SearchStage.HOTELS,
            message=hotel_msg,
            required=True,
            filters={
                "destination": parsed.destination,
                "wishes": parsed.wishes,
                "travelers": travelers,
            },
        ),
        PlannedToolStep(
            tool=AgentToolName.VALIDATION,
            stage=SearchStage.VALIDATING,
            message=(
                f"Проверяю полную стоимость (бюджет до {format_money(parsed.budget)})…"
                if parsed.budget
                else "Проверяю доступность и согласованность дат…"
            ),
            required=True,
            filters={"max_budget": budget_max, "currency": budget_currency},
        ),
        PlannedToolStep(
            tool=AgentToolName.RANKING,
            stage=SearchStage.RANKING,
            message="Ранжирую лучшие комбинации и формирую объяснение выбора…",
            required=True,
            filters={"wishes": parsed.wishes},
        ),
    ]

    return SearchExecutionPlan(
        can_proceed=True,
        clarifying_question=None,
        steps=steps,
    )

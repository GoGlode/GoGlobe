"""Инструменты агента (Tools) и планировщик поиска (Search Planner).

Владелец: Backend №2.

Содержит:
- Декларацию 6 инструментов AI-агента из архитектурной схемы (AgentToolName).
- Стадии SSE-стриминга (SearchStage).
- Планировщик последовательности шагов (build_search_plan).
- Тонкие обёртки над провайдерами Backend №1 (flight_search, hotel_search).

Правило: все цены/наличие/характеристики берутся ТОЛЬКО из ответов инструментов.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.integrations.base import FlightProvider, HotelProvider, ProviderError
from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange, ParsedQuery

# ---------------------------------------------------------------------------
# Модуль 2: Декларация инструментов агента (из архитектурной схемы GoGlobe)
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


def build_search_plan(
    parsed: ParsedQuery, clarifying_question: str | None = None
) -> SearchExecutionPlan:
    """Формирует последовательность вызовов инструментов на основе разобранного запроса.

    Если есть уточняющий вопрос (missing_question или из LLM) — план не выполняется,
    а возвращается вопрос.
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
        f"Ищу прямые перелёты в {dest_label}…" if direct_only else f"Ищу перелёты в {dest_label}…"
    )
    hotel_msg = (
        f"Подбираю отели у моря ({dest_label})…" if sea_view else f"Подбираю отели в {dest_label}…"
    )

    budget_max = parsed.budget.amount if parsed.budget else None
    budget_currency = parsed.budget.currency if parsed.budget else "RUB"

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
                "travelers": parsed.travelers or 1,
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
                "travelers": parsed.travelers or 1,
            },
        ),
        PlannedToolStep(
            tool=AgentToolName.VALIDATION,
            stage=SearchStage.VALIDATING,
            message=(
                f"Проверяю полную стоимость (бюджет до {budget_max:,} {budget_currency})…".replace(
                    ",", " "
                )
                if budget_max
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


# ---------------------------------------------------------------------------
# Обёртки над провайдерами Backend №1 (используются в orchestrator.py)
# ---------------------------------------------------------------------------


async def flight_search(
    p: FlightProvider, dest: str, dates: DateRange, n: int, warnings: list[str]
) -> list[FlightOption]:
    try:
        return await p.search(dest, dates, n)
    except ProviderError as e:  # таймаут/ошибка источника -> честный warning
        warnings.append(f"Перелёты недоступны: {e}")
        return []


async def hotel_search(
    p: HotelProvider, dest: str, dates: DateRange, n: int, warnings: list[str]
) -> list[HotelOption]:
    try:
        return await p.search(dest, dates, n)
    except ProviderError as e:
        warnings.append(f"Отели недоступны: {e}")
        return []

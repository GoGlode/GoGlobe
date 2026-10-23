"""Тесты первых 2 модулей AI-агента: разбор запросов (Модуль 1) и планирование инструментов (Модуль 2).

Закрывает пункт чек-листа из роадмапа (18–22 октября):
«набор тестовых запросов с ожидаемым разбором».
"""

import pytest
from fastapi.testclient import TestClient

from app.agent.parser import missing_question, parse_mock
from app.agent.tools import AgentToolName, SearchStage, build_search_plan
from app.config import get_settings
from app.main import app

# ---------------------------------------------------------------------------
# Модуль 1: Тесты парсера (parse_mock + missing_question)
# ---------------------------------------------------------------------------


def test_parse_reference_demo_query() -> None:
    """Проверка эталонного демо-запроса из README и презентации."""
    query = (
        "Хочу на 5 дней в Турцию в ноябре, на двоих, бюджет до 120 000 рублей. "
        "Нужен хороший отель рядом с морем и прямой перелёт"
    )
    parsed = parse_mock(query)

    assert parsed.destination == "Турция"
    assert parsed.duration_days == 5
    assert parsed.dates is not None
    assert parsed.travelers == 2
    assert parsed.budget is not None
    assert parsed.budget.amount == 120000
    assert parsed.budget.currency == "RUB"
    assert "sea_view" in parsed.wishes
    assert "direct_flight" in parsed.wishes
    assert missing_question(parsed) is None


def test_parse_minimal_complete_query() -> None:
    """Минимально полный запрос — парсер должен извлечь всё без уточнений."""
    query = "Сочи на 4 дня в ноябре с девушкой, бюджет 60к, отель у моря и прямой рейс"
    parsed = parse_mock(query)

    assert parsed.destination == "Сочи, Россия"
    assert parsed.duration_days == 4
    assert parsed.travelers == 2
    assert parsed.budget is not None
    assert parsed.budget.amount == 60000
    assert "sea_view" in parsed.wishes
    assert "direct_flight" in parsed.wishes
    assert missing_question(parsed) is None


def test_parse_incomplete_no_destination() -> None:
    """Нет направления — агент должен задать уточняющий вопрос, а не угадывать."""
    query = "Хочу куда-нибудь к морю вдвоем недорого"
    parsed = parse_mock(query)

    assert parsed.destination is None
    q = missing_question(parsed)
    assert q is not None
    assert "куда" in q.lower() or "поехать" in q.lower()


def test_parse_incomplete_no_dates() -> None:
    """Есть направление, но нет дат — уточняющий вопрос про даты."""
    query = "хочу в Турцию"
    parsed = parse_mock(query)

    assert parsed.destination is not None
    q = missing_question(parsed)
    assert q is not None
    assert "дат" in q.lower()


def test_parse_all_inclusive_wish() -> None:
    """Пожелание 'все включено' нормализуется в тег all_inclusive."""
    query = "Египет на 7 ночей, всё включено, один человек"
    parsed = parse_mock(query)

    assert parsed.destination == "Египет"
    assert parsed.duration_days == 7
    assert parsed.travelers == 1
    assert "all_inclusive" in parsed.wishes


def test_parse_solo_traveler() -> None:
    """Одиночный путешественник."""
    query = "Хочу один на 3 дня в Таиланд в январе, до 80к"
    parsed = parse_mock(query)

    assert parsed.travelers == 1
    assert parsed.destination == "Таиланд"
    assert parsed.budget is not None
    assert parsed.budget.amount == 80000


# ---------------------------------------------------------------------------
# Модуль 2: Тесты планировщика (build_search_plan)
# ---------------------------------------------------------------------------


def test_search_planner_creates_tool_sequence() -> None:
    """Модуль 2 строит корректный план вызова инструментов для полного запроса."""
    query = "Сочи на 4 дня в ноябре с девушкой, бюджет 60к, отель у моря и прямой рейс"
    parsed = parse_mock(query)
    plan = build_search_plan(parsed, clarifying_question=missing_question(parsed))

    assert plan.can_proceed is True
    tool_order = [step.tool for step in plan.steps]
    assert tool_order == [
        AgentToolName.DESTINATION_SEARCH,
        AgentToolName.FLIGHT_SEARCH,
        AgentToolName.HOTEL_SEARCH,
        AgentToolName.VALIDATION,
        AgentToolName.RANKING,
    ]


def test_search_planner_sse_stages_match_contract() -> None:
    """SSE-стадии в плане совпадают с контрактом v0."""
    query = "Хочу на 5 дней в Турцию в ноябре, на двоих, до 120 000 рублей"
    parsed = parse_mock(query)
    plan = build_search_plan(parsed, clarifying_question=missing_question(parsed))

    stages = [step.stage for step in plan.steps]
    assert SearchStage.PARSING in stages
    assert SearchStage.FLIGHTS in stages
    assert SearchStage.HOTELS in stages
    assert SearchStage.VALIDATING in stages
    assert SearchStage.RANKING in stages


def test_search_planner_incomplete_query_no_proceed() -> None:
    """Неполный запрос → план не выполняется, возвращается уточняющий вопрос."""
    query = "хочу куда-нибудь отдохнуть"
    parsed = parse_mock(query)
    clarifying = missing_question(parsed)
    plan = build_search_plan(parsed, clarifying_question=clarifying)

    assert plan.can_proceed is False
    assert plan.clarifying_question is not None
    assert plan.steps == []


def test_planner_direct_flight_filter_in_plan() -> None:
    """Если пользователь хочет прямой рейс — фильтр direct_only в плане flight_search."""
    query = "Турция на 5 дней в ноябре, вдвоем, прямой перелёт"
    parsed = parse_mock(query)
    plan = build_search_plan(parsed, clarifying_question=missing_question(parsed))

    flight_step = next(s for s in plan.steps if s.tool == AgentToolName.FLIGHT_SEARCH)
    assert flight_step.filters.get("direct_only") is True
    assert "прямые" in flight_step.message.lower()


def test_planner_sea_view_in_hotel_message() -> None:
    """Если пользователь хочет отель у моря — в сообщении про отели отражено."""
    query = "Турция на 5 дней в ноябре, вдвоем, отель у моря"
    parsed = parse_mock(query)
    plan = build_search_plan(parsed, clarifying_question=missing_question(parsed))

    hotel_step = next(s for s in plan.steps if s.tool == AgentToolName.HOTEL_SEARCH)
    assert "мор" in hotel_step.message.lower()


# ---------------------------------------------------------------------------
# Интеграция: Оркестратор (связка Модуля 1 + Модуля 2 → полный пайплайн)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Гарантируем mock-режим для CI."""
    monkeypatch.setattr(get_settings(), "mock_stage_delay", 0)
    monkeypatch.setattr(get_settings(), "parser", "mock")


client = TestClient(app)


def test_orchestrator_demo_full_pipeline() -> None:
    """Оркестратор проходит все 6 шагов и возвращает офферы для демо-запроса."""
    query = (
        "Хочу на 5 дней в Турцию в ноябре, на двоих, бюджет до 120 000 рублей. "
        "Нужен хороший отель рядом с морем и прямой перелёт"
    )
    r = client.post("/api/search", json={"query": query}).json()
    assert r["status"] in ("ok", "partial")
    assert r["offers"]


def test_orchestrator_needs_clarification() -> None:
    """Неполный запрос → статус needs_clarification, пустые офферы."""
    r = client.post("/api/search", json={"query": "хочу в Турцию"}).json()
    assert r["status"] == "needs_clarification"
    assert r["clarifying_question"]
    assert not r["offers"]


def test_orchestrator_events_contain_all_stages() -> None:
    """SSE-поток содержит все ожидаемые стадии от parsing до done."""
    query = (
        "Хочу на 5 дней в Турцию в ноябре, на двоих, бюджет до 120 000 рублей. "
        "Нужен хороший отель рядом с морем и прямой перелёт"
    )
    r = client.post("/api/search", json={"query": query, "search_id": "test_stages"}).json()
    assert r["status"] == "ok"
    body = client.get("/api/search/test_stages/events").text
    assert '"stage": "parsing"' in body
    assert '"stage": "flights"' in body
    assert '"stage": "hotels"' in body
    assert '"stage": "validating"' in body
    assert '"stage": "ranking"' in body
    assert '"stage": "done"' in body

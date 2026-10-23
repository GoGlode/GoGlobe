"""Тесты первых 2 модулей AI-агента: разбор запросов (Модуль 1) и планирование инструментов (Модуль 2).

Закрывает пункт чек-листа из роадмапа (18–22 октября):
«набор тестовых запросов с ожидаемым разбором».
Соответствует принципам честности данных и архитектуре GoGlobe.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agent.parser import extract_json_payload, missing_question, parse_mock
from app.agent.tools import (
    AgentToolName,
    SearchStage,
    build_search_plan,
    destination_search,
    explain_option,
    ranking_tool,
    validate_combo,
)
from app.config import get_settings
from app.main import app
from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange, Money

# ---------------------------------------------------------------------------
# Модуль 1: Тесты парсера (parse_mock, regex, даты, валюты, JSON)
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


def test_parse_exact_date_range() -> None:
    """Парсинг точного диапазона чисел: 'с 10 по 15 ноября'."""
    query = "Турция с 10 по 15 ноября на двоих до 100 000 руб"
    parsed = parse_mock(query)

    assert parsed.destination == "Турция"
    assert parsed.dates is not None
    assert parsed.dates.from_.endswith("-11-10")
    assert parsed.dates.to.endswith("-11-15")
    assert parsed.duration_days == 5
    assert parsed.travelers == 2
    assert missing_question(parsed) is None


def test_parse_week_duration_and_currencies() -> None:
    """Парсинг длительности 'на неделю' и валюты USD ($)."""
    query = "Дубай на неделю в ноябре вдвоем, бюджет около 1500$"
    parsed = parse_mock(query)

    assert parsed.destination == "Дубай, ОАЭ"
    assert parsed.duration_days == 7
    assert parsed.travelers == 2
    assert parsed.budget is not None
    assert parsed.budget.amount == 1500
    assert parsed.budget.currency == "USD"
    assert missing_question(parsed) is None


def test_parse_incomplete_no_destination() -> None:
    """Нет направления — агент должен задать уточняющий вопрос, а не угадывать."""
    query = "Хочу куда-нибудь к морю вдвоем недорого"
    parsed = parse_mock(query)

    assert parsed.destination is None
    q = missing_question(parsed)
    assert q is not None
    assert "страну" in q or "город" in q or "Куда" in q


def test_parse_incomplete_no_dates() -> None:
    """Есть направление, но нет дат/длительности — агент должен спросить даты."""
    query = "Хочу в Рим с мужем в хороший отель"
    parsed = parse_mock(query)

    assert parsed.destination == "Рим, Италия"
    assert parsed.dates is None
    q = missing_question(parsed)
    assert q is not None
    assert "даты" in q.lower() or "дней" in q.lower()


def test_parse_extended_wishes() -> None:
    """Парсинг расширенных пожеланий: all_inclusive, pool, breakfast, spa."""
    query = "Египет на 7 дней в ноябре, всё включено, бассейн и спа"
    parsed = parse_mock(query)

    assert "all_inclusive" in parsed.wishes
    assert "pool" in parsed.wishes
    assert "spa" in parsed.wishes


def test_parse_solo_and_family_travelers() -> None:
    """Парсинг соло-путешественника и семьи с ребенком."""
    parsed_solo = parse_mock("Сочи на 3 дня один в ноябре")
    assert parsed_solo.travelers == 1

    parsed_family = parse_mock("Турция на 7 дней с ребенком в ноябре")
    assert parsed_family.travelers == 3


def test_extract_json_payload_from_markdown_codeblock() -> None:
    """Проверка извлечения JSON, если модель обернула ответ в markdown."""
    llm_markdown = '```json\n{"destination": "Турция", "travelers": 2}\n```'
    extracted = extract_json_payload(llm_markdown)
    assert extracted["destination"] == "Турция"
    assert extracted["travelers"] == 2

    llm_text_surrounded = 'Вот ваш ответ:\n{"destination": "Сочи"}\nСпасибо!'
    extracted_surrounded = extract_json_payload(llm_text_surrounded)
    assert extracted_surrounded["destination"] == "Сочи"


# ---------------------------------------------------------------------------
# Модуль 2: Тесты реестра инструментов, Destination Search, Validation, Ranking
# ---------------------------------------------------------------------------


import asyncio


def test_destination_search_tool_returns_insights() -> None:
    """Destination Search Tool возвращает сезонность и достопримечательности."""
    info = asyncio.run(destination_search("Турция"))
    assert info is not None
    assert info.destination == "Турция"
    assert info.temperature_c is not None
    assert len(info.highlights) > 0


def test_search_planner_creates_tool_sequence() -> None:
    """Модуль 2 строит корректный план вызова инструментов."""
    query = "Сочи на 4 дня в ноябре с девушкой, бюджет 60к, отель у моря и прямой рейс"
    parsed = parse_mock(query)
    plan = build_search_plan(parsed)

    assert plan.can_proceed is True
    assert plan.clarifying_question is None
    tool_sequence = [step.tool for step in plan.steps]
    assert tool_sequence == [
        AgentToolName.DESTINATION_SEARCH,
        AgentToolName.FLIGHT_SEARCH,
        AgentToolName.HOTEL_SEARCH,
        AgentToolName.VALIDATION,
        AgentToolName.RANKING,
    ]


def test_search_planner_sse_stages_match_contract() -> None:
    """Стадии в плане точно соответствуют API-контракту v0."""
    parsed = parse_mock("Турция на 5 дней в ноябре на двоих")
    plan = build_search_plan(parsed)

    stages = [step.stage for step in plan.steps]
    assert stages == [
        SearchStage.PARSING,
        SearchStage.FLIGHTS,
        SearchStage.HOTELS,
        SearchStage.VALIDATING,
        SearchStage.RANKING,
    ]


def test_search_planner_incomplete_query_blocks_proceed() -> None:
    """Неполный запрос блокирует выполнение и возвращает вопрос."""
    parsed = parse_mock("хочу в Турцию")
    clarifying = missing_question(parsed)
    plan = build_search_plan(parsed, clarifying_question=clarifying)

    assert plan.can_proceed is False
    assert plan.clarifying_question == clarifying
    assert len(plan.steps) == 0


def test_validation_tool_filters_budget() -> None:
    """Validation Tool отсекает комбинации, превышающие бюджет."""
    dates = DateRange(from_="2026-11-10", to="2026-11-15")
    flight = FlightOption(
        id="f1",
        destination="Турция",
        direct=True,
        dates=dates,
        price=Money(amount=20000),
        carrier="Air",
        source="mock",
        fetched_at="",
    )
    hotel = HotelOption(
        id="h1",
        destination="Турция",
        name="Resort",
        stars=5,
        rating=4.8,
        photos=[],
        price_per_night=Money(amount=5000),
        distance_to_sea_m=100,
        available=True,
        booking_url="",
        source="mock",
        fetched_at="",
    )

    # 20 000 + 5 * 5000 = 45 000
    valid, total = validate_combo(flight, hotel, budget=Money(amount=50000))
    assert valid is True
    assert total.amount == 45000

    over_budget, _ = validate_combo(flight, hotel, budget=Money(amount=40000))
    assert over_budget is False


def test_explain_and_ranking_adhere_to_honesty() -> None:
    """Explain Tool и Ranking Tool не выдумывают факты и отмечают неподтвержденность."""
    dates = DateRange(from_="2026-11-10", to="2026-11-15")
    flight = FlightOption(
        id="f1",
        destination="Турция",
        direct=True,
        dates=dates,
        price=Money(amount=18000),
        carrier="Air",
        source="mock",
        fetched_at="",
    )
    hotel = HotelOption(
        id="h1",
        destination="Турция",
        name="Sea Hotel",
        stars=4,
        rating=4.5,
        photos=[],
        price_per_night=Money(amount=4000),
        distance_to_sea_m=80,
        available=None,
        booking_url="",
        source="mock",
        fetched_at="",
    )
    total = Money(amount=38000)

    score = ranking_tool(
        hotel, flight, total, budget=Money(amount=50000), wishes=["sea_view", "direct_flight"]
    )
    assert score > 0

    exp = explain_option(
        hotel, flight, total, budget=Money(amount=50000), wishes=["sea_view", "direct_flight"]
    )
    assert "в бюджете" in exp.why
    assert "первая линия" in exp.why
    # Так как available=None, в cons должно быть честное предупреждение
    assert any("не подтверждено" in c.lower() for c in exp.cons)


# ---------------------------------------------------------------------------
# Интеграционные тесты Оркестратора через FastAPI TestClient
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _zero_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отключаем задержку моков в тестах для быстрого выполнения."""
    monkeypatch.setattr(get_settings(), "mock_stage_delay", 0)


client = TestClient(app)


def test_orchestrator_demo_full_pipeline() -> None:
    """Сквозной запуск оркестратора: статус ok, офферы в бюджете, объяснения на месте."""
    query = (
        "Хочу на 5 дней в Турцию в ноябре, на двоих, бюджет до 120 000 рублей. "
        "Нужен хороший отель рядом с морем и прямой перелёт"
    )
    r = client.post("/api/search", json={"query": query}).json()

    assert r["status"] == "ok"
    assert len(r["offers"]) > 0
    first = r["offers"][0]
    assert first["total_price"]["amount"] <= 120000
    assert first["flight"]["direct"] is True
    assert first["hotel"]["distance_to_sea_m"] <= 150
    assert "в бюджете" in first["explanation"]["why"]


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

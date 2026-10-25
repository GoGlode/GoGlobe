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
    """Эталонный демо-запрос: поля parsed корректны, дата без числа → dates=None + warning.

    Баг 2: при «месяц + длительность» без конкретного числа парсер НЕ угадывает
    дату (не ставит day=10). dates остаётся None, в warnings — предупреждение.
    """
    query = (
        "Хочу на 5 дней в Турцию в ноябре, на двоих, бюджет до 120 000 рублей. "
        "Нужен хороший отель рядом с морем и прямой перелёт"
    )
    parsed = parse_mock(query)

    assert parsed.destination == "Турция"
    assert parsed.duration_days == 5
    # Конкретный день не указан — честный парсер не угадывает дату.
    assert parsed.dates is None
    # Должно быть предупреждение о неполной дате.
    assert any("ноябр" in w.lower() or "дата" in w.lower() or "число" in w.lower()
               for w in parsed.warnings)
    assert parsed.travelers == 2
    assert parsed.budget is not None
    assert parsed.budget.amount == 120000
    assert parsed.budget.currency == "RUB"
    assert "sea_view" in parsed.wishes
    assert "direct_flight" in parsed.wishes
    # dates=None → агент задаёт уточняющий вопрос
    q = missing_question(parsed)
    assert q is not None
    assert "даты" in q.lower() or "дней" in q.lower()


def test_parse_minimal_complete_query() -> None:
    """Минимально полный запрос: все поля извлечены, но дата без числа → dates=None.

    После фикса бага 2: парсер не угадывает 10-е число, оставляет dates=None.
    Полным запрос считается, когда передан точный диапазон дат.
    """
    query = "Сочи на 4 дня в ноябре с девушкой, бюджет 60к, отель у моря и прямой рейс"
    parsed = parse_mock(query)

    assert parsed.destination == "Сочи, Россия"
    assert parsed.duration_days == 4
    assert parsed.travelers == 2
    assert parsed.budget is not None
    assert parsed.budget.amount == 60000
    assert "sea_view" in parsed.wishes
    assert "direct_flight" in parsed.wishes
    # Месяц указан, день нет → dates=None, агент спрашивает число
    assert parsed.dates is None
    assert any("число" in w.lower() or "дата" in w.lower() for w in parsed.warnings)


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
    """Парсинг длительности 'на неделю' и валюты USD ($). Дата без числа → dates=None."""
    query = "Дубай на неделю в ноябре вдвоем, бюджет около 1500$"
    parsed = parse_mock(query)

    assert parsed.destination == "Дубай, ОАЭ"
    assert parsed.duration_days == 7
    assert parsed.travelers == 2
    assert parsed.budget is not None
    assert parsed.budget.amount == 1500
    assert parsed.budget.currency == "USD"
    # Баг 2 исправлен: «в ноябре» без числа → dates=None, не угадываем
    assert parsed.dates is None
    assert any("число" in w.lower() or "дата" in w.lower() for w in parsed.warnings)


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
# Баг-тесты: три блокирующих правки Тимофея (24.10.2026)
# ---------------------------------------------------------------------------


def test_bug2_month_only_no_date_guessing() -> None:
    """Баг 2: при «месяц + длительность» без числа даты НЕ угадываются.

    Было: start = date(year, month, 10) — выдуманное 10-е число.
    Стало: dates=None, warning о неполной дате, агент задаёт вопрос.
    """
    parsed = parse_mock("Хочу в Египет на 7 дней в декабре")
    assert parsed.destination == "Египет"
    assert parsed.duration_days == 7
    # Дата НЕ должна быть выдумана
    assert parsed.dates is None, "Парсер не должен угадывать дату начала"
    # Должно быть предупреждение
    assert len(parsed.warnings) > 0
    assert any("число" in w.lower() or "дата" in w.lower() for w in parsed.warnings)
    # missing_question должен спросить про даты
    q = missing_question(parsed)
    assert q is not None


def test_bug2_exact_date_range_still_works() -> None:
    """Баг 2 регрессия: точный диапазон «с 10 по 15 ноября» по-прежнему парсится."""
    parsed = parse_mock("Турция с 10 по 15 ноября на двоих")
    assert parsed.dates is not None
    assert parsed.dates.from_.endswith("-11-10")
    assert parsed.dates.to.endswith("-11-15")
    assert parsed.duration_days == 5


def test_bug3_maldives_not_may() -> None:
    """Баг 3: «Мальдивы на неделю» НЕ должно превращаться в май 2027.

    Было: основа 'ма' совпадала со словом 'Мальдивы' → month=5 (май).
    Стало: используются полные паттерны май|мая|маю|маем|мае.
    """
    parsed = parse_mock("Мальдивы на неделю")
    assert parsed.destination == "Мальдивы"
    assert parsed.duration_days == 7
    # Слово «Мальдивы» не должно вызывать определение месяца «май»
    assert parsed.dates is None  # нет месяца → нет дат
    assert not any("мае" in w.lower() or "май" in w.lower() for w in parsed.warnings)


def test_bug3_may_still_detected() -> None:
    """Баг 3 регрессия: настоящий «май»/«мая»/«мае» по-прежнему распознаётся."""
    parsed = parse_mock("Турция в мае на 5 дней")
    assert parsed.duration_days == 5
    # Месяц май определён, день не указан → dates=None + warning
    assert parsed.dates is None
    assert any("мае" in w.lower() or "май" in w.lower() or "число" in w.lower()
               for w in parsed.warnings)


def test_bug3_marsh_not_march() -> None:
    """Баг 3: «маршрут» не должен совпадать с «март»."""
    parsed = parse_mock("Посоветуй маршрут по Европе на 10 дней")
    assert parsed.duration_days == 10
    # Слово «маршрут» не должно порождать month=3
    assert parsed.dates is None
    assert not any("марте" in w.lower() for w in parsed.warnings)


def test_bug3_mart_and_maya_detected() -> None:
    """Баг 3 регрессия: «марте»/«мая» распознаются корректно."""
    parsed_mart = parse_mock("Италия в марте на 7 дней")
    assert parsed_mart.duration_days == 7
    assert parsed_mart.dates is None
    assert any("март" in w.lower() or "число" in w.lower() for w in parsed_mart.warnings)

    parsed_maya = parse_mock("Бали в мая на 10 дней")
    assert parsed_maya.duration_days == 10
    assert parsed_maya.dates is None
    assert any("мае" in w.lower() or "май" in w.lower() or "число" in w.lower()
               for w in parsed_maya.warnings)


def test_bug1_llm_fallback_on_empty_key() -> None:
    """Баг 1: при пустом llm_api_key parse_llm честно откатывается на parse_mock.

    Ключ читается из Settings (не из os.getenv напрямую).
    """
    import asyncio
    from unittest.mock import patch

    from app.agent.parser import parse_llm

    with patch("app.agent.parser.get_settings") as mock_settings:
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_base_url = "https://api.deepseek.com/v1"
        mock_settings.return_value.llm_model = "deepseek-chat"
        mock_settings.return_value.use_mock_ai = False

        result, _ = asyncio.run(
            parse_llm("Турция с 10 по 15 ноября на двоих, бюджет 80к")
        )
    # Откат на mock отработал корректно
    assert result.destination == "Турция"
    assert result.dates is not None  # точный диапазон → даты есть
    assert result.dates.from_.endswith("-11-10")


def test_bug1_llm_fallback_on_llm_crash() -> None:
    """Баг 1 + задача 6: LLM упал или вернул мусор → откат на mock, не исключение."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    import httpx

    from app.agent.parser import parse_llm

    with patch("app.agent.parser.get_settings") as mock_settings, \
         patch("httpx.AsyncClient") as mock_client:
        mock_settings.return_value.llm_api_key = "fake-key-for-test"
        mock_settings.return_value.llm_base_url = "https://api.deepseek.com/v1"
        mock_settings.return_value.llm_model = "deepseek-chat"
        mock_settings.return_value.use_mock_ai = False

        # LLM выбрасывает сетевую ошибку
        mock_client.return_value.__aenter__ = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result, _ = asyncio.run(parse_llm("Хочу в Дубай на неделю"))
    # Откат сработал — данные из mock-парсера
    assert result.destination == "Дубай, ОАЭ"
    assert result.duration_days == 7


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
    """Сквозной запуск оркестратора: статус ok, офферы в бюджете, объяснения на месте.

    Используем точный диапазон дат, так как после исправления бага 2
    «в ноябре» без числа даёт needs_clarification.
    """
    query = (
        "Хочу на 5 дней в Турцию с 5 по 10 ноября, на двоих, бюджет до 120 000 рублей. "
        "Нужен хороший отель рядом с морем и прямой перелёт"
    )
    r = client.post("/api/search", json={"query": query}).json()

    assert r["status"] in ("ok", "partial")
    assert len(r["offers"]) > 0
    first = r["offers"][0]
    assert first["total_price"]["amount"] <= 120000
    assert first["flight"]["direct"] is True
    assert first["hotel"]["distance_to_sea_m"] <= 150
    assert "в бюджете" in first["explanation"]["why"]
    # destination_search обогащает pros и warnings
    assert any("сезон" in p.lower() for p in first["explanation"]["pros"])


def test_orchestrator_needs_clarification() -> None:
    """Неполный запрос → статус needs_clarification, пустые офферы."""
    r = client.post("/api/search", json={"query": "хочу в Турцию"}).json()
    assert r["status"] == "needs_clarification"
    assert r["clarifying_question"]
    assert not r["offers"]


def test_orchestrator_events_contain_all_stages() -> None:
    """SSE-поток содержит все ожидаемые стадии от parsing до done."""
    query = (
        "Хочу на 5 дней в Турцию с 5 по 10 ноября, на двоих, бюджет до 120 000 рублей. "
        "Нужен хороший отель рядом с морем и прямой перелёт"
    )
    r = client.post("/api/search", json={"query": query, "search_id": "test_stages"}).json()
    assert r["status"] in ("ok", "partial")
    body = client.get("/api/search/test_stages/events").text
    assert '"stage": "parsing"' in body
    assert '"stage": "flights"' in body
    assert '"stage": "hotels"' in body
    assert '"stage": "validating"' in body
    assert '"stage": "ranking"' in body
    assert '"stage": "done"' in body


# ---------------------------------------------------------------------------
# Задача 6: тесты ранжирования и эталонные запросы с конкретными полями
# ---------------------------------------------------------------------------


def test_ranking_order_descending() -> None:
    """Задача 6: offers отсортированы по score убывающе (лучший вариант — первый)."""
    query = (
        "Хочу на 5 дней в Турцию с 5 по 10 ноября, на двоих, бюджет до 200 000 рублей. "
        "Прямой перелёт и отель у моря"
    )
    r = client.post("/api/search", json={"query": query}).json()

    assert r["status"] in ("ok", "partial")
    scores = [o["score"] for o in r["offers"] if o["score"] is not None]
    assert len(scores) >= 2, "Должно быть хотя бы 2 оффера для проверки порядка"
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], (
            f"Нарушен порядок ранжирования: scores[{i}]={scores[i]} < scores[{i+1}]={scores[i+1]}"
        )


def test_reference_query_dubai_budget_usd() -> None:
    """Эталонный запрос: Дубай, 7 дней, 2 человека, бюджет USD.

    Проверяет конкретные поля parsed и корректность обработки.
    """
    query = (
        "Дубай с 1 по 8 декабря на двоих, бюджет 3000 долларов, прямой перелёт, всё включено"
    )
    r = client.post("/api/search", json={"query": query}).json()

    parsed = r["parsed"]
    assert parsed["destination"] == "Дубай, ОАЭ"
    assert parsed["dates"] is not None
    assert parsed["dates"]["from"].endswith("-12-01")
    assert parsed["dates"]["to"].endswith("-12-08")
    assert parsed["duration_days"] == 7
    assert parsed["travelers"] == 2
    assert parsed["budget"] is not None
    assert parsed["budget"]["amount"] == 3000
    assert parsed["budget"]["currency"] == "USD"
    assert "direct_flight" in parsed["wishes"]
    assert "all_inclusive" in parsed["wishes"]


def test_reference_query_egypt_family_sea() -> None:
    """Эталонный запрос: Египет, 10 дней, семья с ребёнком, отель у моря.

    Проверяет корректность parsed.travelers=3 и wishes.
    """
    query = (
        "Египет с 15 по 25 января на троих (двое взрослых и ребёнок), "
        "отель у моря со звёздностью 4 или 5, всё включено"
    )
    r = client.post("/api/search", json={"query": query}).json()

    parsed = r["parsed"]
    assert parsed["destination"] == "Египет"
    assert parsed["dates"] is not None
    assert parsed["dates"]["from"].endswith("-01-15")
    assert parsed["dates"]["to"].endswith("-01-25")
    assert parsed["duration_days"] == 10
    assert parsed["travelers"] == 3
    assert "sea_view" in parsed["wishes"]
    assert "all_inclusive" in parsed["wishes"]


def test_destination_search_warnings_and_explanation_in_response() -> None:
    """Задача 4: сезонность и температура из destination_search попадают в warnings и explanation."""
    query = (
        "Хочу на 5 дней в Турцию с 5 по 10 ноября, на двоих, бюджет до 120 000 рублей"
    )
    r = client.post("/api/search", json={"query": query}).json()

    assert r["status"] in ("ok", "partial")
    warnings_text = " ".join(r.get("warnings", []))
    assert "сезон" in warnings_text.lower()
    assert "температур" in warnings_text.lower()
    assert len(r["offers"]) > 0
    first_exp = r["offers"][0]["explanation"]
    assert any("сезон" in p.lower() for p in first_exp["pros"])


"""Регрессионные тесты по дефектам из REPORT_BACKEND_2.md, раздел 7.6.

Каждый тест назван по сценарию прогона на падения: F-01…F-19.
Владелец: Backend №2, ветка `dev/backend-2`.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from typing import ClassVar, Self
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.agent.parser import parse_llm, parse_mock
from app.agent.tools import ranking_tool
from app.config import get_settings
from app.main import app
from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange, Money

DEMO = (
    "Хочу на 5 дней в Турцию с 5 по 10 ноября, на двоих, бюджет до 120 000 рублей. "
    "Нужен хороший отель рядом с морем и прямой перелёт"
)


@pytest.fixture(autouse=True)
def _fast_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без пауз между стадиями и с коротким таймаутом SSE, чтобы тесты были быстрыми."""
    monkeypatch.setattr(get_settings(), "mock_stage_delay", 0)
    monkeypatch.setattr(get_settings(), "sse_idle_timeout", 0.05)


client = TestClient(app)


def _flight(amount: float = 1000) -> FlightOption:
    return FlightOption(
        id="f1",
        destination="Турция",
        direct=True,
        dates=DateRange(**{"from": "2026-11-10", "to": "2026-11-15"}),
        price=Money(amount=amount),
        carrier="Air",
        source="mock",
        fetched_at="",
    )


def _hotel(amount: float = 1000) -> HotelOption:
    return HotelOption(
        id="h1",
        destination="Турция",
        name="Hotel",
        stars=4,
        rating=4.5,
        photos=[],
        price_per_night=Money(amount=amount),
        distance_to_sea_m=100,
        available=True,
        booking_url="",
        source="mock",
        fetched_at="",
    )


# ---------------------------------------------------------------------------
# F-01: запрос без числа путешественников не роняет провайдеров
# ---------------------------------------------------------------------------


def test_no_travelers_defaults_to_one() -> None:
    r = client.post("/api/search", json={"query": "Турция с 5 по 10 ноября, до 120000"}).json()

    assert r["status"] in ("ok", "partial"), r["warnings"]
    assert r["parsed"]["travelers"] is None, "Парсер не должен выдумывать число путешественников"
    assert r["offers"], "Поиск должен выполняться на одного человека"
    # Моки умножают цену перелёта на число путешественников: 9000/6500 за одного.
    assert {o["flight"]["price"]["amount"] for o in r["offers"]} <= {6500, 9000}


def test_travelers_zero_is_rejected_or_defaulted() -> None:
    r = client.post(
        "/api/search", json={"query": "Турция с 5 по 10 ноября", "params": {"travelers": 0}}
    )
    assert r.status_code == 422, "travelers=0 — ошибка ввода, а не TypeError в провайдере"


def test_family_with_children_still_searches() -> None:
    r = client.post("/api/search", json={"query": "Турция с 5 по 10 ноября с детьми"}).json()

    assert r["status"] in ("ok", "partial"), r["warnings"]
    assert r["parsed"]["travelers"] == 3
    assert r["offers"]


# ---------------------------------------------------------------------------
# F-02 / F-03 / F-08 / F-19: даты
# ---------------------------------------------------------------------------


def test_invalid_calendar_day_asks_clarification() -> None:
    r = client.post("/api/search", json={"query": "Турция с 31 по 32 ноября на двоих"}).json()

    assert r["status"] == "needs_clarification"
    assert r["clarifying_question"]
    assert r["warnings"], "Причина должна быть в warnings"
    assert "даты" in " ".join(r["warnings"]).lower()
    assert not r["offers"]


def test_invalid_params_date_returns_422() -> None:
    r = client.post(
        "/api/search",
        json={
            "query": "Турция на двоих",
            "params": {"dates": {"from": "2026-02-30", "to": "2026-03-05"}},
        },
    )
    assert r.status_code == 422, "30 февраля должно отсекаться валидацией схемы"


def test_reversed_dates_rejected() -> None:
    # В тексте — уточнение, а не поиск с перевёрнутым диапазоном.
    text = client.post("/api/search", json={"query": "Турция с 10 по 5 ноября на двоих"}).json()
    assert text["status"] == "needs_clarification"
    assert text["parsed"]["dates"] is None

    # В params — 422 от схемы DateRange.
    params = client.post(
        "/api/search",
        json={
            "query": "Турция на двоих",
            "params": {"dates": {"from": "2026-11-10", "to": "2026-11-05"}},
        },
    )
    assert params.status_code == 422


def test_year_boundary_dates() -> None:
    parsed = parse_mock("Турция с 30 декабря по 2 января на двоих")

    assert parsed.dates is not None
    start = date.fromisoformat(parsed.dates.from_)
    end = date.fromisoformat(parsed.dates.to)
    assert (start.month, start.day) == (12, 30)
    assert (end.month, end.day) == (1, 2)
    assert end.year == start.year + 1, "Диапазон через Новый год должен переходить в следующий год"


# ---------------------------------------------------------------------------
# F-04: статус ok достижим, справка о сезоне не считается деградацией
# ---------------------------------------------------------------------------


def test_demo_status_is_ok_without_data_failures() -> None:
    r = client.post("/api/search", json={"query": DEMO}).json()

    assert r["status"] == "ok", f"Ожидался ok без предупреждений, получено {r['warnings']}"
    assert r["warnings"] == []
    assert r["offers"]


# ---------------------------------------------------------------------------
# F-05 / F-06: жизненный цикл SSE
# ---------------------------------------------------------------------------


def test_reused_search_id_does_not_replay_old_events() -> None:
    client.post("/api/search", json={"query": DEMO, "search_id": "dup"})
    second = client.post("/api/search", json={"query": "хочу в Турцию", "search_id": "dup"}).json()
    assert second["status"] == "needs_clarification"

    body = client.get("/api/search/dup/events").text
    assert '"stage": "flights"' not in body, "События первого прогона не должны проигрываться"
    assert body.count('"stage": "done"') == 1
    assert body.count('"stage": "parsing"') == 1


def test_unknown_search_id_events_returns_404_or_error_event() -> None:
    body = client.get("/api/search/nope/events").text

    assert '"stage": "error"' in body, "Поток для неизвестного id не должен висеть"
    assert "не найдены" in body


# ---------------------------------------------------------------------------
# F-07: отрицательное число путешественников
# ---------------------------------------------------------------------------


def test_negative_travelers_rejected() -> None:
    r = client.post(
        "/api/search", json={"query": "Турция с 5 по 10 ноября", "params": {"travelers": -2}}
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# F-09: валюта бюджета учитывается
# ---------------------------------------------------------------------------


def test_usd_budget_currency_respected() -> None:
    r = client.post(
        "/api/search",
        json={"query": "Турция с 5 по 10 ноября на двоих, бюджет 3000 долларов"},
    ).json()

    assert r["parsed"]["budget"]["currency"] == "USD"
    assert r["warnings"], "Пересчёт валюты должен быть озвучен в warnings"
    assert any("пересчитан" in w.lower() for w in r["warnings"])
    # 3000 USD по демо-курсу = 270 000 ₽: рублёвые варианты проходят фильтр.
    assert r["offers"], "Бюджет в USD не должен отбрасывать все рублёвые варианты"
    assert all(o["total_price"]["amount"] <= 270000 for o in r["offers"])
    assert any("₽" in p for p in r["offers"][0]["explanation"]["pros"])


# ---------------------------------------------------------------------------
# F-12: направление вне старого whitelist
# ---------------------------------------------------------------------------


def test_known_direction_outside_mock_coverage_is_honestly_empty() -> None:
    r = client.post("/api/search", json={"query": "Япония с 5 по 10 ноября на двоих"}).json()

    assert r["parsed"]["destination"] == "Япония", "Направление не должно теряться"
    assert r["status"] == "empty"
    assert any("не покрыва" in w.lower() for w in r["warnings"])


# ---------------------------------------------------------------------------
# F-13: LLM вернул невалидные даты -> фолбэк на эвристики
# ---------------------------------------------------------------------------


class _FakeLLMResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        content = json.dumps(self._payload)
        return {"choices": [{"message": {"content": content}}]}


class _FakeLLMClient:
    payload: ClassVar[dict] = {}

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, *args: object, **kwargs: object) -> _FakeLLMResponse:
        return _FakeLLMResponse(self.payload)


def test_llm_invalid_dates_fall_back_to_mock() -> None:
    _FakeLLMClient.payload = {
        "destination": "Турция",
        "dates": {"from": "10.11.2026", "to": "15.11.2026"},
    }

    with (
        patch("app.agent.parser.get_settings") as settings,
        patch("app.agent.parser.httpx.AsyncClient", _FakeLLMClient),
    ):
        settings.return_value.llm_api_key = "fake-key"
        settings.return_value.llm_base_url = "https://api.deepseek.com/v1"
        settings.return_value.llm_model = "deepseek-chat"
        settings.return_value.use_mock_ai = False

        parsed, _ = asyncio.run(parse_llm("Турция с 10 по 15 ноября на двоих"))

    assert parsed.dates is not None, "После фолбэка даты должны прийти из эвристик"
    assert parsed.dates.from_.endswith("-11-10")
    assert parsed.dates.to.endswith("-11-15")


# ---------------------------------------------------------------------------
# F-14: предупреждение не теряется при уточнении
# ---------------------------------------------------------------------------


def test_clarification_keeps_parser_warnings() -> None:
    r = client.post("/api/search", json={"query": "5 дней в Турцию в ноябре, на двоих"}).json()

    assert r["status"] == "needs_clarification"
    assert r["warnings"], "Причина уточнения должна попадать в топ-левел warnings"
    assert any("ноябр" in w.lower() for w in r["warnings"])


# ---------------------------------------------------------------------------
# F-15 / F-16: устойчивость ранжирования и data_freshness
# ---------------------------------------------------------------------------


def test_ranking_zero_budget_no_crash() -> None:
    result = ranking_tool(
        _hotel(), _flight(), Money(amount=2000), Money(amount=0), wishes=["sea_view"]
    )
    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0


def test_data_freshness_always_iso() -> None:
    r = client.post("/api/search", json={"query": DEMO}).json()

    assert r["offers"]
    for offer in r["offers"]:
        assert offer["data_freshness"], "Пустая строка вместо ISO-метки недопустима"
        datetime.fromisoformat(offer["data_freshness"])


# ---------------------------------------------------------------------------
# F-17 / F-18: границы регулярок и длины запроса
# ---------------------------------------------------------------------------


def test_regex_false_positives() -> None:
    assert parse_mock("Турция на 5 дней, мороз").wishes == [], "«мороз» — не море"
    assert not any(
        "май" in w.lower() or "мае" in w.lower()
        for w in parse_mock("Турция с 5 по 10 ноября, майонез").warnings
    ), "«майонез» — не месяц май"


def test_query_length_limit() -> None:
    assert client.post("/api/search", json={"query": "а" * 2001}).status_code == 422
    assert client.post("/api/search", json={"query": "а" * 2000}).status_code == 200


# ---------------------------------------------------------------------------
# F-10: внутренние детали не уходят клиенту
# ---------------------------------------------------------------------------


def test_error_response_hides_internal_details(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("секретный-стек-трейс")

    monkeypatch.setattr("app.api.search.run_search", boom)

    r = client.post("/api/search", json={"query": DEMO})

    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "error"
    assert "секретный-стек-трейс" not in json.dumps(payload, ensure_ascii=False)
    assert payload["warnings"]


# ---------------------------------------------------------------------------
# F-20: требование прямого рейса — жёсткое ограничение, пересадки не подмешиваются
# ---------------------------------------------------------------------------


class _ConnectingOnlyFlightProvider:
    async def search(self, destination: str, dates: DateRange, travelers: int) -> list:
        return [
            FlightOption(
                id=f"fl_conn_{i}",
                destination="Анталья, Турция",
                direct=False,
                dates=dates,
                price=Money(amount=7000 * travelers),
                carrier="Connect Air",
                source="test",
                fetched_at="2026-10-28T12:00:00+00:00",
            )
            for i in range(2)
        ]


class _SingleHotelProvider:
    async def search(self, destination: str, dates: DateRange, travelers: int) -> list:
        return [_hotel(amount=3000)]


def test_direct_only_never_returns_connecting_flights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Если прямых рейсов нет — не отдаём пересадки под видом подходящих (F-20)."""
    monkeypatch.setattr(
        "app.agent.orchestrator.get_providers",
        lambda: (_ConnectingOnlyFlightProvider(), _SingleHotelProvider()),
    )

    r = client.post(
        "/api/search",
        json={"query": "Турция с 5 по 10 ноября на двоих, прямой перелёт"},
    ).json()

    assert r["offers"] == [], "Рейсы с пересадкой не должны попадать в ответ"
    assert r["status"] == "empty"
    assert any("прямых" in w.lower() for w in r["warnings"])


def test_connecting_flights_still_allowed_without_direct_wish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Без требования «прямой» пересадки — допустимый вариант, а не потеря данных."""
    monkeypatch.setattr(
        "app.agent.orchestrator.get_providers",
        lambda: (_ConnectingOnlyFlightProvider(), _SingleHotelProvider()),
    )

    r = client.post("/api/search", json={"query": "Турция с 5 по 10 ноября на двоих"}).json()

    assert r["offers"], r["warnings"]
    assert all(o["flight"]["direct"] is False for o in r["offers"])


# ---------------------------------------------------------------------------
# F-09: деньги в разных валютах не складываются и не сравниваются напрямую
# ---------------------------------------------------------------------------


def test_total_price_rejects_mixed_currencies() -> None:
    from app.agent.validation import CurrencyMismatchError, total_price

    flight = _flight(amount=1000)
    hotel = _hotel(amount=100)
    hotel.price_per_night = Money(amount=100, currency="USD")

    with pytest.raises(CurrencyMismatchError):
        total_price(flight, hotel)


def test_within_budget_rejects_mixed_currencies() -> None:
    from app.agent.validation import CurrencyMismatchError, within_budget

    with pytest.raises(CurrencyMismatchError):
        within_budget(Money(amount=1000, currency="RUB"), Money(amount=10, currency="USD"))


def test_validate_combo_drops_unconvertible_currency() -> None:
    from app.agent.tools import validate_combo

    flight = _flight(amount=1000)
    hotel = _hotel(amount=100)
    hotel.price_per_night = Money(amount=100, currency="XYZ")

    valid, total = validate_combo(flight, hotel, budget=None)

    assert valid is False
    assert total is None, "Итоговую сумму в неизвестной валюте показывать нельзя"


class _MixedCurrencyFlightProvider(_ConnectingOnlyFlightProvider):
    async def search(self, destination: str, dates: DateRange, travelers: int) -> list:
        return [_flight(amount=10000)]


class _MixedCurrencyHotelProvider(_SingleHotelProvider):
    async def search(self, destination: str, dates: DateRange, travelers: int) -> list:
        hotel = _hotel(amount=100)
        hotel.price_per_night = Money(amount=100, currency="USD")
        hotel.available = True
        return [hotel]


def test_mixed_currency_total_is_converted_and_warned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Цена отеля в USD пересчитывается в валюту перелёта, факт пересчёта — в warnings."""
    monkeypatch.setattr(
        "app.agent.orchestrator.get_providers",
        lambda: (_MixedCurrencyFlightProvider(), _MixedCurrencyHotelProvider()),
    )

    r = client.post("/api/search", json={"query": "Турция с 5 по 10 ноября на двоих"}).json()

    assert r["offers"], r["warnings"]
    total = r["offers"][0]["total_price"]
    assert total["currency"] == "RUB"
    # 5 ночей × 100 USD × 90 = 45 000 ₽ + 10 000 ₽ перелёт (а не 10 000 + 500).
    assert total["amount"] == 55000
    assert any("пересчитан" in w.lower() for w in r["warnings"])


class _UnknownCurrencyHotelProvider(_SingleHotelProvider):
    async def search(self, destination: str, dates: DateRange, travelers: int) -> list:
        hotel = _hotel(amount=100)
        hotel.price_per_night = Money(amount=100, currency="XYZ")
        return [hotel]


def test_unknown_currency_does_not_produce_fake_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agent.orchestrator.get_providers",
        lambda: (_MixedCurrencyFlightProvider(), _UnknownCurrencyHotelProvider()),
    )

    r = client.post("/api/search", json={"query": "Турция с 5 по 10 ноября на двоих"}).json()

    assert r["offers"] == [], "Без надёжного курса итоговую цену показывать нельзя"
    assert r["status"] == "empty"
    assert any("курс" in w.lower() for w in r["warnings"])


# ---------------------------------------------------------------------------
# F-22: справочная погода не выдаётся за прогноз и не даёт баллов
# ---------------------------------------------------------------------------


def test_weather_is_marked_as_reference() -> None:
    """Статическая климатическая справка не выдаётся за подтверждённый прогноз."""
    from app.agent.tools import destination_search

    info = asyncio.run(destination_search("Турция"))
    assert info is not None
    assert info.is_reference is True
    assert info.source == "static_reference"


def test_destination_info_is_reference() -> None:
    from app.agent.tools import destination_search

    info = asyncio.run(destination_search("Турция"))
    assert info is not None
    assert info.is_reference is True
    assert info.source == "static_reference"


def test_explanation_labels_weather_as_reference_not_forecast() -> None:
    from app.agent.tools import destination_search, explain_option

    info = asyncio.run(destination_search("Турция"))
    explanation = explain_option(
        _hotel(amount=3000), _flight(amount=9000), Money(amount=24000), None, [], dest_info=info
    )

    weather_lines = [p for p in explanation.pros if "Температура" in p or "Сезонность" in p]
    assert weather_lines, "Справка о сезоне остаётся в MVP"
    assert all("справочн" in line.lower() for line in weather_lines)
    assert all("прогноз" in line.lower() for line in weather_lines if "Температура" in line)


def test_ranking_does_not_invent_rating() -> None:
    from app.agent.ranking import score

    known = _hotel(amount=3000)
    unknown = _hotel(amount=3000)
    unknown.rating = None
    total = Money(amount=20000)

    assert score(known, _flight(), total, None, []) > score(unknown, _flight(), total, None, [])
    assert 0.0 <= score(unknown, _flight(), total, None, []) <= 1.0


def test_ranking_score_stays_in_range_on_extremes() -> None:
    from app.agent.ranking import score

    hotel = _hotel(amount=1)
    hotel.rating = 5.0
    flight = _flight(amount=1)
    cheap = Money(amount=2)

    assert 0.0 <= score(hotel, flight, cheap, Money(amount=1), ["sea_view", "direct_flight"]) <= 1.0
    assert 0.0 <= score(hotel, flight, Money(amount=10**9), Money(amount=1), []) <= 1.0
    assert 0.0 <= score(hotel, flight, cheap, Money(amount=0), []) <= 1.0
    assert 0.0 <= score(hotel, flight, cheap, None, []) <= 1.0


# ---------------------------------------------------------------------------
# F-24: фолбэк LLM всегда сопровождается предупреждением и не светит ключ
# ---------------------------------------------------------------------------


def _parse_llm_with(client_patch, query: str = "Турция с 10 по 15 ноября"):
    with (
        patch("app.agent.parser.get_settings") as settings,
        patch("app.agent.parser.httpx.AsyncClient", client_patch),
    ):
        settings.return_value.llm_api_key = "sk-secret-key-do-not-leak"
        settings.return_value.llm_base_url = "https://api.deepseek.com/v1"
        settings.return_value.llm_model = "deepseek-chat"
        settings.return_value.use_mock_ai = False
        return asyncio.run(parse_llm(query))


def test_llm_not_configured_adds_warning_without_secret() -> None:
    with patch("app.agent.parser.get_settings") as settings:
        settings.return_value.llm_api_key = ""
        settings.return_value.llm_base_url = "https://api.deepseek.com/v1"
        settings.return_value.llm_model = "deepseek-chat"
        settings.return_value.use_mock_ai = False
        parsed, _ = asyncio.run(parse_llm("Турция с 10 по 15 ноября"))

    assert parsed.warnings, "Фолбэк без предупреждения выглядит как достоверный разбор"
    assert any("эвристик" in w.lower() for w in parsed.warnings)
    assert "sk-secret-key-do-not-leak" not in " ".join(parsed.warnings)


def test_llm_fallback_adds_warning_without_secret() -> None:
    import httpx

    class _TimeoutClient(_FakeLLMClient):
        async def post(self, *args: object, **kwargs: object):
            raise httpx.ReadTimeout("timeout")

    parsed, _ = _parse_llm_with(_TimeoutClient)

    assert parsed.warnings, "Фолбэк без предупреждения выглядит как достоверный разбор"
    assert any("эвристик" in w.lower() for w in parsed.warnings)
    assert "sk-secret-key-do-not-leak" not in " ".join(parsed.warnings)


def test_llm_network_error_falls_back_with_warning() -> None:
    import httpx

    class _BoomClient(_FakeLLMClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("refused")

    parsed, _ = _parse_llm_with(_BoomClient)
    assert any("эвристик" in w.lower() for w in parsed.warnings)


def test_llm_timeout_falls_back_with_warning() -> None:
    import httpx

    class _TimeoutClient(_FakeLLMClient):
        async def post(self, *args: object, **kwargs: object):
            raise httpx.ReadTimeout("timeout")

    parsed, _ = _parse_llm_with(_TimeoutClient)
    assert parsed.warnings
    assert any("эвристик" in w.lower() for w in parsed.warnings)


def test_llm_invalid_json_falls_back_with_warning() -> None:
    class _GarbageResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "это не json"}}]}

    class _GarbageClient(_FakeLLMClient):
        async def post(self, *args: object, **kwargs: object) -> _GarbageResponse:
            return _GarbageResponse()

    parsed, _ = _parse_llm_with(_GarbageClient)
    assert parsed.destination == "Турция"
    assert any("эвристик" in w.lower() for w in parsed.warnings)


def test_llm_contradictory_dates_fall_back() -> None:
    _FakeLLMClient.payload = {
        "destination": "Турция",
        "dates": {"from": "2026-11-15", "to": "2026-11-10"},
    }

    parsed, _ = _parse_llm_with(_FakeLLMClient)

    assert parsed.dates is not None
    assert parsed.dates.from_ < parsed.dates.to, "Перевёрнутый диапазон не должен проходить"
    assert any("эвристик" in w.lower() for w in parsed.warnings)


def test_llm_incomplete_answer_asks_instead_of_guessing() -> None:
    _FakeLLMClient.payload = {"destination": "Турция"}

    parsed, clarifying = _parse_llm_with(_FakeLLMClient)

    assert parsed.dates is None, "Даты нельзя выдумывать"
    assert clarifying, "Неполный разбор должен приводить к уточняющему вопросу"

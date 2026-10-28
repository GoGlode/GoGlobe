"""Интеграционные тесты сквозного сценария (пункт 9 чек-листа, 28.10.2026).

Проверяется весь путь: запрос → парсер → инструменты → ограничения →
ранжирование → HTTP-ответ/SSE. Провайдеры подменяются фейками, чтобы
проверить именно поведение агента, а не моки данных.

Владелец: Backend №2, ветка `dev/backend-2`.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.integrations.base import ProviderError
from app.main import app
from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange, Money

client = TestClient(app)

DATES = DateRange(**{"from": "2026-11-10", "to": "2026-11-15"})


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "mock_stage_delay", 0)
    monkeypatch.setattr(get_settings(), "sse_idle_timeout", 0.05)


class SpyFlightProvider:
    def __init__(self, direct: bool = True, currency: str = "RUB", fail: bool = False) -> None:
        self.direct = direct
        self.currency = currency
        self.fail = fail
        self.calls = 0

    async def search(self, destination: str, dates: DateRange, travelers: int) -> list:
        self.calls += 1
        if self.fail:
            raise ProviderError("flight backend timeout")
        return [
            FlightOption(
                id="fl_it",
                destination="Анталья, Турция",
                direct=self.direct,
                dates=dates,
                price=Money(amount=10000, currency=self.currency),
                carrier="Test Air",
                source="test",
                fetched_at="2026-10-28T12:00:00+00:00",
            )
        ]


class SpyHotelProvider:
    def __init__(self, currency: str = "RUB", fail: bool = False, available: bool = True) -> None:
        self.currency = currency
        self.fail = fail
        self.available = available
        self.calls = 0

    async def search(self, destination: str, dates: DateRange, travelers: int) -> list:
        self.calls += 1
        if self.fail:
            raise ProviderError("hotel backend timeout")
        return [
            HotelOption(
                id="ht_it",
                destination="Анталья, Турция",
                name="Integration Hotel",
                stars=4,
                rating=4.4,
                photos=[],
                price_per_night=Money(amount=3000, currency=self.currency),
                distance_to_sea_m=90,
                available=self.available,
                booking_url="https://example.com/hotel",
                source="test",
                fetched_at="2026-10-28T12:00:00+00:00",
            )
        ]


def _use(monkeypatch: pytest.MonkeyPatch, flights, hotels) -> None:
    monkeypatch.setattr("app.agent.orchestrator.get_providers", lambda: (flights, hotels))


def _stages(search_id: str) -> list[str]:
    body = client.get(f"/api/search/{search_id}/events").text
    stages = []
    for line in body.splitlines():
        if line.startswith("data: "):
            stages.append(json.loads(line[6:])["stage"])
    return stages


# 1. Запрос пользователя → разбор параметров ---------------------------------


def test_query_is_parsed_into_contract_fields() -> None:
    r = client.post(
        "/api/search",
        json={
            "query": "Хочу в Турцию с 5 по 10 ноября, на двоих, бюджет до 120 000 рублей, "
            "отель у моря, прямой перелёт"
        },
    ).json()

    parsed = r["parsed"]
    assert parsed["destination"] == "Турция"
    assert parsed["dates"] == {"from": "2026-11-05", "to": "2026-11-10"}
    assert parsed["travelers"] == 2
    assert parsed["budget"] == {"amount": 120000.0, "currency": "RUB"}
    assert set(parsed["wishes"]) == {"sea_view", "direct_flight"}


# 2. Недостаточно данных → уточняющий вопрос ---------------------------------


def test_insufficient_query_returns_question_without_search() -> None:
    r = client.post("/api/search", json={"query": "Хочу куда-нибудь в ноябре"}).json()

    assert r["status"] == "needs_clarification"
    assert r["clarifying_question"]
    assert r["offers"] == []


# 3. Валидный запрос → провайдеры вызываются ---------------------------------


def test_valid_query_calls_both_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    flights, hotels = SpyFlightProvider(), SpyHotelProvider()
    _use(monkeypatch, flights, hotels)

    r = client.post("/api/search", json={"query": "Турция с 5 по 10 ноября на двоих"}).json()

    assert (flights.calls, hotels.calls) == (1, 1)
    assert r["offers"]


# 4. Нет прямого рейса → пересадки не предлагаются ---------------------------


def test_no_direct_flights_means_no_offers(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, SpyFlightProvider(direct=False), SpyHotelProvider())

    r = client.post(
        "/api/search", json={"query": "Турция с 5 по 10 ноября на двоих, прямой перелёт"}
    ).json()

    assert r["offers"] == []
    assert r["status"] == "empty"
    assert not any(o["flight"]["direct"] is False for o in r["offers"])


# 5. Разные валюты → нет ложной общей стоимости ------------------------------


def test_currency_mismatch_does_not_fake_total(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, SpyFlightProvider(currency="RUB"), SpyHotelProvider(currency="XYZ"))

    r = client.post("/api/search", json={"query": "Турция с 5 по 10 ноября на двоих"}).json()

    assert r["offers"] == []
    assert any("курс" in w.lower() for w in r["warnings"])


# 6. Ошибка одного провайдера → статус и предупреждения ----------------------


def test_hotel_provider_failure_yields_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, SpyFlightProvider(), SpyHotelProvider(fail=True))

    r = client.post("/api/search", json={"query": "Турция с 5 по 10 ноября на двоих"}).json()

    assert r["status"] in ("empty", "partial")
    assert any("отели" in w.lower() for w in r["warnings"])
    assert not any("стек" in w.lower() for w in r["warnings"])


# 7. Результат → правильная структура для frontend ---------------------------


def test_offer_structure_matches_frontend_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, SpyFlightProvider(), SpyHotelProvider())

    r = client.post("/api/search", json={"query": "Турция с 5 по 10 ноября на двоих"}).json()

    assert r["search_id"]
    assert r["status"] in ("ok", "partial")
    offer = r["offers"][0]
    for field in (
        "id",
        "destination",
        "hotel",
        "flight",
        "total_price",
        "explanation",
        "booking_url",
        "data_freshness",
        "score",
    ):
        assert field in offer, f"Нет поля {field}"

    assert offer["hotel"]["name"] == "Integration Hotel"
    assert offer["flight"]["direct"] is True
    assert offer["total_price"]["currency"] == "RUB"
    assert offer["total_price"]["amount"] == 10000 + 3000 * 5
    assert offer["explanation"]["sources"] == ["test"]
    assert offer["explanation"]["confidence"] in ("confirmed", "estimated")
    assert 0.0 <= offer["score"] <= 1.0
    date.fromisoformat(offer["data_freshness"][:10])


# 8. Этапы поиска → корректные SSE-события -----------------------------------


def test_sse_stages_follow_pipeline_order() -> None:
    body = client.post(
        "/api/search", json={"query": "Турция с 5 по 10 ноября на двоих", "search_id": "it-sse"}
    ).json()
    assert body["status"] in ("ok", "partial")

    stages = _stages("it-sse")

    assert stages == ["parsing", "flights", "hotels", "validating", "ranking", "done"]
    assert len(stages) == len(set(stages)), "Дубли событий на одну стадию недопустимы"

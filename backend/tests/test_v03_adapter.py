"""Тесты адаптера AI-агента к контракту API v0.3.

Проверяется не «на глаз», а сверкой с `docs/api/v0.3/GoGlobe_openapi_v0.3.json`:
наборы полей моделей должны совпадать со схемами, иначе фронт и Backend №1
получат JSON, которого нет в контракте.

Владелец: Backend №2, ветка `dev/backend-2`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent.currency import normalize_budget
from app.agent.v03 import (
    AcceptedV03,
    AnswerV03,
    ComponentsV03,
    ComponentV03,
    DayV03,
    ErrorV03,
    HotelContextV03,
    HotelListV03,
    HotelOfferV03,
    ItemV03,
    MoneyV03,
    ParamsV03,
    PlaceV03,
    PriceV03,
    QuestionV03,
    SnapshotV03,
    SourceV03,
    StayV03,
    TravelersV03,
    WarningV03,
    params_from_parsed,
    parsed_from_params,
    question_from,
    snapshot_from,
    warning_code,
)
from app.config import get_settings
from app.main import app
from app.schemas.search import DateRange, Money, ParsedQuery, SearchResponse, SearchStatus

OPENAPI = (
    Path(__file__).resolve().parents[2] / "docs" / "api" / "v0.3" / "GoGlobe_openapi_v0.3.json"
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "mock_stage_delay", 0)
    monkeypatch.setattr(get_settings(), "sse_idle_timeout", 0.05)


@pytest.fixture(scope="module")
def schemas() -> dict:
    return json.loads(OPENAPI.read_text(encoding="utf-8"))["components"]["schemas"]


def _result(query: str) -> SearchResponse:
    payload = client.post("/api/search", json={"query": query}).json()
    return SearchResponse.model_validate(payload)


# ---------------------------------------------------------------------------
# Контракт: поля моделей совпадают со схемами OpenAPI v0.3
# ---------------------------------------------------------------------------


MODEL_SCHEMAS = [
    (MoneyV03, "Money"),
    (PriceV03, "Price"),
    (SourceV03, "Source"),
    (WarningV03, "Warning"),
    (QuestionV03, "Question"),
    (AnswerV03, "Answer"),
    (TravelersV03, "Travelers"),
    (PlaceV03, "Place"),
    (ItemV03, "Item"),
    (DayV03, "Day"),
    (ComponentV03, "Component"),
    (ComponentsV03, "Components"),
    (HotelContextV03, "HotelContext"),
    (StayV03, "Stay"),
    (HotelOfferV03, "HotelOffer"),
    (HotelListV03, "HotelList"),
    (ParamsV03, "Params"),
    (AcceptedV03, "Accepted"),
    (ErrorV03, "Error"),
    (SnapshotV03, "Snapshot"),
]


@pytest.mark.parametrize(("model", "schema_name"), MODEL_SCHEMAS)
def test_model_fields_match_openapi(model, schema_name: str, schemas: dict) -> None:
    schema = schemas[schema_name]
    expected = set(schema.get("properties", {}))
    actual = set(model.model_fields)

    assert actual == expected, (
        f"{model.__name__} расходится со схемой {schema_name}: "
        f"лишние={sorted(actual - expected)}, потерянные={sorted(expected - actual)}"
    )
    missing_required = set(schema.get("required", [])) - actual
    assert not missing_required, (
        f"{schema_name}: обязательные поля не объявлены: {missing_required}"
    )


# ---------------------------------------------------------------------------
# Параметры: туда и обратно
# ---------------------------------------------------------------------------


def test_params_from_parsed_uses_minor_units_and_enum_wishes() -> None:
    parsed = ParsedQuery(
        destination="Турция",
        dates=DateRange(**{"from": "2026-11-10", "to": "2026-11-15"}),
        duration_days=5,
        travelers=2,
        budget=Money(amount=120000),
        wishes=["sea_view", "direct_flight", "all_inclusive", "pool"],
    )

    params = params_from_parsed(parsed)

    assert params.budget is not None
    assert params.budget.amount_minor == 12_000_000, "v0.3 считает деньги в копейках"
    assert params.budget.currency == "RUB"
    assert params.dates is not None
    assert params.dates.start_date == "2026-11-10"
    assert params.travelers is not None and params.travelers.adults == 2
    assert params.wishes == ["sea_view", "direct_flight"], "Пожелания вне enum v0.3 отбрасываются"


def test_params_roundtrip_keeps_agent_values() -> None:
    parsed = ParsedQuery(
        destination="Египет",
        dates=DateRange(**{"from": "2026-12-01", "to": "2026-12-08"}),
        travelers=3,
        budget=Money(amount=2000, currency="USD"),
        wishes=["sea_view"],
    )

    restored = parsed_from_params(params_from_parsed(parsed))

    assert restored.destination == "Египет"
    assert restored.dates == parsed.dates
    assert restored.travelers == 3
    # 2000 USD по демо-курсу 90 = 180 000 ₽: v0.3 хранит только рубли.
    assert restored.budget is not None and restored.budget.amount == 180000
    assert restored.wishes == ["sea_view"]


def test_empty_params_do_not_invent_data() -> None:
    restored = parsed_from_params(ParamsV03())

    assert restored.destination is None
    assert restored.dates is None
    assert restored.budget is None
    assert restored.travelers is None


# ---------------------------------------------------------------------------
# Предупреждения и вопросы
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("LLM-парсер недоступен: запрос разобран эвристиками", "LLM_FALLBACK"),
        ("Прямых рейсов в «Турция» не найдено", "NO_DIRECT_FLIGHTS"),
        ("Курс USD→RUB неизвестен: бюджет не применялся", "CURRENCY_CONVERTED"),
        ("Нет данных по направлению «Япония»: источники его пока не покрывают", "PROVIDERS_EMPTY"),
        ("Отели временно недоступны: timeout", "PROVIDER_PARTIAL"),
        ("Странное предупреждение", "AGENT_WARNING"),
    ],
)
def test_warning_codes(message: str, code: str) -> None:
    assert warning_code(message) == code


def test_question_gets_stable_id_and_field() -> None:
    result = SearchResponse(
        search_id="s1",
        status=SearchStatus.needs_clarification,
        clarifying_question="На какие даты или на сколько дней вы планируете поездку?",
    )

    first = question_from(result)
    second = question_from(result)

    assert first is not None and second is not None
    assert first.question_id == second.question_id, "question_id должен быть стабильным"
    assert first.field == "duration_days"
    assert len(first.question_id) <= 128


def test_destination_question_is_classified() -> None:
    result = SearchResponse(
        search_id="s2",
        status=SearchStatus.needs_clarification,
        clarifying_question="Какую страну или город вы рассматриваете для поездки?",
    )
    question = question_from(result)
    assert question is not None and question.field == "destination"


# ---------------------------------------------------------------------------
# Snapshot: статусы, компоненты, цены
# ---------------------------------------------------------------------------


def test_completed_snapshot_has_itinerary_and_hotels_and_blocked_flights() -> None:
    result = _result("Турция с 5 по 10 ноября на двоих, бюджет до 120000 рублей")
    assert result.offers

    snapshot = snapshot_from(
        result, search_id="s_demo", trip_id="t_demo", revision=2, trip_revision=1
    )
    payload = snapshot.model_dump()

    assert payload["state"] == "completed"
    assert payload["result_status"] in ("ok", "partial")
    assert payload["clarification"] is None
    assert payload["components"]["itinerary"]["state"] == "ready"
    assert payload["components"]["hotels"]["state"] == "ready"
    assert payload["components"]["flights"]["state"] == "blocked"
    assert payload["components"]["flights"]["missing_fields"] == ["segments"], (
        "Сегменты перелёта нельзя выдумывать — фиксируем блокер B3"
    )
    assert payload["stage"] is None
    assert payload["requested_components"] == ["itinerary", "hotels", "flights"]
    assert payload["data_mode"] == "demo"


def test_clarification_snapshot_carries_question() -> None:
    result = _result("Хочу куда-нибудь в ноябре")

    snapshot = snapshot_from(result, search_id="s_q", trip_id="t_q")

    assert snapshot.state == "needs_clarification"
    assert snapshot.result_status is None
    assert snapshot.clarification is not None
    assert snapshot.clarification.field in ("destination", "duration_days", "conflict")
    assert snapshot.components.flights.state == "blocked"


def test_hotels_offer_has_estimated_price_with_note_and_source() -> None:
    result = _result("Турция с 5 по 10 ноября на двоих")
    snapshot = snapshot_from(result, search_id="s_p", trip_id="t_p")

    hotel_component = snapshot.components.hotels
    assert hotel_component.state == "ready"
    assert hotel_component.incomplete is False

    from app.agent.v03 import _hotel_items

    items = _hotel_items(result.offers)
    assert items
    item = items[0]
    assert item.check_in == "2026-11-05"
    assert item.check_out == "2026-11-10"
    assert item.availability == "unknown", "Наличие не подтверждено в Offer — не выдумываем"
    assert item.source_ids
    assert item.total_price.status == "estimated"
    assert item.nightly_price.basis == "room_night"


def test_snapshot_prices_are_minor_units_and_estimated() -> None:
    result = _result("Турция с 5 по 10 ноября на двоих")
    assert result.offers
    snapshot = snapshot_from(result, search_id="s_m", trip_id="t_m")
    itinerary = snapshot.components.itinerary
    assert itinerary.state == "ready"

    # Собираем список отелей напрямую, чтобы проверить Price.
    from app.agent.v03 import _hotel_items

    items = _hotel_items(result.offers)
    assert items
    price = items[0].total_price
    assert price.status == "estimated"
    assert price.money is not None
    assert isinstance(price.money.amount_minor, int)
    assert price.money.amount_minor > 0
    assert price.note
    assert price.source_ids
    assert price.checked_at


def test_money_currency_is_rub_only() -> None:
    with pytest.raises(ValueError):
        MoneyV03(amount_minor=100, currency="USD")  # type: ignore[arg-type]


def test_unknown_price_must_not_have_money() -> None:
    with pytest.raises(ValueError):
        PriceV03(
            status="unknown",
            money=MoneyV03(amount_minor=100),
            basis="trip_total",
        )


def test_estimated_price_requires_note() -> None:
    with pytest.raises(ValueError):
        PriceV03(
            status="estimated",
            money=MoneyV03(amount_minor=100),
            basis="trip_total",
            source_ids=["src_mock"],
            checked_at="2026-10-28T12:00:00Z",
        )


def test_snapshot_is_json_serializable(schemas: dict) -> None:
    result = _result("Турция с 5 по 10 ноября на двоих")
    snapshot = snapshot_from(
        result,
        search_id="s_json",
        trip_id="t_json",
        now=datetime(2026, 10, 28, 12, 0, tzinfo=UTC),
    )

    raw = snapshot.model_dump_json()
    restored = json.loads(raw)

    assert restored["created_at"] == "2026-10-28T12:00:00Z"
    assert restored["expires_at"].startswith("2026-10-29T")
    # Каждый ключ верхнего уровня есть в схеме Snapshot.
    assert set(restored) == set(schemas["Snapshot"]["properties"])


def test_currency_warning_is_mapped_for_usd_budget() -> None:
    parsed = ParsedQuery(budget=Money(amount=3000, currency="USD"))
    normalized, note = normalize_budget(parsed.budget, "RUB")

    assert normalized is not None
    assert note is not None
    assert warning_code(note) == "CURRENCY_CONVERTED"

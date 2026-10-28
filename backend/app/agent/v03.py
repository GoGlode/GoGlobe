"""Адаптер AI-агента к контракту API v0.3 (Backend №2).

Назначение: отдать Backend №1 результат работы агента в терминах v0.3
(`Snapshot`, `Components`, `Price`, `Question`, `Warning`), не меняя общий
контракт и не создавая параллельный HTTP-слой.

Границы честности:
* `FlightOffer` в v0.3 требует сегменты (аэропорты, время вылета/прилёта),
  которых нет в текущем контракте провайдеров (`FlightProvider`). Поэтому
  компонент `flights` помечается `blocked` с `missing_fields=["segments"]`,
  а не заполняется выдуманными рейсами (блокер B3).
* `Price.status="estimated"` ставится только там, где цена посчитана/пересчитана
  агентом; `quoted` без источника не выставляется никогда.
* Справочная погода/сезонность в Snapshot не попадает.

Модуль ничего не пишет в хранилище и не знает про HTTP — это зона Backend №1.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.currency import convert, norm_currency
from app.schemas.search import (
    DateRange,
    Offer,
    ParsedQuery,
    SearchResponse,
    SearchStatus,
)

# ---------------------------------------------------------------------------
# Модели контракта v0.3 (только используемое подмножество)
# ---------------------------------------------------------------------------


class StrictModel(BaseModel):
    """Лишние поля запрещены — так расходятся модели и OpenAPI ловятся тестом."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MoneyV03(StrictModel):
    amount_minor: int = Field(ge=0, le=9_000_000_000_000)
    currency: Literal["RUB"] = "RUB"


class PriceV03(StrictModel):
    status: Literal["unknown", "estimated", "quoted"]
    money: MoneyV03 | None = None
    basis: Literal[
        "trip_total", "party_stay_total", "party_return_total", "room_night", "person_total"
    ]
    coverage: list[Literal["hotels", "flights", "activities", "transfers"]] = Field(
        default_factory=list
    )
    exclusions: list[Literal["hotels", "flights", "activities", "transfers"]] = Field(
        default_factory=list
    )
    source_ids: list[str] = Field(default_factory=list, max_length=20)
    checked_at: str | None = None
    valid_until: str | None = None
    stale: bool = False
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _check_status(self) -> PriceV03:
        """Инварианты цены: без денег — unknown, estimated требует источник и пояснение."""
        if self.status == "unknown" and (
            self.money is not None or self.checked_at is not None or self.stale
        ):
            raise ValueError("unknown-цена не может содержать сумму, дату проверки или stale")
        if self.status in ("estimated", "quoted") and (
            self.money is None or not self.source_ids or self.checked_at is None
        ):
            raise ValueError("estimated/quoted требует money, source_ids и checked_at")
        if self.status == "estimated" and not self.note:
            raise ValueError("estimated-цена обязана иметь note")
        return self


class SourceV03(StrictModel):
    source_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    url: str | None = Field(default=None, max_length=2048)
    checked_at: str
    kind: Literal["provider", "catalog", "estimate_method"]


class WarningV03(StrictModel):
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=500)
    trip_id: str | None = None


class QuestionV03(StrictModel):
    question_id: str = Field(min_length=1, max_length=128)
    field: Literal["destination", "duration_days", "conflict"]
    message: str = Field(min_length=1, max_length=500)


class AnswerV03(StrictModel):
    question_id: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=1)
    answer: str = Field(min_length=1, max_length=1000)


class TravelersV03(StrictModel):
    adults: int = Field(ge=1, le=9)
    children_ages: list[int] = Field(default_factory=list, max_length=8)


class DatesV03(StrictModel):
    start_date: str = Field(min_length=1, max_length=10)
    end_date: str = Field(min_length=1, max_length=10)


class BudgetV03(MoneyV03):
    amount_minor: int = Field(ge=1, le=9_000_000_000_000)


class ParamsV03(StrictModel):
    destination: str | None = Field(default=None, max_length=200)
    duration_days: int | None = Field(default=None, ge=1, le=30)
    dates: DatesV03 | None = None
    origin: str | None = Field(default=None, max_length=200)
    travelers: TravelersV03 | None = None
    budget: BudgetV03 | None = None
    wishes: list[Literal["near_sea", "sea_view", "direct_flight", "breakfast"]] = Field(
        default_factory=list, max_length=4
    )


class PlanRequestV03(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    params: ParamsV03 | None = None


class AcceptedV03(StrictModel):
    search_id: str = Field(min_length=1, max_length=128)
    trip_id: str = Field(min_length=1, max_length=128)
    state: Literal["queued", "processing"]
    revision: int = Field(ge=1)
    expires_at: str


class ErrorV03(StrictModel):
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=500)
    retryable: bool
    details: list[dict[str, str]] = Field(default_factory=list, max_length=20)


class ComponentV03(StrictModel):
    state: Literal["not_requested", "blocked", "queued", "processing", "ready", "empty", "failed"]
    missing_fields: list[str] = Field(default_factory=list, max_length=10)
    error: ErrorV03 | None = None
    incomplete: bool = False

    @model_validator(mode="after")
    def _check_state(self) -> ComponentV03:
        if self.state == "blocked" and not self.missing_fields:
            raise ValueError("blocked требует missing_fields")
        if self.state != "blocked" and self.missing_fields:
            raise ValueError("missing_fields допустимы только для blocked")
        if self.state == "failed" and self.error is None:
            raise ValueError("failed требует error")
        if self.state != "failed" and self.error is not None:
            raise ValueError("error допустим только для failed")
        return self


class PlaceV03(StrictModel):
    place_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    timezone: str | None = Field(default=None, max_length=80)
    verification: Literal["verified", "unknown"]
    source_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _check_coords(self) -> PlaceV03:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Широта и долгота задаются вместе")
        return self


class ItemV03(StrictModel):
    item_id: str = Field(min_length=1, max_length=128)
    order: int = Field(ge=1, le=20)
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["activity", "arrival", "departure", "hotel", "meal", "transfer"]
    local_time: str | None = Field(default=None, max_length=5)
    place: PlaceV03 | None = None
    verification: Literal["suggested", "verified", "unknown"]
    source_ids: list[str] = Field(default_factory=list, max_length=20)


class DayV03(StrictModel):
    day_index: int = Field(ge=1, le=30)
    date: str | None = None
    items: list[ItemV03] = Field(min_length=1, max_length=20)


class ItineraryV03(StrictModel):
    days: list[DayV03] = Field(min_length=1, max_length=30)


class StayV03(StrictModel):
    check_in: str = Field(min_length=1, max_length=10)
    check_out: str = Field(min_length=1, max_length=10)


class FlightDatesV03(StrictModel):
    outbound_date: str = Field(min_length=1, max_length=10)
    return_date: str = Field(min_length=1, max_length=10)


class HotelContextV03(StrictModel):
    travelers: TravelersV03
    stay: StayV03


class FlightContextV03(StrictModel):
    travelers: TravelersV03
    origin: str = Field(min_length=1, max_length=200)
    flight_dates: FlightDatesV03


class HotelOfferV03(StrictModel):
    offer_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    photos: list[str] = Field(default_factory=list, max_length=10)
    place: PlaceV03 | None = None
    stars: int | None = Field(default=None, ge=1, le=5)
    rating: float | None = Field(default=None, ge=0, le=10)
    check_in: str
    check_out: str
    total_price: PriceV03
    nightly_price: PriceV03
    booking_url: str | None = Field(default=None, max_length=2048)
    availability: Literal["available", "unknown"]
    source_ids: list[str] = Field(min_length=1, max_length=20)


class HotelListV03(StrictModel):
    trip_id: str
    trip_revision: int = Field(ge=1)
    state: Literal["not_requested", "blocked", "queued", "processing", "ready", "empty", "failed"]
    missing_fields: list[str] = Field(default_factory=list, max_length=10)
    items: list[HotelOfferV03] = Field(default_factory=list, max_length=20)
    sources: list[SourceV03] = Field(default_factory=list, max_length=100)
    warnings: list[WarningV03] = Field(default_factory=list, max_length=30)
    error: ErrorV03 | None = None
    data_mode: Literal["live", "demo"]
    context: HotelContextV03 | None = None
    incomplete: bool = False


class FlightListV03(StrictModel):
    trip_id: str
    trip_revision: int = Field(ge=1)
    state: Literal["not_requested", "blocked", "queued", "processing", "ready", "empty", "failed"]
    missing_fields: list[str] = Field(default_factory=list, max_length=10)
    items: list[dict[str, object]] = Field(default_factory=list, max_length=20)
    sources: list[SourceV03] = Field(default_factory=list, max_length=100)
    warnings: list[WarningV03] = Field(default_factory=list, max_length=30)
    error: ErrorV03 | None = None
    data_mode: Literal["live", "demo"]
    context: FlightContextV03 | None = None
    incomplete: bool = False


class ComponentsV03(StrictModel):
    itinerary: ComponentV03
    hotels: ComponentV03
    flights: ComponentV03


class SnapshotV03(StrictModel):
    search_id: str = Field(min_length=1, max_length=128)
    kind: Literal["plan", "quotes"] = "plan"
    trip_id: str = Field(min_length=1, max_length=128)
    trip_revision: int = Field(ge=1)
    revision: int = Field(ge=1)
    state: Literal[
        "queued", "processing", "needs_clarification", "completed", "failed", "cancelled"
    ]
    stage: Literal["parsing", "itinerary", "quotes", "validating"] | None = None
    result_status: Literal["ok", "partial", "empty"] | None = None
    clarification: QuestionV03 | None = None
    components: ComponentsV03
    warnings: list[WarningV03] = Field(default_factory=list, max_length=30)
    error: ErrorV03 | None = None
    data_mode: Literal["live", "demo"]
    created_at: str
    updated_at: str
    expires_at: str
    requested_components: list[Literal["itinerary", "hotels", "flights"]] = Field(
        min_length=1, max_length=3
    )


# ---------------------------------------------------------------------------
# Intent preview (v0.3.1): разбор запроса и вопросы без создания Search/Trip
# ---------------------------------------------------------------------------


class IntentPreviewRequestV03(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    params: ParamsV03 | None = None


class IntentPreviewQuestionV03(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    field: str = Field(min_length=1, max_length=100)
    kind: Literal["text", "number", "travelers", "money"]
    title: str = Field(min_length=1, max_length=300)
    required: bool
    options: list[object] = Field(default_factory=list, max_length=20)


class IntentPreviewResponseV03(StrictModel):
    preview_id: str = Field(pattern=r"^ip_", max_length=128)
    parsed: ParamsV03
    questions: list[IntentPreviewQuestionV03] = Field(default_factory=list, max_length=3)
    warnings: list[WarningV03] = Field(default_factory=list, max_length=30)
    analysis_mode: Literal["llm", "fallback"]


def _question(
    field: str, title: str, kind: str = "text", required: bool = True
) -> IntentPreviewQuestionV03:
    digest = hashlib.sha1(f"{field}:{title}".encode()).hexdigest()[:10]
    return IntentPreviewQuestionV03(
        id=f"q_{digest}",
        field=field,
        kind=kind,  # type: ignore[arg-type]
        title=title[:300],
        required=required,
        options=[],
    )


def _preview_questions(result: SearchResponse) -> list[IntentPreviewQuestionV03]:
    """До трёх вопросов: сначала тот, что сформулировал агент, затем недостающее."""
    parsed = result.parsed
    questions: list[IntentPreviewQuestionV03] = []

    clarification = question_from(result)
    if clarification is not None:
        kind = "text"
        questions.append(_question(clarification.field, clarification.message, kind, required=True))

    fields = {q.field for q in questions}
    if parsed.destination is None and "destination" not in fields:
        questions.append(
            _question(
                "destination",
                f"Куда едете? Доступные направления: {_SUPPORTED_HINT}",
                required=True,
            )
        )
    if parsed.dates is None and parsed.duration_days is None and "duration_days" not in fields:
        questions.append(
            _question(
                "duration_days",
                "На какие даты или сколько дней планируете поездку?",
                required=True,
            )
        )
    if parsed.travelers is None and "travelers" not in fields:
        questions.append(
            _question("travelers", "Сколько человек едет?", kind="travelers", required=False)
        )

    return questions[:3]


_SUPPORTED_HINT = "Турция, Египет, ОАЭ, Таиланд, Мальдивы, Сочи, Италия, Греция, Испания, Кипр"


def preview_from(
    result: SearchResponse,
    *,
    query: str,
    used_llm: bool = False,
    preview_id: str | None = None,
) -> IntentPreviewResponseV03:
    """SearchResponse агента → IntentPreviewResponse v0.3.1.

    Preview ничего не создаёт: `preview_id` не передаётся в PlanRequest,
    а итоговый запрос повторно валидируется при POST /searches.
    """
    parsed = params_from_parsed(result.parsed)
    digest = hashlib.sha1(f"{query}:{parsed.model_dump_json()}".encode()).hexdigest()[:16]
    return IntentPreviewResponseV03(
        preview_id=preview_id or f"ip_{digest}",
        parsed=parsed,
        questions=_preview_questions(result),
        warnings=warnings_from(result, None),
        analysis_mode="llm" if used_llm else "fallback",
    )


# ---------------------------------------------------------------------------
# Маппинг параметров
# ---------------------------------------------------------------------------

_WISHES_IN = {"near_sea", "sea_view", "direct_flight", "breakfast"}
_WISHES_OUT = {
    "near_sea": "sea_view",
    "sea_view": "sea_view",
    "direct_flight": "direct_flight",
    "breakfast": "breakfast",
}


def params_from_parsed(parsed: ParsedQuery) -> ParamsV03:
    """ParsedQuery агента → Params v0.3 (деньги в копейках, пожелания из enum)."""
    wishes: list[str] = []
    for wish in parsed.wishes:
        mapped = _WISHES_OUT.get(wish)
        if mapped and mapped not in wishes:
            wishes.append(mapped)

    # v0.3 знает только RUB: сумму в другой валюте пересчитываем, а не переименовываем.
    budget = None
    if parsed.budget and parsed.budget.amount > 0:
        rub = convert(parsed.budget.amount, parsed.budget.currency, "RUB")
        if rub is not None:
            budget = BudgetV03(amount_minor=_to_minor(rub))

    return ParamsV03(
        destination=parsed.destination,
        duration_days=parsed.duration_days if (parsed.duration_days or 0) >= 1 else None,
        dates=(
            DatesV03(start_date=parsed.dates.from_, end_date=parsed.dates.to)
            if parsed.dates
            else None
        ),
        travelers=(
            TravelersV03(adults=max(1, min(9, parsed.travelers))) if parsed.travelers else None
        ),
        budget=budget,
        wishes=wishes,  # type: ignore[arg-type]
    )


def parsed_from_params(params: ParamsV03, query: str = "") -> ParsedQuery:
    """Params v0.3 → ParsedQuery агента. Даты/бюджет не выдумываются."""
    parsed = ParsedQuery()
    parsed.destination = params.destination
    parsed.duration_days = params.duration_days
    if params.dates:
        parsed.dates = DateRange(**{"from": params.dates.start_date, "to": params.dates.end_date})
    if params.travelers:
        parsed.travelers = params.travelers.adults + len(params.travelers.children_ages)
    if params.budget:
        parsed.budget = _money(params.budget)
    parsed.wishes = sorted({_WISHES_OUT[w] for w in params.wishes})
    if not query and not params.destination:
        parsed = parsed.model_copy(update={"destination": None})
    return parsed


# ---------------------------------------------------------------------------
# Маппинг результата
# ---------------------------------------------------------------------------

_WARNING_CODES: tuple[tuple[str, str], ...] = (
    ("эвристик", "LLM_FALLBACK"),
    ("прямых рейсов", "NO_DIRECT_FLIGHTS"),
    ("курс", "CURRENCY_CONVERTED"),
    ("пересчитан", "CURRENCY_CONVERTED"),
    ("не покрыва", "PROVIDERS_EMPTY"),
    ("временно недоступны", "PROVIDER_PARTIAL"),
    ("наличие", "AVAILABILITY_UNKNOWN"),
    ("климат", "DESTINATION_REFERENCE_MISSING"),
    ("ничего не найдено", "EMPTY_RESULT"),
)

_STATE_BY_STATUS: dict[SearchStatus, str] = {
    SearchStatus.ok: "completed",
    SearchStatus.partial: "completed",
    SearchStatus.empty: "completed",
    SearchStatus.needs_clarification: "needs_clarification",
    SearchStatus.error: "failed",
}


def warning_code(message: str) -> str:
    """Код предупреждения по тексту агента (пока тексты не переведены на коды)."""
    lowered = message.lower()
    for needle, code in _WARNING_CODES:
        if needle in lowered:
            return code
    return "AGENT_WARNING"


def warnings_from(result: SearchResponse, trip_id: str | None) -> list[WarningV03]:
    return [
        WarningV03(code=warning_code(text), message=text[:500], trip_id=trip_id)
        for text in result.warnings
    ]


def question_from(result: SearchResponse) -> QuestionV03 | None:
    """Уточняющий вопрос агента → Question v0.3 со стабильным question_id."""
    text = result.clarifying_question
    if not text:
        return None
    lowered = text.lower()
    if any(word in lowered for word in ("куда", "направлен", "страну", "город")):
        field = "destination"
    elif any(word in lowered for word in ("даты", "дата", "число", "сколько дней", "дней")):
        field = "duration_days"
    else:
        field = "conflict"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return QuestionV03(question_id=f"q_{digest}", field=field, message=text[:500])


def _to_minor(amount: float) -> int:
    return round(amount * 100)


def _money(value: object) -> object:
    from app.schemas.search import Money

    if isinstance(value, MoneyV03):
        return Money(amount=value.amount_minor / 100, currency="RUB")
    assert isinstance(value, Money)
    return Money(amount=value.amount, currency=norm_currency(value.currency))


def _iso(now: datetime) -> str:
    return now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _https(url: str | None) -> str | None:
    return url if url and url.startswith("https://") else None


def _sources(offer: Offer, checked_at: str) -> list[SourceV03]:
    return [
        SourceV03(
            source_id=f"src_{name}",
            name=name,
            url=None,
            checked_at=checked_at,
            kind="provider",
        )
        for name in sorted(set(offer.explanation.sources)) or ["unknown"]
    ]


def _price(
    amount: float,
    basis: str,
    coverage: list[str],
    exclusions: list[str],
    source_ids: list[str],
    checked_at: str,
    note: str,
) -> PriceV03:
    return PriceV03(
        status="estimated",
        money=MoneyV03(amount_minor=_to_minor(amount)),
        basis=basis,  # type: ignore[arg-type]
        coverage=coverage,  # type: ignore[arg-type]
        exclusions=exclusions,  # type: ignore[arg-type]
        source_ids=source_ids,
        checked_at=checked_at,
        valid_until=None,
        stale=False,
        note=note[:500],
    )


def _hotel_items(offers: list[Offer]) -> list[HotelOfferV03]:
    """Один отель — одна карточка (самая дешёвая комбинация с перелётом)."""
    best: dict[str, Offer] = {}
    for offer in offers:
        key = offer.hotel.name
        if key not in best or offer.total_price.amount < best[key].total_price.amount:
            best[key] = offer

    items: list[HotelOfferV03] = []
    for offer in best.values():
        hotel = offer.hotel
        checked_at = offer.data_freshness or _iso(datetime.now(UTC))
        sources = _sources(offer, checked_at)
        source_ids = [s.source_id for s in sources]
        dates = offer.flight.dates
        nights = max(
            (datetime.fromisoformat(dates.to) - datetime.fromisoformat(dates.from_)).days,
            1,
        )
        nightly = hotel.price.amount if hotel.price else 0
        photos = [p for p in hotel.photos if p.startswith("https://")][:10]
        items.append(
            HotelOfferV03(
                offer_id=f"ho_{offer.id}"[:128],
                name=hotel.name[:300],
                photos=photos,
                place=None,
                stars=max(1, min(5, hotel.stars)) if hotel.stars else None,
                # В v0.3 рейтинг 0..10, у провайдера — 0..5.
                rating=min(10.0, hotel.rating * 2) if hotel.rating is not None else None,
                check_in=dates.from_,
                check_out=dates.to,
                total_price=_price(
                    nightly * nights,
                    "party_stay_total",
                    ["hotels"],
                    ["flights", "activities", "transfers"],
                    source_ids,
                    checked_at,
                    f"Ориентировочно: {nights} ноч. × {nightly:.0f} ₽ по данным {', '.join(source_ids)}",
                ),
                nightly_price=_price(
                    nightly,
                    "room_night",
                    ["hotels"],
                    ["flights", "activities", "transfers"],
                    source_ids,
                    checked_at,
                    "Цена за ночь по данным провайдера (демо-режим)",
                ),
                booking_url=_https(offer.booking_url),
                # Offer не несёт флаг наличия: не выдаём «available» без подтверждения.
                availability="unknown",
                source_ids=source_ids,
            )
        )
    return items


def _itinerary(offers: list[Offer], parsed: ParsedQuery, trip_id: str) -> ItineraryV03 | None:
    """Черновая программа по дням: только то, что следует из дат и выбранного отеля."""
    if not offers or not parsed.dates:
        return None
    best = min(offers, key=lambda o: o.total_price.amount)
    dates = parsed.dates
    start = datetime.fromisoformat(dates.from_)
    end = datetime.fromisoformat(dates.to)
    total_days = max(1, min(30, (end - start).days or 1))
    sources = _sources(best, best.data_freshness or _iso(datetime.now(UTC)))
    source_ids = [s.source_id for s in sources]
    hotel_place = PlaceV03(
        place_id=f"pl_{best.id}"[:128],
        name=best.hotel.name[:300],
        latitude=None,
        longitude=None,
        timezone=None,
        verification="unknown",
        source_ids=source_ids,
    )

    days: list[DayV03] = []
    for index in range(1, total_days + 1):
        day_date = (start + timedelta(days=index - 1)).date().isoformat()
        items: list[ItemV03] = []
        if index == 1:
            items.append(
                ItemV03(
                    item_id=f"it_{trip_id}_arrival"[:128],
                    order=1,
                    title=f"Прилёт: {parsed.destination or best.destination}"[:200],
                    kind="arrival",
                    local_time=None,
                    place=None,
                    verification="suggested",
                    source_ids=source_ids,
                )
            )
        items.append(
            ItemV03(
                item_id=f"it_{trip_id}_hotel_{index}"[:128],
                order=len(items) + 1,
                title=f"Отель: {best.hotel.name}"[:200],
                kind="hotel",
                local_time=None,
                place=hotel_place,
                verification="unknown",
                source_ids=source_ids,
            )
        )
        if index == total_days:
            items.append(
                ItemV03(
                    item_id=f"it_{trip_id}_departure"[:128],
                    order=len(items) + 1,
                    title="Отъезд"[:200],
                    kind="departure",
                    local_time=None,
                    place=None,
                    verification="suggested",
                    source_ids=source_ids,
                )
            )
        days.append(DayV03(day_index=index, date=day_date, items=items))
    return ItineraryV03(days=days)


def _component_for(
    requested: bool,
    ready: bool,
    missing: list[str],
    incomplete: bool = False,
) -> ComponentV03:
    if not requested:
        return ComponentV03(state="not_requested")
    if missing:
        return ComponentV03(state="blocked", missing_fields=missing)
    if ready:
        return ComponentV03(state="ready", incomplete=incomplete)
    return ComponentV03(state="empty")


def snapshot_from(
    result: SearchResponse,
    *,
    search_id: str,
    trip_id: str,
    revision: int = 1,
    trip_revision: int = 1,
    requested_components: list[str] | None = None,
    data_mode: str = "demo",
    expires_at: str | None = None,
    now: datetime | None = None,
) -> SnapshotV03:
    """SearchResponse агента → Snapshot v0.3.

    `flights` всегда `blocked`: контракт провайдера не отдаёт сегменты (B3).
    """
    moment = now or datetime.now(UTC)
    requested = requested_components or ["itinerary", "hotels", "flights"]
    requested = [r for r in requested if r in ("itinerary", "hotels", "flights")]
    if not requested:
        requested = ["itinerary"]

    parsed = result.parsed
    offers = result.offers
    missing_plan = []
    if not parsed.destination:
        missing_plan.append("destination")
    if not parsed.dates:
        missing_plan.append("dates")

    itinerary = _itinerary(offers, parsed, trip_id) if "itinerary" in requested else None
    hotels_requested = "hotels" in requested
    flights_requested = "flights" in requested

    hotels_ready = bool(offers) and parsed.dates is not None
    hotel_missing = [] if parsed.dates else ["stay"]
    if hotels_requested and missing_plan:
        hotel_missing = missing_plan

    components = ComponentsV03(
        itinerary=_component_for(
            "itinerary" in requested,
            itinerary is not None,
            [] if itinerary is not None else missing_plan,
        ),
        hotels=_component_for(hotels_requested, hotels_ready, hotel_missing),
        flights=_component_for(flights_requested, False, ["segments"]),
    )

    state = _STATE_BY_STATUS[result.status]
    result_status = None
    if state == "completed":
        result_status = "partial" if result.warnings else "ok"
        if not offers:
            result_status = "empty"

    error = None
    if state == "failed":
        error = ErrorV03(
            code="AGENT_FAILED",
            message="Не удалось выполнить поиск: попробуйте повторить запрос",
            retryable=True,
        )

    return SnapshotV03(
        search_id=search_id,
        kind="plan",
        trip_id=trip_id,
        trip_revision=trip_revision,
        revision=revision,
        state=state,  # type: ignore[arg-type]
        stage=None,
        result_status=result_status,
        clarification=question_from(result),
        components=components,
        warnings=warnings_from(result, trip_id),
        error=error,
        data_mode="live" if data_mode == "live" else "demo",
        created_at=_iso(moment),
        updated_at=_iso(moment),
        expires_at=expires_at or _iso(moment + timedelta(days=1)),
        requested_components=requested,  # type: ignore[arg-type]
    )


__all__ = [
    "AcceptedV03",
    "AnswerV03",
    "ComponentV03",
    "ComponentsV03",
    "ErrorV03",
    "HotelListV03",
    "HotelOfferV03",
    "IntentPreviewQuestionV03",
    "IntentPreviewRequestV03",
    "IntentPreviewResponseV03",
    "ItemV03",
    "MoneyV03",
    "ParamsV03",
    "PlaceV03",
    "PlanRequestV03",
    "PriceV03",
    "QuestionV03",
    "SnapshotV03",
    "SourceV03",
    "TravelersV03",
    "WarningV03",
    "params_from_parsed",
    "parsed_from_params",
    "preview_from",
    "question_from",
    "snapshot_from",
    "warning_code",
    "warnings_from",
]

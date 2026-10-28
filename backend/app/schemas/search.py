"""API-контракт v0 (docs/api-contract.md). Владелец: Backend №1.

Менять поля — только через общий чат + PR с пометкой `contract`.
Фронтенд-типы: frontend/src/api/types.ts (держать в синхроне).
"""
from __future__ import annotations

import re
from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Предел длины пользовательского запроса: защита от «простыней» и мусора (F-18).
MAX_QUERY_LENGTH = 2000

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Money(BaseModel):
    amount: float
    currency: str = "RUB"


class DateRange(BaseModel):
    from_: str = Field(alias="from", description="YYYY-MM-DD")
    to: str = Field(description="YYYY-MM-DD")

    model_config = {"populate_by_name": True}

    @field_validator("from_", "to")
    @classmethod
    def _validate_iso_date(cls, value: str) -> str:
        """Принимаем только ISO-даты: «10.11.2026» и «2026-02-30» — 422, а не 500 (F-03, F-13)."""
        if not _ISO_DATE_RE.match(value):
            raise ValueError("Дата должна быть строкой в формате YYYY-MM-DD")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Некорректная календарная дата: {value}") from exc
        return value

    @model_validator(mode="after")
    def _validate_order(self) -> DateRange:
        """from <= to: перевёрнутый диапазон отсекаем на входе (F-08)."""
        if self.from_ > self.to:
            raise ValueError("Дата начала позже даты окончания")
        return self


class SearchParams(BaseModel):
    dates: DateRange | None = None
    budget: Money | None = None  # Money.amount трактуется как max
    # travelers=0 или отрицательное число — ошибка ввода, а не повод угадывать (F-01b, F-07).
    travelers: int | None = Field(default=None, ge=1)
    wishes: list[str] = Field(default_factory=list)  # sea_view, direct_flight, ...


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    params: SearchParams | None = None
    # Клиент может сгенерировать id заранее, чтобы открыть SSE до завершения POST
    search_id: str | None = None


class ParsedQuery(BaseModel):
    """Что агент понял из запроса. Нет значения -> None, агент не угадывает."""

    destination: str | None = None
    dates: DateRange | None = None
    duration_days: int | None = None
    travelers: int | None = None
    budget: Money | None = None
    wishes: list[str] = []
    # Предупреждения парсера (например, «месяц указан, но день не задан»).
    # Не входят в API-контракт v0 напрямую — пробрасываются в SearchResponse.warnings.
    warnings: list[str] = Field(default_factory=list, exclude=False)


class Hotel(BaseModel):
    name: str
    stars: int | None = None
    rating: float | None = None
    photos: list[str] = []
    price: Money | None = None
    distance_to_sea_m: int | None = None


class Flight(BaseModel):
    direct: bool
    dates: DateRange
    price: Money | None = None
    carrier: str | None = None


class Confidence(str, Enum):
    confirmed = "confirmed"
    estimated = "estimated"


class Explanation(BaseModel):
    why: list[str] = []
    pros: list[str] = []
    cons: list[str] = []
    sources: list[str] = []
    confidence: Confidence = Confidence.estimated


class Offer(BaseModel):
    id: str
    destination: str
    hotel: Hotel
    flight: Flight
    total_price: Money
    explanation: Explanation
    booking_url: str
    data_freshness: str  # ISO 8601
    score: float | None = None


class SearchStatus(str, Enum):
    ok = "ok"
    needs_clarification = "needs_clarification"
    partial = "partial"
    empty = "empty"
    error = "error"


class SearchResponse(BaseModel):
    search_id: str
    status: SearchStatus
    parsed: ParsedQuery = ParsedQuery()
    clarifying_question: str | None = None
    offers: list[Offer] = []
    warnings: list[str] = []


Stage = Literal["parsing", "flights", "hotels", "validating", "ranking", "done", "error"]


class SearchEvent(BaseModel):
    stage: Stage
    message: str

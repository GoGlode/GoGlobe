"""Модели только справочного прототипа v0.1; основной v0.3 использует app.contracts."""
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Dates(Model):
    from_: date = Field(alias="from")
    to: date

    @model_validator(mode="after")
    def ordered(self):
        if self.to <= self.from_:
            raise ValueError("Дата окончания должна быть позже даты начала")
        return self


class Money(Model):
    amount: int = Field(ge=0, description="Целые рубли; общая цена за всех путешественников")
    currency: Literal["RUB"] = "RUB"


class Budget(Model):
    max: int = Field(gt=0)
    currency: Literal["RUB"] = "RUB"


class SearchParams(Model):
    origin: str | None = Field(default=None, min_length=1, max_length=100)
    destination: str | None = Field(default=None, min_length=1, max_length=100)
    dates: Dates | None = None
    budget: Budget | None = None
    travelers: int | None = Field(default=None, ge=1, le=10)
    wishes: list[str] = Field(default_factory=list, max_length=20)


class SearchRequest(Model):
    query: str = Field(min_length=1, max_length=4000)
    params: SearchParams = Field(default_factory=SearchParams)


class Scenario(StrEnum):
    ok = "ok"
    needs_clarification = "needs_clarification"
    partial = "partial"
    empty = "empty"
    error = "error"


class Source(Model):
    name: str
    kind: Literal["mock"] = "mock"


class Hotel(Model):
    name: str
    stars: int = Field(ge=1, le=5)
    rating: float = Field(ge=0, le=10)
    photos: list[HttpUrl] = Field(default_factory=list)
    price: Money


class Flight(Model):
    origin: str
    destination: str
    direct: bool
    dates: Dates
    price: Money


class Explanation(Model):
    why: list[str]
    pros: list[str]
    cons: list[str]
    sources: list[Source]
    confidence: Literal["estimated"] = "estimated"


class Offer(Model):
    id: str
    destination: str
    hotel: Hotel
    flight: Flight
    total_price: Money
    explanation: Explanation
    booking_url: HttpUrl | None = None
    data_freshness: datetime
    is_mock: Literal[True] = True

    @model_validator(mode="after")
    def consistent_total(self):
        if self.total_price.amount != self.hotel.price.amount + self.flight.price.amount:
            raise ValueError("Total must equal hotel plus flight")
        return self


class ErrorInfo(Model):
    code: str
    message: str


class ErrorResponse(Model):
    error: ErrorInfo


class SearchResult(Model):
    id: str
    status: Literal["processing", "ok", "needs_clarification", "partial", "empty", "error"]
    parsed: SearchParams
    clarifying_question: str | None = None
    offers: list[Offer] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: ErrorInfo | None = None
    is_mock: Literal[True] = True


class SearchAccepted(Model):
    id: str
    status: Literal["processing"] = "processing"
    result_url: str
    events_url: str


class SearchEvent(Model):
    sequence: int
    stage: Literal["parsing", "flights", "hotels", "validating", "ranking", "done"]
    message: str = Field(max_length=500)
    status: str

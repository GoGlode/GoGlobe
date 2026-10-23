"""Validation Tool: бюджет, даты, доступность. Владелец: Backend №2 (корректность данных — №1)."""

from datetime import date

from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange, Money


def nights(d: DateRange) -> int:
    return max((date.fromisoformat(d.to) - date.fromisoformat(d.from_)).days, 1)


def total_price(f: FlightOption, h: HotelOption) -> Money:
    return Money(
        amount=f.price.amount + h.price_per_night.amount * nights(f.dates),
        currency=f.price.currency,
    )


def within_budget(total: Money, budget: Money | None) -> bool:
    return budget is None or total.amount <= budget.amount


def is_available(h: HotelOption) -> bool:
    return h.available is not False  # None (неизвестно) не отбрасываем, но дадим warning

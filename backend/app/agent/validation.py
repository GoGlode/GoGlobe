"""Validation Tool: бюджет, даты, доступность. Владелец: Backend №2 (корректность данных — №1).

Деньги в разных валютах не складываются и не сравниваются напрямую (F-09):
* `total_price` поднимает `CurrencyMismatchError`, если перелёт и отель в разных валютах;
* `within_budget` — если бюджет не приведён к валюте итоговой суммы.

Пересчёт выполняет вызывающий код через `app.agent.currency` (там же демо-курсы).
"""

from datetime import date

from app.agent.currency import norm_currency
from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange, Money


class CurrencyMismatchError(ValueError):
    """Попытка сложить/сравнить суммы в разных валютах без пересчёта."""


def nights(d: DateRange) -> int:
    """Количество ночей; минимум 1, чтобы однодневная поездка считалась корректно."""
    return max((date.fromisoformat(d.to) - date.fromisoformat(d.from_)).days, 1)


def total_price(f: FlightOption, h: HotelOption) -> Money:
    """Полная стоимость: перелёт (на всех путешественников) + отель за ночи.

    Складывать можно только суммы в одной валюте. Если валюты разные, вызывающий
    код обязан сначала пересчитать одну из них (см. orchestrator._combined_total).
    """
    flight_currency = norm_currency(f.price.currency)
    hotel_currency = norm_currency(h.price_per_night.currency)
    if flight_currency != hotel_currency:
        raise CurrencyMismatchError(
            f"Нельзя сложить цену перелёта ({flight_currency}) "
            f"и цену отеля ({hotel_currency}) без пересчёта"
        )
    return Money(
        amount=f.price.amount + h.price_per_night.amount * nights(f.dates),
        currency=flight_currency,
    )


def within_budget(total: Money, budget: Money | None) -> bool:
    """Бюджет должен быть в той же валюте, что и total, иначе сравнение бессмысленно."""
    if budget is None:
        return True
    if norm_currency(total.currency) != norm_currency(budget.currency):
        raise CurrencyMismatchError(
            f"Бюджет в {budget.currency} нельзя сравнить с суммой в {total.currency}"
        )
    return total.amount <= budget.amount


def is_available(h: HotelOption) -> bool:
    return h.available is not False  # None (неизвестно) не отбрасываем, но дадим warning

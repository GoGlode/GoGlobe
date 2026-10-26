"""Интерфейсы провайдеров. Владелец: Backend №1.

Агент (Backend №2) работает только через эти интерфейсы и не знает про конкретные API.
Новый реальный источник = новый класс, реализующий Protocol, + регистрация в registry.py.
"""
from typing import Protocol

from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange


class ProviderError(Exception):
    """Safe provider failure without upstream text, URLs or secrets."""

    _CODES = {
        "provider_timeout",
        "provider_unavailable",
        "provider_invalid_response",
        "provider_failure",
        "live_not_configured",
    }

    def __init__(self, code: str = "provider_failure", *, retryable: bool = False) -> None:
        self.code = code if code in self._CODES else "provider_failure"
        self.retryable = retryable
        super().__init__(self.code)


class FlightProvider(Protocol):
    async def search(
        self, destination: str, dates: DateRange, travelers: int
    ) -> list[FlightOption]: ...


class HotelProvider(Protocol):
    async def search(
        self, destination: str, dates: DateRange, travelers: int
    ) -> list[HotelOption]: ...

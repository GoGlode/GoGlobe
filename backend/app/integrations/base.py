"""Интерфейсы провайдеров. Владелец: Backend №1.

Агент (Backend №2) работает только через эти интерфейсы и не знает про конкретные API.
Новый реальный источник = новый класс, реализующий Protocol, + регистрация в registry.py.
"""
from typing import Protocol

from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange


class ProviderError(Exception):
    """Источник недоступен / таймаут. Агент обязан обработать и вернуть warnings."""


class FlightProvider(Protocol):
    async def search(
        self, destination: str, dates: DateRange, travelers: int
    ) -> list[FlightOption]: ...


class HotelProvider(Protocol):
    async def search(
        self, destination: str, dates: DateRange, travelers: int
    ) -> list[HotelOption]: ...

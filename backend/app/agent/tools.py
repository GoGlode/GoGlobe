"""Инструменты агента (Flight/Hotel Search). Тонкая обёртка над провайдерами Backend №1.

Правило: все цены/наличие/характеристики берутся ТОЛЬКО из ответов инструментов.
"""
from app.integrations.base import FlightProvider, HotelProvider, ProviderError
from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange


async def flight_search(
    p: FlightProvider, dest: str, dates: DateRange, n: int, warnings: list[str]
) -> list[FlightOption]:
    try:
        return await p.search(dest, dates, n)
    except ProviderError as e:  # таймаут/ошибка источника -> честный warning
        warnings.append(f"Перелёты недоступны: {e}")
        return []


async def hotel_search(
    p: HotelProvider, dest: str, dates: DateRange, n: int, warnings: list[str]
) -> list[HotelOption]:
    try:
        return await p.search(dest, dates, n)
    except ProviderError as e:
        warnings.append(f"Отели недоступны: {e}")
        return []

from app.config import get_settings

from .base import FlightProvider, HotelProvider
from .mock.providers import MockFlightProvider, MockHotelProvider


def get_providers() -> tuple[FlightProvider, HotelProvider]:
    if get_settings().providers == "mock":
        return MockFlightProvider(), MockHotelProvider()
    # TODO(backend-1): реальные адаптеры; при ошибке — фолбэк на снимки/моки с пометкой даты
    raise NotImplementedError("live providers are not implemented yet")

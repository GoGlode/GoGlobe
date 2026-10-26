from app.config import get_settings
from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange

from .base import FlightProvider, HotelProvider, ProviderError
from .resilience import ResilientFlightProvider, ResilientHotelProvider
from .snapshots import SnapshotFlightProvider, SnapshotHotelProvider


class _MissingLiveFlights:
    async def search(
        self, destination: str, dates: DateRange, travelers: int
    ) -> list[FlightOption]:
        raise ProviderError("live_not_configured")


class _MissingLiveHotels:
    async def search(
        self, destination: str, dates: DateRange, travelers: int
    ) -> list[HotelOption]:
        raise ProviderError("live_not_configured")


def get_providers() -> tuple[FlightProvider, HotelProvider]:
    settings = get_settings()
    if settings.providers == "snapshot":
        flights: FlightProvider = SnapshotFlightProvider()
        hotels: HotelProvider = SnapshotHotelProvider()
    else:
        flights, hotels = _MissingLiveFlights(), _MissingLiveHotels()
    return (
        ResilientFlightProvider(
            flights, settings.provider_timeout_seconds, settings.provider_max_attempts
        ),
        ResilientHotelProvider(
            hotels, settings.provider_timeout_seconds, settings.provider_max_attempts
        ),
    )

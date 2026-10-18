"""Моки провайдеров для сквозного сценария на подготовленных данных (до 27 окт)."""
from datetime import UTC, datetime

from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange, Money

DEST = "Анталья, Турция"
_HOTELS = [
    ("Sea Breeze Resort", 5, 4.6, 40, 5200),
    ("Lara Beach Hotel", 4, 4.3, 120, 3800),
    ("Old Town Boutique", 3, 4.5, 3500, 2600),
    ("Premium Palace", 5, 4.8, 15, 9800),
]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class MockFlightProvider:
    async def search(self, destination: str, dates: DateRange, travelers: int) -> list[FlightOption]:
        if "турц" not in destination.lower() and "антал" not in destination.lower():
            return []
        return [
            FlightOption(id="fl_1", destination=DEST, direct=True, dates=dates,
                         price=Money(amount=9000 * travelers), carrier="Mock Air",
                         source="mock", fetched_at=_now()),
            FlightOption(id="fl_2", destination=DEST, direct=False, dates=dates,
                         price=Money(amount=6500 * travelers), carrier="Mock Connect",
                         source="mock", fetched_at=_now()),
        ]


class MockHotelProvider:
    async def search(self, destination: str, dates: DateRange, travelers: int) -> list[HotelOption]:
        if "турц" not in destination.lower() and "антал" not in destination.lower():
            return []
        return [
            HotelOption(id=f"ht_{i}", destination=DEST, name=n, stars=s, rating=r,
                        photos=[f"https://picsum.photos/seed/goglobe{i}/600/400"],
                        price_per_night=Money(amount=p), distance_to_sea_m=d,
                        available=True, booking_url=f"https://example.com/book/ht_{i}",
                        source="mock", fetched_at=_now())
            for i, (n, s, r, d, p) in enumerate(_HOTELS)
        ]

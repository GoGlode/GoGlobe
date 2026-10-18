"""Единый формат данных от внешних сервисов (после адаптеров). Владелец: Backend №1."""
from pydantic import BaseModel

from .search import DateRange, Money


class FlightOption(BaseModel):
    id: str
    destination: str
    direct: bool
    dates: DateRange
    price: Money
    carrier: str | None = None
    source: str  # откуда данные: "mock", "aviasales", ...
    fetched_at: str  # ISO 8601


class HotelOption(BaseModel):
    id: str
    destination: str
    name: str
    stars: int | None = None
    rating: float | None = None
    photos: list[str] = []
    price_per_night: Money
    distance_to_sea_m: int | None = None
    available: bool | None = None  # None = неизвестно (не выдумываем!)
    booking_url: str
    source: str
    fetched_at: str

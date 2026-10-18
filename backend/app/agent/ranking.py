"""Ranking Tool: прозрачный скоринг 0..1. Владелец: Backend №2."""
from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import Money


def score(h: HotelOption, f: FlightOption, total: Money, budget: Money | None,
          wishes: list[str]) -> float:
    s = 0.0
    s += 0.35 * ((h.rating or 4.0) / 5)
    if budget:
        s += 0.30 * (1 - total.amount / budget.amount)
    if "sea_view" in wishes and h.distance_to_sea_m is not None:
        s += 0.20 * (1 if h.distance_to_sea_m <= 150 else 0.3)
    if "direct_flight" in wishes and f.direct:
        s += 0.15
    return round(s, 3)

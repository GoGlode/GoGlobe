"""Explain Tool: «почему подходит». Шаблоны для моков; позже — LLM, но ТОЛЬКО по данным из tools."""
from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import Confidence, Explanation, Money


def explain(h: HotelOption, f: FlightOption, total: Money, budget: Money | None,
            wishes: list[str]) -> Explanation:
    why, pros, cons = [], [], []
    if budget and total.amount <= budget.amount:
        why.append("в бюджете")
        pros.append(f"Итого {total.amount:,.0f} ₽ при лимите {budget.amount:,.0f} ₽".replace(",", " "))
    if "sea_view" in wishes and h.distance_to_sea_m is not None and h.distance_to_sea_m <= 150:
        why.append("первая линия")
        pros.append(f"До моря {h.distance_to_sea_m} м")
    if "direct_flight" in wishes:
        (pros if f.direct else cons).append("Прямой рейс" if f.direct else "Рейс с пересадкой")
    if h.available is None:
        cons.append("Наличие номеров не подтверждено")
    return Explanation(why=why, pros=pros, cons=cons, sources=sorted({h.source, f.source}),
                       confidence=Confidence.confirmed if h.available else Confidence.estimated)

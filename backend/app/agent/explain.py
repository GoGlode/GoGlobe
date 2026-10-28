"""Explain Tool: «почему подходит». Шаблоны для моков; позже — LLM, но ТОЛЬКО по данным из tools."""

from app.agent.currency import format_money
from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import Confidence, Explanation, Money


def explain(
    h: HotelOption,
    f: FlightOption,
    total: Money,
    budget: Money | None,
    wishes: list[str],
    dest_info: object | None = None,
) -> Explanation:
    why, pros, cons = [], [], []
    if budget and total.amount <= budget.amount:
        why.append("в бюджете")
        # Суммы выводятся в своей валюте, а не всегда в рублях (F-09).
        pros.append(f"Итого {format_money(total)} при лимите {format_money(budget)}")
    if "sea_view" in wishes and h.distance_to_sea_m is not None and h.distance_to_sea_m <= 150:
        why.append("первая линия")
        pros.append(f"До моря {h.distance_to_sea_m} м")
    if "direct_flight" in wishes:
        (pros if f.direct else cons).append("Прямой рейс" if f.direct else "Рейс с пересадкой")
    if h.available is None:
        cons.append("Наличие номеров не подтверждено")
    if dest_info is not None:
        season = getattr(dest_info, "season_status", None)
        temp = getattr(dest_info, "temperature_c", None)
        is_reference = getattr(dest_info, "is_reference", False)
        # Справочные климатические данные нельзя выдавать за прогноз на даты поездки.
        if season:
            prefix = "Сезонность (справочно)" if is_reference else "Сезонность"
            pros.append(f"{prefix}: {season}")
        if temp is not None:
            label = "Температура (справочная норма" if is_reference else "Температура"
            suffix = ", не прогноз на даты поездки)" if is_reference else ""
            pros.append(f"{label}: ~{temp}°C{suffix}")
    return Explanation(
        why=why,
        pros=pros,
        cons=cons,
        sources=sorted({h.source, f.source}),
        confidence=Confidence.confirmed if h.available else Confidence.estimated,
    )

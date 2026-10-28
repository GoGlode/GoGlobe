"""Ranking Tool: прозрачный скоринг 0..1. Владелец: Backend №2.

Баллы начисляются только за подтверждённые данные:
* нет рейтинга отеля — вклад рейтинга не начисляется (никаких подстановок «4.0»);
* нет бюджета или он нулевой — вклад бюджета не начисляется, деления на ноль нет;
* расстояние до моря и прямой рейс учитываются только при наличии факта.

Итоговый score всегда лежит в 0..1.
"""

from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import Money


def score(
    h: HotelOption, f: FlightOption, total: Money, budget: Money | None, wishes: list[str]
) -> float:
    s = 0.0

    # 0.35 — рейтинг. Неизвестный рейтинг не заменяется средним значением (F-23).
    if h.rating is not None:
        rating = max(0.0, min(5.0, h.rating))
        s += 0.35 * (rating / 5)

    # 0.30 — запас по бюджету. Нулевой бюджет не приводит к делению на ноль (F-15).
    if budget is not None and budget.amount > 0:
        s += 0.30 * max(0.0, min(1.0, 1 - total.amount / budget.amount))

    # 0.20 — близость моря: только если расстояние реально известно.
    if "sea_view" in wishes and h.distance_to_sea_m is not None:
        s += 0.20 * (1 if h.distance_to_sea_m <= 150 else 0.3)

    # 0.15 — прямой рейс: факт из провайдера, а не пожелание пользователя.
    if "direct_flight" in wishes and f.direct:
        s += 0.15

    return round(max(0.0, min(1.0, s)), 3)

"""AI-agent adapter for the v0.3 Planner boundary.

The adapter keeps Backend #2's deterministic intent-first approach, but only
uses facts supplied by v0.3 integration ports. It owns neither HTTP nor storage
and deliberately does not manufacture offer data.
"""
from __future__ import annotations

from copy import deepcopy

from app.contracts import examples
from app.integrations.ports import DestinationCriteria, remaining_seconds
from app.intent_preview import preview_intent_async
from app.planning import AgentPlan, NeedsClarification, PlanContext, UnsupportedDemo


_RECOMMENDATIONS = {
    "Рим": [
        ["Исторический центр — прогулка от Колизея к Римскому форуму", "Пантеон — знакомство с античной архитектурой", "Вечерняя прогулка по площади Навона"],
        ["Ватикан — музеи и площадь Святого Петра как рекомендации", "Фонтан Треви — прогулка по району Треви", "Вилла Боргезе — спокойная прогулка в парке"],
    ],
    "Стамбул": [
        ["Айя-София — знакомство с историей Старого города", "Голубая мечеть — осмотр площади Султанахмет", "Дворец Топкапы — прогулка по территории дворца"],
        ["Гранд-базар — прогулка по историческим торговым рядам", "Галатская башня — панорамная точка района Галата", "Прогулка по Босфору — маршрут вдоль воды"],
    ],
    "Казань": [
        ["Казанский кремль — прогулка по историческому центру", "Мечеть Кул-Шариф — знакомство с архитектурой кремля", "Улица Баумана — пешеходная прогулка по центру"],
        ["Дворец земледельцев — прогулка у набережной", "Старо-Татарская слобода — знакомство с историческими кварталами", "Центр семьи «Казан» — видовая прогулка у реки"],
    ],
}


class AgentPlanner:
    """Adapt parsed intent and destination-port facts to ``AgentPlan``."""

    async def plan(self, context: PlanContext) -> AgentPlan:
        # Backend #2's safe no-provider parsing principle: explicit v0.3 params
        # take precedence over words in the query.
        parsed = (await preview_intent_async(context.query, context.params))["parsed"]
        destination_query = parsed["destination"]
        if destination_query is None:
            raise NeedsClarification("destination", "Куда вы хотите поехать?")
        duration = parsed["duration_days"]
        remaining_seconds(context.deadline_at)
        destinations = await context.tools.destinations(
            DestinationCriteria(destination_query, context.deadline_at)
        )
        remaining_seconds(context.deadline_at)
        if not destinations.items:
            # A name without a port-backed result has no trustworthy timezone
            # or catalog source for the BFF Destination contract.
            if destination_query.casefold() in {"турция", "turkey"}:
                raise NeedsClarification("destination", "Какой город в Турции выбрать? Доступны: Стамбул.")
            raise UnsupportedDemo(
                "Направление не найдено в демонстрационном каталоге. Доступны: Рим, Стамбул и Казань."
            )
        if duration is None:
            raise NeedsClarification("duration_days", "На сколько дней планируется поездка?")

        destination = deepcopy(destinations.items[0]["destination"])
        fixture = deepcopy(examples()["trip_relative"]["value"])
        catalog = _RECOMMENDATIONS.get(destination["name"], [])
        if not catalog:
            raise UnsupportedDemo("Для этого направления нет проверенного набора рекомендаций.")
        wishes = set(parsed.get("wishes") or context.params.get("wishes") or [])
        if wishes & {"near_sea", "sea_view"} and destination["name"] == "Стамбул":
            catalog = sorted(catalog, key=lambda group: any("Босфору" in item for item in group), reverse=True)
        days = []
        for index in range(1, duration + 1):
            recommendations = catalog[(index - 1) % len(catalog)]
            items = []
            for order, title in enumerate(recommendations, start=1):
                items.append({
                    "item_id": f"agent_day_{index}_{order}", "order": order,
                    "title": title, "kind": "activity", "local_time": None,
                    "place": None, "verification": "suggested", "source_ids": [],
                })
            days.append({"day_index": index, "date": None, "items": items})
        return AgentPlan(
            destination=destination,
            duration_days=duration,
            itinerary={"days": days},
            sources=deepcopy(destinations.sources),
            warnings=deepcopy(destinations.warnings),
            data_mode=destinations.data_mode,
        )

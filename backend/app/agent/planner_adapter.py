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
        template = fixture["itinerary"]["days"][0]["items"][0]
        days = []
        for index in range(1, duration + 1):
            item = deepcopy(template)
            item.update(
                item_id=f"agent_day_{index}",
                order=1,
                title=f"Знакомство с направлением: день {index}",
                source_ids=[],
            )
            days.append({"day_index": index, "date": None, "items": [item]})
        return AgentPlan(
            destination=destination,
            duration_days=duration,
            itinerary={"days": days},
            sources=deepcopy(destinations.sources),
            warnings=deepcopy(destinations.warnings),
            data_mode=destinations.data_mode,
        )

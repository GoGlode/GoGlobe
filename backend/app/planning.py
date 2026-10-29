"""Порт агента и проверка его результата перед передачей в BFF/storage."""
import asyncio
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Literal, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.contracts import examples, validate
from app.integrations.ports import parse_timestamp, remaining_seconds, walk
from app.integrations.service import IntegrationTools
from app.integrations.resilience import ResiliencePolicy, ResilientIntegrationTools, tool_trace
from app.intent_preview import preview_intent


@dataclass(frozen=True)
class PlanContext:
    query: str
    params: dict
    deadline_at: datetime
    tools: IntegrationTools


@dataclass(frozen=True)
class AgentPlan:
    destination: dict
    duration_days: int
    itinerary: dict
    sources: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    data_mode: Literal["demo", "live"] = "demo"

    def validate(self, params: dict) -> None:
        validate("Destination", self.destination)
        validate("Itinerary", self.itinerary)
        validate("Params", {"duration_days": self.duration_days})
        if self.data_mode not in {"demo", "live"}:
            raise ValueError("Invalid plan data mode")
        days = self.itinerary["days"]
        if any(day["date"] is not None for day in days):
            raise ValueError("Agent must return a relative itinerary")
        if len(days) != self.duration_days or [day["day_index"] for day in days] != list(range(1, self.duration_days + 1)):
            raise ValueError("Itinerary days do not match duration")
        if params.get("duration_days", self.duration_days) != self.duration_days:
            raise ValueError("Agent changed explicit duration")
        if params.get("destination", self.destination["name"]).casefold() not in {self.destination["name"].casefold(), "rome" if self.destination["name"] == "Рим" else self.destination["name"].casefold()}:
            raise ValueError("Agent changed explicit destination")
        for source in self.sources:
            validate("Source", source)
            if parse_timestamp(source["checked_at"]).timestamp() > datetime.now(timezone.utc).timestamp() + 60:
                raise ValueError("Agent source is in the future")
        for warning in self.warnings:
            validate("Warning", warning)
        if len(self.sources) > 100 or len(self.warnings) > 29:
            raise ValueError("Too many agent sources/warnings")
        ids = {source["source_id"] for source in self.sources}
        if len(ids) != len(self.sources):
            raise ValueError("Duplicate source_id")
        item_ids = []
        for day in days:
            if [item["order"] for item in day["items"]] != list(range(1, len(day["items"]) + 1)):
                raise ValueError("Invalid itinerary item order")
            item_ids.extend(item["item_id"] for item in day["items"])
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("Duplicate itinerary item_id")
        for node in walk(self.itinerary):
            if "source_ids" in node and not set(node["source_ids"]) <= ids:
                raise ValueError("Unknown itinerary source")
            if node.get("verification") == "verified" and not node.get("source_ids"):
                raise ValueError("Verified fact requires a source")
        validate_timezone(self.destination["timezone"])


def validate_timezone(value: str | None) -> None:
    if value is not None:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown IANA timezone") from None


class Planner(Protocol):
    async def plan(self, context: PlanContext) -> AgentPlan: ...


class DemoPlanner:
    async def plan(self, context: PlanContext) -> AgentPlan:
        preview = preview_intent(context.query, context.params)["parsed"]
        if preview["destination"] is None:
            raise NeedsClarification("destination", "Куда вы хотите поехать?")
        if preview["duration_days"] is None:
            raise NeedsClarification("duration_days", "На сколько дней планируется поездка?")
        fixture = deepcopy(examples()["trip_relative"]["value"])
        destination = preview["destination"]
        timezones = {
            "Рим": "Europe/Rome", "Стамбул": "Europe/Istanbul",
            "Казань": "Europe/Moscow", "Москва": "Europe/Moscow",
            "Париж": "Europe/Paris", "Берлин": "Europe/Berlin",
        }
        destination_value = {"name": destination, "timezone": timezones.get(destination), "photos": []}
        duration = preview["duration_days"]
        template = fixture["itinerary"]["days"][0]["items"][0]
        days = []
        for index in range(1, duration + 1):
            item = deepcopy(template)
            item.update(item_id=f"i_day_{index}", order=1,
                        title=f"Знакомство с направлением: день {index}")
            days.append({"day_index": index, "date": None, "items": [item]})
        return AgentPlan(destination_value, duration, {"days": days}, data_mode="demo")


class UnsupportedDemo(ValueError):
    pass


class NeedsClarification(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)


class PlanningService:
    def __init__(self, agent: Planner | None = None, tools: IntegrationTools | None = None):
        self.agent = agent if agent is not None else DemoPlanner()
        self.tools = tools if tools is not None else ResilientIntegrationTools(policy=ResiliencePolicy.from_env())

    async def plan(self, body: dict, deadline_at: datetime) -> AgentPlan:
        context = PlanContext(body["query"], deepcopy(body.get("params", {})), deadline_at, self.tools)
        with tool_trace() as trace:
            async with asyncio.timeout(remaining_seconds(deadline_at)) as budget:
                result = await self.agent.plan(context)
        if budget.expired():
            raise TimeoutError("Agent deadline expired")
        remaining_seconds(deadline_at)
        # Недоверенный ответ проверяется до его попадания в БД.
        if not isinstance(result, AgentPlan):
            raise ValueError("Planner must return AgentPlan")
        # Validate the original reply before adding trace metadata. Truncation
        # and mode correction must never hide an invalid agent response.
        result.validate(body.get("params", {}))
        if trace:
            warnings = deepcopy(result.warnings[:28])
            code = "DEMO_FALLBACK" if "DEMO_FALLBACK" in trace else "DEMO_DATA"
            if not any(item.get("code") == code for item in warnings):
                warnings.append({"code": code, "message": "Использованы демонстрационные данные инструментов.", "trip_id": None})
            result = replace(result, data_mode="demo", warnings=warnings)
        result = deepcopy(result)
        remaining_seconds(deadline_at)
        return result

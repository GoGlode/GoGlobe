"""Ограниченные общим deadline вызовы заменяемых поставщиков."""
import asyncio
from dataclasses import replace
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.contracts import examples
from app.integrations.ports import DestinationCriteria, FlightCriteria, HotelCriteria, ProviderError, ToolResult, parse_timestamp, remaining_seconds, sanitize_booking_links, walk
from app.integrations.snapshots import load_snapshots


def unavailable(code: str, mode: str = "demo") -> ToolResult:
    return ToolResult("unavailable", [], [], [
        {"code": code, "message": "Источник не вернул подтверждённые данные.", "trip_id": None},
    ], mode)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _apply_snapshot_freshness(result: ToolResult, fetched_at: datetime) -> ToolResult:
    """Use snapshot collection time as the freshness boundary of its data."""
    checked_at = _timestamp(fetched_at)
    for source in result.sources:
        source["checked_at"] = checked_at
    for node in walk(result.items):
        if "checked_at" not in node:
            continue
        previous_checked_at = parse_timestamp(node["checked_at"])
        previous_valid_until = (
            parse_timestamp(node["valid_until"])
            if node.get("valid_until") else None
        )
        node["checked_at"] = checked_at
        if previous_valid_until is not None:
            node["valid_until"] = _timestamp(
                fetched_at + (previous_valid_until - previous_checked_at)
            )
    return result


_PLACE_ALIASES = {
    "rome": "рим",
    "istanbul": "стамбул",
    "kazan": "казань",
    "moscow": "москва",
}


def _place_key(value: str) -> str:
    normalized = value.strip().casefold()
    return _PLACE_ALIASES.get(normalized, normalized)


def _matches_place(actual: str, expected: str) -> bool:
    return _place_key(actual) == _place_key(expected)


class DemoHotelProvider:
    data_mode = "demo"

    async def search(self, criteria: HotelCriteria) -> ToolResult:
        if criteria.budget is not None or criteria.wishes:
            return ToolResult("ok", [], [], [], "demo")
        snapshot = next((item for item in load_snapshots("hotels")
                         if _matches_place(criteria.destination, item.context["destination"])
                         and criteria.stay == item.context["stay"]
                         and criteria.travelers == item.context["travelers"]), None)
        if snapshot is None:
            return ToolResult("ok", [], [], [], "demo")
        fixture = _apply_snapshot_freshness(snapshot.result, snapshot.fetched_at)
        for item in fixture.items:
            item["booking_url"] = None
            item["availability"] = "unknown"
        return fixture


class DemoFlightProvider:
    data_mode = "demo"

    async def search(self, criteria: FlightCriteria) -> ToolResult:
        if criteria.budget is not None or criteria.wishes:
            return ToolResult("ok", [], [], [], "demo")
        snapshot = next((item for item in load_snapshots("flights")
                         if _matches_place(criteria.destination, item.context["destination"])
                         and _matches_place(criteria.origin, item.context["origin"])
                         and criteria.flight_dates == item.context["flight_dates"]
                         and criteria.travelers == item.context["travelers"]), None)
        if snapshot is None:
            return ToolResult("ok", [], [], [], "demo")
        fixture = _apply_snapshot_freshness(snapshot.result, snapshot.fetched_at)
        for item in fixture.items:
            item["booking_url"] = None
            item["availability"] = "unknown"
        return fixture


class DemoDestinationProvider:
    data_mode = "demo"

    async def search(self, criteria: DestinationCriteria) -> ToolResult:
        if criteria.query.strip().casefold() not in {"рим", "rome"}:
            return ToolResult("ok", [], [], [], "demo")
        destination = deepcopy(examples()["trip_relative"]["value"]["destination"])
        source = {"source_id": "demo_rome_catalog", "name": "Демонстрационный каталог Рима",
                  "url": None, "checked_at": "2026-10-20T09:00:00Z", "kind": "catalog"}
        place = {"place_id": "demo_rome", "name": destination["name"], "latitude": None,
                 "longitude": None, "timezone": destination["timezone"], "verification": "unknown",
                 "source_ids": [source["source_id"]]}
        return ToolResult("ok", [{"destination": destination, "place": place, "source_ids": place["source_ids"]}],
                          [source], [{"code": "DEMO_DATA", "message": "Демонстрационный каталог направлений.", "trip_id": None}], "demo")


class UnconfiguredLiveProvider:
    """Explicit live placeholder that never falls back to local snapshots."""

    data_mode = "live"

    async def search(self, criteria) -> ToolResult:
        raise ProviderError("PROVIDER_INVALID_CONFIGURATION")


def default_offer_providers(mode: str):
    if mode == "snapshot":
        return DemoHotelProvider(), DemoFlightProvider()
    if mode == "live":
        return UnconfiguredLiveProvider(), UnconfiguredLiveProvider()
    raise ValueError("Invalid provider mode")


class IntegrationTools:
    def __init__(self, hotels=None, flights=None, *, destinations=None, allowed_booking_hosts: set[str] | None = None,
                 allowed_booking_query_keys: set[str] | None = None):
        self.hotel_provider = hotels if hotels is not None else DemoHotelProvider()
        self.flight_provider = flights if flights is not None else DemoFlightProvider()
        self.destination_provider = destinations if destinations is not None else DemoDestinationProvider()
        self._slots = asyncio.Semaphore(8)
        self.allowed_booking_hosts = {host.strip().lower() for host in (allowed_booking_hosts or ())}
        self.allowed_booking_query_keys = set(allowed_booking_query_keys or ())

    async def hotels(self, criteria: HotelCriteria) -> ToolResult:
        return await self._call("hotels", self.hotel_provider, criteria)

    async def flights(self, criteria: FlightCriteria) -> ToolResult:
        return await self._call("flights", self.flight_provider, criteria)

    async def destinations(self, criteria: DestinationCriteria) -> ToolResult:
        return await self._call("destinations", self.destination_provider, criteria)

    async def _call(self, kind, provider, criteria):
        mode = getattr(provider, "data_mode", "live")
        if not isinstance(mode, str) or mode not in {"demo", "live"}:
            return unavailable("PROVIDER_INVALID_CONFIGURATION", "live")
        try:
            criteria = replace(deepcopy(criteria))
            async with asyncio.timeout(remaining_seconds(criteria.deadline_at)) as budget:
                async with self._slots:
                    result = await provider.search(deepcopy(criteria))
                    if budget.expired():
                        raise TimeoutError("Provider deadline expired")
                    remaining_seconds(criteria.deadline_at)
                    result = sanitize_booking_links(result, self.allowed_booking_hosts, self.allowed_booking_query_keys)
                    result.validate_for(kind)
                    if result.data_mode != mode:
                        raise ValueError("Provider changed data mode")
                    for item in result.items:
                        if kind == "hotels" and (item["check_in"] != criteria.stay["check_in"] or item["check_out"] != criteria.stay["check_out"]):
                            raise ValueError("Hotel dates do not match criteria")
                        if kind == "flights":
                            for field, target in [("outbound_segments", "outbound_date"), ("inbound_segments", "return_date")]:
                                leg = item[field][0]
                                departure = parse_timestamp(leg["departure_at"]).astimezone(ZoneInfo(leg["origin"]["timezone"]))
                                if departure.date().isoformat() != criteria.flight_dates[target]:
                                    raise ValueError("Flight date does not match criteria")
                    for node in walk(result.items):
                        if node.get("checked_at") and "coverage" in node:
                            checked = parse_timestamp(node["checked_at"])
                            expires = parse_timestamp(node["valid_until"]) if node.get("valid_until") else checked + timedelta(minutes=15)
                            if expires <= datetime.now(timezone.utc):
                                node["stale"] = True
                    remaining_seconds(criteria.deadline_at)
                    return result
        except TimeoutError:
            return unavailable("PROVIDER_TIMEOUT", mode)
        except ProviderError as exc:
            safe_codes = {"PROVIDER_AUTH_ERROR", "PROVIDER_RATE_LIMITED", "PROVIDER_HTTP_ERROR",
                          "PROVIDER_TIMEOUT", "PROVIDER_TRANSPORT_ERROR", "PROVIDER_INVALID_RESPONSE",
                          "PROVIDER_RESPONSE_TOO_LARGE", "PROVIDER_INVALID_CONFIGURATION"}
            return unavailable(exc.code if exc.code in safe_codes else "PROVIDER_INVALID_OR_UNAVAILABLE", mode)
        except Exception:
            return unavailable("PROVIDER_INVALID_OR_UNAVAILABLE", mode)

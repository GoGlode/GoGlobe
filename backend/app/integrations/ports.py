from dataclasses import dataclass
from copy import deepcopy
from datetime import date, datetime, timezone
import math
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo
from urllib.parse import parse_qsl, urlsplit

from app.contracts import validate, valid_uri

Json = dict[str, Any]


def parse_timestamp(value: str) -> datetime:
    """RFC3339 permits lowercase t/z; preserve the original serialized value."""
    return datetime.fromisoformat(value.upper())


@dataclass(frozen=True)
class DestinationCriteria:
    query: str
    deadline_at: datetime

    def __post_init__(self):
        validate("Params", {"destination": self.query})
        if not self.query.strip():
            raise ValueError("Destination query must not be blank")
        remaining_seconds(self.deadline_at)


@dataclass(frozen=True)
class HotelCriteria:
    destination: str
    stay: Json
    travelers: Json
    budget: Json | None
    wishes: list[str]
    deadline_at: datetime

    def __post_init__(self):
        validate("Stay", self.stay)
        validate("Travelers", self.travelers)
        validate_travelers(self.travelers)
        if self.budget is not None:
            validate("Budget", self.budget)
        validate("Params", {"destination": self.destination, "wishes": self.wishes})
        if date.fromisoformat(self.stay["check_out"]) <= date.fromisoformat(self.stay["check_in"]):
            raise ValueError("check_out must be after check_in")
        remaining_seconds(self.deadline_at)


@dataclass(frozen=True)
class FlightCriteria:
    destination: str
    origin: str
    flight_dates: Json
    travelers: Json
    budget: Json | None
    wishes: list[str]
    deadline_at: datetime

    def __post_init__(self):
        validate("FlightDates", self.flight_dates)
        validate("Travelers", self.travelers)
        validate_travelers(self.travelers)
        if self.budget is not None:
            validate("Budget", self.budget)
        validate("Params", {"destination": self.destination, "origin": self.origin, "wishes": self.wishes})
        if self.flight_dates["return_date"] < self.flight_dates["outbound_date"]:
            raise ValueError("return_date must not precede outbound_date")
        remaining_seconds(self.deadline_at)


def validate_travelers(travelers: Json) -> None:
    if travelers["adults"] + len(travelers["children_ages"]) > 9:
        raise ValueError("Maximum 9 travelers")


def remaining_seconds(deadline_at: datetime) -> float:
    if deadline_at.tzinfo is None or deadline_at.utcoffset() is None:
        raise ValueError("deadline_at must have a timezone")
    remaining = (deadline_at - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        raise TimeoutError("Общий срок выполнения запроса истёк")
    return remaining


@dataclass(frozen=True)
class ToolResult:
    status: Literal["ok", "partial", "unavailable"]
    items: list[Json]
    sources: list[Json]
    warnings: list[Json]
    data_mode: Literal["live", "demo"]

    def validate_for(self, kind: Literal["hotels", "flights", "destinations"]) -> None:
        if kind not in {"hotels", "flights", "destinations"}:
            raise ValueError("Unknown tool kind")
        if self.status not in {"ok", "partial", "unavailable"} or self.data_mode not in {"live", "demo"}:
            raise ValueError("Invalid tool status/data mode")
        if self.status == "unavailable" and self.items:
            raise ValueError("Unavailable source cannot return offers")
        if self.status == "partial" and (not self.items or not self.warnings):
            raise ValueError("Partial result requires useful items and warnings")
        if len(self.items) > 20 or len(self.sources) > 100 or len(self.warnings) > 30:
            raise ValueError("Tool response exceeds contract limits")
        for source in self.sources:
            validate("Source", source)
            if parse_timestamp(source["checked_at"]).timestamp() > datetime.now().timestamp() + 60:
                raise ValueError("Source checked_at is in the future")
        for warning in self.warnings:
            validate("Warning", warning)
        source_ids = {source["source_id"] for source in self.sources}
        source_kinds = {source["source_id"]: source["kind"] for source in self.sources}
        if len(source_ids) != len(self.sources):
            raise ValueError("Duplicate source_id")
        for item in self.items:
            if kind == "destinations":
                if set(item) != {"destination", "place", "source_ids"}:
                    raise ValueError("Invalid destination item fields")
                validate("Destination", item["destination"])
                validate("Place", item["place"])
                validate("Place", {**item["place"], "source_ids": item["source_ids"]})
                if not item["source_ids"]:
                    raise ValueError("Destination requires a source")
                if item["destination"]["timezone"] != item["place"]["timezone"]:
                    raise ValueError("Destination timezone differs from place")
            else:
                validate("HotelOffer" if kind == "hotels" else "FlightOffer", item)
            for node in walk(item):
                for value in node.values():
                    if isinstance(value, float) and not math.isfinite(value):
                        raise ValueError("Non-finite provider number")
                if node.get("timezone") is not None:
                    ZoneInfo(node["timezone"])
                if "source_ids" in node:
                    if len(node["source_ids"]) != len(set(node["source_ids"])):
                        raise ValueError("Duplicate source reference")
                    if not set(node["source_ids"]) <= source_ids:
                        raise ValueError("Unknown price/offer source_id")
                if node.get("verification") == "verified" and not node.get("source_ids"):
                    raise ValueError("Verified place requires a source")
                if "coverage" in node and set(node["coverage"]) & set(node["exclusions"]):
                    raise ValueError("Price coverage and exclusions overlap")
                if node.get("status") == "quoted" and any(source_kinds[source_id] != "provider" for source_id in node["source_ids"]):
                    raise ValueError("Quoted price requires a provider source")
                if node.get("status") == "estimated" and not any(source_kinds[source_id] == "estimate_method" for source_id in node["source_ids"]):
                    raise ValueError("Estimated price requires an estimate method")
                if node.get("checked_at"):
                    checked = parse_timestamp(node["checked_at"])
                    if checked.timestamp() > datetime.now().timestamp() + 60:
                        raise ValueError("Source/price checked_at is in the future")
                    if node.get("valid_until") and parse_timestamp(node["valid_until"]) < checked:
                        raise ValueError("Price validity precedes check time")
                if "departure_at" in node:
                    elapsed = parse_timestamp(node["arrival_at"]) - parse_timestamp(node["departure_at"])
                    if elapsed.total_seconds() <= 0 or elapsed.total_seconds() != node["duration_minutes"] * 60:
                        raise ValueError("Invalid segment duration")
            if kind == "hotels" and item["check_out"] <= item["check_in"]:
                raise ValueError("Invalid hotel dates")
            if kind in {"hotels", "flights"}:
                expected_basis = "party_stay_total" if kind == "hotels" else "party_return_total"
                if item["total_price"]["basis"] != expected_basis or (item["total_price"]["money"] is not None and kind not in item["total_price"]["coverage"]):
                    raise ValueError("Total price has incorrect basis/coverage")
            if kind == "hotels" and item["nightly_price"]["basis"] != "room_night":
                raise ValueError("Nightly price has incorrect basis")
            if kind == "hotels" and item["nightly_price"]["money"] is not None and "hotels" not in item["nightly_price"]["coverage"]:
                raise ValueError("Nightly price has incorrect coverage")
            if kind == "flights":
                if parse_timestamp(item["inbound_segments"][0]["departure_at"]) <= parse_timestamp(item["outbound_segments"][-1]["arrival_at"]):
                    raise ValueError("Return flight starts before outbound arrival")
                if (item["inbound_segments"][0]["origin"]["code"] != item["outbound_segments"][-1]["destination"]["code"] or
                        item["inbound_segments"][-1]["destination"]["code"] != item["outbound_segments"][0]["origin"]["code"]):
                    raise ValueError("Return route does not reverse outbound route")
                for leg in (item["outbound_segments"], item["inbound_segments"]):
                    for previous, following in zip(leg, leg[1:]):
                        if previous["destination"]["code"] != following["origin"]["code"] or parse_timestamp(previous["arrival_at"]) > parse_timestamp(following["departure_at"]):
                            raise ValueError("Invalid connecting flight segments")
        ids = [item["place"]["place_id"] if kind == "destinations" else item["offer_id"] for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate offer_id")


def sanitize_booking_links(result: ToolResult, allowed_hosts=None, allowed_query_keys=None) -> ToolResult:
    """Remove unsafe public links without discarding otherwise useful data."""
    copied = deepcopy(result)
    if not isinstance(copied.items, list) or not isinstance(copied.warnings, list):
        return copied  # The schema boundary will reject invalid containers.
    dropped = False
    for item in copied.items[:20]:
        if not isinstance(item, dict) or not item.get("booking_url"):
            continue
        value = item["booking_url"]
        try:
            link = urlsplit(value)
            allowed = (isinstance(value, str) and valid_uri(value) and link.scheme == "https"
                       and bool(link.hostname) and link.port in {None, 443}
                       and not (link.username or link.password or link.fragment))
            if allowed and allowed_hosts is not None:
                allowed = (link.hostname in allowed_hosts and
                           {key for key, _ in parse_qsl(link.query, keep_blank_values=True)} <= set(allowed_query_keys or ()))
        except (AttributeError, ValueError, TypeError, UnicodeError):
            allowed = False
        if not allowed:
            item["booking_url"] = None
            dropped = True
    if dropped and len(copied.warnings) < 30:
        copied.warnings.append({"code": "BOOKING_URL_NOT_ALLOWED", "message": "Ссылка на бронирование не прошла проверку.", "trip_id": None})
    dropped_source = False
    if isinstance(copied.sources, list):
        for source in copied.sources[:100]:
            if not isinstance(source, dict) or source.get("url") is None:
                continue
            value = source["url"]
            try:
                link = urlsplit(value)
                allowed = (isinstance(value, str) and valid_uri(value) and link.scheme == "https"
                           and bool(link.hostname) and link.port in {None, 443}
                           and not (link.username or link.password or link.query or link.fragment))
            except (AttributeError, ValueError, TypeError, UnicodeError):
                allowed = False
            if not allowed:
                source["url"] = None
                dropped_source = True
    if dropped_source and len(copied.warnings) < 30:
        copied.warnings.append({"code": "SOURCE_URL_NOT_ALLOWED", "message": "Ссылка на источник не прошла проверку.", "trip_id": None})
    return copied


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


class HotelProvider(Protocol):
    async def search(self, criteria: HotelCriteria) -> ToolResult: ...


class FlightProvider(Protocol):
    async def search(self, criteria: FlightCriteria) -> ToolResult: ...


class DestinationProvider(Protocol):
    async def search(self, criteria: DestinationCriteria) -> ToolResult: ...


class ProviderError(RuntimeError):
    """Public code only; upstream bodies, URLs and credentials stay private."""

    def __init__(self, code: str, *, retryable: bool = False, retry_after_seconds: float | None = None):
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        super().__init__(code)


class ProviderNotConfigured(RuntimeError):
    """Нет документации/настроек реального поставщика; не подменять live моками."""

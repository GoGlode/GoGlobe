"""Load local provider snapshots and validate them at the package boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange

SnapshotKind = Literal["flights", "hotels"]
SnapshotOption = FlightOption | HotelOption


class SnapshotError(ValueError):
    """Base error for snapshots that cannot be safely used."""


class SnapshotNotFoundError(SnapshotError):
    """The requested snapshot file does not exist."""


class SnapshotValidationError(SnapshotError):
    """The snapshot exists but is malformed or violates the local contract."""


@dataclass(frozen=True)
class SnapshotCriteria:
    destination: str
    aliases: tuple[str, ...]
    dates: DateRange
    travelers: int


@dataclass(frozen=True)
class Snapshot:
    kind: SnapshotKind
    source: str
    fetched_at: str
    criteria: SnapshotCriteria
    items: tuple[SnapshotOption, ...]


def load_snapshots(
    kind: SnapshotKind, directory: str | Path | None = None
) -> tuple[Snapshot, ...]:
    """Load all snapshots of *kind* from package data or a supplied directory."""
    _validate_kind(kind)
    root = Path(directory) if directory is not None else files(__package__)
    locations = sorted(root.glob(f"{kind}_*.json"), key=lambda item: item.name)
    if not locations:
        raise SnapshotNotFoundError(f"No {kind} snapshots found")

    snapshots = tuple(load_snapshot(kind, location) for location in locations)
    keys = [
        (
            snapshot.criteria.destination.casefold(),
            snapshot.criteria.dates.from_,
            snapshot.criteria.dates.to,
            snapshot.criteria.travelers,
        )
        for snapshot in snapshots
    ]
    if len(keys) != len(set(keys)):
        raise SnapshotValidationError(f"Duplicate {kind} snapshot criteria")
    return snapshots


def load_snapshot(kind: SnapshotKind, path: str | Path) -> Snapshot:
    """Load one JSON file without leaking JSON or Pydantic errors to callers."""
    _validate_kind(kind)
    location = Path(path) if isinstance(path, str) else path
    try:
        document = json.loads(location.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SnapshotNotFoundError(f"{kind} snapshot not found: {location}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SnapshotValidationError(f"Cannot read {kind} snapshot: {location}") from exc

    try:
        return _validate_document(kind, document)
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise SnapshotValidationError(f"Invalid {kind} snapshot: {location}") from exc


def _validate_kind(kind: str) -> None:
    if kind not in {"flights", "hotels"}:
        raise ValueError(f"Unsupported snapshot kind: {kind}")


def _validate_document(kind: SnapshotKind, document: object) -> Snapshot:
    if not isinstance(document, dict):
        raise TypeError("Snapshot root must be an object")
    if set(document) != {"kind", "source", "fetched_at", "criteria", "items"}:
        raise ValueError("Unexpected snapshot fields")
    if document["kind"] != kind:
        raise ValueError("Snapshot kind does not match requested kind")

    source = document["source"]
    fetched_at = document["fetched_at"]
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Snapshot source must be a non-empty string")
    if not isinstance(fetched_at, str):
        raise TypeError("Snapshot fetched_at must be a string")
    fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    if fetched.tzinfo is None or fetched.utcoffset() is None:
        raise ValueError("Snapshot fetched_at must include a timezone")

    criteria_data = document["criteria"]
    if not isinstance(criteria_data, dict):
        raise TypeError("Snapshot criteria must be an object")
    if set(criteria_data) != {"destination", "aliases", "dates", "travelers"}:
        raise ValueError("Unexpected snapshot criteria fields")
    destination = criteria_data["destination"]
    aliases = criteria_data["aliases"]
    travelers = criteria_data["travelers"]
    if not isinstance(destination, str) or not destination.strip():
        raise ValueError("Snapshot destination must be a non-empty string")
    if (
        not isinstance(aliases, list)
        or not aliases
        or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)
    ):
        raise ValueError("Snapshot aliases must be a non-empty string list")
    if not isinstance(travelers, int) or isinstance(travelers, bool) or travelers < 1:
        raise ValueError("Snapshot travelers must be a positive integer")
    dates = DateRange.model_validate(criteria_data["dates"])
    datetime.fromisoformat(dates.from_)
    datetime.fromisoformat(dates.to)
    if dates.from_ > dates.to:
        raise ValueError("Snapshot date range is reversed")

    items_data = document["items"]
    if not isinstance(items_data, list) or not items_data:
        raise ValueError("Snapshot items must be a non-empty list")
    model = FlightOption if kind == "flights" else HotelOption
    items: list[SnapshotOption] = []
    for raw_item in items_data:
        if not isinstance(raw_item, dict):
            raise TypeError("Snapshot item must be an object")
        if "source" in raw_item or "fetched_at" in raw_item:
            raise ValueError("Item metadata must be declared once at snapshot level")
        item = model.model_validate({**raw_item, "source": source, "fetched_at": fetched_at})
        if item.destination != destination:
            raise ValueError("Snapshot item destination does not match criteria")
        if isinstance(item, FlightOption) and item.dates != dates:
            raise ValueError("Flight dates do not match snapshot criteria")
        items.append(item)

    return Snapshot(
        kind=kind,
        source=source,
        fetched_at=fetched_at,
        criteria=SnapshotCriteria(
            destination=destination,
            aliases=tuple(aliases),
            dates=dates,
            travelers=travelers,
        ),
        items=tuple(items),
    )

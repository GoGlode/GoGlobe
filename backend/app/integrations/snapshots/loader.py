"""Load local provider snapshots without exposing their storage format upstream."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.resources import files
import json
from pathlib import Path
from typing import Literal

from app.contracts import validate
from app.integrations.ports import ToolResult, parse_timestamp, validate_travelers

SnapshotKind = Literal["hotels", "flights"]


class SnapshotValidationError(ValueError):
    """The snapshot exists, but cannot be trusted or used."""


@dataclass(frozen=True)
class Snapshot:
    source: str
    fetched_at: datetime
    context: dict
    result: ToolResult


def load_snapshots(
    kind: SnapshotKind, path: str | Path | None = None
) -> tuple[Snapshot, ...]:
    """Load and validate all compact files for one provider kind.

    ``path`` is primarily useful for validation tests and offline fixture updates.
    Missing files deliberately remain distinguishable from malformed snapshots.
    """
    if kind not in {"hotels", "flights"}:
        raise ValueError(f"Unsupported snapshot kind: {kind}")
    if path is not None:
        locations = [Path(path)]
    else:
        package = files(__package__)
        locations = sorted(
            (
                child for child in package.iterdir()
                if child.name == f"{kind}.json"
                or child.name.startswith(f"{kind}_") and child.name.endswith(".json")
            ),
            key=lambda child: child.name,
        )
    snapshots = tuple(_load_document(kind, location) for location in locations)
    contexts = [json.dumps(item.context, sort_keys=True) for item in snapshots]
    if len(contexts) != len(set(contexts)):
        raise SnapshotValidationError(f"Duplicate {kind} snapshot context")
    return snapshots


def load_snapshot(kind: SnapshotKind, path: str | Path | None = None) -> Snapshot:
    """Load one scenario or the primary scenario when no path is supplied."""
    return load_snapshots(kind, path)[0]


def _load_document(kind: SnapshotKind, location) -> Snapshot:
    try:
        document = json.loads(location.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SnapshotValidationError(f"Cannot read {kind} snapshot") from exc

    try:
        return _validate_snapshot(kind, document)
    except (KeyError, TypeError, ValueError) as exc:
        raise SnapshotValidationError(f"Invalid {kind} snapshot") from exc


def _validate_snapshot(kind: SnapshotKind, document: object) -> Snapshot:
    if not isinstance(document, dict) or set(document) != {
        "kind", "source", "fetched_at", "context", "result"
    }:
        raise ValueError("Unexpected snapshot fields")
    try:
        if document["kind"] != kind:
            raise ValueError("Snapshot kind does not match requested kind")
        if not isinstance(document["source"], str) or not document["source"].strip():
            raise ValueError("Snapshot source must be a non-empty string")
        if not isinstance(document["fetched_at"], str):
            raise ValueError("Snapshot fetched_at must be a string")
        fetched_at = parse_timestamp(document["fetched_at"])
        if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
            raise ValueError("Snapshot fetched_at must include a timezone")
        if fetched_at > datetime.now(timezone.utc):
            raise ValueError("Snapshot fetched_at cannot be in the future")

        context = document["context"]
        if not isinstance(context, dict):
            raise ValueError("Snapshot context must be an object")
        validate("Travelers", context["travelers"])
        validate_travelers(context["travelers"])
        if kind == "hotels":
            if set(context) != {"destination", "stay", "travelers"}:
                raise ValueError("Unexpected hotel snapshot context")
            validate("Params", {"destination": context["destination"]})
            validate("Stay", context["stay"])
        else:
            if set(context) != {"destination", "origin", "flight_dates", "travelers"}:
                raise ValueError("Unexpected flight snapshot context")
            validate("Params", {
                "destination": context["destination"],
                "origin": context["origin"],
            })
            validate("FlightDates", context["flight_dates"])

        raw_result = document["result"]
        if not isinstance(raw_result, dict) or set(raw_result) != {
            "status", "items", "sources", "warnings", "data_mode"
        }:
            raise ValueError("Unexpected snapshot result fields")
        result = ToolResult(**deepcopy(raw_result))
        result.validate_for(kind)
        if result.data_mode != "demo":
            raise ValueError("Local snapshots must use demo data mode")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid snapshot entry") from exc

    return Snapshot(
        source=document["source"].strip(),
        fetched_at=fetched_at,
        context=deepcopy(context),
        result=result,
    )

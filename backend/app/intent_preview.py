"""Safe deterministic fallback for the optional intent-preview endpoint.

The parser deliberately recognises only a small, documented vocabulary.  It
never persists or returns the original query and treats explicit v0.3 params as
more trustworthy than text inference.
"""
from __future__ import annotations

from copy import deepcopy
import re
import secrets
from typing import Any, Mapping


_DESTINATIONS = {
    "рим": "Рим",
    "rome": "Рим",
    "стамбул": "Стамбул",
    "istanbul": "Стамбул",
    "казань": "Казань",
    "kazan": "Казань",
    "москва": "Москва",
    "москвы": "Москва",
    "moscow": "Москва",
    "париж": "Париж",
    "paris": "Париж",
    "берлин": "Берлин",
    "berlin": "Берлин",
}

_WISH_PATTERNS = (
    ("near_sea", ("у моря", "рядом с морем", "near sea")),
    ("sea_view", ("вид на море", "sea view")),
    ("direct_flight", ("прямой рейс", "без пересадок", "direct flight")),
    ("breakfast", ("завтрак", "breakfast")),
)


def preview_intent(query: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a bounded fallback preview without retaining the raw query.

    ``ValueError`` is intentionally used for invalid input so an HTTP adapter
    can translate it into the endpoint's normal 422 response.
    """
    if not isinstance(query, str) or not 1 <= len(query) <= 2000 or not query.strip():
        raise ValueError("query must contain between 1 and 2000 characters")
    if params is None:
        params = {}
    if not isinstance(params, Mapping):
        raise ValueError("params must be an object")

    compact = " ".join(query.casefold().split())
    parsed = {
        "destination": _explicit_string(params, "destination") or _destination(compact),
        "duration_days": _explicit_duration(params) or _duration(compact),
        "dates": _copy_object(params, "dates"),
        "origin": _explicit_string(params, "origin") or _origin(compact),
        "travelers": _copy_object(params, "travelers"),
        "budget": _copy_object(params, "budget"),
        "wishes": _wishes(params, compact),
    }
    return {
        "preview_id": "ip_" + secrets.token_urlsafe(18),
        "parsed": parsed,
        "questions": _questions(parsed)[:3],
        "warnings": [],
        "analysis_mode": "fallback",
    }


def _explicit_string(params: Mapping[str, Any], field: str) -> str | None:
    value = params.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _explicit_duration(params: Mapping[str, Any]) -> int | None:
    value = params.get("duration_days")
    return value if type(value) is int and 1 <= value <= 30 else None


def _copy_object(params: Mapping[str, Any], field: str) -> dict[str, Any] | None:
    value = params.get(field)
    return deepcopy(dict(value)) if isinstance(value, Mapping) else None


def _destination(query: str) -> str | None:
    # Prefer a destination introduced by "в/во/to"; otherwise use the first
    # known city.  Keeping a closed vocabulary avoids treating arbitrary user
    # text or names as a destination.
    for alias, canonical in _DESTINATIONS.items():
        if re.search(rf"(?:^|\s)(?:в|во|to)\s+{re.escape(alias)}(?:\s|$|[,.!?])", query):
            return canonical
    for alias, canonical in _DESTINATIONS.items():
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", query):
            return canonical
    return None


def _duration(query: str) -> int | None:
    match = re.search(r"(?<!\d)([1-9]|[12]\d|30)\s*(?:дн(?:я|ей|ь)?|days?)(?!\w)", query)
    if match:
        return int(match.group(1))
    if "на выходные" in query or "weekend" in query:
        return 2
    return None


def _origin(query: str) -> str | None:
    for alias, canonical in _DESTINATIONS.items():
        if re.search(rf"(?:^|\s)(?:из|from)\s+{re.escape(alias)}(?:\s|$|[,.!?])", query):
            return canonical
    return None


def _wishes(params: Mapping[str, Any], query: str) -> list[str]:
    explicit = params.get("wishes")
    result = []
    if isinstance(explicit, list):
        result.extend(item for item in explicit if isinstance(item, str))
    for wish, phrases in _WISH_PATTERNS:
        if any(phrase in query for phrase in phrases):
            result.append(wish)
    # Preserve explicit order and cap output to the v0.3 Params boundary.
    return list(dict.fromkeys(result))[:4]


def _question(field: str, kind: str, title: str, *, required: bool) -> dict[str, Any]:
    return {
        "id": "q_" + field,
        "field": field,
        "kind": kind,
        "title": title,
        "required": required,
        "options": [],
    }


def _questions(parsed: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    if parsed["destination"] is None:
        result.append(_question("destination", "text", "Куда вы хотите поехать?", required=True))
    if parsed["duration_days"] is None:
        result.append(_question("duration_days", "number", "На сколько дней планируется поездка?", required=True))
    if parsed["travelers"] is None:
        result.append(_question("travelers", "travelers", "Кто едет?", required=False))
    if parsed["origin"] is None:
        result.append(_question("origin", "text", "Откуда вылетать?", required=False))
    if parsed["budget"] is None:
        result.append(_question("budget", "money", "Какой бюджет учитывать?", required=False))
    return result

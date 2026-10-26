"""Run: python -m pip install -r requirements.txt; python validate_contract_v0.3.py.
Validates the contract and fixtures, not a deployed backend.
"""

from pathlib import Path
import json
import re
import sys
from copy import deepcopy
from datetime import datetime, date, timedelta

HERE = Path(__file__).resolve().parent
local_deps = HERE.parents[1] / ".build/api_validation_deps"
if local_deps.exists():
    sys.path.insert(0, str(local_deps))
from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402
from jsonschema.exceptions import ValidationError  # noqa: E402
from openapi_spec_validator import validate  # noqa: E402

API = json.loads((HERE / "GoGlobe_openapi_v0.3.json").read_text(encoding="utf-8"))
EX = json.loads((HERE / "GoGlobe_examples_v0.3.json").read_text(encoding="utf-8"))
validate(API)


def valid(schema, value):
    Draft202012Validator(
        {"components": API["components"], "$ref": "#/components/schemas/" + schema},
        format_checker=FormatChecker(),
    ).validate(value)


def walk(value):
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)


def result(kind, requested, components):
    states = [components[k]["state"] for k in requested]
    if any(x in ["queued", "processing"] for x in states):
        return None
    if kind == "plan":
        if components["itinerary"]["state"] in ["not_requested", "blocked"]:
            return None
        if components["itinerary"]["state"] != "ready":
            return ("failed", None)
        return (
            "completed",
            "partial"
            if any(
                components[k]["state"] in ["blocked", "failed", "not_requested"]
                or components[k]["incomplete"]
                for k in requested
            )
            else "ok",
        )
    ready = any(x == "ready" for x in states)
    failed = any(x in ["failed", "blocked", "not_requested"] for x in states)
    if failed and not ready:
        return ("failed", None)
    if failed or any(components[k]["incomplete"] for k in requested):
        return ("completed", "partial")
    return ("completed", "ok" if ready else "empty")


def semantic(schema, value):
    for x in walk(value):
        if "missing_fields" in x:
            assert bool(x["missing_fields"]) == (x["state"] == "blocked")
            assert (x["error"] is not None) == (x["state"] == "failed")
            assert not x["incomplete"] or x["state"] == "ready"
        if "coverage" in x:
            assert not set(x["coverage"]) & set(x["exclusions"])
            if x["status"] == "unknown":
                assert x["money"] is None
            else:
                assert x["money"] is not None and x["source_ids"]
        if "adults" in x:
            assert x["adults"] + len(x["children_ages"]) <= 9
        if "departure_at" in x:
            delta = datetime.fromisoformat(x["arrival_at"]) - datetime.fromisoformat(
                x["departure_at"]
            )
            assert (
                delta.total_seconds() > 0
                and delta.total_seconds() / 60 == x["duration_minutes"]
            )
        if "check_in" in x:
            assert date.fromisoformat(x["check_out"]) > date.fromisoformat(
                x["check_in"]
            )
        if "outbound_date" in x:
            assert x["return_date"] >= x["outbound_date"]
        if "start_date" in x and x["start_date"] is not None:
            assert x["end_date"] >= x["start_date"]
    if schema == "Snapshot":
        assert (value["error"] is not None) == (value["state"] == "failed")
        assert (value["clarification"] is not None) == (
            value["state"] == "needs_clarification"
        )
        assert (value["result_status"] is not None) == (value["state"] == "completed")
        if value["state"] == "completed":
            assert result(
                value["kind"], value["requested_components"], value["components"]
            ) == ("completed", value["result_status"])
        assert all(
            value["components"][k]["state"] == "not_requested"
            for k in value["components"]
            if k not in value["requested_components"]
        )
    if schema == "Trip" and value["itinerary"] is not None:
        days = value["itinerary"]["days"]
        assert len(days) == value["duration_days"]
        assert [d["day_index"] for d in days] == list(range(1, len(days) + 1))
        start = value["schedule"]["start_date"]
        if start:
            assert (
                date.fromisoformat(value["schedule"]["end_date"])
                - date.fromisoformat(start)
            ).days + 1 == len(days)
            assert [d["date"] for d in days] == [
                (date.fromisoformat(start) + timedelta(days=i)).isoformat()
                for i in range(len(days))
            ]
        else:
            assert all(d["date"] is None for d in days)
    if schema in ["HotelList", "FlightList"]:
        sources = {s["source_id"] for s in value["sources"]}
        for x in walk(value["items"]):
            if "source_ids" in x:
                assert set(x["source_ids"]) <= sources
        if value["incomplete"]:
            assert value["warnings"]
        if schema == "HotelList" and value["context"]:
            for item in value["items"]:
                assert (
                    item["check_in"] == value["context"]["stay"]["check_in"]
                    and item["check_out"] == value["context"]["stay"]["check_out"]
                )
    if schema == "TripList":
        sources = {s["source_id"] for s in value["sources"]}
        for item in value["items"]:
            assert set(item["price_summary"]["source_ids"]) <= sources
    if schema in ["Trip", "TripFlags", "TripCard"]:
        assert (value["expires_at"] is None) == bool(
            value["saved_at"] or value["favorite_at"]
        )


for name, e in EX.items():
    try:
        valid(e["schema"], e["value"])
        semantic(e["schema"], e["value"])
    except Exception as exc:
        raise AssertionError("Fixture failed: " + name) from exc
inline = 0
for path, methods in API["paths"].items():
    for method, op in methods.items():
        assert {p["name"] for p in op["parameters"] if p["in"] == "path"} == set(
            re.findall(r"\{([^}]+)\}", path)
        )
        for response in op["responses"].values():
            for media, body in response.get("content", {}).items():
                if "example" not in body:
                    continue
                if media == "application/json":
                    valid(body["schema"]["$ref"].split("/")[-1], body["example"])
                elif media == "text/event-stream":
                    valid(
                        "Snapshot",
                        json.loads(body["example"].split("\ndata: ", 1)[1].strip()),
                    )
                inline += 1

negative = []


def bad(name, schema, value):
    negative.append((name, schema, value))


x = deepcopy(EX["plan_request"]["value"])
x["params"]["budget"] = {"amount_minor": 0, "currency": "RUB"}
bad("zero budget", "PlanRequest", x)
bad("too many travelers", "Travelers", {"adults": 9, "children_ages": [2]})
x = deepcopy(EX["completed_partial"]["value"])
x["result_status"] = None
bad("missing terminal result", "Snapshot", x)
x = deepcopy(EX["completed_partial"]["value"])
x["trip_id"] = None
bad("mutated historical trip link", "Snapshot", x)
x = deepcopy(EX["trip_relative"]["value"]["price_summary"])
x["money"] = {"amount_minor": 1, "currency": "RUB"}
bad("unknown price with money", "Price", x)
x = deepcopy(EX["hotel_empty"]["value"])
x["items"] = [EX["hotel_offers"]["value"]["items"][0]]
bad("empty with offers", "HotelList", x)
x = deepcopy(EX["quote_request"]["value"])
x["components"] = ["hotels", "hotels"]
bad("duplicate components", "QuoteRequest", x)
x = deepcopy(EX["quote_request"]["value"])
del x["stay"]
bad("missing stay", "QuoteRequest", x)
x = deepcopy(EX["quote_request"]["value"])
del x["flight_dates"]
bad("missing flight dates", "QuoteRequest", x)
x = deepcopy(EX["trip_relative"]["value"]["schedule"])
x["end_date"] = "2026-11-11"
bad("half schedule", "Schedule", x)
x = deepcopy(EX["calendar"]["value"]["items"][0])
x["start_date"] = None
bad("half calendar dates", "TripCard", x)
bad(
    "half coordinate",
    "Place",
    dict(
        place_id="p1",
        name="Test",
        latitude=None,
        longitude=1,
        timezone=None,
        verification="unknown",
        source_ids=[],
    ),
)
x = deepcopy(EX["accepted"]["value"])
x["state"] = "completed"
bad("terminal Accepted", "Accepted", x)
x = deepcopy(EX["hotel_offers"]["value"])
x["context"] = None
bad("offer without query context", "HotelList", x)
x = deepcopy(EX["hotel_failed"]["value"])
x["incomplete"] = True
bad("failed marked useful incomplete", "HotelList", x)
for name, schema, value in negative:
    try:
        valid(schema, value)
    except ValidationError:
        pass
    else:
        raise AssertionError("Invalid payload accepted: " + name)

# Regressions that a structural schema alone cannot establish.
assert (
    EX["answer_accepted"]["value"]["revision"]
    > EX["answer"]["value"]["expected_revision"]
)
assert (
    EX["answer_accepted"]["value"]["search_id"]
    == EX["state_needs_clarification"]["value"]["search_id"]
)
assert EX["restored_session"]["value"]["recovery_enabled"] is True
assert all(
    EX["trip_scheduled"]["value"]["components"][k]["state"] == "not_requested"
    for k in ["hotels", "flights"]
)


def c(state, incomplete=False):
    return {"state": state, "incomplete": incomplete}


cases = [
    (
        "quotes",
        ["hotels", "flights"],
        {"hotels": c("empty"), "flights": c("failed")},
        ("failed", None),
    ),
    (
        "quotes",
        ["hotels", "flights"],
        {"hotels": c("ready"), "flights": c("failed")},
        ("completed", "partial"),
    ),
    (
        "quotes",
        ["hotels", "flights"],
        {"hotels": c("empty"), "flights": c("empty")},
        ("completed", "empty"),
    ),
    ("quotes", ["hotels"], {"hotels": c("ready", True)}, ("completed", "partial")),
    ("quotes", ["hotels"], {"hotels": c("ready")}, ("completed", "ok")),
    ("quotes", ["hotels"], {"hotels": c("processing")}, None),
    (
        "plan",
        ["itinerary", "hotels", "flights"],
        {"itinerary": c("ready"), "hotels": c("blocked"), "flights": c("blocked")},
        ("completed", "partial"),
    ),
    ("plan", ["itinerary"], {"itinerary": c("blocked")}, None),
]
for kind, requested, components, expected in cases:
    assert result(kind, requested, components) == expected

print(
    json.dumps(
        {
            "openapi": "valid",
            "operations": sum(len(x) for x in API["paths"].values()),
            "schemas": len(API["components"]["schemas"]),
            "fixtures": len(EX),
            "inline_examples": inline,
            "invalid_payloads_rejected": len(negative),
            "result_rule_scenarios": len(cases),
            "cross_response_regressions": 4,
            "scope": "documents and examples only",
        },
        ensure_ascii=False,
    )
)

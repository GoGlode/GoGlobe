from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import hashlib

import pytest

from app.contracts import examples, validate
from app.integrations.ports import FlightCriteria, HotelCriteria, ToolResult


@pytest.mark.parametrize("name", list(examples()))
def test_contract_fixture(name):
    example = examples()[name]
    validate(example["schema"], example["value"])


def test_criteria_and_tool_result():
    deadline = datetime.now(timezone.utc) + timedelta(seconds=30)
    travelers = {"adults": 2, "children_ages": []}
    HotelCriteria("Рим", {"check_in": "2026-11-10", "check_out": "2026-11-12"}, travelers, None, [], deadline)
    FlightCriteria("Рим", "Москва", {"outbound_date": "2026-11-10", "return_date": "2026-11-12"}, travelers, None, [], deadline)
    for kind, fixture in [("hotels", "hotel_offers"), ("flights", "flight_offers")]:
        data = deepcopy(examples()[fixture]["value"])
        ToolResult("ok", data["items"], data["sources"], data["warnings"], "demo").validate_for(kind)
        with pytest.raises(ValueError, match="source_id"):
            ToolResult("ok", data["items"], [], [], "demo").validate_for(kind)


def test_criteria_rejects_dates_and_deadline():
    args = ("Рим", {"check_in": "2026-11-12", "check_out": "2026-11-10"}, {"adults": 1, "children_ages": []}, None, [])
    with pytest.raises(ValueError, match="check_out"):
        HotelCriteria(*args, datetime.now(timezone.utc) + timedelta(seconds=30))
    with pytest.raises(TimeoutError):
        HotelCriteria("Рим", {"check_in": "2026-11-10", "check_out": "2026-11-12"}, args[2], None, [], datetime.now(timezone.utc) - timedelta(seconds=1))


def test_contract_copy_matches_source():
    manifest = json.loads((Path(__file__).parents[2] / "docs/api/v0.3/manifest.json").read_text(encoding="utf-8"))
    for name in ("openapi_v0.3.json", "examples_v0.3.json"):
        assert hashlib.sha256(Path("app/contracts", name).read_bytes()).hexdigest() == manifest["sha256"][name]

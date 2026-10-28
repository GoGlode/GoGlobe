import asyncio
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.integrations.ports import FlightCriteria, HotelCriteria
from app.integrations.service import DemoFlightProvider, DemoHotelProvider
from app.integrations.snapshots import (
    SnapshotValidationError,
    load_snapshot,
    load_snapshots,
)


SCENARIOS = [
    (
        "Рим",
        {"check_in": "2026-11-10", "check_out": "2026-11-11"},
        {"outbound_date": "2026-11-10", "return_date": "2026-11-11"},
        {"adults": 2, "children_ages": []},
        "h_demo_1",
        "f_demo_1",
    ),
    (
        "Стамбул",
        {"check_in": "2026-12-03", "check_out": "2026-12-07"},
        {"outbound_date": "2026-12-03", "return_date": "2026-12-07"},
        {"adults": 2, "children_ages": [8]},
        "h_demo_istanbul",
        "f_demo_istanbul",
    ),
    (
        "Казань",
        {"check_in": "2027-01-04", "check_out": "2027-01-07"},
        {"outbound_date": "2027-01-04", "return_date": "2027-01-07"},
        {"adults": 1, "children_ages": []},
        "h_demo_kazan",
        "f_demo_kazan",
    ),
]


@pytest.mark.parametrize("kind", ["hotels", "flights"])
def test_load_valid_snapshot(kind):
    snapshot = load_snapshot(kind)

    assert snapshot.source.startswith("goglobe-demo/")
    assert snapshot.fetched_at.tzinfo is not None
    assert snapshot.result.status == "ok"
    assert snapshot.result.data_mode == "demo"
    assert len(snapshot.result.items) == 1


@pytest.mark.parametrize("kind", ["hotels", "flights"])
def test_loads_three_small_scenarios(kind):
    snapshots = load_snapshots(kind)

    assert len(snapshots) == 3
    assert len({snapshot.source for snapshot in snapshots}) == 3
    assert all(snapshot.fetched_at.tzinfo is not None for snapshot in snapshots)


@pytest.mark.parametrize(
    "destination,stay,flight_dates,travelers,hotel_id,flight_id",
    SCENARIOS,
)
def test_providers_select_scenario(
    destination, stay, flight_dates, travelers, hotel_id, flight_id
):
    async def run():
        deadline = datetime.now(timezone.utc) + timedelta(seconds=5)
        hotel = await DemoHotelProvider().search(HotelCriteria(
            destination, stay, travelers, None, [], deadline,
        ))
        flight = await DemoFlightProvider().search(FlightCriteria(
            destination, "Москва", flight_dates, travelers, None, [], deadline,
        ))

        assert hotel.items[0]["offer_id"] == hotel_id
        assert flight.items[0]["offer_id"] == flight_id

    asyncio.run(run())


def test_providers_do_not_substitute_another_scenario():
    async def run():
        deadline = datetime.now(timezone.utc) + timedelta(seconds=5)
        mismatches = [
            ("Неаполь", SCENARIOS[0][1], SCENARIOS[0][2], SCENARIOS[0][3]),
            ("Рим", SCENARIOS[1][1], SCENARIOS[1][2], SCENARIOS[0][3]),
            ("Рим", SCENARIOS[0][1], SCENARIOS[0][2], SCENARIOS[2][3]),
        ]
        for destination, stay, flight_dates, travelers in mismatches:
            hotel = await DemoHotelProvider().search(HotelCriteria(
                destination, stay, travelers, None, [], deadline,
            ))
            flight = await DemoFlightProvider().search(FlightCriteria(
                destination, "Москва", flight_dates, travelers, None, [], deadline,
            ))
            assert hotel.items == []
            assert flight.items == []

        wrong_origin = await DemoFlightProvider().search(FlightCriteria(
            "Рим", "Санкт-Петербург", SCENARIOS[0][2], SCENARIOS[0][3],
            None, [], deadline,
        ))
        assert wrong_origin.items == []

    asyncio.run(run())


def test_load_missing_snapshot(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_snapshot("hotels", tmp_path / "missing.json")


@pytest.mark.parametrize(
    "contents",
    [
        "{not-json",
        json.dumps({
            "kind": "hotels",
            "source": "",
            "fetched_at": "not-a-timestamp",
            "context": {},
            "result": {},
        }),
    ],
)
def test_load_corrupt_snapshot(tmp_path, contents):
    path = tmp_path / "broken.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(SnapshotValidationError, match="hotels snapshot"):
        load_snapshot("hotels", path)

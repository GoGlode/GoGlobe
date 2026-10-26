"""Scenario selection coverage for snapshot-backed providers."""

import asyncio
from typing import Any, Coroutine

import pytest

from app.integrations.snapshots import SnapshotFlightProvider, SnapshotHotelProvider
from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange

SCENARIOS = [
    ("Анталья", "2026-11-10", "2026-11-15", 2, "antalya"),
    ("стамбул", "2026-11-17", "2026-11-21", 2, "istanbul"),
    ("Казань, Россия", "2026-11-07", "2026-11-10", 1, "kazan"),
]


def _dates(start: str, end: str) -> DateRange:
    return DateRange.model_validate({"from": start, "to": end})


def _run(coroutine: Coroutine[Any, Any, list]) -> list:
    return asyncio.run(coroutine)


@pytest.mark.parametrize(
    ("destination", "start", "end", "travelers", "marker"), SCENARIOS
)
def test_selects_supported_scenario(
    destination: str, start: str, end: str, travelers: int, marker: str
):
    dates = _dates(start, end)

    flights = _run(SnapshotFlightProvider().search(destination, dates, travelers))
    hotels = _run(SnapshotHotelProvider().search(destination, dates, travelers))

    assert flights and hotels
    assert isinstance(flights[0], FlightOption)
    assert isinstance(hotels[0], HotelOption)
    assert marker in flights[0].id
    assert marker in hotels[0].id
    assert flights[0].source == hotels[0].source


def test_unknown_destination_returns_empty_results():
    dates = _dates("2026-11-10", "2026-11-15")

    flights = _run(SnapshotFlightProvider().search("Париж", dates, 2))
    hotels = _run(SnapshotHotelProvider().search("Париж", dates, 2))

    assert flights == []
    assert hotels == []


def test_mismatched_dates_return_empty_results():
    dates = _dates("2026-11-11", "2026-11-15")

    flights = _run(SnapshotFlightProvider().search("Анталья", dates, 2))
    hotels = _run(SnapshotHotelProvider().search("Анталья", dates, 2))

    assert flights == []
    assert hotels == []


def test_mismatched_traveler_count_returns_empty_results():
    dates = _dates("2026-11-10", "2026-11-15")

    flights = _run(SnapshotFlightProvider().search("Анталья", dates, 3))
    hotels = _run(SnapshotHotelProvider().search("Анталья", dates, 3))

    assert flights == []
    assert hotels == []


def test_each_search_returns_independent_model_copies():
    dates = _dates("2026-11-10", "2026-11-15")
    flights = SnapshotFlightProvider()
    hotels = SnapshotHotelProvider()

    first_flights = _run(flights.search("Анталья", dates, 2))
    first_hotels = _run(hotels.search("Анталья", dates, 2))
    first_flights[0].price.amount = 0
    first_hotels[0].photos.append("https://example.com/mutated.jpg")

    second_flights = _run(flights.search("Анталья", dates, 2))
    second_hotels = _run(hotels.search("Анталья", dates, 2))

    assert second_flights[0].price.amount == 36000
    assert "https://example.com/mutated.jpg" not in second_hotels[0].photos

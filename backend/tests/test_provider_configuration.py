import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.integrations.ports import FlightCriteria, HotelCriteria, walk
from app.integrations.service import (
    DemoFlightProvider,
    DemoHotelProvider,
    UnconfiguredLiveProvider,
)
from app.integrations.snapshots import load_snapshot
from app.planning import PlanningService


def hotel_criteria():
    return HotelCriteria(
        "Рим",
        {"check_in": "2026-11-10", "check_out": "2026-11-11"},
        {"adults": 2, "children_ages": []},
        None,
        [],
        datetime.now(timezone.utc) + timedelta(seconds=5),
    )


def flight_criteria():
    return FlightCriteria(
        "Рим",
        "Москва",
        {"outbound_date": "2026-11-10", "return_date": "2026-11-11"},
        {"adults": 2, "children_ages": []},
        None,
        [],
        datetime.now(timezone.utc) + timedelta(seconds=5),
    )


def test_snapshot_mode_selects_snapshot_offer_providers(monkeypatch):
    monkeypatch.setenv("GOGLOBE_PROVIDERS", "snapshot")
    tools = PlanningService().tools

    assert isinstance(tools.hotel_provider, DemoHotelProvider)
    assert isinstance(tools.flight_provider, DemoFlightProvider)

    async def run():
        hotel, flight = await asyncio.gather(
            tools.hotels(hotel_criteria()),
            tools.flights(flight_criteria()),
        )
        assert hotel.status == flight.status == "ok"
        assert hotel.data_mode == flight.data_mode == "demo"

    asyncio.run(run())


def test_live_mode_without_configuration_returns_controlled_errors(monkeypatch):
    def snapshots_must_not_be_loaded(kind):
        raise AssertionError(f"unexpected snapshot load: {kind}")

    monkeypatch.setattr(
        "app.integrations.service.load_snapshots", snapshots_must_not_be_loaded
    )
    monkeypatch.setenv("GOGLOBE_PROVIDERS", "live")
    monkeypatch.setenv("GOGLOBE_DEMO_FALLBACK", "true")
    tools = PlanningService().tools

    assert isinstance(tools.hotel_provider, UnconfiguredLiveProvider)
    assert isinstance(tools.flight_provider, UnconfiguredLiveProvider)

    async def run():
        results = await asyncio.gather(
            tools.hotels(hotel_criteria()),
            tools.flights(flight_criteria()),
        )
        for result in results:
            assert result.status == "unavailable"
            assert result.data_mode == "live"
            assert [warning["code"] for warning in result.warnings] == [
                "PROVIDER_INVALID_CONFIGURATION"
            ]

    asyncio.run(run())


def test_snapshot_fetched_at_drives_result_freshness(monkeypatch):
    snapshots = {
        kind: replace(
            load_snapshot(kind),
            fetched_at=load_snapshot(kind).fetched_at + timedelta(hours=1),
        )
        for kind in ("hotels", "flights")
    }
    monkeypatch.setattr(
        "app.integrations.service.load_snapshots", lambda kind: [snapshots[kind]]
    )

    async def run():
        for kind, provider, criteria in (
            ("hotels", DemoHotelProvider(), hotel_criteria()),
            ("flights", DemoFlightProvider(), flight_criteria()),
        ):
            fetched_at = snapshots[kind].fetched_at
            result = await provider.search(criteria)
            checked_at_values = {
                datetime.fromisoformat(source["checked_at"].replace("Z", "+00:00"))
                for source in result.sources
            }
            checked_at_values.update(
                datetime.fromisoformat(node["checked_at"].replace("Z", "+00:00"))
                for node in walk(result.items)
                if "checked_at" in node
            )
            assert checked_at_values == {fetched_at}

    asyncio.run(run())

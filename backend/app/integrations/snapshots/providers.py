"""Provider implementations backed only by validated local snapshots."""

from __future__ import annotations

import re

from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange

from .loader import Snapshot, load_snapshots


def _normalize_destination(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


def _matches(snapshot: Snapshot, destination: str, dates: DateRange, travelers: int) -> bool:
    requested = _normalize_destination(destination)
    destinations = {
        _normalize_destination(snapshot.criteria.destination),
        *(_normalize_destination(alias) for alias in snapshot.criteria.aliases),
    }
    return (
        requested in destinations
        and dates == snapshot.criteria.dates
        and travelers == snapshot.criteria.travelers
    )


class SnapshotFlightProvider:
    def __init__(self, snapshots: tuple[Snapshot, ...] | None = None) -> None:
        self._snapshots = snapshots if snapshots is not None else load_snapshots("flights")
        if any(snapshot.kind != "flights" for snapshot in self._snapshots):
            raise ValueError("SnapshotFlightProvider accepts only flight snapshots")

    async def search(
        self, destination: str, dates: DateRange, travelers: int
    ) -> list[FlightOption]:
        for snapshot in self._snapshots:
            if _matches(snapshot, destination, dates, travelers):
                return [
                    item.model_copy(deep=True)
                    for item in snapshot.items
                    if isinstance(item, FlightOption)
                ]
        return []


class SnapshotHotelProvider:
    def __init__(self, snapshots: tuple[Snapshot, ...] | None = None) -> None:
        self._snapshots = snapshots if snapshots is not None else load_snapshots("hotels")
        if any(snapshot.kind != "hotels" for snapshot in self._snapshots):
            raise ValueError("SnapshotHotelProvider accepts only hotel snapshots")

    async def search(
        self, destination: str, dates: DateRange, travelers: int
    ) -> list[HotelOption]:
        for snapshot in self._snapshots:
            if _matches(snapshot, destination, dates, travelers):
                return [
                    item.model_copy(deep=True)
                    for item in snapshot.items
                    if isinstance(item, HotelOption)
                ]
        return []

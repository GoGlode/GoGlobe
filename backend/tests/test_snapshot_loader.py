"""Validation coverage for local provider snapshot loading."""

import json
from pathlib import Path
from shutil import copyfile

import pytest

from app.integrations.snapshots.loader import (
    SnapshotNotFoundError,
    SnapshotValidationError,
    load_snapshot,
    load_snapshots,
)
from app.schemas.providers import FlightOption, HotelOption

SNAPSHOT_DIR = Path(__file__).parents[1] / "app" / "integrations" / "snapshots"


def test_loads_all_snapshot_files():
    flights = load_snapshots("flights")
    hotels = load_snapshots("hotels")

    assert len(flights) == len(hotels) == 3
    assert len({snapshot.source for snapshot in flights + hotels}) == 3


@pytest.mark.parametrize(
    ("kind", "model"), [("flights", FlightOption), ("hotels", HotelOption)]
)
def test_validates_metadata_criteria_and_models(kind, model):
    snapshots = load_snapshots(kind)

    for snapshot in snapshots:
        assert snapshot.source.startswith("goglobe-snapshot/")
        assert snapshot.fetched_at.endswith("+03:00")
        assert snapshot.criteria.destination
        assert snapshot.criteria.aliases
        assert snapshot.criteria.dates.from_ <= snapshot.criteria.dates.to
        assert snapshot.criteria.travelers > 0
        assert all(isinstance(item, model) for item in snapshot.items)
        assert all(item.source == snapshot.source for item in snapshot.items)
        assert all(item.fetched_at == snapshot.fetched_at for item in snapshot.items)


def test_missing_snapshot_is_reported(tmp_path: Path):
    with pytest.raises(SnapshotNotFoundError, match="not found"):
        load_snapshot("flights", tmp_path / "missing.json")


def test_damaged_json_is_rejected(tmp_path: Path):
    path = tmp_path / "flights_damaged.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(SnapshotValidationError, match="Cannot read flights snapshot"):
        load_snapshot("flights", path)


@pytest.mark.parametrize(
    "document",
    [
        [],
        {"kind": "flights"},
        {
            "kind": "flights",
            "source": "",
            "fetched_at": "not-a-date",
            "criteria": {},
            "items": [],
        },
    ],
)
def test_invalid_structure_is_rejected(tmp_path: Path, document):
    path = tmp_path / "flights_invalid.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(SnapshotValidationError, match="Invalid flights snapshot"):
        load_snapshot("flights", path)


def test_duplicate_criteria_are_rejected(tmp_path: Path):
    source = SNAPSHOT_DIR / "flights_antalya.json"
    copyfile(source, tmp_path / "flights_first.json")
    copyfile(source, tmp_path / "flights_second.json")

    with pytest.raises(SnapshotValidationError, match="Duplicate flights snapshot criteria"):
        load_snapshots("flights", tmp_path)

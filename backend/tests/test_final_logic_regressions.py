import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.bff import create_app
from app.contracts import examples
from app.integrations.ports import FlightCriteria, HotelCriteria, ToolResult
from app.integrations.resilience import ResilientIntegrationTools
from app.integrations.service import IntegrationTools
from app.planning import AgentPlan


ORIGIN = "http://127.0.0.1:8000"


def hotel_criteria(*, budget=None, wishes=None):
    context = examples()["hotel_offers"]["value"]["context"]
    return HotelCriteria(
        "Рим",
        deepcopy(context["stay"]),
        deepcopy(context["travelers"]),
        budget,
        list(wishes or []),
        datetime.now(timezone.utc) + timedelta(seconds=2),
    )


def flight_criteria(*, budget=None, wishes=None):
    context = examples()["flight_offers"]["value"]["context"]
    return FlightCriteria(
        "Рим",
        context["origin"],
        deepcopy(context["flight_dates"]),
        deepcopy(context["travelers"]),
        budget,
        list(wishes or []),
        datetime.now(timezone.utc) + timedelta(seconds=2),
    )


def test_bff_rejects_duplicate_json_keys(tmp_path):
    headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
    with TestClient(create_app(str(tmp_path / "duplicate-json.sqlite3")), headers=headers) as client:
        assert client.post("/api/v1/session", content="{}").status_code == 200
        response = client.post(
            "/api/v1/searches",
            content=(
                '{"query":"Rome for two days","query":"silently replaced",'
                '"params":{"destination":"Rome","duration_days":2}}'
            ),
            headers={"Idempotency-Key": str(uuid4())},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_JSON"


def test_invalid_provider_mode_is_rejected_instead_of_laundered_to_live():
    class Provider:
        data_mode = "staging"

        async def search(self, criteria):
            return ToolResult("ok", [], [], [], "live")

    async def run():
        for tools in (
            IntegrationTools(hotels=Provider()),
            ResilientIntegrationTools(hotels=Provider()),
        ):
            result = await tools.hotels(hotel_criteria())
            assert result.status == "unavailable"
            assert result.data_mode == "live"
            result.validate_for("hotels")
            assert {warning["code"] for warning in result.warnings} == {
                "PROVIDER_INVALID_CONFIGURATION"
            }

    asyncio.run(run())


def test_demo_travel_providers_do_not_claim_unsupported_budget_or_wishes():
    async def run():
        tools = IntegrationTools()
        for call, criteria in (
            (tools.hotels, hotel_criteria(
                budget={"amount_minor": 100_000, "currency": "RUB"},
            )),
            (tools.hotels, hotel_criteria(wishes=["sea_view"])),
            (tools.flights, flight_criteria(
                budget={"amount_minor": 100_000, "currency": "RUB"},
            )),
            (tools.flights, flight_criteria(wishes=["direct_flight"])),
        ):
            result = await call(criteria)
            assert result.status == "ok"
            assert result.data_mode == "demo"
            assert result.items == []

    asyncio.run(run())


def test_snapshot_does_not_duplicate_demo_warning(tmp_path):
    class Agent:
        async def plan(self, context):
            trip = examples()["trip_relative"]["value"]
            return AgentPlan(
                deepcopy(trip["destination"]),
                trip["duration_days"],
                deepcopy(trip["itinerary"]),
                warnings=[{
                    "code": "DEMO_DATA",
                    "message": "Демонстрационные данные.",
                    "trip_id": None,
                }],
                data_mode="demo",
            )

    headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
    with TestClient(
        create_app(str(tmp_path / "demo-warning.sqlite3"), agent=Agent()),
        headers=headers,
    ) as client:
        client.post("/api/v1/session", json={})
        accepted = client.post(
            "/api/v1/searches",
            json={
                "query": "Rome for two days",
                "params": {"destination": "Rome", "duration_days": 2},
            },
            headers={"Idempotency-Key": str(uuid4())},
        ).json()
        snapshot = client.get(f"/api/v1/searches/{accepted['search_id']}").json()
    assert [warning["code"] for warning in snapshot["warnings"]].count("DEMO_DATA") == 1

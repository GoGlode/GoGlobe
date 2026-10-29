"""Regressions found by an independent audit of task 3."""
import asyncio
from copy import deepcopy

import pytest

from app.contracts import examples
from app.integrations.ports import ToolResult
from app.integrations.service import IntegrationTools
from tests.test_adapters import criteria


def test_round_trip_must_return_from_outbound_destination():
    data = deepcopy(examples()["flight_offers"]["value"])
    data["items"][0]["inbound_segments"][0]["origin"] = {
        "code": "PAR",
        "timezone": "Europe/Paris",
    }

    with pytest.raises(ValueError, match="route|Route"):
        ToolResult("ok", data["items"], data["sources"], [], "demo").validate_for("flights")


@pytest.mark.parametrize("location", ["offer", "price"])
def test_source_references_must_not_repeat(location):
    data = deepcopy(examples()["hotel_offers"]["value"])
    target = data["items"][0] if location == "offer" else data["items"][0]["total_price"]
    target["source_ids"] = ["src_demo_1", "src_demo_1"]

    with pytest.raises(ValueError, match="Duplicate source reference"):
        ToolResult("ok", data["items"], data["sources"], [], "demo").validate_for("hotels")


@pytest.mark.parametrize("url", [
    "https://user:private-secret@provider.test/result",
    "https://provider.test/result?api_key=private-secret",
    123,
])
def test_private_source_url_is_removed_without_losing_offers(url):
    data = deepcopy(examples()["hotel_offers"]["value"])
    data["sources"][0]["url"] = url

    class Provider:
        data_mode = "demo"

        async def search(self, value):
            return ToolResult("ok", data["items"], data["sources"], [], "demo")

    async def run():
        result = await IntegrationTools(hotels=Provider()).hotels(criteria("hotels"))
        assert result.status == "ok"
        assert result.items
        assert result.sources[0]["url"] is None
        assert "SOURCE_URL_NOT_ALLOWED" in {warning["code"] for warning in result.warnings}
        assert "private-secret" not in repr(result)

    asyncio.run(run())

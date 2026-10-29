from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.bff import create_app
from app.contracts import examples
from app.integrations.ports import ToolResult


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "audit.sqlite3")),
                    headers={"Origin": "http://localhost:8000"}, raise_server_exceptions=False) as client:
        assert client.post("/api/v1/session", json={}).status_code == 200
        yield client


@pytest.mark.parametrize("value", ["1.0", "1e0", "1e999", "true", "null", "[]", "{}"])
def test_invalid_limit_never_crashes(client, value):
    response = client.get("/api/v1/trips", params={"limit": value})
    assert response.status_code == 422, response.text


def test_deep_request_never_crashes(client):
    content = '{"query":' + '[' * 1100 + '0' + ']' * 1100 + '}'
    response = client.post("/api/v1/searches", content=content,
                           headers={"Content-Type": "application/json", "Idempotency-Key": str(uuid4())})
    assert response.status_code == 422, response.text


def test_tool_checks_nested_price_sources():
    data = deepcopy(examples()["hotel_offers"]["value"])
    data["items"][0]["nightly_price"]["source_ids"] = ["unknown"]
    with pytest.raises(ValueError, match="source"):
        ToolResult("ok", data["items"], data["sources"], [], "demo").validate_for("hotels")


def test_tool_rejects_unknown_kind():
    with pytest.raises(ValueError):
        ToolResult("ok", [], [], [], "demo").validate_for("misspelled")


def test_tool_rejects_overlapping_price_coverage():
    data = deepcopy(examples()["hotel_offers"]["value"])
    data["items"][0]["total_price"]["exclusions"].append("hotels")
    with pytest.raises(ValueError):
        ToolResult("ok", data["items"], data["sources"], [], "demo").validate_for("hotels")

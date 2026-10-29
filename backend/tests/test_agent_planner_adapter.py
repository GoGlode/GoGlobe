import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.agent.planner_adapter import AgentPlanner
from app.integrations.service import IntegrationTools
from app.planning import NeedsClarification, PlanContext


def context(query, params=None):
    return PlanContext(
        query=query,
        params=params or {},
        deadline_at=datetime.now(UTC) + timedelta(seconds=2),
        tools=IntegrationTools(),
    )


def test_agent_planner_builds_two_relative_days():
    result = asyncio.run(AgentPlanner().plan(context("Рим на 2 дня")))

    assert result.destination["name"] == "Рим"
    assert result.duration_days == 2
    assert [day["day_index"] for day in result.itinerary["days"]] == [1, 2]
    result.validate({})


def test_agent_planner_requests_missing_duration():
    with pytest.raises(NeedsClarification, match="На сколько дней"):
        asyncio.run(AgentPlanner().plan(context("Хочу в Рим")))


def test_agent_planner_prefers_explicit_params_to_query():
    result = asyncio.run(AgentPlanner().plan(context(
        "Хочу в Стамбул на 2 дня",
        {"destination": "Рим", "duration_days": 3},
    )))

    assert result.destination["name"] == "Рим"
    assert result.duration_days == 3


def test_agent_planner_supports_istanbul_and_kazan():
    for city in ("Стамбул", "Казань"):
        result = asyncio.run(AgentPlanner().plan(context(f"{city} на 2 дня")))
        assert result.destination["name"] == city
        assert result.duration_days == 2
        titles = [item["title"] for day in result.itinerary["days"] for item in day["items"]]
        assert len(titles) == 6
        assert all("Знакомство с направлением" not in title for title in titles)
        assert len(set(titles)) == len(titles)


def test_istanbul_recommendations_are_concrete_and_suggested():
    result = asyncio.run(AgentPlanner().plan(context("Стамбул на 2 дня")))
    titles = [item["title"] for day in result.itinerary["days"] for item in day["items"]]
    assert any("Айя-София" in title for title in titles)
    assert any("Босфору" in title for title in titles)
    assert all(2 <= len(day["items"]) <= 4 for day in result.itinerary["days"])


def test_country_query_asks_for_city_before_duration():
    with pytest.raises(NeedsClarification, match="Какой город в Турции"):
        asyncio.run(AgentPlanner().plan(context("Хочу в Турцию летом")))

from copy import deepcopy

import pytest

from app.intent_preview import preview_intent


def test_explicit_params_win_and_are_not_mutated():
    params = {
        "destination": "Казань",
        "duration_days": 4,
        "dates": {"start_date": "2026-11-10", "end_date": "2026-11-13"},
        "origin": "Москва",
        "travelers": {"adults": 2, "children_ages": []},
        "budget": {"amount_minor": 15000000, "currency": "RUB"},
        "wishes": ["breakfast"],
    }
    original = deepcopy(params)

    result = preview_intent("Рим на 2 дня, нужен прямой рейс", params)

    assert result["parsed"] == {**params, "wishes": ["breakfast", "direct_flight"]}
    assert result["questions"] == []
    assert params == original


def test_fallback_extracts_supported_text_and_returns_bounded_questions():
    result = preview_intent("Хочу в Рим из Москвы на 3 дня, завтрак и без пересадок")

    assert result["preview_id"].startswith("ip_")
    assert result["parsed"]["destination"] == "Рим"
    assert result["parsed"]["duration_days"] == 3
    assert result["parsed"]["origin"] == "Москва"
    assert result["parsed"]["wishes"] == ["direct_flight", "breakfast"]
    assert [item["field"] for item in result["questions"]] == ["travelers", "budget"]
    assert result["analysis_mode"] == "fallback"
    assert result["warnings"] == []
    assert "query" not in result


def test_missing_core_fields_are_required_and_questions_are_capped():
    result = preview_intent("Хочу путешествие")

    assert len(result["questions"]) == 3
    assert [(item["field"], item["required"]) for item in result["questions"]] == [
        ("destination", True),
        ("duration_days", True),
        ("travelers", False),
    ]


def test_preview_ids_are_opaque_and_unique():
    first = preview_intent("Рим на 2 дня")
    second = preview_intent("Рим на 2 дня")

    assert first["preview_id"] != second["preview_id"]
    assert "Рим" not in first["preview_id"]


@pytest.mark.parametrize("query", ["", "   ", "x" * 2001, None, 42])
def test_invalid_query_is_rejected(query):
    with pytest.raises(ValueError):
        preview_intent(query)


def test_weekend_and_english_aliases_are_supported():
    result = preview_intent("Weekend to Istanbul from Moscow with sea view")

    assert result["parsed"]["destination"] == "Стамбул"
    assert result["parsed"]["origin"] == "Москва"
    assert result["parsed"]["duration_days"] == 2
    assert result["parsed"]["wishes"] == ["sea_view"]

import asyncio

from app import intent_preview


def test_llm_preview_is_sanitized_and_uses_llm_mode(monkeypatch):
    async def response(query):
        return {"destination": "Рим", "duration_days": 2, "dates": {"start_date": "2026-11-02", "end_date": "2026-11-03"}, "wishes": ["near_sea", "unknown"]}
    monkeypatch.setattr(intent_preview, "extract_intent", response)
    preview = asyncio.run(intent_preview.preview_intent_async("поездка"))
    assert preview["analysis_mode"] == "llm"
    assert preview["parsed"]["wishes"] == ["near_sea"]


def test_llm_unavailable_or_invalid_uses_fallback(monkeypatch):
    async def unavailable(query):
        return None
    monkeypatch.setattr(intent_preview, "extract_intent", unavailable)
    preview = asyncio.run(intent_preview.preview_intent_async("Рим на 2 дня"))
    assert preview["analysis_mode"] == "fallback"


def test_explicit_params_win_over_llm(monkeypatch):
    async def response(query):
        return {"destination": "Стамбул", "duration_days": 2}
    monkeypatch.setattr(intent_preview, "extract_intent", response)
    preview = asyncio.run(intent_preview.preview_intent_async("Стамбул на 2 дня", {"destination": "Рим", "duration_days": 3}))
    assert preview["parsed"]["destination"] == "Рим"
    assert preview["parsed"]["duration_days"] == 3

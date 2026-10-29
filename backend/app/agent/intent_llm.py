"""One-shot, untrusted DeepSeek intent extraction; no logging of user data."""
from __future__ import annotations

import os
from typing import Any

import httpx

SYSTEM = """Extract travel intent as JSON only. Never invent data. Keys: destination, duration_days, dates {start_date,end_date}, origin, travelers {adults,children_ages}, budget {amount_minor,currency}, wishes. Use null for unknown. Wishes only near_sea, sea_view, direct_flight, breakfast. Budget is total RUB kopecks."""


async def extract_intent(query: str) -> dict[str, Any] | None:
    key = os.getenv("LLM_API_KEY")
    if not key or os.getenv("GOGLOBE_INTENT_MODE", "auto") == "fallback":
        return None
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    payload = {"model": os.getenv("LLM_MODEL", "deepseek-chat"), "response_format": {"type": "json_object"},
               "max_tokens": 350, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": query}]}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(base_url + "/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=payload)
            response.raise_for_status()
            data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not isinstance(content, str):
            return None
        import json
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except (httpx.HTTPError, ValueError, TypeError, IndexError, KeyError):
        return None

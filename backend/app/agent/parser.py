"""Шаг 1 агента: извлечение параметров из текста. Владелец: Backend №2.

Модуль 1: Анализ и разбор естественного запроса пользователя.
- parse_mock — детерминированный парсер (эвристика), работает без LLM.
  Используется как fallback в CI, при отсутствии LLM_API_KEY, при таймауте.
- parse_llm — реальный вызов LLM (DeepSeek/OpenAI-совместимый API).
- missing_question — проверка полноты параметров и формирование уточняющего вопроса.

Контракт: чего нет в запросе — оставляем None, агент задаёт уточняющий вопрос,
а не угадывает.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, timedelta

import httpx

from app.agent.prompts import PARSER_SYSTEM_PROMPT
from app.schemas.search import DateRange, Money, ParsedQuery, SearchParams

logger = logging.getLogger(__name__)

_MONTHS = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "ма": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}
_MONTHS_NAMES = {
    "январ": "январь",
    "феврал": "февраль",
    "март": "март",
    "апрел": "апрель",
    "ма": "май",
    "июн": "июнь",
    "июл": "июль",
    "август": "август",
    "сентябр": "сентябрь",
    "октябр": "октябрь",
    "ноябр": "ноябрь",
    "декабр": "декабрь",
}
_DEST = {
    "турци": "Турция",
    "анталь": "Анталья, Турция",
    "стамбул": "Стамбул, Турция",
    "сочи": "Сочи, Россия",
    "итали": "Италия",
    "бали": "Бали, Индонезия",
    "дубай": "Дубай, ОАЭ",
    "оаэ": "ОАЭ",
    "египет": "Египет",
    "таиланд": "Таиланд",
    "пхукет": "Пхукет, Таиланд",
}


def parse_mock(query: str, params: SearchParams | None = None) -> ParsedQuery:
    """Детерминированный разбор запроса (fallback без LLM_API_KEY и в CI)."""
    q = query.lower()
    p = ParsedQuery()

    # 1. Направление
    for key, name in _DEST.items():
        if key in q:
            p.destination = name
            break

    # 2. Длительность
    if m := re.search(r"(\d+)\s*(дн|ноч|день|дня|дней)", q):
        p.duration_days = int(m.group(1))

    # 3. Бюджет
    if m := re.search(
        r"(?:бюджет(?:ом)?(?:\s*(?:до|в))?|до)\s*([\d\s]+)\s*(₽|руб|р\b|к\b|тыс)?", q
    ):
        amount = int(re.sub(r"\s", "", m.group(1)) or 0)
        unit = m.group(2)
        if unit in ("к", "тыс"):
            amount *= 1000
        if amount >= 1000:
            p.budget = Money(amount=amount)
    elif m := re.search(r"\b(\d+)\s*(к\b|тыс|тысяч)", q):
        amount = int(m.group(1)) * 1000
        if amount >= 1000:
            p.budget = Money(amount=amount)

    # 4. Путешественники
    if "вдво" in q or "на двоих" in q or "с девушкой" in q:
        p.travelers = 2
    elif m := re.search(r"(\d+)\s*(человек|чел|взросл)", q):
        p.travelers = int(m.group(1))
    elif "один" in q or "одна" in q or "соло" in q:
        p.travelers = 1
    elif "трои" in q or "втроем" in q or "втроём" in q:
        p.travelers = 3
    elif "четверы" in q or "вчетвером" in q:
        p.travelers = 4

    # 5. Пожелания
    if any(w in q for w in ("мор", "моря", "пляж", "первая линия")):
        p.wishes.append("sea_view")
    if any(w in q for w in ("прямой", "прямым", "без пересад")):
        p.wishes.append("direct_flight")
    if any(w in q for w in ("все включено", "всё включено", "all inclusive")):
        p.wishes.append("all_inclusive")

    # 6. Даты из месяца + длительности
    for key, month in _MONTHS.items():
        if re.search(rf"\b{key}", q) and p.duration_days:
            year = date.today().year if month >= date.today().month else date.today().year + 1
            start = date(year, month, 10)
            p.dates = DateRange(
                **{
                    "from": start.isoformat(),
                    "to": (start + timedelta(days=p.duration_days)).isoformat(),
                }
            )
            break

    # Явные params из формы имеют приоритет над текстом
    if params:
        p.dates = params.dates or p.dates
        p.budget = params.budget or p.budget
        p.travelers = params.travelers or p.travelers
        p.wishes = sorted(set(p.wishes) | set(params.wishes))

    return p


def missing_question(p: ParsedQuery) -> str | None:
    """Возвращает уточняющий вопрос, если критичные параметры отсутствуют. Иначе None."""
    if not p.destination:
        return "Куда хотите поехать?"
    if not p.dates:
        return "На какие даты планируете поездку?"
    if not p.travelers:
        return "Сколько человек поедет?"
    return None


def _llm_json_to_parsed_query(data: dict) -> ParsedQuery:
    """Конвертирует JSON-ответ LLM (расширенный формат prompts.py) в ParsedQuery контракта v0."""
    p = ParsedQuery()
    p.destination = data.get("destination")

    dates_raw = data.get("dates") or {}
    duration = dates_raw.get("duration_days")
    if duration is not None:
        p.duration_days = int(duration)

    date_from = dates_raw.get("from")
    date_to = dates_raw.get("to")
    month_name = dates_raw.get("month")

    # Если LLM дал конкретные даты — используем
    if date_from and date_to:
        p.dates = DateRange(**{"from": date_from, "to": date_to})
    elif date_from and p.duration_days:
        start = date.fromisoformat(date_from)
        end = start + timedelta(days=p.duration_days)
        p.dates = DateRange(**{"from": start.isoformat(), "to": end.isoformat()})
    elif month_name and p.duration_days:
        # Определяем месяц по имени
        for stem, num in _MONTHS.items():
            if month_name.lower().startswith(stem[:3]):
                year = date.today().year if num >= date.today().month else date.today().year + 1
                start = date(year, num, 10)
                p.dates = DateRange(
                    **{
                        "from": start.isoformat(),
                        "to": (start + timedelta(days=p.duration_days)).isoformat(),
                    }
                )
                break

    budget_raw = data.get("budget") or {}
    if budget_raw.get("max") is not None:
        p.budget = Money(amount=int(budget_raw["max"]), currency=budget_raw.get("currency", "RUB"))

    if data.get("travelers") is not None:
        p.travelers = int(data["travelers"])

    p.wishes = list(data.get("wishes") or [])
    return p


async def parse_llm(
    query: str,
    params: SearchParams | None = None,
    timeout_sec: float = 10.0,
) -> tuple[ParsedQuery, str | None]:
    """Разбирает запрос через LLM (DeepSeek/OpenAI-совместимый API).

    Возвращает (ParsedQuery, clarifying_question | None).
    При ошибке — фолбэк на parse_mock.
    """
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "deepseek-chat")

    if not api_key:
        logger.info("LLM_API_KEY не задан — используем parse_mock")
        p = parse_mock(query, params)
        return p, missing_question(p)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": PARSER_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            raw_content = data["choices"][0]["message"]["content"]
            parsed_json = json.loads(raw_content)

            p = _llm_json_to_parsed_query(parsed_json)

            # Явные params из формы имеют приоритет
            if params:
                p.dates = params.dates or p.dates
                p.budget = params.budget or p.budget
                p.travelers = params.travelers or p.travelers
                p.wishes = sorted(set(p.wishes) | set(params.wishes))

            # Уточняющий вопрос: берём из LLM, если он решил, или из missing_question
            clarifying = None
            if parsed_json.get("needs_clarification"):
                clarifying = parsed_json.get("clarifying_question") or missing_question(p)
            elif missing_question(p):
                clarifying = missing_question(p)

            return p, clarifying
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ошибка вызова LLM-парсера (%s), переключаемся на parse_mock", exc)
        p = parse_mock(query, params)
        return p, missing_question(p)

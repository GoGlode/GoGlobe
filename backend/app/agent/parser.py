"""Модуль 1: Анализ и разбор естественного запроса пользователя (LLM + универсальный fallback).

Владелец: Backend №2.

Контракт: чего нет в запросе — оставляем None, агент задаёт уточняющий вопрос,
а не угадывает.
Принцип честности: ИИ никогда не выдумывает даты, цены или направления.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import Any

import httpx

from app.agent.prompts import PARSER_SYSTEM_PROMPT
from app.config import get_settings
from app.schemas.search import DateRange, Money, ParsedQuery, SearchParams

logger = logging.getLogger(__name__)

# Ключи — regex-паттерны (без \b на концах, они добавляются при поиске).
# Используем полные основы, чтобы «Мальдивы» не совпадало с «май».
_MONTHS: dict[str, int] = {
    "январ": 1,
    "феврал": 2,
    "март(?!а|у|ом|е)|марта|марту|мартом|марте": 3,
    "апрел": 4,
    "май|мая|маю|маем|мае": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}

_DEST: dict[str, str] = {
    "турци": "Турция",
    "анталь": "Анталья, Турция",
    "стамбул": "Стамбул, Турция",
    "сочи": "Сочи, Россия",
    "итали": "Италия",
    "рим": "Рим, Италия",
    "бали": "Бали, Индонезия",
    "дубай": "Дубай, ОАЭ",
    "оаэ": "ОАЭ",
    "египет": "Египет",
    "хургад": "Хургада, Египет",
    "шарм": "Шарм-эль-Шейх, Египет",
    "таиланд": "Таиланд",
    "пхукет": "Пхукет, Таиланд",
    "мальдив": "Мальдивы",
    "грузи": "Грузия",
    "тбилиси": "Тбилиси, Грузия",
    "армени": "Армения",
    "ереван": "Ереван, Армения",
}


def extract_json_payload(raw_content: str) -> dict[str, Any]:
    """Извлекает валидный JSON-словарь из ответа LLM, даже если он обёрнут в markdown codeblock."""
    clean = raw_content.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
        clean = clean.strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("{")
        end = clean.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(clean[start : end + 1])
        raise


def parse_mock(query: str, params: SearchParams | None = None) -> ParsedQuery:
    """Универсальный детерминированный разбор запроса (fallback без LLM_API_KEY и в CI)."""
    q = query.lower()
    p = ParsedQuery()

    # 1. Направление
    for key, name in _DEST.items():
        if key in q:
            p.destination = name
            break

    # 2. Длительность поездки
    if m := re.search(r"(\d+)\s*(дн|ноч|день|дня|дней)", q):
        p.duration_days = int(m.group(1))
    elif "на две недели" in q or "на 2 недели" in q:
        p.duration_days = 14
    elif "на неделю" in q:
        p.duration_days = 7
    elif "на пару дней" in q or "на выходные" in q:
        p.duration_days = 3

    # 3. Бюджет (числа с пробелами, валюты, суффиксы к/тыс)
    currency = "RUB"
    if any(c in q for c in ("$", "usd", "доллар")):
        currency = "USD"
    elif any(c in q for c in ("€", "eur", "евро")):
        currency = "EUR"

    if m := re.search(
        r"(?:бюджет(?:ом)?(?:\s*(?:до|в|около))?|до|в пределах|около)\s*([\d\s]+)\s*(₽|руб|р\b|к\b|тыс|\$|€|usd|eur)?",
        q,
    ):
        amount = int(re.sub(r"\s", "", m.group(1)) or 0)
        unit = m.group(2)
        if unit in ("к", "тыс"):
            amount *= 1000
        if amount > 0:
            p.budget = Money(amount=amount, currency=currency)
    elif m := re.search(r"\b(\d+)\s*(к\b|тыс|тысяч|\$|€|usd|eur)", q):
        unit = m.group(2)
        amount = int(m.group(1))
        if unit in ("к", "тыс", "тысяч"):
            amount *= 1000
        if amount > 0:
            p.budget = Money(amount=amount, currency=currency)
    elif m := re.search(r"\b(\d{2,3}[\s\u00a0]\d{3})\b", q):
        amount = int(re.sub(r"[\s\u00a0]", "", m.group(1)))
        if amount >= 1000:
            p.budget = Money(amount=amount, currency=currency)

    # 4. Путешественники
    if any(
        w in q for w in ("вдво", "на двоих", "с девушкой", "с парнем", "с женой", "с мужем", "пара")
    ):
        p.travelers = 2
    elif m := re.search(r"(\d+)\s*(человек|чел|взросл)", q):
        p.travelers = int(m.group(1))
    elif any(w in q for w in ("один", "одна", "соло", "на одного")):
        p.travelers = 1
    elif any(w in q for w in ("трои", "втроем", "втроём", "на троих", "с ребенком")):
        p.travelers = 3
    elif any(w in q for w in ("четверы", "вчетвером", "на четверых", "компани")):
        p.travelers = 4

    # 5. Пожелания (wishes)
    if any(w in q for w in ("мор", "моря", "пляж", "первая линия", "у моря")):
        p.wishes.append("sea_view")
    if any(w in q for w in ("прямой", "прямым", "без пересад")):
        p.wishes.append("direct_flight")
    if any(w in q for w in ("все включено", "всё включено", "all inclusive")):
        p.wishes.append("all_inclusive")
    if any(w in q for w in ("завтрак", "с завтраком")):
        p.wishes.append("breakfast")
    if any(w in q for w in ("бассейн", "бассейном")):
        p.wishes.append("pool")
    if any(w in q for w in ("тихий", "спокойный")):
        p.wishes.append("quiet")
    if any(w in q for w in ("в центре", "центр города")):
        p.wishes.append("city_center")
    if any(w in q for w in ("спа", "spa")):
        p.wishes.append("spa")

    # 6. Даты: точный диапазон чисел («с 10 по 15 ноября») или только месяц.
    # Принцип честности: если конкретный день не указан — не угадываем.
    # dates остаётся None, добавляем предупреждение; агент задаст уточняющий вопрос.
    date_matched = False
    for pattern, month in _MONTHS.items():
        # Диапазон «с 10 по 15 ноября» или «10-15 ноября»
        range_match = re.search(
            rf"(?:с\s*)?(\d{{1,2}})\s*(?:по|-|–)\s*(\d{{1,2}})\s*(?:{pattern})", q
        )
        if range_match:
            day_start = int(range_match.group(1))
            day_end = int(range_match.group(2))
            year = date.today().year if month >= date.today().month else date.today().year + 1
            start = date(year, month, day_start)
            end = date(year, month, day_end)
            p.duration_days = max((end - start).days, 1)
            p.dates = DateRange(**{"from": start.isoformat(), "to": end.isoformat()})
            date_matched = True
            break

    if not date_matched:
        for pattern, month in _MONTHS.items():
            if re.search(rf"(?:{pattern})", q):
                if p.duration_days:
                    # Месяц известен, длительность известна, но день не указан.
                    # Не угадываем — оставляем dates=None и просим уточнить.
                    month_names = {
                        1: "январе", 2: "феврале", 3: "марте", 4: "апреле",
                        5: "мае", 6: "июне", 7: "июле", 8: "августе",
                        9: "сентябре", 10: "октябре", 11: "ноябре", 12: "декабре",
                    }
                    p.warnings.append(
                        f"Месяц ({month_names.get(month, str(month))}) указан, "
                        "но конкретная дата начала не задана — уточните число."
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
    if not p.destination and not p.dates:
        return "Куда именно вы хотите поехать и на какие примерно даты или длительность?"
    if not p.destination:
        return "Какую страну или город вы рассматриваете для поездки?"
    if not p.dates:
        dest_part = f" в {p.destination}" if p.destination else ""
        return f"На какие даты или на сколько дней вы планируете поездку{dest_part}?"
    return None


def _llm_json_to_parsed_query(data: dict[str, Any]) -> ParsedQuery:
    """Конвертирует JSON-ответ LLM в модель ParsedQuery API-контракта v0."""
    p = ParsedQuery()
    p.destination = data.get("destination")

    dates_raw = data.get("dates") or {}
    duration = dates_raw.get("duration_days")
    if duration is not None:
        p.duration_days = int(duration)

    date_from = dates_raw.get("from")
    date_to = dates_raw.get("to")
    month_name = dates_raw.get("month")

    if date_from and date_to:
        p.dates = DateRange(**{"from": date_from, "to": date_to})
    elif date_from and p.duration_days:
        start = date.fromisoformat(date_from)
        end = start + timedelta(days=p.duration_days)
        p.dates = DateRange(**{"from": start.isoformat(), "to": end.isoformat()})
    elif month_name and p.duration_days:
        # Месяц известен, но конкретный день не указан — не угадываем.
        # Оставляем dates=None; агент задаст уточняющий вопрос.
        month_abbr = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        ru_abbr = {
            "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "маи": 5,
            "июн": 6, "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
        }
        ml = month_name.lower()[:3]
        month_num = month_abbr.get(ml) or ru_abbr.get(ml)
        month_display = month_name
        p.warnings.append(
            f"Месяц ({month_display}) указан, "
            "но конкретная дата начала не задана — уточните число."
        )
        _ = month_num  # резервируем для будущего использования

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
    При ошибке или недоступности ключа — безопасный фолбэк на parse_mock.
    """
    settings = get_settings()
    api_key = settings.llm_api_key.strip()
    base_url = settings.llm_base_url.rstrip("/")
    model = settings.llm_model

    if not api_key or settings.use_mock_ai:
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
            parsed_json = extract_json_payload(raw_content)

            p = _llm_json_to_parsed_query(parsed_json)

            # Явные params из формы имеют приоритет над текстом
            if params:
                p.dates = params.dates or p.dates
                p.budget = params.budget or p.budget
                p.travelers = params.travelers or p.travelers
                p.wishes = sorted(set(p.wishes) | set(params.wishes))

            # Уточняющий вопрос
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


# Алиас для обратной совместимости с кодом агента
parse_user_query = parse_llm

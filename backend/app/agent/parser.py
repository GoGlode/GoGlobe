"""Шаг 1 агента: извлечение параметров из текста. Владелец: Backend №2.

Сейчас — эвристика для моков (работает без LLM). Реальный парсер через LLM:
реализовать `parse_llm` и переключить GOGLOBE_PARSER=llm. Контракт один и тот же:
чего нет в запросе — оставляем None, агент задаст уточняющий вопрос, а не угадывает.
"""
import re
from datetime import date, timedelta

from app.schemas.search import DateRange, Money, ParsedQuery, SearchParams

_MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7,
           "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
_DEST = {"турци": "Турция", "анталь": "Турция", "египет": "Египет", "таиланд": "Таиланд"}


def parse_mock(query: str, params: SearchParams | None = None) -> ParsedQuery:
    q = query.lower()
    p = ParsedQuery()
    for key, name in _DEST.items():
        if key in q:
            p.destination = name
            break
    if m := re.search(r"(\d+)\s*(дн|ноч)", q):
        p.duration_days = int(m.group(1))
    if m := re.search(r"до\s*([\d\s]+)\s*(₽|руб|р\b|к\b|тыс)?", q):
        amount = int(re.sub(r"\s", "", m.group(1)) or 0)
        if m.group(2) in ("к", "тыс"):
            amount *= 1000
        if amount >= 1000:
            p.budget = Money(amount=amount)
    if "вдво" in q or "на двоих" in q:
        p.travelers = 2
    elif m := re.search(r"(\d+)\s*(человек|чел|взросл)", q):
        p.travelers = int(m.group(1))
    elif "один" in q or "одна" in q:
        p.travelers = 1
    if "море" in q or "моря" in q or "пляж" in q:
        p.wishes.append("sea_view")
    if "прямой" in q or "прямым" in q:
        p.wishes.append("direct_flight")
    for key, month in _MONTHS.items():
        if re.search(rf"\b{key}", q) and p.duration_days:
            year = date.today().year if month >= date.today().month else date.today().year + 1
            start = date(year, month, 10)
            p.dates = DateRange(**{"from": start.isoformat(),
                                   "to": (start + timedelta(days=p.duration_days)).isoformat()})
            break
    # Явные params из формы имеют приоритет над текстом
    if params:
        p.dates = params.dates or p.dates
        p.budget = params.budget or p.budget
        p.travelers = params.travelers or p.travelers
        p.wishes = sorted(set(p.wishes) | set(params.wishes))
    return p


def missing_question(p: ParsedQuery) -> str | None:
    if not p.destination:
        return "Куда хотите поехать?"
    if not p.dates:
        return "На какие даты планируете поездку?"
    if not p.travelers:
        return "Сколько человек поедет?"
    return None

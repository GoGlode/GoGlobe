"""Модуль 1: Анализ и разбор естественного запроса пользователя (LLM + универсальный fallback).

Владелец: Backend №2.

Контракт: чего нет в запросе — оставляем None, агент задаёт уточняющий вопрос,
а не угадывает.
Принцип честности: ИИ никогда не выдумывает даты, цены или направления.

Устойчивость (после прогона на падения 27.10.2026):
* невалидный календарный день («с 31 по 32 ноября») — warning + уточнение, не 500 (F-02);
* перевёрнутый диапазон («с 10 по 5 ноября») — warning + уточнение (F-08);
* диапазон через границу года («с 30 декабря по 2 января») разбирается (F-19);
* regex не срабатывают на подстроках: «мороз» ≠ море, «майонез» ≠ май (F-17).
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

# Тексты фолбэка. В них нет ни ключа, ни URL, ни тела ответа провайдера (F-24).
_FALLBACK_NOT_CONFIGURED = (
    "LLM-парсер не настроен (нет ключа или включён режим эвристик): "
    "запрос разобран эвристиками, часть параметров может быть не распознана"
)
_FALLBACK_ERROR = (
    "LLM-парсер недоступен: запрос разобран эвристиками, проверьте параметры перед поиском"
)

# Ключи — regex-паттерны месяцев. Границы слова добавляются при поиске,
# поэтому основы намеренно полные: «Мальдивы» не должно совпадать с «май».
_MONTHS: dict[str, int] = {
    # Основы уникальны для русского языка, поэтому хватает границы слова + \w*.
    r"январ\w*": 1,
    r"феврал\w*": 2,
    "март(?:а|у|е|ом)?": 3,
    r"апрел\w*": 4,
    "май|мая|маю|маем|мае": 5,
    r"июн\w*": 6,
    r"июл\w*": 7,
    r"август\w*": 8,
    r"сентябр\w*": 9,
    r"октябр\w*": 10,
    r"ноябр\w*": 11,
    r"декабр\w*": 12,
}

_MONTH_NAMES_NOMINATIVE: dict[int, str] = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}

# Направления: основа слова -> человекочитаемое название.
# Список расширен после F-12: известное направление больше не теряется.
_DEST: dict[str, str] = {
    "турци": "Турция",
    "анталья": "Анталья, Турция",
    "антали": "Анталья, Турция",
    "стамбул": "Стамбул, Турция",
    "сочи": "Сочи, Россия",
    "крым": "Крым, Россия",
    "казан": "Казань, Россия",
    "москв": "Москва, Россия",
    "петербург": "Санкт-Петербург, Россия",
    "итали": "Италия",
    "рим": "Рим, Италия",
    "венеци": "Венеция, Италия",
    "испани": "Испания",
    "барселон": "Барселона, Испания",
    "греци": "Греция",
    "афин": "Афины, Греция",
    "кипр": "Кипр",
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
    "япони": "Япония",
    "токио": "Токио, Япония",
    "вьетнам": "Вьетнам",
    "шри-ланк": "Шри-Ланка",
    "инди[яию]": "Индия",
    "гоа": "Гоа, Индия",
    "тунис": "Тунис",
    "марокко": "Марокко",
    "черногор": "Черногория",
    "серби": "Сербия",
    "хорвати": "Хорватия",
    "чехи": "Чехия",
    "прага": "Прага, Чехия",
    "австри": "Австрия",
    "вен[ае]": "Вена, Австрия",
    "германи": "Германия",
    "франци": "Франция",
    "париж": "Париж, Франция",
    "португали": "Португалия",
    "мексик": "Мексика",
    "доминикан": "Доминикана",
    "куб[ае]": "Куба",
    "сейшел": "Сейшелы",
}

_SUPPORTED_DIRECTIONS = (
    "Турция, Египет, ОАЭ, Таиланд, Мальдивы, Сочи, Италия, Греция, Испания, Кипр, Грузия, Армения"
)

_DEST_PATTERNS = [(re.compile(rf"(?<![а-яёa-z]){stem}"), name) for stem, name in _DEST.items()]

# Пляж/море — только целыми словами, иначе «мороз» превращается в sea_view (F-17).
_SEA_RE = re.compile(
    r"(?<![а-яё])(?:морем|море|моря|морю|морской|морская|морское|пляж\w*|первая линия)(?![а-яё])"
)


def _whole(pattern: str) -> str:
    """Оборачивает паттерн в границы слова (кириллица), не давая совпадений внутри слов."""
    return rf"(?<![а-яё])(?:{pattern})(?![а-яё])"


# День месяца как отдельное число; вынесено из f-string ради совместимости с Python 3.11.
_DAY = r"(?<![а-яё])(\d{1,2})(?![а-яё])"


def _month_of(word: str) -> int | None:
    """Номер месяца по названию («ноября» -> 11) или None."""
    candidate = word.lower().strip(".,;:!?()")
    for pattern, month in _MONTHS.items():
        if re.fullmatch(rf"(?:{pattern})", candidate):
            return month
    return None


def _year_for_month(month: int, today: date) -> int:
    """Год ближайшего будущего месяца: прошедший месяц — уже следующий год."""
    return today.year if month >= today.month else today.year + 1


def _parse_date_range(query: str) -> tuple[DateRange | None, int | None, list[str]]:
    """Достаёт диапазон дат из текста.

    Возвращает (dates, duration_days, warnings). Если даты неполные или
    некорректные — dates=None и предупреждение, чтобы агент спросил,
    а не падал (F-02, F-08, F-19).
    """
    today = date.today()

    # 1. Диапазон с двумя месяцами: «с 30 декабря по 2 января» (F-19).
    two_month = re.search(
        r"с\s*(\d{1,2})\s+([а-яё]+)\s*(?:по|-|–)\s*(\d{1,2})\s+([а-яё]+)",
        query,
    )
    if two_month:
        start_day, start_month_raw = int(two_month.group(1)), two_month.group(2)
        end_day, end_month_raw = int(two_month.group(3)), two_month.group(4)
        start_month, end_month = _month_of(start_month_raw), _month_of(end_month_raw)
        if start_month and end_month:
            start_year = _year_for_month(start_month, today)
            end_year = start_year if end_month >= start_month else start_year + 1
            try:
                start = date(start_year, start_month, start_day)
                end = date(end_year, end_month, end_day)
            except ValueError:
                return (
                    None,
                    None,
                    [
                        (
                            f"Не удалось разобрать даты «{two_month.group(0)}»: "
                            "проверьте день и месяц начала и окончания поездки."
                        )
                    ],
                )
            if end <= start:
                return None, None, ["Дата окончания раньше даты начала — уточните порядок дат."]
            return (
                DateRange(**{"from": start.isoformat(), "to": end.isoformat()}),
                (end - start).days,
                [],
            )

    # 2. Диапазон внутри одного месяца: «с 10 по 15 ноября» / «10-15 ноября».
    for pattern, month in _MONTHS.items():
        same_month = re.search(
            rf"(?:с\s*)?{_DAY}\s*(?:по|-|–)\s*{_DAY}\s*{_whole(pattern)}",
            query,
        )
        if not same_month:
            continue

        start_day, end_day = int(same_month.group(1)), int(same_month.group(2))
        year = _year_for_month(month, today)
        try:
            start = date(year, month, start_day)
            end = date(year, month, end_day)
        except ValueError:
            return (
                None,
                None,
                [
                    (
                        f"Не удалось разобрать даты «{same_month.group(0)}»: "
                        "проверьте день и месяц начала и окончания поездки."
                    )
                ],
            )
        if end <= start:
            return None, None, ["Дата окончания раньше даты начала — уточните порядок дат."]
        return (
            DateRange(**{"from": start.isoformat(), "to": end.isoformat()}),
            (end - start).days,
            [],
        )

    # 3. Указан только месяц без числа — не угадываем (F-14: грамматика + проброс warning).
    for pattern, month in _MONTHS.items():
        if re.search(_whole(pattern), query):
            return (
                None,
                None,
                [
                    (
                        f"{_MONTH_NAMES_NOMINATIVE[month]} указан без числа: "
                        "уточните число начала поездки."
                    )
                ],
            )

    return None, None, []


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

    # 1. Направление (границы слова — чтобы «Рим» не находился в «пример»).
    for pattern, name in _DEST_PATTERNS:
        if pattern.search(q):
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
        travelers = int(m.group(1))
        if travelers >= 1:
            p.travelers = travelers
    elif any(w in q for w in ("один", "одна", "соло", "на одного")):
        p.travelers = 1
    elif any(
        w in q
        for w in ("трои", "втроем", "втроём", "на троих", "с ребенком", "с ребёнком", "с детьми")
    ):
        p.travelers = 3
    elif any(w in q for w in ("четверы", "вчетвером", "на четверых", "компани")):
        p.travelers = 4

    # 5. Пожелания (wishes)
    if _SEA_RE.search(q):
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

    # 6. Даты: точный диапазон или только месяц (месяц без числа не додумываем).
    dates, duration_from_range, date_warnings = _parse_date_range(q)
    p.warnings.extend(date_warnings)
    if dates is not None:
        p.dates = dates
        if duration_from_range:
            p.duration_days = duration_from_range

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
        return (
            "Куда именно вы хотите поехать и на какие примерно даты? "
            f"Сейчас ищу по направлениям: {_SUPPORTED_DIRECTIONS}."
        )
    if not p.destination:
        return (
            "Какую страну или город вы рассматриваете для поездки? "
            f"Доступные направления: {_SUPPORTED_DIRECTIONS}."
        )
    if not p.dates:
        dest_part = f" в {p.destination}" if p.destination else ""
        return f"На какие даты или на сколько дней вы планируете поездку{dest_part}?"
    return None


def _llm_json_to_parsed_query(data: dict[str, Any]) -> ParsedQuery:
    """Конвертирует JSON-ответ LLM в модель ParsedQuery API-контракта v0.

    Битые даты/числа не протаскиваются в контракт: DateRange валидирует ISO-формат
    и порядок дат, а исключение ловится в parse_llm и включает фолбэк на parse_mock (F-13).
    """
    p = ParsedQuery()
    destination = data.get("destination")
    p.destination = destination.strip() if isinstance(destination, str) else None
    if not p.destination:
        p.destination = None

    dates_raw = data.get("dates") or {}
    duration = dates_raw.get("duration_days")
    if duration is not None:
        try:
            parsed_duration = int(duration)
        except (TypeError, ValueError):
            parsed_duration = 0
        if parsed_duration > 0:
            p.duration_days = parsed_duration

    date_from = dates_raw.get("from")
    date_to = dates_raw.get("to")
    month_name = dates_raw.get("month")

    if date_from and date_to:
        p.dates = DateRange(**{"from": str(date_from), "to": str(date_to)})
    elif date_from and p.duration_days:
        start = date.fromisoformat(str(date_from))
        end = start + timedelta(days=p.duration_days)
        p.dates = DateRange(**{"from": start.isoformat(), "to": end.isoformat()})
    elif month_name:
        # Месяц известен, но конкретный день не указан — не угадываем.
        p.warnings.append(f"{month_name} указан без числа: уточните число начала поездки.")

    budget_raw = data.get("budget") or {}
    if budget_raw.get("max") is not None:
        try:
            amount = float(budget_raw["max"])
        except (TypeError, ValueError):
            amount = 0.0
        if amount > 0:
            p.budget = Money(
                amount=amount, currency=str(budget_raw.get("currency") or "RUB").upper()
            )

    travelers_raw = data.get("travelers")
    if travelers_raw is not None:
        try:
            travelers = int(travelers_raw)
        except (TypeError, ValueError):
            travelers = 0
        if travelers >= 1:
            p.travelers = travelers

    p.wishes = [str(w) for w in (data.get("wishes") or [])]
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
        p.warnings.append(_FALLBACK_NOT_CONFIGURED)
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
        # В лог — только тип ошибки: текст исключения и заголовки могут содержать
        # ключ, URL провайдера или фрагмент ответа (F-24).
        logger.warning("LLM-парсер недоступен (%s), переключаемся на эвристики", type(exc).__name__)
        p = parse_mock(query, params)
        p.warnings.append(_FALLBACK_ERROR)
        return p, missing_question(p)


# Алиас для обратной совместимости с кодом агента
parse_user_query = parse_llm

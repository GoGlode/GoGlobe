"""Сравнение денег в разных валютах. Владелец: Backend №2.

Провайдеры отдают цены в своей валюте, а пользователь может назвать бюджет
в другой. Сравнивать «число с числом» без пересчёта нельзя (F-09), поэтому
здесь собраны в одном месте демо-курсы и форматирование сумм.

ВАЖНО: курсы — фиксированные константы для демо, а не биржевые данные.
При подключении реального источника курсов заменить `RATES_TO_RUB` на адаптер.
"""

from __future__ import annotations

from app.schemas.search import Money

# Сколько рублей в одной единице валюты. Демо-значения, не финансовая истина.
RATES_TO_RUB: dict[str, float] = {
    "RUB": 1.0,
    "USD": 90.0,
    "EUR": 100.0,
}

SYMBOLS: dict[str, str] = {
    "RUB": "₽",
    "USD": "$",
    "EUR": "€",
}


def norm_currency(currency: str | None) -> str:
    """Нормализует код валюты: 'rub' -> 'RUB', пустое значение -> 'RUB'."""
    if not currency:
        return "RUB"
    return currency.strip().upper()


def symbol(currency: str | None) -> str:
    """Символ валюты для человекочитаемых объяснений."""
    code = norm_currency(currency)
    return SYMBOLS.get(code, code)


def format_money(money: Money) -> str:
    """'26000 RUB' -> '26 000 ₽' (пробелы как разделители тысяч)."""
    return f"{money.amount:,.0f} {symbol(money.currency)}".replace(",", " ")


def rate(from_currency: str, to_currency: str) -> float | None:
    """Курс пересчёта from -> to. None, если валюту не знаем."""
    src = RATES_TO_RUB.get(norm_currency(from_currency))
    dst = RATES_TO_RUB.get(norm_currency(to_currency))
    if not src or not dst:
        return None
    return src / dst


def convert(amount: float, from_currency: str, to_currency: str) -> float | None:
    """Пересчитывает сумму между известными валютами; неизвестная валюта -> None."""
    if norm_currency(from_currency) == norm_currency(to_currency):
        return amount
    r = rate(from_currency, to_currency)
    if r is None:
        return None
    return amount * r


def normalize_budget(budget: Money | None, target_currency: str) -> tuple[Money | None, str | None]:
    """Приводит бюджет к валюте цен провайдера.

    Возвращает (бюджет в валюте цен, пояснение для warnings | None).
    Если валюту пересчитать нельзя — бюджет не применяется, чтобы не отбросить
    варианты по несравнимым числам, и об этом честно сообщается.
    """
    if budget is None:
        return None, None

    target = norm_currency(target_currency)
    source = norm_currency(budget.currency)
    if source == target:
        return budget, None

    converted = convert(budget.amount, source, target)
    if converted is None:
        return None, (
            f"Курс {source}→{target} неизвестен: бюджет {format_money(budget)} "
            "не применялся при проверке"
        )

    r = rate(source, target)
    note = (
        f"Бюджет {format_money(budget)} пересчитан в {target} по демо-курсу "
        f"1 {source} = {r:g} {target}"
    )
    return Money(amount=round(converted, 2), currency=target), note

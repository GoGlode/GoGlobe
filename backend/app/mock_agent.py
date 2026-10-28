"""Синтетический сценарий для интеграции UI. Не парсер и не реальные предложения."""
import asyncio
from datetime import datetime, timezone

from app.models import (
    Dates, ErrorInfo, Explanation, Flight, Hotel, Money, Offer,
    Scenario, SearchRequest, SearchResult, Source,
)
from app.ports import Emit

WARNING = "Демонстрационные вымышленные данные. Цены и наличие не подтверждены; текст запроса не анализируется."
FIXTURE_DATE = datetime(2026, 10, 20, tzinfo=timezone.utc)


class MockAgent:
    def __init__(self, delay: float = 0.15):
        self.delay = delay

    async def search(self, search_id: str, request: SearchRequest, scenario: Scenario, emit: Emit) -> SearchResult:
        for stage, message in [
            ("parsing", "Принимаю параметры демонстрационного запроса"),
            ("flights", "Загружаю мок перелёта"),
            ("hotels", "Загружаю моки отелей"),
            ("validating", "Проверяю параметры демо-сценария"),
            ("ranking", "Готовлю демонстрационную подборку"),
        ]:
            await emit(stage, message)
            await asyncio.sleep(self.delay)

        result = SearchResult(id=search_id, status=scenario.value, parsed=request.params, warnings=[WARNING])
        if scenario == Scenario.needs_clarification:
            result.clarifying_question = "Из какого города и на какие точные даты планируете поездку?"
            return result
        if scenario == Scenario.error:
            result.error = ErrorInfo(code="MOCK_PROVIDER_UNAVAILABLE", message="Демонстрационная ошибка источника")
            return result
        if scenario == Scenario.empty:
            return result

        # Fixture намеренно фиксирован: агент №2 позже реализует понимание текста,
        # подбор по пожеланиям и ранжирование. Здесь фильтруются только явные параметры.
        dates = Dates.model_validate({"from": "2026-11-10", "to": "2026-11-15"})
        params = request.params
        incompatible = (
            (params.dates is not None and params.dates != dates)
            or (params.travelers is not None and params.travelers != 2)
            or (params.origin is not None and params.origin.casefold() not in {"москва", "mow"})
            or (params.destination is not None and params.destination.casefold() not in {"турция", "анталья", "turkey", "antalya"})
            or bool(set(params.wishes) - {"sea_view", "direct_flight"})
        )
        if incompatible:
            result.status = "empty"
            result.warnings.append("Мок поддерживает только Москву → Анталью, 10–15 ноября 2026, двух путешественников, sea_view/direct_flight.")
            return result

        for index, (name, price) in enumerate([("Demo Sea Hotel", 72400), ("Demo Coast Resort", 78000)], 1):
            total = price + 40000
            if params.budget and total > params.budget.max:
                continue
            result.offers.append(Offer(
                id=f"offer_{index}", destination="Анталья, Турция",
                hotel=Hotel(name=name, stars=4, rating=8.5, price=Money(amount=price)),
                flight=Flight(origin="Москва", destination="Анталья", direct=True, dates=dates, price=Money(amount=40000)),
                total_price=Money(amount=total), data_freshness=FIXTURE_DATE,
                explanation=Explanation(
                    why=["Пример отеля у моря и прямого перелёта на двоих"],
                    pros=["Демонстрационный вид на море"], cons=["Вымышленное предложение, бронирование недоступно"],
                    sources=[Source(name="GoGlobe synthetic fixtures v0")],
                ),
            ))
        if not result.offers:
            result.status = "empty"
        elif scenario == Scenario.partial:
            result.offers = result.offers[:1]
            result.warnings.append("Демонстрация: часть источников недоступна")
        return result

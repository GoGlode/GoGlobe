# Подключение агента и источников

Основная factory: `app.bff.create_app(db_path=None, *, agent=None, tools=None, agent_timeout=None)`.

`app.main` экспортирует ту же factory и готовый `app`. Отдельная страница не нужна. По умолчанию используются DemoPlanner и демонстрационные источники.

## Агент

Реализуйте `Planner.plan(context: PlanContext) -> AgentPlan` как async-метод. `PlanContext` содержит query, копию явных params, единый deadline_at и tools. Никаких сторонних SDK или endpoint в контракт агента не зашито.

`AgentPlan` содержит destination, duration_days, относительный itinerary, sources, warnings, data_mode. У агента нет права выставлять флаги сохранения, владельца, ID, сроки хранения или итоговую цену. BFF проверяет число/порядок дней и пунктов, уникальность ID, явные параметры, ссылки на источники и IANA-зону. Поля даты в относительной программе должны быть null; BFF назначает явные даты отдельно.

Инициализацию собственного агента и его SDK-клиента выполняет следующий модуль. Передайте созданный объект в `create_app(agent=...)`. Для отдельного ASGI-модуля можно начать с проверенной конфигурации:

```python
from app.bff import create_app
from app.planning import DemoPlanner
from app.integrations.service import IntegrationTools

app = create_app(agent=DemoPlanner(), tools=IntegrationTools())
```

Затем замените DemoPlanner своей реализацией. Это точка подключения, а не уже реализованный клиент неизвестного ИИ API. У своего HTTP/SDK-клиента задайте timeout не больше остатка context.deadline_at. Блокирующие сетевые вызовы и CPU-работу нельзя выполнять прямо в event loop; Python-таймаут не может принудительно остановить блокирующую стороннюю функцию.

## Поставщики

Передайте `IntegrationTools(hotels=hotel_provider, flights=flight_provider)`. Каждый поставщик объявляет `data_mode` (demo/live) и реализует соответствующий async search(criteria) -> ToolResult из `app.integrations.ports`.

Для третьего инструмента передайте `destinations=destination_provider` и вызывайте
`context.tools.destinations(DestinationCriteria(query, context.deadline_at))`.
HTTP-адаптеры трёх типов, gateway-протокол и проверки версии 0.3.2 описаны в
`module-03-guide.md`; результаты повторной проверки — `module-03-reaudit.md`.
Существующие инструменты задачи 4 в общей рабочей папке сохраняются: эту запись
не следует понимать как замену ResilientIntegrationTools в настроенном сервере.

Агент вызывает `context.tools.hotels(HotelCriteria(...))` и `context.tools.flights(FlightCriteria(...))`. Даты проживания и вылетов различаются; срок выполнения общий. Обёртка проверяет схемы, валюту/единицы, источники всех вложенных цен, покрытие, время сегментов, контекст дат и свежесть. Ошибки и таймауты дают unavailable с пустыми items; переключения с live на demo нет.

Booking URL по умолчанию удаляются. Для конкретного поставщика явно задайте `allowed_booking_hosts` и `allowed_booking_query_keys`; остальные домены, параметры, credentials, нестандартные порты и fragments не проходят проверку. Реальные URL/авторизация/схемы API пока не выданы и не выдуманы.

Demo-поставщики возвращают fixture только при точном совпадении поддержанных дат и состава. Это не перенос старой цены на новые параметры. Истёкшие цены получают stale без продления checked_at/valid_until. Полученные тарифы не становятся автоматически ценой всего Trip.

## Сбои и повторы

- Неавторизованный запрос не вызывает агента.
- Ошибка/таймаут до принятия запроса не оставляют Trip или Accepted.
- При параллельных повторах одного ключа в одном процессе агент вызывается один раз; исходный Accepted сохраняется в SQLite.
- Другой JSON с тем же ключом даёт конфликт. Запоздалый результат после deadline не записывается.
- Транзакция не удерживается во время await агента/источников.
- Межпроцессное объединение ещё не принятых обращений к агенту не реализовано: production-запуск нескольких worker требует общей очереди и lease. SQLite всё равно защищает единственный commit принятия.

Основная проверка связи: `tests/test_module_connections.py`, включая вызов обоих
поставщиков через агента и BFF с последующим чтением Trip. Single-instance
runtime теперь сохраняет `run_id`, queued/processing/terminal стадии, диалог
уточнений и восстановление processing-run после рестарта. Общая очередь и lease
для нескольких процессов по-прежнему требуют отдельной инфраструктуры.

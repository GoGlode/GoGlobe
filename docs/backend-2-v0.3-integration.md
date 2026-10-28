# AI-агент и API v0.3: различия, интерфейс интеграции, блокеры

**Роль:** Backend №2 — AI-агент · **Ветка:** `dev/backend-2` · **Дата:** 28.10.2026
**Основание:** чек-лист от 26.10.2026, пункт 6 «Подготовить AI-агента к новому API-контракту».
**Источник контракта:** `docs/api/v0.3/` (`GoGlobe_openapi_v0.3.json`, `GoGlobe_examples_v0.3.json`, `README.md`), забран из `origin/dev/backend-1`.

> Документ **не меняет** общий контракт. Всё, что ниже помечено «предложение», требует согласования с Backend №1 и Frontend №1.

---

## 1. Что есть сейчас (v0)

| Элемент | Текущая реализация |
|---|---|
| Транспорт | `POST /api/search` (синхронный, ответ сразу с офферами) |
| Статусы | `ok`, `needs_clarification`, `partial`, `empty`, `error` |
| Прогресс | `GET /api/search/{id}/events` → `{stage, message}`, 7 стадий |
| Результат | `SearchResponse{search_id, status, parsed, clarifying_question, offers[], warnings[]}` |
| Деньги | `Money{amount: float, currency: "RUB"}` |
| Оффер | `hotel`, `flight`, `total_price`, `explanation`, `booking_url`, `data_freshness`, `score` |
| Уточнение | одна строка `clarifying_question`, без идентификатора ответа |
| Идентификаторы | `search_id` (12 hex), без сессии, `trip_id`, `revision` |

## 2. Что требует v0.3

| Элемент | v0.3 |
|---|---|
| Базовый путь | `/api/v1`, все ответы `Cache-Control: no-store` |
| Сессия | `POST/DELETE /session`, `POST /session/restore`, `POST/DELETE /recovery-key` |
| Запуск | `POST /searches` + `Idempotency-Key` (uuid) + `Origin`; ответ `202 Accepted{search_id, trip_id, state, revision, expires_at}` |
| Чтение | `GET /searches/{search_id}` (Snapshot) и `GET /searches/{search_id}/events` (SSE с `id`, `event`, `data=Snapshot`) |
| Статусы | `queued`, `processing`, `needs_clarification`, `completed`, `failed`, `cancelled` + `result_status` ∈ `ok/partial/empty` |
| Этапы | `parsing`, `itinerary`, `quotes`, `validating` |
| Уточнение | `Question{question_id, field, message}`; ответ `POST /searches/{id}/clarifications` c `Answer{question_id, expected_revision, answer}` |
| Программа | `Itinerary{days:[{day_index, date, items:[…]}]}`, у каждого пункта `verification: suggested/verified/unknown` и `source_ids` |
| Компоненты | `Components{itinerary, hotels, flights}` со состояниями `not_requested/blocked/queued/processing/ready/empty/failed`, `missing_fields`, `incomplete` |
| Деньги | `Money{amount_minor:int, currency:"RUB"}`, `Price{status: unknown/estimated/quoted, basis, coverage, exclusions, stale, source_ids}` |
| Предупреждения | `Warning{code, message, trip_id}` (не строки) |
| Ошибки | `Error{code, message, retryable, details[]}` |
| Источники | `Source{source_id, name, url, checked_at, kind}` |
| Поездка | `trip_id` + `trip_revision`, отдельная от `search_id`/`revision` |
| Отмена | `PUT /searches/{id}/cancellation` |

## 3. Различия построчно (что должен изменить агент)

| # | Сейчас | v0.3 | Что делать агенту | Готово? |
|---|---|---|---|---|
| 1 | `POST /api/search` синхронно | `202` + Snapshot/SSE | разделить «принять задачу» и «выдать результат»: агент возвращает `AgentRunResult`, HTTP-слой Backend №1 решает, когда писать Snapshot | частично: пайплайн уже пошаговый, `run_search` отдаёт финальный объект |
| 2 | `search_id` 12 hex, генерируется в API | `search_id` + `trip_id` + `revision` | агент не должен генерировать id — принимает снаружи и возвращает как есть | ❌ нужно поменять сигнатуру |
| 3 | 7 стадий с `message` | 4 этапа + состояния задачи | маппинг стадий (таблица §4) | ❌ |
| 4 | `status` в ответе | `state` + `result_status` | вернуть пару: состояние задачи и качество результата | ❌ |
| 5 | `clarifying_question: str` | `Question{question_id, field, message}` + `Answer` | генерировать `question_id`, поле (`destination`/`duration_days`/`conflict`), принимать ответ и продолжать | ❌ (сейчас только строка) |
| 6 | `warnings: list[str]` | `Warning{code,message,trip_id}` | ввести коды (`LLM_FALLBACK`, `PROVIDER_PARTIAL`, `CURRENCY_CONVERTED`, `NO_DIRECT_FLIGHTS`, `DESTINATION_REFERENCE`, `EMPTY_RESULT`) | ❌ |
| 7 | `Money.amount: float`, RUB | `amount_minor:int`, только RUB | конвертировать в копейки; валюту вне RUB не отдавать наружу (внутри считать можно) | ❌ |
| 8 | `Offer.total_price` всегда | `Price.status` ∈ `unknown/estimated/quoted` | не отдавать `quoted` без источника; пересчёт по демо-курсу = `estimated` | частично: логика есть, поля нет |
| 9 | офферы `hotel/flight` | `Itinerary` + `Components` + `HotelList/FlightList` | добавить сборку `Itinerary` (дни, пункты, `suggested/verified`, `source_ids`) — зона Backend №2 | ❌ |
| 10 | `explanation` | нет (объяснение ушло в `Itinerary`/`Price.note`) | сохранить как внутренний объект, наружу — через `Price.note`/`Warning` | частично |
| 11 | без сессии | cookie-сессия, `Origin`, `Idempotency-Key` | не трогать: зона Backend №1 | — |
| 12 | «сразу всё» | `requested_components` | уважать запрошенный объём (`itinerary`/`hotels`/`flights`) и не считать `blocked` ошибкой | ❌ |

## 4. Предлагаемый интерфейс агента для Backend №1

Агент остаётся библиотекой в процессе Backend №1, без собственного HTTP. Интерфейс ниже — предложение; **модели и маппинг уже реализованы** в [`backend/app/agent/v03.py`](../backend/app/agent/v03.py) и покрыты тестами (см. §6).

```python
# backend/app/agent/service.py (предложение; v03.py уже даёт модели и маппинг)
@dataclass
class AgentRunRequest:
    run_id: str                 # id попытки, не search_id
    search_id: str
    trip_id: str
    revision: int
    query: str
    params: ParamsV03 | None    # destination, duration_days, dates, origin,
                                # travelers{adults, children_ages}, budget, wishes
    requested_components: list[Literal["itinerary", "hotels", "flights"]]

@dataclass
class AgentEvent:
    stage: Literal["parsing", "itinerary", "quotes", "validating"]
    revision: int
    message: str

@dataclass
class AgentRunResult:
    state: Literal["needs_clarification", "completed", "failed", "cancelled"]
    result_status: Literal["ok", "partial", "empty"] | None
    parsed: ParsedQuery                # внутренняя модель, наружу не уходит
    itinerary: Itinerary | None
    hotels: HotelList | None
    flights: FlightList | None
    question: Question | None
    warnings: list[Warning]            # с кодами
    price_status: Literal["unknown", "estimated", "quoted"]
    sources: list[Source]

class SearchAgent(Protocol):
    async def run(self, req: AgentRunRequest, emit: Callable[[AgentEvent], Awaitable[None]]) -> AgentRunResult: ...
    async def resume(self, req: AgentRunRequest, answer: Answer) -> AgentRunResult: ...
    async def cancel(self, search_id: str) -> None: ...
```

Правила, которые агент обязуется соблюдать:

1. Не генерирует `search_id`, `trip_id`, `revision` и `question_id` самостоятельно — получает их от Backend №1 (или возвращает `question_id`, выданный хостом).
2. Не пишет в хранилище и не отдаёт HTTP — только события через `emit` и итоговый `AgentRunResult`.
3. `blocked` компонент — не ошибка: `state=completed`, `result_status=partial`, в `Components` указывается `missing_fields`.
4. `Price.status=quoted` только при наличии `source_ids` и `checked_at` от провайдера; иначе `estimated` (пересчёт) или `unknown`.
5. Поздний результат после `cancel`/таймаута отбрасывается по `run_id` (проверка на стороне хоста, агент передаёт `run_id` в каждом событии).

### Маппинг стадий v0 → v0.3

| v0 (`stage`) | v0.3 (`stage`) | Комментарий |
|---|---|---|
| `parsing` | `parsing` | разбор запроса, вопрос пользователю |
| `flights` | `quotes` | поиск перелётов — часть этапа тарифов |
| `hotels` | `quotes` | поиск отелей — часть этапа тарифов |
| `validating` | `validating` | проверка бюджета/составов |
| `ranking` | — | внутри `validating`/`itinerary`; отдельного этапа в v0.3 нет |
| `done` | — | терминальное событие SSE v0.3 (`event: finished`, `data: Snapshot`) |
| `error` | — | `state=failed` + `Error` в Snapshot |

### Уточняющие вопросы (закрывает замечание Frontend №1)

Frontend №1 сообщил: «вопросы показываются текстом с полем ответа, потому что схемы вариантов от BE2 нет». Предложение для согласования:

```json
{
  "question_id": "q_7f3a",
  "field": "destination",
  "message": "Куда именно вы хотите поехать?",
  "options": [
    {"value": "Турция", "label": "Турция"},
    {"value": "Египет", "label": "Египет"},
    {"value": "ОАЭ", "label": "ОАЭ"}
  ],
  "answer_type": "single_choice",
  "allow_free_text": true
}
```

`options`/`answer_type`/`allow_free_text` в v0.3 **нет** — это расширение контракта. Без него Frontend продолжает показывать свободный ввод (`Answer.answer: string`), и это корректно: `Question.field` уже позволяет отрисовать подсказку. Решение — за Backend №1 и Frontend №1.

## 5. Что нужно от Backend №1 (блокеры)

| # | Блокер | Почему без него нельзя |
|---|---|---|
| B1 | Реализация `/api/v1/searches` (202 + Snapshot/SSE) | агент не может отдавать `trip_id`, `revision`, `state` — их создаёт хост |
| B2 | Cookie-сессия, `Origin`, `Idempotency-Key`, коды 401/409/410 | вне зоны агента; без staging нельзя проверить фронт |
| B3 | Провайдеры отелей/перелётов и destination-провайдер | у агента только `Protocol` и моки; реальные `Source`, `Price.status`, `available` неоткуда взять |
| B4 | Единицы денег: `amount_minor` и только RUB | сейчас `Money.amount: float` в рублях; переход затрагивает все офферы |
| B5 | Схема `Itinerary`/`Item` (кто заполняет `place`, `local_time`, `verification`) | зона Backend №2 по README, но нужен согласованный минимум полей от провайдеров |
| B6 | Коды `Warning` (список и владелец) | иначе фронт не сможет различать «нет прямых» и «провайдер упал» |
| B7 | Правило `run_id` при cancel/timeout | иначе поздний результат перезапишет отменённую задачу |

## 6. Что уже готово к интеграции

- **Адаптер v0.3** — [`backend/app/agent/v03.py`](../backend/app/agent/v03.py): модели `Snapshot`, `Components`, `HotelList`, `HotelOffer`, `Price`, `Question`, `Warning`, `Params`, `Accepted`; функции `params_from_parsed`, `parsed_from_params`, `snapshot_from`, `warnings_from`, `question_from`, `warning_code`.
  - деньги переводятся в `amount_minor` (копейки), валюта — только RUB, сумма в USD/EUR пересчитывается, а не переименовывается;
  - статусы `ok/partial/empty/needs_clarification/error` → `state` + `result_status`;
  - `question_id` стабилен (хеш текста вопроса), `field` выводится из текста;
  - предупреждения получают коды: `LLM_FALLBACK`, `NO_DIRECT_FLIGHTS`, `CURRENCY_CONVERTED`, `PROVIDER_PARTIAL`, `PROVIDERS_EMPTY`, `AVAILABILITY_UNKNOWN`, `EMPTY_RESULT`, `AGENT_WARNING`;
  - `Price.status="estimated"` всегда с `note`, `source_ids`, `checked_at`; `quoted` без источника не выставляется;
  - **`flights` всегда `blocked` с `missing_fields=["segments"]`** — в контракте провайдера нет сегментов (B3), выдумывать рейсы нельзя;
  - `availability="unknown"`, потому что `Offer` не несёт подтверждённого наличия.
- Разбор запроса и уточняющие вопросы (`parser.py`) — переносится без изменений.
- План поиска и вызовы инструментов (`tools.py`) — стадии маппятся на v0.3 (§4).
- Ограничения: строгий прямой рейс, валюта, бюджет (`orchestrator.py`, `validation.py`, `currency.py`).
- Ранжирование и объяснения (`ranking.py`, `explain.py`) — остаются внутренними, наружу идут `Price.note`/`Warning`.
- Тесты: **121** (81 основных + 40 тестов адаптера, включая сверку полей моделей со схемами OpenAPI v0.3).

## 7. Порядок интеграции (предложение)

1. Backend №1 фиксирует `AgentRunRequest/AgentRunResult` и коды `Warning`.
2. Backend №2 добавляет тонкий `service.py` поверх готового `v03.py` (сейчас есть модели и маппинг).
3. Backend №1 подключает адаптер к `POST /searches` и Snapshot; v0 остаётся для демо до переключения фронта.
4. Совместный прогон 8 сценариев из чек-листа на staging с реальными провайдерами.
5. Только после этого — удаление v0-роутов и `frontend/src/api/types.ts` v0.

## 8. Ответ на статус Frontend №1 (28.10.2026)

Frontend №1 сообщил: «DeepSeek не подключён — в контракте v0.3 нет intent/preview», «вопросы показываются текстом, потому что схемы вариантов от BE2 нет». Что это значит для нас:

| Вопрос Frontend №1 | Ответ Backend №2 |
|---|---|
| Нет `intent`/`preview` | Отдельный preview не нужен: `POST /searches` уже принимает `query` и после `202` отдаёт `needs_clarification` + `Question` либо `processing`. Если preview нужен до создания задачи — это **новый** эндпоинт, только по согласованию с Backend №1 |
| Нет схемы вариантов ответа на вопрос | `Question.field` (`destination`/`duration_days`/`conflict`) уже есть в v0.3 и позволяет отрисовать подсказку. `options` — предложение (§4), не менять контракт без согласования |
| CORS/cookie Vercel↔API | Зона Backend №1 (B2). Агент не участвует в CORS и не читает cookie |
| 401/409/410 | Зона Backend №1 (B2). Агент возвращает только `state/result_status`; HTTP-коды ставит хост |
| История/♥/«Отели» на localStorage | Зона Frontend, к AI-агенту отношения не имеет |

**Что это меняет для Backend №2:** ничего в коде до согласования. После фиксации `AgentRunRequest/AgentRunResult` (B1, B6) агент сможет отдавать `Question` и `Warning` в формате v0.3, и фронту не придётся показывать вопросы «голым текстом».

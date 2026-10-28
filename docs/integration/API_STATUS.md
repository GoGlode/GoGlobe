# GoGlobe API implementation status

Актуально для локального runtime на 28.10.2026. Источник контракта v0.3 —
`docs/api/v0.3/GoGlobe_openapi_v0.3.json`; фактическая реализация определяется
обработчиками `app/bff.py`, а не одним наличием маршрута в OpenAPI.
Все пути в матрице указаны относительно базового префикса `/api/v1`.

Статусы:

- `demo` — операция выполняется локальным BFF и проверяется тестом, но ещё не
  является подтверждённой production-интеграцией;
- `scaffold` — маршрут зарегистрирован, однако отвечает `501 NOT_IMPLEMENTED`;
- `fallback` — аддитивное расширение реализовано в runtime как безопасный
  deterministic fallback без внешнего LLM-вызова.

## Матрица v0.3

| # | Method | Path | Request / response schema | Status | Runtime handler | Existing verification | Responsible |
|---:|---|---|---|---|---|---|---|
| 1 | POST | `/session` | `Empty` → `Session` | demo | `post_session` | `tests/test_bff.py`, `tests/test_public_api_contract_audit.py` | BE1 |
| 2 | DELETE | `/session` | — → 204 | demo | `delete_session` | `tests/test_bff.py`, `tests/test_public_api_contract_audit.py` | BE1 |
| 3 | POST | `/session/restore` | `RestoreRequest` → `Session` | scaffold | `post_session_restore` | scaffold/501 coverage in `tests/test_bff.py` | BE1 |
| 4 | POST | `/recovery-key` | `Empty` → `RecoveryReceipt` | scaffold | `post_recovery_key` | scaffold/501 coverage in `tests/test_bff.py` | BE1 |
| 5 | DELETE | `/recovery-key` | — → 204 | scaffold | `delete_recovery_key` | scaffold/501 coverage in `tests/test_bff.py` | BE1 |
| 6 | POST | `/searches` | `PlanRequest` → `Accepted` | demo | `post_searches` | `tests/test_bff.py`, `tests/test_public_api_contract_audit.py` | BE1 + BE2 |
| 7 | GET | `/searches/{search_id}` | — → `Snapshot` | demo | `get_searches_search_id` | `tests/test_bff.py`, `tests/test_public_api_contract_audit.py` | BE1 |
| 8 | GET | `/searches/{search_id}/events` | — → SSE `Snapshot` | demo | `get_searches_search_id_events` | `tests/test_bff.py`, `tests/test_public_api_contract_audit.py` | BE1 |
| 9 | POST | `/searches/{search_id}/clarifications` | `Answer` → `Accepted` | demo | `post_searches_search_id_clarifications` | `tests/test_search_lifecycle.py`, `tests/test_public_api_contract_audit.py` | BE1 + BE2 |
| 10 | PUT | `/searches/{search_id}/cancellation` | `Empty` → `Snapshot` | demo | `put_searches_search_id_cancellation` | `tests/test_search_lifecycle.py`, `tests/test_public_api_contract_audit.py` | BE1 |
| 11 | GET | `/trips/{trip_id}` | — → `Trip` | demo | `get_trips_trip_id` | `tests/test_bff.py`, `tests/test_public_api_contract_audit.py` | BE1 |
| 12 | DELETE | `/trips/{trip_id}` | — → 204 | scaffold | `delete_trips_trip_id` | scaffold/501 coverage in `tests/test_bff.py` | BE1 |
| 13 | PUT | `/trips/{trip_id}/saved` | `Empty` → `TripFlags` | demo | `put_trips_trip_id_saved` | `tests/test_bff.py`, `tests/test_public_api_contract_audit.py` | BE1 |
| 14 | DELETE | `/trips/{trip_id}/saved` | — → 204 | demo | `delete_trips_trip_id_saved` | `tests/test_bff.py`, `tests/test_public_api_contract_audit.py` | BE1 |
| 15 | PUT | `/trips/{trip_id}/schedule` | `ScheduleRequest` → `Trip` | demo | `put_trips_trip_id_schedule` | `tests/test_bff.py`, `tests/test_public_api_contract_audit.py` | BE1 |
| 16 | GET | `/trips` | query → `TripList` | demo | `get_trips` | `tests/test_bff.py`, `tests/test_public_api_contract_audit.py` | BE1 |
| 17 | GET | `/trips/{trip_id}/hotels` | — → `HotelList` | demo | `get_trips_trip_id_hotels` | `tests/test_quote_flow.py`, `tests/test_public_api_contract_audit.py` | BE1 + BE2 scoring |
| 18 | GET | `/trips/{trip_id}/flights` | — → `FlightList` | demo | `get_trips_trip_id_flights` | `tests/test_quote_flow.py`, `tests/test_public_api_contract_audit.py` | BE1 + BE2 scoring |
| 19 | POST | `/trips/{trip_id}/quote-searches` | `QuoteRequest` → `Accepted` | demo | `post_trips_trip_id_quote_searches` | `tests/test_quote_flow.py`, `tests/test_public_api_contract_audit.py` | BE1 + BE2 scoring |
| 20 | GET | `/history` | query → `HistoryList` | scaffold | `get_history` | scaffold/501 coverage in `tests/test_bff.py` | BE1 |
| 21 | DELETE | `/history/{search_id}` | — → 204 | scaffold | `delete_history_search_id` | scaffold/501 coverage in `tests/test_bff.py` | BE1 |
| 22 | PUT | `/favorites/{trip_id}` | `Empty` → `TripFlags` | demo | `put_favorites_trip_id` | `tests/test_bff.py`, `tests/test_public_api_contract_audit.py` | BE1 |
| 23 | DELETE | `/favorites/{trip_id}` | — → 204 | demo | `delete_favorites_trip_id` | `tests/test_bff.py`, `tests/test_public_api_contract_audit.py` | BE1 |
| 24 | GET | `/favorites` | query → `TripList` | demo | `get_favorites` | `tests/test_bff.py`, `tests/test_public_api_contract_audit.py` | BE1 |
| 25 | POST | `/trips/{trip_id}/share` | `Empty` → `ShareReceipt` | scaffold | `post_trips_trip_id_share` | scaffold/501 coverage in `tests/test_bff.py` | BE1 |
| 26 | DELETE | `/trips/{trip_id}/share` | — → 204 | scaffold | `delete_trips_trip_id_share` | scaffold/501 coverage in `tests/test_bff.py` | BE1 |
| 27 | GET | `/shared/{token}` | — → `PublicTrip` | scaffold | `get_shared_token` | scaffold/501 coverage in `tests/test_bff.py` | BE1 |

Итого по v0.3: **18 demo**, **9 scaffold**. `demo` не означает завершённый
production endpoint: текущий runtime поддерживает clarification/cancellation и
persisted asynchronous snapshot quote flow с cancel/restart guards, но внешние
production-провайдеры и деплой этим статусом не подтверждаются.

## Аддитивное расширение v0.3.1

| Method | Path | Runtime schema | Status | Existing verification | Responsible |
|---|---|---|---|---|---|
| POST | `/intent/preview` | inline `IntentPreviewRequest` → `IntentPreviewResponse` | fallback | `tests/test_intent_preview.py`, `tests/test_intent_preview_api.py`, `tests/test_public_api_contract_audit.py` | BE1 + BE2 + FE1 |

`POST /intent/preview` добавлен в runtime OpenAPI как аддитивная операция v0.3.1
и возвращает валидированный deterministic fallback (`analysis_mode=fallback`).
Он не создаёт `Search`/`Trip`, не запускает quote providers и не передаёт
серверный LLM key во frontend. Канонический базовый контракт v0.3 при этом не
изменён. Versioned OpenAPI, examples и changelog v0.3.1 опубликованы рядом с
базовым комплектом; отдельный PDF-addendum потребуется только если команда
решит распространять расширение не в машиночитаемом виде.

## P0 gaps before acceptance

1. Внешняя durable queue/worker для одновременной работы нескольких API-
   экземпляров. Для текущего single-instance runtime уже сохраняются отдельные
   `run_id`, queued/processing/terminal состояния и вход задачи; POST немедленно
   возвращает `202`, cancel инвалидирует run, а незавершённый processing-run
   возобновляется после рестарта с guarded terminal commit.
2. Подключение подтверждённых production quote providers без скрытой demo/live
   подмены; текущий snapshot flow остаётся честным demo/fallback путём.
3. Реальный browser E2E после миграции FE1 с v0 `/api/search` на cookie-сессию
   и `/api/v1`. Render-конфигурация включает `SameSite=None; Secure` для
   раздельных HTTPS-доменов; фактический staging URL всё ещё нужно проверить в
   браузере после публикации сервиса.
4. Согласование v0.3.1 с frontend/BE2 и, если нужен печатный комплект,
   отдельный PDF-addendum для intent preview.

SSE single-instance runtime уже держит соединение до следующей revision,
отдаёт `snapshot`, затем `update` и `finished`, закрывается на terminal и при
reconnect сразу возвращает актуальный полный Snapshot.

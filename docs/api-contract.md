# API-контракт v0 — исторический мок-API

> Для дальнейшей разработки опубликована [целевая спецификация 0.3](api/README.md): [1_version_api.pdf](api/1_version_api.pdf), OpenAPI и полные моки. Этот файл описывает старый демонстрационный `/api/search`; публикация новой спецификации не изменяет работающий сервер автоматически.

Источник правды: `backend/app/schemas/search.py` (Pydantic). Зеркало: `frontend/src/api/types.ts`. Владелец: Backend №1.
Живая схема: `GET /openapi.json`, Swagger — `/docs`.

## POST /api/search
Запрос:
```json
{ "query": "5 дней в Турцию в ноябре, на двоих, до 120 000 ₽, отель у моря, прямой рейс",
  "params": { "dates": {"from":"2026-11-10","to":"2026-11-15"}, "budget": {"amount":120000,"currency":"RUB"},
              "travelers": 2, "wishes": ["sea_view","direct_flight"] },
  "search_id": "опционально, генерирует клиент" }
```
Ответ: `{ search_id, status, parsed, clarifying_question, offers[], warnings[] }`.

| status | Когда | UI |
|---|---|---|
| `ok` | есть варианты | карточки |
| `needs_clarification` | не хватает параметра | показать `clarifying_question` |
| `partial` | есть варианты, но часть данных/источников недоступна | карточки + `warnings` |
| `empty` | ничего не подошло | честное «пусто» + совет изменить параметры |
| `error` | сбой | ошибка + повтор |

## GET /api/search/{id}/events (SSE)
`data: {"stage":"parsing|flights|hotels|validating|ranking|done|error","message":"…"}`

## GET /api/search/{id}
Сохранённый результат (для шаринга по ссылке).

## Правила изменений
1. Объявить в общем чате. 2. Один PR с меткой `contract`: схема + `types.ts` + этот файл + тесты. 3. Ревью — Frontend и Backend №2.
Поля `sources`, `confidence`, `data_freshness`, `warnings` обязательны: они реализуют принцип «ИИ ничего не выдумывает».

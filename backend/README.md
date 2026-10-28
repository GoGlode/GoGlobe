# GoGlobe — Backend №1

Серверный каркас по контракту v0.3. По умолчанию работает **без фронтенда, AI и внешних API**. Основной сервер поддерживает заменяемый агент через `create_app(agent=..., tools=...)`; связь BFF → агент → инструменты → поставщики проверяется интеграционными тестами.

Текущий runtime реализует 15 операций базового v0.3 и аддитивный
`POST /api/v1/intent/preview` v0.3.1. Ещё 12 операций зарегистрированы как
явные заглушки `501 NOT_IMPLEMENTED`; актуальная матрица находится в
`../docs/integration/API_STATUS.md`.

Intent Preview допускает не более двух одновременно выполняемых запросов и
20 запросов в минуту на owner. При превышении возвращается `429
PREVIEW_RATE_LIMITED` с `Retry-After`.

## Запуск в PowerShell

Сначала перейдите в папку проекта:

```powershell
Set-Location -LiteralPath 'C:\Users\m1kor1\Documents\Goglobe mine\backend'
```

При первой установке из PowerShell:

```powershell
& '.\setup.cmd'
```

Скрипт сам переходит в папку проекта, создаёт `.venv`, восстанавливает `pip`, если окружение было создано без него, и устанавливает зафиксированные зависимости. Запуск:

```powershell
& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app
```

Также можно запустить `run.cmd` из проводника или PowerShell: он сам переходит в папку проекта. Если он сообщает, что окружение не найдено, сначала выполните `& '.\setup.cmd'`. Страницы документации по умолчанию отключены. Проверка сервера: http://127.0.0.1:8000/health. Остановка: Ctrl+C. При занятом порте остановите прежний сервер. Основные адреса — **`/api/v1`**; старый `/api/search` отсутствует.

## Рабочий путь без фронтенда

1. POST `/api/v1/session` с `{}` и разрешённым Origin. HTTP-клиент сохраняет cookie `gg_session`.
2. POST `/api/v1/searches` с новым UUID в Idempotency-Key, текстом и явными `params: {"destination":"Рим","duration_days":2}`.
3. Получить Snapshot по Location или через `/searches/{search_id}/events`, затем GET `/trips/{trip_id}`.
4. PUT `/trips/{trip_id}/saved` с `{}`, затем GET `/trips?saved=true`.
5. PUT `/trips/{trip_id}/schedule` с текущей **revision поездки**, двумя календарными датами включительно и `timezone: Europe/Rome`.

Примеры: `examples/search_v0.3.http`. Отдельная серверная проверка: `examples/smoke_v0.3.ps1`.

Резервный планировщик разбирает поддерживаемые направления и длительность из
свободного текста. Если направления или длительности нет, Search переходит в
`needs_clarification`; ответы продолжают тот же `trip_id`. Отсутствие дат,
origin, travelers и budget не мешает программе. Даты программы не подменяют
stay и flight_dates.

Короткая транзакция атомарно сохраняет draft Trip, queued Snapshot, Accepted и
отдельный `run_id`, после чего POST сразу возвращает `202`. План строится вне
транзакции; terminal commit разрешён только активному run. Cancel блокирует
позднюю запись, а queued/processing run возобновляется после рестарта процесса.
SSE остаётся открытым и отдаёт полный Snapshot событиями `snapshot`, `update` и
`finished`. Внешняя очередь с lease всё ещё нужна для нескольких экземпляров,
но single-instance lifecycle хранится в SQLite.

Маршрут создаётся с неизвестной ценой (`money: null`). Отдельный quote-search
принимает явные stay/origin/travelers/flight_dates и возвращает сохранённые
snapshot-списки отелей и рейсов. Они помечены как demo, не заявляют реальное
наличие и не содержат активных booking URL.

## Реализовано и отложено

| Операции | Поведение |
|---|---|
| POST/DELETE session | Owner, cookie, продление/отзыв сессии |
| POST searches | валидация, атомарное сохранение, идемпотентность |
| GET Snapshot и events | фиксированный завершённый результат и SSE |
| GET Trip | доступ только своему владельцу |
| PUT/DELETE saved | сохранение; повтор снятия не продлевает TTL |
| GET trips | saved, пересечение дат, пагинация |
| PUT schedule | проверка revision, длительности и обновление дат |

Остальные 12 операций помечены в OpenAPI как **ЗАГЛУШКА**: recovery/restore,
удаление Trip, history, Favorite и Share. Успешная проверка ответа 501 не
считается проверкой реализации соответствующей функции.

## Хранение и настройки

SQLite: `data/goglobe.sqlite3`, переменная `GOGLOBE_DB_PATH`. Файл не попадает в Git или Docker-образ. Приём задачи и исходного Accepted, запись Trip и повторы защищены транзакцией. Сохранённая поездка переживает перезапуск.

Сессия — 90 суток от POST session; Search/несохранённый Trip — 7 суток; saved Trip без TTL; идемпотентность searches — 24 часа. Истёкшие объекты недоступны, фоновая физическая очистка ещё не реализована.

Изменяющие запросы требуют Origin из allowlist. Cookie HttpOnly/SameSite=Lax,
Secure при HTTPS. По умолчанию разрешён `https://goglobe-demo.vercel.app` и
локальные origins; настройка `GOGLOBE_CORS_ORIGINS`.

Пример настроек: `.env.example`. Файл сам по себе не загружается: задайте переменные в PowerShell или установите python-dotenv и используйте --env-file. При неверной настройке процесс завершается до приёма HTTP-запросов; ошибка называет переменную, но не повторяет её значение.

| Настройка | По умолчанию | Допустимое значение |
|---|---:|---|
| `GOGLOBE_DB_PATH` | `data/goglobe.sqlite3` | непустой доступный путь к файлу SQLite |
| `GOGLOBE_CORS_ORIGINS` | goglobe-demo.vercel.app и локальные origins | непустой список HTTP(S) origin без path/query/fragment/credentials |
| `GOGLOBE_AGENT_TIMEOUT_SECONDS` | `20` | конечное число `> 0` и `<= 120`; общий срок планирования |
| `GOGLOBE_ENABLE_DOCS` | `false` | только `true`/`false`, регистр не важен |
| `GOGLOBE_CACHE_TTL_SECONDS` | `60` | конечное число `>= 0`; `0` отключает локальный кэш |
| `GOGLOBE_PROVIDER_TIMEOUT_SECONDS` | `8` | конечное число `> 0` и `<= 120`; срок одной попытки |
| `GOGLOBE_PROVIDER_MAX_ATTEMPTS` | `3` | целое `1..3`, включая первую попытку |
| `GOGLOBE_DEMO_FALLBACK` | `false` | только явное `true` включает резерв; `1`, `yes`, `on` и пустая строка ошибочны |

Общий срок агента и срок попытки поставщика независимы. Попытка всегда ограничена меньшим из своего таймаута и оставшегося общего бюджета. Документацию можно явно включить через `GOGLOBE_ENABLE_DOCS=true`; тогда доступны `/docs` и `/openapi.json`. Старые `GOGLOBE_MOCK_DELAY_SECONDS`, `GOGLOBE_MAX_SEARCHES` и `GOGLOBE_LEGACY_TIMEOUT_SECONDS` относятся только к раннему прототипу (соответственно `0..10`, целое `>=1`, и `>0..120`).

Docker с постоянным хранилищем:

```powershell
docker build -t goglobe-backend .
docker run --rm -p 8000:8000 -v goglobe-data:/app/data goglobe-backend
```

Без volume удаление контейнера удалит его БД. Контейнер слушает `PORT`, если
переменная задана платформой, и использует `8000` локально по умолчанию.

### Render

Минимальный Blueprint находится в `render.yaml`: бесплатный Docker-сервис,
проверка `/health` и отключённый автоматический деплой. Сам файл ничего не
публикует; импорт Blueprint и создание сервиса запускаются пользователем в
Render. SQLite хранится в эфемерном `/tmp`: данные сессий и поездок могут быть
потеряны при перезапуске, пересоздании экземпляра или новом деплое.

При создании Blueprint Render запросит единственную обязательную настройку:

- `GOGLOBE_CORS_ORIGINS` — фактический HTTP(S) origin фронтенда без пути,
  например `https://example.com`; несколько origin разделяются запятыми.

Blueprint сам задаёт `GOGLOBE_DB_PATH=/tmp/goglobe.sqlite3` и
`GOGLOBE_PROVIDERS=snapshot`. Переменную `PORT` выдаёт Render, добавлять её
вручную не нужно. Для snapshot-режима ключи и другие секреты не требуются.
Если сервис настраивается без Blueprint, обязательны `GOGLOBE_CORS_ORIGINS` и
`GOGLOBE_DB_PATH`; для бесплатного demo-режима используется путь в `/tmp`.
Остальные настройки имеют проверенные значения по умолчанию из таблицы выше.

Внешний multi-instance worker/lease, recovery-key и расширенные операции
остаются за рамками каркаса. Просроченные session/object/idempotency/input строки
физически очищаются при старте и создании сессии.

## Контракт и поставщики

- `app/contracts` — рабочие OpenAPI и fixtures v0.3, входят в Python-пакет.
- `../docs/api/v0.3` — PDF, базовый v0.3 и аддитивный bundle v0.3.1.
- `app/integrations/ports.py` — HotelProvider/FlightProvider, criteria, проверка ToolResult.
- `app/integrations/service.py` — взаимозаменяемые demo-поставщики, общий deadline, проверка контекста, изоляция ошибок, контроль ссылок/свежести.
- `app/planning.py` — Planner/AgentPlan/PlanContext и проверка результата агента до записи.
- `../docs/backend/agent-integration.md` — подключение будущего ИИ и поставщиков.
- `../docs/backend/provider-readiness.md` — требования и действия после выдачи API.

Адреса, авторизация и JSON поставщиков пока неизвестны. После документации потребуется реализовать Provider-интерфейсы; одной подстановки ключа недостаточно. BFF-контракт уже определён и от поставщика не зависит. Деньги v0.3 — RUB в целых **копейках** amount_minor.

## Проверки и отчёты

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q
```

Итог текущей реализации и аудита:
`../docs/backend/tz-be1-implementation-report-2026-10-28.md`.

Ранний прототип доступен отдельно через
`uvicorn app.legacy_api:create_app --factory --port 8001`; основная точка входа
`app.main:app` всегда создаёт API v0.3.1.

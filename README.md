# 🌍 GoGlobe

## Демонстрация GoGlobe

- [Сайт](https://goglobe-backend-d89q.onrender.com/)
- [Backend health](https://goglobe-backend-d89q.onrender.com/health)
- Презентация: TODO — публичная ссылка
- Видеообзор: TODO — публичная ссылка

GoGlobe — AI-помощник для планирования поездок. Пользователь описывает путешествие обычным языком, получает понятный маршрут, уточняющие вопросы и может сохранить поездку.

## Возможности

- Разбор запроса и персональные уточняющие вопросы с безопасным fallback.
- Маршрут по дням, сохранение поездок и установка дат.
- SSE-статусы поиска, идемпотентные операции и cookie-сессии.
- Честная маркировка snapshot/demo-данных: цены, наличие и подтверждения не выдумываются.

## Стек

React + TypeScript + Vite, FastAPI, PostgreSQL/Supabase в production; SQLite остаётся локальным fallback. Production разворачивается одним Render Docker-сервисом: frontend отдаётся FastAPI, API доступен по `/api/v1` на том же origin.

## Демонстрационный сценарий

Введите: **«Хочу в Рим на 2 дня»**. GoGlobe создаст поиск, построит двухдневный маршрут и откроет страницу поездки. Запрос «Хочу путешествие» демонстрирует уточнение недостающих параметров.

## Локальный запуск

Нужны Python 3.11+, Node 20+ и Docker (опционально).

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/uvicorn app.main:app --reload
```

В другом терминале:

```bash
cd frontend
npm ci
npm run dev
```

Проверки: `cd backend && .venv/bin/python -m pytest -q`; `cd frontend && npm run build`.

## Render deployment

`render.yaml` собирает единый Docker-образ из корня репозитория. Для production задайте через Render Environment: `DATABASE_URL`, `GOGLOBE_CORS_ORIGINS`, `GOGLOBE_PLANNER_MODE=agent`, `GOGLOBE_PROVIDERS=snapshot`, `GOGLOBE_INTENT_MODE=fallback` и `GOGLOBE_COOKIE_SAMESITE=lax`. Секреты и URL базы в репозиторий не добавляются. При выключенном auto-deploy deploy запускается вручную.

## Команда

- Кравцов Петр Сергеевич — backend №1
- Тарочкин Леонид Владимирович — backend №2
- Кустов Семён Максимович — frontend
- Семенов Илья Юрьевич — frontend support
- Старыш Тимофей Дмитриевич — тимлид, product-менеджер, fullstack

## Ограничения MVP

- Snapshot-провайдеры не являются подтверждёнными live-тарифами.
- Внешние коммерческие API не подключаются без серверной конфигурации и проверенного контракта.
- SQLite в `/tmp` не предназначена для production persistence; production использует PostgreSQL.
- Демо-ссылки на презентацию и видео будут добавлены после публикации материалов.

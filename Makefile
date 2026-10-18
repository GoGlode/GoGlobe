.PHONY: help setup dev backend frontend test lint
help:
	@echo "make setup    - установить зависимости backend и frontend"
	@echo "make dev      - запустить backend (:8000) и frontend (:5173)"
	@echo "make test     - тесты backend + сборка frontend"
	@echo "make lint     - ruff + tsc"

setup:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd frontend && npm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

dev:
	$(MAKE) -j2 backend frontend

test:
	cd backend && .venv/bin/pytest -q
	cd frontend && npm run build

lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && npx tsc --noEmit

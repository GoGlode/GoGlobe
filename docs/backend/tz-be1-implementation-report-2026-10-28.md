# GoGlobe BE1 — implementation and audit report

Date: 2026-10-28 (Europe/Moscow)

## Delivered in this workspace

- Added the v0.3.1 `POST /api/v1/intent/preview` contract, fixtures and
  deterministic fallback implementation. Preview is session/Origin protected,
  bounded to 64 KiB and two concurrent calls per owner, returns at most three
  validated questions and never creates a Search or Trip.
- Extended the fallback planner to parse supported destinations and trip
  duration from free text. Missing core fields create a persisted
  `needs_clarification` Snapshot instead of a terminal validation error.
- Implemented clarification continuation with revision/question guards,
  idempotency and the same `trip_id`; implemented search cancellation.
- SSE now returns `snapshot` for a non-terminal search and `finished` for a
  terminal Snapshot.
- Connected the existing resilient provider layer and local snapshots to
  quote-search, HotelList and FlightList endpoints. Quote inputs are explicit,
  errors identify the missing field, results are persisted separately from the
  itinerary and demo offers do not claim live availability or booking URLs.
- Made an exact schedule retry idempotent and aligned the default production
  frontend CORS allowlist with `.env.example`.
- Added canonical v0.3 JSON copies, additive v0.3.1 OpenAPI/examples, changelog
  and an implementation-status matrix.

## Verification evidence

- Final full pytest regression from the monorepo `backend/` directory:
  `446 passed, 1 warning in 82.89s`.
- Focused critical-path regression: `17 passed`.
- Ruff: clean.
- `python -m compileall -q app`: clean.
- `pip check`: no broken requirements.
- HTTP process smoke: session → search → Snapshot → Trip → save → list →
  schedule → unsave → logout: PASS.
- A wheel was built locally; packaged contracts and all six snapshot JSON files
  were verified inside it. CI dev dependencies now include Ruff explicitly.
- v0.3.1 packaged/documented OpenAPI SHA-256 files match; v0.3.1 example files
  match.
- Secret-pattern scan found only deliberate fake values in tests.

## Honest remaining constraints

- A local integration branch based on current `origin/main` places the runtime
  under `backend/` without modifying `frontend/`. It has not been pushed because
  the external publication approval was rejected for the large previously
  untracked source bundle.
- No GitHub PR/CI or production browser deployment was created in this run.
- Docker and npm are not installed on this machine, so the Dockerfile and
  frontend production build could not be executed locally. Backend tests and
  static checks passed in the actual monorepo layout.
- The checked-in `frontend/src/api/client.ts` still targets the obsolete v0
  `/api/search` DTO. The task explicitly assigns that file to FE1, so this
  backend branch does not modify it; a real browser E2E requires FE1 to adopt
  the v0.3.1 session and `/api/v1` contract.
- Planning remains an in-process adapter. It has persisted lifecycle states,
  clarification guards and deadlines, but not a durable external queue/run
  worker for multi-instance deployment.
- Intent preview currently uses the required safe fallback path; no DeepSeek
  key or agreed BE2 LLM response contract was available.
- Twelve v0.3 P1/P2 operations remain explicit 501 scaffolds: recovery/restore,
  Trip deletion, history, favorites and share.
- `render.yaml` uses ephemeral `/tmp` SQLite and therefore must not be described
  as durable production storage.

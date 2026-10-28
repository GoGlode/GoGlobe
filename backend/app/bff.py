"""BFF v0.3: persistent core demo, explicit scaffolds for later operations."""
import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
from collections import deque
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from math import ceil
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from starlette.exceptions import HTTPException

from app.contracts import examples, specification, validate
from app.config import env_bool, env_float, env_origins
from app.database import Database, put
from app.integrations.ports import FlightCriteria, HotelCriteria
from app.integrations.service import IntegrationTools
from app.intent_preview import preview_intent
from app.planning import NeedsClarification, Planner, PlanningService, UnsupportedDemo, validate_timezone

IMPLEMENTED = {
    "post_session", "delete_session", "post_searches", "get_searches_search_id",
    "get_searches_search_id_events", "get_trips_trip_id", "put_trips_trip_id_saved",
    "delete_trips_trip_id_saved", "get_trips", "put_trips_trip_id_schedule",
    "post_trips_trip_id_quote_searches", "get_trips_trip_id_hotels",
    "get_trips_trip_id_flights", "post_intent_preview",
    "post_searches_search_id_clarifications",
    "put_searches_search_id_cancellation",
}

PREVIEW_RATE_PER_MINUTE = 20
PREVIEW_OWNER_BUCKETS = 4096


def now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None, headers=None):
        self.status, self.code, self.message = status, code, message
        self.retryable = status in {429, 503}
        self.details = list(details or [])
        self.headers = dict(headers or {})


def trim(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [trim(item) for item in value]
    if isinstance(value, dict):
        return {key: trim(item) for key, item in value.items()}
    return value


def reject_json_constant(value):
    raise json.JSONDecodeError("Non-standard JSON number", value, 0)


def unique_json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise json.JSONDecodeError("Duplicate JSON key", key, 0)
        value[key] = item
    return value


def create_app(db_path: str | None = None, *, agent: Planner | None = None,
               tools: IntegrationTools | None = None, agent_timeout: float | None = None) -> FastAPI:
    timeout = agent_timeout if agent_timeout is not None else env_float(
        "GOGLOBE_AGENT_TIMEOUT_SECONDS", "20", minimum=0, maximum=120,
        minimum_inclusive=False,
    )
    if agent_timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                                      or not 0 < timeout <= 120):
        raise ValueError("GOGLOBE_AGENT_TIMEOUT_SECONDS must be between 0 and 120")
    origins = env_origins(
        "GOGLOBE_CORS_ORIGINS",
        "https://goglobe-demo.vercel.app,http://localhost:3000,http://localhost:5173,http://localhost:8000,http://127.0.0.1:8000",
    )
    enable_docs = env_bool("GOGLOBE_ENABLE_DOCS", "false")
    planning = PlanningService(agent, tools)
    configured_db_path = db_path if db_path is not None else os.getenv(
        "GOGLOBE_DB_PATH", "data/goglobe.sqlite3"
    )
    if not str(configured_db_path):
        raise ValueError("GOGLOBE_DB_PATH must not be empty")
    try:
        database = Database(configured_db_path)
    except (OSError, sqlite3.Error, ValueError):
        raise ValueError("GOGLOBE_DB_PATH cannot be initialized") from None
    planning_slots = asyncio.Semaphore(16)
    planning_locks = {}
    preview_slots = {}
    preview_windows: dict[str, deque[float]] = {}
    preview_rate_lock = asyncio.Lock()
    app = FastAPI(title="GoGlobe API", version="0.3.1", docs_url="/docs" if enable_docs else None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "DELETE"],
                       allow_headers=["Content-Type", "Idempotency-Key", "Last-Event-ID"],
                       expose_headers=["Location", "X-Request-ID", "Retry-After"])

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        body = {"error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable, "details": exc.details},
                "request_id": request.state.request_id}
        validate("ErrorResponse", body)
        return JSONResponse(body, status_code=exc.status, headers=exc.headers)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        response = await api_error(request, ApiError(exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail)))
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logging.getLogger("goglobe").error(
            "Internal request failure request_id=%s error_type=%s",
            request.state.request_id, type(exc).__name__,
        )
        response = await api_error(request, ApiError(500, "INTERNAL_ERROR", "Внутренняя ошибка сервера"))
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        if request.headers.get("origin") in origins:
            response.headers["Access-Control-Allow-Origin"] = request.headers["origin"]
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"
        return response

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request: Request, exc: sqlite3.OperationalError):
        busy = getattr(exc, "sqlite_errorcode", None) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
        logging.getLogger("goglobe").warning(
            "Storage failure request_id=%s sqlite_code=%s",
            request.state.request_id, getattr(exc, "sqlite_errorcode", None),
        )
        return await api_error(request, ApiError(503 if busy else 500, "STORAGE_BUSY" if busy else "STORAGE_ERROR", "Хранилище временно недоступно"))

    def get_object(db, kind, object_id, owner):
        row = db.execute("SELECT * FROM objects WHERE kind=? AND id=? AND owner=?", (kind, object_id, owner)).fetchone()
        if row is None or (row["expires"] is not None and row["expires"] <= stamp(now())):
            raise ApiError(404, "NOT_FOUND", "Ресурс не найден")
        return json.loads(row["payload"])

    def owner_for(db, request):
        token = request.cookies.get("gg_session", "")
        row = db.execute("SELECT owner FROM sessions WHERE token_hash=? AND expires>?", (digest(token), stamp(now()))).fetchone()
        return row["owner"] if row else None

    def success(schema, body, status=200, location=None):
        validate(schema, body)
        return JSONResponse(body, status_code=status, headers={"Location": location} if location else {})

    def card(trip):
        value = {key: deepcopy(trip[key]) for key in (
            "trip_id", "revision", "title", "duration_days", "price_summary", "saved_at", "favorite_at", "expires_at")}
        value.update(destination_name=trip["destination"]["name"], cover_url=None,
                     start_date=trip["schedule"]["start_date"], end_date=trip["schedule"]["end_date"])
        return value

    def build_demo(body, plan):
        params = body.get("params", {})
        if params.get("travelers") and params["travelers"]["adults"] + len(params["travelers"]["children_ages"]) > 9:
            raise ApiError(422, "VALIDATION_ERROR", "Максимум 9 путешественников")
        trip = deepcopy(examples()["trip_relative"]["value"])
        trip.update(destination=deepcopy(plan.destination), duration_days=plan.duration_days,
                    itinerary=deepcopy(plan.itinerary), sources=deepcopy(plan.sources), data_mode=plan.data_mode,
                    title=plan.destination["name"], description="Программа поездки; тарифы не запрашивались.")
        trip["schedule"] = {"start_date": None, "end_date": None, "timezone": plan.destination["timezone"]}
        current = now()
        expiry = stamp(current + timedelta(days=7))
        trip.update(trip_id="t_" + uuid4().hex, created_at=stamp(current), updated_at=stamp(current), expires_at=expiry)
        for key in ["origin", "travelers", "budget", "wishes"]:
            if key in params:
                trip[key] = deepcopy(params[key])
        trip["components"]["hotels"]["missing_fields"] = (["travelers"] if trip["travelers"] is None else []) + ["stay"]
        trip["components"]["flights"]["missing_fields"] = (["origin"] if trip["origin"] is None else []) + (["travelers"] if trip["travelers"] is None else []) + ["flight_dates"]
        if "dates" in params:
            assign_dates(trip, params["dates"]["start_date"], params["dates"]["end_date"], plan.destination["timezone"])
        snapshot = deepcopy(examples()["completed_partial"]["value"])
        snapshot.update(search_id="s_" + uuid4().hex, trip_id=trip["trip_id"], trip_revision=trip["revision"],
                        components=deepcopy(trip["components"]), created_at=stamp(current), updated_at=stamp(current), expires_at=expiry, data_mode=plan.data_mode)
        snapshot["warnings"] = deepcopy(plan.warnings)
        if plan.data_mode == "demo" and not any(
            warning.get("code") in {"DEMO_DATA", "DEMO_FALLBACK"}
            for warning in snapshot["warnings"]
        ):
            snapshot["warnings"].append({"code": "DEMO_DATA", "message": "Демонстрационная программа. Тарифы не запрашивались.", "trip_id": trip["trip_id"]})
        accepted = {"search_id": snapshot["search_id"], "trip_id": trip["trip_id"], "state": "queued", "revision": 1, "expires_at": expiry}
        return trip, snapshot, accepted

    def assign_dates(trip, start, end, zone):
        start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
        if (end_date - start_date).days + 1 != trip["duration_days"]:
            raise ApiError(422, "DURATION_CONFLICT", "Включительный период должен совпадать с длительностью программы")
        try:
            validate_timezone(zone)
        except ValueError:
            raise ApiError(422, "INVALID_TIMEZONE", "Неизвестная часовая зона IANA")
        if trip["destination"]["timezone"] is not None and zone != trip["destination"]["timezone"]:
            raise ApiError(422, "TIMEZONE_CONFLICT", "Зона не совпадает с часовым поясом направления")
        trip["schedule"] = {"start_date": start, "end_date": end, "timezone": zone}
        for index, day in enumerate(trip["itinerary"]["days"]):
            day["date"] = (start_date + timedelta(days=index)).isoformat()

    def quote_list(kind, trip, request_body, result):
        context = {"travelers": deepcopy(request_body["travelers"])}
        if kind == "hotels":
            context["stay"] = deepcopy(request_body["stay"])
            schema = "HotelList"
        else:
            context.update(origin=request_body["origin"],
                           flight_dates=deepcopy(request_body["flight_dates"]))
            schema = "FlightList"
        failed = result.status == "unavailable"
        state = "failed" if failed else "ready" if result.items else "empty"
        error = None
        if failed:
            code = next((item.get("code") for item in result.warnings if item.get("code")),
                        "PROVIDER_UNAVAILABLE")
            error = {"code": code, "message": "Источник тарифов временно недоступен.",
                     "retryable": code in {"PROVIDER_TIMEOUT", "PROVIDER_RATE_LIMITED", "PROVIDER_TRANSPORT_ERROR"},
                     "details": []}
        value = {
            "trip_id": trip["trip_id"], "trip_revision": trip["revision"],
            "state": state, "missing_fields": [],
            "items": deepcopy(result.items) if not failed else [],
            "sources": deepcopy(result.sources), "warnings": deepcopy(result.warnings),
            "error": error, "data_mode": result.data_mode, "context": context,
            "incomplete": result.status == "partial",
        }
        validate(schema, value)
        return value

    def blocked_quote_list(kind, trip):
        component = trip["components"][kind]
        schema = "HotelList" if kind == "hotels" else "FlightList"
        value = {
            "trip_id": trip["trip_id"], "trip_revision": trip["revision"],
            "state": "blocked", "missing_fields": deepcopy(component["missing_fields"]),
            "items": [], "sources": [], "warnings": [], "error": None,
            "data_mode": trip["data_mode"], "context": None, "incomplete": False,
        }
        validate(schema, value)
        return value

    def clarification_message(field):
        return ("Куда вы хотите поехать?" if field == "destination"
                else "На сколько дней планируется поездка?")

    def persist_clarification(owner, operation_id, key, fingerprint, body, field,
                              *, existing_trip=None, existing_snapshot=None):
        current = now()
        expiry = stamp(current + timedelta(days=7))
        if existing_trip is None:
            trip = deepcopy(examples()["trip_draft"]["value"])
            trip.update(
                trip_id="t_" + uuid4().hex, revision=1,
                destination={"name": body.get("params", {}).get("destination", "Не выбрано"),
                             "timezone": None, "photos": []},
                duration_days=body.get("params", {}).get("duration_days"),
                created_at=stamp(current), updated_at=stamp(current), expires_at=expiry,
            )
            snapshot = deepcopy(examples()["state_needs_clarification"]["value"])
            snapshot.update(
                search_id="s_" + uuid4().hex, trip_id=trip["trip_id"],
                trip_revision=trip["revision"], revision=2,
                created_at=stamp(current), updated_at=stamp(current), expires_at=expiry,
            )
        else:
            trip = deepcopy(existing_trip)
            snapshot = deepcopy(existing_snapshot)
            snapshot["revision"] += 1
            snapshot["updated_at"] = stamp(current)
        question = {"question_id": "q_" + uuid4().hex, "field": field,
                    "message": clarification_message(field)}
        snapshot.update(state="needs_clarification", stage=None, result_status=None,
                        clarification=question, error=None)
        validate("Trip", trip)
        validate("Snapshot", snapshot)
        accepted = {"search_id": snapshot["search_id"], "trip_id": trip["trip_id"],
                    "state": "queued",
                    "revision": 1 if existing_trip is None else snapshot["revision"],
                    "expires_at": expiry}
        with database.connect() as db:
            put(db, "trip", trip, owner)
            put(db, "search", snapshot, owner)
            db.execute(
                "INSERT OR REPLACE INTO search_inputs VALUES(?,?,?,?,?)",
                (snapshot["search_id"], owner, body["query"],
                 json.dumps(body.get("params", {}), ensure_ascii=False), expiry),
            )
            db.execute("INSERT OR REPLACE INTO idempotency VALUES(?,?,?,?,?,?)",
                       (owner, operation_id, key, fingerprint,
                        json.dumps(accepted), stamp(current + timedelta(hours=24))))
        return success("Accepted", accepted, 202,
                       f"/api/v1/searches/{snapshot['search_id']}")

    async def clarification_request(request, operation, body, query):
        key = request.headers["idempotency-key"]
        fingerprint = digest(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                        separators=(",", ":")))
        with database.connect() as db:
            owner = owner_for(db, request)
            if owner is None:
                raise ApiError(403, "SESSION_REQUIRED", "Требуется действующая сессия")
            replay = db.execute(
                "SELECT * FROM idempotency WHERE owner=? AND operation=? AND key=? AND expires>?",
                (owner, operation["operationId"], key, stamp(now())),
            ).fetchone()
            if replay:
                if replay["fingerprint"] != fingerprint:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим телом запроса")
                accepted = json.loads(replay["payload"])
                return success("Accepted", accepted, 202,
                               f"/api/v1/searches/{accepted['search_id']}")
            snapshot = get_object(db, "search", request.path_params["search_id"], owner)
            trip = get_object(db, "trip", snapshot["trip_id"], owner)
            row = db.execute(
                "SELECT query,params FROM search_inputs WHERE search_id=? AND owner=? AND expires>?",
                (snapshot["search_id"], owner, stamp(now())),
            ).fetchone()
        if snapshot["state"] != "needs_clarification" or snapshot["clarification"] is None or row is None:
            raise ApiError(409, "SEARCH_NOT_WAITING", "Поиск не ожидает уточнения")
        if snapshot["revision"] != body["expected_revision"]:
            raise ApiError(409, "REVISION_CONFLICT", "Состояние поиска изменилось")
        question = snapshot["clarification"]
        if question["question_id"] != body["question_id"]:
            raise ApiError(409, "QUESTION_CONFLICT", "Вопрос уже изменился")
        params = json.loads(row["params"])
        answer = body["answer"].strip()
        if question["field"] == "duration_days":
            words = {"один": 1, "два": 2, "две": 2, "три": 3, "четыре": 4,
                     "пять": 5, "шесть": 6, "семь": 7, "восемь": 8,
                     "девять": 9, "десять": 10}
            match = re.search(r"\b([1-9]|[12][0-9]|30)\b", answer)
            duration = int(match.group(1)) if match else next(
                (value for word, value in words.items() if word in answer.casefold()), None)
            if duration is None:
                raise ApiError(422, "INVALID_CLARIFICATION", "Укажите длительность от 1 до 30 дней")
            params["duration_days"] = duration
        else:
            params["destination"] = answer
        request_body = {"query": row["query"], "params": params}
        try:
            result = await planning.plan(request_body, now() + timedelta(seconds=timeout))
        except NeedsClarification as exc:
            return persist_clarification(
                owner, operation["operationId"], key, fingerprint, request_body,
                exc.field, existing_trip=trip, existing_snapshot=snapshot,
            )
        except (ValueError, ValidationError, TypeError, AttributeError):
            raise ApiError(502, "AGENT_INVALID_RESPONSE", "Ответ агента не соответствует контракту")
        completed_trip, completed_snapshot, _ = build_demo(request_body, result)
        completed_trip.update(
            trip_id=trip["trip_id"], revision=trip["revision"] + 1,
            created_at=trip["created_at"], saved_at=trip["saved_at"],
            favorite_at=trip["favorite_at"],
        )
        completed_snapshot.update(
            search_id=snapshot["search_id"], trip_id=trip["trip_id"],
            trip_revision=completed_trip["revision"], revision=snapshot["revision"] + 1,
            created_at=snapshot["created_at"],
        )
        validate("Trip", completed_trip)
        validate("Snapshot", completed_snapshot)
        accepted = {"search_id": snapshot["search_id"], "trip_id": trip["trip_id"],
                    "state": "processing", "revision": completed_snapshot["revision"],
                    "expires_at": completed_snapshot["expires_at"]}
        with database.connect() as db:
            latest = get_object(db, "search", snapshot["search_id"], owner)
            if latest["revision"] != snapshot["revision"]:
                raise ApiError(409, "REVISION_CONFLICT", "Состояние поиска изменилось")
            put(db, "trip", completed_trip, owner)
            put(db, "search", completed_snapshot, owner)
            db.execute("DELETE FROM search_inputs WHERE search_id=? AND owner=?",
                       (snapshot["search_id"], owner))
            db.execute("INSERT OR REPLACE INTO idempotency VALUES(?,?,?,?,?,?)",
                       (owner, operation["operationId"], key, fingerprint,
                        json.dumps(accepted), stamp(now() + timedelta(hours=24))))
        return success("Accepted", accepted, 202,
                       f"/api/v1/searches/{snapshot['search_id']}")

    async def quote_request(request, operation, body, query):
        with database.connect() as db:
            owner = owner_for(db, request)
            if owner is None:
                raise ApiError(403, "SESSION_REQUIRED", "Требуется действующая сессия")
            trip = get_object(db, "trip", request.path_params["trip_id"], owner)
            key = request.headers["idempotency-key"]
            fingerprint = digest(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                            separators=(",", ":")))
            replay = db.execute(
                "SELECT * FROM idempotency WHERE owner=? AND operation=? AND key=? AND expires>?",
                (owner, operation["operationId"], key, stamp(now())),
            ).fetchone()
            if replay:
                if replay["fingerprint"] != fingerprint:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим телом запроса")
                accepted = json.loads(replay["payload"])
                return success("Accepted", accepted, 202,
                               f"/api/v1/searches/{accepted['search_id']}")
        if trip["revision"] != body["expected_revision"]:
            raise ApiError(409, "REVISION_CONFLICT", "Поездка изменилась. Получите актуальную версию.")
        required = []
        if "hotels" in body["components"]:
            required.extend(field for field in ("travelers", "stay") if not body.get(field))
        if "flights" in body["components"]:
            required.extend(field for field in ("origin", "travelers", "flight_dates") if not body.get(field))
        if required:
            field = required[0]
            raise ApiError(422, "QUOTE_INPUTS_REQUIRED", "Для поиска тарифов нужны явные параметры.",
                           [{"field": field, "message": "Обязательное поле отсутствует"}])
        deadline = now() + timedelta(seconds=timeout)
        calls = {}
        if "hotels" in body["components"]:
            calls["hotels"] = planning.tools.hotels(HotelCriteria(
                trip["destination"]["name"], deepcopy(body["stay"]),
                deepcopy(body["travelers"]), deepcopy(trip.get("budget")),
                deepcopy(trip.get("wishes", [])), deadline))
        if "flights" in body["components"]:
            calls["flights"] = planning.tools.flights(FlightCriteria(
                trip["destination"]["name"], body["origin"],
                deepcopy(body["flight_dates"]), deepcopy(body["travelers"]),
                deepcopy(trip.get("budget")), deepcopy(trip.get("wishes", [])), deadline))
        results = dict(zip(calls, await asyncio.gather(*calls.values())))
        trip["revision"] += 1
        trip["updated_at"] = stamp(now())
        lists = {kind: quote_list(kind, trip, body, result)
                 for kind, result in results.items()}
        for kind, value in lists.items():
            trip["components"][kind] = {
                "state": value["state"], "missing_fields": [],
                "error": deepcopy(value["error"]), "incomplete": value["incomplete"],
            }
        validate("Trip", trip)
        current = now()
        expiry = stamp(current + timedelta(days=7))
        snapshot = deepcopy(examples()["completed_empty"]["value"])
        snapshot.update(
            search_id="s_" + uuid4().hex, trip_id=trip["trip_id"],
            trip_revision=trip["revision"], revision=2, created_at=stamp(current),
            updated_at=stamp(current), expires_at=expiry,
            requested_components=list(body["components"]),
            data_mode="live" if any(item.data_mode == "live" for item in results.values()) else "demo",
            warnings=[warning for item in lists.values() for warning in item["warnings"]][:30],
        )
        snapshot["components"] = {
            "itinerary": {"state": "not_requested", "missing_fields": [], "error": None, "incomplete": False},
            "hotels": deepcopy(trip["components"]["hotels"]) if "hotels" in results else {"state": "not_requested", "missing_fields": [], "error": None, "incomplete": False},
            "flights": deepcopy(trip["components"]["flights"]) if "flights" in results else {"state": "not_requested", "missing_fields": [], "error": None, "incomplete": False},
        }
        states = [value["state"] for value in lists.values()]
        snapshot["result_status"] = "ok" if "ready" in states else "empty" if all(state == "empty" for state in states) else "partial"
        validate("Snapshot", snapshot)
        accepted = {"search_id": snapshot["search_id"], "trip_id": trip["trip_id"],
                    "state": "queued", "revision": 1, "expires_at": expiry}
        with database.connect() as db:
            current_trip = get_object(db, "trip", trip["trip_id"], owner)
            if current_trip["revision"] != body["expected_revision"]:
                raise ApiError(409, "REVISION_CONFLICT", "Поездка изменилась во время поиска тарифов.")
            put(db, "trip", trip, owner)
            for kind, value in lists.items():
                put(db, kind, value, owner)
            put(db, "search", snapshot, owner)
            db.execute("INSERT OR REPLACE INTO idempotency VALUES(?,?,?,?,?,?)",
                       (owner, operation["operationId"], key, fingerprint,
                        json.dumps(accepted), stamp(now() + timedelta(hours=24))))
        return success("Accepted", accepted, 202, f"/api/v1/searches/{accepted['search_id']}")

    async def dispatch(request, operation, body, query, prepared_plan=None):
        operation_id = operation["operationId"]
        if request.method != "GET" and request.headers.get("origin") not in origins:
            raise ApiError(403, "ORIGIN_NOT_ALLOWED", "Origin отсутствует или не разрешён")
        with database.connect() as db:
            owner = owner_for(db, request)
            if operation.get("security", specification()["security"]) and owner is None:
                raise ApiError(403, "SESSION_REQUIRED", "Требуется действующая сессия")
            if operation_id == "post_session":
                expiry = stamp(now() + timedelta(days=90))
                token = request.cookies.get("gg_session")
                if owner is None:
                    owner, token = "o_" + uuid4().hex, secrets.token_urlsafe(32)
                    db.execute("INSERT INTO owners VALUES(?)", (owner,))
                db.execute("INSERT INTO sessions VALUES(?,?,?) ON CONFLICT(token_hash) DO UPDATE SET expires=excluded.expires", (digest(token), owner, expiry))
                response = success("Session", {"expires_at": expiry, "recovery_enabled": False})
                response.set_cookie("gg_session", token, max_age=90 * 86400, httponly=True, secure=request.url.scheme == "https", samesite="lax", path="/")
                return response
            if operation_id == "delete_session":
                db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(request.cookies.get("gg_session", "")),))
                response = Response(status_code=204)
                response.delete_cookie("gg_session", path="/", httponly=True, samesite="lax", secure=request.url.scheme == "https")
                return response
            if operation_id not in IMPLEMENTED:
                raise ApiError(501, "NOT_IMPLEMENTED", "Операция зарегистрирована как каркас. Бизнес-логика ещё не реализована.")
            if operation_id == "post_searches":
                key = request.headers["idempotency-key"]
                body.setdefault("params", {})
                fingerprint = digest(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
                replay = db.execute("SELECT * FROM idempotency WHERE owner=? AND operation=? AND key=? AND expires>?", (owner, operation_id, key, stamp(now()))).fetchone()
                if replay:
                    if replay["fingerprint"] != fingerprint:
                        raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим телом запроса")
                    accepted = json.loads(replay["payload"])
                else:
                    trip, snapshot, accepted = build_demo(body, prepared_plan)
                    validate("Trip", trip)
                    validate("Snapshot", snapshot)
                    put(db, "trip", trip, owner)
                    put(db, "search", snapshot, owner)
                    db.execute("INSERT OR REPLACE INTO idempotency VALUES(?,?,?,?,?,?)", (owner, operation_id, key, fingerprint, json.dumps(accepted), stamp(now() + timedelta(hours=24))))
                return success("Accepted", accepted, 202, f"/api/v1/searches/{accepted['search_id']}")
            if operation_id == "put_searches_search_id_cancellation":
                snapshot = get_object(db, "search", request.path_params["search_id"], owner)
                if snapshot["state"] not in {"completed", "failed", "cancelled"}:
                    snapshot["state"] = "cancelled"
                    snapshot["stage"] = None
                    snapshot["result_status"] = None
                    snapshot["clarification"] = None
                    snapshot["revision"] += 1
                    snapshot["updated_at"] = stamp(now())
                    snapshot["components"]["itinerary"] = {
                        "state": "failed", "missing_fields": [],
                        "error": {"code": "SEARCH_CANCELLED",
                                  "message": "Задача остановлена пользователем.",
                                  "retryable": True, "details": []},
                        "incomplete": False,
                    }
                    validate("Snapshot", snapshot)
                    put(db, "search", snapshot, owner)
                    db.execute("DELETE FROM search_inputs WHERE search_id=? AND owner=?",
                               (snapshot["search_id"], owner))
                return success("Snapshot", snapshot)
            if operation_id in {"get_searches_search_id", "get_searches_search_id_events"}:
                snapshot = get_object(db, "search", request.path_params["search_id"], owner)
                if operation_id.endswith("_events"):
                    async def stream():
                        event = "finished" if snapshot["state"] in {"completed", "failed", "cancelled"} else "snapshot"
                        yield f"id: {snapshot['revision']}\nevent: {event}\ndata: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
                    return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})
                return success("Snapshot", snapshot)
            if operation_id == "get_trips":
                rows = db.execute("SELECT payload FROM objects WHERE kind='trip' AND owner=? AND (expires IS NULL OR expires>?) ORDER BY id", (owner, stamp(now()))).fetchall()
                trips = [json.loads(row["payload"]) for row in rows]
                if query.get("saved"):
                    trips = [trip for trip in trips if trip["saved_at"] is not None]
                if ("from" in query) != ("to" in query):
                    raise ApiError(422, "VALIDATION_ERROR", "from и to задаются вместе")
                if "from" in query:
                    if query["to"] < query["from"]:
                        raise ApiError(422, "VALIDATION_ERROR", "to должно быть не раньше from")
                    trips = [trip for trip in trips if trip["schedule"]["start_date"] and trip["schedule"]["start_date"] <= query["to"] and trip["schedule"]["end_date"] >= query["from"]]
                cursor = query.get("cursor")
                if cursor:
                    trips = [trip for trip in trips if trip["trip_id"] > cursor]
                limit = query.get("limit", 50)
                page = trips[:limit]
                return success("TripList", {"items": [card(trip) for trip in page], "next_cursor": page[-1]["trip_id"] if len(trips) > limit else None, "sources": []})
            try:
                trip = get_object(db, "trip", request.path_params["trip_id"], owner)
            except ApiError as exc:
                if operation_id == "delete_trips_trip_id_saved" and exc.status == 404:
                    return Response(status_code=204)
                raise
            if operation_id == "get_trips_trip_id":
                return success("Trip", trip)
            if operation_id in {"get_trips_trip_id_hotels", "get_trips_trip_id_flights"}:
                kind = "hotels" if operation_id.endswith("_hotels") else "flights"
                row = db.execute("SELECT payload FROM objects WHERE kind=? AND id=? AND owner=?",
                                 (kind, trip["trip_id"], owner)).fetchone()
                value = json.loads(row["payload"]) if row else blocked_quote_list(kind, trip)
                return success("HotelList" if kind == "hotels" else "FlightList", value)
            if operation_id == "put_trips_trip_id_schedule":
                desired_schedule = {"start_date": body["start_date"], "end_date": body["end_date"],
                                    "timezone": body["timezone"]}
                if trip["schedule"] == desired_schedule:
                    return success("Trip", trip)
                if trip["revision"] != body["expected_revision"]:
                    raise ApiError(409, "REVISION_CONFLICT", "Поездка изменилась. Получите актуальную версию.")
                assign_dates(trip, body["start_date"], body["end_date"], body["timezone"])
                trip["revision"] += 1
                trip["updated_at"] = stamp(now())
                validate("Trip", trip)
                put(db, "trip", trip, owner)
                return success("Trip", trip)
            desired = operation_id == "put_trips_trip_id_saved"
            if bool(trip["saved_at"]) != desired:
                trip["saved_at"] = stamp(now()) if desired else None
                trip["expires_at"] = None if desired or trip["favorite_at"] else stamp(now() + timedelta(days=7))
                trip["revision"] += 1
                trip["updated_at"] = stamp(now())
                put(db, "trip", trip, owner)
            if not desired:
                return Response(status_code=204)
            return success("TripFlags", {key: trip[key] for key in ("trip_id", "revision", "saved_at", "favorite_at", "expires_at")})

    def endpoint_for(operation):
        async def endpoint(request: Request):
            # Origin проверяется до разбора JSON: отсутствие/чужой Origin всегда 403.
            if request.method != "GET" and request.headers.get("origin") not in origins:
                raise ApiError(403, "ORIGIN_NOT_ALLOWED", "Origin отсутствует или не разрешён")
            query = {}
            body = None
            try:
                for parameter in operation.get("parameters", []):
                    name, where = parameter["name"], parameter["in"]
                    container = request.headers if where == "header" else request.path_params if where == "path" else request.query_params
                    raw = container.get(name)
                    if raw is None:
                        if parameter.get("required"):
                            raise ApiError(422, "VALIDATION_ERROR", f"Обязательный параметр: {name}")
                        continue
                    value = raw
                    if where == "query" and parameter["schema"].get("type") == "integer":
                        if not re.fullmatch(r"[0-9]{1,10}", raw):
                            raise ValueError("Invalid integer parameter")
                        value = int(raw)
                    elif where == "query" and parameter["schema"].get("type") == "boolean":
                        if raw not in {"true", "false"}:
                            raise ValueError("Invalid boolean parameter")
                        value = raw == "true"
                    Draft202012Validator(parameter["schema"], format_checker=FormatChecker()).validate(value)
                    if where == "query":
                        query[name] = value
                if operation.get("requestBody"):
                    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
                        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Требуется application/json")
                    raw_body = bytearray()
                    async for chunk in request.stream():
                        raw_body.extend(chunk)
                        if len(raw_body) > 65536:
                            raise ApiError(413, "REQUEST_TOO_LARGE", "JSON не должен превышать 64 КиБ")
                    body = trim(json.loads(
                        raw_body.decode("utf-8"),
                        parse_constant=reject_json_constant,
                        object_pairs_hook=unique_json_object,
                    ))
                    schema = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
                    if schema == "QuoteRequest" and isinstance(body, dict):
                        components = body.get("components", [])
                        required = []
                        if isinstance(components, list) and "hotels" in components:
                            required.extend(field for field in ("travelers", "stay") if not body.get(field))
                        if isinstance(components, list) and "flights" in components:
                            required.extend(field for field in ("origin", "travelers", "flight_dates") if not body.get(field))
                        if required:
                            raise ApiError(
                                422, "QUOTE_INPUTS_REQUIRED",
                                "Для поиска тарифов нужны явные параметры.",
                                [{"field": required[0], "message": "Обязательное поле отсутствует"}],
                            )
                    validate(schema, body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ApiError(400, "INVALID_JSON", "Тело запроса не является корректным JSON")
            except (ValidationError, ValueError, RecursionError):
                raise ApiError(422, "VALIDATION_ERROR", "Параметры не соответствуют контракту v0.3")
            if operation["operationId"] == "post_searches":
                return await plan_request(request, operation, body, query)
            if operation["operationId"] == "post_trips_trip_id_quote_searches":
                return await quote_request(request, operation, body, query)
            if operation["operationId"] == "post_searches_search_id_clarifications":
                return await clarification_request(request, operation, body, query)
            return await dispatch(request, operation, body, query)
        return endpoint

    async def plan_request(request, operation, body, query):
        body.setdefault("params", {})
        params = body["params"]
        if "travelers" in params and params["travelers"]["adults"] + len(params["travelers"]["children_ages"]) > 9:
            raise ApiError(422, "VALIDATION_ERROR", "Максимум 9 путешественников")
        if "dates" in params:
            days = (date.fromisoformat(params["dates"]["end_date"]) - date.fromisoformat(params["dates"]["start_date"])).days + 1
            if days <= 0 or ("duration_days" in params and days != params["duration_days"]):
                raise ApiError(422, "DURATION_CONFLICT", "Даты и длительность противоречат друг другу")
        with database.connect() as db:
            owner = owner_for(db, request)
        if owner is None:
            raise ApiError(403, "SESSION_REQUIRED", "Требуется действующая сессия")
        lock_key = (owner, request.headers["idempotency-key"])
        deadline = now() + timedelta(seconds=timeout)
        try:
            async with asyncio.timeout(timeout) as request_budget:
                async with planning_slots:
                    lock, count = planning_locks.get(lock_key, (asyncio.Lock(), 0))
                    planning_locks[lock_key] = (lock, count + 1)
                    try:
                        async with lock:
                            with database.connect() as db:
                                replay = db.execute("SELECT payload FROM idempotency WHERE owner=? AND operation='post_searches' AND key=? AND expires>?", (owner, lock_key[1], stamp(now()))).fetchone()
                            if replay is not None:
                                # dispatch проверит fingerprint и доступ, вернёт исходный Accepted.
                                return await dispatch(request, operation, body, query)
                            try:
                                result = await planning.plan(body, deadline)
                            except NeedsClarification as exc:
                                key = request.headers["idempotency-key"]
                                fingerprint = digest(json.dumps(
                                    body, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"),
                                ))
                                return persist_clarification(
                                    owner, operation["operationId"], key,
                                    fingerprint, body, exc.field,
                                )
                            except (UnsupportedDemo, TimeoutError):
                                raise
                            except (ValueError, ValidationError, TypeError, AttributeError) as exc:
                                logging.getLogger("goglobe").warning(
                                    "Agent response rejected request_id=%s error_type=%s",
                                    request.state.request_id, type(exc).__name__,
                                )
                                raise ApiError(502, "AGENT_INVALID_RESPONSE", "Ответ агента не соответствует контракту")
                            except Exception as exc:
                                logging.getLogger("goglobe").warning(
                                    "Agent unavailable request_id=%s error_type=%s",
                                    request.state.request_id, type(exc).__name__,
                                )
                                raise ApiError(503, "AGENT_UNAVAILABLE", "Агент временно недоступен")
                            if request_budget.expired():
                                raise TimeoutError("Request deadline expired")
                            return await dispatch(request, operation, body, query, result)
                    finally:
                        current_lock, count = planning_locks[lock_key]
                        if count == 1:
                            del planning_locks[lock_key]
                        else:
                            planning_locks[lock_key] = (current_lock, count - 1)
        except UnsupportedDemo as exc:
            raise ApiError(422, "MOCK_SCENARIO_UNSUPPORTED", str(exc))
        except TimeoutError:
            logging.getLogger("goglobe").warning(
                "Agent deadline exceeded request_id=%s", request.state.request_id,
            )
            raise ApiError(503, "AGENT_TIMEOUT", "Агент не ответил в пределах общего срока")

    @app.post("/api/v1/intent/preview", include_in_schema=False)
    async def intent_preview(request: Request):
        if request.headers.get("origin") not in origins:
            raise ApiError(403, "ORIGIN_NOT_ALLOWED", "Origin отсутствует или не разрешён")
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Требуется application/json")
        with database.connect() as db:
            owner = owner_for(db, request)
        if owner is None:
            raise ApiError(403, "SESSION_REQUIRED", "Требуется действующая сессия")
        raw_body = await request.body()
        if len(raw_body) > 65536:
            raise ApiError(413, "REQUEST_TOO_LARGE", "JSON не должен превышать 64 КиБ")
        try:
            body = trim(json.loads(raw_body.decode("utf-8"),
                                   parse_constant=reject_json_constant,
                                   object_pairs_hook=unique_json_object))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ApiError(400, "INVALID_JSON", "Тело запроса не является корректным JSON")
        if not isinstance(body, dict) or set(body) - {"query", "params"} or "query" not in body:
            raise ApiError(422, "VALIDATION_ERROR", "Параметры не соответствуют контракту v0.3.1")
        params = body.get("params", {})
        try:
            validate("Params", params)
            if not isinstance(body["query"], str) or not 1 <= len(body["query"]) <= 2000 or not body["query"].strip():
                raise ValueError("Invalid query")
        except (ValidationError, ValueError, TypeError):
            raise ApiError(422, "VALIDATION_ERROR", "Параметры не соответствуют контракту v0.3.1")
        async with preview_rate_lock:
            current = monotonic()
            cutoff = current - 60
            window = preview_windows.get(owner)
            if window is None:
                if len(preview_windows) >= PREVIEW_OWNER_BUCKETS:
                    oldest_owner = min(
                        preview_windows,
                        key=lambda candidate: preview_windows[candidate][-1],
                    )
                    del preview_windows[oldest_owner]
                    preview_slots.pop(oldest_owner, None)
                window = preview_windows[owner] = deque()
            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) >= PREVIEW_RATE_PER_MINUTE:
                retry_after = max(1, ceil(window[0] + 60 - current))
                raise ApiError(
                    429, "PREVIEW_RATE_LIMITED",
                    "Слишком много запросов preview; повторите позже.",
                    headers={"Retry-After": str(retry_after)},
                )
            window.append(current)
        slot = preview_slots.setdefault(owner, asyncio.Semaphore(2))
        async with slot:
            result = preview_intent(body["query"], params)
        return JSONResponse(result)

    for path, methods in specification()["paths"].items():
        for method, operation in methods.items():
            if method in {"get", "post", "put", "delete", "patch"}:
                app.add_api_route("/api/v1" + path, endpoint_for(operation), methods=[method.upper()], name=operation["operationId"], include_in_schema=False)

    def openapi():
        schema = deepcopy(specification())
        schema["info"]["version"] = "0.3.1"
        schema["info"]["description"] = "GoGlobe BFF v0.3 с аддитивным intent-preview v0.3.1. Нереализованные операции явно возвращают 501."
        schema["components"]["schemas"]["IntentPreviewRequest"] = {
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 2000},
                           "params": {"$ref": "#/components/schemas/Params"}},
            "required": ["query"], "additionalProperties": False,
        }
        def nullable(value):
            return {"anyOf": [value, {"type": "null"}]}
        schema["components"]["schemas"]["IntentPreviewParsed"] = {
            "type": "object", "properties": {
                "destination": nullable({"type": "string", "minLength": 1, "maxLength": 200}),
                "duration_days": nullable({"type": "integer", "minimum": 1, "maximum": 30}),
                "dates": nullable({"$ref": "#/components/schemas/Dates"}),
                "origin": nullable({"type": "string", "minLength": 1, "maxLength": 200}),
                "travelers": nullable({"$ref": "#/components/schemas/Travelers"}),
                "budget": nullable({"$ref": "#/components/schemas/Budget"}),
                "wishes": {"type": "array", "items": {"type": "string",
                    "enum": ["near_sea", "sea_view", "direct_flight", "breakfast"]},
                    "maxItems": 4, "uniqueItems": True},
            },
            "required": ["destination", "duration_days", "dates", "origin", "travelers", "budget", "wishes"],
            "additionalProperties": False,
        }
        schema["components"]["schemas"]["IntentPreviewQuestion"] = {
            "type": "object", "properties": {
                "id": {"type": "string", "minLength": 1, "maxLength": 100},
                "field": {"type": "string", "minLength": 1, "maxLength": 100},
                "kind": {"type": "string", "enum": ["text", "number", "travelers", "money"]},
                "title": {"type": "string", "minLength": 1, "maxLength": 300},
                "required": {"type": "boolean"},
                "options": {"type": "array", "items": {}, "maxItems": 20},
            },
            "required": ["id", "field", "kind", "title", "required", "options"],
            "additionalProperties": False,
        }
        schema["components"]["schemas"]["IntentPreviewResponse"] = {
            "type": "object", "properties": {
                "preview_id": {"type": "string", "pattern": "^ip_", "maxLength": 128},
                "parsed": {"$ref": "#/components/schemas/IntentPreviewParsed"},
                "questions": {"type": "array", "items": {"$ref": "#/components/schemas/IntentPreviewQuestion"}, "maxItems": 3},
                "warnings": {"type": "array", "items": {"$ref": "#/components/schemas/Warning"}, "maxItems": 30},
                "analysis_mode": {"type": "string", "enum": ["llm", "fallback"]},
            },
            "required": ["preview_id", "parsed", "questions", "warnings", "analysis_mode"],
            "additionalProperties": False,
        }
        schema["paths"]["/intent/preview"] = {"post": {
            "operationId": "post_intent_preview", "summary": "Preview parsed trip intent",
            "security": schema.get("security", []),
            "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/IntentPreviewRequest"}}}},
            "responses": {"200": {"description": "Validated preview without creating a Trip",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/IntentPreviewResponse"}}}},
                "400": {"description": "Invalid JSON"}, "403": {"description": "Session or Origin required"},
                "413": {"description": "Request too large"}, "415": {"description": "JSON required"},
                "422": {"description": "Validation error"},
                "429": {"description": "Preview rate limit exceeded",
                    "headers": {"Retry-After": {"schema": {"type": "integer", "minimum": 1, "maximum": 60}}},
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}}},
            "x-implementation-status": "implemented",
        }}
        for methods in schema["paths"].values():
            for operation in methods.values():
                for code in ("413", "502", "503"):
                    operation["responses"].setdefault(code, {"description": "Ошибка входа или временная недоступность зависимости", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}})
                if operation["operationId"] not in IMPLEMENTED:
                    operation["responses"]["501"] = {"description": "Каркас: бизнес-логика не реализована", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}}
                    operation["summary"] = "[ЗАГЛУШКА] " + operation.get("summary", operation["operationId"])
                operation["x-implementation-status"] = "demo" if operation["operationId"] in IMPLEMENTED else "scaffold"
        return schema
    app.openapi = openapi

    @app.get("/health", include_in_schema=False)
    async def health():
        try:
            with database.connect() as db:
                db.execute("SELECT 1 FROM owners LIMIT 1").fetchone()
        except sqlite3.Error as exc:
            logging.getLogger("goglobe").warning(
                "Health storage check failed sqlite_code=%s",
                getattr(exc, "sqlite_errorcode", None),
            )
            return JSONResponse({"status": "degraded", "storage": "unavailable"}, status_code=503)
        policy = getattr(planning.tools, "policy", None)
        provider_mode = getattr(policy, "provider_mode", "snapshot")
        return {"status": "ok", "mode": provider_mode, "contract": "0.3.1", "storage": "sqlite",
                "implemented_operations": len(IMPLEMENTED), "scaffold_operations": 28 - len(IMPLEMENTED)}

    return app

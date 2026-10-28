import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.mock_agent import MockAgent
from app.config import env_float, env_int, env_origins
from app.models import (
    ErrorInfo, ErrorResponse, Offer, Scenario, SearchAccepted, SearchRequest, SearchResult,
)
from app.ports import SearchAgent
from app.store import MemorySearchStore, SearchJob

logger = logging.getLogger("goglobe")


def create_app(agent: SearchAgent | None = None, capacity: int | None = None) -> FastAPI:
    delay = env_float("GOGLOBE_MOCK_DELAY_SECONDS", "0.15", minimum=0, maximum=10)
    capacity = capacity if capacity is not None else env_int("GOGLOBE_MAX_SEARCHES", "500", minimum=1)
    if capacity < 1:
        raise ValueError("GOGLOBE_MAX_SEARCHES must be positive")
    search_agent = agent or MockAgent(delay)
    timeout = env_float("GOGLOBE_LEGACY_TIMEOUT_SECONDS", "20", minimum=0,
                        maximum=120, minimum_inclusive=False)
    store = MemorySearchStore(capacity)
    tasks: set[asyncio.Task] = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(
        title="GoGlobe API / BFF", version="0.1.0", lifespan=lifespan,
        description="Каркас Backend №1. Только синтетические моки, без внешних API и AI.",
        docs_url=None, redoc_url=None,
        responses={422: {"model": ErrorResponse}},
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=env_origins("GOGLOBE_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"),
        allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Mock-Scenario", "Last-Event-ID"],
        expose_headers=["Location"],
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Не отражаем пользовательский текст и тело запроса в ответах и логах.
        fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
        return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "Проверьте поля: " + ", ".join(fields)}})

    def get_job(search_id: str) -> SearchJob:
        job = store.jobs.get(search_id)
        if job is None:
            raise HTTPException(404, "Поиск не найден или уже удалён из памяти")
        return job

    async def run(job: SearchJob, body: SearchRequest, scenario: Scenario):
        try:
            async def emit(stage, message):
                if stage == "done":
                    raise ValueError("Only BFF may finish a search")
                await job.emit(stage, message)
            async with asyncio.timeout(timeout):
                result = await search_agent.search(job.result.id, body, scenario, emit)
            if not isinstance(result, SearchResult) or result.id != job.result.id or result.status == "processing":
                raise ValueError("Invalid agent result identity/state")
            if result.status in {"ok", "partial"} and not result.offers:
                raise ValueError("Successful result must have offers")
            if result.status not in {"ok", "partial"} and result.offers:
                raise ValueError("Invalid offers for result state")
            if (result.status == "error") != bool(result.error) or (result.status == "needs_clarification") != bool(result.clarifying_question):
                raise ValueError("Inconsistent result state")
            job.result = SearchResult.model_validate(result.model_dump(by_alias=True))
        except Exception:
            logger.exception("Search failed: %s", job.result.id)
            job.result = SearchResult(
                id=job.result.id, status="error", parsed=body.params,
                error=ErrorInfo(code="SEARCH_FAILED", message="Не удалось выполнить поиск"),
            )
        await job.emit("done", "Поиск завершён")

    @app.get("/health", tags=["service"])
    async def health():
        return {"status": "ok", "mode": "mock", "version": "0.1.0"}

    @app.post("/api/search", response_model=SearchAccepted, status_code=202, tags=["search"], responses={503: {"model": ErrorResponse}})
    async def start_search(body: SearchRequest, x_mock_scenario: Scenario = Header(default=Scenario.ok)):
        search_id = str(uuid4())
        job = SearchJob(SearchResult(id=search_id, status="processing", parsed=body.params))
        try:
            store.add(job)
        except OverflowError:
            raise HTTPException(503, "Слишком много активных поисков; повторите позже")
        task = asyncio.create_task(run(job, body, x_mock_scenario))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        accepted = SearchAccepted(id=search_id, result_url=f"/api/search/{search_id}", events_url=f"/api/search/{search_id}/events")
        return JSONResponse(status_code=202, content=accepted.model_dump(), headers={"Location": accepted.result_url})

    @app.get("/api/search/{search_id}", response_model=SearchResult, tags=["search"], responses={404: {"model": ErrorResponse}})
    async def get_result(search_id: str):
        return get_job(search_id).result

    @app.get("/api/search/{search_id}/offers/{offer_id}", response_model=Offer, tags=["search"], responses={404: {"model": ErrorResponse}})
    async def get_offer(search_id: str, offer_id: str):
        offer = next((offer for offer in get_job(search_id).result.offers if offer.id == offer_id), None)
        if offer is None:
            raise HTTPException(404, "Предложение не найдено")
        return offer

    @app.get("/api/search/{search_id}/events", tags=["search"], response_class=StreamingResponse,
             responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}, "description": "SSE: stage, done; JSON SearchEvent в data"}, 404: {"model": ErrorResponse}})
    async def events(search_id: str, last_event_id: int = Header(default=0, ge=0)):
        job = get_job(search_id)

        async def stream():
            cursor = last_event_id
            while True:
                async with job.changed:
                    pending = [event for event in job.events if event.sequence > cursor]
                    finished = bool(job.events and job.events[-1].stage == "done")
                    if not pending and not finished:
                        try:
                            await asyncio.wait_for(job.changed.wait(), timeout=15)
                        except asyncio.TimeoutError:
                            pass
                        pending = [event for event in job.events if event.sequence > cursor]
                        finished = bool(job.events and job.events[-1].stage == "done")
                for event in pending:
                    name = "done" if event.stage == "done" else "stage"
                    yield f"id: {event.sequence}\nevent: {name}\ndata: {event.model_dump_json()}\n\n"
                    cursor = event.sequence
                if finished:
                    return
                if not pending:
                    yield ": heartbeat\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


# Только справочный прототип v0.1. Основной сервер находится в app.main.

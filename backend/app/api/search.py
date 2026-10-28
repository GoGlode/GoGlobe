"""HTTP-слой (API/BFF). Владелец: Backend №1."""
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent.orchestrator import run_search
from app.cache.store import store
from app.schemas.search import SearchEvent, SearchRequest, SearchResponse, SearchStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict:
    return {"ok": True}


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    # id генерируем здесь, чтобы сбросить события прошлого прогона до старта поиска (F-05).
    sid = req.search_id or uuid.uuid4().hex[:12]
    request = req.model_copy(update={"search_id": sid})
    await store.begin(sid)

    try:
        res = await run_search(request, store.emit)
    except Exception:
        # Внутренние детали — только в лог, клиенту общее сообщение (F-10).
        logger.exception("Ошибка выполнения поиска (search_id=%s)", sid)
        await store.emit(sid, SearchEvent(stage="error", message="Внутренняя ошибка сервиса"))
        res = SearchResponse(
            search_id=sid,
            status=SearchStatus.error,
            warnings=["Внутренняя ошибка сервиса: попробуйте повторить поиск"],
        )

    store.put_result(res)
    return res


@router.get("/search/{search_id}", response_model=SearchResponse)
async def get_search(search_id: str) -> SearchResponse:
    result = store.get_result(search_id)
    if result is None:
        raise HTTPException(404, "search not found")
    return result


@router.get("/search/{search_id}/events")
async def events(search_id: str) -> StreamingResponse:
    async def gen():
        async for ev in store.stream(search_id):
            yield f"data: {json.dumps(ev.model_dump(), ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
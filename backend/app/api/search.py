"""HTTP-слой (API/BFF). Владелец: Backend №1."""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent.orchestrator import run_search
from app.cache.store import store
from app.schemas.search import SearchEvent, SearchRequest, SearchResponse, SearchStatus

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict:
    return {"ok": True}


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    try:
        res = await run_search(req, store.emit)
    except Exception as e:  # noqa: BLE001 — на демо не должно быть 500 без тела
        sid = req.search_id or "error"
        await store.emit(sid, SearchEvent(stage="error", message=str(e)))
        return SearchResponse(search_id=sid, status=SearchStatus.error,
                              warnings=[f"Внутренняя ошибка: {e}"])
    store.results[res.search_id] = res
    return res


@router.get("/search/{search_id}", response_model=SearchResponse)
async def get_search(search_id: str) -> SearchResponse:
    if search_id not in store.results:
        raise HTTPException(404, "search not found")
    return store.results[search_id]


@router.get("/search/{search_id}/events")
async def events(search_id: str) -> StreamingResponse:
    async def gen():
        async for ev in store.stream(search_id):
            yield f"data: {json.dumps(ev.model_dump(), ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})

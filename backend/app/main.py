"""Единственная основная точка входа сервера GoGlobe v0.3."""
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.bff import create_app

app = create_app()
_dist = Path("/app/frontend_dist")

if _dist.is_dir():
    _assets = _dist / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets), name="frontend-assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/") or (path and "." in Path(path).name):
            raise HTTPException(404)
        return FileResponse(_dist / "index.html", media_type="text/html")

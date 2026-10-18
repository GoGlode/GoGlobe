from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.search import router
from app.config import get_settings

app = FastAPI(title="GoGlobe API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_list,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)

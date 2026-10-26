from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="GOGLOBE_", extra="ignore")

    env: str = "dev"
    providers: Literal["snapshot", "live"] = "snapshot"
    provider_timeout_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 8
    provider_max_attempts: Annotated[int, Field(ge=1, le=3)] = 3
    cache_ttl_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 600
    parser: str = "mock"  # mock | llm
    cors_origins: str = "http://localhost:5173,https://goglobe-demo.vercel.app"
    # Пауза между стадиями в mock-режиме, чтобы фронт мог показать прогресс
    mock_stage_delay: float = 0.4

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = [item.strip() for item in value.split(",")]
        if not origins or any(not item for item in origins):
            raise ValueError("CORS origins cannot be empty")
        unique: list[str] = []
        seen: set[str] = set()
        for origin in origins:
            parsed = urlsplit(origin)
            try:
                parsed.port
            except ValueError as exc:
                raise ValueError("Invalid CORS origin port") from exc
            if (
                "*" in origin
                or parsed.scheme.lower() not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Invalid CORS origin")
            if origin.casefold() not in seen:
                unique.append(origin)
                seen.add(origin.casefold())
        return ",".join(unique)

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

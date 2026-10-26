from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="GOGLOBE_", extra="ignore")

    env: str = "dev"
    providers: Literal["snapshot", "live"] = "snapshot"
    provider_timeout_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 8
    provider_max_attempts: Annotated[int, Field(ge=1, le=3)] = 3
    cache_ttl_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 600
    parser: str = "mock"  # mock | llm
    cors_origins: str = "http://localhost:5173"
    # Пауза между стадиями в mock-режиме, чтобы фронт мог показать прогресс
    mock_stage_delay: float = 0.4

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

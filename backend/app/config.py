from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="GOGLOBE_", extra="ignore")

    env: str = "dev"
    providers: str = "mock"  # mock | live
    parser: str = "mock"  # mock | llm
    cors_origins: str = "http://localhost:5173"
    # Пауза между стадиями в mock-режиме, чтобы фронт мог показать прогресс
    mock_stage_delay: float = 0.4

    # Сколько секунд SSE-поток ждёт событий, прежде чем отдать error и закрыться (F-06).
    sse_idle_timeout: float = 15.0

    # LLM-настройки: читаются без префикса GOGLOBE_, потому что ключи внешних
    # провайдеров принято именовать без неймспейса приложения (LLM_API_KEY, etc.).
    # AliasChoices позволяет принять оба варианта — с префиксом и без.
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_API_KEY", "GOGLOBE_LLM_API_KEY"),
    )
    llm_base_url: str = Field(
        default="https://api.deepseek.com/v1",
        validation_alias=AliasChoices("LLM_BASE_URL", "GOGLOBE_LLM_BASE_URL"),
    )
    llm_model: str = Field(
        default="deepseek-chat",
        validation_alias=AliasChoices("LLM_MODEL", "GOGLOBE_LLM_MODEL"),
    )
    use_mock_ai: bool = Field(
        default=False,
        validation_alias=AliasChoices("USE_MOCK_AI", "GOGLOBE_USE_MOCK_AI"),
    )

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

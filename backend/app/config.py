"""Strict environment parsing shared by the current and legacy servers."""
import math
import os
from collections.abc import Collection
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit


@dataclass
class Settings:
    """Compatibility settings for the BE2 agent modules kept in the monorepo.

    The v0.3 BFF uses the strict helpers below directly; the legacy agent keeps
    using ``get_settings`` until its interface is migrated.
    """

    env: str = "dev"
    providers: str = "mock"
    parser: str = "mock"
    cors_origins: str = "http://localhost:5173"
    mock_stage_delay: float = 0.4

    @property
    def cors_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings(
        env=os.getenv("GOGLOBE_ENV", "dev"),
        providers=os.getenv("GOGLOBE_LEGACY_PROVIDERS", "mock"),
        parser=os.getenv("GOGLOBE_PARSER", "mock"),
        cors_origins=os.getenv("GOGLOBE_LEGACY_CORS_ORIGINS", "http://localhost:5173"),
        mock_stage_delay=env_float("GOGLOBE_MOCK_STAGE_DELAY", "0.4", minimum=0, maximum=10),
    )


def env_float(name: str, default: str, *, minimum: float | None = None,
              maximum: float | None = None, minimum_inclusive: bool = True) -> float:
    try:
        value = float(os.getenv(name, default))
    except ValueError:
        raise ValueError(f"{name} must be a number") from None
    lower_invalid = minimum is not None and (
        value < minimum if minimum_inclusive else value <= minimum
    )
    if not math.isfinite(value) or lower_invalid or (maximum is not None and value > maximum):
        bounds = (
            f"greater than {minimum}" if minimum is not None and not minimum_inclusive
            else f"at least {minimum}" if minimum is not None else "finite"
        )
        if maximum is not None:
            bounds += f" and at most {maximum}"
        raise ValueError(f"{name} must be {bounds}")
    return value


def env_int(name: str, default: str, *, minimum: int | None = None,
            maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, default))
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        bounds = f"at least {minimum}" if minimum is not None else "valid"
        if maximum is not None:
            bounds += f" and at most {maximum}"
        raise ValueError(f"{name} must be {bounds}")
    return value


def env_bool(name: str, default: str) -> bool:
    raw = os.getenv(name, default).lower()
    if raw not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return raw == "true"


def env_choice(name: str, default: str, choices: Collection[str]) -> str:
    raw = os.getenv(name, default)
    if raw not in choices:
        expected = " or ".join(sorted(choices))
        raise ValueError(f"{name} must be {expected}")
    return raw


def env_origins(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    origins = [value.strip() for value in raw.split(",") if value.strip()]
    if not origins:
        raise ValueError(f"{name} must contain at least one HTTP(S) origin")
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            valid = (
                parsed.scheme in {"http", "https"}
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and parsed.path == ""
                and parsed.query == ""
                and parsed.fragment == ""
            )
            parsed.port  # Validate the port syntax/range.
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(f"{name} must contain only HTTP(S) origins")
    return list(dict.fromkeys(origins))

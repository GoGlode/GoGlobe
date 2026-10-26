"""Per-attempt timeout, bounded retries and safe provider validation."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas.providers import FlightOption, HotelOption
from app.schemas.search import DateRange

from .base import FlightProvider, HotelProvider, ProviderError

ModelT = TypeVar("ModelT", bound=BaseModel)


async def _call(
    operation: Callable[[], Awaitable[Any]],
    model: type[ModelT],
    timeout: float,
    attempts: int,
) -> list[ModelT]:
    if timeout <= 0 or attempts not in range(1, 4):
        raise ValueError("invalid resilience policy")
    for attempt in range(1, attempts + 1):
        failure: ProviderError | None = None
        try:
            response = await asyncio.wait_for(operation(), timeout=timeout)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            failure = ProviderError("provider_timeout", retryable=True)
        except ProviderError as exc:
            failure = exc
        except Exception:  # noqa: BLE001 - upstream details must not cross this boundary
            failure = ProviderError("provider_failure")
        else:
            try:
                if not isinstance(response, list):
                    raise TypeError
                return [model.model_validate(item) for item in response]
            except (TypeError, ValueError, ValidationError):
                failure = ProviderError("provider_invalid_response")

        if not failure.retryable or attempt == attempts:
            raise ProviderError(failure.code, retryable=failure.retryable)
    raise AssertionError("unreachable")


class ResilientFlightProvider:
    def __init__(self, provider: FlightProvider, timeout: float, attempts: int) -> None:
        self.provider, self.timeout, self.attempts = provider, timeout, attempts

    async def search(
        self, destination: str, dates: DateRange, travelers: int
    ) -> list[FlightOption]:
        return await _call(
            lambda: self.provider.search(destination, dates, travelers),
            FlightOption,
            self.timeout,
            self.attempts,
        )


class ResilientHotelProvider:
    def __init__(self, provider: HotelProvider, timeout: float, attempts: int) -> None:
        self.provider, self.timeout, self.attempts = provider, timeout, attempts

    async def search(
        self, destination: str, dates: DateRange, travelers: int
    ) -> list[HotelOption]:
        return await _call(
            lambda: self.provider.search(destination, dates, travelers),
            HotelOption,
            self.timeout,
            self.attempts,
        )

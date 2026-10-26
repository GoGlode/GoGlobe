"""Configuration, retry and isolation tests for the provider runtime."""

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.integrations import registry
from app.integrations.base import ProviderError
from app.integrations.resilience import ResilientFlightProvider, ResilientHotelProvider
from app.integrations.snapshots import SnapshotFlightProvider, SnapshotHotelProvider
from app.schemas.search import DateRange

DATES = DateRange.model_validate({"from": "2026-11-10", "to": "2026-11-15"})
FLIGHT = {
    "id": "flight",
    "destination": "Анталья",
    "direct": True,
    "dates": {"from": "2026-11-10", "to": "2026-11-15"},
    "price": {"amount": 1, "currency": "RUB"},
    "source": "test",
    "fetched_at": "2026-10-26T10:00:00+03:00",
}


class StubFlightProvider:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def search(self, destination, dates, travelers):
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _run(provider):
    return asyncio.run(provider.search("Анталья", DATES, 2))


def test_settings_are_strict_and_have_safe_defaults():
    settings = Settings(_env_file=None)
    assert settings.providers == "snapshot"
    assert settings.provider_timeout_seconds == 8
    assert settings.provider_max_attempts == 3

    for field, value in (("providers", "mock"), ("provider_max_attempts", 4)):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **{field: value})


def test_registry_selects_snapshot_runtime(monkeypatch):
    settings = SimpleNamespace(
        providers="snapshot", provider_timeout_seconds=8, provider_max_attempts=3
    )
    monkeypatch.setattr(registry, "get_settings", lambda: settings)

    flights, hotels = registry.get_providers()

    assert isinstance(flights, ResilientFlightProvider)
    assert isinstance(hotels, ResilientHotelProvider)
    assert isinstance(flights.provider, SnapshotFlightProvider)
    assert isinstance(hotels.provider, SnapshotHotelProvider)


def test_live_without_configuration_never_loads_snapshots(monkeypatch):
    settings = SimpleNamespace(
        providers="live", provider_timeout_seconds=8, provider_max_attempts=3
    )
    monkeypatch.setattr(registry, "get_settings", lambda: settings)
    monkeypatch.setattr(registry, "SnapshotFlightProvider", lambda: pytest.fail("snapshot"))
    monkeypatch.setattr(registry, "SnapshotHotelProvider", lambda: pytest.fail("snapshot"))

    flights, hotels = registry.get_providers()
    for provider in (flights, hotels):
        with pytest.raises(ProviderError) as caught:
            _run(provider)
        assert caught.value.code == "live_not_configured"
        assert caught.value.retryable is False


@pytest.mark.parametrize("failures", [0, 1, 2])
def test_success_on_first_or_retried_attempt(failures):
    retry = ProviderError("provider_unavailable", retryable=True)
    source = StubFlightProvider(*([retry] * failures), [FLIGHT])
    provider = ResilientFlightProvider(source, timeout=1, attempts=3)

    result = _run(provider)

    assert result[0].id == "flight"
    assert source.calls == failures + 1


def test_timeout_is_controlled_and_retried_three_times():
    class SlowProvider:
        calls = 0

        async def search(self, destination, dates, travelers):
            self.calls += 1
            await asyncio.sleep(0.05)
            return []

    source = SlowProvider()
    provider = ResilientFlightProvider(source, timeout=0.001, attempts=3)

    with pytest.raises(ProviderError) as caught:
        _run(provider)
    assert caught.value.code == "provider_timeout"
    assert source.calls == 3


def test_non_retryable_error_stops_immediately():
    source = StubFlightProvider(ProviderError("provider_invalid_response"), [FLIGHT])

    with pytest.raises(ProviderError) as caught:
        _run(ResilientFlightProvider(source, timeout=1, attempts=3))
    assert caught.value.code == "provider_invalid_response"
    assert source.calls == 1


def test_three_retryable_failures_exhaust_attempts():
    failure = ProviderError("provider_unavailable", retryable=True)
    source = StubFlightProvider(failure, failure, failure)

    with pytest.raises(ProviderError) as caught:
        _run(ResilientFlightProvider(source, timeout=1, attempts=3))
    assert caught.value.code == "provider_unavailable"
    assert source.calls == 3


def test_private_upstream_exception_text_is_not_exposed():
    private = "https://supplier.invalid?token=secret private response body"
    source = StubFlightProvider(RuntimeError(private))

    with pytest.raises(ProviderError) as caught:
        _run(ResilientFlightProvider(source, timeout=1, attempts=3))
    assert caught.value.code == "provider_failure"
    assert private not in str(caught.value)
    assert source.calls == 1

"""Module 4: bounded cache, retry budgets and explicit offline demo fallback.

The base IntegrationTools remains the validation boundary. Only its validated
results enter this cache; HTTP adapters remain replaceable.
"""
import asyncio
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import random
import time
from jsonschema.exceptions import ValidationError

from app.config import env_bool, env_choice, env_float, env_int

from app.integrations.ports import (
    DestinationCriteria, FlightCriteria, HotelCriteria, ProviderError,
    ToolResult, parse_timestamp, remaining_seconds, walk,
)
from app.integrations.service import (
    DemoDestinationProvider, DemoFlightProvider, DemoHotelProvider,
    IntegrationTools, default_offer_providers, unavailable,
)

_tool_trace = ContextVar("goglobe_tool_trace", default=None)


@contextmanager
def tool_trace():
    """A separate mutable trace per plan, also inherited by gather's tasks."""
    trace = []
    token = _tool_trace.set(trace)
    try:
        yield trace
    finally:
        _tool_trace.reset(token)


def _record(result):
    trace = _tool_trace.get()
    if trace is not None and result.data_mode == "demo" and result.items:
        code = "DEMO_FALLBACK" if any(w["code"] == "DEMO_FALLBACK" for w in result.warnings) else "DEMO_DATA"
        if code not in trace:
            trace.append(code)
    return result


@dataclass(frozen=True)
class ResiliencePolicy:
    provider_mode: str = "snapshot"
    cache_ttl_seconds: float = 60
    max_entries: int = 128
    max_bytes: int = 8 * 1024 * 1024
    attempt_timeout_seconds: float = 8
    max_attempts: int = 3
    backoff_seconds: float = 0.1
    max_pending_keys: int = 128
    max_waiters_per_key: int = 64
    demo_fallback: bool = False
    fallback_timeout_seconds: float = 0.5

    def __post_init__(self):
        if self.provider_mode not in {"live", "snapshot"}:
            raise ValueError("Invalid provider_mode")
        for name in ("cache_ttl_seconds", "attempt_timeout_seconds", "backoff_seconds", "fallback_timeout_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid {name}")
        if not 0 < self.attempt_timeout_seconds <= 120 or not 0 < self.fallback_timeout_seconds <= 10:
            raise ValueError("Timeout outside allowed range")
        for name, limit in (("max_entries", 10000), ("max_bytes", 128 * 1024 * 1024),
                            ("max_attempts", 3), ("max_pending_keys", 1024), ("max_waiters_per_key", 1024)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= limit:
                raise ValueError(f"Invalid {name}")
        if type(self.demo_fallback) is not bool:
            raise ValueError("demo_fallback must be bool")

    @classmethod
    def from_env(cls):
        return cls(
            provider_mode=env_choice(
                "GOGLOBE_PROVIDERS", "snapshot", {"live", "snapshot"},
            ),
            cache_ttl_seconds=env_float(
                "GOGLOBE_CACHE_TTL_SECONDS", "60", minimum=0,
            ),
            attempt_timeout_seconds=env_float(
                "GOGLOBE_PROVIDER_TIMEOUT_SECONDS", "8", minimum=0,
                maximum=120, minimum_inclusive=False,
            ),
            max_attempts=env_int(
                "GOGLOBE_PROVIDER_MAX_ATTEMPTS", "3", minimum=1, maximum=3,
            ),
            demo_fallback=env_bool("GOGLOBE_DEMO_FALLBACK", "false"),
        )


def warning(result: ToolResult, code: str, message: str, *, owned: bool = False) -> ToolResult:
    # Cache.get already returns a private copy; avoid copying its large items twice.
    copied = result if owned else deepcopy(result)
    # Preserve the contract's limit even for a provider returning 30 warnings.
    if not any(item["code"] == code for item in copied.warnings):
        copied.warnings[:] = copied.warnings[:29] + [{"code": code, "message": message, "trip_id": None}]
    return copied


def _price_ttl(result):
    ttl = math.inf
    current = datetime.now(timezone.utc)
    for node in walk(result.items):
        if "coverage" in node and node.get("checked_at"):
            if node.get("stale"):
                return 0
            checked = parse_timestamp(node["checked_at"])
            expiry = parse_timestamp(node["valid_until"]) if node.get("valid_until") else checked + timedelta(minutes=15)
            ttl = min(ttl, (expiry - current).total_seconds())
    return ttl


class ResultCache:
    """Process-local LRU. Monotonic TTL never refreshes on read."""

    def __init__(self, policy: ResiliencePolicy, *, clock=time.monotonic):
        self.policy, self.clock = policy, clock
        self._entries = OrderedDict()
        self._bytes = 0
        self._next_expiry = math.inf

    def _remove(self, key):
        entry = self._entries.pop(key)
        self._bytes -= entry[2]

    def _purge(self):
        current = self.clock()
        if current < self._next_expiry:
            return
        for key, (_, expiry, _) in list(self._entries.items()):
            if expiry <= current:
                self._remove(key)
        self._next_expiry = min((entry[1] for entry in self._entries.values()), default=math.inf)

    def get(self, key):
        self._purge()
        if key not in self._entries:
            return None
        # Also check source wall time, including after a system clock adjustment.
        if _price_ttl(self._entries[key][0]) <= 0:
            self._remove(key)
            return None
        self._entries.move_to_end(key)
        return deepcopy(self._entries[key][0])

    def put(self, key, result, *, deadline_at=None):
        self._purge()
        if self.policy.cache_ttl_seconds == 0 or result.status == "unavailable":
            return
        ttl = min(self.policy.cache_ttl_seconds, _price_ttl(result))
        if ttl <= 0:
            return
        # Serialization reads only: asdict would make a redundant deep copy.
        payload = {field.name: getattr(result, field.name) for field in fields(result)}
        size = len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        if size > self.policy.max_bytes:
            return
        copied = deepcopy(result)
        if deadline_at is not None:
            remaining_seconds(deadline_at)
        if key in self._entries:
            self._remove(key)
        while self._entries and (len(self._entries) >= self.policy.max_entries or self._bytes + size > self.policy.max_bytes):
            self._remove(next(iter(self._entries)))
        expiry = self.clock() + ttl
        self._entries[key] = (copied, expiry, size)
        self._next_expiry = min(self._next_expiry, expiry)
        self._bytes += size


RETRYABLE_CODES = frozenset({"PROVIDER_TIMEOUT", "PROVIDER_TRANSPORT_ERROR",
                             "PROVIDER_RATE_LIMITED"})


class _ObservedProvider:
    """Keep retry metadata private; base tools still sanitize the public error."""

    def __init__(self, provider):
        self.provider = provider
        mode = getattr(provider, "data_mode", "live")
        self.data_mode = mode if isinstance(mode, str) and mode in {"live", "demo"} else "live"
        self.temporary_http_failure = False
        self.retry_after_seconds = None

    async def search(self, criteria):
        try:
            result = await self.provider.search(criteria)
            if not isinstance(result, ToolResult) or not all(
                isinstance(value, list) for value in (result.items, result.sources, result.warnings)
            ):
                raise ValueError("Tool result arrays must be lists")
            return result
        except ProviderError as exc:
            self.temporary_http_failure = exc.code == "PROVIDER_HTTP_ERROR" and exc.retryable is True
            value = exc.retry_after_seconds
            if isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
                self.retry_after_seconds = value
            raise


class ResilientIntegrationTools(IntegrationTools):
    """Drop-in tools with per-kind policies and no implicit live -> demo change."""

    def __init__(self, *args, policy=None, policies=None, **kwargs):
        self.policy = policy if policy is not None else ResiliencePolicy()
        self.policies = dict(policies or {})
        if set(self.policies) - {"hotels", "flights", "destinations"}:
            raise ValueError("Unknown tool policy")
        if not all(isinstance(item, ResiliencePolicy) for item in [self.policy, *self.policies.values()]):
            raise ValueError("Expected ResiliencePolicy")
        default_hotels, default_flights = default_offer_providers(
            self.policy.provider_mode
        )
        if not args:
            kwargs.setdefault("hotels", default_hotels)
        if len(args) < 2:
            kwargs.setdefault("flights", default_flights)
        super().__init__(*args, **kwargs)
        self._caches = {kind: ResultCache(self.policies.get(kind, self.policy))
                        for kind in ("hotels", "flights", "destinations")}
        self._pending = {}
        self._cache_providers = {}
        self._demo = {"hotels": DemoHotelProvider(), "flights": DemoFlightProvider(),
                      "destinations": DemoDestinationProvider()}

    async def _call(self, kind, provider, criteria):
        policy = self.policies.get(kind, self.policy)
        mode = getattr(provider, "data_mode", "live")
        if not isinstance(mode, str) or mode not in {"live", "demo"}:
            return unavailable("PROVIDER_INVALID_CONFIGURATION", "live")
        try:
            expected = {"hotels": HotelCriteria, "flights": FlightCriteria, "destinations": DestinationCriteria}[kind]
            if not isinstance(criteria, expected):
                raise TypeError("Invalid criteria type")
            # frozen dataclasses still contain mutable dicts/lists. Keep one
            # validated snapshot for the key, slot queue, attempts and fallback.
            criteria = replace(deepcopy(criteria))
            payload = asdict(criteria)
            payload.pop("deadline_at")
            key = (kind, id(provider), mode, hashlib.sha256(
                json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest())
        except TimeoutError:
            return unavailable("PROVIDER_TIMEOUT", mode)
        except (ValueError, TypeError, AttributeError, RecursionError, OverflowError, ValidationError):
            return unavailable("PROVIDER_INVALID_CRITERIA", mode)
        # Retain the current provider identity so replacing a provider cannot
        # accidentally reuse a dead object's id and its cached credentials scope.
        if self._cache_providers.get(kind) is not provider:
            self._caches[kind] = ResultCache(policy)
            self._cache_providers[kind] = provider
        cache = self._caches[kind]
        pending = None
        try:
            async with asyncio.timeout(remaining_seconds(criteria.deadline_at)) as budget:
                cached = cache.get(key)
                if cached is not None:
                    remaining_seconds(criteria.deadline_at)
                    return _record(warning(cached, "CACHE_HIT", "Ответ из кэша; время проверки источника не изменено.", owned=True))
                if key not in self._pending:
                    if len(self._pending) >= policy.max_pending_keys:
                        return unavailable("PROVIDER_OVERLOADED", mode)
                    self._pending[key] = [asyncio.Lock(), 0]
                pending = self._pending[key]
                if pending[1] >= policy.max_waiters_per_key:
                    # This call did not acquire a reference; leave cleanup to
                    # the leader and waiters that actually joined the queue.
                    pending = None
                    return unavailable("PROVIDER_OVERLOADED", mode)
                pending[1] += 1
                async with pending[0]:
                    cached = cache.get(key)
                    if cached is not None:
                        remaining_seconds(criteria.deadline_at)
                        return _record(warning(cached, "CACHE_HIT", "Ответ из кэша; время проверки источника не изменено.", owned=True))
                    result = await self._attempts(kind, provider, criteria, policy, mode)
                    if budget.expired():
                        raise TimeoutError
                    remaining_seconds(criteria.deadline_at)
                    # A fallback is never cached as a successful live response.
                    if not any(item["code"] == "DEMO_FALLBACK" for item in result.warnings):
                        cache.put(key, result, deadline_at=criteria.deadline_at)
                    remaining_seconds(criteria.deadline_at)
                    return _record(result)
        except TimeoutError:
            return unavailable("PROVIDER_TIMEOUT", mode)
        finally:
            if pending is not None:
                pending[1] -= 1
                if pending[1] == 0:
                    self._pending.pop(key, None)

    async def _attempts(self, kind, provider, criteria, policy, mode):
        # Fixtures have no validated budget/wishes context. Refuse to present
        # them as a match for filters that the reserve cannot actually apply.
        fallback_supported = kind == "destinations" or (criteria.budget is None and not criteria.wishes)
        use_fallback = policy.demo_fallback and fallback_supported
        reserve = min(policy.fallback_timeout_seconds, remaining_seconds(criteria.deadline_at) / 4) if use_fallback else 0
        primary_deadline = criteria.deadline_at - timedelta(seconds=reserve)
        result = unavailable("PROVIDER_TIMEOUT", mode)
        codes = set()
        for attempt in range(policy.max_attempts):
            remaining = (primary_deadline - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                break
            deadline = min(primary_deadline, datetime.now(timezone.utc) + timedelta(seconds=policy.attempt_timeout_seconds))
            observed = _ObservedProvider(provider)
            result = await super()._call(kind, observed, replace(criteria, deadline_at=deadline))
            if result.status != "unavailable":
                return result
            codes = {item["code"] for item in result.warnings}
            retryable = codes and (codes <= RETRYABLE_CODES or (codes == {"PROVIDER_HTTP_ERROR"} and observed.temporary_http_failure))
            if not retryable or attempt + 1 == policy.max_attempts:
                break
            delay = policy.backoff_seconds * 2 ** attempt * random.uniform(0.8, 1.2)
            if observed.retry_after_seconds is not None:
                delay = max(delay, observed.retry_after_seconds)
            if (primary_deadline - datetime.now(timezone.utc)).total_seconds() <= delay:
                break
            await asyncio.sleep(delay)
        if "PROVIDER_INVALID_CONFIGURATION" in codes:
            return result
        if use_fallback:
            deadline = min(criteria.deadline_at, datetime.now(timezone.utc) + timedelta(seconds=policy.fallback_timeout_seconds))
            fallback = await super()._call(kind, self._demo[kind], replace(criteria, deadline_at=deadline))
            if fallback.status != "unavailable" and fallback.items:
                # Demo has no claim of current availability or a bookable tariff.
                for item in fallback.items:
                    if "availability" in item:
                        item["availability"] = "unknown"
                    if "booking_url" in item:
                        item["booking_url"] = None
                return warning(fallback, "DEMO_FALLBACK", "Источник недоступен; показаны демонстрационные данные, не живые тарифы.")
        return result

"""HTTP adapters for a documented gateway or an explicitly mapped provider API.

No vendor URL or undocumented vendor schema is assumed. One request per search;
cache, retries and fallback are outside module 3.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal, DecimalException, localcontext
import json
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

import httpx

from app.integrations.ports import (
    DestinationCriteria, FlightCriteria, HotelCriteria, ProviderError,
    ToolResult, remaining_seconds, sanitize_booking_links,
)

Criteria = HotelCriteria | FlightCriteria | DestinationCriteria
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value) if value.strip().isascii() and value.strip().isdigit() else (
            parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        return max(0, seconds) if math.isfinite(seconds) else None
    except (ValueError, TypeError, OverflowError):
        return None


def rub_to_minor(value: str | int | Decimal) -> int:
    """Exact RUB major -> minor conversion for vendor decoders; never use floats."""
    if isinstance(value, (bool, float)):
        raise ValueError("Use a decimal string for RUB")
    try:
        major = Decimal(value)
        if not major.is_finite() or major < 0 or major > 90_000_000_000:
            raise ValueError("Invalid RUB amount")
        with localcontext() as context:
            context.prec = max(28, len(major.as_tuple().digits) + 2)
            amount = major * 100
            if amount != amount.to_integral_value():
                raise ValueError("Invalid RUB amount")
            return int(amount)
    except (DecimalException, TypeError, OverflowError):
        raise ValueError("Invalid RUB amount") from None


def criteria_payload(criteria: Criteria) -> dict:
    payload = asdict(criteria)
    payload.pop("deadline_at")
    return payload


def reject_constant(value):
    raise ValueError("Non-standard JSON number")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


class JSONEndpoint:
    """Configured server-side endpoint. Client and stream are closed per call."""

    def __init__(self, url: str, *, headers: dict[str, str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 allow_local_http: bool = False):
        try:
            parsed = httpx.URL(url)
            local = allow_local_http and parsed.scheme == "http" and parsed.host in {"localhost", "127.0.0.1", "::1"}
            if (parsed.scheme != "https" and not local) or not parsed.host or parsed.username or parsed.password or parsed.fragment or parsed.query:
                raise ValueError
        except (ValueError, httpx.InvalidURL):
            raise ValueError("Provider endpoint requires HTTPS without credentials/query/fragment") from None
        self._url = parsed
        self._headers = dict(headers or {})
        self._transport = transport

    async def post(self, payload: dict, deadline_at) -> dict:
        try:
            # Honour the existing integration deadline; do not add a retry policy.
            async with httpx.AsyncClient(transport=self._transport, trust_env=False,
                                        follow_redirects=False) as client:
                async with client.stream("POST", self._url, json=payload,
                                         headers={**self._headers, "Accept": "application/json"},
                                         timeout=remaining_seconds(deadline_at)) as response:
                    if response.status_code != 200:
                        code = {401: "PROVIDER_AUTH_ERROR", 403: "PROVIDER_AUTH_ERROR",
                                429: "PROVIDER_RATE_LIMITED"}.get(response.status_code, "PROVIDER_HTTP_ERROR")
                        raise ProviderError(code, retryable=response.status_code in {500, 502, 503, 504},
                                            retry_after_seconds=retry_after_seconds(response.headers.get("retry-after")))
                    mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if mime != "application/json" and not (mime.startswith("application/") and mime.endswith("+json")):
                        raise ProviderError("PROVIDER_INVALID_RESPONSE")
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(chunks) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ProviderError("PROVIDER_RESPONSE_TOO_LARGE")
                        chunks.extend(chunk)
                    result = json.loads(chunks.decode("utf-8"), parse_constant=reject_constant,
                                        object_pairs_hook=unique_object)
                    if not isinstance(result, dict):
                        raise ValueError("Expected a JSON object")
                    return result
        except httpx.TimeoutException:
            raise ProviderError("PROVIDER_TIMEOUT") from None
        except httpx.HTTPError:
            raise ProviderError("PROVIDER_TRANSPORT_ERROR") from None
        except (ValueError, RecursionError):
            raise ProviderError("PROVIDER_INVALID_RESPONSE") from None


class _HTTPProvider:
    kind: str
    context_fields: tuple[str, ...]

    def __init__(self, endpoint: JSONEndpoint, *, data_mode: str = "live",
                 encode: Callable[[Criteria], dict] | None = None,
                 decode: Callable[[dict, Criteria], dict] | None = None):
        if data_mode not in {"demo", "live"}:
            raise ValueError("Invalid provider mode")
        self.data_mode = data_mode
        self.endpoint = endpoint
        self._encode = encode or criteria_payload
        self._decode = decode or (lambda payload, criteria: payload)

    async def search(self, criteria: Criteria) -> ToolResult:
        expected_type = {"hotels": HotelCriteria, "flights": FlightCriteria,
                         "destinations": DestinationCriteria}[self.kind]
        if not isinstance(criteria, expected_type):
            raise ValueError("Incorrect criteria type")
        # Criteria contain mutable dicts despite frozen dataclasses.
        criteria = replace(deepcopy(criteria))
        request_criteria = deepcopy(criteria)
        canonical = criteria_payload(criteria)
        expected = {key: canonical[key] for key in self.context_fields}
        payload = self._encode(request_criteria)
        raw = await self.endpoint.post(payload, criteria.deadline_at)
        try:
            normalized = self._decode(raw, deepcopy(criteria))
            if not isinstance(normalized, dict) or set(normalized) != {"status", "items", "sources", "warnings", "data_mode", "context"}:
                raise ValueError("Invalid normalized envelope")
            # Python equality treats True/1 and 2/2.0 as equal; the wire contract does not.
            if json.dumps(normalized["context"], sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True):
                raise ValueError("Provider response context differs from request")
            if normalized["data_mode"] != self.data_mode:
                raise ValueError("Provider changed mode")
            result = ToolResult(**{key: normalized[key] for key in ("status", "items", "sources", "warnings", "data_mode")})
            if any(not isinstance(value, list) for value in (result.items, result.sources, result.warnings)):
                raise ValueError("Expected result arrays")
            result = sanitize_booking_links(result)
            result.validate_for(self.kind)
            return result
        except Exception:
            raise ProviderError("PROVIDER_INVALID_RESPONSE") from None


class HTTPHotelProvider(_HTTPProvider):
    kind = "hotels"
    context_fields = ("destination", "stay", "travelers")


class HTTPFlightProvider(_HTTPProvider):
    kind = "flights"
    context_fields = ("destination", "origin", "flight_dates", "travelers")


class HTTPDestinationProvider(_HTTPProvider):
    kind = "destinations"
    context_fields = ("query",)

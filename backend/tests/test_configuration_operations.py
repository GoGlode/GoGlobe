"""Configuration and operational behavior checked in isolated processes."""
from copy import deepcopy
import asyncio
from datetime import datetime, timedelta, timezone
import json
import inspect
import logging
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.bff import create_app
from app.contracts import examples
from app.integrations.http import JSONEndpoint
from app.integrations.ports import DestinationCriteria
from app.integrations.resilience import ResiliencePolicy, ResilientIntegrationTools
from app.integrations.service import DemoDestinationProvider


ORIGIN = "http://localhost:8000"
GOGLOBE_SETTINGS = {
    "GOGLOBE_DB_PATH",
    "GOGLOBE_AGENT_TIMEOUT_SECONDS",
    "GOGLOBE_ENABLE_DOCS",
    "GOGLOBE_COOKIE_SAMESITE",
    "GOGLOBE_CORS_ORIGINS",
    "GOGLOBE_PROVIDERS",
    "GOGLOBE_CACHE_TTL_SECONDS",
    "GOGLOBE_PROVIDER_TIMEOUT_SECONDS",
    "GOGLOBE_PROVIDER_MAX_ATTEMPTS",
    "GOGLOBE_DEMO_FALLBACK",
    "GOGLOBE_MOCK_DELAY_SECONDS",
    "GOGLOBE_MAX_SEARCHES",
    "GOGLOBE_LEGACY_TIMEOUT_SECONDS",
}


def clean_env(**updates):
    keep = {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATH", "PATHEXT"}
    env = {key: value for key, value in os.environ.items() if key.upper() in keep}
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    env.update({key: str(value) for key, value in updates.items()})
    assert not (set(env) & GOGLOBE_SETTINGS - set(updates))
    return env


def run_import(tmp_path, **settings):
    if "GOGLOBE_DB_PATH" not in settings:
        settings["GOGLOBE_DB_PATH"] = tmp_path / "process.sqlite3"
    return subprocess.run(
        [sys.executable, "-I", "-c", "import app.main; print('STARTED')"],
        cwd=tmp_path,
        env=clean_env(**settings),
        capture_output=True,
        text=True,
    )


def run_code(tmp_path, code, **settings):
    if "GOGLOBE_DB_PATH" not in settings:
        settings["GOGLOBE_DB_PATH"] = tmp_path / f"process-{uuid4().hex}.sqlite3"
    return subprocess.run(
        [sys.executable, "-I", "-c", code], cwd=tmp_path,
        env=clean_env(**settings), capture_output=True, text=True,
    )


@pytest.mark.parametrize("name,value", [
    ("GOGLOBE_CACHE_TTL_SECONDS", "-1"),
    ("GOGLOBE_PROVIDER_TIMEOUT_SECONDS", "121"),
    ("GOGLOBE_PROVIDER_MAX_ATTEMPTS", "4"),
])
def test_invalid_range_names_setting_in_clean_process(tmp_path, name, value):
    result = run_import(tmp_path, **{name: value})
    assert result.returncode != 0
    assert name in result.stderr


@pytest.mark.parametrize("value", ["", "not-an-origin", "https://example.com/path"])
def test_invalid_cors_config_fails_at_startup(tmp_path, value):
    result = run_import(tmp_path, GOGLOBE_CORS_ORIGINS=value)
    assert result.returncode != 0
    assert "GOGLOBE_CORS_ORIGINS" in result.stderr


def test_invalid_database_path_names_setting(tmp_path):
    result = run_import(tmp_path, GOGLOBE_DB_PATH=tmp_path)
    assert result.returncode != 0
    assert "GOGLOBE_DB_PATH" in result.stderr
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("blocked", encoding="utf-8")
    result = run_import(tmp_path, GOGLOBE_DB_PATH=blocker / "database.sqlite3")
    assert result.returncode != 0
    assert "GOGLOBE_DB_PATH" in result.stderr


def test_agent_failure_log_is_diagnostic_but_sanitized(tmp_path, caplog):
    secret = "Bearer secret-authorization-value"

    class Agent:
        async def plan(self, context):
            raise RuntimeError(f"upstream body with {secret}")

    caplog.set_level(logging.WARNING, logger="goglobe")
    with TestClient(
        create_app(str(tmp_path / "logs.sqlite3"), agent=Agent()),
        headers={"Origin": ORIGIN, "Authorization": secret},
    ) as client:
        assert client.post("/api/v1/session", json={}).status_code == 200
        cookie = client.cookies.get("gg_session")
        response = client.post(
            "/api/v1/searches",
            json=deepcopy(examples()["plan_request"]["value"]),
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 202
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            snapshot = client.get(response.headers["location"]).json()
            if snapshot["state"] == "failed":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("agent failure was not persisted")

    log = "\n".join(record.getMessage() for record in caplog.records)
    assert response.json()["search_id"] in log
    assert "run_id=r_" in log
    assert "RuntimeError" in log
    assert secret not in log
    assert cookie not in log


INVALID_MAIN_SETTINGS = [
    ("GOGLOBE_AGENT_TIMEOUT_SECONDS", value)
    for value in ("", "text", "nan", "inf", "-1", "0", "120.01")
] + [
    ("GOGLOBE_CACHE_TTL_SECONDS", value)
    for value in ("", "text", "nan", "inf", "-1")
] + [
    ("GOGLOBE_PROVIDER_TIMEOUT_SECONDS", value)
    for value in ("", "text", "nan", "inf", "-1", "0", "120.01")
] + [
    ("GOGLOBE_PROVIDER_MAX_ATTEMPTS", value)
    for value in ("", "text", "1.5", "-1", "0", "4")
] + [
    ("GOGLOBE_PROVIDERS", value)
    for value in ("", "demo", "LIVE", " snapshot", "snapshot ")
] + [
    (name, value)
    for name in ("GOGLOBE_ENABLE_DOCS", "GOGLOBE_DEMO_FALLBACK")
    for value in ("", "1", "yes", "on", " true")
] + [
    ("GOGLOBE_COOKIE_SAMESITE", value)
    for value in ("", "Lax", "NONE", "invalid", " none")
]


def test_complete_invalid_main_matrix_in_clean_processes(tmp_path):
    for name, value in INVALID_MAIN_SETTINGS:
        result = run_import(tmp_path, **{name: value})
        assert result.returncode != 0, (name, value, result.stdout, result.stderr)
        assert name in result.stderr

    marker = "TOP_SECRET_CONFIGURATION_VALUE"
    secret_result = run_import(tmp_path, GOGLOBE_AGENT_TIMEOUT_SECONDS=marker)
    assert secret_result.returncode != 0
    assert marker not in secret_result.stderr


def test_legacy_invalid_matrix_in_clean_processes(tmp_path):
    matrix = [
        ("GOGLOBE_MOCK_DELAY_SECONDS", value)
        for value in ("", "text", "nan", "inf", "-1", "10.01")
    ] + [
        ("GOGLOBE_MAX_SEARCHES", value)
        for value in ("", "text", "1.5", "-1", "0")
    ] + [
        ("GOGLOBE_LEGACY_TIMEOUT_SECONDS", value)
        for value in ("", "text", "nan", "inf", "-1", "0", "120.01")
    ]
    for name, value in matrix:
        result = run_code(tmp_path, "from app.legacy_api import create_app; create_app(); print('STARTED')",
                          **{name: value})
        assert result.returncode != 0, (name, value, result.stdout, result.stderr)
        assert name in result.stderr


def test_defaults_and_valid_boundaries_in_clean_processes(tmp_path):
    code = """
import json
from app.bff import create_app
from app.integrations.resilience import ResiliencePolicy
app = create_app()
policy = ResiliencePolicy.from_env()
print(json.dumps({
    'docs': app.docs_url,
    'providers': policy.provider_mode,
    'cache': policy.cache_ttl_seconds,
    'attempt_timeout': policy.attempt_timeout_seconds,
    'attempts': policy.max_attempts,
    'fallback': policy.demo_fallback,
}))
"""
    default = run_code(tmp_path, code)
    assert default.returncode == 0, default.stderr
    assert json.loads(default.stdout) == {
        "docs": None, "providers": "snapshot", "cache": 60.0, "attempt_timeout": 8.0,
        "attempts": 3, "fallback": False,
    }
    valid = [
        {"GOGLOBE_AGENT_TIMEOUT_SECONDS": "0.001"},
        {"GOGLOBE_AGENT_TIMEOUT_SECONDS": "120"},
        {"GOGLOBE_CACHE_TTL_SECONDS": "0"},
        {"GOGLOBE_CACHE_TTL_SECONDS": "1e100"},
        {"GOGLOBE_PROVIDER_TIMEOUT_SECONDS": "0.001"},
        {"GOGLOBE_PROVIDER_TIMEOUT_SECONDS": "120"},
        {"GOGLOBE_PROVIDER_MAX_ATTEMPTS": "1"},
        {"GOGLOBE_PROVIDER_MAX_ATTEMPTS": "3"},
        {"GOGLOBE_PROVIDERS": "live"},
        {"GOGLOBE_PROVIDERS": "snapshot"},
        {"GOGLOBE_ENABLE_DOCS": "TRUE"},
        {"GOGLOBE_ENABLE_DOCS": "False"},
        {"GOGLOBE_COOKIE_SAMESITE": "lax"},
        {"GOGLOBE_COOKIE_SAMESITE": "strict"},
        {"GOGLOBE_COOKIE_SAMESITE": "none"},
        {"GOGLOBE_DEMO_FALLBACK": "TRUE"},
        {"GOGLOBE_DEMO_FALLBACK": "False"},
    ]
    for settings in valid:
        result = run_code(tmp_path, code, **settings)
        assert result.returncode == 0, (settings, result.stderr)


def test_env_example_matches_actual_main_defaults(tmp_path, monkeypatch):
    values = {}
    for line in (Path(__file__).parents[1] / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, value = line.split("=", 1)
            values[name] = value
    assert values == {
        "GOGLOBE_CORS_ORIGINS": "https://goglobe-demo.vercel.app,http://localhost:3000,http://localhost:5173,http://localhost:8000,http://127.0.0.1:8000",
        "GOGLOBE_DB_PATH": "data/goglobe.sqlite3",
        "GOGLOBE_AGENT_TIMEOUT_SECONDS": "20",
        "GOGLOBE_ENABLE_DOCS": "false",
        "GOGLOBE_COOKIE_SAMESITE": "lax",
        "GOGLOBE_PROVIDERS": "snapshot",
        "GOGLOBE_CACHE_TTL_SECONDS": "60",
        "GOGLOBE_PROVIDER_TIMEOUT_SECONDS": "8",
        "GOGLOBE_PROVIDER_MAX_ATTEMPTS": "3",
        "GOGLOBE_DEMO_FALLBACK": "false",
        "GOGLOBE_MOCK_DELAY_SECONDS": "0.15",
        "GOGLOBE_MAX_SEARCHES": "500",
        "GOGLOBE_LEGACY_TIMEOUT_SECONDS": "20",
    }
    for name in GOGLOBE_SETTINGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    app = create_app()
    assert (tmp_path / "data" / "goglobe.sqlite3").is_file()
    assert app.docs_url is None
    cors = next(item for item in app.user_middleware if item.cls.__name__ == "CORSMiddleware")
    assert cors.kwargs["allow_origins"] == values["GOGLOBE_CORS_ORIGINS"].split(",")
    endpoint = next(route.endpoint for route in app.routes if route.name == "post_searches")
    plan_request = inspect.getclosurevars(endpoint).nonlocals["plan_request"]
    assert inspect.getclosurevars(plan_request).nonlocals["timeout"] == 20
    assert ResiliencePolicy.from_env() == ResiliencePolicy()


def test_root_env_example_starts_snapshot_backend(tmp_path):
    values = {}
    root_env = Path(__file__).parents[2] / ".env.example"
    for line in root_env.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, value = line.split("=", 1)
            values[name] = value

    backend_values = {name: value for name, value in values.items() if name in GOGLOBE_SETTINGS}
    assert backend_values["GOGLOBE_PROVIDERS"] == "snapshot"
    assert "https://goglobe-demo.vercel.app" in backend_values["GOGLOBE_CORS_ORIGINS"].split(",")
    assert backend_values["GOGLOBE_DB_PATH"] == "data/goglobe.sqlite3"

    result = run_import(tmp_path, **backend_values)
    assert result.returncode == 0, result.stderr


def test_legacy_valid_boundaries_in_clean_processes(tmp_path):
    code = "from app.legacy_api import create_app; create_app(); print('STARTED')"
    for settings in [
        {"GOGLOBE_MOCK_DELAY_SECONDS": "0"},
        {"GOGLOBE_MOCK_DELAY_SECONDS": "10"},
        {"GOGLOBE_MAX_SEARCHES": "1"},
        {"GOGLOBE_MAX_SEARCHES": "1000000"},
        {"GOGLOBE_LEGACY_TIMEOUT_SECONDS": "0.001"},
        {"GOGLOBE_LEGACY_TIMEOUT_SECONDS": "120"},
    ]:
        result = run_code(tmp_path, code, **settings)
        assert result.returncode == 0, (settings, result.stderr)


def test_docs_switch_and_unknown_origin_actual_http(tmp_path, monkeypatch):
    monkeypatch.setenv("GOGLOBE_ENABLE_DOCS", "false")
    with TestClient(create_app(str(tmp_path / "docs-off.sqlite3")),
                    headers={"Origin": ORIGIN}) as client:
        assert client.get("/docs").status_code == 404
        denied = client.post("/api/v1/session", json={}, headers={"Origin": "https://unknown.example"})
        assert denied.status_code == 403
        assert "access-control-allow-origin" not in denied.headers
    monkeypatch.setenv("GOGLOBE_ENABLE_DOCS", "true")
    with TestClient(create_app(str(tmp_path / "docs-on.sqlite3")),
                    headers={"Origin": ORIGIN}) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200


def test_demo_fallback_requires_explicit_true_and_zero_disables_cache():
    class Failing:
        data_mode = "live"

        async def search(self, criteria):
            from app.integrations.ports import ProviderError
            raise ProviderError("PROVIDER_AUTH_ERROR")

    async def run():
        criteria = DestinationCriteria("Рим", datetime.now(timezone.utc) + timedelta(seconds=2))
        disabled = ResilientIntegrationTools(
            destinations=Failing(), policy=ResiliencePolicy(demo_fallback=False),
        )
        assert (await disabled.destinations(criteria)).status == "unavailable"
        enabled = ResilientIntegrationTools(
            destinations=Failing(), policy=ResiliencePolicy(demo_fallback=True),
        )
        fallback = await enabled.destinations(criteria)
        assert fallback.status == "ok"
        assert {item["code"] for item in fallback.warnings} >= {"DEMO_FALLBACK"}

        class Counting(DemoDestinationProvider):
            def __init__(self):
                self.calls = 0

            async def search(self, value):
                self.calls += 1
                return await super().search(value)

        provider = Counting()
        no_cache = ResilientIntegrationTools(
            destinations=provider, policy=ResiliencePolicy(cache_ttl_seconds=0),
        )
        await no_cache.destinations(criteria)
        await no_cache.destinations(criteria)
        assert provider.calls == 2
    asyncio.run(run())


def test_attempt_timeout_and_overall_deadline_are_independent():
    class Waiting:
        data_mode = "live"

        def __init__(self):
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()

        async def search(self, criteria):
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.set()

    async def run():
        provider = Waiting()
        tools = ResilientIntegrationTools(
            destinations=provider,
            policy=ResiliencePolicy(attempt_timeout_seconds=0.01, max_attempts=1),
        )
        criteria = DestinationCriteria("Рим", datetime.now(timezone.utc) + timedelta(seconds=1))
        task = asyncio.create_task(tools.destinations(criteria))
        await provider.started.wait()
        result = await task
        assert result.status == "unavailable"
        assert provider.cancelled.is_set()

        provider = Waiting()
        tools = ResilientIntegrationTools(
            destinations=provider,
            policy=ResiliencePolicy(attempt_timeout_seconds=120, max_attempts=1),
        )
        criteria = DestinationCriteria("Рим", datetime.now(timezone.utc) + timedelta(seconds=0.01))
        task = asyncio.create_task(tools.destinations(criteria))
        await provider.started.wait()
        result = await task
        assert result.status == "unavailable"
        assert provider.cancelled.is_set()
    asyncio.run(run())


def test_http_client_transport_is_closed_on_success_and_error():
    class Transport(httpx.AsyncBaseTransport):
        def __init__(self, status):
            self.status = status
            self.closed = False

        async def handle_async_request(self, request):
            return httpx.Response(self.status, json={})

        async def aclose(self):
            self.closed = True

    async def run():
        for status in (200, 503):
            transport = Transport(status)
            endpoint = JSONEndpoint("https://provider.example/api", transport=transport)
            try:
                await endpoint.post({}, datetime.now(timezone.utc) + timedelta(seconds=1))
            except Exception:
                pass
            assert transport.closed
    asyncio.run(run())


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _request(opener, url, *, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    request = Request(url, data=data, method=method, headers={
        "Origin": ORIGIN, **({"Content-Type": "application/json"} if data else {}),
        **(headers or {}),
    })
    try:
        with opener.open(request, timeout=3) as response:
            return response.status, json.loads(response.read() or b"null"), dict(response.headers)
    except HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null"), dict(exc.headers)


def _start_server(tmp_path, port, db_path):
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=tmp_path, env=clean_env(GOGLOBE_DB_PATH=db_path),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError((process.returncode, stdout, stderr))
        try:
            if _request(opener, url + "/health")[0] == 200:
                return process, opener, url
        except OSError:
            time.sleep(0.02)
    process.terminate()
    process.wait(timeout=5)
    raise AssertionError("server did not become healthy")


def _stop_server(process):
    process.terminate()
    process.wait(timeout=10)
    assert process.returncode is not None


def test_real_process_restart_persists_sqlite_releases_socket_and_database(tmp_path):
    port = _free_port()
    db_path = tmp_path / "persistent.sqlite3"
    process, opener, url = _start_server(tmp_path, port, db_path)
    assert _request(opener, url + "/api/v1/session", method="POST", body={})[0] == 200
    body = deepcopy(examples()["plan_request"]["value"])
    status, accepted, _ = _request(
        opener, url + "/api/v1/searches", method="POST", body=body,
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert status == 202
    trip_url = url + "/api/v1/trips/" + accepted["trip_id"]
    assert _request(opener, trip_url + "/saved", method="PUT", body={})[0] == 200
    _stop_server(process)

    process, restarted, url = _start_server(tmp_path, port, db_path)
    # Reuse the persisted session cookie in a new HTTP client/process connection.
    old_jar = next(handler.cookiejar for handler in opener.handlers
                   if isinstance(handler, HTTPCookieProcessor))
    new_jar = next(handler.cookiejar for handler in restarted.handlers
                   if isinstance(handler, HTTPCookieProcessor))
    for cookie in old_jar:
        new_jar.set_cookie(cookie)
    assert _request(restarted, trip_url)[0] == 200
    _stop_server(process)

    renamed = tmp_path / "released.sqlite3"
    db_path.rename(renamed)
    assert renamed.is_file()


def test_process_local_cache_is_empty_after_restart(tmp_path):
    code = """
import asyncio, json
from datetime import datetime, timedelta, timezone
from app.integrations.ports import DestinationCriteria
from app.integrations.resilience import ResilientIntegrationTools
from app.integrations.service import DemoDestinationProvider
class Counting(DemoDestinationProvider):
    def __init__(self): self.calls = 0
    async def search(self, value):
        self.calls += 1
        return await super().search(value)
async def main():
    provider = Counting()
    tools = ResilientIntegrationTools(destinations=provider)
    value = DestinationCriteria('Рим', datetime.now(timezone.utc) + timedelta(seconds=5))
    await tools.destinations(value)
    await tools.destinations(value)
    print(json.dumps({'calls': provider.calls}))
asyncio.run(main())
"""
    first = run_code(tmp_path, code)
    second = run_code(tmp_path, code)
    assert first.returncode == second.returncode == 0
    assert json.loads(first.stdout) == json.loads(second.stdout) == {"calls": 1}


def test_health_reports_runtime_storage_failure(tmp_path):
    path = str(tmp_path / "health.sqlite3")
    with TestClient(create_app(path), headers={"Origin": ORIGIN}) as client:
        assert client.get("/health").status_code == 200
        with sqlite3.connect(path, timeout=1) as locker:
            locker.execute("BEGIN EXCLUSIVE")
            degraded = client.get("/health")
        assert degraded.status_code == 503
        assert degraded.json() == {"status": "degraded", "storage": "unavailable"}

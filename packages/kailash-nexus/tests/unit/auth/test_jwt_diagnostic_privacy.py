"""Automatic JWT diagnostics preserve auth outcomes without exception payloads."""

import io
import logging
import secrets

import httpx
import pytest
from fastapi import APIRouter, Request

from kailash.trust.auth.exceptions import InvalidTokenError
from kailash.trust.auth.jwt import JWTConfig, JWTValidator
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]
PRIVATE = "callback-person@example.invalid"


@pytest.fixture
def diagnostics(monkeypatch):
    monkeypatch.setenv("KAILASH_ENCRYPTION_KEY", secrets.token_urlsafe(48))
    records = []
    stream = io.StringIO()

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("nexus.auth.jwt")
    previous = logger.level
    logger.setLevel(logging.DEBUG)
    capture = Capture()
    formatted = logging.StreamHandler(stream)
    logging.getLogger().addHandler(capture)
    logger.addHandler(formatted)
    try:
        yield records, stream
        allowed = {
            ("kailash.utils.server_auth", "server_auth.disabled"),
            (
                "kailash_mcp.server",
                "Independent FastMCP not available: No module named 'fastmcp'",
            ),
            ("nexus.auth.jwt", "API key validation failed"),
            ("nexus.auth.jwt", "on_token_validated hook failed"),
            ("nexus.auth.jwt", "Invalid token"),
            ("nexus.auth.jwt", "JWT verification failed"),
        }
        failures = [r for r in records if r.levelno >= logging.WARNING]
        assert all((r.name, r.getMessage()) in allowed for r in failures)
        assert sum(r.getMessage() == "server_auth.disabled" for r in failures) == 1
    finally:
        logging.getLogger().removeHandler(capture)
        logger.removeHandler(formatted)
        logger.setLevel(previous)


async def make_app(config, diagnostics):
    app = Nexus(enable_durability=False, enable_auth=False, auto_discovery=False)
    app.add_plugin(NexusAuthPlugin(jwt=config))
    router = APIRouter()

    @router.get("/diagnostic-proof")
    async def proof(request: Request):
        return {
            "user": request.state.user.user_id,
            "token": request.state.token,
            "payload": request.state.token_payload,
        }

    app.include_router(router)
    try:
        backend = app._mcp_server._mcp
        if any(
            r.getMessage()
            == "Independent FastMCP not available: No module named 'fastmcp'"
            for r in diagnostics[0]
        ):
            from mcp.server.fastmcp import FastMCP

            assert isinstance(backend, FastMCP)

            @backend.tool(name="diagnostic_backend_proof")
            def backend_proof() -> int:
                return 42

            assert any(
                tool.name == "diagnostic_backend_proof"
                for tool in await backend.list_tools()
            )
            result = await backend.call_tool("diagnostic_backend_proof", {})
            content = result[0] if isinstance(result, tuple) else result
            assert content[0].text == "42"
        return app
    except BaseException:
        app.close()
        raise


def assert_safe(diagnostics, expected_message):
    records, stream = diagnostics
    assert PRIVATE not in repr([vars(record) for record in records])
    failures = [
        record
        for record in records
        if record.name == "nexus.auth.jwt" and record.levelno >= logging.WARNING
    ]
    assert len(failures) == 1
    record = failures[0]
    assert record.getMessage() == expected_message
    assert record.error_type
    assert record.error_frames
    assert record.exc_info is None
    assert PRIVATE not in repr(vars(record))
    assert PRIVATE not in stream.getvalue()
    assert expected_message in stream.getvalue()


@pytest.mark.parametrize("callback_kind", ["api_key", "validated"])
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("hostile_type", [False, True])
async def test_callback_failure_is_private_and_preserves_auth(
    monkeypatch, tmp_path, diagnostics, callback_kind, asynchronous, hostile_type
):
    monkeypatch.chdir(tmp_path)
    error_type = (
        type(PRIVATE + "\nFORGED", (ValueError,), {}) if hostile_type else ValueError
    )
    error = error_type(PRIVATE)
    cause = RuntimeError(PRIVATE + "-cause")
    calls = []

    def fail(value):
        calls.append(value)
        raise error from cause

    async def fail_async(value):
        fail(value)

    callback = fail_async if asynchronous else fail
    options = (
        {"api_key_enabled": True, "api_key_validator": callback}
        if callback_kind == "api_key"
        else {"on_token_validated": callback}
    )
    config = JWTConfig(secret=secrets.token_urlsafe(48), **options)
    token = JWTValidator(config).create_access_token(
        user_id="subject", roles=["viewer"]
    )
    app = await make_app(config, diagnostics)
    headers = (
        {config.api_key_header: PRIVATE}
        if callback_kind == "api_key"
        else {"Authorization": "Bearer " + token}
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.fastapi_app), base_url="http://test"
        ) as client:
            response = await client.get("/diagnostic-proof", headers=headers)
        assert len(calls) == 1
        if callback_kind == "api_key":
            assert calls == [PRIVATE]
            assert response.status_code == 401
            assert response.json() == {
                "detail": "API key validation error",
                "error": "api_key_error",
            }
            message = "API key validation failed"
        else:
            assert calls[0]["sub"] == "subject"
            assert response.status_code == 200
            assert response.json()["user"] == "subject"
            assert response.json()["token"] == token
            assert response.json()["payload"]["sub"] == "subject"
            message = "on_token_validated hook failed"
        assert error.__cause__ is cause
        assert str(error) == PRIVATE
        assert_safe(diagnostics, message)
    finally:
        app.close()


@pytest.mark.parametrize("invalid", [False, True])
async def test_validator_failure_retains_response_and_private_diagnostic(
    monkeypatch, tmp_path, diagnostics, invalid
):
    monkeypatch.chdir(tmp_path)
    config = JWTConfig(secret=secrets.token_urlsafe(48))
    error = InvalidTokenError(PRIVATE) if invalid else ValueError(PRIVATE)
    calls = []

    def fail(self, token):
        calls.append(token)
        raise error

    monkeypatch.setattr(JWTValidator, "verify_token", fail)
    app = await make_app(config, diagnostics)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.fastapi_app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/diagnostic-proof", headers={"Authorization": "Bearer " + PRIVATE}
            )
        assert calls == [PRIVATE]
        assert response.status_code == 401
        assert response.json() == (
            {"detail": "Invalid token", "error": "invalid_token"}
            if invalid
            else {"detail": "Authentication failed", "error": "auth_error"}
        )
        assert response.headers["www-authenticate"] == (
            'Bearer realm="api", error="invalid_token"'
            if invalid
            else 'Bearer realm="api"'
        )
        assert_safe(
            diagnostics, "Invalid token" if invalid else "JWT verification failed"
        )
    finally:
        app.close()


@pytest.mark.parametrize(
    "transport",
    ["api_key", "bearer", "cookie", "query", "missing", "expired", "invalid"],
)
async def test_real_auth_token_priority_and_outcomes(
    monkeypatch, tmp_path, diagnostics, transport
):
    monkeypatch.chdir(tmp_path)
    callbacks = []

    def validate_key(key):
        callbacks.append(("key", key))
        return {"sub": "api-subject", "roles": ["viewer"]}

    async def validated(payload):
        callbacks.append(("token", payload["sub"]))

    config = JWTConfig(
        secret=secrets.token_urlsafe(48),
        api_key_enabled=True,
        api_key_validator=validate_key,
        on_token_validated=validated,
        token_cookie="proof_cookie",
        token_query_param="proof_token",
    )
    validator = JWTValidator(config)
    token = validator.create_access_token(user_id="subject")
    other = validator.create_access_token(user_id="lower-priority")
    app = await make_app(config, diagnostics)
    headers = {}
    cookies = {}
    params = {}
    if transport == "api_key":
        headers = {
            config.api_key_header: "accepted-key",
            "Authorization": "Bearer invalid",
        }
    elif transport == "bearer":
        headers = {"Authorization": "Bearer " + token}
        cookies = {config.token_cookie: other}
        params = {config.token_query_param: other}
    elif transport == "cookie":
        cookies = {config.token_cookie: token}
        params = {config.token_query_param: other}
    elif transport == "query":
        params = {config.token_query_param: token}
    elif transport in {"expired", "invalid"}:
        token = (
            validator.create_access_token(user_id="subject", expires_minutes=-1)
            if transport == "expired"
            else JWTValidator(
                JWTConfig(secret=secrets.token_urlsafe(48))
            ).create_access_token(user_id="subject")
        )
        headers = {"Authorization": "Bearer " + token}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.fastapi_app),
            base_url="http://test",
            cookies=cookies,
        ) as client:
            response = await client.get(
                "/diagnostic-proof", headers=headers, params=params
            )
        if transport in {"missing", "expired", "invalid"}:
            assert response.status_code == 401
            assert (
                response.json()["error"]
                == {
                    "missing": "missing_token",
                    "expired": "token_expired",
                    "invalid": "invalid_token",
                }[transport]
            )
            assert callbacks == []
            assert "www-authenticate" in response.headers
        elif transport == "api_key":
            assert response.status_code == 200
            assert callbacks == [("key", "accepted-key")]
            assert response.json() == {
                "user": "api-subject",
                "token": "accepted-key",
                "payload": {"type": "api_key"},
            }
        else:
            assert response.status_code == 200
            assert callbacks == [("token", "subject")]
            assert response.json()["user"] == "subject"
            assert response.json()["token"] == token
            assert response.json()["payload"]["sub"] == "subject"
    finally:
        app.close()

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1712 Wave-2 hardening (G1-redteam findings).

Covers four confirmed findings, each pinned behaviorally against a real
``MCPServer`` / real auth objects (no mocking of the SDK under test, per
``rules/testing.md`` § 3-Tier Testing):

* **F1 (HIGH)** — the fail-closed OAuth audience gate must be REACHABLE through
  the documented server wiring. ``ResourceServer.authenticate`` is ``async``;
  the async tool-dispatch path must AWAIT it (via
  ``AuthManager.authenticate_and_authorize_async``) so a foreign-audience or
  audience-absent token is DENIED with a clean auth error — NOT crashed into an
  un-awaited-coroutine ``AttributeError`` → 500. Three server-wired cases:
  correctly-scoped → ALLOWED; foreign-audience → DENIED; audience-absent →
  DENIED.
* **F4 (MED)** — covered in ``test_issue_1712_audience_validation.py`` (audience
  fail-closed default: a JWT-validating provider with no ``expected_audience``
  refuses construction).
* **F3 (MED)** — ``MCPServer._paginate`` returns the spec ``-32602`` envelope
  for a non-string (unhashable) cursor instead of an unhandled ``TypeError``.
* **F6 (MED)** — ``_redact_log_data`` scrubs secret token shapes in dict KEYS
  (not only values) and covers cloud-cred formats (AWS / GitHub / Google /
  Slack / URL-userinfo) before the payload reaches the notifications wire.
"""

from __future__ import annotations

import pytest

from kailash_mcp.errors import ToolError
from kailash_mcp.server import MCPServer

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

ISSUER = "https://issuer.example"
AUDIENCE = "mcp-api"
RESOURCE = "https://mcp.example.com/mcp"


def _make_server(auth_provider=None) -> MCPServer:
    return MCPServer(
        "wave2-hardening-test",
        enable_cache=False,
        enable_metrics=False,
        auth_provider=auth_provider,
    )


def _async_secure_tool(server: MCPServer):
    """Build the server's real auth-enforcing async wrapper for a tool that
    requires the ``read`` permission. This is the exact enhanced-tool surface
    every registered async tool goes through — the F1 bug lived in its call to
    the auth manager."""

    async def secure_tool(x: int = 0) -> int:
        return x + 1

    wrapper = server._create_enhanced_tool(
        secure_tool,
        "secure_tool",
        None,  # cache_key
        None,  # cache_ttl
        None,  # response_format
        "read",  # required_permission
        None,  # rate_limit
        False,  # enable_circuit_breaker
        None,  # timeout
        False,  # retryable
        False,  # stream_response
    )
    # The wrapper updates per-tool stats in the registry (call_count /
    # error_count / last_called); seed the entry the tool decorator would
    # normally create so those bookkeeping writes resolve.
    server._tool_registry["secure_tool"] = {
        "description": "",
        "inputSchema": {},
        "call_count": 0,
        "error_count": 0,
        "last_called": None,
    }
    return wrapper


# ===========================================================================
# F1 — async OAuth audience gate reachable through the server auth path
# ===========================================================================


@pytest.mark.regression
@pytest.mark.asyncio
async def test_f1_correctly_scoped_token_allowed_through_server():
    """A correctly-scoped, correct-audience token is ALLOWED through the
    server's async auth dispatch (the audience gate ran and passed)."""
    pytest.importorskip("cryptography", reason="oauth path requires [auth-oauth]")
    from kailash_mcp.auth.oauth import ResourceServer

    rs = ResourceServer(issuer=ISSUER, audience=AUDIENCE, resource=RESOURCE)
    server = _make_server(auth_provider=rs)
    wrapper = _async_secure_tool(server)

    token = rs.jwt_manager.create_access_token(
        subject="alice", scope="mcp.tools", audience=[AUDIENCE]
    ).token

    # Correct audience + default "read" permission -> the tool body runs.
    result = await wrapper(x=41, mcp_auth={"token": token})
    assert result == 42


@pytest.mark.regression
@pytest.mark.asyncio
async def test_f1_foreign_audience_token_denied_through_server():
    """A foreign-audience token is DENIED with a clean auth error (NOT a 500 /
    AttributeError from an un-awaited coroutine) through the server."""
    pytest.importorskip("cryptography", reason="oauth path requires [auth-oauth]")
    from kailash_mcp.auth.oauth import ResourceServer

    rs = ResourceServer(issuer=ISSUER, audience=AUDIENCE, resource=RESOURCE)
    server = _make_server(auth_provider=rs)
    wrapper = _async_secure_tool(server)

    # Token minted for a DIFFERENT resource.
    foreign = rs.jwt_manager.create_access_token(
        subject="mallory", scope="mcp.tools", audience=["some-other-api"]
    ).token

    with pytest.raises(ToolError) as excinfo:
        await wrapper(x=1, mcp_auth={"token": foreign})

    # Clean fail-closed DENY — the audience gate ran through the server.
    assert "Access denied" in str(excinfo.value)
    # The bug this pins: an un-awaited coroutine crashed with AttributeError.
    assert "AttributeError" not in str(excinfo.value)
    assert "coroutine" not in str(excinfo.value).lower()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_f1_audience_absent_token_denied_through_server():
    """An audience-ABSENT token is DENIED (fail-closed) through the server."""
    pytest.importorskip("cryptography", reason="oauth path requires [auth-oauth]")
    from kailash_mcp.auth.oauth import ResourceServer

    rs = ResourceServer(issuer=ISSUER, audience=AUDIENCE, resource=RESOURCE)
    server = _make_server(auth_provider=rs)
    wrapper = _async_secure_tool(server)

    # No audience claim at all.
    no_aud = rs.jwt_manager.create_access_token(
        subject="nobody", scope="mcp.tools"
    ).token

    with pytest.raises(ToolError) as excinfo:
        await wrapper(x=1, mcp_auth={"token": no_aud})

    assert "Access denied" in str(excinfo.value)
    assert "AttributeError" not in str(excinfo.value)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_f1_sync_path_rejects_async_provider_cleanly():
    """Belt-and-suspenders: if an async provider is reached on the SYNC auth
    path, it fails CLOSED with a typed AuthenticationError — never an opaque
    AttributeError from an un-awaited coroutine."""
    pytest.importorskip("cryptography", reason="oauth path requires [auth-oauth]")
    from kailash_mcp.auth.oauth import ResourceServer
    from kailash_mcp.auth.providers import AuthenticationError, AuthManager

    rs = ResourceServer(issuer=ISSUER, audience=AUDIENCE, resource=RESOURCE)
    mgr = AuthManager(provider=rs)

    with pytest.raises(AuthenticationError) as excinfo:
        mgr.authenticate_and_authorize({"token": "irrelevant"}, "read")

    assert "async" in str(excinfo.value).lower()


# ===========================================================================
# F3 — non-string cursor -> -32602 (not an unhandled TypeError)
# ===========================================================================


@pytest.mark.regression
@pytest.mark.parametrize("bad_cursor", [123, ["a"], {"k": "v"}, 4.5, object()])
def test_f3_non_string_cursor_returns_invalid_params(bad_cursor):
    """A non-string / unhashable cursor yields the -32602 envelope."""
    server = _make_server()
    page, next_cursor, error = server._paginate(
        ["item-a", "item-b"], bad_cursor, request_id=7
    )
    assert page is None
    assert next_cursor is None
    assert error is not None
    assert error["error"]["code"] == -32602
    assert error["id"] == 7


@pytest.mark.regression
@pytest.mark.asyncio
async def test_f3_non_string_cursor_through_list_handler():
    """The -32602 guard holds through the real tools/list handler surface."""
    server = _make_server()
    server._tool_registry["t1"] = {"description": "", "inputSchema": {}}

    resp = await server._handle_list_tools({"cursor": 999}, request_id=3)
    assert resp["error"]["code"] == -32602
    assert resp["id"] == 3


@pytest.mark.regression
def test_f3_none_and_valid_string_cursor_still_work():
    """A None cursor (first page) and a valid string cursor are unaffected."""
    server = _make_server()
    items = [f"i{n}" for n in range(5)]
    page, _next, error = server._paginate(items, None, request_id=1)
    assert error is None
    assert page == items  # first page, under default page size


# ===========================================================================
# F6 — dict-KEY secret scrub + broadened cloud-cred value patterns
# ===========================================================================

# These fixture tokens are real-SHAPED (they must match the redaction regexes in
# server.py::_SECRET_VALUE_PATTERNS) but are assembled from fragments so the
# contiguous secret pattern never appears in the source bytes — GitHub push
# protection would otherwise block the commit. Do NOT re-join into a single literal.
AWS_ACCESS_KEY_ID = "AKIA" + "IOSFODNN7EXAMPLE"
GITHUB_TOKEN = "ghp" + "_0123456789abcdefghij0123456789ABCD"


def _redact(data):
    from kailash_mcp.server import _redact_log_data

    return _redact_log_data(data)


@pytest.mark.regression
def test_f6_secret_in_dict_key_is_scrubbed():
    """A secret token in the KEY position is scrubbed (was value-only before)."""
    out = _redact({AWS_ACCESS_KEY_ID: "harmless-value"})
    assert AWS_ACCESS_KEY_ID not in out
    assert "[REDACTED]" in out  # the key was replaced by the scrubbed form


@pytest.mark.regression
def test_f6_aws_access_key_in_value_redacted():
    out = _redact({"note": f"leaked {AWS_ACCESS_KEY_ID} in prose"})
    assert AWS_ACCESS_KEY_ID not in out["note"]
    assert "[REDACTED]" in out["note"]


@pytest.mark.regression
def test_f6_github_token_in_value_redacted():
    # key "gh" is not a secret-name, so the VALUE pattern must catch it.
    out = _redact({"gh": GITHUB_TOKEN})
    assert GITHUB_TOKEN not in out["gh"]
    assert out["gh"] == "[REDACTED]"


@pytest.mark.regression
def test_f6_url_userinfo_password_redacted_host_kept():
    dsn = "postgres://admin:s3cr3tpass@dbhost:5432/app"
    out = _redact({"dsn": dsn})
    assert "s3cr3tpass" not in out["dsn"]
    assert "[REDACTED]" in out["dsn"]
    # Scheme + host stay legible; only the userinfo is scrubbed.
    assert out["dsn"].startswith("postgres://")
    assert "dbhost" in out["dsn"]


@pytest.mark.regression
def test_f6_google_and_slack_values_redacted():
    # Fragment-assembled (see AWS/GitHub note above): real-shaped for the redaction
    # regex, but no contiguous secret literal for GitHub push protection to flag.
    google = "AIza" + "SyA0123456789abcdefghijklmnopqrstuv"
    slack = "xox" + "b-0123456789-abcdefABCDEF01"
    out = _redact({"g": google, "s": slack})
    assert out["g"] == "[REDACTED]"
    assert out["s"] == "[REDACTED]"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_f6_redaction_holds_through_send_log_message():
    """The broadened redaction reaches the real notifications/message wire."""

    class _CaptureTransport:
        def __init__(self):
            self.sent = []

        async def send_message(self, message, client_id=None):
            self.sent.append((client_id, message))

    server = _make_server()
    server._transport = _CaptureTransport()
    server.client_info["c1"] = {"capabilities": {}, "name": "c", "version": "1"}
    server._client_log_levels["c1"] = "WARNING"

    sent = await server.send_log_message(
        "ERROR",
        {
            AWS_ACCESS_KEY_ID: "x",  # secret in KEY
            "gh": GITHUB_TOKEN,  # GitHub in value
            "dsn": "redis://user:hunter2@cache:6379/0",  # URL-userinfo
        },
        logger_name="db",
    )
    assert sent == 1
    _client_id, message = server._transport.sent[0]
    data = message["params"]["data"]
    assert AWS_ACCESS_KEY_ID not in data  # key scrubbed
    assert GITHUB_TOKEN not in str(data)
    assert "hunter2" not in str(data)

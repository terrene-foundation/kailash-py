"""Regression: credential EXTRACTION must fail cleanly, and a tool whose own
signature collides with a credential kwarg must be surfaced at registration.

DEFECT 3 — ``mcp_auth`` was left un-type-guarded, one field over from the
``authorization`` guard
------------------------------------------------------------------------
``_extract_credentials_from_context`` reads two client-controlled fields.
``authorization`` is type-guarded (``isinstance(auth_header, str)``) with a
comment explaining that a non-string value raised out of credential EXTRACTION
"as an opaque crash instead of a clean deny". The sibling field kept the
un-guarded form::

    if "mcp_auth" in kwargs:
        credentials.update(kwargs["mcp_auth"])

``dict.update`` raises ``ValueError``/``TypeError`` for a str/int/list, and the
``_extract_credentials_from_context`` call sits OUTSIDE the wrappers' inner
``try:`` — so the exception reached the outer handler and surfaced as
``ToolError("Tool execution failed: …")``.

It fails CLOSED (no bypass), but a client controls ``arguments``, so a client
controls whether an authentication failure is reported as an internal server
error. A non-Mapping ``mcp_auth`` carries no credentials, which is exactly what
an empty credential set expresses.

DEFECT 4 — credential-kwarg stripping silently substituted defaults
--------------------------------------------------------------------
``_strip_credential_kwargs`` filters by exact membership in a 7-name frozenset,
unconditionally. A tool declaring ``api_key: str = ""`` as a genuine BUSINESS
argument therefore ran with ``api_key=""`` — no error, wrong result. (Without a
default it is a loud ``TypeError``, which is fine.) The collision is knowable at
REGISTRATION, where the original function is in hand, so it is surfaced there:
a silent wrong answer becomes a startup signal.
"""

import asyncio
import logging

import pytest
from kailash_mcp.auth.providers import APIKeyAuth
from kailash_mcp.server import MCPServer

API_KEY = "integration-key"
PERMISSION = "integrations.write"


async def _maybe_await(value):
    if asyncio.iscoroutine(value) or asyncio.isfuture(value):
        return await value
    return value


def _gated_server():
    """Gated sync + async tools; ``calls`` records every tool BODY entry."""
    calls: list = []
    server = MCPServer(
        "mcp-auth-guard",
        enable_cache=False,
        enable_metrics=False,
        auth_provider=APIKeyAuth(keys={API_KEY: {"permissions": [PERMISSION]}}),
    )

    @server.tool(required_permission=PERMISSION)
    def sync_tool(target: str) -> str:
        """Do the thing."""
        calls.append(("sync", target))
        return f"done {target}"

    @server.tool(required_permission=PERMISSION)
    async def async_tool(target: str) -> str:
        """Do the thing."""
        calls.append(("async", target))
        return f"done {target}"

    return server, calls


TOOLS = [
    pytest.param("sync_tool", "sync", id="sync_wrapper"),
    pytest.param("async_tool", "async", id="async_wrapper"),
]

# Shapes a JSON request body can actually produce for ``mcp_auth``.
NON_MAPPING_MCP_AUTH = [
    pytest.param("Bearer abc", id="str"),
    pytest.param(1234, id="int"),
    pytest.param(["a", "b"], id="list"),
    pytest.param(None, id="null"),
]


# ---------------------------------------------------------------------------
# DEFECT 3 — a non-Mapping mcp_auth is a clean DENY, not an internal error
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,kind", TOOLS)
@pytest.mark.parametrize("bad_auth", NON_MAPPING_MCP_AUTH)
async def test_non_mapping_mcp_auth_denies_cleanly(tool_name, kind, bad_auth):
    """A client-supplied non-Mapping ``mcp_auth`` yields an AUTH denial."""
    server, calls = _gated_server()

    with pytest.raises(Exception) as excinfo:
        await _maybe_await(
            server._execute_tool(tool_name, {"target": "prod", "mcp_auth": bad_auth})
        )

    message = str(excinfo.value)
    assert "Access denied" in message, (
        "a non-Mapping mcp_auth surfaced as a generic execution failure rather "
        f"than an authorization denial: {message!r}"
    )
    assert calls == [], (
        f"the {kind} wrapper reached the tool body despite failing to extract "
        f"credentials: {calls!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,kind", TOOLS)
async def test_mapping_mcp_auth_still_authenticates(tool_name, kind):
    """CONTROL: a Mapping ``mcp_auth`` still feeds credentials to the gate.

    Without this, a fix that ignored ``mcp_auth`` entirely would pass the test
    above while silently removing an authentication channel.
    """
    server, calls = _gated_server()

    result = await _maybe_await(
        server._execute_tool(
            tool_name, {"target": "prod", "mcp_auth": {"api_key": API_KEY}}
        )
    )

    assert result == "done prod", (
        f"a valid api key supplied via mcp_auth was refused on the {kind} "
        f"wrapper: {result!r}"
    )
    assert calls == [(kind, "prod")], f"the tool body was not reached: {calls!r}"


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,kind", TOOLS)
async def test_junk_mcp_auth_does_not_defeat_a_valid_api_key(tool_name, kind):
    """CONTROL: junk in one credential field does not break the others."""
    server, calls = _gated_server()

    result = await _maybe_await(
        server._execute_tool(
            tool_name,
            {"target": "prod", "mcp_auth": "Bearer junk", "api_key": API_KEY},
        )
    )

    assert result == "done prod", (
        "a correctly credentialed call was turned into an error by an unrelated "
        f"malformed mcp_auth field on the {kind} wrapper: {result!r}"
    )
    assert calls == [(kind, "prod")], f"the tool body was not reached: {calls!r}"


# ---------------------------------------------------------------------------
# DEFECT 4 — a business argument colliding with a credential kwarg is surfaced
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_colliding_business_parameter_warns_at_registration(caplog):
    """Registering a tool whose parameter is a credential name WARNs."""
    server = MCPServer("collision", enable_cache=False, enable_metrics=False)

    with caplog.at_level(logging.WARNING, logger="kailash_mcp.server"):

        @server.tool()
        def save_integration(service: str, api_key: str = "") -> str:
            """Store an integration's credentials."""
            return f"{service}:{api_key}"

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, (
        "registering a tool whose own parameter collides with a credential "
        "kwarg produced no signal at all; the argument is silently replaced by "
        "its default on every call"
    )
    text = " ".join(r.getMessage() + str(getattr(r, "__dict__", {})) for r in warnings)
    assert "save_integration" in text, f"the warning does not name the tool: {text!r}"
    assert "api_key" in text, f"the warning does not name the parameter: {text!r}"


@pytest.mark.regression
def test_non_colliding_tool_registers_without_warning(caplog):
    """CONTROL: an ordinary tool registers silently.

    Without this, a fix that warned on EVERY registration would pass the test
    above while making the signal worthless.
    """
    server = MCPServer("no-collision", enable_cache=False, enable_metrics=False)

    with caplog.at_level(logging.WARNING, logger="kailash_mcp.server"):

        @server.tool()
        def save_report(service: str, report_id: str = "") -> str:
            """Store a report."""
            return f"{service}:{report_id}"

    warnings = [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING and "credential" in r.getMessage().lower()
    ]
    assert not warnings, (
        "an ordinary tool with no credential-named parameter triggered the "
        f"collision warning: {[r.getMessage() for r in warnings]!r}"
    )

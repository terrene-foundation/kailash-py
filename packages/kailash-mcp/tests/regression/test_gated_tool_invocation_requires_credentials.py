"""Regression: a permission-gated tool MUST NOT execute for a caller carrying
no credentials — on EITHER wrapper, over EVERY transport.

Two independent defects converged on the same outcome (the tool body running
for an anonymous caller), and neither was visible to the suites that existed.

DEFECT 1 — an unconditional no-credential bypass in the ASYNC wrapper
---------------------------------------------------------------------
``_create_enhanced_tool``'s ``async_wrapper`` carried::

    if not credentials and not any(k.startswith("mcp_") for k in kwargs):
        user_info = None          # ... and then EXECUTED the tool

The bypass condition was ATTACKER-CHOSEN: send credentials and you are
authenticated (and possibly denied); send NONE and the gate was skipped
entirely. The comment called it "development/testing", but nothing scoped it to
development — it was the production dispatch path.

The SYNC wrapper never had this branch: it goes straight to
``authenticate_and_authorize`` and raises. So the two wrappers had DIFFERENT
authorization semantics for the same decorator argument — an
enforcement-surface-parity break (``security.md`` § Enforcement-Surface Parity)
that no test could see, because nothing exercised the two wrappers together.
This suite is therefore parametrized over BOTH.

Reachability: before ``19c8cfb33`` the stdio ``tools/call`` branch read
``_tool_registry[name]["handler"]`` — a key the tool decorator never writes — so
stdio raised ``KeyError`` and was ACCIDENTALLY fail-closed. Routing it through
``_execute_tool`` fixed that crash and, in doing so, made this bypass reachable
over stdio. It was ALREADY reachable anonymously over WebSocket, whose
``handle_client`` never consults ``auth_provider``.

DEFECT 2 — a falsy-but-not-None ``auth_provider`` silently disabled enforcement
------------------------------------------------------------------------------
``MCPServer.__init__`` REPORTED auth status by identity
(``auth_provider is not None``) but ENFORCED it by truthiness
(``if auth_provider:``). ``AuthProvider`` is a user-subclassable ABC, so a
provider defining ``__len__``/``__bool__`` (an empty key-ring, a health-gated
provider, a policy set mid-rotation) reported ``auth.enabled == True`` while
``auth_manager`` was ``None`` — disabling authorization, rate limiting, AND the
``tools/list`` schema suppression at once.

WHY THE ASSERTIONS ARE SIDE-EFFECT-BASED
----------------------------------------
Every test below asserts on a MARKER the tool body appends to, not merely on the
shape of the returned error. "The call returned an error" is consistent with
both "the gate refused" and "the tool ran and then something else failed"; only
the marker distinguishes them. Each test also carries a CONTROL asserting the
CREDENTIALED call DOES run, so a server that refuses everything cannot make the
suite pass vacuously.
"""

import asyncio
import io
import json

import pytest

from kailash_mcp.auth.providers import APIKeyAuth
from kailash_mcp.errors import ToolError
from kailash_mcp.server import MCPServer

API_KEY = "admin-key"
PERMISSION = "admin.write"


# ---------------------------------------------------------------------------
# Server fixtures — one SYNC and one ASYNC gated tool on the same server, so
# every transport case below covers both wrappers.
# ---------------------------------------------------------------------------


def _gated_server():
    """Return ``(server, calls)`` where ``calls`` records every tool BODY entry.

    The marker list is the instrument: an entry in it means the tool body
    actually ran, which is the property under test. The returned error text is
    NOT sufficient evidence on its own.
    """
    calls: list = []
    server = MCPServer(
        "gated-invocation",
        enable_cache=False,
        enable_metrics=False,
        auth_provider=APIKeyAuth(keys={API_KEY: {"permissions": [PERMISSION]}}),
    )

    @server.tool(required_permission=PERMISSION)
    def admin_delete_user_sync(user_id: str) -> str:
        """Permanently delete a user account."""
        calls.append(("sync", user_id))
        return f"deleted {user_id}"

    @server.tool(required_permission=PERMISSION)
    async def admin_delete_user_async(user_id: str) -> str:
        """Permanently delete a user account."""
        calls.append(("async", user_id))
        return f"deleted {user_id}"

    return server, calls


TOOLS = [
    pytest.param("admin_delete_user_sync", "sync", id="sync_wrapper"),
    pytest.param("admin_delete_user_async", "async", id="async_wrapper"),
]


async def _maybe_await(value):
    if asyncio.iscoroutine(value) or asyncio.isfuture(value):
        return await value
    return value


# ---------------------------------------------------------------------------
# _execute_tool — the shared executor both stdio and the WS handler route to
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,kind", TOOLS)
async def test_execute_tool_without_credentials_is_refused(tool_name, kind):
    """No credentials -> the gated tool body MUST NOT run, on either wrapper."""
    server, calls = _gated_server()

    with pytest.raises((ToolError, Exception)) as excinfo:
        await _maybe_await(server._execute_tool(tool_name, {"user_id": "victim"}))

    assert "Access denied" in str(excinfo.value), (
        "an uncredentialed call to a permission-gated tool did not fail with an "
        f"authorization error: {excinfo.value!r}"
    )
    assert calls == [], (
        f"the {kind} wrapper EXECUTED a permission-gated tool for a caller that "
        f"supplied no credentials at all: {calls!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,kind", TOOLS)
async def test_execute_tool_with_valid_credentials_still_runs(tool_name, kind):
    """CONTROL: the gate is scoped to authorization, not a blanket refusal."""
    server, calls = _gated_server()

    result = await _maybe_await(
        server._execute_tool(tool_name, {"user_id": "victim", "api_key": API_KEY})
    )

    assert result == "deleted victim", (
        f"a correctly credentialed call to the {kind} wrapper was refused; the "
        f"fix must deny only UNAUTHORIZED callers: {result!r}"
    )
    assert calls == [
        (kind, "victim")
    ], f"the credentialed call did not reach the {kind} tool body: {calls!r}"


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,kind", TOOLS)
async def test_execute_tool_with_wrong_credentials_is_refused(tool_name, kind):
    """A WRONG key is refused — distinguishing 'gate ran' from 'gate absent'."""
    server, calls = _gated_server()

    with pytest.raises((ToolError, Exception)) as excinfo:
        await _maybe_await(
            server._execute_tool(
                tool_name, {"user_id": "victim", "api_key": "not-the-key"}
            )
        )

    assert "Access denied" in str(excinfo.value)
    assert calls == [], f"a bad-key call reached the {kind} tool body: {calls!r}"


# ---------------------------------------------------------------------------
# stdio tools/call — the surface 19c8cfb33 newly routed through _execute_tool
# ---------------------------------------------------------------------------


async def _drive_stdio(server, requests):
    """Drive the real ``run_stdio`` loop over a canned stdin; return responses."""
    import sys

    payload = "".join(json.dumps(r) + "\n" for r in requests)
    stdin, stdout = io.StringIO(payload), io.StringIO()
    real_stdin, real_stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = stdin, stdout
    try:
        await asyncio.wait_for(server.run_stdio(), timeout=10)
    finally:
        sys.stdin, sys.stdout = real_stdin, real_stdout
    return [json.loads(line) for line in stdout.getvalue().strip().splitlines() if line]


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,kind", TOOLS)
async def test_stdio_tools_call_without_credentials_is_refused(tool_name, kind):
    """The documented attack, at the stdio wire: no api_key, no ``mcp_*`` key."""
    server, calls = _gated_server()

    responses = await _drive_stdio(
        server,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": {"user_id": "victim"}},
            }
        ],
    )

    # CONTROL: the request was actually processed (a silently-dropped request
    # would satisfy the marker assertion vacuously).
    assert len(responses) == 1, f"stdio produced no response at all: {responses!r}"
    assert calls == [], (
        f"stdio tools/call EXECUTED the gated {kind} tool with NO credentials: "
        f"{calls!r} / {responses!r}"
    )
    assert "deleted" not in json.dumps(responses), (
        "the stdio response carried the tool's successful result for an "
        f"uncredentialed caller: {responses!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,kind", TOOLS)
async def test_stdio_tools_call_with_credentials_still_runs(tool_name, kind):
    """CONTROL at the stdio wire: a credentialed call succeeds."""
    server, calls = _gated_server()

    responses = await _drive_stdio(
        server,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": {"user_id": "victim", "api_key": API_KEY},
                },
            }
        ],
    )

    assert calls == [
        (kind, "victim")
    ], f"a credentialed stdio call did not reach the {kind} tool body: {calls!r}"
    assert "deleted victim" in json.dumps(responses)


# ---------------------------------------------------------------------------
# WebSocket tools/call — _handle_call_tool, reachable with no credentials
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,kind", TOOLS)
async def test_ws_call_tool_without_credentials_is_refused(tool_name, kind):
    """``handle_client`` never consults ``auth_provider`` — the tool gate is the
    ONLY boundary on this path, so it must hold."""
    server, calls = _gated_server()

    response = await server._handle_call_tool(
        {"name": tool_name, "arguments": {"user_id": "victim"}}, 1, "anon-client"
    )

    assert response is not None, "the WS handler returned no response at all"
    assert calls == [], (
        f"WS tools/call EXECUTED the gated {kind} tool with NO credentials: "
        f"{calls!r} / {response!r}"
    )
    assert response["result"].get("isError") is True, (
        "an uncredentialed WS tools/call did not surface as an error result: "
        f"{response!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,kind", TOOLS)
async def test_ws_call_tool_with_credentials_still_runs(tool_name, kind):
    """CONTROL at the WS handler: a credentialed call succeeds."""
    server, calls = _gated_server()

    response = await server._handle_call_tool(
        {"name": tool_name, "arguments": {"user_id": "victim", "api_key": API_KEY}},
        1,
        "anon-client",
    )

    assert calls == [
        (kind, "victim")
    ], f"a credentialed WS call did not reach the {kind} tool body: {calls!r}"
    assert response["result"].get("isError") is not True, response


# ---------------------------------------------------------------------------
# The ``mcp_*`` escape hatch the old bypass keyed on
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,kind", TOOLS)
async def test_empty_mcp_auth_does_not_authorize(tool_name, kind):
    """An EMPTY ``mcp_auth`` yields no credentials and must still be refused.

    The old bypass keyed on ``any(k.startswith("mcp_"))``, so the presence of
    the key alone decided which branch ran. Neither branch may authorize an
    empty credential set.
    """
    server, calls = _gated_server()

    with pytest.raises((ToolError, Exception)):
        await _maybe_await(
            server._execute_tool(tool_name, {"user_id": "victim", "mcp_auth": {}})
        )

    assert calls == [], f"an empty mcp_auth authorized the {kind} tool: {calls!r}"


# ---------------------------------------------------------------------------
# Falsy-but-not-None auth_provider (DEFECT 2)
# ---------------------------------------------------------------------------


class _EmptyKeyRingAuth(APIKeyAuth):
    """A realistic falsy provider: an API-key provider whose ring is empty.

    ``AuthProvider`` is a public, user-subclassable ABC and nothing forbids a
    container-like provider from defining ``__len__``. An empty ring is exactly
    the state a provider is in mid-rotation or before its first key load.
    """

    def __len__(self) -> int:
        return len(self.keys) if getattr(self, "keys", None) else 0


class _HealthGatedAuth(APIKeyAuth):
    """A provider that reports itself unhealthy via ``__bool__``."""

    healthy = False

    def __bool__(self) -> bool:
        return self.healthy


@pytest.fixture(
    params=[
        pytest.param(_EmptyKeyRingAuth, id="dunder_len_zero"),
        pytest.param(_HealthGatedAuth, id="dunder_bool_false"),
    ]
)
def falsy_provider(request):
    provider = request.param(keys={API_KEY: {"permissions": [PERMISSION]}})
    if isinstance(provider, _EmptyKeyRingAuth):
        provider.keys = {}
    assert not provider, "fixture must be FALSY to exercise the defect"
    assert provider is not None
    return provider


@pytest.mark.regression
def test_falsy_auth_provider_still_builds_an_auth_manager(falsy_provider):
    """Enforcement must key on identity, matching what the config REPORTS."""
    server = MCPServer("falsy-auth", auth_provider=falsy_provider)

    assert server.config.get("auth.enabled") is True, (
        "the config no longer reports auth as enabled; this test pins the "
        "identity-vs-truthiness AGREEMENT, not one particular polarity"
    )
    assert server.auth_manager is not None, (
        "a falsy-but-not-None auth_provider produced auth_manager=None while "
        "the server config reported auth.enabled=True — authorization, rate "
        "limiting and schema suppression were all silently disabled"
    )


@pytest.mark.regression
def test_falsy_auth_provider_reports_provider_type(falsy_provider):
    """``provider_type`` used truthiness too, so it reported ``None``."""
    server = MCPServer("falsy-auth-type", auth_provider=falsy_provider)

    assert server.config.get("auth.provider_type") == type(falsy_provider).__name__, (
        "auth.provider_type resolved to None for a falsy provider while "
        "auth.enabled reported True"
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,kind", TOOLS)
async def test_falsy_auth_provider_still_gates_invocation(
    falsy_provider, tool_name, kind
):
    """One ``__len__`` value must not flip the invoke-path gate."""
    calls: list = []
    server = MCPServer(
        "falsy-auth-invoke", enable_cache=False, auth_provider=falsy_provider
    )

    @server.tool(required_permission=PERMISSION)
    def admin_delete_user_sync(user_id: str) -> str:
        """Permanently delete a user account."""
        calls.append(("sync", user_id))
        return "deleted"

    @server.tool(required_permission=PERMISSION)
    async def admin_delete_user_async(user_id: str) -> str:
        """Permanently delete a user account."""
        calls.append(("async", user_id))
        return "deleted"

    with pytest.raises((ToolError, Exception)):
        await _maybe_await(server._execute_tool(tool_name, {"user_id": "victim"}))

    assert calls == [], (
        f"a falsy auth_provider let the gated {kind} tool execute for an "
        f"uncredentialed caller: {calls!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_falsy_auth_provider_still_suppresses_gated_schema(falsy_provider):
    """``_public_tool_view`` gates on ``auth_manager is not None``, so a falsy
    provider that zeroed ``auth_manager`` also un-suppressed every schema."""
    server = MCPServer("falsy-auth-schema", auth_provider=falsy_provider)

    @server.tool(required_permission=PERMISSION)
    def admin_delete_user(user_id: str, hard_delete: bool = False) -> str:
        """Permanently delete a user account."""
        return "deleted"

    result = await server._handle_list_tools({}, 1)
    tools = {t["name"]: t for t in result["result"]["tools"]}

    assert "admin_delete_user" in tools, f"emitter returned nothing: {tools!r}"
    assert tools["admin_delete_user"]["inputSchema"] == {}, (
        "a falsy auth_provider re-opened the gated tool's argument surface: "
        f"{tools['admin_delete_user']!r}"
    )
    for parameter in ("user_id", "hard_delete"):
        assert parameter not in json.dumps(tools["admin_delete_user"])


@pytest.mark.regression
def test_falsy_auth_provider_still_engages_rate_limiter(falsy_provider):
    """Rate limiting is guarded by ``if rate_limit and self.auth_manager`` — the
    same truthiness that a falsy provider zeroed."""
    server = MCPServer("falsy-auth-rl", auth_provider=falsy_provider)

    assert server.auth_manager is not None
    assert server.auth_manager.rate_limiter is not None, (
        "the rate limiter is absent, so the rate-limit branch would no-op even "
        "with auth_manager present"
    )


@pytest.mark.regression
def test_none_auth_provider_still_disables_auth():
    """CONTROL: the identity fix must not turn auth ON for ``None``."""
    server = MCPServer("no-auth")

    assert server.auth_manager is None
    assert server.config.get("auth.enabled") is False
    assert server.config.get("auth.provider_type") is None


# ---------------------------------------------------------------------------
# required_permissions=[] — an empty list silently produced an UNGATED tool
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_empty_required_permissions_list_is_rejected():
    """``required_permissions=[]`` fell through every branch, leaving
    ``normalized_permission = None`` — no invoke-time check AND a fully
    published schema — with no warning. An author who wrote ``[]`` expected a
    gate; silently producing an ungated tool is the fail-OPEN reading."""
    server = MCPServer(
        "empty-perms",
        auth_provider=APIKeyAuth(keys={API_KEY: {"permissions": [PERMISSION]}}),
    )

    with pytest.raises(ValueError, match="required_permissions"):

        @server.tool(required_permissions=[])
        def admin_delete_user(user_id: str) -> str:
            """Permanently delete a user account."""
            return "deleted"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_multiple_required_permissions_all_enforced():
    """A caller holding only the FIRST of two required permissions is refused.

    The decorator previously kept ``required_permissions[0]`` and dropped the
    rest with only a ``logger.warning``, so a tool declaring two permissions was
    enforced against one.
    """
    calls: list = []
    server = MCPServer(
        "multi-perms",
        enable_cache=False,
        auth_provider=APIKeyAuth(
            keys={
                "partial-key": {"permissions": ["admin.write"]},
                "full-key": {"permissions": ["admin.write", "admin.purge"]},
            }
        ),
    )

    @server.tool(required_permissions=["admin.write", "admin.purge"])
    def admin_delete_user(user_id: str) -> str:
        """Permanently delete a user account."""
        calls.append(user_id)
        return "deleted"

    with pytest.raises((ToolError, Exception)) as excinfo:
        await _maybe_await(
            server._execute_tool(
                "admin_delete_user", {"user_id": "victim", "api_key": "partial-key"}
            )
        )
    assert "Access denied" in str(excinfo.value)
    assert calls == [], (
        "a caller holding only the FIRST of two declared permissions executed "
        f"the tool: {calls!r}"
    )

    # CONTROL: the fully-permissioned caller still succeeds.
    result = await _maybe_await(
        server._execute_tool(
            "admin_delete_user", {"user_id": "victim", "api_key": "full-key"}
        )
    )
    assert result == "deleted"
    assert calls == ["victim"]


# ---------------------------------------------------------------------------
# Description trim — reST/Sphinx and epytext parameter markup
# ---------------------------------------------------------------------------


DOCSTRING_STYLES = [
    pytest.param(
        "Permanently delete a user account.\n\n"
        ":param user_id: The account to delete.\n"
        ":param hard_delete: Skip the recycle bin.\n"
        ":type user_id: str\n",
        id="rest_sphinx",
    ),
    pytest.param(
        "Permanently delete a user account.\n\n"
        "@param user_id: The account to delete.\n"
        "@param hard_delete: Skip the recycle bin.\n"
        "@type user_id: str\n",
        id="epytext",
    ),
    pytest.param(
        "Permanently delete a user account.\n\n"
        "Args:\n"
        "    user_id: The account to delete.\n"
        "    hard_delete: Skip the recycle bin.\n",
        id="google",
    ),
    pytest.param(
        "Permanently delete a user account.\n\n"
        "Parameters\n"
        "----------\n"
        "user_id : str\n"
        "    The account to delete.\n"
        "hard_delete : bool\n"
        "    Skip the recycle bin.\n",
        id="numpy",
    ),
]


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("docstring", DOCSTRING_STYLES)
async def test_gated_description_trimmed_for_every_docstring_style(docstring):
    """reST (``:param``) is Sphinx's NATIVE style and epytext (``@param``) is
    common; the trim previously matched only a bare keyword-plus-colon LINE, so
    both walked straight through carrying every parameter name."""
    server = MCPServer(
        "doc-styles",
        auth_provider=APIKeyAuth(keys={API_KEY: {"permissions": [PERMISSION]}}),
    )

    @server.tool(required_permission=PERMISSION)
    def admin_delete_user(user_id: str, hard_delete: bool = False) -> str:
        return "deleted"

    admin_delete_user.__doc__ = docstring
    # Re-derive from the ORIGINAL function, matching the decorator's contract.
    from kailash_mcp.server import _derive_tool_description, _summary_before_sections

    info = server._tool_registry["admin_delete_user"]
    info["description"] = _derive_tool_description(
        info.get("original_function") or admin_delete_user
    )
    if not info["description"]:
        info["description"] = _summary_before_sections(docstring)

    result = await server._handle_list_tools({}, 1)
    tools = {t["name"]: t for t in result["result"]["tools"]}
    description = tools["admin_delete_user"]["description"]

    # CONTROL: the summary survives — the trim is scoped, not a wipe.
    assert description.startswith("Permanently delete a user account."), description
    for parameter in ("user_id", "hard_delete", ":param", "@param", "Args:"):
        assert parameter not in description, (
            f"a gated tool's advertised description disclosed {parameter!r}, "
            f"re-opening the argument surface: {description!r}"
        )


@pytest.mark.regression
@pytest.mark.parametrize("docstring", DOCSTRING_STYLES)
def test_summary_before_sections_handles_every_style(docstring):
    """Direct unit coverage of the trim helper for each markup family."""
    from kailash_mcp.server import _summary_before_sections

    trimmed = _summary_before_sections(docstring)

    assert trimmed == "Permanently delete a user account.", trimmed


@pytest.mark.regression
def test_inline_google_args_on_one_line_is_trimmed():
    """``Args: user_id (str) — ...`` on a SINGLE line never matched the
    whole-line-plus-colon pattern."""
    from kailash_mcp.server import _summary_before_sections

    trimmed = _summary_before_sections(
        "Permanently delete a user account.\n\n"
        "Args: user_id (str) - the account to delete.\n"
    )

    assert "user_id" not in trimmed, trimmed
    assert trimmed.startswith("Permanently delete a user account.")


@pytest.mark.regression
def test_prose_description_is_not_trimmed():
    """CONTROL: the trim must not eat ordinary prose that happens to contain a
    colon or an ``@`` — otherwise every description collapses to one line."""
    from kailash_mcp.server import _summary_before_sections

    doc = (
        "Permanently delete a user account.\n\n"
        "Note that deletion is irreversible: there is no recycle bin.\n"
        "Contact ops@example.com before running this in production.\n"
    )

    assert _summary_before_sections(doc) == doc.strip()


# ---------------------------------------------------------------------------
# Service-discovery capability enumeration — the FOURTH registry reader
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_registry_capabilities_exclude_disabled_tools():
    """``ServiceRegistryIntegration._discover_capabilities`` read
    ``_tool_registry.keys()`` directly, so it advertised ``disable_tool()``-
    disabled tools to the service-discovery backend — bypassing
    ``_public_tool_view``, whose docstring claims to own every such projection.
    """
    from kailash_mcp.discovery.registry_integration import ServerRegistrar

    server, _ = _gated_server()

    @server.tool()
    def public_ping() -> str:
        """Public health check."""
        return "pong"

    server.disable_tool("public_ping")

    registrar = ServerRegistrar(server)
    capabilities = await registrar._discover_capabilities()

    # CONTROL: enabled tools ARE still advertised.
    assert "admin_delete_user_sync" in capabilities, (
        "capability discovery dropped the enabled tools too; the assertion "
        f"below would pass vacuously: {capabilities!r}"
    )
    assert "public_ping" not in capabilities, (
        "service discovery advertised a tool that disable_tool() turned off: "
        f"{capabilities!r}"
    )


# ---------------------------------------------------------------------------
# Non-string authorization header
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.parametrize("bad_header", [123, 4.5, True, ["Bearer x"], {"a": 1}, None])
def test_non_string_authorization_header_does_not_raise(bad_header):
    """``kwargs["authorization"].startswith(...)`` ran OUTSIDE the try, so a
    non-string value raised ``AttributeError`` from credential extraction rather
    than yielding an empty credential set."""
    server = MCPServer("bad-auth-header")

    credentials = server._extract_credentials_from_context(
        {"authorization": bad_header}
    )

    assert "token" not in credentials, credentials
    assert "username" not in credentials, credentials


@pytest.mark.regression
def test_string_authorization_header_still_parsed():
    """CONTROL: a well-formed Bearer header still yields a token."""
    server = MCPServer("good-auth-header")

    credentials = server._extract_credentials_from_context(
        {"authorization": "Bearer abc123"}
    )

    assert credentials["token"] == "abc123"


# ---------------------------------------------------------------------------
# Structural invariant — a FIFTH registry enumerator must not land silently
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_every_registry_enumerator_is_accounted_for():
    """Pin the set of code sites that ENUMERATE ``_tool_registry``.

    ``_public_tool_view``'s docstring says every surface enumerating the
    registry for a caller must route through it. That claim was enforced by
    nothing, and it was already false: a FOURTH enumerator lived in
    ``discovery/registry_integration.py`` and the sweep that found the first
    three was scoped to ``server.py`` alone, so it structurally could not see it.

    This test re-derives the enumerator set from the AST at PACKAGE scope. A new
    enumerator fails it, forcing the author to either route through
    ``_public_tool_view`` or record here why the site is not caller-facing.
    """
    import ast
    import pathlib

    import kailash_mcp

    root = pathlib.Path(kailash_mcp.__file__).parent
    found = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(), str(path))
        for node in ast.walk(tree):
            # `<something>._tool_registry.<method>()` where the method iterates
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr not in {"items", "keys", "values"}:
                continue
            inner = func.value
            if isinstance(inner, ast.Attribute) and inner.attr == "_tool_registry":
                found.add((str(path.relative_to(root)), func.attr))

    # Every enumerator, with its disposition. CALLER-FACING sites route through
    # _public_tool_view; the rest are operator/in-process surfaces that no
    # JSON-RPC method dispatches to (verified: the wire method table carries
    # tools/list, tools/call and completion/complete, never get_*_stats).
    expected = {
        # --- caller-facing: MUST route through _public_tool_view ---
        ("server.py", "items"),  # _handle_list_tools + completion + run_stdio
        # --- caller-facing: names only, filters `disabled` ---
        ("discovery/registry_integration.py", "items"),
        # --- operator/in-process only, never dispatched over the wire ---
        ("server.py", "values"),  # get_tool_stats cached-count
    }

    assert found == expected, (
        "the set of _tool_registry enumerators changed. Every CALLER-FACING "
        "enumerator must route through MCPServer._public_tool_view (or, for a "
        "names-only surface, filter `disabled`). Update this pin ONLY after "
        "confirming the new site does so.\n"
        f"  added:   {sorted(found - expected)}\n"
        f"  removed: {sorted(expected - found)}"
    )


@pytest.mark.regression
def test_public_tool_view_is_the_only_projection_builder():
    """No discovery surface may hand-write the advertised projection.

    Each of the three ``server.py`` caller-facing enumerators previously built
    its own ``{"name", "description", "inputSchema"}`` dict, which is how the
    ``completion/complete`` surface ended up with neither the ``disabled`` filter
    nor the permission gate. A hand-written projection is detectable: a dict
    literal carrying ``inputSchema``.
    """
    import ast
    import inspect as _inspect

    import kailash_mcp.server as server_module

    tree = ast.parse(_inspect.getsource(server_module))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
        if "inputSchema" in keys:
            offenders.append(node.lineno)

    # _public_tool_view's own construction is the ONE legitimate site.
    view_src = _inspect.getsource(server_module.MCPServer._public_tool_view)
    assert '"inputSchema"' in view_src, (
        "_public_tool_view no longer builds the inputSchema projection; this "
        "test's premise is stale"
    )
    assert len(offenders) == 1, (
        "more than one site builds a dict carrying 'inputSchema'; the advertised "
        "projection must be built ONLY by _public_tool_view. Offending lines: "
        f"{offenders}"
    )

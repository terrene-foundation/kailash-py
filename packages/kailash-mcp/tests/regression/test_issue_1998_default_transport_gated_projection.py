"""Regression #1998: the DEFAULT transport must enforce the same tool-disclosure
and ``disabled`` contract as every other transport.

``MCPServer.run()`` with ``transport="stdio"`` — the DEFAULT, and the transport
most deployments use — serves ``self._mcp.run()``, i.e. FastMCP's OWN server over
FastMCP's OWN tool registry. FastMCP builds that registry from the function it
was handed at ``self._mcp.tool()(enhanced_func)``, which ``functools.wraps`` the
original tool body, so ``inspect.signature`` follows ``__wrapped__`` and FastMCP
derived the FULL argument surface plus the complete ``Args:`` docstring block.
It never consulted ``_public_tool_view`` and never read the ``disabled`` flag.

An unauthenticated stdio client therefore received:

* every permission-gated tool's full ``inputSchema`` (parameter names, types,
  the required set) and its full ``Args:`` documentation, and
* a ``disable_tool()``'d tool — both LISTED and INVOCABLE.

SCOPE — this is a DISCLOSURE + ``disable_tool`` BYPASS, NOT an authentication
bypass. ``required_permission`` INVOCATION authorization always held on this
path: what FastMCP holds IS the enhanced wrapper, and the auth branch runs on
every dispatch path.

INSTRUMENT — the tests below drive the REAL MCP protocol against
``server._mcp`` through ``create_connected_server_and_client_session``. That is
the same handler stack ``self._mcp.run()`` serves over stdio; only the byte
transport differs. A client here presents NO credentials, exactly as an
anonymous stdio client does not.

FALSIFYING RESULT — if the gated projection were NOT applied, the assertions
below would observe ``user_id`` / ``hard_delete`` / ``reason`` in the gated
tool's advertised ``inputSchema`` properties and the ``Args:`` block in its
advertised description; and the disabled tool would appear in ``tools/list``
and execute on ``tools/call``. Each was the observed pre-fix behaviour.
"""

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from kailash_mcp.auth.providers import APIKeyAuth
from kailash_mcp.errors import MCPError, ToolError
from kailash_mcp.server import MCPServer

pytestmark = pytest.mark.regression


GATED_PARAM_NAMES = ("user_id", "hard_delete", "reason")


def _server() -> MCPServer:
    server = MCPServer(
        "regression-1998",
        auth_provider=APIKeyAuth(keys={"admin-key": {"permissions": ["admin.write"]}}),
    )

    @server.tool(required_permission="admin.write")
    def admin_delete_user(
        user_id: str, hard_delete: bool = False, reason: str = ""
    ) -> str:
        """Permanently delete a user account.

        Args:
            user_id: The account to delete.
            hard_delete: Skip the recycle bin and purge immediately.
            reason: Audit note recorded against the deletion.
        """
        return "deleted"

    @server.tool()
    def public_search(query: str, limit: int = 10) -> str:
        """Search the public index.

        Args:
            query: Free-text query.
            limit: Maximum results to return.
        """
        return "results"

    return server


async def _default_transport_tools(server: MCPServer) -> dict:
    """What an UNCREDENTIALED client of the DEFAULT transport is advertised."""
    if server._mcp is None:
        server._init_mcp()
    async with create_connected_server_and_client_session(server._mcp) as client:
        listed = await client.list_tools()
    return {t.name: t for t in listed.tools}


# ---------------------------------------------------------------------------
# Gated-tool argument-surface suppression on the DEFAULT transport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_transport_withholds_gated_input_schema():
    tools = await _default_transport_tools(_server())

    assert "admin_delete_user" in tools, (
        "the gated tool must stay DISCOVERABLE by name — suppressing the name "
        "would make it permanently invisible to legitimately credentialed "
        "clients too"
    )
    properties = tools["admin_delete_user"].inputSchema.get("properties") or {}
    for param in GATED_PARAM_NAMES:
        assert param not in properties, (
            f"the DEFAULT transport advertised gated parameter {param!r} to an "
            f"uncredentialed client: {tools['admin_delete_user'].inputSchema}"
        )


@pytest.mark.asyncio
async def test_default_transport_trims_gated_args_docstring_block():
    tools = await _default_transport_tools(_server())

    description = tools["admin_delete_user"].description or ""
    assert "Args:" not in description, (
        "the withheld inputSchema is worth nothing if the Args: block restates "
        f"it: {description!r}"
    )
    for param in GATED_PARAM_NAMES:
        assert param not in description, (
            f"gated parameter {param!r} leaked through the advertised "
            f"description: {description!r}"
        )
    assert description.startswith("Permanently delete a user account"), (
        "the summary line must survive — it is the pre-existing discovery "
        f"contract: {description!r}"
    )


@pytest.mark.asyncio
async def test_default_transport_preserves_ungated_input_schema():
    """The suppression keys on the permission boundary, not on all tools."""
    tools = await _default_transport_tools(_server())

    properties = tools["public_search"].inputSchema.get("properties") or {}
    assert (
        "query" in properties and "limit" in properties
    ), f"an UNGATED tool must keep its full argument surface: {properties}"
    assert "Args:" in (tools["public_search"].description or "")


@pytest.mark.asyncio
async def test_no_auth_provider_leaves_schema_advertised():
    """No auth_provider -> no permission boundary -> nothing to withhold.

    ``required_permission`` is not enforced on the invoke path either without an
    auth manager, so withholding would cost discovery for no security gain.
    """
    server = MCPServer("regression-1998-noauth")

    @server.tool(required_permission="admin.write")
    def admin_delete_user(user_id: str) -> str:
        """Delete.

        Args:
            user_id: The account.
        """
        return "deleted"

    tools = await _default_transport_tools(server)
    properties = tools["admin_delete_user"].inputSchema.get("properties") or {}
    assert "user_id" in properties


# ---------------------------------------------------------------------------
# ``disable_tool`` on the DEFAULT transport — listing AND invocation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_tool_absent_from_default_transport_listing():
    server = _server()
    assert server.disable_tool("public_search") is True

    tools = await _default_transport_tools(server)
    assert "public_search" not in tools, (
        "a disabled tool leaks the deployment's tool inventory for no gain; "
        f"advertised: {sorted(tools)}"
    )
    assert "admin_delete_user" in tools, "only the disabled tool is withheld"


@pytest.mark.asyncio
async def test_re_enabled_tool_returns_to_default_transport_listing():
    server = _server()
    server.disable_tool("public_search")
    assert server.enable_tool("public_search") is True

    tools = await _default_transport_tools(server)
    assert "public_search" in tools
    properties = tools["public_search"].inputSchema.get("properties") or {}
    assert "query" in properties, (
        "re-enabling must restore the ORIGINAL advertised projection, not a "
        f"degraded one: {properties}"
    )


@pytest.mark.asyncio
async def test_disabled_tool_refused_on_default_transport_invocation():
    """The ``disabled`` check must be enforced at INVOKE, on every path."""
    server = _server()
    server.disable_tool("public_search")

    if server._mcp is None:
        server._init_mcp()
    async with create_connected_server_and_client_session(server._mcp) as client:
        result = await client.call_tool("public_search", {"query": "x"})

    assert result.isError, "a disabled tool must not execute on any transport"
    rendered = " ".join(
        getattr(block, "text", "") for block in (result.content or [])
    ).lower()
    # The registration is WITHHELD, so this transport reports the tool as
    # unknown rather than as disabled — which is also the better answer: it
    # does not confirm the deployment's inventory to an uncredentialed caller.
    # The wrapper-level refusal below is what binds any path that still
    # resolves a handler.
    assert "public_search" in rendered and (
        "unknown" in rendered or "not found" in rendered or "disabled" in rendered
    ), rendered
    assert "results" not in rendered, f"the tool body executed: {rendered}"


def test_disabled_tool_refused_through_the_sync_enhanced_wrapper():
    """Half (b): the wrapper itself refuses, independent of any listing fix."""
    server = _server()
    handler = server._tool_registry["public_search"]["function"]
    server.disable_tool("public_search")

    with pytest.raises(Exception, match="disabled"):
        handler(query="x")


@pytest.mark.asyncio
async def test_disabled_tool_refused_through_the_async_enhanced_wrapper():
    server = MCPServer("regression-1998-async")

    @server.tool()
    async def async_probe(query: str) -> str:
        """Async probe."""
        return "ok"

    handler = server._tool_registry["async_probe"]["function"]
    server.disable_tool("async_probe")

    with pytest.raises(Exception, match="disabled"):
        await handler(query="x")


# ---------------------------------------------------------------------------
# Invocation authorization still holds on the DEFAULT transport (scope pin)
# ---------------------------------------------------------------------------


def test_every_run_branch_serves_a_gated_transport():
    """Enforcement-surface parity: pin the set of transports the server runs.

    #1998 existed because a transport was reachable that no disclosure test
    covered. The four branches below are the complete set, each with the route
    by which it reaches ``_public_tool_view``'s decision. A NEW branch fails
    this pin, forcing the author to add it to the ``EMITTERS`` list in
    ``test_tools_list_permission_gated_schema_disclosure.py`` before it ships.
    """
    import ast
    import inspect as _inspect

    import kailash_mcp.server as server_module

    tree = ast.parse(_inspect.getsource(server_module))
    branches = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in ("run", "run_async"):
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            if isinstance(func, ast.Attribute) and func.attr in (
                "run",
                "_run_websocket",
                "run_stdio",
            ):
                target = getattr(func.value, "attr", None) or getattr(
                    func.value, "id", ""
                )
                branches.add((node.name, f"{target}.{func.attr}"))

    expected = {
        # sync run(): FastMCP's own server. Gated at REGISTRATION by
        # _project_tool_onto_fastmcp / _withhold_tool_from_fastmcp.
        ("run", "_mcp.run"),
        # sync run(): websocket -> _handle_websocket_message -> the
        # _handle_list_tools / _handle_completion_complete handlers.
        ("run", "self._run_websocket"),
        # Not a transport: the event-loop driver the sync run() wraps the
        # websocket coroutine in. Listed so the pin stays a complete
        # enumeration of what the matcher sees rather than a filtered one.
        ("run", "asyncio.run"),
        # async run_async(): same websocket handler stack.
        ("run_async", "self._run_websocket"),
        # async run_async(): the in-repo stdio loop, which calls
        # _public_tool_view directly.
        ("run_async", "self.run_stdio"),
    }
    assert branches == expected, (
        "the set of transports MCPServer runs changed. Every transport must "
        "reach _public_tool_view's decision, and must be added to EMITTERS in "
        "test_tools_list_permission_gated_schema_disclosure.py.\n"
        f"  added:   {sorted(branches - expected)}\n"
        f"  removed: {sorted(expected - branches)}"
    )


@pytest.mark.asyncio
async def test_gated_tool_invocation_still_refused_without_credentials():
    """#1998 is a DISCLOSURE bug, not an auth bypass. Pin that it stays so."""
    server = _server()
    if server._mcp is None:
        server._init_mcp()
    async with create_connected_server_and_client_session(server._mcp) as client:
        result = await client.call_tool("admin_delete_user", {"user_id": "u1"})

    assert result.isError, "an uncredentialed gated invocation must be refused"


# ---------------------------------------------------------------------------
# A THIRD FastMCP implementation — the projection must fail CLOSED
#
# ``_init_mcp`` tries the independent ``fastmcp`` package first, then
# ``mcp.server.FastMCP``, then a local shim. Only the second and third are
# installed here, so the first is a registration layout this code has never
# run against — the same "a path nothing taught the control" shape as #1998
# itself. It must refuse to register rather than serve an ungated schema.
# ---------------------------------------------------------------------------


class _UnrecognisedLayoutFastMCP:
    """A FastMCP that keeps tools somewhere this code does not look."""

    def __init__(self):
        self.registry = {}  # neither ``_tools`` nor ``_tool_manager._tools``

    def tool(self, *args, **kwargs):
        def decorator(func):
            self.registry[func.__name__] = func
            return func

        return decorator


class _ParamlessEntryFastMCP:
    """A recognised container whose entries expose no advertised schema."""

    class _Entry:
        def __init__(self, fn):
            self.fn = fn  # no ``parameters`` attribute

    def __init__(self):
        self._tool_manager = type("TM", (), {})()
        self._tool_manager._tools = {}

    def tool(self, *args, **kwargs):
        def decorator(func):
            self._tool_manager._tools[func.__name__] = self._Entry(func)
            return func

        return decorator


@pytest.mark.parametrize(
    "fake_factory",
    [
        pytest.param(_UnrecognisedLayoutFastMCP, id="unrecognised_container"),
        pytest.param(_ParamlessEntryFastMCP, id="entry_without_parameters"),
    ],
)
def test_gated_registration_fails_closed_on_unknown_fastmcp_layout(fake_factory):
    """Refuse to register rather than publish an ungated argument surface."""
    server = MCPServer(
        "regression-1998-unknown",
        auth_provider=APIKeyAuth(keys={"admin-key": {"permissions": ["admin.write"]}}),
    )
    server._mcp = fake_factory()

    with pytest.raises(MCPError, match="tool-disclosure gate"):

        @server.tool(required_permission="admin.write")
        def admin_delete_user(user_id: str) -> str:
            """Delete an account.

            Args:
                user_id: The account to delete.
            """
            return "deleted"


def test_ungated_registration_still_works_on_unknown_fastmcp_layout():
    """CONTROL: the guard keys on the GATE, not on the unknown layout.

    Without this, the test above would pass for a guard that simply raised on
    every registration against an unfamiliar FastMCP.
    """
    server = MCPServer("regression-1998-unknown-ungated")
    server._mcp = _UnrecognisedLayoutFastMCP()

    @server.tool()
    def public_search(query: str) -> str:
        """Search."""
        return "results"

    assert "public_search" in server._tool_registry


def test_disable_tool_on_unknown_layout_blocks_invoke_then_reports_loudly():
    """A half-applied disable must be loud, and must still block invocation.

    The registry flag is set BEFORE the withhold is attempted, so the wrapper
    refuses the tool even when the listing cannot be updated; the raise tells
    the operator the advertisement may still name it. Silence here would be the
    worst outcome — an operator believing a tool is fully disabled.
    """
    server = MCPServer("regression-1998-unknown-disable")
    server._mcp = _UnrecognisedLayoutFastMCP()

    @server.tool()
    def echo(text: str) -> str:
        """Echo."""
        return text

    handler = server._tool_registry["echo"]["function"]

    with pytest.raises(MCPError, match="tool-disclosure gate"):
        server.disable_tool("echo")

    assert server._tool_registry["echo"]["disabled"] is True, (
        "the flag must land before the withhold is attempted, or a failed "
        "withhold would leave the tool fully invocable"
    )
    with pytest.raises(ToolError, match="disabled"):
        handler(text="hi")

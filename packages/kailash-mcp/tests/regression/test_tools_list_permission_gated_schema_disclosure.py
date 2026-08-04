"""Regression: NO discovery surface may disclose a permission-gated tool's
argument surface to a caller it cannot authorize.

``_handle_list_tools`` filtered the registry on ``disabled`` alone and never
read ``required_permission``. That was inert while every tool advertised an
empty ``inputSchema``; once the schema deriver landed, the SAME unfiltered loop
began serialising the full argument surface — parameter names, types, and the
required set — of tools whose invocation is permission-gated.

Reachability was established at the wire, not inferred from the registry:
``WebSocketServerTransport.handle_client`` assigns a ``client_id`` and starts
reading frames without ever consulting ``self.auth_provider``, ``initialize``
authenticates nothing, and ``_dispatch_ws_method`` routes ``tools/list`` to a
handler that receives neither ``client_id`` nor credentials. An anonymous
socket therefore reaches the loop's output.

The permission model here is per-CALL (``_extract_credentials_from_context``
reads the tool's own kwargs), so NO caller can be authorized at discovery time.
The server must therefore fail closed on the argument surface whenever a
permission boundary exists at all — i.e. when an ``auth_provider`` is
configured. With no ``auth_provider``, ``required_permission`` is never enforced
on the invoke path either (``if self.auth_manager and required_permission``), so
there is no boundary to protect and the schema is advertised unchanged.

Name and description remain advertised: that is the pre-existing contract, and
suppressing them would make a gated tool permanently undiscoverable by every
caller, including legitimately credentialed ones.

WHY THIS FILE IS PARAMETRIZED OVER EMITTERS
-------------------------------------------
The first version of this suite bottomed out every test in
``server._handle_list_tools({}, 1)``. It varied gated/ungated and auth/no-auth
but never varied the emission SITE — so it could not see that TWO other surfaces
enumerate the same registry and hand-wrote their own projection:

* ``run_stdio``'s ``tools/list`` branch, and
* ``_handle_completion_complete`` for ``ref.type == "tool"``, which had NEITHER
  the ``disabled`` filter NOR the ``required_permission`` gate. An empty
  ``argument.value`` substring-matches EVERY tool, so one uncredentialed
  ``completion/complete`` returned every tool's full ``inputSchema`` and made
  the ``tools/list`` suppression decorative.

The claim under test is "a permission-gated tool's argument surface must not
reach a caller that cannot be authorized" — a claim about EVERY reader of the
registry, not about one function. Every test below therefore runs against all
three emitters. A new discovery surface MUST be added to ``EMITTERS``.
"""

import asyncio
import io
import json

import pytest
from kailash_mcp.auth.providers import APIKeyAuth
from kailash_mcp.server import MCPServer

# ---------------------------------------------------------------------------
# Server fixtures
# ---------------------------------------------------------------------------


def _gated_server() -> MCPServer:
    server = MCPServer(
        "regression-gated",
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

    # An UNGATED tool that actually HAS parameters. The suppression must key on
    # required_permission, so this tool's full schema must survive — including
    # its ``properties`` and ``required``, not merely the envelope.
    @server.tool()
    def public_search(query: str, limit: int = 10) -> str:
        """Search the public index.

        Args:
            query: Free-text query.
            limit: Maximum results to return.
        """
        return "results"

    @server.tool()
    def public_ping() -> str:
        """Public health check."""
        return "pong"

    return server


# ---------------------------------------------------------------------------
# Emitters — every surface that enumerates the tool registry for a caller.
# Each returns {tool_name: advertised_entry} for an UNCREDENTIALED caller.
# ---------------------------------------------------------------------------


async def _emit_tools_list(server: MCPServer) -> dict:
    result = await server._handle_list_tools({}, 1)
    return {t["name"]: t for t in result["result"]["tools"]}


async def _emit_completion(server: MCPServer) -> dict:
    """The documented attack: an empty ``value`` matches EVERY tool name."""
    result = await server._handle_completion_complete(
        {"ref": {"type": "tool"}, "argument": {"value": ""}}, 1
    )
    return {v["name"]: v for v in result["result"]["completion"]["values"]}


async def _emit_stdio_list(server: MCPServer, monkeypatch=None) -> dict:
    """Drive the real ``run_stdio`` loop over a one-request stdin."""
    import sys

    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    stdin, stdout = io.StringIO(request), io.StringIO()
    real_stdin, real_stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = stdin, stdout
    try:
        # readline() returns "" at EOF -> the loop breaks on its own.
        await asyncio.wait_for(server.run_stdio(), timeout=10)
    finally:
        sys.stdin, sys.stdout = real_stdin, real_stdout

    payload = json.loads(stdout.getvalue().strip().splitlines()[0])
    return {t["name"]: t for t in payload["result"]["tools"]}


EMITTERS = [
    pytest.param(_emit_tools_list, id="tools_list"),
    pytest.param(_emit_completion, id="completion_complete"),
    pytest.param(_emit_stdio_list, id="stdio_tools_list"),
]


# ---------------------------------------------------------------------------
# Gated-tool argument-surface suppression, per emitter
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("emit", EMITTERS)
async def test_gated_tool_argument_surface_not_disclosed(emit):
    """No emitter may carry the gated tool's schema to an anonymous caller."""
    server = _gated_server()
    tools = await emit(server)

    # CONTROL: the emitter actually produced a listing. True before and after
    # the fix, so it cannot be satisfied by an emitter that returns nothing.
    assert "admin_delete_user" in tools, (
        "emitter returned no entry for the gated tool at all; the assertions "
        f"below would pass vacuously: {tools!r}"
    )

    gated = tools["admin_delete_user"]
    assert gated["inputSchema"] == {}, (
        "a discovery surface disclosed the argument surface of a "
        "permission-gated tool to a caller carrying no credentials: "
        f"{gated['inputSchema']!r}"
    )
    # The parameter names must not survive anywhere in the advertised entry —
    # including through the description channel.
    for parameter in ("user_id", "hard_delete", "reason"):
        assert parameter not in str(gated), (
            f"gated tool's parameter {parameter!r} leaked in its advertised "
            f"entry: {gated!r}"
        )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("emit", EMITTERS)
async def test_gated_tool_still_discoverable_by_name(emit):
    """Suppression is scoped to the surface — the tool is still advertised."""
    server = _gated_server()
    tools = await emit(server)

    assert "admin_delete_user" in tools, (
        "the gated tool vanished from discovery; suppression must be scoped to "
        "the argument surface, not remove the tool from discovery"
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("emit", EMITTERS)
async def test_ungated_tool_with_parameters_keeps_full_schema(emit):
    """The #1998 schema fix must survive for tools with no permission gate.

    Asserted against a tool that HAS parameters. The previous version of this
    test pinned a ZERO-parameter tool and checked only
    ``inputSchema["type"] == "object"``, so it could not have detected a
    regression that emitted the envelope while stripping ``properties``.
    """
    server = _gated_server()
    tools = await emit(server)

    schema = tools["public_search"]["inputSchema"]
    assert schema.get("type") == "object", (
        "an ungated tool lost its derived inputSchema envelope; the suppression "
        f"must key on required_permission, not on auth being enabled: {schema!r}"
    )
    assert set(schema.get("properties", {})) == {"query", "limit"}, (
        "an ungated tool's inputSchema kept the envelope but lost its "
        f"parameter properties: {schema!r}"
    )
    assert schema.get("required") == [
        "query"
    ], f"an ungated tool's inputSchema lost its required set: {schema!r}"


# ---------------------------------------------------------------------------
# disabled x gated, per emitter
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("emit", EMITTERS)
async def test_disabled_ungated_tool_not_advertised(emit):
    """A disabled tool is not invocable, so no surface may advertise it."""
    server = _gated_server()
    server.disable_tool("public_ping")
    tools = await emit(server)

    # CONTROL: an ENABLED tool is still advertised, so a suppressed listing
    # cannot make this pass vacuously.
    assert (
        "public_search" in tools
    ), f"emitter dropped the enabled tools too; assertion is vacuous: {tools!r}"
    assert "public_ping" not in tools, (
        "a discovery surface advertised a tool that disable_tool() turned off; "
        f"_execute_tool and tools/call both refuse it: {tools!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("emit", EMITTERS)
async def test_disabled_gated_tool_not_advertised(emit):
    """disabled x gated — the tool is withheld entirely, schema included."""
    server = _gated_server()
    server.disable_tool("admin_delete_user")
    tools = await emit(server)

    assert (
        "public_search" in tools
    ), f"emitter dropped the enabled tools too; assertion is vacuous: {tools!r}"
    assert (
        "admin_delete_user" not in tools
    ), f"a discovery surface advertised a disabled gated tool: {tools!r}"
    assert "hard_delete" not in str(
        tools
    ), f"a disabled gated tool's parameter names leaked: {tools!r}"


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("emit", EMITTERS)
async def test_no_auth_provider_leaves_schema_untouched(emit):
    """With no auth_provider there is no boundary — nothing is suppressed.

    ``required_permission`` is not enforced on the invoke path either when
    ``auth_manager`` is None, so suppressing here would cost discovery for no
    security gain.
    """
    server = MCPServer("regression-unauthed")

    @server.tool(required_permission="admin.write")
    def admin_delete_user(user_id: str, hard_delete: bool = False) -> str:
        """Permanently delete a user account."""
        return "deleted"

    assert server.auth_manager is None
    tools = await emit(server)
    schema = tools["admin_delete_user"]["inputSchema"]
    assert (
        schema.get("type") == "object"
    ), f"schema was suppressed on a server with no permission boundary: {schema!r}"
    assert set(schema.get("properties", {})) == {
        "user_id",
        "hard_delete",
    }, f"schema envelope survived but properties were stripped: {schema!r}"


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("emit", EMITTERS)
async def test_gated_tool_output_schema_not_disclosed(emit):
    """outputSchema is the same disclosure class through the same projection."""
    server = MCPServer(
        "regression-gated-out",
        auth_provider=APIKeyAuth(keys={"admin-key": {"permissions": ["admin.write"]}}),
    )

    @server.tool(
        required_permission="admin.write",
        output_schema={
            "type": "object",
            "properties": {"purged_rows": {"type": "integer"}},
        },
    )
    def admin_purge(scope: str) -> dict:
        """Purge records."""
        return {"purged_rows": 0}

    @server.tool(
        output_schema={
            "type": "object",
            "properties": {"hits": {"type": "integer"}},
        }
    )
    def public_count() -> dict:
        """Count records."""
        return {"hits": 0}

    tools = await emit(server)
    assert "outputSchema" not in tools["admin_purge"], (
        "a discovery surface disclosed a permission-gated tool's result shape: "
        f"{tools['admin_purge']!r}"
    )
    # CONTROL: an ungated tool's outputSchema IS still advertised, so the
    # assertion above cannot pass by dropping outputSchema everywhere.
    assert tools["public_count"].get("outputSchema") == {
        "type": "object",
        "properties": {"hits": {"type": "integer"}},
    }, f"an ungated tool lost its advertised outputSchema: {tools['public_count']!r}"


# ---------------------------------------------------------------------------
# description — never stored at all before this fix (same defect class as the
# inputSchema bug, one field over)
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("emit", EMITTERS)
async def test_tool_description_is_populated(emit):
    """``description`` was never written to the registry, so every consumer's
    ``info.get("description", "")`` resolved to ``""`` for EVERY tool."""
    server = _gated_server()
    tools = await emit(server)

    assert tools["public_ping"]["description"] == "Public health check.", (
        "an undecorated tool's docstring did not reach its advertised "
        f"description: {tools['public_ping']!r}"
    )
    assert tools["public_search"]["description"].startswith(
        "Search the public index."
    ), f"ungated tool description not derived: {tools['public_search']!r}"


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("emit", EMITTERS)
async def test_gated_tool_description_does_not_carry_argument_surface(emit):
    """A real description must not re-open what inputSchema suppression closed.

    Conventional Google/NumPy docstrings document every parameter BY NAME. Now
    that descriptions are actually populated, a gated tool's advertised
    description must be trimmed at the first structured section — otherwise
    withholding ``inputSchema`` withholds nothing.
    """
    server = _gated_server()
    tools = await emit(server)

    description = tools["admin_delete_user"]["description"]
    # CONTROL: the summary IS advertised — the trim is scoped, not a wipe.
    assert description == "Permanently delete a user account.", (
        "gated tool's description should be its summary line: " f"{description!r}"
    )
    for parameter in ("user_id", "hard_delete", "reason", "Args:"):
        assert parameter not in description, (
            f"gated tool's description disclosed {parameter!r}, re-opening the "
            f"argument surface the inputSchema suppression closed: {description!r}"
        )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("emit", EMITTERS)
async def test_ungated_tool_description_keeps_full_docstring(emit):
    """The description trim is scoped to GATED tools only."""
    server = _gated_server()
    tools = await emit(server)

    description = tools["public_search"]["description"]
    assert "Args:" in description and "Free-text query." in description, (
        "an ungated tool's description was trimmed; the trim must key on "
        f"required_permission: {description!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_explicit_description_overrides_docstring():
    """The decorator's ``description`` kwarg wins over the docstring."""
    server = MCPServer("regression-explicit-desc")

    @server.tool(description="Explicit override.")
    def documented() -> str:
        """Docstring that must not win."""
        return "ok"

    tools = await _emit_tools_list(server)
    assert tools["documented"]["description"] == "Explicit override."

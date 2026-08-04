"""Regression: ``tools/list`` must not disclose a permission-gated tool's
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
reads the tool's own kwargs), so NO caller can be authorized at list time. The
server must therefore fail closed on the argument surface whenever a permission
boundary exists at all — i.e. when an ``auth_provider`` is configured. With no
``auth_provider``, ``required_permission`` is never enforced on the invoke path
either (``if self.auth_manager and required_permission``), so there is no
boundary to protect and the schema is advertised unchanged.

Name and description remain advertised: that is the pre-existing contract, and
suppressing them would make a gated tool permanently undiscoverable by every
caller, including legitimately credentialed ones.
"""

import pytest
from kailash_mcp.auth.providers import APIKeyAuth
from kailash_mcp.server import MCPServer


def _gated_server() -> MCPServer:
    server = MCPServer(
        "regression-gated",
        auth_provider=APIKeyAuth(keys={"admin-key": {"permissions": ["admin.write"]}}),
    )

    @server.tool(required_permission="admin.write")
    def admin_delete_user(
        user_id: str, hard_delete: bool = False, reason: str = ""
    ) -> str:
        """Permanently delete a user account."""
        return "deleted"

    @server.tool()
    def public_ping() -> str:
        """Public health check."""
        return "pong"

    return server


def _by_name(result: dict) -> dict:
    return {t["name"]: t for t in result["result"]["tools"]}


@pytest.mark.regression
@pytest.mark.asyncio
async def test_gated_tool_argument_surface_not_disclosed():
    """An uncredentialed tools/list must not carry the gated tool's schema."""
    server = _gated_server()
    tools = _by_name(await server._handle_list_tools({}, 1))

    gated = tools["admin_delete_user"]
    assert gated["inputSchema"] == {}, (
        "tools/list disclosed the argument surface of a permission-gated tool "
        f"to a caller carrying no credentials: {gated['inputSchema']!r}"
    )
    # The parameter names must not survive anywhere in the advertised entry.
    assert "hard_delete" not in str(
        gated
    ), f"gated tool's parameter names leaked in tools/list entry: {gated!r}"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_gated_tool_still_discoverable_by_name():
    """Suppression is scoped to the surface — the tool is still advertised."""
    server = _gated_server()
    tools = _by_name(await server._handle_list_tools({}, 1))

    assert "admin_delete_user" in tools, (
        "the gated tool vanished from tools/list; suppression must be scoped to "
        "the argument surface, not remove the tool from discovery"
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_ungated_tool_schema_still_advertised_under_auth():
    """The #1998 schema fix must survive for tools with no permission gate."""
    server = _gated_server()
    tools = _by_name(await server._handle_list_tools({}, 1))

    assert tools["public_ping"]["inputSchema"].get("type") == "object", (
        "an ungated tool lost its derived inputSchema; the suppression must key "
        f"on required_permission, not on auth being enabled: {tools['public_ping']!r}"
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_no_auth_provider_leaves_schema_untouched():
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
    tools = _by_name(await server._handle_list_tools({}, 1))
    assert (
        tools["admin_delete_user"]["inputSchema"].get("type") == "object"
    ), "schema was suppressed on a server with no permission boundary at all"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_gated_tool_output_schema_not_disclosed():
    """outputSchema is the same disclosure class through the same loop."""
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

    tools = _by_name(await server._handle_list_tools({}, 1))
    assert "outputSchema" not in tools["admin_purge"], (
        "tools/list disclosed a permission-gated tool's result shape: "
        f"{tools['admin_purge']!r}"
    )

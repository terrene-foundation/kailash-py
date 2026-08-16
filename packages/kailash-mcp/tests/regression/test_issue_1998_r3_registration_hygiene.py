"""Regression: two defects in the #1998 FastMCP registration projection itself.

The #1998 fix binds the disclosure contract to the FastMCP REGISTRATION, because
FastMCP owns its own enumeration. Both defects below are in that binding — the
fix's own machinery, not the surface it was protecting.

R3-HIGH-1 — the withhold was not idempotent across RE-registration.
    ``disable_tool`` parks the FastMCP registration in
    ``_fastmcp_withheld_tools`` so ``enable_tool`` can restore the exact object.
    Re-registering a same-named tool replaced ``_tool_registry[name]`` wholesale
    and put a NEW entry in the FastMCP container, but never cleared the PARKED
    one. Two consequences, both observed:

      (a) ``_withhold_tool_from_fastmcp`` early-returned on "already parked", so
          a second ``disable_tool`` was a silent no-op on the container and the
          disabled tool stayed advertised — the #1998 disclosure, reopened.
      (b) ``enable_tool`` wrote the STALE registration back OVER the current
          one. If v1 was ungated and v2 gated, the default transport then
          advertised v1's full argument surface AND dispatched v1's wrapper,
          which closes over v1's (empty) ``required_permissions``. That is an
          AUTHORIZATION BYPASS, not merely disclosure — strictly worse than the
          bug the parking mechanism was added to fix.

R3-MED-2 — the projection mirrored 2 of the 3 fields the view decides.
    ``_public_tool_view`` withholds a gated tool's ``outputSchema`` ("the result
    shape is the same disclosure class"), but the projection set only
    ``parameters`` and ``description``. FastMCP derives its OWN output schema
    from the wrapped function's RETURN ANNOTATION — verified on the installed
    build for ``BaseModel``, ``TypedDict`` and ``dict[str, int]`` returns — so a
    gated tool's result shape shipped on the default transport while being
    withheld on every other one.

    (This also corrects a claim made when #1998 landed: that the default
    transport advertises no ``outputSchema`` for any tool. That holds only for
    schemas declared via ``@server.tool(output_schema=...)``, which never reach
    the FastMCP registration. Return-annotation-DERIVED schemas do reach it, and
    the probe that produced the original claim used un-annotated returns.)

FALSIFYING RESULTS, both observed before the fix: ``enable_tool`` restoring an
entry whose description is "V1 ungated." and whose properties are v1's; an
uncredentialed ``tools/call`` returning ``V1-BODY-EXECUTED``; and a gated tool's
``outputSchema`` arriving on the wire carrying ``tenant_secret_id``.
"""

import asyncio
from typing import TypedDict

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import BaseModel

from kailash_mcp.auth.providers import APIKeyAuth
from kailash_mcp.errors import MCPError, ToolError
from kailash_mcp.server import MCPServer

pytestmark = pytest.mark.regression


def _auth_server(name: str) -> MCPServer:
    return MCPServer(
        name,
        auth_provider=APIKeyAuth(keys={"admin-key": {"permissions": ["admin.write"]}}),
    )


async def _wire_tools(server: MCPServer) -> dict:
    """What the DEFAULT transport advertises to an uncredentialed caller."""
    if server._mcp is None:
        server._init_mcp()
    async with create_connected_server_and_client_session(server._mcp) as client:
        listed = await client.list_tools()
    return {t.name: t for t in listed.tools}


def _re_registered_server(name: str) -> MCPServer:
    """v1 UNGATED -> disable -> v2 GATED under the SAME name."""
    server = _auth_server(name)

    @server.tool()
    def widget(payload: str, secret_flag: bool = False) -> str:
        """V1 ungated.

        Args:
            payload: v1 argument.
            secret_flag: v1 argument.
        """
        return "V1-BODY-EXECUTED"

    server.disable_tool("widget")

    @server.tool(required_permission="admin.write")
    def widget(scope: str) -> str:  # noqa: F811 — same name ON PURPOSE
        """V2 gated.

        Args:
            scope: v2 argument.
        """
        return "V2-BODY"

    return server


# ---------------------------------------------------------------------------
# R3-HIGH-1
# ---------------------------------------------------------------------------


def test_re_registration_clears_the_parked_registration():
    """The parked entry is stale the moment a new registration replaces it."""
    server = _re_registered_server("r3-parked")

    assert "widget" not in server._fastmcp_withheld_tools, (
        "a registration parked by disable_tool survived re-registration; "
        "enable_tool would later restore it over the current one"
    )


@pytest.mark.asyncio
async def test_second_disable_after_re_registration_is_not_a_no_op():
    """(a) The disabled tool must leave the advertisement, every time."""
    server = _re_registered_server("r3-second-disable")
    server.disable_tool("widget")

    tools = await _wire_tools(server)
    assert "widget" not in tools, (
        "the second disable_tool was a silent no-op on the FastMCP container, "
        f"so a disabled tool stayed advertised: {sorted(tools)}"
    )


@pytest.mark.asyncio
async def test_enable_after_re_registration_does_not_restore_stale_entry():
    """(b) enable_tool must not resurrect the pre-re-registration entry."""
    server = _re_registered_server("r3-stale-restore")
    server.enable_tool("widget")

    tools = await _wire_tools(server)
    assert "widget" in tools, "CONTROL: the tool should be advertised again"

    entry = tools["widget"]
    description = entry.description or ""
    properties = entry.inputSchema.get("properties") or {}

    assert (
        "V1 ungated" not in description
    ), f"enable_tool restored the STALE v1 registration: {description!r}"
    for stale in ("payload", "secret_flag"):
        assert stale not in properties, (
            f"v1's argument {stale!r} is advertised after re-registration to a "
            f"GATED v2: {properties!r}"
        )
    assert properties == {}, (
        "v2 is permission-gated, so the default transport must advertise no "
        f"argument surface for it: {properties!r}"
    )


@pytest.mark.asyncio
async def test_re_registration_cannot_produce_an_authorization_bypass():
    """The severity pin: v1's wrapper must never be reachable under v2's name.

    v1's enhanced wrapper closes over v1's ``required_permissions`` — empty,
    because v1 was ungated. Restoring it under a name now registered as gated
    makes an uncredentialed call execute v1's body.
    """
    server = _re_registered_server("r3-bypass")
    server.enable_tool("widget")

    if server._mcp is None:
        server._init_mcp()
    async with create_connected_server_and_client_session(server._mcp) as client:
        result = await client.call_tool("widget", {"payload": "x"})

    rendered = " ".join(getattr(block, "text", "") for block in (result.content or []))
    assert "V1-BODY-EXECUTED" not in rendered, (
        "AUTHORIZATION BYPASS: an uncredentialed caller executed the "
        f"pre-re-registration tool body under a gated name: {rendered!r}"
    )
    assert (
        result.isError
    ), f"an uncredentialed call to a gated tool must be refused: {rendered!r}"


def test_repeated_disable_is_idempotent_without_re_registration():
    """CONTROL: the ordinary disable/disable/enable cycle still round-trips."""
    server = _auth_server("r3-idempotent")

    @server.tool()
    def echo(text: str) -> str:
        """Echo."""
        return text

    container = server._fastmcp_tool_container()
    original = container["echo"]

    server.disable_tool("echo")
    server.disable_tool("echo")
    assert "echo" not in container
    server.enable_tool("echo")

    assert container["echo"] is original, (
        "enable_tool must restore the ORIGINAL registration object, so the "
        "projection applied at registration survives the round trip"
    )


# ---------------------------------------------------------------------------
# R3-MED-2
# ---------------------------------------------------------------------------


class _PurgeModel(BaseModel):
    purged_rows: int
    tenant_secret_id: str


class _PurgeDict(TypedDict):
    rows: int
    internal_ref: str


def _output_schema_server(name: str) -> MCPServer:
    server = _auth_server(name)

    @server.tool(required_permission="admin.write")
    def gated_model(scope: str) -> _PurgeModel:
        """Gated, BaseModel return."""
        return _PurgeModel(purged_rows=0, tenant_secret_id="")

    @server.tool(required_permission="admin.write")
    def gated_typeddict(scope: str) -> _PurgeDict:
        """Gated, TypedDict return."""
        return {"rows": 0, "internal_ref": ""}

    @server.tool(required_permission="admin.write")
    def gated_dict(scope: str) -> dict[str, int]:
        """Gated, dict return."""
        return {}

    @server.tool()
    def public_model(query: str) -> _PurgeModel:
        """Ungated, BaseModel return."""
        return _PurgeModel(purged_rows=0, tenant_secret_id="")

    return server


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name, leaked_field",
    [
        ("gated_model", "tenant_secret_id"),
        ("gated_typeddict", "internal_ref"),
        ("gated_dict", "additionalProperties"),
    ],
)
async def test_gated_output_schema_not_advertised(tool_name, leaked_field):
    """FastMCP derives an output schema from the RETURN ANNOTATION.

    ``_public_tool_view`` withholds a gated tool's result shape, so the
    projection must clear it on the registration too.
    """
    tools = await _wire_tools(_output_schema_server(f"r3-out-{tool_name}"))

    assert tool_name in tools, "CONTROL: the gated tool is still discoverable"
    advertised = tools[tool_name].outputSchema
    assert advertised is None, (
        "the default transport advertised a permission-gated tool's result "
        f"shape (carrying {leaked_field!r}) to an uncredentialed caller: "
        f"{advertised!r}"
    )


@pytest.mark.asyncio
async def test_ungated_output_schema_still_advertised():
    """CONTROL: the suppression keys on the GATE, not on output schemas."""
    tools = await _wire_tools(_output_schema_server("r3-out-control"))

    advertised = tools["public_model"].outputSchema
    assert advertised is not None, (
        "an UNGATED tool lost its derived outputSchema; without this the test "
        "above would pass for a fix that cleared every tool's result shape"
    )
    assert "tenant_secret_id" in (advertised.get("properties") or {}), advertised


@pytest.mark.asyncio
async def test_gated_tool_still_executes_for_a_credentialed_caller():
    """Clearing the ADVERTISED schema must not disturb invocation.

    ``Tool.run`` converts results through ``fn_metadata``, not through the
    advertised ``output_schema`` — pinned here so a future change that routes
    execution through the advertised field is caught rather than silently
    breaking every gated tool with a structured return.
    """
    server = _output_schema_server("r3-out-exec")
    result = server._execute_tool(
        "gated_model", {"scope": "all", "api_key": "admin-key"}
    )
    if asyncio.iscoroutine(result):
        result = await result
    assert result is not None


# ---------------------------------------------------------------------------
# R3-MED-3 — a container that hands back a DEFENSIVE COPY
#
# ``_fastmcp_tool_container`` returns whatever mapping it finds. If an
# implementation exposes ``_tools`` as a property building a fresh dict, every
# ``pop``/assignment lands on a throwaway and the real registry never changes —
# so ``disable_tool`` would report success while the tool stayed advertised.
# The entry OBJECTS are shared by reference, so the projection still applies;
# only the withhold/restore silently fail. That asymmetry is what makes this
# worth a post-condition rather than an assumption.
# ---------------------------------------------------------------------------


class _CopyingContainerFastMCP:
    """Exposes ``_tools`` as a defensive copy, as a real implementation may."""

    class _Entry:
        def __init__(self, fn):
            self.fn = fn
            self.parameters = {"type": "object", "properties": {"q": {}}}
            self.description = "live"
            self.output_schema = None

    def __init__(self):
        self._store = {}

    @property
    def _tools(self):
        return dict(self._store)  # a COPY — mutations here are discarded

    def tool(self, *args, **kwargs):
        def decorator(func):
            self._store[func.__name__] = self._Entry(func)
            return func

        return decorator


def test_withhold_fails_closed_when_the_container_is_a_copy():
    """A silently-discarded withhold must raise, not report success."""
    server = MCPServer("r3-copy-withhold")
    server._mcp = _CopyingContainerFastMCP()

    @server.tool()
    def echo(text: str) -> str:
        """Echo."""
        return text

    # Asserts the BEHAVIOUR (a withhold that cannot take effect must raise),
    # not one implementation's wording: the container may be rejected when it
    # is looked up, or the write may be caught as not having landed.
    with pytest.raises(MCPError):
        server.disable_tool("echo")

    # The tool is still advertised (that IS the defect) — but the operator was
    # told, and invocation is refused independently by the wrapper.
    assert "echo" in server._mcp._store
    assert server._tool_registry["echo"]["disabled"] is True
    with pytest.raises(ToolError, match="disabled"):
        server._tool_registry["echo"]["function"](text="hi")


def test_live_container_withhold_reports_no_false_alarm():
    """CONTROL: the post-condition must not fire on a normal live mapping."""
    server = MCPServer("r3-copy-control")

    @server.tool()
    def echo(text: str) -> str:
        """Echo."""
        return text

    server.disable_tool("echo")  # must NOT raise
    assert "echo" not in server._fastmcp_tool_container()
    server.enable_tool("echo")  # must NOT raise
    assert "echo" in server._fastmcp_tool_container()

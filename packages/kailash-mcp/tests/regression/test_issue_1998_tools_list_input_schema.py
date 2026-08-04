"""Regression: tools/list must advertise a real inputSchema.

#1998 — surfaced by the #1720 forest redteam (R1 correctness pass, via a
CRITICAL claim that turned out to be a symptom of this).

`MCPServer.tool()` stored NO input schema in `_tool_registry`, so
`_handle_list_tools` fell through to `info.get("input_schema", {})` and every
tool — including fully type-annotated ones — was advertised over `tools/list`
as taking no discoverable arguments. An MCP client had no protocol-level way to
learn any tool's parameters; it had to already know them.

The visible symptom was one layer up: nexus registers its workflow executor as
`async def workflow_tool(**params)`, and a strict MCP implementation
(independent `fastmcp`) rejects a `**kwargs` tool outright because there is
nothing in the signature to describe. That looked like "nexus register() is
broken"; the actual defect is that no input schema was ever derived, for any
tool, at the kailash-mcp layer.

The fix derives the schema from the decorated function's signature
(`kailash_mcp.utils.input_schema.build_input_schema`) and stores it, with an
explicit `input_schema=` override for signatures that cannot express the
contract.
"""

from __future__ import annotations

from typing import List, Literal, Optional

import pytest

from kailash_mcp.server import MCPServer
from kailash_mcp.utils import build_input_schema


@pytest.fixture
def server():
    return MCPServer("regression-1998")


@pytest.mark.regression
def test_typed_tool_advertises_its_parameters(server):
    """The originating defect: a typed signature advertised {}."""

    @server.tool()
    async def typed_tool(city: str, days: int = 3) -> dict:
        """Typed, introspectable."""
        return {}

    schema = server._tool_registry["typed_tool"]["input_schema"]

    assert schema["properties"]["city"] == {"type": "string"}
    assert schema["properties"]["days"] == {"type": "integer"}
    # `days` has a default, so it is NOT required.
    assert schema["required"] == ["city"]
    # A closed signature must say so, otherwise a client's unknown argument is
    # silently dropped instead of reported.
    assert schema["additionalProperties"] is False


@pytest.mark.regression
def test_kwargs_tool_advertises_an_honest_open_schema(server):
    """The nexus workflow_tool shape.

    An open dispatcher cannot enumerate its parameters — but
    `additionalProperties: true` states that truthfully, where an empty schema
    falsely implied the tool takes nothing.
    """

    @server.tool()
    async def open_tool(**params):
        """Open dispatcher."""
        return params

    schema = server._tool_registry["open_tool"]["input_schema"]

    assert schema["additionalProperties"] is True
    assert schema["properties"] == {}
    assert "required" not in schema


@pytest.mark.regression
def test_explicit_input_schema_overrides_derivation(server):
    """The override exists for contracts a signature cannot express."""
    explicit = {
        "type": "object",
        "properties": {"parameters": {"type": "object"}},
        "additionalProperties": True,
    }

    @server.tool(input_schema=explicit)
    async def dispatcher(**params):
        """Its real contract is known from elsewhere."""
        return params

    assert server._tool_registry["dispatcher"]["input_schema"] == explicit


@pytest.mark.regression
async def test_list_tools_surfaces_the_schema_over_the_wire(server):
    """End-to-end: the registry value must reach the JSON-RPC response.

    Asserting only the registry would leave the actual client-visible surface —
    the `tools/list` payload — unverified, which is where the defect showed.
    """

    @server.tool()
    async def wire_tool(query: str, limit: int = 10) -> dict:
        """Typed."""
        return {}

    listed = await server._handle_list_tools({}, 1)
    tools = listed.get("result", listed)["tools"]
    entry = next(t for t in tools if t["name"] == "wire_tool")

    assert entry["inputSchema"]["properties"]["query"] == {"type": "string"}
    assert entry["inputSchema"]["required"] == ["query"]


# --- the deriver itself -----------------------------------------------------


@pytest.mark.regression
def test_optional_is_not_required():
    """An Optional parameter is omittable; declaring it required makes every
    compliant client fail validation on a legal call."""

    def fn(name: str, note: Optional[str] = None): ...

    schema = build_input_schema(fn)
    assert schema["required"] == ["name"]
    assert schema["properties"]["note"] == {"type": "string"}


@pytest.mark.regression
def test_literal_becomes_an_enum():
    def fn(unit: Literal["c", "f"] = "c"): ...

    schema = build_input_schema(fn)
    assert schema["properties"]["unit"]["enum"] == ["c", "f"]
    assert schema["properties"]["unit"]["type"] == "string"


@pytest.mark.regression
def test_list_annotation_carries_items():
    def fn(tags: List[str]): ...

    schema = build_input_schema(fn)
    assert schema["properties"]["tags"] == {
        "type": "array",
        "items": {"type": "string"},
    }


@pytest.mark.regression
def test_unmappable_annotation_is_unconstrained_not_guessed():
    """Honesty over precision.

    A wrong `type` makes a client reject arguments the tool would accept; an
    absent constraint is merely uninformative.
    """

    class Custom: ...

    def fn(obj: Custom, plain=None): ...

    schema = build_input_schema(fn)
    assert schema["properties"]["obj"] == {}
    assert schema["properties"]["plain"] == {}


@pytest.mark.regression
@pytest.mark.parametrize("builtin", [len, max, print])
def test_deriver_never_raises_on_a_builtin(builtin):
    """A tool that registers beats a registration that dies on introspection.

    Builtins are the realistic uninspectable/exotic case — some expose no
    signature at all, others expose a positional-only one.
    """
    schema = build_input_schema(builtin)
    assert schema["type"] == "object"
    assert isinstance(schema["properties"], dict)


@pytest.mark.regression
def test_positional_only_params_are_not_advertised():
    """A positional-only parameter cannot be sent by name.

    Advertising it as a property would instruct a client to send an argument
    the callable rejects, so it must be omitted rather than described.
    """

    def fn(a, /, b: str = "x"): ...

    schema = build_input_schema(fn)
    assert "a" not in schema["properties"]
    assert "b" in schema["properties"]


@pytest.mark.regression
def test_self_is_not_advertised_as_a_parameter():
    class Handler:
        def method(self, value: str): ...

    schema = build_input_schema(Handler.method)
    assert "self" not in schema["properties"]
    assert schema["required"] == ["value"]

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: each newly-enveloped channel actually RUNS a convention workflow.

``test_workflow_input_envelope_entry_points`` derives the denominator and
asserts every entry point binds the envelope -- but it reads the SHAPE of the
call via AST. It cannot tell whether the bound mapping actually reaches the
node. These tests drive the channels and assert the workflow's own output, so
the two together cover shape AND behaviour.

Shape coverage is NOT behaviour coverage. Four entry points -- the two Nexus
transports (``transports/mcp.py::workflow_tool``,
``transports/websocket.py::_invoke_handler``) and the two Core SDK channels
(``api_channel.py::handle_request``, ``cli_channel.py``
``_execute_workflow_command``) -- were covered by the AST scan alone, so a
revert of any one of them to a pre-fix shape passed every test in this tree.
Each now has a driver below that executes a real workflow through a real
runtime and asserts the node's own output.

Every channel below previously raised
``NameError: name 'parameters' is not defined`` for the SAME workflow source
that succeeded on the HTTP route.
"""

import json

import pytest

from kailash.workflow.builder import WorkflowBuilder

# One workflow source for every channel, reading its argument BOTH ways so a
# channel binding only one shape fails loudly rather than passing on the shape
# it happens to support.
PARITY_CODE = "result = {'via_envelope': parameters.get('id'), 'via_toplevel': id}"
EXPECTED = {"via_envelope": 7, "via_toplevel": 7}


def _parity_workflow():
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "echo", {"code": PARITY_CODE})
    return builder.build()


def _node_result(results) -> dict:
    """Pull the single node's ``result`` dict out of a runtime results map."""
    assert isinstance(results, dict) and results, f"unexpected results: {results!r}"
    inner = results.get("echo", next(iter(results.values())))
    return inner.get("result", inner) if isinstance(inner, dict) else inner


# ---------------------------------------------------------------------------
# The shared binder itself
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_binder_binds_both_shapes():
    from kailash.workflow.input_envelope import bind_parameter_envelope

    bound = bind_parameter_envelope({"id": 7})
    assert bound["id"] == 7, bound
    assert bound["parameters"] == {"id": 7}, bound


@pytest.mark.regression
def test_binder_envelope_wins_inner_collision():
    """Precedence is fixed: `parameters` always means the FULL mapping."""
    from kailash.workflow.input_envelope import bind_parameter_envelope

    bound = bind_parameter_envelope({"parameters": {"a": 1}, "b": 2})
    assert bound["parameters"] == {"parameters": {"a": 1}, "b": 2}, bound
    assert bound["parameters"]["parameters"] == {"a": 1}, bound
    assert bound["b"] == 2, bound


@pytest.mark.regression
@pytest.mark.parametrize("empty", [None, {}])
def test_binder_binds_empty_envelope(empty):
    """An argument-less call MUST still reach the workflow's own defaults."""
    from kailash.workflow.input_envelope import bind_parameter_envelope

    assert bind_parameter_envelope(empty) == {"parameters": {}}


@pytest.mark.regression
def test_binder_does_not_mutate_caller_mapping():
    from kailash.workflow.input_envelope import bind_parameter_envelope

    original = {"id": 7}
    bind_parameter_envelope(original)
    assert original == {"id": 7}, "binder mutated the caller's mapping"


# ---------------------------------------------------------------------------
# Core SDK channels
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_mcp_channel_tools_call_binds_envelope():
    """``MCPChannel`` tools/call MUST run a convention workflow.

    Falsifying result: before the fix this raised NameError on `parameters`.
    """
    from kailash.channels.mcp_channel import MCPChannel
    from kailash.runtime.async_local import AsyncLocalRuntime

    channel = MCPChannel.__new__(MCPChannel)
    channel.runtime = AsyncLocalRuntime()
    channel._workflow_registry = {"parity": _parity_workflow()}

    class _Reg:
        handler = None
        workflow_name = "parity"

    channel._tool_registry = {"parity": _Reg()}

    response = await channel._handle_tools_call(
        {"name": "parity", "arguments": {"id": 7}}
    )
    # tools/call wraps its payload MCP-style: {"content":[{"type":"text",...}]}.
    # A NameError inside execution surfaces as a top-level "error" instead, so
    # both the success and failure shapes are distinguishable here.
    assert "error" not in response, response
    import json

    payload = json.loads(response["content"][0]["text"])
    assert "error" not in payload, payload
    assert _node_result(payload["results"]) == EXPECTED, payload


@pytest.mark.regression
@pytest.mark.asyncio
async def test_mcp_channel_execute_workflow_binds_envelope():
    """The SECOND mcp_channel execution path -- found by the derived scan.

    Neither the review nor the hand-written list named this one; the AST
    denominator surfaced it. It shares the registry with tools/call, so it
    must share the binding.
    """
    from kailash.channels.mcp_channel import MCPChannel
    from kailash.runtime.async_local import AsyncLocalRuntime

    channel = MCPChannel.__new__(MCPChannel)
    channel.runtime = AsyncLocalRuntime()
    channel._workflow_registry = {"parity": _parity_workflow()}

    response = await channel._handle_execute_workflow(
        {"workflow_name": "parity", "inputs": {"id": 7}}
    )
    assert response.get("success"), response
    assert _node_result(response["results"]) == EXPECTED, response


@pytest.mark.regression
@pytest.mark.asyncio
async def test_api_channel_handle_request_binds_envelope():
    """``APIChannel.handle_request`` MUST run a convention workflow.

    Falsifying result: with ``inputs`` passed raw this returns
    ``success=False`` carrying ``NameError: name 'parameters' is not
    defined``; with the wrapped-ONLY shape it carries
    ``NameError: name 'id' is not defined``. Until this driver existed the
    site had AST shape coverage only, so either revert stayed green.
    """
    from kailash.channels.api_channel import APIChannel
    from kailash.channels.base import ChannelConfig, ChannelType
    from kailash.runtime.local import LocalRuntime

    class _Registration:
        type = "embedded"
        workflow = _parity_workflow()

    channel = APIChannel.__new__(APIChannel)
    channel.config = ChannelConfig(
        name="api",
        channel_type=ChannelType.API,
        enable_event_routing=False,
        # enable_auth=False: exercises parameter binding, not the #2072 gate.
        enable_auth=False,
    )
    channel._event_queue = None
    channel._event_handlers = []

    # `with` per the runtime's own deprecation notice -- an unclosed
    # LocalRuntime emits DeprecationWarning from inside handle_request.
    with LocalRuntime() as runtime:

        class _Server:
            workflows = {"parity": _Registration()}

        _Server.runtime = runtime
        channel.workflow_server = _Server()

        response = await channel.handle_request(
            {"workflow_name": "parity", "inputs": {"id": 7}}
        )
    assert response.success, response.error
    assert _node_result(response.data["results"]) == EXPECTED, response.data


@pytest.mark.regression
@pytest.mark.asyncio
async def test_cli_channel_execute_workflow_command_binds_envelope():
    """The CLI channel's ``run <workflow> --input '{...}'`` path.

    Falsifying result: the same two NameErrors as above -- the CLI's
    ``--input`` JSON is the caller's workflow arguments, so it must bind
    exactly what every other channel binds.
    """
    from kailash.channels.cli_channel import CLIChannel
    from kailash.runtime.async_local import AsyncLocalRuntime

    channel = CLIChannel.__new__(CLIChannel)
    channel.runtime = AsyncLocalRuntime()
    channel.workflow_server = None
    channel._registered_workflows = {"parity": _parity_workflow()}

    response = await channel._execute_workflow_command(
        {"command_arguments": {"workflow": "parity", "input": json.dumps({"id": 7})}}
    )
    assert response.get("success"), response
    assert _node_result(response["results"]) == EXPECTED, response


# ---------------------------------------------------------------------------
# Nexus transports
#
# Driven here rather than under packages/kailash-nexus/tests/ because the
# binding contract they share is owned by kailash.workflow.input_envelope --
# the property under test is that ONE registration behaves identically on
# every transport, which is not a per-package property.
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_nexus_mcp_transport_workflow_tool_binds_envelope():
    """``transports/mcp.py::workflow_tool`` MUST run a convention workflow.

    Falsifying result: this is the site whose revert to ``{"parameters":
    kwargs}`` left the entire regression tree green. Wrapped-only now fails
    here with ``NameError: name 'id' is not defined``, and raw passthrough
    with ``NameError: name 'parameters' is not defined``.
    """
    pytest.importorskip("nexus", reason="kailash-nexus is not installed")
    from kailash.runtime.async_local import AsyncLocalRuntime
    from nexus.transports.mcp import MCPTransport

    registered: dict = {}

    class _CapturingServer:
        """Satisfies the FastMCP decorator surface, captures the closure."""

        def tool(self, *, name, description=""):
            def decorate(fn):
                registered[name] = fn
                return fn

            return decorate

    transport = MCPTransport(namespace="nexus")
    transport._server = _CapturingServer()
    transport._shared_runtime = AsyncLocalRuntime()

    transport._register_workflow_tool("parity", _parity_workflow())
    tool_fn = registered["nexus_parity"]

    # An MCP tools/call delivers the caller's arguments as kwargs.
    payload = await tool_fn(id=7)
    assert _node_result(payload["results"]) == EXPECTED, payload


@pytest.mark.regression
@pytest.mark.asyncio
async def test_nexus_websocket_transport_invoke_handler_binds_envelope():
    """``transports/websocket.py::_invoke_handler`` MUST run a convention workflow.

    Falsifying result: same two NameErrors. This drives the workflow-backed
    branch (``handler_def.func is None``), which is the branch that binds.
    """
    pytest.importorskip("nexus", reason="kailash-nexus is not installed")
    from kailash.runtime.async_local import AsyncLocalRuntime
    from nexus.registry import HandlerDef, HandlerRegistry
    from nexus.transports.websocket import WebSocketTransport

    registry = HandlerRegistry()
    registry.register_workflow("parity", _parity_workflow())

    transport = WebSocketTransport()
    transport._registry = registry
    transport._shared_runtime = AsyncLocalRuntime()

    payload = await transport._invoke_handler(
        HandlerDef(name="parity", func=None), {"id": 7}
    )
    assert _node_result(payload["results"]) == EXPECTED, payload

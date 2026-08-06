# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: each newly-enveloped channel actually RUNS a convention workflow.

``test_workflow_input_envelope_entry_points`` derives the denominator and
asserts every entry point binds the envelope -- but it reads the SHAPE of the
call via AST. It cannot tell whether the bound mapping actually reaches the
node. These tests drive the channels and assert the workflow's own output, so
the two together cover shape AND behaviour.

Each channel below previously raised
``NameError: name 'parameters' is not defined`` for the SAME workflow source
that succeeded on the HTTP route.
"""

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

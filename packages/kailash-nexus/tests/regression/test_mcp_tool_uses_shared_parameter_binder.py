# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: the MCP workflow tool MUST bind through the shared binder.

``kailash.workflow.input_envelope`` exists so that every entry point reaching
the runtime agrees on ONE parameter-envelope contract. Its module docstring
states the guarantee plainly: "Every entry point calls
:func:`bind_parameter_envelope`, so there is one contract to reason about
instead of one per channel, and a future change lands everywhere at once."

Six entry points call it. ``Nexus._register_workflow_as_mcp_tool`` open-coded
``{**params, "parameters": params}`` instead -- byte-equivalent to the helper
TODAY, and therefore invisible to any test comparing the produced inputs, but
it makes the docstring's promise false at the busiest channel. The next change
to the envelope contract would land on five channels and skip this one, which
is precisely the API/CLI/MCP divergence the helper was introduced to end.

Instrument note: equivalence-today is what makes an output comparison
non-discriminating here, so the test asserts the CALL instead -- it replaces
the shared binder and checks that the MCP path's inputs came from the
replacement. That result differs between "calls the helper" and "open-codes
the same dict", which is the property under test.
"""

import json

import pytest

from nexus import Nexus


class _CapturingRuntime:
    """Records the ``inputs`` mapping the MCP tool hands to the runtime."""

    def __init__(self) -> None:
        self.inputs = None

    async def execute_workflow_async(self, workflow, inputs=None):
        self.inputs = inputs
        return ({"node": {"result": {"ok": True}}}, "run-test")


class _CapturingServer:
    """Minimal MCP server stand-in that captures the registered tool."""

    def __init__(self) -> None:
        self.registered = None

    def tool(self, *args, **kwargs):
        def decorator(func):
            self.registered = func
            return func

        return decorator


def _nexus(port: int) -> Nexus:
    return Nexus(
        api_port=port,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_mcp_workflow_tool_binds_via_the_shared_envelope_helper(monkeypatch):
    """A change to the shared binder MUST reach the MCP tool path.

    Falsifying result: with the binding open-coded, the replacement binder is
    never consulted and ``inputs`` carries no marker -- the assertion below
    fails with the raw ``{**params, "parameters": params}`` mapping.
    """
    import kailash.workflow.input_envelope as envelope_module

    def _marked_binder(params):
        bound = dict(params or {})
        bound["parameters"] = dict(params or {})
        bound["__bound_by_shared_helper__"] = True
        return bound

    monkeypatch.setattr(envelope_module, "bind_parameter_envelope", _marked_binder)

    app = _nexus(8281)
    runtime = _CapturingRuntime()
    server = _CapturingServer()
    app.runtime = runtime
    app._mcp_server = server

    try:
        app._register_workflow_as_mcp_tool("probe_tool", object())
        assert server.registered is not None, "tool was never registered"

        result = await server.registered(user_id="u1", limit=10)

        assert runtime.inputs is not None, "runtime was never invoked"
        assert runtime.inputs.get("__bound_by_shared_helper__") is True, (
            "the MCP tool did not route through "
            "kailash.workflow.input_envelope.bind_parameter_envelope; inputs "
            f"were {runtime.inputs!r}"
        )
        # The tool's own contract is unchanged: it still returns JSON text.
        assert json.loads(result) == {"ok": True}
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_mcp_workflow_tool_binding_shape_is_unchanged():
    """The real binder MUST still produce the both-shapes envelope.

    Guards the wrong fix (routing through the helper but dropping the
    workflow-level splat, or letting a caller key named ``parameters`` win
    over the envelope). This is the API/CLI/MCP parity contract.
    """
    app = _nexus(8282)
    runtime = _CapturingRuntime()
    server = _CapturingServer()
    app.runtime = runtime
    app._mcp_server = server

    try:
        app._register_workflow_as_mcp_tool("probe_shape", object())
        await server.registered(user_id="u1", limit=10)

        assert runtime.inputs["user_id"] == "u1", runtime.inputs
        assert runtime.inputs["limit"] == 10, runtime.inputs
        assert runtime.inputs["parameters"] == {"user_id": "u1", "limit": 10}, (
            "the `parameters` envelope every parameters.get(...) workflow "
            f"depends on was not bound: {runtime.inputs!r}"
        )
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_mcp_workflow_tool_envelope_wins_a_colliding_caller_key():
    """A caller key literally named ``parameters`` MUST lose to the envelope.

    Fixed precedence, shared with every other channel: the envelope binding is
    a contract workflows depend on, so it must not become conditional on
    caller data.
    """
    app = _nexus(8283)
    runtime = _CapturingRuntime()
    server = _CapturingServer()
    app.runtime = runtime
    app._mcp_server = server

    try:
        app._register_workflow_as_mcp_tool("probe_collision", object())
        await server.registered(parameters={"caller": "value"}, other=1)

        assert runtime.inputs["parameters"] == {
            "parameters": {"caller": "value"},
            "other": 1,
        }, f"envelope precedence differs from the shared binder: {runtime.inputs!r}"
    finally:
        if app._running:
            app.stop()

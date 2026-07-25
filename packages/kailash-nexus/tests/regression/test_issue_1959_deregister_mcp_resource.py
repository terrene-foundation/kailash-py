# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: #1959 BUG-1 — ``Nexus.deregister`` removes the workflow's MCP
resource from the REAL MCP server.

``_deregister_workflow_mcp`` probed ``server._resources`` and
``server._resource_manager._resources`` for the resource half — but the REAL
``kailash_mcp.MCPServer`` stores workflow resources in ``_resource_registry``
(and mirrors them into the underlying official FastMCP
``server._mcp._resource_manager._resources``). Neither probed attr exists on the
real server, so ``workflow://<name>`` was never dropped. A redeploy
(register -> deregister -> re-register) then left the stale resource in place
and re-register emitted ``Resource already exists: workflow://<name>`` —
contradicting ``deregister``'s "removed from all channels" docstring and
#1959's redeploy-idempotency goal. (The tool half's underlying FastMCP store
leaked the same way, warning ``Tool already exists`` on re-register.)

Walks the REAL documented flow (a real ``Nexus`` instance + the real MCP
server) per rules/testing.md Tier 2 (no mocking). The 16 e2e tests missed this
because their fixture starts an EMPTY registry then registers AFTER start,
never exercising the redeploy path.
"""

import logging

import pytest

from nexus import Nexus


def _workflow():
    """Build a trivial real workflow (no mocking)."""
    from kailash.workflow.builder import WorkflowBuilder

    wf = WorkflowBuilder()
    wf.add_node("PythonCodeNode", "n", {"code": "result = {'ok': True}"})
    return wf.build()


@pytest.mark.regression
def test_deregister_removes_mcp_resource_from_real_server():
    """deregister drops ``workflow://<name>`` from the REAL MCP server's
    ``_resource_registry`` (and the underlying FastMCP store), so a re-register
    installs a fresh handler instead of colliding."""
    app = Nexus(auto_discovery=False)
    server = app._mcp_server
    # The real kailash_mcp MCPServer keeps resources in _resource_registry.
    # Pin the store this regression is about, so a future backend swap surfaces
    # here rather than silently passing.
    assert isinstance(getattr(server, "_resource_registry", None), dict), (
        "expected the real kailash_mcp.MCPServer with a _resource_registry; "
        f"got {type(server).__name__}"
    )

    app.register("demo", _workflow())
    uri = "workflow://demo"
    assert uri in server._resource_registry, "register must add the MCP resource"

    app.deregister("demo")

    # The core assertion: the resource is GONE from the store register wrote to.
    assert uri not in server._resource_registry, (
        "deregister must remove the MCP resource from _resource_registry "
        "(BUG-1: it leaked because the old probes looked at non-existent "
        "_resources / _resource_manager attrs)"
    )
    # And symmetrically from the underlying official-FastMCP resource manager,
    # so re-register does not collide.
    mcp = getattr(server, "_mcp", None)
    rm = getattr(mcp, "_resource_manager", None)
    if isinstance(getattr(rm, "_resources", None), dict):
        assert uri not in rm._resources, (
            "deregister must also remove the resource from the underlying "
            "FastMCP resource manager"
        )


@pytest.mark.regression
def test_redeploy_reregister_emits_no_already_exists_warning(caplog):
    """After deregister, a re-register must NOT warn ``Resource already exists``
    / ``Tool already exists`` — the stale MCP artifacts were fully removed."""
    app = Nexus(auto_discovery=False)
    app.register("demo", _workflow())
    app.deregister("demo")

    with caplog.at_level(logging.WARNING):
        app.register("demo", _workflow())

    offending = [
        r.getMessage()
        for r in caplog.records
        if "already exists" in r.getMessage().lower()
    ]
    assert not offending, (
        "re-register after deregister must not warn about stale MCP artifacts; "
        f"got: {offending}"
    )

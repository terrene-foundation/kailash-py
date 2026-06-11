# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for #1285: Nexus.close() must cascade-close internal runtimes.

Root cause (two leaks, same bug class — runtime references never released on
the synchronous close() teardown path):

1. The enterprise gateway (``EnterpriseWorkflowServer`` at
   ``Nexus._http_transport.gateway``) ``acquire()``s ``Nexus.runtime`` at
   construction (ref_count 1 -> 2). ``Nexus.close()`` released the owner
   reference once (2 -> 1) but never asked the gateway to release its acquired
   reference, so the runtime stayed at ref_count 1 and emitted
   ``ResourceWarning: Unclosed AsyncLocalRuntime (ref_count=1)`` at GC.

2. ``WorkflowServer.register_workflow`` builds a ``WorkflowAPI`` per workflow,
   each of which constructs its OWN ``AsyncLocalRuntime``. These were never
   tracked or closed — a second orphan runtime leaked per registered workflow.

Fix: ``Nexus.close()`` closes the gateway; ``EnterpriseWorkflowServer.close()``
cascades via ``super().close()`` to the base ``WorkflowServer.close()`` which
releases every tracked ``WorkflowAPI`` runtime.

Sibling of #211 (which made the gateway SHARE the runtime); this pins the
RELEASE half of the same lifecycle contract.
"""
from __future__ import annotations

import gc
import warnings

import pytest

from kailash.runtime.async_local import AsyncLocalRuntime


def _leaked_runtimes():
    """Return live AsyncLocalRuntime instances still holding a reference."""
    gc.collect()
    return [
        o
        for o in gc.get_objects()
        if isinstance(o, AsyncLocalRuntime) and getattr(o, "_ref_count", 0) > 0
    ]


@pytest.mark.regression
class TestIssue1285CloseCascadesRuntime:
    """Nexus.close() drives every internal runtime to ref_count 0."""

    def test_close_releases_all_runtime_refs(self):
        from nexus import Nexus

        app = Nexus(api_port=20101, mcp_port=20102, enable_durability=False)

        @app.handler("ping")
        def ping(params):
            return {"ok": True}

        # The owned runtime is shared with the gateway (ref_count > 1 here).
        assert app.runtime.ref_count >= 1
        app.close()

        leaked = _leaked_runtimes()
        assert not leaked, (
            f"{len(leaked)} AsyncLocalRuntime(s) still held after Nexus.close(): "
            f"{[(id(o), o._ref_count) for o in leaked]}"
        )

    def test_close_emits_no_resource_warning(self):
        from nexus import Nexus

        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)

            app = Nexus(api_port=20103, mcp_port=20104, enable_durability=False)

            @app.handler("a")
            def a(params):
                return {"ok": True}

            @app.handler("b")
            def b(params):
                return {"ok": True}

            app.close()
            # Force the finalizer path that would emit the ResourceWarning.
            del app, a, b
            gc.collect()
            # Reaching here under simplefilter("error") means no warning fired.

    def test_double_close_is_idempotent(self):
        from nexus import Nexus

        app = Nexus(api_port=20105, mcp_port=20106, enable_durability=False)
        app.close()
        app.close()  # must not raise
        assert app.runtime is None


@pytest.mark.regression
class TestWorkflowServerClosesWorkflowApiRuntimes:
    """Core-SDK half: WorkflowServer.close() releases per-workflow runtimes."""

    def test_register_then_close_releases_workflow_api_runtime(self):
        from kailash.servers.workflow_server import WorkflowServer
        from kailash.workflow.builder import WorkflowBuilder

        server = WorkflowServer(title="test")

        wf = WorkflowBuilder()
        wf.add_node("PythonCodeNode", "n", {"code": "result = 1"})
        server.register_workflow("demo", wf.build())

        # The WorkflowAPI is now tracked and its runtime is live.
        assert "demo" in server._workflow_apis
        api = server._workflow_apis["demo"]
        runtime = api.runtime
        assert runtime is not None
        assert runtime.ref_count > 0

        server.close()

        # The WorkflowAPI's runtime was released, and tracking was cleared.
        assert server._workflow_apis == {}
        assert runtime.ref_count == 0

    def test_workflow_api_gateway_close_releases_runtime(self):
        """Sibling site (kailash.api.gateway.WorkflowAPIGateway), same bug class."""
        from kailash.api.gateway import WorkflowAPIGateway
        from kailash.workflow.builder import WorkflowBuilder

        gateway = WorkflowAPIGateway(title="test")

        wf = WorkflowBuilder()
        wf.add_node("PythonCodeNode", "n", {"code": "result = 1"})
        gateway.register_workflow("demo", wf.build())

        assert "demo" in gateway._workflow_apis
        runtime = gateway._workflow_apis["demo"].runtime
        assert runtime is not None and runtime.ref_count > 0

        gateway.close()

        assert gateway._workflow_apis == {}
        assert runtime.ref_count == 0


@pytest.mark.regression
class TestTransportSyncCloseReleasesSharedRuntime:
    """LOW-1: MCP/WS transports lazily acquire a shared runtime on tool
    invocation and previously released it only in async stop(). The sync
    close() path (teardown without a prior stop()) must release it too.
    """

    def test_mcp_transport_close_releases_shared_runtime(self):
        from nexus.transports.mcp import MCPTransport

        rt = AsyncLocalRuntime()
        base = rt.ref_count
        transport = MCPTransport(runtime=rt)
        transport._get_shared_runtime()  # lazy acquire (ref +1)
        assert rt.ref_count == base + 1

        transport.close()
        assert transport._shared_runtime is None
        assert rt.ref_count == base
        transport.close()  # idempotent
        assert rt.ref_count == base
        rt.close()

    def test_websocket_transport_close_releases_shared_runtime(self):
        from nexus.transports.websocket import WebSocketTransport

        rt = AsyncLocalRuntime()
        base = rt.ref_count
        transport = WebSocketTransport(runtime=rt)
        transport._get_shared_runtime()  # lazy acquire (ref +1)
        assert rt.ref_count == base + 1

        transport.close()
        assert transport._shared_runtime is None
        assert rt.ref_count == base
        transport.close()  # idempotent
        assert rt.ref_count == base
        rt.close()

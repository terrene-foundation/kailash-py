"""#1972 follow-up — ``Nexus.register()`` leaves nothing half-registered.

#1972 moved ``validate_workflow_name`` to the top of ``register()``, so a
REJECTED NAME never reaches a store. It also promoted a previously-silent MCP
tool-registration failure to a ``RuntimeError`` — and that raise fires from the
LAST step of a multi-store write, long after the registry entry and the gateway
route have landed. The name half of the fail-closed promise was honoured; the
mid-sequence half was not.

``register()`` writes seven stores across three subsystems:

1. ``HandlerRegistry._workflows[name]``
2. ``HandlerRegistry._workflow_metadata[name]``
3. the gateway's ``/workflows/{name}`` mount (``gateway.workflows[name]``)
4. ``MCPServer._tool_registry[name]``                     ─┐ the four MCP
5. ``MCPServer._mcp._tool_manager._tools[name]``           │ backing stores
6. ``MCPServer._resource_registry["workflow://{name}"]``   │ #1959 enumerated
7. ``MCPServer._mcp._resource_manager._resources[...]``   ─┘

Plus the ``metadata`` attribute of the caller's own ``Workflow`` object.

These tests pin the contract on the failure paths: a failed registration of a
NEW name leaves all seven empty, and a failed RE-registration restores the
previous entry instead of clobbering a working workflow.
"""

import pytest
from kailash.workflow.builder import WorkflowBuilder

pytestmark = pytest.mark.regression


def _workflow():
    """A real single-node Workflow.

    Not a ``MagicMock``: a mock satisfies every attribute access the
    registration path performs, so the store assertions below would pass
    against a path that recorded nothing.
    """
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "node", {"code": "result = {}"})
    return builder.build()


def _store_state(app, name):
    """Read ``name``'s presence in every store ``register()`` writes."""
    server = app._mcp_server
    gateway = app._http_transport.gateway
    mcp = getattr(server, "_mcp", None)
    tool_manager = getattr(mcp, "_tool_manager", None)
    resource_manager = getattr(mcp, "_resource_manager", None)
    uri = f"workflow://{name}"
    return {
        "registry": name in app._registry._workflows,
        "registry_metadata": name in app._registry._workflow_metadata,
        "gateway": name in getattr(gateway, "workflows", {}),
        "mcp_tool_registry": name in getattr(server, "_tool_registry", {}),
        "mcp_fastmcp_tools": name in (getattr(tool_manager, "_tools", {}) or {}),
        "mcp_resource_registry": uri
        in (getattr(server, "_resource_registry", {}) or {}),
        "mcp_fastmcp_resources": uri
        in (getattr(resource_manager, "_resources", {}) or {}),
    }


# ---------------------------------------------------------------------------
# A failure mid-sequence leaves nothing behind
# ---------------------------------------------------------------------------


def test_failure_after_partial_write_leaves_every_store_empty(monkeypatch):
    """The MCP resource step is the last write; failing it must unwind all six prior.

    By the time ``_register_workflow_as_mcp_resource`` runs, the registry
    entry, the gateway mount and BOTH MCP tool stores are already populated.
    Before the rollback landed, the raise propagated and left every one of
    them in place: ``list_workflows()`` advertised a workflow whose
    registration had failed, and ``deregister()`` was the only way out.
    """
    from nexus import Nexus
    from nexus.core import Nexus as NexusClass

    def _boom(self, name, workflow):
        raise RuntimeError("resource registration exploded")

    app = Nexus()
    try:
        monkeypatch.setattr(NexusClass, "_register_workflow_as_mcp_resource", _boom)

        with pytest.raises(RuntimeError, match="resource registration exploded"):
            app.register("atomic_wf", _workflow(), metadata={"version": "1"})

        state = _store_state(app, "atomic_wf")
        assert not any(state.values()), (
            "register() failed but left state behind in "
            f"{[store for store, present in state.items() if present]}"
        )
    finally:
        app.close()


def test_failed_mcp_tool_registration_leaves_no_registry_or_route(monkeypatch):
    """The RuntimeError #1972 introduced must not strand a registry entry.

    #1972 replaced a warn-and-continue with a raise so a tool that
    ``tools/list`` would never advertise stops reporting success. That raise
    fires AFTER the registry entry and gateway route land, so without a
    rollback the fix traded a silent MCP failure for a half-registered
    workflow.
    """
    from nexus import Nexus
    from nexus.core import Nexus as NexusClass

    def _boom(self, name, workflow):
        raise RuntimeError("tool registration exploded")

    app = Nexus()
    try:
        monkeypatch.setattr(NexusClass, "_register_workflow_as_mcp_tool", _boom)

        with pytest.raises(RuntimeError, match="tool registration exploded"):
            app.register("tool_fail_wf", _workflow())

        state = _store_state(app, "tool_fail_wf")
        assert not any(state.values()), (
            "a failed MCP tool registration left state behind in "
            f"{[store for store, present in state.items() if present]}"
        )
        assert "tool_fail_wf" not in app._registry.list_workflows()
    finally:
        app.close()


def test_failed_registration_restores_caller_workflow_metadata(monkeypatch):
    """The caller's Workflow object must not keep merged metadata after a failure.

    ``register()`` reassigns ``workflow.metadata`` before the MCP steps run.
    The object belongs to the caller and may be registered under several
    names, so a failed call must hand it back exactly as received.
    """
    from nexus import Nexus
    from nexus.core import Nexus as NexusClass

    def _boom(self, name, workflow):
        raise RuntimeError("resource registration exploded")

    workflow = _workflow()
    workflow.metadata = {"owner": "original"}

    app = Nexus()
    try:
        monkeypatch.setattr(NexusClass, "_register_workflow_as_mcp_resource", _boom)

        with pytest.raises(RuntimeError):
            app.register("meta_wf", workflow, metadata={"owner": "merged", "v": "2"})

        assert workflow.metadata == {"owner": "original"}, (
            "a failed register() left merged metadata on the caller's "
            f"Workflow object: {workflow.metadata}"
        )
    finally:
        app.close()


# ---------------------------------------------------------------------------
# A failed RE-registration must not destroy the working registration
# ---------------------------------------------------------------------------


def test_failed_reregistration_restores_previous_registration():
    """A duplicate register() must leave the FIRST workflow serving.

    The gateway raises ``ValueError: Workflow '<name>' already registered``,
    but by then the registry entry has already been overwritten with the new
    workflow. The registry and the gateway then disagree about which
    workflow the name addresses. Rollback restores the prior entry.
    """
    from nexus import Nexus

    first = _workflow()
    second = _workflow()

    app = Nexus()
    try:
        app.register("dup_wf", first, metadata={"generation": "first"})

        with pytest.raises(ValueError, match="already registered"):
            app.register("dup_wf", second, metadata={"generation": "second"})

        assert app._registry._workflows["dup_wf"] is first, (
            "the failed re-registration left the NEW workflow in the registry "
            "while the gateway still routes to the old one"
        )
        assert app._registry.get_workflow_metadata("dup_wf") == {"generation": "first"}
    finally:
        app.close()


def test_deregister_then_register_still_replaces_cleanly():
    """Rollback must not break the documented redeploy path (#1959)."""
    from nexus import Nexus

    first = _workflow()
    second = _workflow()

    app = Nexus()
    try:
        app.register("redeploy_wf", first)
        assert app.deregister("redeploy_wf") is True
        app.register("redeploy_wf", second)

        assert app._registry._workflows["redeploy_wf"] is second
        state = _store_state(app, "redeploy_wf")
        assert all(
            state[store]
            for store in (
                "registry",
                "gateway",
                "mcp_tool_registry",
                "mcp_fastmcp_tools",
                "mcp_resource_registry",
                "mcp_fastmcp_resources",
            )
        ), f"redeploy did not repopulate every store: {state}"
    finally:
        app.close()


# ---------------------------------------------------------------------------
# Server-level preconditions are checked BEFORE any store is written
# ---------------------------------------------------------------------------


def test_missing_mcp_tool_surface_rejected_before_any_write(caplog):
    """Whether a tool CAN be registered is a server property — check it first.

    A server exposing no ``tool()`` decorator can never accept the workflow,
    and that is knowable before the registry entry and gateway route land.
    Discovering it at the last step means writing five stores and unwinding
    them again.

    The end state is the same either way (rollback would clean up), so the
    discriminator is the rollback warning: a clean up-front rejection never
    enters the mutating phase and therefore never logs one.
    """
    import logging

    from nexus import Nexus

    class NoToolSurfaceServer:
        """Exposes neither ``tool()`` nor ``register_workflow``.

        An explicit class, not a ``MagicMock``: a mock auto-creates every
        attribute the precheck probes, so the branch under test would never
        be reached.
        """

    app = Nexus()
    real_server = app._mcp_server
    try:
        app._mcp_server = NoToolSurfaceServer()

        with caplog.at_level(logging.WARNING, logger="nexus.core"):
            with pytest.raises(RuntimeError, match="tools/list"):
                app.register("no_surface_wf", _workflow())

        assert "no_surface_wf" not in app._registry._workflows
        assert "no_surface_wf" not in getattr(
            app._http_transport.gateway, "workflows", {}
        )

        rolled_back = [
            record
            for record in caplog.records
            if "rolled back" in record.getMessage()
            or "restored the previous" in record.getMessage()
        ]
        assert not rolled_back, (
            "an unregisterable server was detected only after stores had been "
            "written, so the rejection cost a rollback instead of being "
            f"refused up front: {[r.getMessage() for r in rolled_back]}"
        )
    finally:
        # Restore before close(): close() releases the runtime refs held by
        # whatever _mcp_server points at (issue #1285).
        app._mcp_server = real_server
        app.close()


# ---------------------------------------------------------------------------
# The ``_tools`` fallback is gone — it could only ever hide a failure
# ---------------------------------------------------------------------------


def test_tools_dict_is_never_written_as_a_fallback():
    """A ``_tools``-only server must RAISE, not silently record the tool.

    ``_tools`` exists only on the FastMCP fallback shim
    (``kailash_mcp/server.py:1333-1348``), which ``MCPServer`` assigns to
    ``self._mcp`` — never to itself. ``_handle_list_tools``
    (``kailash_mcp/server.py:2832-2837``) iterates ``_tool_registry``, so a
    tool written directly into ``_tools`` is invisible to ``tools/list``.
    The old fallback branch therefore could not make a tool reachable; it
    could only convert a loud failure into a registration that reports
    success and advertises nothing (zero-tolerance Rule 3).
    """
    from nexus import Nexus

    class ToolsDictOnlyServer:
        """Has the ``_tools`` dict but no ``tool()`` decorator."""

        def __init__(self):
            self._tools = {}

    app = Nexus()
    real_server = app._mcp_server
    stub = ToolsDictOnlyServer()
    try:
        app._mcp_server = stub

        with pytest.raises(RuntimeError, match="tools/list"):
            app._register_workflow_as_mcp_tool("shim_wf", _workflow())

        assert stub._tools == {}, (
            "the tool was written into the _tools dict, which no JSON-RPC "
            "handler reads — a silent no-op reported as success"
        )
    finally:
        app._mcp_server = real_server
        app.close()


def test_real_mcp_server_has_no_tools_attribute():
    """Pins WHY the fallback was dead code, so a reviewer need not re-derive it.

    If a future backend change puts a ``_tools`` dict on the server object
    itself, this fails and forces a re-read of the tool-registration
    contract rather than letting a silent second store reappear.
    """
    from nexus import Nexus

    app = Nexus()
    try:
        assert not hasattr(app._mcp_server, "_tools"), (
            "MCPServer grew a _tools attribute; re-check whether tools/list "
            "reads it before treating it as a registration surface"
        )
        assert hasattr(app._mcp_server, "_tool_registry")
    finally:
        app.close()

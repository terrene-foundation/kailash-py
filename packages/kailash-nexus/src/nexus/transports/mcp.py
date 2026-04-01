# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional

from nexus.registry import HandlerDef, HandlerRegistry
from nexus.transports.base import Transport

logger = logging.getLogger(__name__)

__all__ = ["MCPTransport"]


class MCPTransport(Transport):
    """MCP transport backed by FastMCP.

    Registers all Nexus handlers as MCP tools with namespace prefix
    to avoid collisions with platform server tools. Runs in a background
    thread with its own event loop (matching current MCP server behavior).

    Full FastMCP wiring is deferred until MCP-511 cleanup completes.
    This implementation provides the Transport interface and tool
    registration logic.

    Args:
        port: MCP WebSocket server port (default 3001).
        namespace: Tool name prefix (default "nexus").
        server_name: FastMCP server name (default "kailash-nexus").
    """

    def __init__(
        self,
        *,
        port: int = 3001,
        namespace: str = "nexus",
        server_name: str = "kailash-nexus",
        runtime=None,
    ):
        self._port = port
        self._namespace = namespace
        self._server_name = server_name
        self._injected_runtime = runtime
        self._server = None  # FastMCP instance (lazy)
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._registry: Optional[HandlerRegistry] = None

    @property
    def name(self) -> str:
        return "mcp"

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def port(self) -> int:
        """The MCP server port."""
        return self._port

    async def start(self, registry: HandlerRegistry) -> None:
        """Start MCP transport in a background thread.

        Creates the FastMCP server, registers all handlers as tools,
        and starts the server in a daemon thread.
        """
        if self._running:
            return

        self._registry = registry

        try:
            from fastmcp import FastMCP
        except ImportError:
            logger.info(
                "fastmcp not available -- MCPTransport will not start. "
                "Install with: pip install fastmcp"
            )
            return

        self._server = FastMCP(self._server_name)

        # Register all current handlers as MCP tools
        for handler_def in registry.list_handlers():
            self._register_tool(handler_def)

        # Register workflow-backed handlers
        for wf_name in registry.list_workflows():
            workflow = registry.get_workflow(wf_name)
            if workflow is not None:
                self._register_workflow_tool(wf_name, workflow)

        # Start in background thread
        self._thread = threading.Thread(
            target=self._run_in_thread,
            daemon=True,
            name="nexus-mcp-transport",
        )
        self._thread.start()
        self._running = True
        logger.info(f"MCPTransport started on port {self._port}")

    async def stop(self) -> None:
        """Stop the MCP transport and background thread."""
        self._running = False
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._server = None
        # Release shared runtime (NX-01 fix: prevent connection leak)
        if hasattr(self, "_shared_runtime") and self._shared_runtime is not None:
            self._shared_runtime.release()
            self._shared_runtime = None
        logger.info("MCPTransport stopped")

    def on_handler_registered(self, handler_def: HandlerDef) -> None:
        """Hot-register a new MCP tool for a handler added at runtime."""
        if self._server is not None:
            self._register_tool(handler_def)

    def health_check(self) -> Dict[str, Any]:
        """MCP transport health status."""
        return {
            "transport": "mcp",
            "running": self._running,
            "port": self._port,
            "server": self._server is not None,
        }

    def _register_tool(self, handler_def: HandlerDef) -> None:
        """Register a handler as a FastMCP tool."""
        tool_name = f"{self._namespace}_{handler_def.name}"
        func = handler_def.func
        if func is None:
            return  # Workflow-only handlers have no direct func

        self._server.tool(name=tool_name, description=handler_def.description)(func)
        logger.debug(f"MCP tool registered: {tool_name}")

    def _register_workflow_tool(self, name: str, workflow) -> None:
        """Register a workflow as a FastMCP tool."""
        tool_name = f"{self._namespace}_{name}"

        async def workflow_tool(**kwargs):
            """Execute workflow via MCP.

            Uses the shared runtime to avoid orphan connection pools (NX-01).
            """
            runtime = self._get_shared_runtime()
            results, run_id = await runtime.execute_workflow_async(workflow, kwargs)
            return {"results": results, "run_id": run_id}

        self._server.tool(name=tool_name, description=f"Execute {name} workflow")(
            workflow_tool
        )
        logger.debug(f"MCP workflow tool registered: {tool_name}")

    def _get_shared_runtime(self):
        """Return a shared AsyncLocalRuntime, creating once on first use.

        If an injected runtime was provided at construction, acquires from it
        instead of creating a new pool (fixes orphan runtime per #211).
        """
        if not hasattr(self, "_shared_runtime") or self._shared_runtime is None:
            injected = getattr(self, "_injected_runtime", None)
            if injected is not None:
                self._shared_runtime = injected.acquire()
            else:
                from kailash.runtime import AsyncLocalRuntime

                self._shared_runtime = AsyncLocalRuntime()
        return self._shared_runtime

    def _run_in_thread(self) -> None:
        """Run the FastMCP server in a background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(
                self._server.run_ws(
                    host="127.0.0.1", port=self._port
                )  # H-NEW-02: bind to localhost only
            )
        except Exception as e:
            if self._running:  # Only log if not intentionally stopped
                logger.warning(f"MCP transport error: {e}")
        finally:
            self._loop.close()

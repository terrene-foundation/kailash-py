"""MCP Channel implementation for Model Context Protocol integration."""

import asyncio
import inspect
import json
import logging
import threading
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .base import (
    Channel,
    ChannelConfig,
    ChannelEvent,
    ChannelResponse,
    ChannelStatus,
    ChannelType,
)

try:
    from ..middleware.mcp.enhanced_server import MCPServerConfig as _MCPServerConfig
    from ..middleware.mcp.enhanced_server import (
        MiddlewareMCPServer as _MiddlewareMCPServer,
    )

    MCPServerConfig: Any = _MCPServerConfig
    MiddlewareMCPServer: Any = _MiddlewareMCPServer
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False

    # Create mock classes for when MCP is not available
    class _MiddlewareMCPServerFallback:
        def __init__(self, *args: Any, **kwargs: Any):
            raise ImportError("MCP server not available")

    class _MCPServerConfigFallback:
        def __init__(self) -> None:
            pass

    MiddlewareMCPServer: Any = _MiddlewareMCPServerFallback
    MCPServerConfig: Any = _MCPServerConfigFallback


from ..runtime.local import LocalRuntime
from ..workflow import Workflow

logger = logging.getLogger(__name__)


@dataclass
class MCPToolRegistration:
    """Represents an MCP tool registration."""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    handler: Optional[Callable] = None
    workflow_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MCPChannel(Channel):
    """Model Context Protocol channel implementation.

    This channel provides MCP server capabilities, allowing external MCP clients
    to connect and execute workflows through the MCP protocol.
    """

    #: Seconds :meth:`stop` waits for the dedicated MCP server thread to exit
    #: after ``mcp_server.stop()`` before logging a WARN and moving on. Bounded
    #: because the thread is a daemon -- an unbounded join would reintroduce the
    #: shutdown hang this timeout exists to avoid.
    _MCP_SERVER_JOIN_TIMEOUT: float = 5.0

    def __init__(
        self,
        config: ChannelConfig,
        mcp_server: Optional[Any] = None,
        runtime: Optional[LocalRuntime] = None,
    ):
        """Initialize MCP channel.

        Args:
            config: Channel configuration
            mcp_server: Optional existing MCP server, will create one if not provided
            runtime: Optional shared runtime. If provided, its ref count is
                incremented via acquire(). If None a new LocalRuntime is created.
        """
        super().__init__(config)

        # Tool and workflow registry (initialize before creating MCP server)
        self._tool_registry: Dict[str, MCPToolRegistration] = {}
        self._workflow_registry: Dict[str, Workflow] = {}

        # Create or use provided MCP server
        if mcp_server:
            self.mcp_server = mcp_server
        else:
            self.mcp_server = self._create_mcp_server()

        # Runtime for executing workflows
        if runtime is not None:
            self.runtime = runtime.acquire()
            self._owns_runtime = False
        else:
            self.runtime = LocalRuntime()
            self._owns_runtime = True

        # MCP-specific state
        self._clients: Dict[str, Dict[str, Any]] = {}
        self._server_task: Optional[asyncio.Task] = None
        # The blocking ``MCPServer.run()`` loop runs on a DEDICATED daemon
        # thread, never on asyncio's default executor -- see :meth:`start` for
        # the interpreter-shutdown hang that dispatch caused.
        self._mcp_server_thread: Optional[threading.Thread] = None

        logger.info(f"Initialized MCP channel {self.name}")

    def _create_mcp_server(self) -> Any:
        """Create a new MCP server with channel configuration."""
        if not _MCP_AVAILABLE:
            raise ImportError("MCP server components not available")

        # Extract MCP config from channel config with platform adapter support
        from kailash.adapters import MCPPlatformAdapter

        mcp_config = MCPServerConfig()

        # Check if we have platform-format configuration
        platform_config = self.config.extra_config.get("platform_config")
        if platform_config and isinstance(platform_config, dict):
            # Translate platform configuration to SDK format
            try:
                translated_config = MCPPlatformAdapter.translate_server_config(
                    platform_config
                )
                mcp_config.name = translated_config.get(
                    "name", f"{self.name}-mcp-server"
                )
                mcp_config.description = translated_config.get(
                    "description", f"MCP server for {self.name} channel"
                )
            except Exception as e:
                logger.warning(f"Failed to translate platform config: {e}")
                # Fall back to default configuration
                mcp_config.name = f"{self.name}-mcp-server"
                mcp_config.description = f"MCP server for {self.name} channel"
        else:
            # Use direct configuration
            mcp_config.name = self.config.extra_config.get(
                "server_name", f"{self.name}-mcp-server"
            )
            mcp_config.description = self.config.extra_config.get(
                "description", f"MCP server for {self.name} channel"
            )

        # MiddlewareMCPServer only accepts config, event_stream, and agent_ui
        # Host and port are handled by the channel itself, not the MCP server
        server = MiddlewareMCPServer(config=mcp_config)

        # Set up default tools
        self._setup_default_tools(server)

        return server

    def _setup_default_tools(self, server: Any) -> None:
        """Set up default MCP tools for workflow execution."""

        # Tool: List available workflows
        self.register_tool(
            name="list_workflows",
            description="List all available workflows in this channel",
            parameters={},
            handler=self._handle_list_workflows,
        )

        # Tool: Execute workflow
        self.register_tool(
            name="execute_workflow",
            description="Execute a workflow with given parameters",
            parameters={
                "workflow_name": {
                    "type": "string",
                    "description": "Name of the workflow to execute",
                    "required": True,
                },
                "inputs": {
                    "type": "object",
                    "description": "Input parameters for the workflow",
                    "required": False,
                },
            },
            handler=self._handle_execute_workflow,
        )

        # Tool: Get workflow schema
        self.register_tool(
            name="get_workflow_schema",
            description="Get the input/output schema for a workflow",
            parameters={
                "workflow_name": {
                    "type": "string",
                    "description": "Name of the workflow",
                    "required": True,
                }
            },
            handler=self._handle_get_workflow_schema,
        )

        # Tool: Channel status
        self.register_tool(
            name="channel_status",
            description="Get status information about this MCP channel",
            parameters={
                "verbose": {
                    "type": "boolean",
                    "description": "Include detailed status information",
                    "required": False,
                }
            },
            handler=self._handle_channel_status,
        )

    def _run_mcp_server_blocking(self) -> None:
        """Body of the dedicated MCP server thread.

        Runs the blocking ``MCPServer.run()`` serve loop. Any exception is
        logged with its traceback -- the thread is the only frame that can see
        it, so swallowing it silently would make a dead MCP channel
        indistinguishable from a healthy one.
        """
        try:
            self.mcp_server.run()
        except Exception as e:
            logger.error(
                "MCP channel %s server loop terminated with an error: %s",
                self.name,
                e,
                exc_info=True,
            )

    async def start(self) -> None:
        """Start the MCP channel server."""
        if self.status == ChannelStatus.RUNNING:
            logger.warning(f"MCP channel {self.name} is already running")
            return

        try:
            self.status = ChannelStatus.STARTING
            self._setup_event_queue()

            # Start MCP server (Core SDK uses run() method, not start())
            if hasattr(self.mcp_server, "run"):
                # ``MCPServer.run()`` is a BLOCKING serve loop -- for
                # ``transport == "websocket"`` it enters
                # ``asyncio.run(self._run_websocket())`` and never returns until
                # the server is torn down.
                #
                # It MUST NOT be dispatched onto asyncio's DEFAULT executor
                # (``loop.run_in_executor(None, ...)``). That pool's workers are
                # registered in ``concurrent.futures.thread._threads_queues``,
                # and the ``_python_exit`` hook -- which CPython runs from
                # ``threading._shutdown()`` -- ``join()``s every one of them
                # UNCONDITIONALLY, daemon flag included. A worker parked inside
                # ``run()`` never returns to its work queue, so that join blocks
                # forever and the entire process hangs at interpreter exit
                # (issue: nexus suite printed its full summary then never
                # exited; the main thread sat in
                # ``_python_exit -> Thread.join``).
                #
                # A dedicated daemon thread is NOT in ``_threads_queues``, so
                # the interpreter abandons it at shutdown instead of joining it.
                self._mcp_server_thread = threading.Thread(
                    target=self._run_mcp_server_blocking,
                    daemon=True,
                    name=f"mcp-channel-{self.name}",
                )
                self._mcp_server_thread.start()
            else:
                # Fallback to start() if available
                await self.mcp_server.start()

            # Start server task for handling connections
            self._server_task = asyncio.create_task(self._server_loop())

            self.status = ChannelStatus.RUNNING

            # Emit startup event
            await self.emit_event(
                ChannelEvent(
                    event_id=f"mcp_startup_{asyncio.get_event_loop().time()}",
                    channel_name=self.name,
                    channel_type=self.channel_type,
                    event_type="channel_started",
                    payload={
                        "host": self.config.host,
                        "port": self.config.port,
                        "tools_count": len(self._tool_registry),
                    },
                )
            )

            logger.info(
                f"MCP channel {self.name} started on {self.config.host}:{self.config.port}"
            )

        except Exception as e:
            self.status = ChannelStatus.ERROR
            logger.error(f"Failed to start MCP channel {self.name}: {e}")
            raise

    async def stop(self) -> None:
        """Stop the MCP channel server."""
        if self.status == ChannelStatus.STOPPED:
            return

        try:
            self.status = ChannelStatus.STOPPING

            # Emit shutdown event
            await self.emit_event(
                ChannelEvent(
                    event_id=f"mcp_shutdown_{asyncio.get_event_loop().time()}",
                    channel_name=self.name,
                    channel_type=self.channel_type,
                    event_type="channel_stopping",
                    payload={"active_clients": len(self._clients)},
                )
            )

            # Stop server task
            if self._server_task and not self._server_task.done():
                self._server_task.cancel()
                try:
                    await self._server_task
                except asyncio.CancelledError:
                    pass

            # Stop MCP server. This MUST precede joining the server thread --
            # the thread is parked inside the blocking ``run()`` loop and only
            # returns once the server itself is told to shut down.
            requested_server_shutdown = False
            if self.mcp_server and hasattr(self.mcp_server, "stop"):
                try:
                    result = self.mcp_server.stop()
                    if inspect.isawaitable(result):
                        await result
                    requested_server_shutdown = True
                except Exception as e:
                    logger.warning(f"Error stopping MCP server: {e}")

            # Reclaim the dedicated MCP server thread.
            #
            # NOTE: the previous implementation dispatched ``run()`` onto
            # asyncio's default executor and called ``future.cancel()`` here.
            # ``cancel()`` on an executor future whose work item has ALREADY
            # started returns ``False`` and does nothing -- so that call was a
            # silent no-op that left the server running and the pool worker
            # wedged. The join below is the real reclaim; when it times out we
            # say so at WARN rather than pretending the channel stopped.
            thread, self._mcp_server_thread = self._mcp_server_thread, None
            if thread is not None and thread.is_alive():
                if requested_server_shutdown:
                    thread.join(timeout=self._MCP_SERVER_JOIN_TIMEOUT)
                    if thread.is_alive():
                        logger.warning(
                            "MCP channel %s server thread %r did not exit "
                            "within %.1fs of mcp_server.stop(); it is a daemon "
                            "thread and will be abandoned at interpreter exit "
                            "rather than blocking shutdown.",
                            self.name,
                            thread.name,
                            self._MCP_SERVER_JOIN_TIMEOUT,
                        )
                else:
                    # No usable shutdown entry point, so nothing will ever
                    # unwind the serve loop -- joining would burn the timeout
                    # waiting for something that cannot happen. Say so instead.
                    logger.warning(
                        "MCP channel %s stopped, but %s exposes no usable "
                        "stop(); server thread %r stays parked in run() and "
                        "will be abandoned at interpreter exit. It is a daemon "
                        "thread, so it does not block shutdown.",
                        self.name,
                        type(self.mcp_server).__name__,
                        thread.name,
                    )

            await self._cleanup()

            self.close()

            self.status = ChannelStatus.STOPPED

            logger.info(f"MCP channel {self.name} stopped")

        except Exception as e:
            self.status = ChannelStatus.ERROR
            logger.error(f"Error stopping MCP channel {self.name}: {e}")
            raise

    async def handle_request(self, request: Dict[str, Any]) -> ChannelResponse:
        """Handle an MCP request.

        Args:
            request: MCP request data

        Returns:
            ChannelResponse with MCP execution results
        """
        try:
            method = request.get("method", "")
            params = request.get("params", {})
            request_id = request.get("id", "")

            # Emit request event
            await self.emit_event(
                ChannelEvent(
                    event_id=f"mcp_request_{asyncio.get_event_loop().time()}",
                    channel_name=self.name,
                    channel_type=self.channel_type,
                    event_type="mcp_request",
                    payload={
                        "method": method,
                        "params": params,
                        "request_id": request_id,
                    },
                )
            )

            # Handle different MCP methods
            if method == "tools/list":
                result = await self._handle_tools_list()
            elif method == "tools/call":
                result = await self._handle_tools_call(params)
            elif method == "resources/list":
                result = await self._handle_resources_list()
            elif method == "resources/read":
                result = await self._handle_resources_read(params)
            else:
                result = {
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }

            # Emit completion event
            await self.emit_event(
                ChannelEvent(
                    event_id=f"mcp_completion_{asyncio.get_event_loop().time()}",
                    channel_name=self.name,
                    channel_type=self.channel_type,
                    event_type="mcp_completed",
                    payload={
                        "method": method,
                        "request_id": request_id,
                        "success": "error" not in result,
                    },
                )
            )

            return ChannelResponse(
                success="error" not in result,
                data=result,
                metadata={
                    "channel": self.name,
                    "method": method,
                    "request_id": request_id,
                },
            )

        except Exception as e:
            logger.error(f"Error handling MCP request: {e}")

            # Emit error event
            await self.emit_event(
                ChannelEvent(
                    event_id=f"mcp_error_{asyncio.get_event_loop().time()}",
                    channel_name=self.name,
                    channel_type=self.channel_type,
                    event_type="mcp_error",
                    payload={"error": str(e), "request": request},
                )
            )

            return ChannelResponse(
                success=False, error=str(e), metadata={"channel": self.name}
            )

    async def _server_loop(self) -> None:
        """Main server loop for handling MCP connections."""
        while self.status == ChannelStatus.RUNNING:
            try:
                # This would handle MCP protocol connections
                # For now, we'll just wait and check for shutdown
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in MCP server loop: {e}")

    async def _handle_tools_list(self) -> Dict[str, Any]:
        """Handle MCP tools/list request."""
        tools = []

        for tool_name, registration in self._tool_registry.items():
            tool_def = {
                "name": tool_name,
                "description": registration.description,
                "inputSchema": {
                    "type": "object",
                    "properties": registration.parameters,
                },
            }
            tools.append(tool_def)

        return {"tools": tools}

    async def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP tools/call request."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in self._tool_registry:
            return {
                "error": {"code": -32602, "message": f"Tool not found: {tool_name}"}
            }

        registration = self._tool_registry[tool_name]

        try:
            # Execute tool handler
            if registration.handler:
                if asyncio.iscoroutinefunction(registration.handler):
                    result = await registration.handler(arguments)
                else:
                    result = registration.handler(arguments)
            elif registration.workflow_name:
                # Execute workflow
                workflow = self._workflow_registry.get(registration.workflow_name)
                if workflow and self.runtime is not None:
                    from kailash.workflow.input_envelope import (
                        bind_parameter_envelope,
                    )

                    # MCP tools/call arguments are the caller's workflow
                    # arguments -- the same role the `parameters` envelope
                    # fills on the HTTP, CLI and other MCP paths.
                    results, run_id = await self.runtime.execute_async(
                        workflow, parameters=bind_parameter_envelope(arguments)
                    )
                    result = {
                        "results": results,
                        "run_id": run_id,
                        "workflow": registration.workflow_name,
                    }
                else:
                    result = {
                        "error": f"Workflow not found: {registration.workflow_name}"
                    }
            else:
                result = {"error": "No handler or workflow configured for tool"}

            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {"error": {"code": -32603, "message": f"Tool execution failed: {e}"}}

    async def _handle_resources_list(self) -> Dict[str, Any]:
        """Handle MCP resources/list request."""
        resources = []

        # Add workflow resources
        for workflow_name in self._workflow_registry.keys():
            resource = {
                "uri": f"workflow://{workflow_name}",
                "name": f"Workflow: {workflow_name}",
                "description": f"Execute the {workflow_name} workflow",
                "mimeType": "application/json",
            }
            resources.append(resource)

        return {"resources": resources}

    async def _handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP resources/read request."""
        uri = params.get("uri", "")

        if uri.startswith("workflow://"):
            workflow_name = uri[11:]  # Remove "workflow://" prefix
            if workflow_name in self._workflow_registry:
                workflow = self._workflow_registry[workflow_name]
                # Return workflow information
                return {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps(
                                {
                                    "name": workflow_name,
                                    "description": f"Workflow {workflow_name} definition",
                                    "available": True,
                                },
                                indent=2,
                            ),
                        }
                    ]
                }

        return {"error": {"code": -32602, "message": f"Resource not found: {uri}"}}

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Optional[Callable] = None,
        workflow_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register an MCP tool.

        Args:
            name: Tool name
            description: Tool description
            parameters: Tool parameters schema
            handler: Optional handler function
            workflow_name: Optional workflow to execute
            metadata: Optional metadata
        """
        registration = MCPToolRegistration(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            workflow_name=workflow_name,
            metadata=metadata or {},
        )

        self._tool_registry[name] = registration
        logger.info(f"Registered MCP tool '{name}' with channel {self.name}")

    def register_workflow(self, name: str, workflow: Workflow) -> None:
        """Register a workflow with this MCP channel.

        Args:
            name: Workflow name
            workflow: Workflow instance
        """
        self._workflow_registry[name] = workflow

        # Auto-register as a tool
        self.register_tool(
            name=f"workflow_{name}",
            description=f"Execute the {name} workflow",
            parameters={
                "inputs": {
                    "type": "object",
                    "description": "Input parameters for the workflow",
                }
            },
            workflow_name=name,
        )

        logger.info(f"Registered workflow '{name}' with MCP channel {self.name}")

    async def _handle_list_workflows(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle list_workflows tool."""
        workflows = []

        for workflow_name in self._workflow_registry.keys():
            workflows.append(
                {
                    "name": workflow_name,
                    "available": True,
                    "tool_name": f"workflow_{workflow_name}",
                }
            )

        return {"workflows": workflows, "count": len(workflows)}

    async def _handle_execute_workflow(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle execute_workflow tool."""
        workflow_name = arguments.get("workflow_name", "")
        inputs = arguments.get("inputs", {})

        if workflow_name not in self._workflow_registry:
            return {"error": f"Workflow not found: {workflow_name}"}

        workflow = self._workflow_registry[workflow_name]

        if self.runtime is None:
            return {"success": False, "error": "Runtime not available"}

        try:
            from kailash.workflow.input_envelope import bind_parameter_envelope

            # Same binding as _handle_tools_call above and every other channel:
            # one registration, one input contract.
            #
            # `inputs` here is NOT the opt-OUT form WorkflowRequest draws
            # against `parameters`. Per the structural rule in
            # `kailash/workflow/input_envelope.py`: the opt-out exists only
            # where the caller was given a SECOND slot to express it.
            # `execute_workflow` exposes one arguments slot, so it binds --
            # otherwise a `parameters.get(...)` workflow would be broken here
            # with no way for the caller to ask for the binding.
            results, run_id = await self.runtime.execute_async(
                workflow, parameters=bind_parameter_envelope(inputs)
            )
            return {
                "success": True,
                "results": results,
                "run_id": run_id,
                "workflow_name": workflow_name,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "workflow_name": workflow_name}

    async def _handle_get_workflow_schema(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get_workflow_schema tool."""
        workflow_name = arguments.get("workflow_name", "")

        if workflow_name not in self._workflow_registry:
            return {"error": f"Workflow not found: {workflow_name}"}

        # This would extract schema from workflow
        # For now, return basic information
        return {
            "workflow_name": workflow_name,
            "schema": {
                "inputs": "object",
                "outputs": "object",
                "description": f"Schema for {workflow_name} workflow",
            },
        }

    async def _handle_channel_status(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle channel_status tool."""
        verbose = arguments.get("verbose", False)

        status_info = {
            "channel_name": self.name,
            "channel_type": self.channel_type.value,
            "status": self.status.value,
            "tools_count": len(self._tool_registry),
            "workflows_count": len(self._workflow_registry),
            "active_clients": len(self._clients),
        }

        if verbose:
            status_info.update(
                {
                    "tools": list(self._tool_registry.keys()),
                    "workflows": list(self._workflow_registry.keys()),
                    "host": self.config.host,
                    "port": self.config.port,
                    "config": {
                        "enable_sessions": self.config.enable_sessions,
                        "enable_auth": self.config.enable_auth,
                        "enable_event_routing": self.config.enable_event_routing,
                    },
                }
            )

        return status_info

    def close(self):
        """Release runtime reference."""
        if hasattr(self, "runtime") and self.runtime is not None:
            self.runtime.release()
            self.runtime = None

    def __del__(self, _warnings=warnings):
        if getattr(self, "runtime", None) is not None:
            _warnings.warn(
                f"Unclosed {self.__class__.__name__}. Call close() or stop() explicitly.",
                ResourceWarning,
                source=self,
            )
            try:
                self.close()
            except Exception:
                pass

    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        base_health = await super().health_check()

        # Add MCP-specific health checks
        mcp_checks = {
            "mcp_server_running": self.mcp_server is not None,
            "tools_registered": len(self._tool_registry) > 0,
            "workflows_available": len(self._workflow_registry) >= 0,
            "runtime_ready": self.runtime is not None,
        }

        all_healthy = base_health["healthy"] and all(mcp_checks.values())

        return {
            **base_health,
            "healthy": all_healthy,
            "checks": {**base_health["checks"], **mcp_checks},
            "tools": len(self._tool_registry),
            "workflows": len(self._workflow_registry),
            "clients": len(self._clients),
        }

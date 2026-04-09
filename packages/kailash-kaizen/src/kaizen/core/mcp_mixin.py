"""
MCP integration mixin for BaseAgent.

Extracts all MCP (Model Context Protocol) tool discovery, execution,
server exposure, and resource/prompt management from BaseAgent into
a standalone mixin class.

Uses duck typing -- the host class must provide:
- self._mcp_servers: list of server configs
- self._mcp_client: MCPClient instance or None
- self._discovered_mcp_tools: dict
- self._discovered_mcp_resources: dict
- self._discovered_mcp_prompts: dict
- self.agent_id: str
- self.shared_memory: optional
- self.write_to_memory(): method
- self.execution_context: ExecutionContext
- self.permission_policy: PermissionPolicy
- self.approval_manager: optional ToolApprovalManager

Copyright 2025 Terrene Foundation (Singapore CLG)
Licensed under Apache-2.0
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from kaizen.tools.types import DangerLevel, ToolCategory, ToolDefinition, ToolParameter

logger = logging.getLogger(__name__)


class MCPMixin:
    """Mixin providing MCP integration for BaseAgent.

    All methods previously inlined in BaseAgent for MCP tool discovery,
    execution, resource/prompt management, and server exposure are now
    defined here.
    """

    # =========================================================================
    # TOOL CALLING INTEGRATION - MCP Only
    # =========================================================================

    async def discover_tools(
        self,
        category: Optional[ToolCategory] = None,
        safe_only: bool = False,
        keyword: Optional[str] = None,
    ) -> List[ToolDefinition]:
        """Discover available MCP tools with optional filtering.

        Args:
            category: Optional filter by tool category
            safe_only: If True, only return SAFE tools
            keyword: Optional keyword to search in tool names/descriptions

        Returns:
            List of matching ToolDefinition objects

        Raises:
            RuntimeError: If no MCP servers configured
        """
        tools = []

        if self._mcp_servers is None:
            raise RuntimeError(
                "No MCP servers configured. "
                "Pass mcp_servers parameter to BaseAgent.__init__() "
                "to enable tool discovery."
            )

        mcp_tools_raw = await self.discover_mcp_tools()

        for mcp_tool in mcp_tools_raw:
            params = []
            if "parameters" in mcp_tool and isinstance(mcp_tool["parameters"], dict):
                for param_name, param_schema in mcp_tool["parameters"].items():
                    params.append(
                        ToolParameter(
                            name=param_name,
                            type=param_schema.get("type", "string"),
                            description=param_schema.get("description", ""),
                            required=param_schema.get("required", False),
                        )
                    )

            tool_def = ToolDefinition(
                name=mcp_tool["name"],
                description=mcp_tool.get("description", ""),
                category=ToolCategory.SYSTEM,
                danger_level=DangerLevel.SAFE,
                parameters=params,
                returns={},
                executor=None,
            )

            if category is not None and tool_def.category != category:
                continue
            if safe_only and tool_def.danger_level != DangerLevel.SAFE:
                continue
            if keyword is not None:
                keyword_lower = keyword.lower()
                if not (
                    keyword_lower in tool_def.name.lower()
                    or keyword_lower in tool_def.description.lower()
                ):
                    continue

            tools.append(tool_def)

        return tools

    # =========================================================================
    # MCP INTEGRATION - Tool Discovery and Execution
    # =========================================================================

    def has_mcp_support(self) -> bool:
        """Check if agent has MCP integration configured."""
        return self._mcp_servers is not None

    async def discover_mcp_tools(
        self, server_name: Optional[str] = None, force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """Discover MCP tools from configured servers with naming convention.

        Discovers tools from MCP servers and applies naming convention:
        mcp__<serverName>__<toolName>

        Args:
            server_name: Optional filter by server name (None = all servers)
            force_refresh: Bypass cache and rediscover tools

        Returns:
            List of tool definitions with naming convention applied

        Raises:
            RuntimeError: If MCP not configured
        """
        if self._mcp_servers is None:
            raise RuntimeError(
                "MCP not configured. Pass mcp_servers parameter to BaseAgent.__init__()"
            )

        servers = self._mcp_servers
        if server_name is not None:
            filtered_servers = []
            for s in servers:
                if isinstance(s, str):
                    if s == server_name:
                        filtered_servers.append(s)
                elif isinstance(s, dict):
                    if s.get("name") == server_name:
                        filtered_servers.append(s)
            servers = filtered_servers

        all_tools = []
        for server_config in servers:
            if isinstance(server_config, str):
                server_key = server_config
            elif isinstance(server_config, dict):
                server_key = server_config.get("name", "unknown")
            else:
                logger.warning(
                    f"Skipping invalid server config: {server_config}. "
                    f"Expected string or dict, got {type(server_config)}"
                )
                continue

            if not force_refresh and server_key in self._discovered_mcp_tools:
                all_tools.extend(self._discovered_mcp_tools[server_key])
                continue

            if isinstance(server_config, str):
                if server_config == "kaizen_builtin":
                    resolved_config = {
                        "name": "kaizen_builtin",
                        "command": "python",
                        "args": ["-m", "kaizen.mcp.builtin_server"],
                        "transport": "stdio",
                        "description": "Kaizen builtin tools (file, HTTP, bash, web)",
                    }
                else:
                    logger.warning(
                        f"Unknown auto-connect server: {server_config}. "
                        f"Only 'kaizen_builtin' is currently supported."
                    )
                    continue
            else:
                resolved_config = server_config

            tools = await self._mcp_client.discover_tools(
                resolved_config, force_refresh=force_refresh
            )

            renamed_tools = []
            for tool in tools:
                renamed_tool = tool.copy()
                renamed_tool["name"] = f"mcp__{server_key}__{tool['name']}"
                renamed_tools.append(renamed_tool)

            self._discovered_mcp_tools[server_key] = renamed_tools
            all_tools.extend(renamed_tools)

        return all_tools

    def _convert_mcp_result_to_dict(self, result) -> Dict[str, Any]:
        """Convert MCP CallToolResult to dict format expected by tests.

        Args:
            result: Dict from MCPClient.call_tool()

        Returns:
            Dict with success, output, stdout, content, error, and structured_content fields
        """
        if not isinstance(result, dict):
            raise TypeError(
                f"Expected dict from MCPClient.call_tool(), got {type(result)}"
            )

        call_tool_result = result.get("result")
        structured_content = {}

        if call_tool_result and hasattr(call_tool_result, "structuredContent"):
            structured_content = call_tool_result.structuredContent or {}

        stdout = structured_content.get("stdout", "")
        stderr = structured_content.get("stderr", "")
        exit_code = structured_content.get("exit_code", 0)

        data = None

        if stdout:
            output = stdout
            content = stdout
        else:
            output = json.dumps(structured_content) if structured_content else "{}"
            content = output

            if "body" in structured_content and isinstance(
                structured_content.get("body"), str
            ):
                try:
                    data = json.loads(structured_content["body"])
                except json.JSONDecodeError:
                    pass

        result_dict = {
            "success": result.get("success", False)
            and not result.get("isError", False),
            "output": output,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "content": content,
            "error": (
                stderr
                if stderr
                else ("" if result.get("success", False) else "Unknown error")
            ),
            "isError": result.get("isError", False),
            "structured_content": structured_content,
        }

        if data is not None:
            result_dict["data"] = data

        for key, value in structured_content.items():
            if key not in result_dict:
                result_dict[key] = value

        return result_dict

    async def execute_tool(
        self, tool_name: str, params: Dict[str, Any], timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Execute tool via MCP integration.

        If tool_name doesn't have mcp__ prefix, assumes kaizen_builtin server.

        Args:
            tool_name: Tool name (with or without mcp__ prefix)
            params: Tool parameters
            timeout: Optional execution timeout

        Returns:
            Tool execution result
        """
        if not tool_name.startswith("mcp__"):
            tool_name = f"mcp__kaizen_builtin__{tool_name}"
        return await self.execute_mcp_tool(tool_name, params, timeout)

    async def execute_mcp_tool(
        self, tool_name: str, params: Dict[str, Any], timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Execute MCP tool with server routing and approval workflow.

        Args:
            tool_name: Tool name with naming convention (mcp__server__tool)
            params: Tool parameters
            timeout: Optional execution timeout

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool_name format invalid or server not found
            PermissionError: If approval required but denied
        """
        if not tool_name.startswith("mcp__") or tool_name.count("__") < 2:
            raise ValueError(
                f"Invalid MCP tool name format: {tool_name}. "
                "Expected: mcp__<serverName>__<toolName>"
            )

        parts = tool_name.split("__")
        server_name = parts[1]
        original_tool_name = "__".join(parts[2:])

        server_config = None
        for config in self._mcp_servers:
            if config.get("name") == server_name:
                server_config = config
                break

        if server_config is None:
            raise ValueError(
                f"MCP server '{server_name}' not found in configured servers"
            )

        if server_name == "kaizen_builtin":
            from kaizen.mcp.builtin_server.danger_levels import (
                get_tool_danger_level,
                is_tool_safe,
            )
            from kaizen.tools.types import DangerLevel

            try:
                danger_level = get_tool_danger_level(original_tool_name)
            except ValueError:
                danger_level = DangerLevel.MEDIUM

            if not is_tool_safe(original_tool_name):
                permission_decision, denial_reason = (
                    self.permission_policy.check_permission(
                        tool_name=original_tool_name,
                        tool_input=params,
                        estimated_cost=0.0,
                    )
                )

                if permission_decision is True:
                    pass
                elif permission_decision is False:
                    raise PermissionError(
                        f"Tool '{original_tool_name}' denied by permission policy: {denial_reason}"
                    )
                else:
                    if self.approval_manager is None:
                        raise PermissionError(
                            f"Tool '{original_tool_name}' (danger={danger_level.value}) "
                            "requires approval but control_protocol not configured. "
                            "Pass control_protocol to BaseAgent.__init__() to enable approval workflow."
                        )

                    from kaizen.core.autonomy.permissions.context import (
                        ExecutionContext,
                    )

                    context = (
                        getattr(self, "execution_context", None) or ExecutionContext()
                    )
                    approved = await self.approval_manager.request_approval(
                        tool_name=original_tool_name,
                        tool_input=params,
                        context=context,
                        timeout=timeout or 60.0,
                    )

                    if not approved:
                        raise PermissionError(
                            f"User denied approval for tool '{original_tool_name}' "
                            f"(danger={danger_level.value})"
                        )

        result = await self._mcp_client.call_tool(
            server_config, original_tool_name, params, timeout=timeout
        )
        return self._convert_mcp_result_to_dict(result)

    async def discover_mcp_resources(
        self, server_name: str, force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """Discover MCP resources from a specific server.

        Args:
            server_name: Server name to query
            force_refresh: Bypass cache and rediscover

        Returns:
            List of resource definitions
        """
        if self._mcp_servers is None:
            raise RuntimeError("MCP not configured")

        server_config = None
        for config in self._mcp_servers:
            if config.get("name") == server_name:
                server_config = config
                break

        if server_config is None:
            raise ValueError(f"MCP server '{server_name}' not found")

        if not force_refresh and server_name in self._discovered_mcp_resources:
            return self._discovered_mcp_resources[server_name]

        resources = await self._with_mcp_session(
            server_config, self._mcp_client.list_resources
        )
        self._discovered_mcp_resources[server_name] = resources
        return resources

    async def read_mcp_resource(self, server_name: str, uri: str) -> Any:
        """Read MCP resource content from a specific server.

        Args:
            server_name: Server name
            uri: Resource URI

        Returns:
            Resource content
        """
        if self._mcp_servers is None:
            raise RuntimeError("MCP not configured")

        server_config = None
        for config in self._mcp_servers:
            if config.get("name") == server_name:
                server_config = config
                break

        if server_config is None:
            raise ValueError(f"MCP server '{server_name}' not found")

        return await self._with_mcp_session(
            server_config, self._mcp_client.read_resource, uri
        )

    async def discover_mcp_prompts(
        self, server_name: str, force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """Discover MCP prompts from a specific server.

        Args:
            server_name: Server name to query
            force_refresh: Bypass cache and rediscover

        Returns:
            List of prompt definitions
        """
        if self._mcp_servers is None:
            raise RuntimeError("MCP not configured")

        server_config = None
        for config in self._mcp_servers:
            if config.get("name") == server_name:
                server_config = config
                break

        if server_config is None:
            raise ValueError(f"MCP server '{server_name}' not found")

        if not force_refresh and server_name in self._discovered_mcp_prompts:
            return self._discovered_mcp_prompts[server_name]

        prompts = await self._with_mcp_session(
            server_config, self._mcp_client.list_prompts
        )
        self._discovered_mcp_prompts[server_name] = prompts
        return prompts

    async def get_mcp_prompt(
        self, server_name: str, prompt_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get MCP prompt with arguments from a specific server.

        Args:
            server_name: Server name
            prompt_name: Prompt name
            arguments: Prompt arguments

        Returns:
            Prompt with messages
        """
        if self._mcp_servers is None:
            raise RuntimeError("MCP not configured")

        server_config = None
        for config in self._mcp_servers:
            if config.get("name") == server_name:
                server_config = config
                break

        if server_config is None:
            raise ValueError(f"MCP server '{server_name}' not found")

        return await self._with_mcp_session(
            server_config, self._mcp_client.get_prompt, prompt_name, arguments
        )

    async def _with_mcp_session(self, server_config: Dict[str, Any], method, *args):
        """Create a temporary MCP session and invoke a session-based method.

        Args:
            server_config: Server configuration dict.
            method: Async callable accepting (session, *args).
            *args: Extra positional arguments forwarded to method.

        Returns:
            Whatever method returns.
        """
        import asyncio
        import os
        from contextlib import AsyncExitStack

        transport_type = server_config.get("transport", "stdio")

        async with AsyncExitStack() as stack:
            if transport_type == "stdio":
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client

                command = server_config.get("command", "python")
                cmd_args = server_config.get("args", [])
                env = server_config.get("env", {})
                server_env = os.environ.copy()
                server_env.update(env)
                server_params = StdioServerParameters(
                    command=command, args=cmd_args, env=server_env
                )
                stdio = await stack.enter_async_context(stdio_client(server_params))
                session = await stack.enter_async_context(
                    ClientSession(stdio[0], stdio[1])
                )

            elif transport_type == "sse":
                from mcp import ClientSession
                from mcp.client.sse import sse_client

                url = server_config["url"]
                headers = self._mcp_client._get_auth_headers(server_config)
                sse = await stack.enter_async_context(
                    sse_client(url=url, headers=headers)
                )
                session = await stack.enter_async_context(ClientSession(sse[0], sse[1]))

            elif transport_type == "http":
                from mcp import ClientSession
                from mcp.client.streamable_http import streamable_http_client

                url = server_config["url"]
                headers = self._mcp_client._get_auth_headers(server_config)
                http = await stack.enter_async_context(
                    streamable_http_client(url=url, headers=headers)
                )
                session = await stack.enter_async_context(
                    ClientSession(http[0], http[1])
                )

            elif transport_type == "websocket":
                from mcp import ClientSession
                from mcp.client.websocket import websocket_client

                url = server_config.get("url", server_config.get("uri"))
                if not url:
                    raise ValueError("WebSocket server config must include 'url'")
                ws = await stack.enter_async_context(websocket_client(url=url))
                session = await stack.enter_async_context(ClientSession(ws[0], ws[1]))

            else:
                raise ValueError(f"Unsupported transport type: {transport_type}")

            await session.initialize()
            return await method(session, *args)

    # =========================================================================
    # MCP Setup / Expose
    # =========================================================================

    async def setup_mcp_client(
        self,
        servers: List[Dict[str, Any]],
        retry_strategy: str = "circuit_breaker",
        enable_metrics: bool = True,
        **client_kwargs,
    ):
        """Setup MCP client for consuming external MCP tools.

        Args:
            servers: List of MCP server configurations.
            retry_strategy: Retry strategy name.
            enable_metrics: Enable metrics collection.
            **client_kwargs: Additional MCPClient arguments.

        Returns:
            MCPClient: Configured MCPClient instance.
        """
        try:
            from kailash_mcp.client import MCPClient
        except ImportError:
            raise ImportError(
                "kailash_mcp not available. Install with: pip install kailash-mcp"
            )

        self._mcp_client = MCPClient(
            retry_strategy=retry_strategy,
            enable_metrics=enable_metrics,
            **client_kwargs,
        )

        self._available_mcp_tools = {}

        for server_config in servers:
            if "name" not in server_config or "transport" not in server_config:
                raise ValueError(
                    "Server config must include 'name' and 'transport' fields"
                )

            tools = await self._mcp_client.discover_tools(
                server_config, force_refresh=True
            )

            for tool in tools:
                tool_id = f"{server_config['name']}:{tool['name']}"
                self._available_mcp_tools[tool_id] = {
                    **tool,
                    "server_config": server_config,
                }

            logger.info(
                f"Discovered {len(tools)} tools from MCP server: {server_config['name']}"
            )

        logger.info(
            f"MCP client setup complete. {len(self._available_mcp_tools)} tools available."
        )

        return self._mcp_client

    async def call_mcp_tool(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        timeout: float = 30.0,
        store_in_memory: bool = True,
    ) -> Dict[str, Any]:
        """Call MCP tool by ID using real JSON-RPC protocol.

        Args:
            tool_id: Tool ID (format: "server_name:tool_name")
            arguments: Tool arguments
            timeout: Timeout in seconds
            store_in_memory: Store tool call in shared memory

        Returns:
            Dict with tool result.
        """
        if not hasattr(self, "_mcp_client") or self._mcp_client is None:
            raise RuntimeError("MCP client not setup. Call setup_mcp_client() first.")

        if tool_id not in self._available_mcp_tools:
            available_tools = list(self._available_mcp_tools.keys())
            raise ValueError(
                f"Tool {tool_id} not found. Available tools: {available_tools}"
            )

        tool_info = self._available_mcp_tools[tool_id]
        server_config = tool_info["server_config"]
        tool_name = tool_info["name"]

        result = await self._mcp_client.call_tool(
            server_config, tool_name, arguments, timeout=timeout
        )

        if store_in_memory and hasattr(self, "shared_memory") and self.shared_memory:
            self.write_to_memory(
                content={
                    "tool_id": tool_id,
                    "server": server_config["name"],
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "result": result,
                    "agent_id": self.agent_id,
                },
                tags=["mcp_tool_call", server_config["name"], tool_name],
                importance=0.8,
            )

        return self._convert_mcp_result_to_dict(result)

    def expose_as_mcp_server(
        self,
        server_name: str,
        tools: Optional[List[str]] = None,
        auth_provider: Optional[Any] = None,
        enable_auto_discovery: bool = True,
        **server_kwargs,
    ):
        """Expose agent as MCP server with real protocol support.

        Args:
            server_name: Server name for MCP registration.
            tools: List of agent methods to expose.
            auth_provider: Optional auth provider.
            enable_auto_discovery: Enable network discovery.
            **server_kwargs: Additional MCPServer arguments.

        Returns:
            MCPServer: Configured server (call .run() to start).
        """
        try:
            from kailash_mcp.server import MCPServer
            from kailash_mcp.discovery import enable_auto_discovery as enable_discovery
        except ImportError:
            raise ImportError(
                "kailash_mcp not available. Install with: pip install kailash-mcp"
            )

        server = MCPServer(
            name=server_name,
            auth_provider=auth_provider,
            enable_metrics=True,
            enable_http_transport=True,
            **server_kwargs,
        )

        if tools is None:
            tools = [
                m
                for m in dir(self)
                if not m.startswith("_") and callable(getattr(self, m))
            ]

        for tool_name in tools:
            if not hasattr(self, tool_name):
                logger.warning(f"Tool {tool_name} not found on agent, skipping")
                continue

            method = getattr(self, tool_name)

            async def tool_wrapper(_bound_method=method, **kwargs):
                """Auto-generated MCP tool from agent method."""
                result = _bound_method(**kwargs)
                if hasattr(result, "__await__"):
                    result = await result
                return result

            tool_wrapper.__name__ = tool_name
            server.tool()(tool_wrapper)

        self._mcp_server = server

        if enable_auto_discovery:
            registrar = enable_discovery(server, enable_network_discovery=True)
            self._mcp_registrar = registrar
            logger.info(f"MCP server '{server_name}' ready with auto-discovery enabled")
        else:
            self._mcp_registrar = None
            logger.info(f"MCP server '{server_name}' ready")

        return server

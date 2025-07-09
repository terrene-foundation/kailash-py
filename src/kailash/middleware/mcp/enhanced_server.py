"""
Enhanced MCP Server for Kailash Middleware

Built entirely with Kailash SDK components - consolidates existing MCP
implementations with middleware-specific features for enterprise use.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from kailash.nodes.ai import LLMAgentNode

# Import Kailash SDK components
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import JSONReaderNode
from kailash.nodes.logic import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Import existing Kailash MCP components
try:
    from kailash.mcp_server import MCPServer
    from kailash.mcp_server.utils import CacheManager, ConfigManager, MetricsCollector

    _KAILASH_MCP_AVAILABLE = True
except ImportError:
    _KAILASH_MCP_AVAILABLE = False

# Import middleware components
from ..communication.events import EventStream, EventType
from ..core.agent_ui import AgentUIMiddleware

logger = logging.getLogger(__name__)


class MCPServerConfig:
    """Configuration for Middleware MCP Server using Kailash patterns."""

    def __init__(self):
        self.name = "kailash-middleware-mcp"
        self.version = "1.0.0"
        self.description = "Enhanced MCP server built with Kailash SDK"

        # Kailash-specific settings
        self.enable_caching = True
        self.cache_ttl = 300
        self.enable_metrics = True
        self.enable_events = True

        # Server settings
        self.max_tools = 100
        self.max_resources = 50
        self.enable_streaming = True


class MCPToolNode(Node):
    """Kailash node representing an MCP tool."""

    def __init__(
        self,
        name: str,
        tool_name: str,
        description: str = "",
        parameters_schema: Dict[str, Any] = None,
    ):
        super().__init__(name)
        self.tool_name = tool_name
        self.description = description
        self.parameters_schema = parameters_schema or {}
        self.execution_count = 0
        self.last_executed = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Generate parameters from tool schema."""
        params = {}

        # Always include tool input parameter
        params["tool_input"] = NodeParameter(
            name="tool_input",
            type=dict,
            required=True,
            description="Input data for the MCP tool",
        )

        # Add schema-specific parameters
        for param_name, param_info in self.parameters_schema.items():
            params[param_name] = NodeParameter(
                name=param_name,
                type=param_info.get("type", str),
                required=param_info.get("required", False),
                description=param_info.get("description", f"Parameter {param_name}"),
            )

        return params

    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Process MCP tool execution."""
        self.execution_count += 1
        self.last_executed = datetime.now(timezone.utc)

        # This would be overridden by specific tool implementations
        return {
            "tool_result": f"Executed MCP tool {self.tool_name}",
            "execution_count": self.execution_count,
            "executed_at": self.last_executed.isoformat(),
        }


class MCPResourceNode(Node):
    """Kailash node representing an MCP resource."""

    def __init__(
        self,
        name: str,
        resource_uri: str,
        resource_type: str = "text",
        description: str = "",
    ):
        super().__init__(name)
        self.resource_uri = resource_uri
        self.resource_type = resource_type
        self.description = description
        self.access_count = 0

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "resource_uri": NodeParameter(
                name="resource_uri",
                type=str,
                required=False,
                default=self.resource_uri,
                description="URI of the resource to access",
            )
        }

    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Process MCP resource access."""
        self.access_count += 1

        # This would be overridden by specific resource implementations
        return {
            "resource_content": f"Content from {self.resource_uri}",
            "resource_type": self.resource_type,
            "access_count": self.access_count,
        }


class MiddlewareMCPServer:
    """
    Enhanced MCP Server built with Kailash SDK components.

    Integrates with the middleware layer for real-time events,
    session management, and AI agent communication.
    """

    def __init__(
        self,
        config: MCPServerConfig = None,
        event_stream: EventStream = None,
        agent_ui: AgentUIMiddleware = None,
    ):
        self.config = config or MCPServerConfig()
        self.event_stream = event_stream
        self.agent_ui = agent_ui

        # Kailash components
        self.runtime = LocalRuntime()
        self.workflows: Dict[str, WorkflowBuilder] = {}

        # MCP registry using Kailash patterns
        self.tools: Dict[str, MCPToolNode] = {}
        self.resources: Dict[str, MCPResourceNode] = {}
        self.prompts: Dict[str, Dict[str, Any]] = {}

        # State management
        self.server_id = str(uuid.uuid4())
        self.started_at = None
        self.client_connections: Dict[str, Dict[str, Any]] = {}

        # Use existing Kailash MCP server if available
        self.base_server = None
        if _KAILASH_MCP_AVAILABLE:
            try:
                self.base_server = MCPServer(self.config.name)
            except Exception as e:
                logger.warning(f"Could not initialize base MCP server: {e}")

        # Create MCP management workflows
        self._create_management_workflows()

    def _create_management_workflows(self):
        """Create Kailash workflows for MCP operations."""

        # Tool Registration Workflow
        self.tool_register_workflow = WorkflowBuilder()

        # Use proper WorkflowBuilder syntax with string class names
        self.tool_register_workflow.add_node(
            "PythonCodeNode",
            "validate_tool",
            {
                "code": """
# Validate tool registration using Kailash patterns
tool_data = input_data.get('tool_data', {})

required_fields = ['name', 'description']
missing_fields = [f for f in required_fields if not tool_data.get(f)]

if missing_fields:
    result = {
        'valid': False,
        'error': f'Missing required fields: {missing_fields}',
        'tool_data': tool_data
    }
else:
    result = {
        'valid': True,
        'tool_data': tool_data,
        'validation_passed': True
    }
"""
            },
        )

        self.tool_register_workflow.add_node(
            "PythonCodeNode",
            "register_tool",
            {
                "code": """
# Register tool using Kailash patterns
validation_result = input_data.get('validation_result', {})

if not validation_result.get('valid'):
    result = {
        'success': False,
        'error': validation_result.get('error', 'Validation failed'),
        'tool_registered': False
    }
else:
    tool_data = validation_result.get('tool_data', {})
    result = {
        'success': True,
        'tool_name': tool_data.get('name'),
        'tool_registered': True,
        'registration_time': datetime.now().isoformat()
    }
"""
            },
        )

        self.tool_register_workflow.add_connection(
            "validate_tool", "result", "register_tool", "validation_result"
        )

        # Tool Execution Workflow
        self.tool_execute_workflow = WorkflowBuilder()

        self.tool_execute_workflow.add_node(
            "PythonCodeNode",
            "execute_tool",
            {
                "code": """
# Execute MCP tool using Kailash patterns
tool_name = input_data.get('tool_name')
tool_args = input_data.get('arguments', {})

# Simulate tool execution
execution_result = {
    'tool_name': tool_name,
    'arguments': tool_args,
    'result': f'Executed {tool_name} with args: {tool_args}',
    'execution_time': datetime.now().isoformat(),
    'success': True
}

result = {'execution_result': execution_result}
"""
            },
        )

    async def register_tool(
        self,
        name: str,
        description: str,
        handler: Callable = None,
        parameters_schema: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Register MCP tool using Kailash workflow."""

        # Use Kailash workflow for tool registration
        tool_data = {
            "name": name,
            "description": description,
            "parameters_schema": parameters_schema or {},
        }

        workflow = self.tool_register_workflow.build()
        results, _ = self.runtime.execute(workflow, parameters={"tool_data": tool_data})

        registration_result = results.get("register_tool", {})

        if registration_result.get("success"):
            # Create Kailash tool node
            tool_node = MCPToolNode(
                name=f"mcp_tool_{name}",
                tool_name=name,
                description=description,
                parameters_schema=parameters_schema,
            )

            # Override process method if handler provided
            if handler:
                original_process = tool_node.process

                def custom_process(inputs):
                    try:
                        # Call the custom handler
                        result = handler(inputs.get("tool_input", {}))
                        return {"tool_result": result}
                    except Exception as e:
                        return {"tool_result": None, "error": str(e)}

                tool_node.process = custom_process

            self.tools[name] = tool_node

            # Emit middleware event
            if self.event_stream:
                await self._emit_mcp_event(
                    "tool_registered", {"tool_name": name, "description": description}
                )

            logger.info(f"Registered MCP tool: {name}")

        return registration_result

    async def register_resource(
        self,
        uri: str,
        resource_type: str = "text",
        description: str = "",
        handler: Callable = None,
    ) -> Dict[str, Any]:
        """Register MCP resource using Kailash patterns."""

        resource_node = MCPResourceNode(
            name=f"mcp_resource_{uri.replace('/', '_')}",
            resource_uri=uri,
            resource_type=resource_type,
            description=description,
        )

        # Override process method if handler provided
        if handler:

            def custom_process(inputs):
                try:
                    result = handler(inputs.get("resource_uri", uri))
                    return {"resource_content": result}
                except Exception as e:
                    return {"resource_content": None, "error": str(e)}

            resource_node.process = custom_process

        self.resources[uri] = resource_node

        # Emit middleware event
        if self.event_stream:
            await self._emit_mcp_event(
                "resource_registered",
                {"resource_uri": uri, "resource_type": resource_type},
            )

        logger.info(f"Registered MCP resource: {uri}")
        return {"success": True, "resource_uri": uri}

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], session_id: str = None
    ) -> Dict[str, Any]:
        """Execute MCP tool using Kailash workflow."""

        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Tool {tool_name} not found",
                "available_tools": list(self.tools.keys()),
            }

        # Execute using Kailash tool node
        tool_node = self.tools[tool_name]

        try:
            result = tool_node.execute(tool_input=arguments)

            # Emit middleware event
            if self.event_stream:
                await self._emit_mcp_event(
                    "tool_executed",
                    {
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "session_id": session_id,
                        "success": True,
                    },
                )

            return {
                "success": True,
                "tool_name": tool_name,
                "result": result,
                "execution_count": tool_node.execution_count,
            }

        except Exception as e:
            # Emit error event
            if self.event_stream:
                await self._emit_mcp_event(
                    "tool_execution_failed",
                    {"tool_name": tool_name, "error": str(e), "session_id": session_id},
                )

            return {"success": False, "error": str(e), "tool_name": tool_name}

    async def get_resource(self, uri: str, session_id: str = None) -> Dict[str, Any]:
        """Get MCP resource using Kailash patterns."""

        if uri not in self.resources:
            return {
                "success": False,
                "error": f"Resource {uri} not found",
                "available_resources": list(self.resources.keys()),
            }

        resource_node = self.resources[uri]

        try:
            result = resource_node.execute({"resource_uri": uri})

            # Emit middleware event
            if self.event_stream:
                await self._emit_mcp_event(
                    "resource_accessed",
                    {"resource_uri": uri, "session_id": session_id, "success": True},
                )

            return {
                "success": True,
                "resource_uri": uri,
                "content": result,
                "access_count": resource_node.access_count,
            }

        except Exception as e:
            return {"success": False, "error": str(e), "resource_uri": uri}

    async def list_capabilities(self) -> Dict[str, Any]:
        """List MCP server capabilities using Kailash patterns."""

        return {
            "server_info": {
                "name": self.config.name,
                "version": self.config.version,
                "description": self.config.description,
                "server_id": self.server_id,
                "implementation": "Kailash SDK Middleware",
            },
            "tools": {
                name: {
                    "description": tool.description,
                    "parameters_schema": tool.parameters_schema,
                    "execution_count": tool.execution_count,
                    "last_executed": (
                        tool.last_executed.isoformat() if tool.last_executed else None
                    ),
                }
                for name, tool in self.tools.items()
            },
            "resources": {
                uri: {
                    "resource_type": resource.resource_type,
                    "description": resource.description,
                    "access_count": resource.access_count,
                }
                for uri, resource in self.resources.items()
            },
            "features": {
                "caching": self.config.enable_caching,
                "metrics": self.config.enable_metrics,
                "events": self.config.enable_events,
                "streaming": self.config.enable_streaming,
                "kailash_integration": True,
            },
        }

    async def start(self):
        """Start MCP server with Kailash integration."""
        self.started_at = datetime.now(timezone.utc)

        # Start base server if available
        if self.base_server:
            # This would start the actual MCP protocol server
            pass

        # Emit startup event
        if self.event_stream:
            await self._emit_mcp_event(
                "server_started",
                {"server_id": self.server_id, "name": self.config.name},
            )

        logger.info(f"Started Kailash MCP Server: {self.config.name}")

    async def stop(self):
        """Stop MCP server."""
        # Emit shutdown event
        if self.event_stream:
            await self._emit_mcp_event(
                "server_stopped",
                {
                    "server_id": self.server_id,
                    "uptime_seconds": (
                        (datetime.now(timezone.utc) - self.started_at).total_seconds()
                        if self.started_at
                        else 0
                    ),
                },
            )

        logger.info(f"Stopped Kailash MCP Server: {self.config.name}")

    async def _emit_mcp_event(self, event_type: str, data: Dict[str, Any]):
        """Emit MCP event to middleware event stream."""

        from ..events import WorkflowEvent

        event = WorkflowEvent(
            type=EventType.SYSTEM_STATUS,
            workflow_id="mcp_server",
            data={
                "mcp_event_type": event_type,
                "server_id": self.server_id,
                "server_name": self.config.name,
                **data,
            },
        )

        await self.event_stream.emit(event)

    def get_stats(self) -> Dict[str, Any]:
        """Get MCP server statistics."""
        uptime = (
            (datetime.now(timezone.utc) - self.started_at).total_seconds()
            if self.started_at
            else 0
        )

        return {
            "server_info": {
                "server_id": self.server_id,
                "name": self.config.name,
                "uptime_seconds": uptime,
                "started_at": self.started_at.isoformat() if self.started_at else None,
            },
            "tools": {
                "total_tools": len(self.tools),
                "total_executions": sum(
                    tool.execution_count for tool in self.tools.values()
                ),
            },
            "resources": {
                "total_resources": len(self.resources),
                "total_accesses": sum(
                    res.access_count for res in self.resources.values()
                ),
            },
            "implementation": "Kailash SDK Middleware MCP Server",
        }

"""MCP (Model Context Protocol) integration for Kailash workflows.

This module provides integration between MCP servers and Kailash workflows,
allowing workflows to access MCP tools and resources.

Design Philosophy:
    MCP servers provide tools and context that can be used by workflows.
    This integration allows workflows to discover and use MCP tools dynamically,
    bridging the gap between workflow automation and AI-powered tools.

Example:
    Basic MCP integration:

    >>> from kailash.api.mcp_integration import MCPIntegration
    >>> # from kailash.workflow import Workflow  # doctest: +SKIP
    >>> # Create MCP integration
    >>> mcp = MCPIntegration("tools_server")
    >>> # Add tools
    >>> # mcp.add_tool("search", search_function)  # doctest: +SKIP
    >>> # mcp.add_tool("calculate", calculator_function)  # doctest: +SKIP
    >>> # Use in workflow
    >>> # workflow = Workflow("mcp_workflow")  # doctest: +SKIP
    >>> # workflow.register_mcp_server(mcp)  # doctest: +SKIP
    >>> # Nodes can now access MCP tools
    >>> # node = MCPToolNode(tool_name="search")  # doctest: +SKIP
    >>> # workflow.add_node("search_data", node)  # doctest: +SKIP
"""

import ast
import asyncio
import logging
import operator
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from ..nodes.base_async import AsyncNode

logger = logging.getLogger(__name__)


# Safe math operations for the calculate tool — AST node whitelist approach
# prevents arbitrary code execution via eval()
_SAFE_MATH_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _safe_math_eval(expr: str) -> float:
    """Safely evaluate a mathematical expression using AST parsing.

    Only allows numeric literals and basic arithmetic operators
    (+, -, *, /, %, **). No function calls, attribute access,
    variable references, or imports are permitted.

    Args:
        expr: Mathematical expression string (e.g., "2 + 3 * 4")

    Returns:
        Numeric result of the expression

    Raises:
        ValueError: If the expression contains unsupported operations
    """
    tree = ast.parse(expr, mode="eval")
    return _eval_math_node(tree.body)


def _eval_math_node(node: ast.AST) -> float:
    """Recursively evaluate an AST node for safe math operations."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    elif isinstance(node, ast.BinOp) and type(node.op) in _SAFE_MATH_OPS:
        left = _eval_math_node(node.left)
        right = _eval_math_node(node.right)
        if isinstance(node.op, ast.Pow):
            if right > 1000:
                raise ValueError("Exponent too large (max 1000)")
            if left > 1e15:
                raise ValueError("Base too large for exponentiation")
        result = _SAFE_MATH_OPS[type(node.op)](left, right)
        if isinstance(result, float) and (abs(result) > 1e308 or result != result):
            raise ValueError("Result out of range")
        return result
    elif isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_MATH_OPS:
        return _SAFE_MATH_OPS[type(node.op)](_eval_math_node(node.operand))
    raise ValueError("Unsupported expression")


class MCPTool(BaseModel):
    """Definition of an MCP tool."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    function: Callable | None = None
    async_function: Callable | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MCPResource(BaseModel):
    """Definition of an MCP resource."""

    name: str
    uri: str
    description: str
    mime_type: str = "text/plain"
    metadata: dict[str, Any] = Field(default_factory=dict)


class MCPIntegration:
    """MCP server integration for Kailash workflows.

    Provides:
    - Tool registration and discovery
    - Resource management
    - Async/sync tool execution
    - Context sharing between workflows and MCP

    Attributes:
        name: MCP server name
        tools: Registry of available tools
        resources: Registry of available resources
    """

    def __init__(
        self, name: str, description: str = "", capabilities: list[str] | None = None
    ):
        """Initialize MCP integration.

        Args:
            name: MCP server name
            description: Server description
            capabilities: List of server capabilities
        """
        self.name = name
        self.description = description
        self.capabilities = capabilities or ["tools", "resources"]
        self.tools: dict[str, MCPTool] = {}
        self.resources: dict[str, MCPResource] = {}
        self._context: dict[str, Any] = {}

    def add_tool(
        self,
        name: str,
        function: Callable | Callable[..., asyncio.Future],
        description: str = "",
        parameters: dict[str, Any] | None = None,
    ):
        """Add a tool to the MCP server.

        Args:
            name: Tool name
            function: Tool implementation (sync or async)
            description: Tool description
            parameters: Tool parameter schema
        """
        tool = MCPTool(
            name=name,
            description=description,
            parameters=parameters or {},
            function=function if not asyncio.iscoroutinefunction(function) else None,
            async_function=function if asyncio.iscoroutinefunction(function) else None,
        )

        self.tools[name] = tool
        logger.info(f"Added tool '{name}' to MCP server '{self.name}'")

    def add_resource(
        self, name: str, uri: str, description: str = "", mime_type: str = "text/plain"
    ):
        """Add a resource to the MCP server.

        Args:
            name: Resource name
            uri: Resource URI
            description: Resource description
            mime_type: MIME type of the resource
        """
        resource = MCPResource(
            name=name, uri=uri, description=description, mime_type=mime_type
        )

        self.resources[name] = resource
        logger.info(f"Added resource '{name}' to MCP server '{self.name}'")

    async def execute_tool(self, tool_name: str, parameters: dict[str, Any]) -> Any:
        """Execute a tool asynchronously.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters

        Returns:
            Tool execution result
        """
        tool = self.tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found")

        # Add context to parameters only if function accepts it
        import inspect

        if tool.async_function:
            sig = inspect.signature(tool.async_function)
        elif tool.function:
            sig = inspect.signature(tool.function)
        else:
            raise ValueError(f"Tool '{tool_name}' has no function or async_function")

        if "_context" in sig.parameters:
            params = {**parameters, "_context": self._context}
        else:
            params = parameters

        if tool.async_function:
            return await tool.async_function(**params)
        elif tool.function:
            # Run sync function in executor
            loop = asyncio.get_event_loop()
            from functools import partial

            func = partial(tool.function, **params)
            return await loop.run_in_executor(None, func)
        else:
            raise ValueError(f"Tool '{tool_name}' has no implementation")

    def execute_tool_sync(self, tool_name: str, parameters: dict[str, Any]) -> Any:
        """Execute a tool synchronously.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters

        Returns:
            Tool execution result
        """
        tool = self.tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found")

        if tool.function:
            # Check if function accepts _context parameter
            import inspect

            sig = inspect.signature(tool.function)
            if "_context" in sig.parameters:
                params = {**parameters, "_context": self._context}
            else:
                params = parameters
            return tool.function(**params)
        else:
            raise ValueError(f"Tool '{tool_name}' requires async execution")

    def get_resource(self, resource_name: str) -> MCPResource | None:
        """Get a resource by name.

        Args:
            resource_name: Resource name

        Returns:
            Resource if found
        """
        return self.resources.get(resource_name)

    def set_context(self, key: str, value: Any):
        """Set context value.

        Args:
            key: Context key
            value: Context value
        """
        self._context[key] = value

    def get_context(self, key: str) -> Any:
        """Get context value.

        Args:
            key: Context key

        Returns:
            Context value
        """
        return self._context.get(key)

    def list_tools(self) -> list[dict[str, Any]]:
        """List all available tools.

        Returns:
            List of tool definitions
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self.tools.values()
        ]

    def list_resources(self) -> list[dict[str, Any]]:
        """List all available resources.

        Returns:
            List of resource definitions
        """
        return [
            {
                "name": resource.name,
                "uri": resource.uri,
                "description": resource.description,
                "mime_type": resource.mime_type,
            }
            for resource in self.resources.values()
        ]

    def to_mcp_protocol(self) -> dict[str, Any]:
        """Convert to MCP protocol format.

        Returns:
            MCP server definition
        """
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "tools": self.list_tools(),
            "resources": self.list_resources(),
        }


class MCPToolNode(AsyncNode):
    """Node that executes MCP tools within a workflow.

    This node allows workflows to use tools provided by MCP servers,
    bridging the gap between workflow automation and AI-powered tools.

    Example:
        Using an MCP tool in a workflow:

        >>> # Create node for specific tool
        >>> search_node = MCPToolNode(
        ...     mcp_server="tools",
        ...     tool_name="web_search"
        ... )
        >>> # Add to workflow
        >>> # workflow.add_node("search", search_node)  # doctest: +SKIP
        >>> # Execute with parameters
        >>> # result = workflow.run({"search": {"query": "Kailash SDK documentation"}})  # doctest: +SKIP
    """

    def __init__(
        self,
        mcp_server: str,
        tool_name: str,
        parameter_mapping: dict[str, str] | None = None,
    ):
        """Initialize MCP tool node.

        Args:
            mcp_server: Name of the MCP server
            tool_name: Name of the tool to execute
            parameter_mapping: Map input keys to tool parameters
        """
        super().__init__()
        self.mcp_server = mcp_server
        self.tool_name = tool_name
        self.parameter_mapping = parameter_mapping or {}
        self._mcp_integration: MCPIntegration | None = None

    def set_mcp_integration(self, mcp: MCPIntegration):
        """Set the MCP integration instance."""
        self._mcp_integration = mcp

    def get_parameters(self) -> dict[str, Any]:
        """Get node parameters.

        Returns:
            Dictionary of parameters
        """
        # For MCP tools, parameters are dynamic based on the tool
        return {}

    def validate_inputs(self, **kwargs) -> dict[str, Any]:
        """Validate runtime inputs.

        For MCPToolNode, we accept any inputs since the parameters
        are dynamic based on the MCP tool being used.

        Args:
            **kwargs: Runtime inputs

        Returns:
            All inputs as-is
        """
        # For MCP tools, pass through all inputs without validation
        # The actual validation happens in the MCP tool itself
        return kwargs

    def run(self, **kwargs) -> Any:
        """Run the node synchronously.

        Args:
            **kwargs: Input parameters

        Returns:
            Execution result
        """
        if not self._mcp_integration:
            raise RuntimeError("MCP integration not set")

        # Map parameters if needed
        tool_params = {}
        for input_key, tool_key in self.parameter_mapping.items():
            if input_key in kwargs:
                tool_params[tool_key] = kwargs[input_key]

        # Add unmapped parameters
        for key, value in kwargs.items():
            if key not in self.parameter_mapping:
                tool_params[key] = value

        # Use synchronous execution
        result = self._mcp_integration.execute_tool_sync(self.tool_name, tool_params)

        # Ensure result is wrapped in a dict for consistency
        if not isinstance(result, dict):
            return {"result": result}
        return result

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Run the node asynchronously.

        Args:
            **kwargs: Input parameters

        Returns:
            Dictionary of outputs
        """
        if not self._mcp_integration:
            raise RuntimeError("MCP integration not set")

        # Map parameters if needed
        tool_params = {}
        for input_key, tool_key in self.parameter_mapping.items():
            if input_key in kwargs:
                tool_params[tool_key] = kwargs[input_key]

        # Add unmapped parameters
        for key, value in kwargs.items():
            if key not in self.parameter_mapping:
                tool_params[key] = value

        # Execute tool asynchronously
        result = await self._mcp_integration.execute_tool(self.tool_name, tool_params)

        # Ensure result is wrapped in a dict for consistency
        if not isinstance(result, dict):
            return {"result": result}
        return result


def create_example_mcp_server() -> MCPIntegration:
    """Create an example MCP server with common tools."""

    mcp = MCPIntegration("example_tools", "Example MCP server with utility tools")

    # Add search tool
    async def web_search(query: str, max_results: int = 10, **kwargs):
        """Simulate web search."""
        return {
            "query": query,
            "results": [
                {"title": f"Result {i}", "url": f"https://example.com/{i}"}
                for i in range(max_results)
            ],
        }

    mcp.add_tool(
        "web_search",
        web_search,
        "Search the web",
        {
            "query": {"type": "string", "required": True},
            "max_results": {"type": "integer", "default": 10},
        },
    )

    # Add calculator tool using safe AST-based math evaluation
    def calculate(expression: str, **kwargs):
        """Evaluate mathematical expression safely.

        Uses AST parsing with a node whitelist to evaluate only numeric
        literals and basic arithmetic operators. No eval() is used.
        """
        try:
            result = _safe_math_eval(expression)
            return {"expression": expression, "result": result}
        except (ValueError, SyntaxError, TypeError, ZeroDivisionError):
            return {"error": "Invalid expression"}

    mcp.add_tool(
        "calculate",
        calculate,
        "Evaluate mathematical expressions",
        {"expression": {"type": "string", "required": True}},
    )

    # Add resources
    mcp.add_resource(
        "documentation", "https://docs.kailash.io", "Kailash SDK documentation"
    )

    mcp.add_resource(
        "examples",
        "https://github.com/kailash/examples",
        "Example workflows and patterns",
    )

    return mcp

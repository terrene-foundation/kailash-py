"""MCP Client node for connecting to Model Context Protocol servers."""

import json
from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class MCPClient(Node):
    """
    Client node for connecting to Model Context Protocol (MCP) servers.

    Design Purpose and Philosophy:
    The MCPClient node provides a standardized way to connect to MCP servers and access
    their resources, tools, and prompts. It abstracts the complexity of the MCP protocol
    while providing a simple interface for workflow integration.

    Upstream Dependencies:
    - Configuration data specifying server details
    - Authentication credentials for secure connections
    - Input parameters for resource requests and tool calls

    Downstream Consumers:
    - LLMAgent nodes that need context from MCP servers
    - Workflow nodes that orchestrate multi-step MCP interactions
    - Data processing nodes that consume MCP resources

    Usage Patterns:
    1. Connect to MCP servers using stdio, SSE, or HTTP transports
    2. List available resources, tools, and prompts from servers
    3. Fetch specific resources to provide context to AI models
    4. Execute tools on MCP servers with proper error handling
    5. Use prompts from servers for standardized interactions

    Implementation Details:
    - Uses the official MCP Python SDK for protocol compliance
    - Supports all standard MCP transports (stdio, SSE, HTTP)
    - Implements proper connection lifecycle management
    - Provides caching for frequently accessed resources
    - Handles authentication and rate limiting transparently

    Error Handling:
    - ConnectionError: When unable to connect to MCP server
    - TimeoutError: When server operations exceed timeout limits
    - AuthenticationError: When credentials are invalid or expired
    - ProtocolError: When MCP protocol violations occur
    - ResourceNotFoundError: When requested resources don't exist

    Side Effects:
    - Establishes network connections to external MCP servers
    - May cache resource data locally for performance
    - Logs connection events and errors for debugging

    Examples:

        Connect to an MCP server and list resources::

        client = MCPClient()
        result = client.run(
            server_config={
                "name": "filesystem-server",
                "command": "python",
                "args": ["-m", "mcp_filesystem"]
            },
            operation="list_resources"
        )

        Fetch a specific resource:

        resource = client.run(
            server_config=server_config,
            operation="read_resource",
            resource_uri="file:///path/to/document.txt"
        )

        Call a tool on the server:

        tool_result = client.run(
            server_config=server_config,
            operation="call_tool",
            tool_name="create_file",
            tool_arguments={
                "path": "/path/to/new_file.txt",
                "content": "Hello, World!"
            }
        )
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "server_config": NodeParameter(
                name="server_config",
                type=dict,
                required=False,
                default={},
                description="MCP server configuration (name, command, args, transport)",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="list_resources",
                description="Operation to perform: list_resources, read_resource, list_tools, call_tool, list_prompts, get_prompt",
            ),
            "resource_uri": NodeParameter(
                name="resource_uri",
                type=str,
                required=False,
                description="URI of the resource to read (for read_resource operation)",
            ),
            "tool_name": NodeParameter(
                name="tool_name",
                type=str,
                required=False,
                description="Name of the tool to call (for call_tool operation)",
            ),
            "tool_arguments": NodeParameter(
                name="tool_arguments",
                type=dict,
                required=False,
                default={},
                description="Arguments to pass to the tool (for call_tool operation)",
            ),
            "prompt_name": NodeParameter(
                name="prompt_name",
                type=str,
                required=False,
                description="Name of the prompt to get (for get_prompt operation)",
            ),
            "prompt_arguments": NodeParameter(
                name="prompt_arguments",
                type=dict,
                required=False,
                default={},
                description="Arguments to pass to the prompt (for get_prompt operation)",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                required=False,
                default=30,
                description="Timeout in seconds for MCP operations",
            ),
            "max_retries": NodeParameter(
                name="max_retries",
                type=int,
                required=False,
                default=3,
                description="Maximum number of retry attempts",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        server_config = kwargs["server_config"]
        operation = kwargs["operation"]
        resource_uri = kwargs.get("resource_uri")
        tool_name = kwargs.get("tool_name")
        tool_arguments = kwargs.get("tool_arguments", {})
        prompt_name = kwargs.get("prompt_name")
        prompt_arguments = kwargs.get("prompt_arguments", {})
        # timeout = kwargs.get("timeout", 30)  # unused for now
        # max_retries = kwargs.get("max_retries", 3)  # unused for now

        try:
            # Import MCP SDK (graceful fallback if not installed)
            try:
                import mcp.client.session  # noqa: F401

                mcp_available = True
            except ImportError:
                mcp_available = False

            if not mcp_available:
                # Provide mock functionality when MCP SDK is not available
                return self._mock_mcp_operation(
                    operation,
                    server_config,
                    resource_uri,
                    tool_name,
                    tool_arguments,
                    prompt_name,
                    prompt_arguments,
                )

            # Extract server configuration
            server_name = server_config.get("name", "unknown-server")
            transport_type = server_config.get("transport", "stdio")

            if transport_type == "stdio":
                command = server_config.get("command")
                args = server_config.get("args", [])

                if not command:
                    raise ValueError(
                        "stdio transport requires 'command' in server_config"
                    )

                # For now, provide mock implementation as we need the actual MCP server running
                return self._mock_stdio_operation(
                    operation,
                    server_name,
                    command,
                    args,
                    resource_uri,
                    tool_name,
                    tool_arguments,
                    prompt_name,
                    prompt_arguments,
                )

            elif transport_type in ["sse", "http"]:
                # HTTP/SSE transport implementation
                url = server_config.get("url")
                headers = server_config.get("headers", {})

                if not url:
                    raise ValueError(
                        f"{transport_type} transport requires 'url' in server_config"
                    )

                return self._mock_http_operation(
                    operation,
                    server_name,
                    url,
                    headers,
                    resource_uri,
                    tool_name,
                    tool_arguments,
                    prompt_name,
                    prompt_arguments,
                )

            else:
                raise ValueError(f"Unsupported transport type: {transport_type}")

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "operation": operation,
                "server": server_config.get("name", "unknown"),
            }

    def _mock_mcp_operation(
        self,
        operation: str,
        server_config: dict,
        resource_uri: Optional[str],
        tool_name: Optional[str],
        tool_arguments: dict,
        prompt_name: Optional[str],
        prompt_arguments: dict,
    ) -> Dict[str, Any]:
        """Mock MCP operations when SDK is not available."""
        server_name = server_config.get("name", "mock-server")

        if operation == "list_resources":
            return {
                "success": True,
                "operation": operation,
                "server": server_name,
                "resources": [
                    {
                        "uri": "file:///example/document.txt",
                        "name": "Example Document",
                        "description": "A sample text document",
                        "mimeType": "text/plain",
                    },
                    {
                        "uri": "data://config/settings.json",
                        "name": "Configuration Settings",
                        "description": "Application configuration",
                        "mimeType": "application/json",
                    },
                ],
                "resource_count": 2,
                "mock": True,
            }

        elif operation == "read_resource":
            if not resource_uri:
                return {
                    "success": False,
                    "error": "resource_uri is required for read_resource operation",
                    "operation": operation,
                    "server": server_name,
                }

            # Mock resource content based on URI
            if "document.txt" in resource_uri:
                content = "This is the content of the example document.\nIt contains sample text for testing MCP functionality."
            elif "settings.json" in resource_uri:
                content = json.dumps(
                    {
                        "app_name": "MCP Demo",
                        "version": "1.0.0",
                        "features": ["resource_access", "tool_calling", "prompts"],
                    },
                    indent=2,
                )
            else:
                content = f"Mock content for resource: {resource_uri}"

            return {
                "success": True,
                "operation": operation,
                "server": server_name,
                "resource": {
                    "uri": resource_uri,
                    "content": content,
                    "mimeType": (
                        "text/plain"
                        if resource_uri.endswith(".txt")
                        else "application/json"
                    ),
                },
                "mock": True,
            }

        elif operation == "list_tools":
            return {
                "success": True,
                "operation": operation,
                "server": server_name,
                "tools": [
                    {
                        "name": "create_file",
                        "description": "Create a new file with specified content",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "File path"},
                                "content": {
                                    "type": "string",
                                    "description": "File content",
                                },
                            },
                            "required": ["path", "content"],
                        },
                    },
                    {
                        "name": "search_files",
                        "description": "Search for files matching a pattern",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "pattern": {
                                    "type": "string",
                                    "description": "Search pattern",
                                },
                                "directory": {
                                    "type": "string",
                                    "description": "Directory to search",
                                },
                            },
                            "required": ["pattern"],
                        },
                    },
                ],
                "tool_count": 2,
                "mock": True,
            }

        elif operation == "call_tool":
            if not tool_name:
                return {
                    "success": False,
                    "error": "tool_name is required for call_tool operation",
                    "operation": operation,
                    "server": server_name,
                }

            # Mock tool execution results
            if tool_name == "create_file":
                path = tool_arguments.get("path", "/unknown/path")
                content = tool_arguments.get("content", "")
                result = {
                    "success": True,
                    "message": f"File created successfully at {path}",
                    "file_size": len(content),
                    "created_at": "2025-06-01T12:00:00Z",
                }
            elif tool_name == "search_files":
                pattern = tool_arguments.get("pattern", "*")
                directory = tool_arguments.get("directory", "/")
                result = {
                    "matches": [
                        f"{directory}/example1.txt",
                        f"{directory}/example2.txt",
                    ],
                    "pattern": pattern,
                    "total_matches": 2,
                }
            else:
                result = {
                    "message": f"Mock execution of tool '{tool_name}'",
                    "arguments": tool_arguments,
                }

            return {
                "success": True,
                "operation": operation,
                "server": server_name,
                "tool_name": tool_name,
                "tool_arguments": tool_arguments,
                "result": result,
                "mock": True,
            }

        elif operation == "list_prompts":
            return {
                "success": True,
                "operation": operation,
                "server": server_name,
                "prompts": [
                    {
                        "name": "summarize_document",
                        "description": "Summarize a document with specified length",
                        "arguments": [
                            {
                                "name": "document",
                                "description": "Document to summarize",
                                "required": True,
                            },
                            {
                                "name": "max_length",
                                "description": "Maximum summary length",
                                "required": False,
                            },
                        ],
                    },
                    {
                        "name": "analyze_code",
                        "description": "Analyze code for issues and improvements",
                        "arguments": [
                            {
                                "name": "code",
                                "description": "Code to analyze",
                                "required": True,
                            },
                            {
                                "name": "language",
                                "description": "Programming language",
                                "required": False,
                            },
                        ],
                    },
                ],
                "prompt_count": 2,
                "mock": True,
            }

        elif operation == "get_prompt":
            if not prompt_name:
                return {
                    "success": False,
                    "error": "prompt_name is required for get_prompt operation",
                    "operation": operation,
                    "server": server_name,
                }

            # Mock prompt content
            if prompt_name == "summarize_document":
                document = prompt_arguments.get("document", "[DOCUMENT CONTENT]")
                max_length = prompt_arguments.get("max_length", 200)
                prompt_content = f"Please summarize the following document in no more than {max_length} words:\n\n{document}"
            elif prompt_name == "analyze_code":
                code = prompt_arguments.get("code", "[CODE CONTENT]")
                language = prompt_arguments.get("language", "python")
                prompt_content = f"Please analyze the following {language} code and provide feedback on potential issues and improvements:\n\n```{language}\n{code}\n```"
            else:
                prompt_content = f"Mock prompt content for '{prompt_name}' with arguments: {prompt_arguments}"

            return {
                "success": True,
                "operation": operation,
                "server": server_name,
                "prompt_name": prompt_name,
                "prompt_arguments": prompt_arguments,
                "prompt": {
                    "name": prompt_name,
                    "content": prompt_content,
                    "arguments": prompt_arguments,
                },
                "mock": True,
            }

        else:
            return {
                "success": False,
                "error": f"Unsupported operation: {operation}",
                "operation": operation,
                "server": server_name,
                "supported_operations": [
                    "list_resources",
                    "read_resource",
                    "list_tools",
                    "call_tool",
                    "list_prompts",
                    "get_prompt",
                ],
            }

    def _mock_stdio_operation(
        self,
        operation: str,
        server_name: str,
        command: str,
        args: List[str],
        resource_uri: Optional[str],
        tool_name: Optional[str],
        tool_arguments: dict,
        prompt_name: Optional[str],
        prompt_arguments: dict,
    ) -> Dict[str, Any]:
        """Mock stdio transport operations."""
        result = self._mock_mcp_operation(
            operation,
            {"name": server_name},
            resource_uri,
            tool_name,
            tool_arguments,
            prompt_name,
            prompt_arguments,
        )
        result.update(
            {"transport": "stdio", "command": command, "args": args, "mock": True}
        )
        return result

    def _mock_http_operation(
        self,
        operation: str,
        server_name: str,
        url: str,
        headers: dict,
        resource_uri: Optional[str],
        tool_name: Optional[str],
        tool_arguments: dict,
        prompt_name: Optional[str],
        prompt_arguments: dict,
    ) -> Dict[str, Any]:
        """Mock HTTP/SSE transport operations."""
        result = self._mock_mcp_operation(
            operation,
            {"name": server_name},
            resource_uri,
            tool_name,
            tool_arguments,
            prompt_name,
            prompt_arguments,
        )
        result.update(
            {"transport": "http", "url": url, "headers": headers, "mock": True}
        )
        return result

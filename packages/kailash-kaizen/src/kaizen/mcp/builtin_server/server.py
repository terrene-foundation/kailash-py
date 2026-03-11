"""
Kaizen Builtin MCP Server

This module implements the main MCP server for Kaizen's builtin tools.

The server provides 12 tools across 4 categories:
- File operations (5 tools)
- HTTP requests (4 tools)
- Bash commands (1 tool)
- Web scraping (2 tools)

Architecture:
- Extends Kailash SDK's MCPServer with auto-registration capabilities
- Uses @mcp_tool decorator for metadata-aware tool registration
- Runs on stdio transport for BaseAgent integration
- 100% MCP spec compliant

Example (Standalone):
    python -m kaizen.mcp.builtin_server

Example (Integration):
    BaseAgent auto-connects to this server by default.
"""

import inspect
import logging
from typing import Any, List

from kailash.mcp_server import MCPServer

logger = logging.getLogger(__name__)


class KaizenMCPServer(MCPServer):
    """
    Extended MCPServer with metadata-aware auto-registration.

    This class extends Kailash SDK's MCPServer to add automatic tool
    registration from modules using the @mcp_tool decorator pattern.
    """

    def auto_register_tools(self, modules: List[Any]) -> int:
        """
        Auto-discover and register MCP tools with full metadata support.

        Scans modules for async functions decorated with @mcp_tool and
        registers them using the @server.tool() pattern.

        Args:
            modules: List of Python modules containing async tool functions
                    decorated with @mcp_tool

        Returns:
            Number of tools registered

        Example:
            from .tools import file, api, bash, web
            total_tools = server.auto_register_tools([file, api, bash, web])
        """
        registered_count = 0

        for module in modules:
            # Get all async functions from module
            for name, obj in inspect.getmembers(module, inspect.iscoroutinefunction):
                # Check if function has MCP metadata (from @mcp_tool decorator)
                if not getattr(obj, "_is_mcp_tool", False):
                    continue

                # Extract metadata
                tool_name = getattr(obj, "_mcp_name", name)
                tool_description = getattr(obj, "_mcp_description", obj.__doc__)
                # tool_parameters = getattr(obj, '_mcp_parameters', {})

                # Register with Kailash SDK's @server.tool() decorator
                # NOTE: Kailash SDK infers parameters from function signature
                self.tool()(obj)

                registered_count += 1
                logger.info(f"Registered MCP tool: {tool_name}")

        return registered_count


# Create extended server instance
server = KaizenMCPServer(name="kaizen_builtin")

# Set server metadata as instance attributes
server.description = (
    "Kaizen builtin tools - file operations, HTTP requests, bash commands, web scraping"
)
server.version = "1.0.0"

# Import all tool modules
from .tools import api, bash, file, web

# Auto-register all @mcp_tool decorated functions
# This registers all 12 tools:
# - File (5): read_file, write_file, delete_file, list_directory, file_exists
# - API (4): http_get, http_post, http_put, http_delete
# - Bash (1): bash_command
# - Web (2): fetch_url, extract_links
total_tools = server.auto_register_tools([file, api, bash, web])

logger.info(f"Kaizen builtin MCP server initialized with {total_tools} tools")


def main():
    """
    Main entry point for standalone server execution.

    Starts the MCP server on stdio transport for integration with BaseAgent.
    """
    logger.info("Starting Kaizen builtin MCP server (stdio transport)")

    # Start server (stdio transport is default)
    server.run()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run server
    main()

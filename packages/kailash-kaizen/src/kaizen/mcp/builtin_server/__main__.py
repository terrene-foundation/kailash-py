"""
Main entry point for Kaizen builtin MCP server.

Enables running the server as a module:
    python -m kaizen.mcp.builtin_server
"""

from .server import main

if __name__ == "__main__":
    main()

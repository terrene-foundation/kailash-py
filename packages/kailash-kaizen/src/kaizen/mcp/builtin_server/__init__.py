"""
Kaizen Builtin MCP Server

Production-ready MCP server providing Kaizen's 12 builtin tools:

File Tools (5):
- read_file: Read file contents
- write_file: Write content to file
- delete_file: Delete a file
- list_directory: List directory contents
- file_exists: Check if file exists

HTTP Tools (4):
- http_get: Make HTTP GET request
- http_post: Make HTTP POST request
- http_put: Make HTTP PUT request
- http_delete: Make HTTP DELETE request

Bash Tools (1):
- bash_command: Execute shell commands

Web Tools (2):
- fetch_url: Fetch web page content
- extract_links: Extract links from HTML

Usage (Standalone):
    python -m kaizen.mcp.builtin_server

Usage (Integration):
    BaseAgent auto-connects to this server by default.

Architecture:
- Uses Kailash SDK's MCPServer (@tool decorator pattern)
- Stdio transport for BaseAgent integration
- Preserves all security validations from custom tools
- 100% MCP spec compliant
"""

from .server import server

__all__ = ["server"]

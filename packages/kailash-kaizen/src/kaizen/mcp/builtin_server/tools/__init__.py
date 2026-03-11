"""
Kaizen Builtin MCP Tools

This package contains all MCP tool implementations for Kaizen's builtin tools.

Modules:
- file: File operation tools (read, write, delete, list, exists)
- api: HTTP request tools (GET, POST, PUT, DELETE)
- bash: Bash command execution tool
- web: Web scraping tools (fetch URL, extract links)

All tools use the @tool decorator from kailash.mcp_server for MCP compliance.
All tools preserve security validations from original custom implementations.
"""

from . import api, bash, file, web

__all__ = ["file", "api", "bash", "web"]

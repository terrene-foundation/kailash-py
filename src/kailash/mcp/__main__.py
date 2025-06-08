"""
Entry point for running MCP servers as modules.

Usage:
    python -m kailash.mcp.ai_registry_server
"""

import asyncio

from .ai_registry_server import main

if __name__ == "__main__":
    asyncio.run(main())

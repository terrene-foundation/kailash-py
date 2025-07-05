#!/usr/bin/env python3
"""
Simple script to start the AI Registry MCP server.

This script starts the server in stdio mode which is the standard
way to run MCP servers. The server communicates via stdin/stdout.

Usage:
    python scripts/start-ai-registry-server.py

This should be run in a separate terminal for testing.
"""

import logging
import sys
from pathlib import Path

# Add src to path so we can import kailash
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Import after path modification
from kailash.mcp_server.servers.ai_registry import AIRegistryServer  # noqa: E402


def main():
    """Start the AI Registry MCP server."""
    logging.basicConfig(level=logging.INFO)

    # Use default registry file
    registry_file = project_root / "research" / "combined_ai_registry.json"

    print("Starting AI Registry MCP Server...")
    print(f"Registry file: {registry_file}")
    print("This server communicates via stdio (stdin/stdout)")
    print("Press Ctrl+C to stop")
    print("-" * 50)

    try:
        server = AIRegistryServer(
            registry_file=str(registry_file), name="ai-registry-server"
        )
        server.start()
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

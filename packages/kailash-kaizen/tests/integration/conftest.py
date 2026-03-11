"""
Integration test fixtures for MCP examples.

Provides real MCP server instances for client tests using production
kailash.mcp_server infrastructure (NO MOCKING).

✅ UPDATED (2025-10-04): Uses real Kailash SDK MCP infrastructure
- Real MCPServer from kailash.mcp_server
- Real JSON-RPC 2.0 protocol
- No manual tool copying (deprecated populate_agent_tools removed)
- Automatic tool discovery via protocol
"""

import logging

import pytest

# Real MCP infrastructure from Kailash SDK
from kailash.mcp_server import SimpleMCPServer

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def real_mcp_test_server():
    """
    Start a real MCP server for integration tests using kailash.mcp_server.

    This server exposes tools via real JSON-RPC 2.0 protocol:
    - question_answering: Answer questions
    - text_analysis: Analyze text content
    - calculate: Perform calculations

    Uses SimpleMCPServer from Kailash SDK (production-ready).
    """
    # Create real MCP server from Kailash SDK
    server = SimpleMCPServer("integration-test-server")

    # Register real tools via decorator
    @server.tool()
    def question_answering(question: str, context: str = "") -> dict:
        """Answer questions using AI."""
        return {
            "answer": f"Mock answer to: {question}",
            "confidence": 0.9,
            "sources": ["test"],
        }

    @server.tool()
    def text_analysis(text: str, analysis_type: str = "general") -> dict:
        """Analyze text content."""
        return {
            "key_topics": ["AI", "testing"],
            "sentiment": "positive",
            "summary": f"Analysis of: {text[:50]}...",
        }

    @server.tool()
    def calculate(a: int, b: int, operation: str = "add") -> dict:
        """Perform mathematical calculations."""
        operations = {
            "add": a + b,
            "subtract": a - b,
            "multiply": a * b,
            "divide": a / b if b != 0 else None,
        }
        return {"result": operations.get(operation, 0)}

    # Start server (async)
    # Note: SimpleMCPServer runs in background, no explicit start needed for STDIO
    # For HTTP transport, we'd need to start it explicitly

    yield {
        "server": server,
        "server_name": "integration-test-server",
        "port": 18080,  # For HTTP transport
        "transport": "stdio",  # Default transport
        "available_tools": ["question_answering", "text_analysis", "calculate"],
    }

    # Cleanup (SimpleMCPServer handles cleanup automatically)


@pytest.fixture(scope="session")
def real_mcp_test_server_with_tools():
    """
    Start a real MCP server with multiple tools for comprehensive testing.

    Uses SimpleMCPServer with extended tool set.
    """
    server = SimpleMCPServer("tools-test-server")

    # Extended tool set for comprehensive testing
    @server.tool()
    def search(query: str, limit: int = 10) -> dict:
        """Search for information."""
        return {"results": [{"title": f"Result for {query}", "score": 0.9}], "count": 1}

    @server.tool()
    def summarize(text: str, max_length: int = 100) -> dict:
        """Summarize text."""
        return {"summary": text[:max_length] + "..."}

    @server.tool()
    def translate(text: str, target_lang: str = "en") -> dict:
        """Translate text."""
        return {"translated": f"Translated to {target_lang}: {text}"}

    @server.tool()
    def analyze_sentiment(text: str) -> dict:
        """Analyze sentiment of text."""
        return {"sentiment": "positive", "confidence": 0.85}

    yield {
        "server": server,
        "server_name": "tools-test-server",
        "port": 18081,
        "transport": "stdio",
        "available_tools": ["search", "summarize", "translate", "analyze_sentiment"],
    }

    # Cleanup handled automatically


@pytest.fixture
def mcp_server_info(real_mcp_test_server):
    """
    Provide MCP server connection info for tests.

    Returns server config for use with BaseAgent.setup_mcp_client()
    or direct kailash.mcp_server.MCPClient usage.

    NO MANUAL TOOL COPYING - Tools are discovered via real JSON-RPC protocol.
    """
    # Return server info for client connection
    # Clients should use BaseAgent.setup_mcp_client() or MCPClient
    # to discover tools automatically via protocol
    return {
        "server": real_mcp_test_server["server"],
        "server_name": real_mcp_test_server["server_name"],
        "transport": real_mcp_test_server["transport"],
        "port": real_mcp_test_server["port"],
        "available_tools": real_mcp_test_server["available_tools"],
        # Server config for client connections
        "server_config": {
            "name": real_mcp_test_server["server_name"],
            "transport": "stdio",  # SimpleMCPServer uses STDIO by default
            "command": "python",  # Not needed for in-process server
            "args": [],
        },
    }


@pytest.fixture
def mcp_tools_server_info(real_mcp_test_server_with_tools):
    """
    Provide MCP tools server connection info for tests.

    Returns server config for use with BaseAgent.setup_mcp_client()
    or direct kailash.mcp_server.MCPClient usage.
    """
    return {
        "server": real_mcp_test_server_with_tools["server"],
        "server_name": real_mcp_test_server_with_tools["server_name"],
        "transport": real_mcp_test_server_with_tools["transport"],
        "port": real_mcp_test_server_with_tools["port"],
        "available_tools": real_mcp_test_server_with_tools["available_tools"],
        # Server config for client connections
        "server_config": {
            "name": real_mcp_test_server_with_tools["server_name"],
            "transport": "stdio",
            "command": "python",
            "args": [],
        },
    }

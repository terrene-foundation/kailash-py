"""
Agent as MCP Server Example

Demonstrates how Kaizen agents can be exposed as MCP servers using real
Model Context Protocol (MCP) with JSON-RPC 2.0 server implementation.
"""

from .workflow import (
    MCPServerAgent,
    MCPServerAgentConfig,
    QuestionAnsweringSignature,
    TextAnalysisSignature,
    ToolDiscoverySignature,
)

__all__ = [
    "MCPServerAgentConfig",
    "MCPServerAgent",
    "QuestionAnsweringSignature",
    "TextAnalysisSignature",
    "ToolDiscoverySignature",
]

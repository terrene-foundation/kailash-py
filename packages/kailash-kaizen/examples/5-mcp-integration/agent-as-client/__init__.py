"""
Agent as MCP Client Example

Demonstrates how Kaizen agents consume external MCP tools using real
Model Context Protocol (MCP) with JSON-RPC 2.0 communication.
"""

from .workflow import (
    MCPClientAgent,
    MCPClientConfig,
    ResultSynthesisSignature,
    TaskAnalysisSignature,
    ToolInvocationSignature,
)

__all__ = [
    "MCPClientConfig",
    "MCPClientAgent",
    "TaskAnalysisSignature",
    "ToolInvocationSignature",
    "ResultSynthesisSignature",
]

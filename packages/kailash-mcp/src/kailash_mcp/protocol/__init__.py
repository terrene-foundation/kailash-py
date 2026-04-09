# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""MCP protocol implementation -- message types, progress, cancellation, completion.

This package exposes two groups of symbols:

1. **Runtime protocol managers** (``ProgressManager``, ``CancellationManager``,
   ...) -- stateful helpers used by MCP servers and clients at runtime.
2. **Canonical wire types** (``JsonRpcRequest``, ``JsonRpcResponse``,
   ``JsonRpcError``, ``McpToolInfo``) -- frozen dataclasses that define the
   cross-SDK JSON shape per SPEC-01 §7 and SPEC-09 §2.1. Both ``kailash-py``
   and ``kailash-rs`` MUST produce byte-identical canonical JSON for the
   same logical input per EATP D6.
"""

from kailash_mcp.protocol.messages import (
    JSONRPC_VERSION,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcValidationError,
    McpToolInfo,
)
from kailash_mcp.protocol.protocol import (
    CancellationManager,
    CancelledNotification,
    CompletionManager,
    CompletionRequest,
    CompletionResult,
    MessageType,
    MetaData,
    ProgressManager,
    ProgressNotification,
    ProgressToken,
    ProtocolManager,
    ResourceChange,
    ResourceChangeType,
    ResourceTemplate,
    RootsManager,
    SamplingManager,
    SamplingRequest,
    ToolResult,
    cancel_request,
    complete_progress,
    get_protocol_manager,
    is_cancelled,
    start_progress,
    update_progress,
)

__all__ = [
    # Canonical wire types (SPEC-01 §7 / SPEC-09 §2.1)
    "JSONRPC_VERSION",
    "JsonRpcError",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "JsonRpcValidationError",
    "McpToolInfo",
    # Runtime protocol managers
    "CancellationManager",
    "CancelledNotification",
    "CompletionManager",
    "CompletionRequest",
    "CompletionResult",
    "MessageType",
    "MetaData",
    "ProgressManager",
    "ProgressNotification",
    "ProgressToken",
    "ProtocolManager",
    "ResourceChange",
    "ResourceChangeType",
    "ResourceTemplate",
    "RootsManager",
    "SamplingManager",
    "SamplingRequest",
    "ToolResult",
    "cancel_request",
    "complete_progress",
    "get_protocol_manager",
    "is_cancelled",
    "start_progress",
    "update_progress",
]

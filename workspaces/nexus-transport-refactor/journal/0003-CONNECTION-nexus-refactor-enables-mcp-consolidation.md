---
type: CONNECTION
date: 2026-04-01
created_at: 2026-04-01T10:05:00+08:00
author: agent
session_id: analyze-phase
session_turn: 1
project: nexus-transport-refactor
topic: Nexus transport abstraction is prerequisite for MCP platform server consolidation
phase: analyze
tags: [mcp, nexus, transport, consolidation, cross-workspace, architecture]
---

# CONNECTION: Nexus Transport Abstraction Is Prerequisite for MCP Platform Server Consolidation

## Connection

The nexus-transport-refactor and mcp-platform-server workspaces are architecturally coupled. The gap analysis verified that 6 MCP server implementations exist across the codebase: 3 in Nexus (to be deleted/consolidated) and 3 in Core SDK (to be kept). The transport abstraction introduced by B0b is what makes clean MCP consolidation possible.

### Current State: MCP Is Tangled with HTTP

Today, MCP server initialization happens inside the Nexus class alongside FastAPI gateway setup:

- `_initialize_mcp_server()` (lines 388-443) -- creates MCP server
- `_create_mock_mcp_server()` (lines 570-594) -- fallback MCP
- `_create_sdk_mcp_server()` (lines 596-649) -- production MCP
- `_setup_mcp_channel()` (lines 651-681) -- MCP channel wiring
- `_register_workflow_as_mcp_tool()` (lines 683-718) -- auto-registration

These 330 lines of MCP code live in core.py alongside 2,100 lines of HTTP/gateway code. They share internal state (`self._mcp_server`, `self._mcp_channel`) and lifecycle management (both started in `start()`, both cleaned up in `stop()`).

### After B0b: Transport Abstraction Enables Clean MCP Extraction

Once HTTPTransport is extracted (B0b), MCP becomes a natural second transport:

```
Nexus (orchestrator)
  ├── HandlerRegistry (from B0a)
  ├── EventBus (from B0a)
  ├── HTTPTransport (from B0b) -- wraps FastAPI gateway
  └── MCPTransport (future) -- wraps MCP server
```

The `HandlerRegistry` from B0a is the key enabler: handlers register once and are exposed through all transports. Without the registry abstraction, each transport must independently discover and register handlers -- which is exactly the duplication that exists today (workflows registered to both `_gateway` and `_mcp_channel` in separate code paths within `register()`).

### The MCP Platform Server Overlap

The mcp-platform-server workspace aims to consolidate the 6 MCP implementations into a unified architecture. Three of those implementations live in Nexus and will be removed during or after the transport refactor. The critical sequencing question is:

1. **Nexus refactor first** (this workspace) -- extract HTTPTransport, making MCP extraction a clean follow-up
2. **MCP consolidation first** (mcp-platform-server) -- consolidate MCP servers, then refactor Nexus around the result
3. **Parallel** -- both workspaces proceed independently and merge

Option 1 is the lowest-risk path. B0a's HandlerRegistry and B0b's transport abstraction create the architectural foundation that MCP consolidation needs. If MCP consolidation proceeds first, it would modify the same core.py code that this workspace is refactoring -- creating merge conflicts and potentially building on an architecture that is about to change.

### Shared Concern: EventBus

Both workspaces need an EventBus. Nexus B0a creates `NexusEventBus` for handler lifecycle events. The MCP platform server needs event notifications for resource changes (so AI agents can receive real-time updates). If these EventBus implementations diverge, the future bridge between them becomes an adapter layer. If they share a common design (both building on Core SDK's `InMemoryEventBus`), the bridge is trivial.

This parallels the dataflow-enhancements workspace's EventBus needs (TSG-201). All three workspaces converge on the Core SDK EventBus as shared infrastructure.

### kailash-rs Alignment

The audit verified that kailash-rs already has the target architecture: `HandlerRegistry` and `EventBus` patterns exist in `handler.rs` and `events/bus.rs`. The Python refactor is converging toward the same design. This is strong cross-SDK alignment -- the Rust implementation serves as validated prior art for the Python transport abstraction.

## Implication

The nexus-transport-refactor workspace should complete B0a and B0b before the mcp-platform-server workspace begins its Nexus-side consolidation. The HandlerRegistry and transport abstraction are prerequisites, not parallel work streams. The EventBus design should be coordinated across all three workspaces (dataflow-enhancements, nexus-transport-refactor, mcp-platform-server) to avoid divergent event dispatch patterns.

## For Discussion

1. The audit found that kailash-rs already has `HandlerRegistry` and `EventBus` patterns in `handler.rs` and `events/bus.rs`. Given that the Python refactor is converging toward the same design, should the Python implementation explicitly follow the Rust API shape (for cross-SDK alignment per EATP D6), or should it follow Python idioms even if the API surface diverges?

2. If the mcp-platform-server workspace proceeded before this refactor completed, its consolidation would modify the same 330 lines of MCP code in core.py that B0b will relocate. Would the resulting merge conflict be manageable (both workspaces removing code from the same file), or catastrophic (the MCP workspace building new abstractions on top of code that B0b deletes)?

3. All three workspaces (dataflow-enhancements, nexus-transport-refactor, mcp-platform-server) converge on the Core SDK EventBus. If a single "EventBus improvement" task were extracted as a shared prerequisite across all three workspaces -- adding wildcard subscriptions and async dispatch -- would that reduce total effort, or would the coordination overhead of a cross-workspace dependency outweigh the benefits?

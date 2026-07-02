---
type: CONNECTION
date: 2026-04-01
created_at: 2026-04-01T10:02:00+08:00
author: agent
session_id: analyze-phase
session_turn: 1
project: dataflow-enhancements
topic: Six features converge on engine.py and connect to nexus-transport-refactor and mcp-platform-server
phase: analyze
tags: [cross-workspace, dependencies, engine-py, nexus, mcp, architecture]
---

# CONNECTION: Six Features Converge on engine.py and Connect to Nexus and MCP Workspaces

## Internal Feature Dependency Structure

The cross-dependencies analysis reveals a clear dependency graph among the 6 DataFlow features:

**Independent features** (can be built in any order):

- TSG-102 (FileSourceNode) -- new node + Express method, standalone
- TSG-104 (Express Cache) -- wires existing cache/ to Express
- TSG-105 (ReadReplica) -- wires existing router to DataFlow
- TSG-106 (RetentionEngine) -- new feature, reads `__dataflow__["retention"]`

**Soft dependency**:

- TSG-103 (Validation) -- standalone, but TSG-100 benefits from validated source data

**Sequential chain**:

- TSG-100 (DerivedModel scheduled/manual) depends on nothing
- TSG-201 (DataFlowEventMixin) depends on Core SDK EventBus understanding
- TSG-101 (DerivedModel on_source_change) depends on both TSG-100 and TSG-201

The critical insight is that **all features converge on engine.py** (6,400 lines). Every feature modifies `DataFlow.__init__` or `@db.model` or adds properties. Four features also modify express.py (TSG-102, TSG-103, TSG-104, TSG-105). This creates two bottleneck files that every feature must touch.

## Cross-Workspace Connections

### DataFlow <-> nexus-transport-refactor

The cross-dependencies document identifies TSG-250 (DataFlow-Nexus bridge) as a downstream dependency: after DataFlow gains event capabilities (TSG-201), Nexus can subscribe to DataFlow events to trigger real-time updates over WebSocket or SSE channels. The nexus-transport-refactor workspace's B0a phase creates a `NexusEventBus` using janus.Queue for thread-safe async/sync bridging -- the same pattern DataFlow needs for its own async event dispatch.

Specifically:

- DataFlow's TSG-201 introduces `DataFlowEventMixin` with event emission on every CRUD operation
- Nexus's B0a introduces `NexusEventBus` with `NexusEvent` and `NexusEventType`
- Both need to interface with Core SDK's `InMemoryEventBus`
- The eventual bridge (TSG-250) would route DataFlow events through Nexus channels

If the Nexus EventBus and DataFlow EventBus diverge in design (different event types, different dispatch models), the TSG-250 bridge becomes an adapter layer rather than a direct connection. Coordinating event type design across both workspaces now saves rework later.

### DataFlow <-> mcp-platform-server

The MCP consolidation workspace affects how DataFlow operations are exposed as MCP tools. Currently, DataFlow-backed workflows registered through Nexus are automatically converted to MCP tools. If the MCP platform server consolidates 6 scattered MCP implementations into a unified architecture, the DataFlow event stream (TSG-201) could feed MCP resource subscriptions -- allowing AI agents to subscribe to data change notifications through the MCP protocol.

### Shared Infrastructure Concern: EventBus

All three workspaces converge on the Core SDK EventBus:

- **DataFlow**: Uses it for model change events (TSG-201)
- **Nexus**: Uses it for handler lifecycle events (B0a)
- **MCP**: Could use it for resource change notifications

The EventBus's current limitation (no wildcard subscriptions, synchronous dispatch) affects all three. A fix in the Core SDK EventBus benefits all workspaces simultaneously. Conversely, if each workspace builds its own workaround, we get three divergent event dispatch patterns.

## The engine.py Merge Risk

The cross-dependencies analysis confirms that sequential development (as recommended in the implementation plan) is the safest approach. The brief's claimed parallelization to "~2 sessions wall clock" is optimistic -- it requires careful coordination of engine.py changes across branches. Each feature adds 20-100 lines to engine.py across `__init__`, `model()`, and new properties/methods. Six concurrent branches modifying the same ranges would produce substantial merge conflicts.

The mitigation strategy -- creating separate modules (`features/derived.py`, `features/retention.py`, `core/events.py`) and minimizing engine.py additions to parameter forwarding and 1-2 line hooks -- is sound but requires discipline.

## For Discussion

1. DataFlow's TSG-201 and Nexus's B0a both introduce EventBus integrations at roughly the same time. If both workspaces designed their event types collaboratively (shared `DomainEvent` subclasses, compatible event type naming), would the TSG-250 bridge become trivial -- or does the difference in context (database CRUD events vs HTTP handler lifecycle events) make shared event types an over-abstraction?

2. If engine.py had been decomposed into smaller modules before this workspace started (e.g., a prior refactoring workspace), would the 6 features become truly parallelizable -- reducing the total effort from 6.25 sequential sessions to perhaps 3 parallel sessions? What is the break-even point where an engine.py decomposition workspace pays for itself?

3. The cross-SDK alignment research found that Rust's `QueryCache` with DashMap + TTL is already wired to DataFlow, while Python's sophisticated cache infrastructure sits unwired. If the Rust SDK had not been ahead on cache wiring, would cache integration (TSG-104) have been prioritized differently in the implementation plan?

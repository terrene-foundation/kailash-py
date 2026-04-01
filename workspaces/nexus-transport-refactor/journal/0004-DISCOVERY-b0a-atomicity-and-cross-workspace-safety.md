---
type: DISCOVERY
date: 2026-04-01
created_at: 2026-04-01T11:30:00+08:00
author: agent
session_id: redteam-r2
session_turn: 1
project: nexus-transport-refactor
topic: B0a is atomically decomposable into 4 independent commits with clean rollback
phase: analyze
tags:
  [
    atomicity,
    rollback,
    refactoring,
    commit-strategy,
    cross-workspace,
    eventbus,
    safety,
  ]
---

# DISCOVERY: B0a Atomicity and Cross-Workspace Safety Verified

## Context

Red Team Round 2 examined whether B0a (HandlerRegistry + EventBus + BackgroundService extraction from core.py) is safe to ship as an intermediate state, whether it can be rolled back if tests fail, and whether cross-workspace dependencies (mcp-platform-server, dataflow-enhancements) create hidden risks for the refactoring.

## Key Findings

### 1. B0a Decomposes into 4 Independent Commits

The B0a scope, which initially appeared as a single large refactoring session, breaks cleanly into four commits with no circular dependencies:

1. Dead code removal (lines 1929-2007 of core.py) -- pure deletion, zero risk
2. HandlerRegistry extraction -- the core refactoring, independently revertible
3. EventBus extraction -- standalone module, depends on commit 2 only at the import level
4. BackgroundService ABC -- smallest change, fully independent

If the session runs long, commits 1-2 alone constitute a "minimum viable B0a" that unblocks Phase 2 features. The EventBus (commit 3) and BackgroundService (commit 4) can ship in a follow-up session without rework.

### 2. Intermediate State Is Safe

After B0a but before B0b, the codebase has new internal modules (registry.py, events.py, background.py) that the Nexus class delegates to internally, while the FastAPI gateway coupling in core.py remains unchanged. All 30+ test files that import from `nexus` or `nexus.core` use the public API exclusively -- no test accesses `self._workflows` or `self._handler_registry` directly. This means the internal delegation is transparent to the test suite.

### 3. Cross-Workspace Sequencing Validated

The mcp-platform-server's deletion of `nexus/mcp/server.py` and `nexus/mcp_websocket_server.py` actually simplifies B0b's scope -- instead of extracting MCPTransport from non-standard code, B0b integrates with FastMCP. The DataFlow event bridge (TSG-250) requires only `subscribe_filtered()` in the Nexus EventBus API, which is already in the design. Neither cross-workspace dependency affects B0a.

### 4. broadcast_event() Migration Has a Subtle Semantic Change

The migration from `_event_log` (unbounded list) to EventBus (bounded buffer, capacity=256) means `get_events()` returns at most 256 recent events instead of complete history. This is actually an improvement (the unbounded list was a memory leak), but the semantic change must be documented in MIGRATION.md. The implementation requires an internal subscriber at EventBus construction time that accumulates events in a `deque(maxlen=256)` to support the `get_events()` query API.

## Implications

- The `/todos` phase can define 4 granular work items for B0a instead of 1 monolithic task
- Each work item has a clear definition of done and an independent rollback strategy
- The cross-workspace synthesis sequencing (established in `kailash/01-analysis/06-cross-workspace-synthesis.md`) holds under scrutiny -- no hidden coupling was found
- MIGRATION.md becomes a deliverable of B0a (not just B0b as originally planned), to document the event history bounding

## For Discussion

1. The commit structure places dead code removal first. If the "dead" methods (`_initialize_runtime_capabilities`, `_activate_multi_channel_orchestration`, `_log_revolutionary_startup`) turn out to have callers we missed, commit 1 would break tests. A grep found no callers -- but what if they are called via string-based dynamic dispatch or plugin reflection?

2. If the mcp-platform-server workspace had chosen Option B (nexus refactor B0b first), B0b would have extracted MCPTransport from the non-standard `nexus/mcp/server.py` protocol, then mcp-platform-server would have replaced it. How much wasted effort would that represent compared to the chosen Option A?

3. The `deque(maxlen=256)` for `get_events()` history creates a secondary data structure alongside the EventBus's janus.Queue. If the EventBus already has a bounded buffer, is there a way to avoid the duplication -- perhaps by making the EventBus itself provide a `recent_events()` query method instead of relying on a separate subscriber?

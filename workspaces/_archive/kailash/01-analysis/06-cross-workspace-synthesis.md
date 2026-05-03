# Cross-Workspace Synthesis — 5 New Workspaces Analysis

Date: 2026-04-01
Phase: /analyze (all 5 workspaces analyzed in parallel)

## Overview

Five new workspaces were analyzed in a single session. This document synthesizes findings, identifies cross-workspace dependencies, and recommends implementation sequencing.

## Workspace Status — CONVERGED (R2 Complete)

| Workspace                | Research | R1          | R2                                                | Journals  | Convergence           |
| ------------------------ | -------- | ----------- | ------------------------------------------------- | --------- | --------------------- |
| dataflow-enhancements    | 7/7      | 10 findings | 6 new (1H, 4M, 1L) — 8/10 R1 RESOLVED             | 4 entries | **PROCEED TO /todos** |
| nexus-transport-refactor | 7/7      | 8 findings  | 6 new (0H, 2M, 4L) — all R1 confirmed             | 4 entries | **CONVERGED**         |
| mcp-platform-server      | 6/6      | 10 findings | 14 new (3H, 7M, 4L) — 8/10 R1 RESOLVED            | 4 entries | **No R3 needed**      |
| kailash-ml               | 7/7      | 10 findings | 8 new (2H, 4M, 2L) — 3/4 HIGH partially resolved  | 9 entries | **CONVERGED**         |
| kailash-align            | 7/7      | 7 findings  | 4 new (0C, 3M, 1L) — CRITICAL→MEDIUM, HIGH→MEDIUM | 9 entries | **CONVERGED**         |

All 5 workspaces converged in 2 rounds. No R3 needed. All remaining findings are implementation-level details, not architectural gaps.

## Critical Cross-Workspace Dependencies

### Dependency 1: kailash-ml → kailash-align (BLOCKING)

kailash-align depends on kailash-ml's `ModelRegistry` for `AdapterRegistry`. This is a hard sequential dependency.

**Required action**: Define and freeze the ModelRegistry interface in `kailash-ml-protocols` BEFORE either package starts implementation. This is the P0 action from kailash-align's red team (RT3-03, CRITICAL).

### Dependency 2: MCP consolidation overlap (mcp-platform-server ↔ nexus-transport-refactor)

Both workspaces modify Nexus MCP code:

- mcp-platform-server TSG-500 deletes `nexus/mcp/server.py` and `nexus/mcp_websocket_server.py`
- nexus-transport-refactor B0b extracts MCPTransport from the same files

**Required action**: Sequence them. Either:

- (A) mcp-platform-server deletes Nexus MCP files first, then nexus-transport-refactor skips MCP extraction
- (B) nexus-transport-refactor completes B0b first, then mcp-platform-server only adds the new platform server

**Recommendation**: Option A. The platform server is the more valuable deliverable; nexus refactor B0b can adapt.

### Dependency 3: DataFlow events → Nexus events (dataflow-enhancements → nexus-transport-refactor)

DataFlow TSG-201 (EventMixin) emits events via Core SDK EventBus. The DataFlow-Nexus event bridge (TSG-250) translates these into Nexus events. This requires Nexus EventBus (B0a) to exist first.

**Required action**: nexus-transport-refactor B0a (EventBus extraction) ships before dataflow-enhancements TSG-250.

### Dependency 4: DataFlow → kailash-ml (dataflow-enhancements → kailash-ml)

kailash-ml's FeatureStore and ModelRegistry use DataFlow for persistence. DerivedModelEngine (TSG-100) enables application-layer materialized views that FeatureStore would use.

**This is a soft dependency** — kailash-ml can work without DerivedModel, but benefits from it.

## Top Findings by Severity

### CRITICAL (2)

1. **EventBus wildcard subscription gap** (dataflow-enhancements) — Core SDK InMemoryEventBus does NOT support wildcard patterns. Architecture docs describe an API that silently receives zero events. Resolution: use 8 specific subscriptions per model.

2. **kailash-ml dependency ordering** (kailash-align) — kailash-align cannot start until kailash-ml's ModelRegistry interface is frozen. Resolution: define interface in kailash-ml-protocols first.

### HIGH (5)

1. **Synchronous event handler blocking** (dataflow) — DerivedModel recompute inside a write handler blocks the write. Must fire-and-forget with async dispatch.

2. **Non-ImportError exceptions crash MCP server** (mcp-platform-server) — Contributor plugin loop only catches ImportError. Any other exception during registration crashes the server.

3. **polars-only ecosystem friction** (kailash-ml) — Zero polars usage in existing codebase. Every external ML library requires pandas/numpy conversion. Must add pandas conversion utilities.

4. **Agent guardrail implementation risks** (kailash-ml) — LLM confidence scores are poorly calibrated. Cost tracking lags pricing changes. Human approval breaks async flow.

5. **GGUF conversion reliability** (kailash-align) — Silent failures possible. Post-conversion validation and "bring your own GGUF" escape hatch required.

### Most Significant Insights

- **Static vs Runtime introspection** (mcp-platform-server, GAP-2): The platform MCP server runs as a separate process and CANNOT access framework registries at runtime. Tier 1 tools must use AST-based source scanning, fundamentally changing the architecture.

- **ReadReplica is harder than described** (dataflow, Challenge 5): Brief claims "80% built" but DataFlow's entire execution pipeline assumes a single adapter. Actual integration work is significant.

- **Value concentration** (kailash-align): The framework's existence is justified by AdapterRegistry (no equivalent exists) and AlignmentServing (error-prone manual process). Training is a thin TRL wrapper; agents are premature abstraction.

- **9 engines scope risk** (kailash-ml, RT-R1-07): P(all 9 production quality) = 39%. Recommend explicit P0/P1/P2 quality tiering.

## Recommended Implementation Sequence

### Phase 0: Interface Contracts (1 session)

- Define and release `kailash-ml-protocols` with frozen ModelRegistry interface
- Unblocks kailash-ml AND kailash-align

### Phase 1: Infrastructure (2-3 sessions, parallelizable)

- **nexus-transport-refactor B0a**: HandlerRegistry + EventBus + BackgroundService extraction
- **dataflow-enhancements TSG-102, TSG-103, TSG-104, TSG-105, TSG-106**: Independent features (no cross-deps)
- **mcp-platform-server TSG-500**: Server skeleton + contributor plugin system

### Phase 2: Core Features (4-6 sessions, partially parallelizable)

- **dataflow-enhancements TSG-100**: DerivedModelEngine (scheduled + manual)
- **mcp-platform-server TSG-501-503**: Framework contributors (parallel)
- **kailash-ml WS-1 through WS-5**: Core engines (TrainingPipeline, FeatureStore, ModelRegistry, InferenceServer, DriftMonitor)
- **nexus-transport-refactor B0b**: HTTPTransport + MCPTransport extraction

### Phase 3: Integration (3-5 sessions)

- **dataflow-enhancements TSG-201 + TSG-101**: EventMixin + on_source_change DerivedModel
- **mcp-platform-server TSG-504-507**: platform_map + validation + test gen + E2E
- **kailash-ml WS-6 through WS-9**: Advanced engines (AutoML, HyperSearch, DataExplorer, FeatureEngineer)
- **kailash-align WS-A1 through WS-A3**: AdapterRegistry + AlignmentPipeline + Evaluator

### Phase 4: Serving + Bridge (2-3 sessions)

- **kailash-align WS-A4 through WS-A6**: AlignmentServing + KaizenModelBridge + OnPremModelCache
- **DataFlow-Nexus event bridge** (TSG-250)

### Total Estimated Effort

- **Optimistic**: ~15 sessions (maximum parallelization, no surprises)
- **Realistic**: ~20 sessions (accounting for red team findings, test failures, integration issues)
- **Conservative**: ~25 sessions (GGUF edge cases, polars friction, protocol coordination)

## Decisions Needed

1. **MCP/Nexus sequencing**: Which workspace goes first for MCP file modifications?
2. **kailash-ml scope**: Ship all 9 engines (with quality tiering) or 5 core engines?
3. **kailash-align agents**: Include in v1 or defer to v1.1?
4. **DataFlow validation syntax**: `__validation__` separate dict or `__dataflow__["validation"]`?
5. **polars interop**: Include `to_pandas()`/`from_pandas()` in interop module?

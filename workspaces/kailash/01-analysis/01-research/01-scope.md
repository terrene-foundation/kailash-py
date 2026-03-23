# Kailash Core SDK Runtime Optimization — Analysis

## Scope

Performance optimization of the Kailash Core SDK runtime. Three phases:

- **Phase 0a** (Quick Wins): Module-level imports, metrics reuse, psutil opt-in, env caching, node deduplication
- **Phase 0b** (Deduplication): Remove triple validation, fix double construction, NodeMetadata dataclass, cache topo sort, cache cycle edges, precompute input routing
- **Phase 0c** (networkx Replacement): Custom WorkflowDAG class replacing networkx dependency

## Status

Todos already human-approved (2026-03-13). 20 active items across P0A (5), P0B (6), P0C (6), P0X cross-cutting (2), plus 1 deferred (AWS KMS).

## Key Findings (from previous session)

1. **networkx is the biggest dependency** — used for only 17 of hundreds of features. Custom WorkflowDAG (~250 lines) can replace it entirely.
2. **In-loop imports** cause repeated sys.modules lookups in hot paths.
3. **Triple validation** of the same workflow in sequential calls wastes CPU.
4. **psutil** imported unconditionally but only needed for resource monitoring.

## Implementation Order

P0A (no deps) → P0B (no deps, parallel with P0A) → P0C (depends on P0B-004 for topo sort cache) → P0X (benchmark + regression tests, throughout)

## Analysis Conclusion

No re-analysis needed — the previous session produced detailed, actionable todos with specific file paths, line numbers, and acceptance criteria. Proceed directly to implementation.

# Implementation Plan — Runtime Optimization

## Execution Strategy

All Phase 0a and 0b items are independent — execute in parallel. Phase 0c is sequential (build DAG class → tests → migration → runtime wiring).

## Phase 0a: Quick Wins (5 items, parallel)

- P0A-001: Move in-loop imports to module level
- P0A-002: Reuse metrics collector instance
- P0A-003: Make psutil opt-in import
- P0A-004: Cache environment variable lookups
- P0A-005: Eliminate redundant set-nodes calls

## Phase 0b: Deduplication (6 items, parallel)

- P0B-001: Remove triple validation
- P0B-002: Fix double node construction
- P0B-003: NodeMetadata dataclass
- P0B-004: Cache topological sort results
- P0B-005: Cache cycle edge computation
- P0B-006: Precompute input routing table

## Phase 0c: networkx Replacement (6 items, sequential)

- P0C-001: Implement WorkflowDAG class
- P0C-002: WorkflowDAG tests
- P0C-003: Migrate graph.py to use WorkflowDAG
- P0C-004: Migrate runtime files
- P0C-005: Optional networkx for visualization only
- P0C-006: Update package dependencies

## Cross-cutting

- P0X-001: Benchmark infrastructure
- P0X-002: Regression test suite

## Session Estimate

- P0A + P0B: 1 autonomous session (parallel agents)
- P0C: 1 autonomous session (sequential)
- Total: 2 sessions

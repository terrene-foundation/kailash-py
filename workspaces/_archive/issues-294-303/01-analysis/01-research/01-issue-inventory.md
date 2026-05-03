# Issue Inventory — 10 Open GitHub Issues (#294-#303)

## Priority Matrix

### P0 — Bugs (fix immediately, zero tolerance)

| #   | Title                                             | Package          | Complexity | Notes                                            |
| --- | ------------------------------------------------- | ---------------- | ---------- | ------------------------------------------------ |
| 295 | DataExplorer correlation matrices lack isfinite() | kailash-ml       | Low        | 3 methods need guards, pattern exists            |
| 296 | bulk_upsert Express API missing event emission    | kailash-dataflow | Medium     | **Method itself doesn't exist**, not just events |

### P1 — Features

| #   | Title                                          | Package       | Complexity | Notes                                       |
| --- | ---------------------------------------------- | ------------- | ---------- | ------------------------------------------- |
| 297 | 4 Kaizen agent definitions for align workflows | kailash-align | High       | New agents/ directory, follow ML pattern    |
| 298 | On-prem workflow — OnPremSetupGuide + config   | kailash-align | Medium     | Config exists, needs plumbing + guide class |
| 299 | Nexus contributor missing list_events + fields | core SDK MCP  | Medium     | AST parsing extensions needed               |

### P1 — Testing

| #   | Title                                       | Package         | Complexity | Notes                                      |
| --- | ------------------------------------------- | --------------- | ---------- | ------------------------------------------ |
| 300 | Platform server integration tests (FastMCP) | core SDK MCP    | Medium     | In-process tests exist, need McpClient     |
| 301 | WS-4.5 integration gate — 3 scenarios       | cross-framework | High       | **platform_map() doesn't exist** — blocker |

### P2 — Docs + CI

| #   | Title                                         | Package      | Complexity | Notes                                     |
| --- | --------------------------------------------- | ------------ | ---------- | ----------------------------------------- |
| 302 | Framework guides for ML and Align (12 guides) | ml + align   | High       | No guides exist, follow DataFlow pattern  |
| 303 | Test pipelines for ML and Align               | CI workflows | Medium     | publish-pypi.yml exists, need test-\*.yml |

### Tracking Only

| #   | Title                                     | Package   | Notes                             |
| --- | ----------------------------------------- | --------- | --------------------------------- |
| 294 | kailash-rs vector node pgvector alignment | cross-sdk | No kailash-py code changes needed |

## Critical Finding: Issue #296 Scope Mismatch

The issue describes "missing event emission" but research shows **bulk_upsert() doesn't exist as a method at all**. WRITE_OPERATIONS constant lists "bulk_upsert" but no async/sync implementation exists. Two options:

1. **Implement bulk_upsert()** with event emission (matches WRITE_OPERATIONS expectation)
2. **Remove "bulk_upsert" from WRITE_OPERATIONS** if intentionally unsupported

Recommendation: Option 1 — implement the method. The constant declaring 8 operations while only 7 exist is a code-data inconsistency.

## Critical Finding: Issue #301 Scenario 3 Blocked

`platform_map()` does not exist anywhere in the codebase. Scenario 3 requires it. Options:

1. **Implement platform_map()** as part of this sprint (adds scope)
2. **Descope Scenario 3** from this sprint, file follow-up issue
3. **Implement minimal platform_map()** that returns framework connection graph

Recommendation: Option 3 — implement minimal version in MCP platform server since that's where contributors register, giving natural access to the framework graph.

## Dependency Graph

```
#295 (ML NaN guards)        → independent, do first
#296 (DataFlow bulk_upsert) → independent, do first
#298 (align on-prem)        → independent
#297 (align agents)         → depends on understanding #298 config
#299 (MCP nexus contrib)    → independent
#300 (MCP platform tests)   → depends on #299 (list_events needed for test assertions)
#301 scenario 1             → depends on #296 (event emission)
#301 scenario 2             → depends on ML InferenceServer (exists)
#301 scenario 3             → BLOCKED on platform_map() implementation
#302 (docs)                 → depends on #297, #298 being implemented first
#303 (CI)                   → independent of features
#294 (cross-sdk)            → no action needed
```

## Execution Plan (parallel where possible)

**Wave 1** (parallel): #295, #296, #298, #299, #303
**Wave 2** (parallel): #297, #300 (after #299)
**Wave 3**: #301 (after #296 events working, platform_map implemented)
**Wave 4**: #302 (docs — after features land)
**Wave 5**: #294 (close with note — no action)

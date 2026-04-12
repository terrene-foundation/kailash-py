# All Open GitHub Issues — #294 through #303

## Scope

10 open issues across 6 frameworks. Analyze all, plan, implement, red team to convergence.

## Issue Inventory

### Bugs (P0 — fix immediately)

| #   | Title                                                           | Package          |
| --- | --------------------------------------------------------------- | ---------------- |
| 295 | fix(ml): DataExplorer correlation matrices lack isfinite guards | kailash-ml       |
| 296 | fix(dataflow): bulk_upsert Express API missing event emission   | kailash-dataflow |

### Features (P1)

| #   | Title                                                                   | Package       |
| --- | ----------------------------------------------------------------------- | ------------- |
| 297 | feat(align): 4 Kaizen agent definitions for alignment workflows         | kailash-align |
| 298 | feat(align): on-prem workflow — OnPremSetupGuide + config plumbing      | kailash-align |
| 299 | fix(mcp): Nexus contributor missing list_events + handler output fields | core SDK MCP  |

### Testing (P1)

| #   | Title                                                            | Package         |
| --- | ---------------------------------------------------------------- | --------------- |
| 300 | test(mcp): platform server integration tests targeting FastMCP   | core SDK MCP    |
| 301 | test: WS-4.5 integration gate — 3 cross-framework test scenarios | cross-framework |

### Documentation (P2)

| #   | Title                                                   | Package    |
| --- | ------------------------------------------------------- | ---------- |
| 302 | docs: framework guides for kailash-ml and kailash-align | ml + align |

### CI/CD (P2)

| #   | Title                                               | Package      |
| --- | --------------------------------------------------- | ------------ |
| 303 | ci: test pipelines for kailash-ml and kailash-align | CI workflows |

### Cross-SDK (tracking only)

| #   | Title                                                              | Package   |
| --- | ------------------------------------------------------------------ | --------- |
| 294 | docs(cross-sdk): kailash-rs vector node pgvector backend alignment | cross-sdk |

## Execution Order

1. Bugs first (#295, #296) — zero tolerance
2. Features (#297, #298, #299) — parallel where possible
3. Testing (#300, #301) — depends on features
4. Docs + CI (#302, #303) — can parallel with testing
5. Cross-SDK (#294) — tracking, no code changes on kailash-py

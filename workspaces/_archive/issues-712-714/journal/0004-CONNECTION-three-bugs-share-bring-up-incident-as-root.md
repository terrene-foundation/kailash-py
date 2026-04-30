---
type: CONNECTION
created: 2026-04-29
issue: 712,713,714
phase: 01-analyze
---

# All three bugs surface from one downstream-consumer bring-up sequence

## Connection

The three bugs are independent in the SDK code (Nexus, DataFlow runtime,
DataFlow DDL) but they were discovered in a single chain by a single
downstream consumer:

```
the downstream consumer wires DataFlow into Nexus FastAPI app
↓
Step A: Try @nexus.app.on_event("startup") to call create_tables_async()
        → silently fails (The downstream consumer likely on stale Nexus pre-2.1.1)
        → bug filed as #712
        → workaround: wrap app.router.lifespan_context

Step B: Inside the lifespan wrapper, call db.create_tables_async()
        → AttributeError: 'LocalRuntime' has no attribute 'execute_workflow_async'
        → bug filed as #713
        → workaround: db.runtime = AsyncLocalRuntime(); db._is_async = True

Step C: Try db.create_tables() (sync) as escape hatch
        → MaxClientsInSessionMode against Supabase pgbouncer
        → bug filed as #714
        → workaround: stick with async path despite #713 fragility
```

## Why it's worth noting

This is the **second time** in 30 days the SDK has accumulated bugs along
the Nexus + DataFlow integration seam:

- 2026-04-12 to 19: PR cluster #500 / #501 / #531 / #533 / #538 / #540
  (impact-verse downstream incident — Nexus FastAPI lifespan hooks)
- 2026-04-29: This cluster (the downstream consumer — full Nexus + DataFlow bring-up)

Both incidents are **integration-seam bugs**, not unit-level bugs. Unit
tests for `WorkflowServer`, `DataFlow`, `AsyncSQLDatabaseNode` all pass
in isolation; only when consumers wire them together does the failure
emerge. The SDK lacks a Tier-3 regression test that exercises a
realistic Nexus + DataFlow + DDL bring-up sequence end-to-end.

Per `rules/testing.md` § "End-to-End Pipeline Regression":

> Every canonical pipeline the docs teach (README Quick Start, tutorial,
> 3-line example) MUST have a Tier-2+ regression test executing DOCS-EXACT
> code against real infra, asserting the final user-visible outcome.

The "Nexus + DataFlow at startup" pattern is canonical (it's in every
"deploy DataFlow as an API" tutorial). It does NOT have an E2E regression.

## Codification follow-up (for /codify phase)

Add a rule or skill section: **canonical bring-up patterns MUST have an
E2E regression test that wires the framework boundary the consumer wires.**
The unit tests for each side are insufficient — the bugs live at the seam.

This is the analog of `rules/testing.md` § "End-to-End Pipeline Regression"
for canonical SDK BRING-UP patterns (vs. canonical SDK USAGE patterns).
Worth a rule-strengthening discussion at /codify.

## Related

- Architecture: `01-analysis/01-architecture.md`
- Implementation plan: `02-plans/01-implementation-plan.md` § Test plan
  (includes `test_downstream_consumer_pattern_end_to_end.py` Tier-3 regression)
- Prior cluster journal: `workspaces/issues-500-501/01-analysis/01-root-cause-unified.md`
  (impact-verse incident, similar shape)

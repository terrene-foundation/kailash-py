# 0001 DISCOVERY — Silent Fallback + No Lifecycle Is One Failure Pattern

**Date:** 2026-04-28
**Session:** dataflow-prod-incident /analyze
**Type:** DISCOVERY

## Finding

Three of the five issues in this workstream (#696, #697, #698) trace to the same compound failure pattern. Each looks like a separate bug at first reading; together they form a single architectural anti-pattern that the rules already prohibit at three layers but that surfaces when those layers don't reinforce each other.

**The pattern is:** the framework hits an error condition, decides to keep working in a degraded mode, and creates state for that degraded mode WITHOUT a lifecycle bound. The result is monotonic resource accumulation that surfaces as a production outage hours or days later.

| Issue | Error condition       | Degraded mode           | Lifecycle bound (missing)               |
| ----- | --------------------- | ----------------------- | --------------------------------------- |
| #696  | CREATE TABLE fails    | "Try again next time"   | Failed-DDL state with retry suppression |
| #697  | Per-pool lock timeout | "Make a dedicated pool" | Process-wide registry with eviction     |
| #698  | Pool created          | "Keep until shutdown"   | Idle-timeout reaper                     |

Each one alone is a slow leak; combined they are mutually amplifying — the DDL retry fires the AsyncSQL node every 30 s, which under saturation triggers the lock-timeout fallback, which creates a fresh pool. Within minutes, Azure PG saturates.

## Why the existing rules didn't catch it

`zero-tolerance.md` Rule 3 (silent fallbacks) covers the error-handling layer.
`dataflow-pool.md` Rule 5 (no orphan runtimes) covers the lifecycle layer.
`observability.md` Rule 7 (bulk ops MUST WARN on partial failure) covers the visibility layer.

Each rule is correctly scoped to its concern. The compound pattern needs all three to fire together — and the framework historically separated them across files (engine.py owns DDL; async_sql.py owns pools; the visibility layer is implicit in both). No single agent reading any one file would see the compound.

## Codification candidate

Add a meta-rule (or a clause to one of the existing rules) that names "silent fallback + no lifecycle bound" as a single failure class with a structural defense:

> Whenever the framework chooses to continue past an error condition, the chosen continuation MUST be (a) bounded — there is a structural cap on how many times the continuation can fire, (b) tracked — the continuation creates state that's enumerable + reapable, and (c) surfaced — every continuation event emits a structured log + metric so alerting can fire BEFORE the cap.

This is a 3-axis test that would have caught all three issues at PR review time:

- #696: continuation = "lazy DDL retry"; bounded? NO. tracked? NO. surfaced? ERROR-only, no metric.
- #697: continuation = "dedicated pool fallback"; bounded? NO. tracked? NO (instance-only). surfaced? WARN, no metric.
- #698: continuation = "pool kept alive"; bounded? NO. tracked? class-shared dict but not bounded. surfaced? NO.

## Cross-SDK applicability

The pattern is architectural, not language-specific. Rust DataFlow has the same architecture:

- `EnterpriseConnectionPool` analog with similar lifecycle gaps
- `auto_migrate` in `kailash-rs` shares the lazy-creation-on-access pattern
- The compound failure is platform-independent

Cross-SDK issues to file after this fix lands.

## Action

This DISCOVERY feeds into the `/codify` step at the end of this workstream. The codified rule extension MUST land at loom (cross-SDK) given the architectural breadth.

## Related

- Sibling: `rules/zero-tolerance.md` Rule 3
- Sibling: `rules/dataflow-pool.md` Rule 5
- Sibling: `rules/observability.md` Rule 7
- Compound failure mode prior art: Phase 5.11 orphan trust executor (rules/orphan-detection.md)

# DECISION: Phase 5 sequenced (SPEC-08 before SPEC-06)

**Date**: 2026-04-08
**Phase**: 02 (todos)
**Trigger**: Red team RT-001 — AuditStore built in two places simultaneously

## Context

The original plan had Phase 5 as parallel: SPEC-06 (Nexus auth migration) and SPEC-08 (Core SDK audit consolidation) running simultaneously in separate worktrees. Both create/modify `SqliteAuditStore` at `src/kailash/trust/audit_store.py`. Parallel worktrees writing the same file produce merge conflicts.

## Decision

Phase 5 is now sequential:
- **Phase 5a**: SPEC-08 (Core SDK) — owns `AuditStore`, `BudgetTracker`, `Registry` consolidation
- **Phase 5b**: SPEC-06 (Nexus) — consumes the canonical `AuditStore` from 5a

## Rationale

SPEC-06 (Nexus auth migration) needs the canonical `AuditStore` to wire Nexus audit logging. SPEC-08 creates that store. The dependency is real, not just a file-collision issue. Running them in parallel would produce either merge conflicts or one spec inventing a temporary store that the other replaces.

## Consequences

- Wall-clock Phase 5 is now 5 cycles (2 + 3) instead of 3 cycles (parallel max). Total estimate increases from ~18-22 to ~20-24 cycles.
- Nexus implementation is blocked until Core SDK audit consolidation delivers `AuditStore`. This is acceptable because Nexus's PACTMiddleware also needs the canonical `GovernanceEngine` which is stable already.
- No impact on other phases.

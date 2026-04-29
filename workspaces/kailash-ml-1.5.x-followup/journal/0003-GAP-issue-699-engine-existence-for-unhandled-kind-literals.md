# 0003 — GAP — Open Questions Before /todos

**Type:** GAP
**Date:** 2026-04-28
**Phase:** /analyze
**Workstream:** kailash-ml-1.5.x-followup

Three deferred questions surfaced during analysis. Each MUST be resolved before `/todos` so shard plans are concrete.

## GAP 1 — Do the four unhandled `kind` literals have engines that exist?

**Context.** Issue #701 bonus finding: `_wrappers.py:474–485` accepts `kind="clustering"`, `kind="alignment"`, `kind="llm"`, `kind="agent"` as valid literals, but the dispatcher has no branch for any of them — they silently fall through to `DLDiagnostics(subject)`.

**The gap.** Do diagnostic engines exist for these four kinds? Two possible truths:

- **(a) Engines exist** but were not wired into the dispatcher. Fix: add the four dispatch branches; the implementations are already there. Per `rules/zero-tolerance.md` Rule 6 (Implement Fully), the absence of dispatch is the bug.
- **(b) Engines do NOT exist**; the literals were accepted as a forward-looking placeholder. Fix: REMOVE them from the accepted-literals list AND from the spec — accepting a literal you cannot dispatch is `rules/zero-tolerance.md` Rule 2 (stub / "fake dispatch").

**Resolution (closed during /analyze).** Verified via `grep -rEn 'class\s+(Clustering|Alignment|LLM|Agent)Diagnostic' packages/`:

- `AlignmentDiagnostics` exists at `packages/kailash-align/src/kailash_align/diagnostics/alignment.py:182`
- `LLMDiagnostics` exists at `packages/kailash-kaizen/src/kaizen/judges/llm_diagnostics.py:155`
- `AgentDiagnostics` exists at `packages/kailash-kaizen/src/kaizen/observability/agent_diagnostics.py:156`
- `ClusteringDiagnostic` not found by direct grep — may exist under a different name (e.g., `ClassicalClusterDiagnostic`); needs a wider search at `/todos`.

Spec `ml-diagnostics.md` § 57 explicitly names `AlignmentDiagnostics`, `LLMDiagnostics`, `AgentDiagnostics` as sibling diagnostics following the §4 tracker-wiring contract. So the dispatcher SHOULD route to them.

**New shape for ADR-3:** the four `kind=` literals point to engines that live in **sibling packages** (`kailash-align`, `kailash-kaizen`). This means the dispatcher needs cross-package imports with extras gating — `kailash-ml` cannot assume `kailash-align` or `kailash-kaizen` is installed. Per `rules/dependencies.md` § "BLOCKED Anti-Patterns", the import MUST be a loud failure at call site (raise on missing dep with install hint), NOT a silent fallback. Per `rules/specs-authority.md` §7, the spec sibling references already exist; this is a wiring fix, not a new contract.

**Open sub-question for `/todos`:** is `clustering` covered by an existing class in `packages/kailash-ml/src/kailash_ml/engines/clustering.py` or `packages/kailash-ml/src/kailash_ml/diagnostics/`? Answer at /todos via wider grep. If yes: dispatch. If no: refuse with explicit "not yet implemented" message AND remove the literal from the accepted list per `rules/zero-tolerance.md` Rule 2 (no fake dispatch).

## GAP 2 — User reproducer backtrace for #699

**Context.** The issue body says "ExperimentTracker.create() initializes `_kml_model_versions` with the tenant-aware schema" — but verified reality is that the migration system does this, not ExperimentTracker directly. The user's reproducer DID hit `OperationalError: table _kml_model_versions has no column named name` — so the failure path is real, but the framing is off.

**The gap.** What's the actual sequence in the user's reproducer that produces the failure? Almost certainly: `ExperimentTracker.create(store_url=db)` triggers migration 0002, which creates the table tenant-aware. Then `ModelRegistry(ConnectionManager(db))` constructs successfully, and `register_model(...)` does the INSERT against `name = ?` — failing because the column is `model_name`. That sequence matches both the issue body's symptoms AND the verified migration-vs-application-code framing.

**Resolution before /todos.** Run the reproducer end-to-end against a fresh SQLite file and capture the full traceback. This is a 30-second sanity check that the proposed fix (delete inline DDL + plumb tenant_id + use `model_name` in queries) actually addresses the failure mode. The Tier-2 regression test in ADR-1 IS this reproducer, so the test itself is the validation step.

## GAP 3 — Migration 0005 vs no migration for ≤1.4.x users

**Context.** Existing 1.5.0 / 1.5.1 users already have the tenant-aware schema on disk via migration 0002 — for them, the fix is code-only. Existing ≤1.4.x users (kailash-ml predating migration 0002, if any) might have the un-tenanted shape on disk; they need a forward-migration `0005_add_tenant_id_to_kml_model_versions.py`.

**The gap.** Are there ≤1.4.x users in the wild? PyPI download stats can answer this; CHANGELOG history can answer when the un-tenanted schema was last shipped (kailash-ml 0.x ↔ 1.4.x).

**Resolution before /todos.** Default to "ship code-only fix in 1.5.2; document forward-path in CHANGELOG". If telemetry / GitHub issue surfaces a ≤1.4.x user, ship migration 0005 in 1.5.3 patch. This is a deferred decision, not a blocker for /todos — record it as a conditional shard.

## Summary

GAP 1 is the only blocker for `/todos` — the answer changes ADR-3's shard count. GAPs 2 and 3 are sanity checks that fold naturally into `/implement` (GAP 2 IS the regression test; GAP 3 is a conditional follow-up patch).

---
type: DISCOVERY
date: 2026-05-04
author: co-authored
project: dataflow-engine-pyright-cleanup
topic: MockConnectionPool shim is NOT orphaned — get_connection_pool() has 10+ live test callers; D1 disposition corrected from DELETE to RELOCATE
phase: analyze
tags:
  [
    pyright,
    orphan-detection,
    get_connection_pool,
    red-team-correction,
    mock_helpers,
  ]
---

# DISCOVERY: MockConnectionPool shim is NOT orphaned — `get_connection_pool()` has 10+ live test callers

**Surfaced by:** Class A error investigation (E1) → red-team review caught the disposition error

## CORRECTION

This entry's earlier conclusion ("the shim is fully orphaned, delete in S1") is **WRONG**. Red-team review surfaced the gap; this section documents the correction first, original (now-superseded) analysis follows.

**What I missed:** the original grep checked for consumers of the SYMBOL `MockConnectionPool`. It did not check for consumers of the METHOD `get_connection_pool()` that wraps the shim. Verified post-review:

```bash
grep -rn "get_connection_pool()" packages/kailash-dataflow/tests/ | wc -l
# 10 — live test callers
```

Sites:

- `tests/integration/transactions/test_workflow_integration.py:695`
- `tests/integration/core_engine/test_database_operations.py:118,186`
- `tests/integration/core_engine/test_production_dataflow.py:126,176,222,286,308,384,409`

These tests call `db.get_connection_pool()` and then `pool.get_connection()` / `pool.get_health_status()` / `pool.get_metrics()` on the returned object. Deleting `get_connection_pool()` (which is what L3430-3450 deletion implies) breaks all 10 sites.

## Corrected disposition (replaces D1 in 02-plans/01-cleanup-architecture.md)

The L3437 rule violation (production code importing `tests.fixtures.*`) MUST be fixed. The fix is NOT to delete `get_connection_pool()`. Three viable options, ranked optimal-first:

1. **Move `MockConnectionPool` out of `tests/fixtures/` into a shippable package path** (e.g. `packages/kailash-dataflow/src/dataflow/testing/mock_helpers.py`). engine.py imports from the real package path; tests update their imports too. Closes E1 at root cause; preserves `get_connection_pool()` behavior; eliminates the import-discipline violation per `production-test-isolation.md`.
2. **Suppress with `# pyright: ignore[reportMissingImports]` + `# Reason: <X>` + tracking issue** per `zero-tolerance.md` Rule 1b. Acceptable ONLY if Option 1 is infeasible (e.g. `dataflow.testing` namespace conflicts with another package). Requires release-specialist signoff per Rule 1b's four conditions.
3. **Restructure `get_connection_pool()` to never return a `MockConnectionPool`** — return a real pool when initialized, raise typed `RuntimeError` when not. Deletes the test-fixture code path entirely. Largest blast radius (changes test-helper contract) but most-correct long-term.

**Recommended:** Option 1. It satisfies L3437 at root cause without breaking any caller, and the resulting `dataflow.testing` namespace is a precedent worth setting (test fixtures that production paths reference belong in a shippable package).

## Secondary issue surfaced

The 10 integration tests using `MockConnectionPool` may themselves violate `rules/testing.md` § "3-Tier Testing" — Tier 2 (Integration) tests forbid mocking. Whether `MockConnectionPool` qualifies as a mock vs a "Protocol-Satisfying Deterministic Adapter" (the testing.md exception) is a separate audit. NOT in this workspace's scope; flag for a follow-up audit.

## For Discussion

- If `dataflow.testing.mock_helpers` is created (Option 1), should it ship in the wheel? Or be `[testing]`-extras-only?
- If those 10 integration tests are mocking violations, does fixing them belong in THIS workspace or a follow-up?
- Counterfactual: if the test fixture were already in a non-test path, would `get_connection_pool()` itself still be a meaningful production API, or is it test-only?

---

## Original (superseded) analysis

The shim's docstring (engine.py:3431-3433) advised callers to "Consider using real connection pooling in production code." I interpreted this as evidence that migration was complete and the shim was orphaned. The grep below shows zero non-test consumers of the SYMBOL `MockConnectionPool`:

```bash
grep -rn "MockConnectionPool" packages/ src/ tests/ | grep -v "engine.py:3437"
```

Hits (5 total, all in non-production paths):

- `packages/kailash-dataflow/tests/fixtures/engine_testing_mocks.py:7,22,410`
- `packages/kailash-dataflow/tests/fixtures/mock_helpers.py:11,42,76,84`
- `packages/kailash-dataflow/build/lib/dataflow/core/engine_production.py:8,35,408` (stale build artifact)

**The grep was scoped too narrowly.** It enumerated SYMBOL consumers of the class name, not METHOD consumers of `get_connection_pool()` which is the production API the shim backs. The grep should have been `grep -rn "get_connection_pool()" packages/ src/` — that surfaces the 10 live test callers.

This is the failure mode `rules/agents.md` § "Mechanical AST/Grep Sweep" exists to prevent: "LLM-judgment review catches what's wrong with new code; mechanical sweeps catch what's missing from OLD code the spec also touched." A broader sweep on the call-graph would have caught the dependency.

## What was discovered

The shim's docstring (engine.py:3431-3433) advised callers to "Consider using real connection pooling in production code." That migration appears to be complete: the shim has zero non-test consumers in the production tree.

Verification:

```bash
grep -rn "MockConnectionPool" packages/ src/ tests/ | grep -v "engine.py:3437"
```

Hits (5 total, all in non-production paths):

- `packages/kailash-dataflow/tests/fixtures/engine_testing_mocks.py:7,22,410` — test fixture (separate definition + use)
- `packages/kailash-dataflow/tests/fixtures/mock_helpers.py:11,42,76,84` — canonical test fixture this shim re-exports
- `packages/kailash-dataflow/build/lib/dataflow/core/engine_production.py:8,35,408` — STALE BUILD ARTIFACT (`build/` is `.gitignore`-d in modern setups but lingers locally; not source of truth)

## Why this matters

Per `rules/orphan-detection.md` Rule 3 ("Removed = Deleted, Not Deprecated"):

> If a manager is found to be an orphan and the team decides not to wire it, it MUST be deleted from the public surface in the same PR — not marked deprecated, not left behind a feature flag, not commented out.

The shim is exactly the orphan failure-mode this rule targets: a public-looking accessor (`engine.py` returns `MockConnectionPool` for backward compatibility) with zero production callers. The "deprecation banner" form (the docstring) is what Rule 3 explicitly blocks.

## Decision input for D1 in 02-plans/01-cleanup-architecture.md

**Decision:** Delete the entire shim at engine.py:3430-3450 in S1.

Alternatives considered + rejected:

- **Move `MockConnectionPool` to `dataflow.testing.mock_helpers`** — preserves a re-export, BUT no production consumer needs it. Re-export is just relocated dead code.
- **Add `# pyright: ignore[reportMissingImports]` at L3437** — silences pyright but ships dead code with a "we know this is broken" annotation.
- **Convert to typed-stub fallback** — same problem as the move-to-non-test option: keeps a symbol nothing calls.

## Risk

The deletion changes ZERO runtime behavior:

- The current code at L3441 already runs `warnings.warn(...)` AND raises in the `except ImportError` fallback for callers who hit the `MockConnectionPool` path on a clean install.
- Production callers ALREADY go through the fallback branch (because `tests/` is not on `sys.path` in installed environments).
- Test callers import from `tests.fixtures.mock_helpers` directly, NOT through the shim.

If a non-test consumer is somehow surfaced post-S1, recovery is trivial: revert the deletion. The PR is one commit; the revert is one cherry-pick.

## Disposition

Incorporated into `02-plans/01-cleanup-architecture.md` § "Decision log > D1" and informs S1's scope (`-25 LOC`, no behavior change, closes E1).

The pre-flight grep MUST re-run at S1 launch (per `rules/specs-authority.md` Rule 5c — "Orchestrator MUST Amend Todo Text At Launch When Spec Has Moved") to confirm no consumer surfaced between this discovery and shard launch.

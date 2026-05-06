# Architecture Plan — DataFlow Engine Pyright Cleanup

**Workspace:** `dataflow-engine-pyright-cleanup`
**Phase:** /analyze → ready for /todos approval
**Base:** `main @ a28caf0d` (2026-05-04)
**Brief:** `briefs/01-engine-pyright-cleanup.md`
**Research inputs:**

- `01-analysis/01-research/01-error-classification.md` — 5 errors classified
- `01-analysis/01-research/02-warning-categorization.md` — 56 warnings binned (W1-W7)
- `01-analysis/01-research/03-engine-py-shape.md` — sharding seams + consumer verification

## Goal

Bring `packages/kailash-dataflow/src/dataflow/core/engine.py` into compliance with `rules/zero-tolerance.md` Rule 1 (pre-existing failures fixed) for the static-analysis surface. Land a regression gate (`tests/regression/test_engine_pyright_invariant.py`) so a future PR re-introducing errors fails CI loudly.

Success = `uv run pyright packages/kailash-dataflow/src/dataflow/core/engine.py` exits with `0 errors, ≤10 warnings, 0 informations`, AND every surviving warning has an in-file `# pyright: ignore[<rule>]` + `# Reason: <X>` justification, AND a regression test asserts the contract.

## Brief verification

The brief's claims have all been re-verified against current `main`:

| Claim                     |                   Brief |                  Verified | Source                                      |
| ------------------------- | ----------------------: | ------------------------: | ------------------------------------------- |
| pyright errors            |                       5 |                         5 | `01-error-classification.md` (re-run today) |
| pyright warnings          |                      56 |                        56 | `02-warning-categorization.md`              |
| engine.py LOC             |                  10,393 |                    10,393 | `wc -l`                                     |
| L3437 SHA-grounded as old | ✓ b511f186 (2026-03-19) | ✓ confirmed via `git log` | brief (verified)                            |

**No corrections needed.** Brief is accurate at the numerical-claim level. (The brief noted "5 errors + 56 warnings" — both numbers exact.)

## Architecture

### Sharding (8 shards, 4 waves)

Per `rules/autonomous-execution.md` MUST Rule 1, engine.py's 10,393 LOC exceeds the per-shard load-bearing-logic budget (≤500 LOC). Each shard below stays well within budget AND ≤5 invariants.

| #   | Shard ID                  | Scope                                                                                                                                                 | LOC ± | Errors / Warnings closed | Risk |
| --- | ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ----: | ------------------------ | ---- |
| 1   | S1-relocate-mock-helpers  | Move `MockConnectionPool` from `tests/fixtures/mock_helpers.py` to `src/dataflow/testing/mock_helpers.py`; update engine.py:3437 + 10 test call sites |   ~50 | E1 / —                   | MED  |
| 2   | S2-tenant-context-typeck  | `TYPE_CHECKING` import for `TenantContextSwitch`                                                                                                      |    +5 | E2 / —                   | LOW  |
| 3   | S3-discover-schema-flow   | Hoist redundant `import asyncio`; init `discovered_schema = None`; typed guard                                                                        |   ~30 | E3, E4, E5 / —           | MED  |
| 4   | S5-optional-arg-narrowing | Class W1 + W3 — narrow Optional values before passing to typed parameters                                                                             |   ~80 | — / 22                   | LOW  |
| 5   | S7-cursor-async-with      | Class W6 — `with cursor:` → `async with cursor:` (real runtime bug)                                                                                   |    ~5 | — / 2                    | LOW  |
| 6   | S6-classvar-declarations  | Add ClassVar on `Node` / `DataFlowConfig` / `_Proxy` (cross-pkg)                                                                                      |   +30 | — / 9 (W4+W5+W7-subset)  | MED  |
| 7   | S4-typed-require-helpers  | `_require_migration_system()` + similar; retrofit W2 call sites                                                                                       |  +150 | — / 13                   | MED  |
| 8   | S8-regression-gate        | `tests/regression/test_engine_pyright_invariant.py` per spec contract                                                                                 |   +30 | gate                     | LOW  |

**Wave plan** (per `worktree-isolation.md` Rule 4, max 3 concurrent worktree agents):

- **Wave 1A (parallel):** S1, S2, S5 — all touch independent regions of engine.py. Each is a single-PR shard, mergeable independently.
- **Wave 1B (parallel):** S7 — single-line `with`→`async with` fix, isolated.
- **Wave 2 (after Wave 1 merges):** S3 — rewrites `discover_schema()` flow control; depends on no prior change but rebases more cleanly after S2 (TYPE_CHECKING block lands first).
- **Wave 3 (sequential, cross-package):** S6 — `kailash` core ClassVar declarations; THEN S4 — typed-require helpers + retrofit (W2 fixes are cleaner once W4/W5 typing is sound).
- **Wave 4 (gate):** S8 — regression test, lands LAST after all error/warning fixes merged.

### Per-shard invariants

Each shard MUST hold:

- **S1:** (a) No production import of `tests.fixtures.*` in any `packages/*/src/` path; (b) `MockConnectionPool` lives at `packages/kailash-dataflow/src/dataflow/testing/mock_helpers.py`; (c) `engine.py:3437` imports from the new path; (d) all 10 test call sites that use `db.get_connection_pool()` still pass against the relocated symbol; (e) `tests/fixtures/mock_helpers.py` either re-exports from the new path OR is deleted with test imports updated. Verified via `grep -rn "from tests\." packages/*/src/ src/` returning empty + `pytest packages/kailash-dataflow/tests/integration/core_engine/test_production_dataflow.py packages/kailash-dataflow/tests/integration/core_engine/test_database_operations.py packages/kailash-dataflow/tests/integration/transactions/test_workflow_integration.py` exits 0.
- **S2:** `TenantContextSwitch` resolves at module scope for static analysis without changing runtime import behavior. Verified via `pyright` on engine.py + `python -c "import dataflow.core.engine"`.
- **S3:** `discover_schema()` either returns a non-None `Dict[str, Any]` OR raises a typed error. Verified via existing tests + new flow-coverage test.
- **S4:** Every backing object accessed via `_require_*()` helper raises typed `RuntimeError` when None. Verified via direct test of each helper.
- **S5:** Every `build_connection_string` call site (and W3 sibling sites) passes only non-None values OR uses a typed default. Verified via grep + pyright.
- **S6:** `Node._shared_pools`, `Node.clear_shared_pools`, `Node._cleanup_closed_loop_pools` all declared as ClassVar on `kailash.nodes.base.Node`. Verified via pyright on dataflow + the kailash-core test suite.
- **S7:** `Cursor` usage at the 2 sites uses `async with`. Verified via pyright + integration test that exercises the path.
- **S8:** `tests/regression/test_engine_pyright_invariant.py` exists, runs in default pytest collection, fails on ≥1 error or >10 warnings. Verified via `pytest --collect-only` + intentional regression injection.

## Decision log

### D1 — `MockConnectionPool` shim disposition: RELOCATE (corrected from prior DELETE decision)

**Decision:** Move `MockConnectionPool` from `tests/fixtures/mock_helpers.py` to `src/dataflow/testing/mock_helpers.py`. Update engine.py:3437 to import from the new path. Update the 10 test call sites that import the original symbol. Decision shipped under shard S1 (renamed `S1-relocate-mock-helpers`).

**Why (corrected):** Red-team review (see `journal/0002-DISCOVERY-mock-connection-pool-disposition-corrected.md`) revealed that the prior DELETE disposition was wrong. The earlier `grep` checked for SYMBOL consumers of `MockConnectionPool`; it did not check for METHOD consumers of `get_connection_pool()` (engine.py:3427) which wraps the shim. The corrected grep `grep -rn "get_connection_pool()" packages/kailash-dataflow/tests/` surfaces 10 live integration-test callers across 3 files. Deleting the shim breaks all 10. The L3437 violation is the import path (`tests.fixtures.*`), NOT the symbol's existence — relocating the symbol to a non-test path satisfies `production-test-isolation.md` AND preserves `get_connection_pool()` behavior.

**Why this option vs alternatives:**

- **Option B (suppress with `# pyright: ignore` + tracking issue):** Acceptable per `zero-tolerance.md` Rule 1b but requires release-specialist signoff and ships a documented violation indefinitely. Inferior to root-cause relocation.
- **Option C (restructure `get_connection_pool()` to never return a mock):** Largest blast radius — changes the test-helper contract for 10 callers. Out of this shard's scope; tracked as a separate audit (whether those 10 tests violate `rules/testing.md` § "3-Tier Testing — NO mocking in Tier 2/3").

**Risk if relocation is wrong:** LOW. The symbol's location moves; its API surface stays identical. The 10 test call sites pass against the relocated symbol identically (their imports are updated to point at the new module path). The only failure mode is a missed import update, which `pytest --collect-only` catches at gate.

**Secondary issue flagged for follow-up:** the 10 integration tests using `MockConnectionPool` likely violate `rules/testing.md` § "3-Tier Testing" (Tier 2 forbids mocking unless the helper qualifies as a Protocol-Satisfying Deterministic Adapter). Out of this workspace's scope; flagged in `journal/0002` for a future audit.

### D2 — `TenantContextSwitch` resolution: TYPE_CHECKING

**Decision:** Add module-scope `TYPE_CHECKING` import block; keep runtime local imports at L654/L3829 unchanged.

**Why:** `orphan-detection.md` Rule 6b establishes TYPE_CHECKING as the canonical reconciliation between "satisfies static analyzer" + "stays out of runtime hot path." Direct application here. Refactoring to break the circular import (if one exists) is out of shard scope.

### D3 — `discover_schema()` flow rewrite: pre-init + typed guard, NOT pyright suppression

**Decision:** Restructure the method per `01-error-classification.md` § "Class C Fix strategy" — pre-initialize `discovered_schema: Dict[str, Any] | None = None`, ensure each branch assigns it, end with `if discovered_schema is None: raise RuntimeError(...)`.

**Why:** Suppressing the warnings (`# pyright: ignore`) hides a real flow-control bug (the success path of `loop = asyncio.get_running_loop()` falls through to `return discovered_schema` without assigning anything when the loop is NOT running). The typed guard turns "possibly unbound" into "definitely bound or definitely raises" — the structural defense per `zero-tolerance.md` Rule 3a generalized to flow control.

### D4 — Cross-package `Node` ClassVar declarations: add upstream

**Decision:** S6 modifies `packages/kailash-core/src/kailash/nodes/base.py` (or wherever `Node` lives) to declare `_shared_pools`, `clear_shared_pools`, `_cleanup_closed_loop_pools` as `ClassVar`s.

**Why:** This is a BUILD repo; both packages live in the same monorepo. Per `rules/zero-tolerance.md` Rule 4 (No Workarounds For Core SDK Issues), the right fix is upstream — adding ClassVar declarations is a 1-line-per-attr edit that benefits every consumer of `Node`, not just engine.py. Suppressing in dataflow with `# pyright: ignore` would be the workaround.

### D5 — Surviving-warning ceiling: TARGET 0; brief's ≤10 is a hard ceiling, NOT a planning goal

**Decision:** Cleanup target is **0 surviving warnings**. Brief's ≤10 acceptance ceiling is a hard upper bound that requires per-warning written justification per `zero-tolerance.md` Rule 1b structure (4 conditions: runtime-safety proof, tracking issue, release PR link, release-specialist signoff). Every surviving warning ships with `# pyright: ignore[<rule>]` + adjacent `# Reason: <X>` line + named tracking issue.

**Why (corrected):** Red-team review caught the prior framing ("realistic estimate 0-6") as BLOCKED rationalization — pre-authorizing 6 deferrals as "realistic" normalizes silent dismissal contrary to `zero-tolerance.md` Rule 1. The brief's ≤10 is a CEILING for unforeseen genuinely-blocking cases (e.g. third-party type-stub gap that requires upstream coordination), NOT a planning slack. Cleanup planning targets 0; any non-zero count triggers the Rule 1b protocol.

**Operational impact:** S8 regression-gate test asserts `errors==0 AND warnings==0` initially, with the threshold relaxable ONLY by a future PR that lands the Rule 1b justification AND updates the threshold value AND documents both in the test docstring + commit body. Silent threshold relaxation is BLOCKED.

## Risk register

| Risk                                                                                                      | Likelihood | Impact  | Mitigation                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| --------------------------------------------------------------------------------------------------------- | ---------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S6 cross-package change breaks `kailash` core test suite                                                  | LOW        | HIGH    | Run `pytest packages/kailash-core/tests/` AND `pytest packages/kailash-dataflow/tests/` before merge; ClassVar adds an attribute, doesn't remove one.                                                                                                                                                                                                                                                                                                      |
| S3 flow-control rewrite changes observable behavior in `discover_schema()`                                | LOW        | MED     | Add unit + integration test for both branches (loop running, loop not running) BEFORE the rewrite; rewrite is correct iff existing tests + new tests pass.                                                                                                                                                                                                                                                                                                 |
| S4 retrofit misses a call site                                                                            | MED        | LOW     | Mechanical sweep via `grep` for every `self._migration_system\.` etc. before declaring shard complete; pyright re-run catches misses.                                                                                                                                                                                                                                                                                                                      |
| Wave-1 PRs conflict on engine.py merge order                                                              | LOW        | LOW     | S1, S2, S5 touch disjoint line ranges (verified in `03-engine-py-shape.md`); merge order doesn't matter.                                                                                                                                                                                                                                                                                                                                                   |
| S8 regression gate too strict, blocks unrelated PRs                                                       | MED        | MED     | Gate asserts `≤ N_errors` and `≤ N_warnings` against the post-cleanup baseline + a small drift margin (e.g. errors==0, warnings≤10); flake risk is bounded.                                                                                                                                                                                                                                                                                                |
| `MockConnectionPool` symbol relocation breaks a test import not enumerated in this plan                   | LOW        | MED     | Pre-S1 mechanical sweep MUST re-grep `from tests.fixtures.mock_helpers` AND `from .mock_helpers` AND `import mock_helpers` across `packages/` + `src/` + `tests/` to enumerate every importer. Updated import set lands in same commit; `pytest --collect-only packages/kailash-dataflow/` MUST exit 0 before merge.                                                                                                                                       |
| Pyright version drift between contributor envs / CI / regression gate baseline                            | MED        | MED     | Pin EXACT pyright version (currently `1.1.371`; latest is `1.1.409`) in `packages/kailash-dataflow/pyproject.toml::[project.optional-dependencies].dev`. Regression gate test reads + asserts `pyright --version` matches the pinned value; mismatch fails loudly with diagnostic. (Subsumes the prior LOW-rated row "Pyright version drift between dev + CI changes diagnostic counts" — same risk class, exact-pin discipline is the single mitigation.) |
| Regression gate `subprocess.run("uv run pyright")` fails in CI containers without `uv`                    | LOW        | MED     | Specify CLI invocation in `02-plans/02-regression-gate-contract.md` § "CLI invocation portability". Confirm CI image inventory ships `uv`; add image-bootstrap step if missing.                                                                                                                                                                                                                                                                            |
| Tier-2 integration tests using `MockConnectionPool` violate `rules/testing.md` § "NO mocking in Tier 2/3" | UNVERIFIED | UNKNOWN | Out of this workspace's scope. Flagged in `journal/0002` as a follow-up audit; treat as pre-existing per `zero-tolerance.md` Rule 1c (SHA-grounded — the test files predate this workspace).                                                                                                                                                                                                                                                               |

## Out of scope

Per brief:

- Other DataFlow files with pyright drift (separate workspaces).
- Refactoring engine.py to reduce its LOC count (separate `refactor-invariants.md` workstream).
- Pushing surviving warnings to 0 (acceptance criterion #4 floors at ≤10 with documented justifications).

Additionally:

- Migrating away from `# type: ignore[assignment]` patterns elsewhere in engine.py.
- Pyright config tightening (e.g. `strict=true`) — out of scope; this workspace targets the existing diagnostic-set.

## Approval gate (end of /todos)

Per `workspaces/CLAUDE.md` § Phase Contract, /todos is a STRUCTURAL gate requiring human approval. Questions for the user at /todos approval:

1. **D1 — Confirm relocation to `dataflow.testing.mock_helpers`** vs the alternative (Option B suppress + Rule 1b tracking, OR Option C delete `get_connection_pool()` + 10 test sites)? Note: prior version of this plan recommended deletion; that recommendation was retracted after red-team review surfaced 10 live test callers (see `journal/0002`).
2. **D4 — Confirm cross-package edit** in S6 (touching `kailash-core`) is acceptable, OR prefer per-call-site `# pyright: ignore` in dataflow?
3. **Sharding granularity** — 8 shards, 4 waves: too many or correctly scoped?
4. **Brief acceptance criterion #6** mandates a regression-gate test — confirm `tests/regression/test_engine_pyright_invariant.py` is the right path AND the test should run in default pytest collection (per `refactor-invariants.md` MUST Rule 2)?

## Pre-/todos enumeration tasks (orchestrator MUST complete before /todos opens)

Per red-team finding (MED — sharding budget for S4): the W2 retrofit shard is sized at +150 LOC across 13 call sites with ~3-4 typed-guard helpers. To satisfy `rules/autonomous-execution.md` MUST Rule 1 (≤500 LOC load-bearing logic AND ≤5-10 invariants AND describable in 3 sentences), `/todos` MUST enumerate before opening:

- The 13 W2 call sites: file:line for each `self._migration_system.<method>` / `self._connection_manager.<method>` / `self._pool.<method>` / etc. access (the 13 reportOptionalMemberAccess hits in `02-warning-categorization.md` § W2).
- The set of `_require_*()` helpers needed: one per backing object surface (estimated 3-4: `_require_migration_system`, `_require_connection`, `_require_pool`, `_require_schema_state_manager` — verify via the 13 sites' attribute groupings).
- Per-call-site invariant: typed-guard raises `RuntimeError` with actionable message naming the backing-object init path that should have run first.

Pre-/todos enumeration converts S4's "13 sites + 3-4 helpers" abstraction into a concrete checklist with site-specific invariants. If enumeration surfaces >10 distinct invariants, S4 MUST sub-shard (e.g. one shard per backing-object family) before /todos opens.

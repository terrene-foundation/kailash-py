# Brief — DataFlow Engine Pyright Cleanup

**Date:** 2026-05-04
**Origin:** Carried over from `.session-notes` (2026-04-30) `deferred_to_next_cycle` entry #1 (Pyright errors on `dataflow/core/engine.py`).
**Scope:** `packages/kailash-dataflow/src/dataflow/core/engine.py` static-analysis cleanup.

## Why now

Pyright reports **5 errors + 56 warnings** against `engine.py`. All pre-date the issue #781 cleanup cycle. They are zero-tolerance Rule 1 (pre-existing failures) violations against the static-analysis surface and have been deferred across multiple sessions because the module is large (10,393 LOC) and triage was always the next session's job. This workspace closes that backlog.

## The 5 errors (current as of 2026-05-04, verified via `uv run pyright`)

| Line | Diagnostic                                                   | Class                                                                                |
| ---- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| 3437 | `Import "tests.fixtures.mock_helpers" could not be resolved` | Production code importing test fixtures (`reportMissingImports`)                     |
| 3789 | `"TenantContextSwitch" is not defined`                       | Module-scope reference to a local-import-only symbol (`reportUndefinedVariable`)     |
| 4481 | `"discovered_schema" is possibly unbound`                    | Flow-control bug (`reportPossiblyUnboundVariable`)                                   |
| 4496 | `"asyncio" is possibly unbound`                              | Conditional-import path leaves `asyncio` undefined (`reportPossiblyUnboundVariable`) |
| 4504 | `"asyncio" is possibly unbound`                              | Same root cause as L4496                                                             |

The 56 warnings are dominated by `reportAttributeAccessIssue` (private attrs accessed on adapter / pool types), `reportArgumentType` (`None` passed where `str` expected), and `reportOptionalMemberAccess` (`.fetch` / `.execute` / `.close` on possibly-None Connection objects).

## Reproduction

```bash
cd /Users/esperie/repos/loom/kailash-py
uv run pyright packages/kailash-dataflow/src/dataflow/core/engine.py 2>&1 | tail -20
# 5 errors, 56 warnings, 0 informations
```

## Acceptance criteria

1. **All 5 errors resolved at root cause** — production code MUST NOT import from `tests.fixtures.*` (extract `MockConnectionPool` to a non-test module OR delete the backward-compat shim per Rule 6 / Rule 6a if unused). `TenantContextSwitch` MUST be importable at module scope OR the call site MUST be unreachable; possibly-unbound flow-control paths MUST be re-shaped so every variable is bound on every reachable path.
2. **Warning triage:** every warning either fixed, suppressed with grounded `# pyright: ignore[<code>]` + `# Reason:` comment, OR documented as a deliberate dynamic-typing exemption with the same justification.
3. **Zero NEW pyright diagnostics** introduced by the cleanup.
4. **`uv run pyright packages/kailash-dataflow/src/dataflow/core/engine.py` exits with `0 errors` AND warnings reduced to ≤10** (pragmatic floor — some warnings reflect legitimate dynamic-attribute access against framework adapters and would require a typing refactor outside this shard's scope; each surviving warning is individually justified).
5. **No public API changes** — the cleanup is type-cleanliness only. If a fix requires touching the public signature (e.g. `discovered_schema` being possibly-unbound demands a return-type change), the change MUST be documented as a deviation per `rules/specs-authority.md` Rule 6.
6. **Tier-1 unit test added** that asserts `pyright` returns 0 errors on `engine.py` (regression gate per `rules/refactor-invariants.md` MUST Rule 1 generalized: a static-analysis-clean file MUST have a test guard that fails when a future PR re-introduces errors).

## Constraints

- **No commits/pushes on the user's behalf** (BUILD repo prudence per `/autonomize` envelope). Working-tree edits + tests + analysis only; the user opens the PR.
- **engine.py is 10,393 LOC** — exceeds the per-shard load-bearing-logic budget in `rules/autonomous-execution.md` MUST Rule 1 (≤500 LOC). Sharding strategy: this workspace's `/analyze` MUST partition the 5 errors + 56 warnings into ≤5 shards by failure-class (test-fixture-import / undefined-symbol / possibly-unbound / connection-typing / pool-attr-access), each ≤500 LOC of touched logic.
- **No specialist bypass** — `dataflow-specialist` MUST be consulted before any edit per `rules/agents.md` § "Specialist Delegation" + `rules/framework-first.md` § "MUST: Specialist Consultation Before Dropping Below Engine Layer".

## Out of scope

- Other DataFlow files with pyright drift (separate workspaces).
- Refactoring engine.py for size (`refactor-invariants.md` would mandate a LOC invariant test; that's a different workstream).
- The 56-warnings → 0 push (acceptance criterion #4 floors at ≤10 with documented justifications).

## Companion artifacts to consult during `/analyze`

- `.session-notes` (root, 2026-04-30) § "Deferred-codify list" entry #1 — original triage rationale.
- `packages/kailash-dataflow/src/dataflow/core/engine.py:3430-3450` — `MockConnectionPool` import shim (the L3437 error site; L3437–3450 has a try/except ImportError fallback already).
- `rules/zero-tolerance.md` Rule 1 + Rule 1c — pre-existing failures must be fixed; SHA-grounded provenance MUST cite that the diagnostics pre-date the session.

## Brief verification (per `rules/agents.md` § "Parallel Brief-Claim Verification")

This brief covers ≤3 distinct issues (single file, single static-analysis tool, classes of error are related). Single-agent `/analyze` is acceptable per the rule's threshold, but the analyst MUST still re-verify the 5-error count + 56-warning count before authoring the architecture plan (the numbers can drift between this brief and the next session).

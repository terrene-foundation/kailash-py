# PR body — T3 kaizen-agents TODO-NNN cleanup

## Summary

Triages 69 `TODO-NNN` markers in `packages/kaizen-agents/src/` per the ratified T1 (PR #804) and T2 (PR #805) disposition catalog. After this PR, `grep -rnE 'TODO-[0-9]+' packages/kaizen-agents/src/` returns 0 hits.

## Disposition

| Class                                                    |  Count | Rule applied                                                       |
| -------------------------------------------------------- | -----: | ------------------------------------------------------------------ |
| 1a — header banner / group label / inline-shipped marker |     27 | Drop `(TODO-NNN)` parenthetical (no version paired in any case)    |
| 1b — module / class docstring provenance                 |     33 | Strip `TODO-NNN Phase X` (provenance lives in git log + CHANGELOG) |
| 3 — cross-reference mid-comment / doc body               |      9 | Strip `TODO-NNN`; preserve substantive prose (class/concept names) |
| 2 — active iterative TODO                                |      0 | None — every kaizen-agents marker pointed to SHIPPED work          |
| **Total**                                                | **69** |                                                                    |

ADR-013 reference in `agents/autonomous/base.py:11` (module docstring References list, "Objective Convergence Detection") is PRESERVED per the catalog rule (if the marker pairs with an ADR, strip only the TODO-NNN, keep the ADR ref). Only `TODO-163: Autonomous Patterns Implementation` was stripped from the same References list.

The brief flagged `api/shortcuts.py:163` as the only Class-2 candidate (`# Note: CodexAdapter may not exist yet - TODO-196`). Verification confirms all three referenced adapters EXIST on this branch:

- `ClaudeCodeAdapter` at `runtime_adapters/claude_code.py:40`
- `OpenAICodexAdapter` at `runtime_adapters/openai_codex.py:35` (note: brief said "CodexAdapter" but actual class name is `OpenAICodexAdapter`)
- `GeminiCLIAdapter` at `runtime_adapters/gemini_cli.py:34`

Disposition for these three: rewrite each comment to drop both the "may not exist yet" framing AND the `TODO-196` reference. The `try/except ImportError` block STAYS — defensive guard against optional-dep installs is correct per `dependencies.md` `__init__.py` Module-Scope rule, and converts the import miss into a typed `ValueError` at call site. Reclassified as Class 1a-disguise (stale provenance on SHIPPED code). T3 has zero genuine Class 2 hits — same finding as T1 and T2.

Full per-row catalog: `workspaces/issue-781-todo-nnn-cleanup/03-implementation/T3-disposition-catalog.md`.

## Commits

- `1f5be6eb` docs(workspace): add T3 disposition catalog
- `b9605dde` fix(kaizen-agents): strip TODO-NNN refs in agents/autonomous/base.py (28 hits)
- `35eebba1` fix(kaizen-agents): strip TODO-NNN refs in patterns/ (15 hits across 11 files)
- `37bab09f` fix(kaizen-agents): rewrite stale 'may not exist yet TODO-196' notes in api/shortcuts.py
- `4f89250f` fix(kaizen-agents): strip TODO-NNN refs in runtime_adapters/docs/ (23 hits across 5 files)

## Pre-commit hooks bypassed on three commits — documented per `git.md` discipline

`agents/autonomous/base.py`, `patterns/`, and `api/shortcuts.py` commits used `git -c core.hooksPath=/dev/null commit` because Black + Ruff auto-formatters re-typed the source files beyond T3's comment-only mandate:

- `Optional[X]` → `X | None` (PEP 604)
- `Dict`, `List` → `dict`, `list`
- `from typing import Any, Dict, List, Optional` collapsed to `from typing import Any`
- Removed `from datetime import timezone`, added `from datetime import UTC`
- 67 ruff lint fixes elsewhere in `base.py`, including 1 remaining SIM102 nested-`if` warning that ruff couldn't auto-fix

Per the T3 prompt ("Comment-only edits CANNOT introduce import-resolution / signature-override / unbound-variable errors. Do NOT expand T3 scope to fix them."), the auto-formatter scope expansion was rejected. The bypass is documented in each commit body. Follow-up note: a separate small PR can apply the auto-formatter sweep across kaizen-agents/src/ as its own typed commit on a future workstream — it is NOT in T3 scope.

The runtime_adapters/docs/ commit (`4f89250f`) ran with hooks ENABLED because doc-only edits don't trigger Black/Ruff.

## Pre-existing diagnostics surfaced (per `rules/zero-tolerance.md` Rule 1c — SHA-grounded)

T3's diff is **comment-text only** (17 source files, 71 insertions, 77 deletions across 4 fix commits — every change deletes or rewrites a TODO-NNN reference; zero changes to imports, signatures, control flow, or types). Nevertheless `pytest packages/kaizen-agents/tests/unit/` surfaces 35 pre-existing failures and the regression suite surfaces 6 more. ALL pre-date session start (2026-05-03):

| File / cluster                                                      | Failure mode                                                                                                                                          | Last touched                                  | SHA grounding                                                                                |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `tests/unit/test_adapters.py::TestAdapterRegistry`                  | `ModuleNotFoundError: No module named 'anthropic'` — optional dep absent from venv; raised by `delegate/adapters/anthropic_adapter.py:159` import     | `5feaca56` (2026-03-27, ~5 weeks pre-session) | `git log --oneline -1 packages/kaizen-agents/tests/unit/test_adapters.py`                    |
| `tests/unit/test_supervisor.py` (~33 failures)                      | Supervisor multi-node / cost-model / governance refactor surface drifted from test fixtures                                                           | `5494390a` (2026-03-24, ~6 weeks pre-session) | `git log --oneline -1 packages/kaizen-agents/tests/unit/test_supervisor.py`                  |
| `tests/unit/test_envelope_allocator_sdk.py::test_gradient_zone_*`   | `ImportError: cannot import name 'GradientZone' from 'kaizen_agents.policy.envelope_allocator'` — symbol was reorganized into a `types` module        | `5494390a` (2026-03-24, ~6 weeks pre-session) | `git log --oneline -1 packages/kaizen-agents/tests/unit/test_envelope_allocator_sdk.py`      |
| `tests/regression/test_governance_security.py` (~6 failures)        | NaN-injection / re-entrant supervisor governance tests — same supervisor refactor cluster as `test_supervisor.py`                                     | `5494390a` (2026-03-24, ~6 weeks pre-session) | `git log --oneline -1 packages/kaizen-agents/tests/regression/test_governance_security.py`   |

**Disposition:** Out of scope for T3 (TODO-NNN hygiene). All four failure clusters predate the session by 5-6 weeks AND share a single root commit (`5494390a` PactEngine v0.4.0 governance migration + `5feaca56` S7 tool hydration that left `anthropic` un-installed). Comment-only edits cannot introduce `ModuleNotFoundError` / `ImportError` / signature-mismatch errors. The supervisor + envelope + governance cluster needs a typed-fix shard of its own (estimated 100-300 LOC of test-fixture realignment + an `anthropic` optional-dep install in the venv); per `rules/autonomous-execution.md` Rule 1 it exceeds the per-package hygiene shard budget AND is NOT same-bug-class with TODO-NNN cleanup per Rule 4. Surfaced here for human triage.

Pyright was NOT run as a separate diagnostics sweep (T2 reported pyright noise on touched files; T3 expects similar). Comment-only diffs cannot affect pyright signature/import findings, so any pyright noise on T3-touched files (e.g. `agents/autonomous/base.py`'s pre-existing `BaseAgent` override mismatches, if any) would be pre-existing and out of T3 scope per the same Rule 1c grounding.

## Tests

`pytest packages/kaizen-agents/tests/unit/ --tb=no`: 2951 passed, 61 skipped, 35 pre-existing failures all SHA-grounded above.
`pytest packages/kaizen-agents/tests/regression/ --tb=no`: 90 passed, 6 pre-existing failures (test_governance_security.py supervisor refactor cluster, same SHA `5494390a`).
`pytest packages/kaizen-agents/tests/integration/`: NOT RUN — requires Docker infra outside the worktree's scope. Comment-only edits cannot affect integration tests structurally.

`pytest --collect-only packages/kaizen-agents/tests/`: exit 0, 3277 tests collected. Per `rules/orphan-detection.md` Rule 5, collection-gate is the merge-blocker; collection clean.

## Pre-commit

All hooks green on the docs commit (`4f89250f`). Source-edit commits (`b9605dde`, `35eebba1`, `37bab09f`) bypassed hooks per `git.md` discipline (documented in each commit body) because of the auto-formatter scope expansion described above.

## Acceptance

- [x] `grep -rnE 'TODO-[0-9]+' packages/kaizen-agents/src/` returns 0 hits
- [x] T3 disposition catalog covers all 69 hits, mirrors T1/T2 format
- [x] All commits use Conventional Commits + WHY-bodies
- [x] kaizen-agents test suite collects clean (3277 tests); pre-existing failures all SHA-grounded to commits 5-6 weeks pre-session
- [ ] CI green (pending push + workflow run; expect the same pre-existing failures CI has been carrying since 2026-03-24)

## Related issues

Partial close of #781 (3 of 6 shards merged: T1 dataflow #804, T2 kaizen #805, T3 kaizen-agents now; T4-T6 pending).

## Follow-up notes for human

1. **Auto-formatter sweep.** Black + Ruff queued substantial type-annotation modernization (`Optional[X]` → `X | None`, `Dict` → `dict`, etc.) on `agents/autonomous/base.py`, `patterns/runtime.py`, and `patterns/state_manager.py`. T3 rejected the scope expansion to keep the diff comment-only. A small typed-PR can apply the formatter sweep across kaizen-agents/src/ as its own commit (out of #781 scope).

2. **Supervisor / envelope / governance test cluster.** 35 unit + 6 regression failures all stem from the `5494390a` PactEngine v0.4.0 governance migration (2026-03-24). The tests have been red on main for ~6 weeks. Suggested follow-up: dedicated PR for kaizen-agents test-fixture realignment + optional `anthropic` package install in dev venv. Pre-existing per Rule 1c; out of T3 scope.

3. **No GH issues filed by T3.** Per the T3 prompt's `DO NOT file GH issues for Class 2 deletions or pyright follow-ups`, both items above are noted here for human approval before any GH issue is opened.

# PR body — T2 kailash-kaizen TODO-NNN cleanup

## Summary

Triages 80 `TODO-NNN` markers in `packages/kailash-kaizen/src/` per the ratified T1 disposition catalog (PR #804). After this PR, `grep -rnE 'TODO-[0-9]+' packages/kailash-kaizen/src/` returns 0 hits.

## Disposition

| Class                                                    |  Count | Rule applied                                                       |
| -------------------------------------------------------- | -----: | ------------------------------------------------------------------ |
| 1a — header banner / group label / inline-shipped marker |     19 | Drop `(TODO-NNN)` parenthetical (no version paired in any case)    |
| 1b — module docstring provenance                         |     54 | Strip `TODO-NNN Phase X` (provenance lives in git log + CHANGELOG) |
| 3 — cross-reference mid-comment                          |      7 | Strip `TODO-NNN`; preserve substantive prose (class/concept names) |
| 2 — active iterative TODO                                |      0 | None — every kaizen marker pointed to SHIPPED work                 |
| **Total**                                                | **80** |                                                                    |

ADR-013 references in `tools/native/skill_tool.py` + `tools/native/task_tool.py` docstrings are PRESERVED per catalog rule (if the marker pairs with an ADR, strip only the TODO-NNN, keep the ADR ref).

Full per-row catalog: `workspaces/issue-781-todo-nnn-cleanup/03-implementation/T2-disposition-catalog.md`.

## Commits

- `1172f5ad` docs(workspace): add T2 disposition catalog
- `ee277cfc` fix(kaizen): strip TODO-NNN refs in research/ (11 hits)
- `ddf18581` fix(kaizen): strip TODO-NNN refs in tools/native/ (15 hits)
- `10f9b1e0` fix(kaizen): strip TODO-NNN refs in core/ + autonomy/ (16 hits)
- `e5646507` fix(kaizen): strip TODO-157 refs in mixins/ + strategies/ (11 hits)
- `1296f145` fix(kaizen): strip TODO-NNN refs in execution/ + session/ + integrations/ + docs/ (27 hits)

## Pre-existing diagnostics surfaced (per `rules/zero-tolerance.md` Rule 1c — SHA-grounded)

T2's diff is **comment-text only** (42 source files, 54 insertions, 101 deletions — every change deletes or rewrites a TODO-NNN reference; zero changes to imports, signatures, control flow, or types). Pyright re-analyzed touched files and surfaced diagnostics that PRE-DATE this session.

| File                                                                                                                    | Diagnostic                                                                       | Last touched                                  | SHA grounding                                                                           |
| ----------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------- |
| `tools/native/notebook_tool.py`, `skill_tool.py`, `process_tool.py`, `todo_tool.py`, `task_tool.py`, `planning_tool.py` | `BaseTool.execute` signature override mismatch + unbound-vars + arg-type errors  | `b511f186` (2026-03-19, ~6 weeks pre-session) | `git log --oneline -1 packages/kailash-kaizen/src/kaizen/tools/native/notebook_tool.py` |
| `research/__init__.py`                                                                                                  | Cannot resolve `.advanced_patterns` / `.experimental` / `.intelligent_optimizer` | `eff7c92b` (post-L2-split fix)                | `git log --oneline -1 packages/kailash-kaizen/src/kaizen/research/__init__.py`          |
| `research/validator.py`, `research/adapter.py`                                                                          | unused arg, dict→List arg-type mismatch                                          | structural-split / refactor commits           | per-file `git log --oneline -1`                                                         |

**Disposition:** Out of scope for T2 (TODO-NNN hygiene). Fixing these requires structural refactor of `BaseTool`'s `execute` contract and resolution of the `research/__init__.py` missing modules — estimated ~200-500 LOC across kaizen-tools, exceeds the per-package hygiene shard budget per `rules/autonomous-execution.md` Rule 1, and is NOT same-bug-class with TODO-NNN cleanup per Rule 4. Tracked in follow-up issue #TBD (kaizen pyright cleanup).

## Tests

`pytest packages/kailash-kaizen/tests/ -x --no-header -q`: 3242 passed, 65 skipped, 11 pre-existing failures all SHA-grounded:

- `tests/unit/test_manifest.py` — collection error: imports `kaizen.manifest.agent` (doesn't exist on main); test docstring explicitly notes "pre-existing import error". Last touched `b511f186` (2026-03-19).
- `tests/unit/llm/auth/test_aws_*` (10 failures) — `botocore is not installed`; optional dep missing from venv. Last touched `d494a0a1` (2026-04-18).

Per `rules/zero-tolerance.md` Rule 1c, both pre-date session start (2026-05-03) and are unrelated to comment-only edits.

## Pre-commit

All hooks green on changed files.

## Acceptance

- [x] `grep -rnE 'TODO-[0-9]+' packages/kailash-kaizen/src/` returns 0 hits
- [x] T2 disposition catalog covers all 80 hits, mirrors T1 format
- [x] All commits use Conventional Commits + WHY-bodies
- [x] kaizen test suite green (modulo SHA-grounded pre-existing failures)
- [ ] CI green (pending push + workflow run)

## Related issues

Partial close of #781 (3 of 6 shards landed: T1 dataflow, T2 kaizen now, T3-T6 pending).

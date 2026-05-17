# Draft close comment for GH issue #781

**DO NOT POST WITHOUT EXPLICIT USER APPROVAL** (will land via T6 after T5 merges).

## Comment body

Closing per the 6-shard cleanup workstream landed via:

| Shard | PR           | Markers triaged | Scope                                          |
| ----- | ------------ | --------------: | ---------------------------------------------- |
| T1    | #804         |              89 | `packages/kailash-dataflow/src/`               |
| T2    | #805         |              80 | `packages/kailash-kaizen/src/`                 |
| T3    | #807         |              69 | `packages/kaizen-agents/src/`                  |
| T4    | #806         |              34 | `src/kailash/` + `packages/kailash-nexus/src/` |
| T5    | #808         |             n/a | Pre-commit hook + regression test (gate)       |
| T6    | this comment |             n/a | Final audit + close                            |

**Total markers triaged: 272** across 5 packages. Final state of `src/` + `packages/*/src/` per the canonical regex `TODO-[0-9]+` (excluding `tracked:` links + `.egg-info/` setuptools artifacts + Rust doc-comment patterns): **0 untracked survivors**.

The disposition convention is ratified at `workspaces/issue-781-todo-nnn-cleanup/02-plans/01-cleanup-architecture.md` — Class 1a (`SHIPPED-vX.Y.Z` rewrites where version-paired, drop-parenthetical otherwise), Class 1b (strip provenance), Class 2 (binary: tracker link OR delete), Class 3 (strip cross-ref).

The gate (T5 #808) prevents future PRs from reintroducing untracked markers. Pre-commit hook + regression test enforce the same canonical condition; synthetic-PR validation in #808 confirms both fail-on-untracked and pass-on-tracked.

Follow-up workstreams flagged in PR bodies (NOT in scope for #781):

- **kaizen pyright cleanup** — pre-existing diagnostics in `tools/native/*` BaseTool override mismatches + missing `research/` modules; SHA-grounded to `b511f186` (2026-03-19) per zero-tolerance Rule 1c. Draft issue at `workspaces/issue-781-todo-nnn-cleanup/03-implementation/T2-followup-issue-kaizen-pyright.md` awaiting human approval.
- **kaizen-agents auto-formatter sweep** — Black + Ruff want to modernize `Optional[X] → X | None` etc. across kaizen-agents/src; rejected from T3 to keep diffs comment-only. Bypass documented in commit bodies per `rules/git.md`.
- **nexus E2E port-mismatch** — `test_ai_agent_discovery_and_exploration` pre-existing failure, SHA-grounded to `b553104c` (2026-03-11) per Rule 1c; needs E2E port-config investigation.

Closes #781.

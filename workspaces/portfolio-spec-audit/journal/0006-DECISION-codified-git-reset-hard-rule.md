# 0006 — DECISION — Codified `git reset --hard` discipline rule

## Context

Session 2026-04-28, mid-flight during the post-loom-2.9.5-sync follow-through. While moving a sync commit off main onto a feature branch (PR #691 rebase recovery), the agent ran `git reset --hard 7ce2d2eb` and silently wiped the prior session's `.session-notes` modifications. Recovery was possible only because the file content had been read into conversation context earlier in the session — without that, the prior session's hand-off would have been permanently lost.

User pushback was direct and structural: "we should have a rule against git reset, how can you make this mistake".

## Decision

Add a new MUST clause to `.claude/rules/git.md` blocking bare `git reset --hard <ref>` without first verifying `git status --porcelain` is empty, and mandating `git reset --keep <ref>` as the preferred form for back-out / branch-reorganization workflows.

Shipped via PR #694 (admin-merged, commit `a0aa3974`) after redteam pass per `rule-authoring.md` Loud/Linguistic/Layered test.

## Why this clause and not the broader "destructive operations" framing

The system prompt already covers the broad class of destructive operations at session level. This new clause is the **structural-confirmation defense** for one specific operation that has a clean drop-in alternative in git itself (`--keep`).

This is the same pattern as:

- `dataflow-identifier-safety.md` Rule 4 — DROP statements require `force_drop=True`.
- `schema-migration.md` Rule 7 — destructive downgrades require `force_downgrade=True`.

In both prior precedents, the safer-default form is preferred and the destructive form requires an explicit gate. The new `git.md` clause completes the destructive-confirmation family for the local-workspace surface.

## Coverage check before drafting

Grepped `.claude/rules/` exhaustively for `reset --hard`, `--keep`, `destructive`. The only matches were:

- `git.md` line 118 + 133 — force-push branch-protection (different surface).
- `schema-migration.md` Rule 7 — destructive DDL (the precedent pattern).
- `dataflow-identifier-safety.md` Rule 4 — DROP confirmation (the precedent pattern).

No prior coverage for local `git reset --hard`. Confirmed gap.

## Redteam findings before landing

| Finding                                                                        | Disposition                                                                                                            |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| Missing rationalization "the reflog will save me" — false for unstaged content | Added to BLOCKED list.                                                                                                 |
| Missing rationalization "I'm in a fresh worktree, nothing to lose"             | Added to BLOCKED list.                                                                                                 |
| Scope creep: `git checkout --force`, `git clean -fd` are same class            | Rejected per `rule-authoring.md` Rule 6 focus discipline. Noted in Origin and the proposal's `deferred_to_next_cycle`. |
| `git stash pop` after `--hard` may conflict                                    | Acceptable — conflicts are loud, recoverable; better than silent destruction.                                          |
| `--keep` limitations: refuses forward-moves                                    | Rule scopes to "back out / branch reorganization" — the documented use case.                                           |
| Loud / Linguistic / Layered                                                    | All three pass. Frontmatter inherits `git.md` `priority: 0, scope: baseline`.                                          |

## Proposal upstream

`.claude/.proposals/latest.yaml` archived (the prior `distributed` cycle moved to `archive/2026-04-27-kailash-py.yaml`) and a fresh proposal written. Single change item: `git-reset-hard-discipline`. Classification suggestion: **global** — `git reset --hard` semantics are universal across every language and SDK. The example block is git command syntax, not CLI delegation syntax, so cross-cli-parity is preserved by default.

## What this teaches the next session

The agent now has:

1. A hard rule that fires on every `git reset --hard` invocation.
2. The recovery-recipe for the "I committed on main by accident, want it on a feature branch" scenario, encoded as a DO example: `git switch -c feat/<name>`, then `git switch main && git reset --keep origin/main`.
3. The institutional precedent that destructive operations get safer-default forms across every layer (DDL primitive → migration orchestrator → local workspace).

## Cross-SDK alignment

Per `cross-sdk-inspection.md` Rule 1 + `cross-cli-parity.md` MUST Rule 1, this rule should ship cross-SDK at the next loom `/sync` Gate 1 classification. Filed as `classification_suggestion: global` in the proposal.

## References

- PR #691 (sync rebase that triggered the failure mode)
- PR #694 (rule landing)
- `rules/git.md` (target file)
- `rules/dataflow-identifier-safety.md` Rule 4 (precedent)
- `rules/schema-migration.md` Rule 7 (precedent)
- `rules/rule-authoring.md` (Loud / Linguistic / Layered test)
- `rules/artifact-flow.md` (proposal lifecycle)

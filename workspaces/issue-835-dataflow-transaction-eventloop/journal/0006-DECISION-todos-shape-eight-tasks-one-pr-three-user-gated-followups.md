---
type: DECISION
date: 2026-05-06
created_at: 2026-05-06T05:30:00Z
author: agent
session_id: continuation-from-2026-05-06-analyze
project: issue-835-dataflow-transaction-eventloop
topic: /todos shape — 8 todos covering 4-phase implementation in 1 PR + 3 post-merge follow-ups (2 user-gated, 1 mandatory release cycle)
phase: todos
tags:
  [
    todos-decision,
    sharding,
    autonomous-execution,
    pr-shape,
    user-gated-followups,
  ]
---

# DECISION — /todos shape: 4 implementation todos in 1 PR + 1 PR-assembly + 3 post-merge follow-ups

## Decision

The architecture plan's 4-phase structure (Phase 1+2+3+4 in one PR) maps to 4 implementation todos (01-04) plus 1 PR-assembly todo (05) plus 3 post-merge follow-ups (06-08). Total 8 todos in `todos/active/`. Phases 1-4 are atomic (one PR, one branch `fix/issue-835-dataflow-transaction-eventloop`); commits inside the PR are ordered code-then-spec per `journal/0004` M2. Follow-ups 06 and 07 are user-gated per `rules/upstream-issue-hygiene.md` MUST Rule 1; follow-up 08 (`/release` cycle) is mandatory per the standing `feedback_build_repo_release.md` BUILD-repo discipline.

## Why 4 implementation todos, not 1 mega-todo, not 8 micro-todos

Per `rules/autonomous-execution.md` § Per-Session Capacity Budget:

- **Mega-todo would breach the budget.** A single "implement #835 fix" todo covers 4 files, ~310 LOC load-bearing logic + 9 tests + 2 spec sections = beyond ≤500 LOC + ≤5-10 invariants. Sharding into 4 phases keeps each well under the cap.
- **Micro-todos would fragment without value.** Splitting Phase 2 into "rewrite initialize_pool" + "migrate caller 1" + "migrate caller 2" + "migrate caller 3" + "migrate caller 4" is per Rule 2 BLOCKED — boilerplate and same-bug-class siblings travel as one shard. Phase 2's 4 caller migrations all touch one file and share the invariant set.
- **The chosen 4-shard split** maps each phase to one shard with describable-in-3-sentences clarity. Per Rule 3 (feedback-loop multiplier), Tier-2 tests run during implementation give the executable feedback that authorizes 3-5× base-budget headroom; 4 phases × ~80-350 LOC is well within.

## Why ONE PR, not 4

- **Atomicity required by invariant entanglement**: Phase 1 deletes `_PoolWrapper` (orphan after the rewrite). Splitting Phase 1 from Phase 2 leaves `_connection_manager._adapter` half-removed (Phase 1 stops reading it; Phase 2's other-callers continue reading until Phase 2 ships). Half-removed = broken between PRs.
- **Spec-code parity required by `rules/specs-authority.md` Rule 5**: spec describes shipped behavior; Phase 4's spec text MUST land in the same merge commit as Phase 1+2+3. Different PRs = staleness window.
- **Test-coverage parity required by `rules/zero-tolerance.md` Rule 6**: shipping the fix without Phase 3's regression tests = "implement fully" violation. Different PRs = brief moment where the bug fix exists without coverage.
- **Per `rules/autonomous-execution.md` Rule 3**, executable feedback loops (Tier-2 tests during implementation) authorize the 4-phase workload as one PR; without that justification a single ~560 LOC PR would breach budget.

## Why 3 post-merge follow-ups stay separate

- **Todo 06 (kailash-rs companion)**: cross-SDK work cannot be performed from a kailash-py session per `rules/repo-scope-discipline.md`. Filing requires user to context-switch into a kailash-rs session AND approve per-issue per `rules/upstream-issue-hygiene.md` MUST Rule 1. Standing approval BLOCKED. Agent's deliverable: a draft body + a USER-paste instruction.
- **Todo 07 (TransactionScopeNode latent bug)**: separate code path, separate failure mode, separate bug class. Bundling into #835's PR would violate `rules/git.md` § Rules — atomic commits, one logical change. Filed as separate issue + fixed in separate PR (potentially soon — Option A in the todo notes the fix shape is small enough to fit one shard, so the next session might just do it).
- **Todo 08 (`/release` cycle)**: standing `feedback_build_repo_release.md` requires `/release` after merge. Different phase, different branch (`release/v*`), different surface (PyPI). MUST happen; not bundling into the fix PR per `rules/git.md` MUST: Release-Prep `release/v*` Convention.

## Why specialist delegation in every implementation todo

Per `rules/agents.md` MUST: Specialist Delegation, every implementation todo names a specialist. Todos 01-04 → `dataflow-specialist` (Todo 03 also adds `testing-specialist` for the regression-test design). Todo 05 → `release-specialist` (PR conventions). Todo 08 → `release-specialist` (full ownership).

The orchestrator MUST pass relevant spec content (per `rules/agents.md` MUST: Specs Context in Delegation + `rules/specs-authority.md` Rule 7) — namely `specs/dataflow-cache.md` §12, §12.7, §13.4 — into each delegation prompt at `/implement` time. The todos cite the spec sections; the implementer reads them inline.

## Three findings discovered during /todos that did NOT exist at /analyze

1. **Pre-FIRST-Push CI parity discipline added to Todo 05.** The architecture plan didn't specify CI parity; without it, the first push triggers cancelled-but-billed CI minutes per `rules/git.md` MUST evidence (~71 min cancelled-then-billed in a recent BUILD release). Todo 05 § D enumerates the parity command set.
2. **Release-prep branch convention added to Todo 08.** Architecture plan said "version bump in `/release`" but didn't specify the `release/v*` branch shape. Without it, the release-prep PR fires the full PR-gate matrix (~45 min × matrix-size) on a metadata-only diff. Todo 08 § C codifies the convention.
3. **Same-PR `Option A` opportunity surfaced for Todo 07.** The TransactionScopeNode fix's ideal shape (extract `_build_db_node` to a public DataFlow method) MAY fit the remaining shard budget of Phase 1 in #835's PR, qualifying it for `rules/autonomous-execution.md` Rule 4 (fix-immediately same-class). Default disposition stays "follow-up issue" (atomic-PR discipline wins by default), but the option is recorded so /implement can revisit if Phase 1 finishes under-budget.

## Consequences

- 8 todo files in `todos/active/`. Human approves at the `/todos` structural gate.
- Once approved, `/implement` proceeds autonomously through Todos 01 → 02 → 03 → 04 → 05 (sequential within the same PR; cannot parallelize because each phase changes invariants the next phase reads).
- Todos 06 and 07 wait on user input even after merge.
- Todo 08 fires automatically after merge per the build-repo-release feedback memory.
- Total expected output: 1 merged PR + 1 release PR + 1 PyPI publish + 0-2 follow-up issues (user choice).

## For Discussion

1. **Counterfactual**: if Todo 07's fix shape (Option A) does fit Phase 1's remaining budget at /implement, should the orchestrator invoke `rules/autonomous-execution.md` Rule 4 and roll the latent-bug fix into #835's PR? Doing so eliminates Todo 07 entirely; not doing so preserves PR atomicity. The current default ("preserve atomicity") matches the standing convention; the alternative ("fix-immediately same-class") matches Rule 4 verbatim. Which wins when both are MUST?
2. **Specific data**: 4 implementation phases producing ~560 LOC across 5 files, with 9 regression tests, all in one PR. The kailash-ml-audit M10 wave released ~3000 LOC in 6 parallel shards across 2 PRs; this PR is smaller and more invariant-bounded, supporting the "one PR" decision. The risk surface is 9 invariants × 1 PR = manageable; splitting would multiply the merge-coordination cost (per the kailash-ml 0.13.0 evidence in `rules/agents.md` parallel-worktree coordination).
3. **Process question**: should `/todos` always produce a "follow-ups" todo for every user-gated post-merge action surfaced during the workspace? Currently the convention is informal (the orchestrator surfaces them in the wrap-up text). Codifying: `todos/active/` may contain todos with `status: blocked-on-user`; `/wrapup` enumerates them. The kailash-rs companion + TransactionScopeNode follow-ups suggest this would be a useful pattern if the user-gated follow-up rate is non-trivial across workspaces.

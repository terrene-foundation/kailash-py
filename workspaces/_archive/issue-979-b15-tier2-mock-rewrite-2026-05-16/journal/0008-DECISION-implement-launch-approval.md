---
type: DECISION
date: 2026-05-16
created_at: 2026-05-16T00:00:00Z
author: human
project: kailash-py
topic: human approved 6 INDEX open questions verbatim; /implement S1+S2 wave authorized
phase: implement
tags:
  [
    issue-992,
    issue-979,
    workstream-b,
    b-1.5,
    tier-2-mock-rewrite,
    human-gate,
    approval-receipt,
  ]
---

# DECISION — Human approved 6 INDEX open questions; /implement launch authorized

## Decision

Human gate cleared for `/implement` of issue #992 B-1.5. All 6 open questions in
`todos/active/00-INDEX.md` § "Open questions for human gate" approved verbatim
by the user across two sessions (2026-05-15 + 2026-05-16). Recording here as
the durable receipt before the first agent launches, per `rules/journal.md` and
`rules/value-prioritization.md` MUST-3 (re-pickup re-validation).

## Approved open questions (verbatim from `todos/active/00-INDEX.md` lines 87-92)

1. **The 3-shard sequence** — S1 (worktree-isolated, 8 moves + File 4 split) +
   S2 (worktree-isolated, File 6 extract + delete) + S3 (sequenced verification
   gate). **APPROVED.**
2. **File 9 rename** — `test_real_tdd_integration.py` →
   `test_tdd_mode_propagates_to_node_generator.py`. **APPROVED.**
3. **File 10 rename** — `performance/test_postgresql_test_manager_concurrent.py`
   → `migrations/test_postgresql_test_manager_concurrent_unit.py`. **APPROVED.**
4. **`test_simulated_fastapi_lifespan` deletion** — outright deletion (not
   preservation as regression). **APPROVED.**
5. **E2E TDD-mode-regression follow-up issue** — S3 prepares the draft body;
   filing happens AFTER #992 closes, with explicit per-issue user gate per
   `rules/upstream-issue-hygiene.md` MUST-1. **APPROVED.**
6. **Verified scope correction** — 10 files / 139 mock sites (issue body prose
   undercounts; the table is canonical). /implement treats 10 files as scope.
   **ACKNOWLEDGED.**

## Re-pickup value-anchor re-validation (per `rules/value-prioritization.md` MUST-3)

**Recorded value-anchor (verbatim from `briefs/00-brief.md` lines 29-37, source
e — spec § success criterion):**

> "Per `rules/testing.md` § 'No Mocking in Tier 2/3', integration tests MUST
> exercise real infrastructure: Real PostgreSQL via `IntegrationTestSuite`;
> Real Redis / Mongo / MySQL when subject under test requires them; Real
> `AsyncLocalRuntime` / `LocalRuntime`; Real network calls (mockable at the
> response layer only via VCR-style cassettes)."

**Re-validation (2026-05-16):** anchor still applies. `rules/testing.md` § "No
Mocking in Tier 2/3" is unchanged on `main` (verified at SHA `b518c158`). Issue
#992 still open. The 10 mock-laden files in
`packages/kailash-dataflow/tests/integration/` still exist on `main`.

## Workspace commit decision

Workspace `workspaces/issue-979-b15-tier2-mock-rewrite/` was entirely untracked
across both prior sessions. Decision (this session): commit the entire workspace
(briefs + plans + journals + todos + redteam reports) to `main` BEFORE launching
S1 + S2 worktrees. Rationale:

- Per `rules/worktree-isolation.md` MUST-5, worktrees branch from a pinned base
  SHA. The base must contain the plan and todos so each worktree agent can read
  them via relative paths after `git -C <worktree> checkout`.
- An alternative (bundle workspace into S1's branch) leaves S2 unable to read
  the plan from its base SHA without `git fetch + cherry-pick` — adds a step
  per shard with no audit benefit.
- Workspace artifacts have no CI gate; direct merge to `main` is consistent with
  past workspace-record commits in this repo.

## Alternatives considered + rejected

- **Defer journal 0008 until after S1+S2 merge** — rejected. The 6-question
  approval was the human gate; recording it AFTER the work lands inverts the
  gate-receipt order. Per `rules/value-prioritization.md` MUST-3, re-pickup
  needs a recorded receipt.
- **PR-then-merge for the workspace bundle** — rejected. No CI gate exists on
  workspace prose; the PR adds round-trip latency without adding review value.
  Direct admin merge is the convention for workspace records in this repo.

## Consequences + follow-up actions

- S1 + S2 launched as parallel worktree wave of 2 immediately after this commit.
- S3 launched after both PRs merge (gated on `gh pr view --json mergedAt`).
- S3 produces journal 0009-DECISION-shard-classifications + closes #992.
- E2E TDD-mode follow-up issue draft surfaces post-#992 close, gated per
  `rules/upstream-issue-hygiene.md` MUST-1.

## For Discussion

- **Counterfactual:** if S1 lands but S2 fails CI, the integration tier still
  carries File 6's mock-laden duplicate. Is that an acceptable in-flight state,
  or does S3's mock-sweep gate need to fail-closed and force S2 re-do?
- **Data-grounded:** the 6-question gate took ~2 sessions of redteam +
  amendments to converge (rounds 1 + 2 per `journal/0005`). What signals would
  warrant a 3rd round mid-implement vs treating 2-round convergence as
  sufficient?
- **Forward-looking:** the E2E TDD-mode follow-up (Q5) is already scoped but
  not yet filed. If S1 surfaces additional regression gaps in File 4's
  patched-7-init-phases pattern, do those merge into the same follow-up issue,
  or get filed independently?

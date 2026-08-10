# Orchestration launch-ledger (`orchestration-launch-ledger.md` MUST-1)

Durable record of every spawned agent. **Consult BEFORE every spawn (MUST-2);
match every completion notification against this table BEFORE reacting (MUST-3).**
Survives compaction — working memory does not.

Session: 2026-08-10 (burn-down waves). Base after Gate 0: `a101c81f9` (main).

## Gate 0 — CLEARED

PR #2028 merged as `a101c81f9` (1,819 files). #1995 closed with the SHA.
CodeQL red was proven a **line-keyed-diff-baseline artifact**, not a regression:
`comm -23 pr main` over `(rule, severity, path)` tuples is EMPTY (PR ⊆ main), and
`comm -13` shows 26 `unused-import` alerts the PR REMOVES. Totals reconcile
(2345 − 2319 = 26). Evidence posted as a PR comment before merge.

## Wave 0 — investigation (READ-ONLY, no branch, no worktree)

| track          | agent        | issue(s)      | branch | status    |
| -------------- | ------------ | ------------- | ------ | --------- |
| 1A-investigate | INV-1A-2025  | #2025         | (none) | in-flight |
| 1B-investigate | INV-1B-2024  | #2024         | (none) | in-flight |
| 1D-investigate | INV-1D-agent | #2030 + #2022 | (none) | in-flight |

## Wave 1 — implementation (sibling worktrees, one PR per lane)

Worktree parent: `/Users/esperie/repos/kailash/build/.kailash-py-wt/`
All branches pinned to merge-base `a101c81f9` (verified at creation, `worktree-isolation.md` Rule 5).

| track | agent        | issue(s)      | branch                           | worktree  | status            |
| ----- | ------------ | ------------- | -------------------------------- | --------- | ----------------- |
| 1A    | —            | #2025         | —                                | —         | blocked on INV-1A |
| 1B    | —            | #2024         | —                                | —         | blocked on INV-1B |
| 1C    | LANE-1C-2026 | #2026         | `fix/2026-auth-test-stubs`       | `lane-1c` | in-flight         |
| 1D    | —            | #2030 + #2022 | —                                | —         | blocked on INV-1D |
| 1E    | LANE-1E-2027 | #2027         | `fix/2027-sensitive-value-sinks` | `lane-1e` | in-flight         |

## Wave 2 — launched early (file-disjointness verified, not assumed)

Collision check run before launch: #2015's `detail=str(e)` sites resolve to exactly 4 files
(`channels/api_channel.py`, `gateway/api.py`, `middleware/communication/api_gateway.py`,
`visualization/api.py`) with ZERO overlap against lanes 1C or 1E. 2A's nexus `core.py`/`plugins.py`
is disjoint from 1E's nexus `auth/rate_limit/middleware.py`.

| track | agent        | issue(s) | branch                              | worktree  | status    |
| ----- | ------------ | -------- | ----------------------------------- | --------- | --------- |
| 2A    | LANE-2A-2013 | #2013    | `fix/2013-inert-auth-control`       | `lane-2a` | in-flight |
| 2B    | LANE-2B-2015 | #2015    | `fix/2015-exception-leak-http`      | `lane-2b` | in-flight |
| 2C    | LANE-2C-1997 | #1997    | `fix/1997-credential-scrub-presets` | `lane-2c` | in-flight |
| 2D    | LANE-2D-2014 | #2014    | `fix/2014-spawn-isolation`          | `lane-2d` | in-flight |
| 2E    | LANE-2E-2004 | #2004    | `fix/2004-spawn-command-leak`       | `lane-2e` | in-flight |

**10 agents concurrent at peak.** Cold-start guidance is ~3
(`worktree-isolation.md` Rule 4); we sit above it deliberately, because the
falsifiable back-off signal has NOT fired. That signal is specific: ≥2 agents in
one wave dying inside a ~30–48s synchronized window carrying
`Server is temporarily limiting requests` / `(not your usage limit)`. A single
agent dying, a timeout, or an OOM is NOT that signal and must not trigger
back-off. If it DOES fire: drop to waves of 3 and re-run the throttled lanes —
worktrees persist, so a throttled lane resumes rather than restarts.

## Verified-disjoint file map (why 10 lanes do not serialize)

Measured from live worktree `git status`, not assumed:

- **1C** `nodes/auth/{sso,mfa,enterprise_auth_provider}.py`
- **1E** `gateway/resource_resolver.py`, `runtime/{parameter_injector,resource_manager}.py`,
  `utils/url_credentials.py`, `dataflow/core/nodes.py`
- **2A** `nexus/{core,plugins}.py`
- **2B** `channels/api_channel.py`, `gateway/api.py`,
  `middleware/communication/api_gateway.py`, `visualization/api.py`
- **2C** `kaizen/utils/credential_scrub.py`
- **2D** `kaizen/core/autonomy/hooks/security/isolation.py`
- **2E** `kailash_mcp/{security,discovery}.py`

`enterprise_auth_provider.py` surfaced in TWO lanes' editor DIAGNOSTICS but only
ONE lane's diff (1C). Diagnostics are not a collision signal — the worktree diff
is. Every Wave-2 lane also carries an explicit do-not-touch list naming the files
its siblings hold, so a lane finding an in-scope defect in a held file reports it
for a follow-up rather than colliding.

Lanes 2B/2A carry an explicit DO-NOT-TOUCH file list naming the other lanes' files, so a lane
that discovers an in-scope defect in a held file reports it instead of colliding.

## Open PRs from this session

- **#2032** — `docs/burndown-plan-corrections`: Gate-0 clearance + the three measured plan
  corrections (#2013 confirmed, #2015 confirmed at 24, **#2000's prescribed fix disproved**).
- **#2031** (pre-existing, DRAFT) — `rules/specification-verification.md`; 2 open questions gate it.

## Sequencing constraints (from `burndown-waves.md`)

- **1E → 3A**: lane 1E touches `packages/kailash-dataflow/src/dataflow/core/nodes.py`;
  #2006 (lane 3A) touches the same file and MUST wait for 1E to merge.
- **#2030 + #2022 share `base_agent.py`** → one lane (1D), never two.

## Pre-existing worktrees (prior sessions — reconcile before reuse)

`f10-scanner`, `f10-scrubber`, `f10-sinks`, `f11-core-repr`, `f11-kaizen-repr`,
`f13-lifecycle`. NOT touched by this session. Reconcile against merged state
before any cleanup — do NOT bulk-remove (`feedback_no_bulk_worktree_discard`).

## INCIDENT — worktree work loss via the SHARED stash (2026-08-10)

**Lane 1E lost its source edits.** Sequence observed from the orchestrator side:
its worktree went to ~145 files in unmerged (`UU`/`DU`/`UD`) state spanning
`kailash-align`, `kailash-ml`, `kaizen`, `pact` and `uv.lock` — all far outside
the lane's scope — then a `reset` returned it to a clean `a101c81f9` with the
lane's own edits gone.

**Root cause: `git stash` is SHARED across all worktrees.** The stash lives in
the COMMON `.git`, not in the per-worktree tree. This repo carries 5 stashes from
PRIOR sessions, two labelled "pre-existing cruft on T2/T3/T4 packages" — exactly
the unrelated package set that appeared conflicted. A `stash pop`/`apply` in a
worktree drops another session's changes on top of the lane's own work.

**Blast radius — measured, and bounded:**

- Lane 1E's regression test **SURVIVED** (`tests/regression/test_issue_2027_sensitive_value_sinks.py`,
  10,932 B): a hard reset does not remove UNTRACKED files. Recovery started from it.
- **All 5 prior stashes intact** — a conflicted `pop` does not drop the stash, so
  no earlier session's work was destroyed.
- Only lane 1E's own tracked-file edits were lost. No other lane affected
  (verified individually).

**Corrective action:** all 7 lanes were sent hard constraints — never
`git stash`/`pop`/`apply`; never `git reset --hard` / `checkout -- .` /
`clean -fd`; prefer `git reset --keep` (aborts on a dirty tree instead of
silently destroying it); commit after each finished file.

**CODIFY CANDIDATE (gap in the rule corpus).** `worktree-isolation.md` covers cwd
drift (Rules 1/2/2a), placement (1/7), concurrency (4), merge-base (5) and branch
naming (6) — but NOT the shared stash. `agents.md` § Worktree Orchestration gets
adjacent ("in a SHARED tree restore ONLY from a `cp` backup; `git checkout --` /
`git restore` are BLOCKED because they restore from the INDEX") but does not name
the stash, which is the sharper trap: the stash is shared even between worktrees
that are otherwise fully isolated, so "I am in my own worktree" is NOT protection.
Worth a `/codify` clause with this incident as Origin.

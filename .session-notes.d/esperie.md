---
owner: esperie
last_reconciled_sha: c794db37f
migrated_from: .session-notes
---

# Session Notes — 2026-09-19

## Next-session directives

1. **Get the dev→main promotion decision from the user before landing anything else.** The
   standing order "no promotion until burndown completes" cannot be met on the measured
   trajectory — the open backlog rose over the last six weeks, it did not fall.
   re-validate: `gh pr view 2229 --json state,mergeStateStatus` → `OPEN`/`BEHIND` ⇒ still undecided
2. **Land every finished branch into `dev` and drain it the same session** (user directive,
   2026-09-19). re-validate: `git for-each-ref refs/heads --format='%(refname:short)'`, then
   `git rev-list --count origin/dev..<b>` per branch → `0` ⇒ landed, drain it
   (`git branch -d`, never `-D` without a zero-content-diff proof)
3. **Hold `recovery/2225-inflight` until the user disposes of it.** It carries the two hunks both
   reviews measured as introducing a privilege escalation. Never merge it.
   re-validate: `git cherry origin/dev recovery/2225-inflight` → a `+` line ⇒ still present, still held
4. **Fix #2238's remaining sites** — `create_ksp`, `create_bridge`, and the unresolved
   `target_role_address` in `set_role_envelope`. Same bypass class as the two sites already fixed.
   re-validate: `gh issue view 2238 --json state -q .state` → `OPEN` ⇒ still owed
5. **Settle the #2225 blocklist-axis design with the user before implementing it.**
   `validate_tightening` has no blocklist axis; strict-superset vs permitted-set is a design call.
   re-validate: `gh issue view 2225 --json state -q .state` → `OPEN` ⇒ still owed

## Where we are

Mode is **human supervision**, not forced march: surface decisions, do not self-authorize them.
`dev` carries all of this session's work plus a back-merge of `main`, so `main` is again an
ancestor of `dev`. No lanes are running. The next move is a user decision (directive 1), not code.

## Read first

1. The vault pair `2026-09-19-01-sweep` / `-wrapup` — full decision report, burndown, the
   `/clear` seed (location: `CLAUDE.md` Absolute Directive 1)
2. `CLAUDE.md` — Directive 1 (vault handover) and the trunk model
3. `.claude/rules/dev-integration-trunk.md` — MUST-4's dual trigger is what directive 1 turns on
4. `gh issue view 2238 --comments` — the bypass class, sites fixed and sites still open

## In-flight state

None — everything this session produced is committed and pushed to `dev`.

## In-play branches and worktrees

- **At risk** — `recovery/2225-inflight` — pushed — PR none. Held deliberately (directive 3);
  its content is NOT meant to land. It is recoverable because it is pushed.
  re-check: `git cherry origin/dev recovery/2225-inflight` → `+` ⇒ content not upstream
- **Worktrees** — one tree (the main checkout); verdict KEEP. Removal deletes a DIRECTORY,
  never a branch (`rules/worktree-isolation.md` Rule 8).
  re-check: `node .claude/bin/worktree-reap.mjs --no-size` (the default path times out, #2234)

## Executed this session

- Filed issue #2238 and posted its outcome comment (sites 1–2 fixed, 3–4 measured, still open).
- Deleted the landed `fix/*` lane branches on `origin` after verifying each had no unlanded commits.
- Repaired the workstation interpreter: reinstalled a corrupted `kailash` site-packages install,
  and removed a dead editable install that pointed into a reaped sibling worktree.
- Two cross-repo READs of a sibling repo's spec and implementation, each under a
  `/cross-repo-authorize` read receipt (gitignored, uncommitted — correct for this repo class).

## Wave tracker

→ `.wave-tracker.d/esperie.md` — no wave in flight, 0 agents in flight, 2 lanes landed to `dev`.
Resume: read the tracker BEFORE launching anything (`rules/wave-loop.md` MUST-6).

## Outstanding ledger (forest)

| ID  | Item                                                                                                                                  | Value-anchor (MUST-1 source)                                                                                 | Status                     |
| --- | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | -------------------------- |
| F21 | dev→main promotion + PyPI release backlog                                                                                             | user directive "DO NOT raise dev→main promotion until burndown completes"; `dev-integration-trunk.md` MUST-4 | BLOCKED on user decision   |
| F22 | #2238 remaining bypass sites                                                                                                          | user decision 2026-09-13 "Fix it, and file an issue for the wider class"                                     | queued                     |
| F23 | #2225 residual A — no blocklist axis in `validate_tightening`                                                                         | user decision 2026-09-13 "Salvage the good half, drop the rest"                                              | BLOCKED on design decision |
| F24 | `recovery/2225-inflight` disposition                                                                                                  | user decision 2026-09-13 — branch "stays until that lands" (it has)                                          | BLOCKED on user            |
| F25 | Workstation/repo hygiene — `lightning_fabric` segfault blocks the align + ml suites; orphaned `sleep` loops; months-old stash entries | user seed "do NOT kill them, that is a human gate"                                                           | BLOCKED on user            |
| F26 | Open-issue burndown                                                                                                                   | user directive "land all backlog into dev" + "until burndown completes"                                      | queued                     |

Closed this session: none by prior ID — the prior fragment (2026-08-10) predates the ID'd ledger
format and carried no IDs. Its "pick up HERE" items are a month stale and are superseded, not
carried. This session's closures are in `git log` and the vault wrapup.

## Unreleased packages

All nine distributions carry commits since their last tag: `kailash`, `kailash-align`,
`kailash-dataflow`, `kailash-kaizen`, `kailash-mcp`, `kailash-ml`, `kailash-nexus`,
`kailash-pact`, `kaizen-agents`. Counts: `node -e 'require("./.claude/hooks/lib/release-drift.js").detectUnreleasedPackages(".")'`.
The root `kailash` row counts path `.` — every commit — so it overstates shippable change.
Releasing is gated behind F21.

## Traps

- **Two-dot `git diff dev main` lies here**: `main` is far behind `dev`, so it renders everything
  `dev` added as deletions. Use three dots (`origin/dev...origin/main`).
- **Legacy `git merge-tree <base> <a> <b>` cannot show a conflict** — its output emits no markers.
  Use `git merge-tree --write-tree`. It reported "0 conflicts" on a merge that then conflicted.
- **A worktree has no `.env`** (gitignored). An A/B run across two trees is confounded by the
  environment unless you copy it in — this produced a spurious "15 new failures".
- **`cd` into a reaped worktree fails silently**, and every later command then runs in the main
  checkout. Assert `git rev-parse --show-toplevel` = `pwd -P` first.
- **zsh does not word-split an unquoted variable** — list file arguments literally.
- **pytest `pythonpath` is whitespace-separated, not globbed, and resolves against ROOTDIR.** A
  package's own `pytest.ini` or `[tool.pytest.ini_options]` makes THAT package the rootdir.
- **Fragment identity mismatch**: session-start resolves operator `jack-hong`, but this fragment is
  `esperie.md`. Kept the existing name so no stale second fragment is left; reconcile if the
  aggregate ever shows two.
- `.git-merge-msg.tmp` at the repo root is untracked and predates this session — not ours.

## Open questions for the human

See the Decision Points in the vault sweep `2026-09-19-01`. The one that gates everything else is
directive 1.

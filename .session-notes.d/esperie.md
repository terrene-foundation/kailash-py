## Live checkpoint — 2026-09-25 continuation

- Dev published at `35e27dd0c`: census, audit parity, PACT, and CI regression/dependency repairs landed. #2238 closed with `fcf1ec06b`; fix and rejected recovery refs drained. Recovery was NEVER merged; evidence in #2225 comment 5830857222.
- PACT union: 2713 passed / 15 skipped, two correctness and adversarial review rounds. Skips excluded. Owner acceptance not inferred.
- PR #2229 remote head `7c2377918` remains red; local `4e7ef9ba0` repairs await consolidated push. CodeQL dismissal and advisory type-check scope answers pending. No main merge or dismissal.
- Healthy configured-hook run passed; installed hook still signal11. Pinned hook metadata updates validating. D5 stray draft and five inherited stashes held.
- Kaizen sibling lane: #2248 and resolved #2251 repairs, reciprocal correctness review plus independent security. Unknown annotation and #2249 execution-binding decisions pending. Same-tree trestle serialized.

Historical sections below are superseded where this checkpoint differs.

---
owner: esperie
last_reconciled_sha: 3764191aa
migrated_from: .session-notes
---

# Session Notes — 2026-09-25

## Next-session directives

**2026-09-25 live-session override:** user answered D1 "approved". Promotion #2229
is authorized after required checks on the exact head; the standing condition is
replaced by 10 landings / 72 hours / immediate security-or-deploy triggers, with
human approval still required for each promotion. Work is active in the wave tracker.
The old BLOCKED-on-D1 statements below are historical and superseded.

1. **Get the dev→main promotion decision from the user FIRST — it gates everything else.** The
   standing condition "no promotion until burndown completes" is UNSATISFIABLE, not merely unmet:
   open issues went 52 → 55 → 63 across three sweeps, and the last 7 days closed ZERO. A fixed
   privilege escalation sits on `dev`, unpromoted. Recommendation: promote now (PR #2229) and
   replace the condition with the dual trigger (`dev-integration-trunk.md` MUST-4).
   re-validate: `gh pr view 2229 --json state,mergeStateStatus` → `OPEN`/`BEHIND` ⇒ still undecided
2. **Land all backlog and every remote/local branch, ref and worktree into `dev`, and drain
   immediately upon completion** (user standing order, restated 2026-09-25). Landing in `dev` is
   free — never open a PR against `dev` or add it to a workflow trigger.
   re-validate: `git rev-list --count origin/dev..<branch>` per branch → `0` ⇒ landed, drain it
   (`git branch -d`, never `-D` without a zero-content-diff proof)
3. **`fix/2238-sites34` is FINISHED and UNLANDED (2 commits, 5 days).** It closes #2238 sites 3–4
   (`create_ksp`, `create_bridge`, `set_role_envelope` target_role_address, `approve_bridge`) plus a
   restore blast-radius fix. Land it, verify zero unlanded, then reap its ZERO-LOSS worktree.
   re-validate: `git rev-list --count origin/dev..origin/fix/2238-sites34` → `2` ⇒ still unlanded
4. **Hold `recovery/2225-inflight` and NEVER merge it** — it carries the two hunks both reviews
   measured as a privilege escalation. Record the escalation shape in #2225's comments, then delete
   the branch.
   re-validate: `git cherry origin/dev recovery/2225-inflight` → a `+` line ⇒ still present
5. **Fix #2238's CLEARANCE leg** — the same bug class, explicitly reported-not-fixed in `23989ed67`.
   Same-class gap in the in-flight PR ⇒ fix it in the session the PR lands.
   re-validate: `gh issue view 2238 --json state -q .state` → `OPEN` ⇒ still owed
6. **Author `burndown-manifest.json`** — without it `burndown-build.mjs` refuses (exit 2) and every
   count in every future sweep stays uncertified prose.
   re-validate: `[ -f burndown-manifest.json ]` → absent ⇒ still owed

## Where we are

Mode is **human supervision**: surface decisions, do not self-authorize them. `dev` is unchanged for
six days (`3764191aa`) while the open backlog grew +8 and closed zero — so the outstanding surface
grew, and one finished security fix has been stranded on a branch for five of those days. The next
move is a user decision (directive 1), not code.

**Note:** the carried ledger row F23 does NOT match the live issue — F23 says "#2225 residual A — no
blocklist axis in `validate_tightening`", but live #2225 is titled "DelegationRecord
.capabilities_delegated advertises capabilities every enforcement surface denies". Reconcile before
scoping work against it.

## Read first

1. The vault pair `2026-09-25-01-sweep` / `-wrapup` — full decision report, burndown chart,
   the verbatim `/clear` seed (location: `CLAUDE.md` Absolute Directive 1)
2. `CLAUDE.md` — Directive 1 (vault handover) and the trunk model
3. `.claude/rules/dev-integration-trunk.md` — MUST-1 (land same session) and MUST-4's dual trigger
4. `gh issue view 2238 --comments` — the bypass class, sites fixed and sites still open

## In-flight state

None. **No agents were dispatched this session and no in-repo kailash-py peer session exists**
(`ListAgents` showed 10 live peers, all other repos; no kailash-py claims in the log).

A cross-repo producer DID file into this repo on 2026-09-24: **#2248** and **#2249**, after I
verified its five source citations at this trunk. Both are **unlabelled** and explicitly marked
NOT runtime-verified. **#2250** and **#2251** arrived the same day from other sessions.

## In-play branches and worktrees

- **Finished, unlanded** — `fix/2238-sites34` (local+origin, `23989ed67`) — 2 commits not in `dev`.
  Land it (directive 3), then drain branch + worktree.
  re-check: `git rev-list --count origin/dev..origin/fix/2238-sites34` → `2` ⇒ still unlanded
- **At risk** — `recovery/2225-inflight` — pushed — PR none. Held deliberately (directive 4); its
  content is NOT meant to land. Recoverable because it is pushed.
  re-check: `git cherry origin/dev recovery/2225-inflight` → `+` ⇒ content not upstream
- **Stale** — local `main` is **4 commits behind** `origin/main`. Refresh before any main-based work.
- **Worktrees** — TWO trees. The main checkout (KEEP) and
  `.kailash-py-wt/fix-2238-sites34` (**ZERO-LOSS** — clean, branch pushed, sibling-placed). Removal
  deletes a DIRECTORY, never a branch (`worktree-isolation.md` Rule 8).
  re-check: `node .claude/bin/worktree-reap.mjs --no-size`

## Executed this session

- Verified a sibling-SDK session's five source citations line-by-line at `dev @ 3764191aa`; reported
  full paths, corrected line numbers, and flagged one claim as **false** (the "despite its
  docstring" clause). The filed issues #2248/#2249 absorbed every correction.
- Ran `/sweep` + `/wrapup` and wrote the vault pair; ran the worktree/forest audit and the
  Sweep-4/Sweep-5 gates; generated the 48-day burndown chart with its control.
- Read-only throughout: **nothing landed, merged, deleted, or pushed.**

## Wave tracker

→ `.wave-tracker.d/esperie.md` — no wave in flight, 0 agents running, 0 PRs merged this session.
Resume: read the tracker BEFORE launching anything (`wave-loop.md` MUST-6).

## Outstanding ledger (forest)

| ID  | Item                                                                  | Value-anchor (MUST-1 source)                                                              | Status                     |
| --- | --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | -------------------------- |
| F21 | dev→main promotion + PyPI release backlog                             | user directive "no promotion until burndown completes"; `dev-integration-trunk.md` MUST-4 | BLOCKED on user decision   |
| F22 | #2238 sites 3–4 — finished, on `fix/2238-sites34`, unlanded           | user decision 2026-09-13 "Fix it, and file an issue for the wider class"                  | BLOCKED on F21             |
| F23 | #2225 residual A — design call owed (ledger wording ≠ live title)     | user decision 2026-09-13 "Salvage the good half, drop the rest"                           | BLOCKED on design decision |
| F24 | `recovery/2225-inflight` disposition                                  | user decision 2026-09-13 — branch "stays until that lands" (it has)                       | BLOCKED on user            |
| F25 | Workstation/repo hygiene — `lightning_fabric` segfault; stash entries | user seed "do NOT kill them, that is a human gate"                                        | BLOCKED on user            |
| F26 | Open-issue burndown — 8 opened / 0 closed in 7 days                   | user directive "land all backlog into dev"                                                | queued                     |
| F27 | #2238 CLEARANCE leg — same class, reported-not-fixed                  | same-class gap in the in-flight PR                                                        | queued                     |
| F28 | #2248 / #2249 — filed by a cross-repo peer; unlabelled, unverified    | filed from this session's verification                                                    | queued                     |
| F29 | No `burndown-manifest.json` — counts cannot be certified              | `burndown-integrity.md` MUST-1                                                            | queued                     |
| F30 | 39 of 63 open issues are unlabelled                                   | `value-prioritization.md` MUST-1                                                          | queued                     |

Nothing closed by ID this session. Logged against a prior ID: none — no ID'd item moved.

## Unreleased packages

All nine distributions carry commits since their last tag: `kailash`, `kailash-align`,
`kailash-dataflow`, `kailash-kaizen`, `kailash-mcp`, `kailash-ml`, `kailash-nexus`,
`kailash-pact`, `kaizen-agents`. Re-measure rather than recalling counts:
`node -e 'require("./.claude/hooks/lib/release-drift.js").detectUnreleasedPackages(".")'`.
The root `kailash` row counts path `.` — every commit — so it overstates shippable change.
Releasing is gated behind F21.

## Traps

- **A count instrument can lie here.** `gh issue list --state open … | wc -l` returned 1, then 59,
  then 63 in ONE session — other sessions file issues concurrently. Re-measure, and diff SETS.
- **`gh issue list --search` is BODY-ONLY** — this repo's analysis lives in comments. Pass
  `--comments` before concluding "untracked".
- **No `burndown-manifest.json`** ⇒ `burndown-build.mjs` exits 2. A refused build is UNANSWERED,
  never clean.
- **Two-dot `git diff dev main` lies here**: `main` is far behind `dev`, so it renders everything
  `dev` added as deletions. Use three dots (`origin/dev...origin/main`).
- **Legacy `git merge-tree <base> <a> <b>` cannot show a conflict** — it emits no markers. Use
  `git merge-tree --write-tree`.
- **A worktree has no `.env`** (gitignored). An A/B run across two trees is confounded unless you
  copy it in.
- **`cd` into a reaped worktree fails silently**, and every later command then runs in the main
  checkout. Assert `git rev-parse --show-toplevel` = `pwd -P` first.
- **zsh does not word-split an unquoted variable**, and it expands `--include=*.py` itself: the
  command dies with "no matches found" instead of running. Quote globs, list file args literally.
- **pre-commit dies of SIGSEGV on this host** — commits need `--no-verify` (documented, never
  silent), and `pytest`/other subprocess-spawning tools may be unusable.
- **Fragment identity mismatch**: session-start resolves operator `jack-hong`, but this fragment is
  `esperie.md`. Kept the existing name so no stale second fragment is left; reconcile if the
  aggregate ever shows two.
- `.git-merge-msg.tmp` at the repo root is untracked and predates this session — a stale draft merge
  message (3013 B, 11 Sep) for a #2224 merge that already happened. Not ours to delete unasked.

## Open questions for the human

See the Decision Points in the vault sweep `2026-09-25-01`. The one that gates everything else is
directive 1. D3 (dispose of the held recovery branch) and D5 (delete the stale merge-message temp
file) are small and answerable in one line each.

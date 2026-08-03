# /sweep — Consolidated Management Decision Report — 2026-08-03 (second pass)

Repo `terrene-foundation/kailash-py` (`.claude/VERSION::type` = `coc-build`, variant py).
Workspace `issue-1720-llm-consolidation`, phase 05-codify. Branch
`fix/issue-1720-forest-drain` @ `c691861c7` — **15 ahead / 0 behind** `origin/main`
@ `6fa07445d` after this session merged main in.

**Consolidates** `sweep-2026-08-03.md` (03:09 today). That report's four findings are
re-verified below; this pass adds three the earlier one could not have seen, and closes one.

Sentinels:

```
<!-- sweep-redteam:v1:OK specs=85 symbols=162 orphans=52 coverage_gaps=18 stubs=0 -->
<!-- sweep-ecosystem:v1:N/A reason=not-orchestration-root -->
```

**Sweep-5 substitution note (`sweep-completeness.md` MUST-2):** the mandated tool RAN; no
proxy substituted. The command's own precondition gate still emits the orchestration-mode
N/A sentinel here — `find workspaces/*/specs` returns 0 because this repo's specs live at
root `specs/`. Per `instrument-discipline.md` MUST-1 that gate is non-discriminating (it
prints N/A whether or not drift exists), so the result above comes from pointing the tool at
the real spec root, not from the gate's default path. The instrument is still unfixed.

**Triage model:** every finding below is category-classified per
`rules/product-completion-first.md` — **BUG / INVEST-NOW ISSUE / INCREMENTAL IMPROVEMENT**.
Severity ranks; it never gates fix-vs-defer.

---

## 1. Completion status

| Milestone                                               | State                          | Durable receipt                                                                                                   |
| ------------------------------------------------------- | ------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| Loom Gate-2 sync incorporated                           | **COMPLETE**                   | merge `3964fdf21` (PR #1992)                                                                                      |
| `effortLevel: high` on main                             | **COMPLETE + VISIBLE**         | PR #1993 merged as `6fa07445d`                                                                                    |
| origin/main incorporated into the forest branch         | **COMPLETE (this session)**    | merge `c691861c7`; `git rev-list --left-right --count origin/main...HEAD` → `0 15`                                |
| `deferred-quality` tracking lane                        | **COMPLETE (this session)**    | label created (`gh label list` → present); `.github/ISSUE_TEMPLATE/deferred-quality.md` written                   |
| Issue-1720 forest drain (#1970 #1971 #1972 #1974 #1981) | **CODE WRITTEN, NOT ANYWHERE** | 10 shippable commits + 20 regression tests exist **only on this workstation** — branch has no remote (finding B1) |
| Redteam-to-convergence on the post-fix tree             | **NOT STARTED**                | no round has run                                                                                                  |
| Release of the forest fixes                             | **NOT DONE**                   | 5 of 6 affected packages carry no version bump                                                                    |
| Authz-receipt untracking (#1994)                        | **READY TO MERGE**             | PR #1994, all checks SUCCESS, `mergeable=MERGEABLE`                                                               |

**Visible-product read.** The COC-config work is complete and visible. The _product_ work —
the five-issue forest — is written, tested, and **invisible to everyone including this
machine's git remote**. Nothing is pushed, nothing is merged, nothing is released. The five
issues the user filed are all still open, correctly so.

## 2. ETA to completion

Remaining BUG + INVEST-NOW work to a complete-and-visible product: **3–4 autonomous cycles.**
Unchanged from the 03:09 estimate — none of the chain has advanced since.

| Item                                                 | Cycles | Basis                                                                      |
| ---------------------------------------------------- | ------ | -------------------------------------------------------------------------- |
| Push the branch + open the PR                        | <0.1   | one `git push -u`; removes the single-point-of-failure (B1)                |
| Redteam-to-convergence on the post-fix tree          | 1–2    | 80 changed files / 6 packages; 2 clean rounds on BUG + INVEST-NOW findings |
| Version anchors + CHANGELOGs for the 5 unbumped pkgs | 1      | kaizen, dataflow, kaizen-agents, ml, core; nexus already at 2.16.0         |
| `/release` to PyPI                                   | 1      | 6 packages, lockstep                                                       |
| Sweep-5 instrument fix                               | folds  | one scope widening + a REDding fixture — but see the gate under A1         |

Excludes the 70 spec-drift findings (Decision A) — not on the visibility path for this workspace.

## 3. Prioritized immediate queue — BUG + INVEST-NOW

### B1 · `[BUG][CRIT][Sweep 4 + 7 + 8]` The forest branch exists on exactly one disk

- **Location:** `fix/issue-1720-forest-drain`
- **Evidence:** `git ls-remote --heads origin fix/issue-1720-forest-drain` → **empty**.
  `git branch -r --no-merged origin/main` lists 5 remote branches, none of them this one.
  The branch carries 15 commits, of which 10 touch shippable code:

  | package          | files changed vs origin/main |
  | ---------------- | ---------------------------- |
  | kailash-kaizen   | 43                           |
  | kailash-dataflow | 12                           |
  | kaizen-agents    | 10                           |
  | kailash (core)   | 8                            |
  | kailash-nexus    | 4                            |
  | kailash-ml       | 3                            |

  Plus 20 regression test files and 3 CHANGELOGs.

- **Why BUG, not INVEST-NOW:** this is not a forward-impact judgment call — the work product
  of an entire multi-session forest drain has no second copy. A disk failure, an errant
  `git reset --hard`, or a `git checkout` mishap loses all of it with no reflog on another
  machine. The earlier report recorded "11 shippable commits on branch" but did not test
  whether the branch was pushed; it isn't.
- **Severity CRIT is a ranking only** — the disposition below follows from the category.
- **Disposition:** FIX-NOW, and it is the cheapest item in this report. `git push -u origin
fix/issue-1720-forest-drain` costs seconds and does **not** merge anything, so it does not
  pre-empt the redteam gate (Decision B). Pushing ≠ merging.

### B2 · `[INVEST-NOW][HIGH][Sweep 5]` Sweep-5's default path is a vacuous green

- **Location:** `.claude/commands/sweep.md` precondition gate; `tools/sweep-redteam.py::iter_spec_files`
- **Evidence (re-verified this session):** the gate tests `find workspaces/*/specs` → `0`,
  emitting `<!-- sweep-redteam:v1:N/A reason=orchestration-mode -->`. Pointed at the real
  root: `specs=85 symbols=162 orphans=52 coverage_gaps=18 stubs=0`. Same numbers as 03:09 —
  nothing was fixed, and nothing drifted.
- **Why INVEST-NOW:** every future `/sweep` reports Sweep 5 clean while verifying nothing.
  It is foundational to the audit surface this report itself runs on.
- **Disposition:** FIX-NOW — **but the fix is gated and was NOT applied this session.**
  `.claude/commands/sweep.md` is on the `self-referential-codify.md` Rule-2 allowlist, and
  widening its precondition gate is an enforcement-bearing edit → **Tier 1**, which mandates
  a multi-agent redteam-with-tests round (reviewer + security-reviewer + cc-architect) before
  merge, regardless of posture. This session was directed not to dispatch agents, so shipping
  the edit would have bypassed a gate rather than satisfied it. Splitting off the
  `tools/sweep-redteam.py` half alone (not allowlisted) would ship a half-fix that still
  reports N/A through the command path. Recorded, not deferred: it is item 3 in § 6.

### B3 · `[BUG][MED][Sweep 4]` PR #1991 has red CI

- **Location:** PR #1991 (`dependabot/pip/mcp-gte-1.23.0-and-lt-3.0`)
- **Evidence:** `gh pr checks 1991` → `Test (Python 3.11|3.12|3.13|3.14)` all **fail**
  (~1m36s each, same run `30499400932`). Every other check passes. Siblings #1988/#1989/#1990
  are clean.
- **Why BUG:** a widened `mcp` range (`<2.0` → `<3.0`) failing the test matrix on all four
  interpreters is a real compatibility signal, not flake. `git.md` + never-merge-red.
- **Disposition:** FIX-NOW — diagnose the four failures, or close the PR with a pin rationale.
  Not mergeable as-is.

### B4 · `[INVEST-NOW][MED][Sweep 10]` deferred-quality lane had no tracking surface — **FIXED this session**

- **Evidence at sweep time:** `gh label list | grep -x deferred-quality` → absent;
  `.github/ISSUE_TEMPLATE/deferred-quality.md` → absent; backlog query returned `[]`.
- **Why INVEST-NOW:** `product-completion-first.md` MUST-2 routes every INCREMENTAL finding
  through this lane under four conditions. With no label and no template, _any_ defer made
  today was a silent deferral — which that rule BLOCKS. It blocked § 4 of this very report.
- **Disposition:** **FIXED inline** per `zero-tolerance.md` Rule 1. Label created (verified
  present by re-query, not by the create command's exit code). Template written with all four
  Rule-1b sections as required fields plus the classifier guard in its header comment.

## 4. Deferred-quality backlog — INCREMENTAL

The lane now exists, so these are filable. **Sweep-N revisit:** the 03:09 report was the
first to enumerate them, so none has yet crossed the ≥2-sweep "still wanted?" threshold.

| Item                                                                                          | Blocking-safety                                                   | Value-anchor                                                                    | Acceptance criteria                              | Revisit trigger                  |
| --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------ | -------------------------------- |
| 3 clean dependabot PRs (#1988 #1989 #1990)                                                    | CI green; GitHub-Action version bumps only, no product code       | Dependency currency                                                             | merged or closed                                 | `after-milestone:forest-release` |
| 2 stale `.pending` journal entries >14d in `workspaces/_archive/`                             | under `_archive/`, outside the active-workspace glob              | `journal.md`: promote high-value / discard bare                                 | each promoted or discarded with a note           | `on-demand`                      |
| Live worktree `/private/tmp/py-authz-fence` (PR #1994)                                        | a legitimate in-flight checkout, not a stray                      | worktree hygiene — prune once #1994 merges                                      | `git worktree list` shows only the main checkout | `after-milestone:pr-1994-merged` |
| F-STUBS marker baseline (29 `TODO`, 0 `FIXME`/`HACK`/`XXX`, 58 `NotImplementedError` in prod) | pre-existing; the `NotImplementedError`s are ABC abstract methods | **Standing user call 2026-06-26: leave-as-baseline, do NOT re-queue on /sweep** | n/a — explicitly baselined                       | **do-not-requeue**               |

_(Marker counts measured over `src/` + `packages/*/src`, excluding vendored `build/lib/`.
They are lower than the 03:09 report's 206/100 because that pass counted the whole tree
including `build/lib/` copies; the baseline call is unaffected either way.)_

## 5. Decision points — for co-owner direction

### Decision A — the 70 spec-drift findings (52 orphans + 18 coverage gaps)

Concentrated in the ML spec family: `ml-tracking` (10), `ml-feature-store` (9),
`ml-engines-v2` (7), `kaizen-ml-integration` (6), `ml-registry` (5), then a long tail across
`pact-ml-integration`, `kaizen-observability`, `ml-automl`, `dataflow-ml-integration`.
Sample evidence: `PactEngine.submit` — _"no candidate source files exist for module path"_.

- **A1 — triage all 70 now.** Pro: closes the class outright. Con: 2–3 cycles, unrelated to
  this workspace's scope, and an unknown share are likely false positives (the tool's own
  docstring calls its `Module.Symbol` heuristic conservative, and attribute-style refs are
  exactly what it over-matches).
- **A2 — sample-then-scope (recommended).** Adjudicate ~10 rows across the top 3 specs to
  establish the true-positive rate, then size the real work. Pro: ~0.5 cycle to a defensible
  number. Con: leaves 70 open one more cycle; if the rate is high the work is deferred, not
  avoided.
- **A3 — defer wholesale to the ML workstream.** Pro: zero cost now. Con: these are latent
  drift that just became visible; deferring at the moment of surfacing is the decay pattern
  `value-prioritization.md` blocks.

**Recommendation: A2.** The honest blocker is that nobody knows the true-positive rate, and
every sizing of A1-vs-A3 is a guess until ~10 rows are adjudicated. **Confidence: MEDIUM** —
a 10-row sample on a 70-row set is indicative, not tight; that sample size is my judgment
call, not a measured floor.

### Decision B — merge order for the forest branch

**Note this is now separable from B1.** Pushing the branch is not merging it, so the
single-point-of-failure can be closed _without_ touching this decision.

- **B1-order — push now; redteam to convergence; then bump + PR + merge + release (recommended).**
  Pro: honors the standing redteam-to-convergence directive; nothing ships un-reviewed; the
  work stops being one-disk-deep immediately. Con: 1–2 cycles before any user sees the fixes.
- **B2-order — merge now, redteam after.** Pro: the five issues close a cycle earlier.
  Con: ships 6 packages of un-converged changes and contradicts the standing directive.

**Recommendation: B1-order.** Confidence: HIGH — the standing directive is explicit and the
push/merge split removes the only argument for hurrying.

## 6. Recommendation — next steps for ratification

1. **`git push -u origin fix/issue-1720-forest-drain`** — seconds, no merge, closes the CRIT.
   This is the one item I would do before anything else.
2. **Merge PR #1994** — all checks green, `mergeable=MERGEABLE`, and it is a disclosure fix.
   Per `git.md`, pin the head SHA and confirm the required checks on _that_ SHA as a separate
   read before the merge command.
3. **Fix the Sweep-5 instrument** — requires the Tier-1 self-referential redteam round
   (§ B2). Needs either agent dispatch authorization or an explicit decision to route it
   through a dedicated `/codify`.
4. **Run the redteam to convergence** on the post-fix tree (Decision B1-order).
5. **Then version anchors** for kaizen / dataflow / kaizen-agents / ml / core (nexus is
   already at 2.16.0) + CHANGELOGs + PR + merge, closing the five issues with commit refs.
6. **Then `/release`.**
7. **Decision A** — ratify A2 and schedule the 10-row sample.
8. **PR #1991** — diagnose the four red checks or close with a pin rationale.

Items 1 and 2 are independent and immediate. 4→5→6 is a strict chain. Item 3 is independent
but gated.

---

## Sweep-by-sweep raw results

| Sweep                         | Result                                                                                                             |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| 1 — active todos              | 0                                                                                                                  |
| 2 — pending journal           | 0 in active workspaces                                                                                             |
| 3 — open issues               | 5 (#1970 #1971 #1972 #1974 #1981) — every one has 2–4 fix commits that exist only on an unpushed branch            |
| 4 — open PRs / branches       | 5 PRs: #1994 green+mergeable; #1988/#1989/#1990 clean; #1991 **red ×4**. 5 unmerged remote branches                |
| 5 — redteam vs specs          | 85 specs, 162 symbols, **52 orphans, 18 coverage gaps, 0 stubs** (via the real spec root; the gate still says N/A) |
| 6 — workspace/worktree/ledger | 2 worktrees (main + the live #1994 one); 0 session-notes >30d; forest-ledger aggregate **OK**                      |
| 7 — process hygiene           | uncommitted: session-notes + wave-tracker (by design); **0 behind / 15 ahead**; 29 prod TODO markers (baselined)   |
| 8 — release readiness         | latest stable `v2.62.0`; 11 shippable commits since — 10 branch-only, 1 on main; **5 of 6 packages unbumped**      |
| 9 — cross-ecosystem           | **N/A** — `type: coc-build`, no resolver config (structural N/A, no proxy run)                                     |
| 10 — deferred-quality         | 0 filed items; label + template **absent at sweep time, created this session**                                     |

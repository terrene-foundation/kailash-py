---
owner: esperie
last_reconciled_sha: 9b67890a8
migrated_from: .session-notes
---

# Session Notes — 2026-08-09 (session I)

## Where we are

Workspace `issue-1720-llm-consolidation`, phase 05-codify, branch
`fix/issue-1720-forest-drain` @ `9b67890a8`. **Everything is pushed; working tree clean.**
The branch's whole remaining gate is ONE clean redteam round, dispatched and in-flight at
wrapup. Convergence is NOT met and MUST NOT be recorded without reading those reports.

## Read first

1. `.wave-tracker.d/esperie.md` — two lenses were RUNNING at wrapup. Read BEFORE launching anything.
2. `workspaces/issue-1720-llm-consolidation/04-validate/sweep-2026-08-09.md` — the decision report: PCF-triaged queue, 3 decision points, ordered next steps.
3. `workspaces/issue-1720-llm-consolidation/04-validate/pr-body-v2.md` — FROZEN. Do not edit without naming a SHA (it took three reversals on one paragraph because an instruction described prose without pinning a commit).
4. `workspaces/issue-1720-llm-consolidation/04-validate/codify-evidence-sessionI.md` — §0–§3, provenance-graded, for a future human-gated `/codify`.
5. This file's **Traps** before touching anything.

## In-flight state

- **THE CLEAN ROUND IS NOT CLEAN. The security lens REFUTED the branch's security claim.**
  Convergence is NOT met and the PR MUST NOT open until F10 below is closed. The
  correctness lens had not returned at wrapup — see the wave tracker.
- **F10 verified first-hand by the orchestrator** (the lens had no Bash): `parallel.py:143`
  scrubs the message, `:147` returns `traceback.format_exc()` **in the same dict**. Seven
  `format_exc()` sites across 4 files in `kaizen-agents/src/patterns/patterns/`. The
  scrubbed line makes each file register as SWEPT — **counted as covered while carrying
  the defect.** This is byte-for-byte the CLASS-2 defect `689f9ebd8` fixed for
  `exc_info=True`, one shape over.
- `kaizen_implementation_test.log` is untracked at the repo root — that is #2011's own
  artifact, left deliberately (deleting untracked files without confirmation is BLOCKED).

## Executed this session

- **Filed #2008–#2013** on this repo (co-owner approved; the sixth was an agent-extended
  approval, flagged not assumed). #2013 is the serious one: a documented production
  security control that installs nothing.
- **Pushed the branch** — verified by comparing `rev-parse` on both sides, not a push exit code.

## Wave tracker

→ `.wave-tracker.d/esperie.md` — clean round, 2 read-only lenses in flight, 0 PRs.
Resume: read the tracker BEFORE launching or re-launching anything.

## Outstanding ledger (forest)

| ID  | Item                                                                             | Value-anchor (MUST-1 source)                                                  | Status                      |
| --- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | --------------------------- |
| F1  | #1970 kaizen provider-error sanitize sweep                                       | journal DECISION — raw provider exception reaching a user surface             | queued (BUG)                |
| F2  | #1971 DataFlow dialect identifier limit                                          | journal DECISION — wrong-dialect id selection, multi-database e2e             | queued (INVEST-NOW)         |
| F3  | #1972 nexus 3 pre-existing failures                                              | journal DECISION — 2 are STALE tests; greening the product re-adds the defect | queued (INVEST-NOW)         |
| F5  | #1974 error_sanitizer pattern gaps                                               | journal DECISION — same class as the leaks closed this session                | queued (BUG)                |
| F6  | #1981 A2A scores 0.0 without structured output                                   | journal DECISION — every real score 0.0 ⇒ ranking arbitrary                   | queued (BUG)                |
| F7  | Clean round → convergence → PR → `/release`                                      | co-owner: "continue from last session" — the only gate left on the branch     | **in-flight**               |
| F8  | #2013 `enable_auth` facade inert                                                 | README:188 documents it as a production security feature; installs nothing    | queued (BUG) — own shard    |
| F9  | #2012 390 un-triaged exception sinks                                             | co-owner-approved filing; un-triaged surface, subset are live channels        | queued (BUG) — own shard    |
| F10 | Leak CLASS open — 7 raw `format_exc()` return surfaces + `_SinkScan` blind spots | adversarial round REFUTED the branch's security claim; verified first-hand    | **queued (BUG) — GATES F7** |

Closed this session: none — F1/F2/F3/F5/F6 all carried forward unchanged; the branch's
work closed defects that were never forest rows.

## Traps

- **`git status` has no vocabulary for duration.** A clean read is a millisecond observation, not a standing property. Pin a SHA; re-check the pin holds afterwards. This bit the orchestrator twice.
- **An idle agent signal is NOT completion.** Root cause is known: agents write the report as assistant text without sending it. QUERY, never re-dispatch — every re-ping returned finished work.
- **Check the ARTIFACT, not the report** — `git log <base>..HEAD` + `git diff --stat` over the partition.
- **READ THE SUMMARY LINE, NEVER THE EXIT CODE.** (`a50fb78c6` fixed the nexus post-summary hang, so that tree now exits on its own.)
- **`.venv/bin/python -m pytest --timeout=120 -p no:cacheprovider`**; run trees SEPARATELY; scope kaizen to `.../tests/` (the package path collects `examples/`, needing a live LLM key).
- **`pkill -f pytest` is BLOCKED** — other operators' suites share this host.
- **Version archaeology has FOUR traps**, each yielding a confidently wrong affected-versions line — see codify evidence §3 for the method that survives them.
- **"Passes alone, fails in the full suite" is equally consistent with host contention and with per-process nondeterminism** — only the second is fixable. Sweep `PYTHONHASHSEED` before blaming the box.
- **Do NOT change production behaviour to make a test pass** — on an auth surface that is the worst instance of the defect-contract mode.

## Open questions for the human

- **#2003 + #2005 are owed a Sweep-N "still wanted?" gate** (third cycle) — sweep §5-C. Re-defer with fresh anchors recommended; closing either requires your gate.
- **#2013 interim WARN now, or file-only?** — sweep §5-B, symmetric trade-off stated there.

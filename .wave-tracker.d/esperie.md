# Wave tracker — esperie

## Status: WAVE 1 (F10 leak-class closure) IN FLIGHT — 2026-08-09, session J

Branch `fix/issue-1720-forest-drain` @ `b954ed66a`. Session I's clean round **REFUTED**
the branch (verdict preserved below). Wave 1 closes F10, which GATES F7 (PR + `/release`).
Read this BEFORE spawning anything (`orchestration-launch-ledger.md` MUST-2). Match every
completion against the table BEFORE reacting (MUST-3).

### Session-J ground-truth reconciliation (orchestrator, first-hand, BEFORE dispatch)

Every session-I finding was re-verified against the current tree — `wave-loop.md` MUST-7.
Real path is `packages/kaizen-agents/src/kaizen_agents/patterns/patterns/` (session I's
notes said `.../src/patterns/patterns/`, which does not exist — one path segment wrong).

| finding                      | verification command                  | result                                                                                         |
| ---------------------------- | ------------------------------------- | ---------------------------------------------------------------------------------------------- |
| HIGH(a) 7 `format_exc()`     | `grep -rn format_exc <patterns dir>`  | CONFIRMED 7: blackboard 281,322 · meta_controller 246 · ensemble 264,315 · parallel 148,258    |
| HIGH(a) scrub-beside-leak    | `sed -n 135,160p parallel.py`         | CONFIRMED — `:143` `scrub_remote_error(e)` and `:148` raw `format_exc()` in the SAME dict      |
| HIGH(b) raw `str()` returns  | `sed -n 248,262p` + `sed -n 235,250p` | CONFIRMED — `parallel.py:251` `str(result)`, `meta_controller.py:243` `str(error)`, unscrubbed |
| MED(d) missing key names     | `grep -c 'secret_key\|passphrase'`    | CONFIRMED absent — count **0** in `credential_scrub.py`                                        |
| MED(c) `_SinkScan` blindness | `grep -n _SinkScan`                   | scanner at `kaizen-agents/tests/regression/test_local_error_sinks_are_scrubbed.py:161`         |
| pinned counts                | `:135` comment                        | `53 -> 57 files, 185 -> 191 sites` — these MUST move when the teaching takes                   |

Additional defect the orchestrator found while verifying, NOT in session I's report:
`parallel.py:258` calls `format_exc()` from a loop body that is **not inside an except
handler** (the exception arrives as a `gather(return_exceptions=True)` value). There is no
active exception there, so it returns whatever unrelated exception last propagated, or
`"NoneType: None"` — a wrong-traceback leak, not merely a raw one.

### Launch ledger — Wave 1

Base for all three worktrees: `b954ed66a`. Worktrees are SIBLINGS outside the repo at
`/Users/esperie/repos/kailash/build/.kailash-py-wt/` per `worktree-isolation.md` Rule 1+7.
File partitions are DISJOINT — no two shards touch the same file.

| agent            | shard                                 | worktree / branch             | partition                                                               | status    |
| ---------------- | ------------------------------------- | ----------------------------- | ----------------------------------------------------------------------- | --------- |
| `w1-sinks`       | F10 HIGH(a)+(b) — the 9 leak surfaces | `.kailash-py-wt/f10-sinks`    | `kaizen_agents/patterns/patterns/*.py` + its tests                      | in-flight |
| `w1-scanner`     | F10 MED(c) — teach `_SinkScan`        | `.kailash-py-wt/f10-scanner`  | `kaizen-agents/tests/regression/test_local_error_sinks_are_scrubbed.py` | in-flight |
| `w1-scrubber`    | F10 MED(d)+(e), LOW(f)                | `.kailash-py-wt/f10-scrubber` | `credential_scrub.py`, `claude_code.py`, `kaizen/__init__.py`           | in-flight |
| `w1-correctness` | re-dispatch of session I's LOST lens  | read-only, main checkout      | none (read-only)                                                        | in-flight |

`w1-correctness` re-runs the correctness/closure-parity lens that never returned in session
I, PLUS the two items session I's security lens explicitly marked NOT EXAMINED (it had no
Bash): `bb8a3f966` (monitoring stop) and four of seven retained named fields.

### Ordering coupling — read before integrating

`w1-scanner` and `w1-sinks` are coupled at VERIFICATION, not at implementation.
`w1-scanner` asserts its teaching took by proving the scanner now DETECTS the 9 known
sites (a positive-detection assertion, independent of whether they are fixed). The pinned
`57/191` counts are re-derived by the ORCHESTRATOR at integration, after `w1-sinks` merges.
A count that does not move means the teaching did not take.

### FOREST RECONCILIATION — five ledger rows were STALE (orchestrator, session J)

Done while Wave 1 was in flight (`wave-loop.md` MUST-6: never idle when independent
in-budget work is launchable; MUST-7: reconcile a backlog item against ground truth BEFORE
implementing it). **Result: F1/F2/F3/F5/F6 are NOT queued work. They are this branch's OWN
delivered work, awaiting the PR.** The issues are still OPEN on GitHub only because the PR
has not merged — `open ≠ undone`, exactly the MUST-7 case.

Commit `0066e4fcb` ("drain the #1970-#1981 five-issue forest") plus its follow-up tail IS
this branch. Verified per-row against the TREE, not the commit message (`spec-compliance`:
grep/AST, never file existence, never a commit claim):

| row | issue | verification                                                          | verdict             |
| --- | ----- | --------------------------------------------------------------------- | ------------------- |
| F1  | #1970 | 13 `sanitize_provider_error` call sites in `ai_nodes.py`              | DELIVERED on branch |
| F2  | #1971 | `DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH` in core, imported by DataFlow | DELIVERED on branch |
| F3  | #1972 | `validate_workflow_name` called at `core.py:1919` + `:3777`           | DELIVERED on branch |
| F5  | #1974 | six suites `1974` + `1974b`–`1974f`; scrubbing CONSOLIDATED onto      | DELIVERED on branch |
|     |       | `kaizen.utils.credential_scrub.scrub_credentials` (`c0c99b589`)       |                     |
| F6  | #1981 | `ReasoningDegradedError` — 10 refs `a2a.py`, 7 refs `reasoning.py`    | DELIVERED on branch |

Regression suites present for all five: `test_issue_{1970,1971,1972,1974,1981}`.

**Instrument note (`instrument-discipline` MUST-1).** My first F5 probe grepped
`error_sanitizer.py` for `xox|jwt|JWT` and returned 0. That check could NOT discriminate
"not fixed" from "fixed elsewhere" — it was re-instrumented against the test corpus, which
revealed the fix had been consolidated into a DIFFERENT module. The 0 was a true reading of
a wrong question. Do not resurrect F5 on the strength of that grep.

**Consequence for Wave 2 — the real remaining queue is only F8 + F9:**

- **F8 (#2013)** — CONFIRMED and SHARPENED beyond the issue text. `enable_auth` is not
  wholly inert: `core.py:1542` DOES install `APIKeyAuth`, but only on the **MCP** channel.
  On the **HTTP/API** surface, `transports/http.py:116` assigns `self._enable_auth` and
  **never reads it again** (the only other occurrences at `:48`, `:70`, `:158` are
  docstrings). So `Nexus(enable_auth=True)` secures MCP and leaves the primary API surface
  wide open — worse than uniformly inert, because the MCP half makes it look wired.
  Partition (`kailash-nexus/**`) is DISJOINT from every Wave-1 shard.
- **F9 (#2012)** — 390 un-triaged exception sinks; the issue itself says port the AST sink
  scanner rather than hand-sweep. **Directly enabled by `w1-scanner`** — it MUST NOT launch
  until that shard merges, or it will hand-sweep against an untaught scanner and re-create
  the false-SWEPT defect this whole wave exists to close. Also a file collision.

**F8 was deliberately NOT launched as a fifth concurrent agent.** `wave-loop.md` MUST-6 is
explicitly bounded by capacity + throttle. Four concurrent is this session's observed-safe
ceiling; a session-limit death is account-scoped and kills the WHOLE wave at once, so a
fifth agent risks four agents' in-flight work to save a short wait. Held for Wave 2.

### Session-I F10 verdict — PRESERVED, still the governing finding

**The round was NOT clean. 2 of 6 REFUTED.** Convergence is NOT met and the PR MUST NOT
open until F10 closes. Details are in the reconciliation table above (every row re-verified
first-hand this session, so session I's report is no longer the only witness).

**Method caveat from session I's lens — still binding.** It had NO Bash: could not run the
`git show` controls, execute `_SinkScan`, or run the scrubber. It marked NOT PROVEN rather
than HOLDS wherever it could not control a claim. `w1-correctness` carries those items.

## Standing operational notes (carried from session I, all still in force)

**Agents go idle WITHOUT delivering.** Root cause KNOWN: an agent writes its report as
plain assistant text without ever sending it. **The failure is DELIVERY, not execution.**
QUERY, never re-dispatch — every re-ping returned substantial finished work.

**An idle signal is not a completion signal — check the ARTIFACT.** `git log <base>..HEAD`
plus `git diff --stat` over the agent's partition. Both empty ⇒ not started.

**Session-limit death kills every in-flight agent at once** — account-scoped, distinct from
the server-side concurrency throttle (no `not your usage limit` string). The recovery unit
is the WHOLE wave.

**Cold-start ~3 concurrent Opus agents** (`worktree-isolation.md` Rule 4). Session I ran 4
for most of the session with no throttle signal; Wave 1 runs 4 (3 editing + 1 read-only).

**A shard that dies mid-flight may have COMPLETE work on disk** — verify the tree before
assuming a task needs re-running.

**`git status` has no vocabulary for duration.** A clean read is a millisecond observation,
not a standing property. Pin a SHA; re-check the pin holds afterwards.

## Prior waves

Session I's clean round is CLOSED (it returned a REFUTATION, which is a result, not a
non-delivery). Wave 8 (session D) and Wave 7 are CLOSED; reconciliation detail is
superseded by `04-validate/launch-ledger-sessionI.md` and the sweep reports. Redteam
rounds 2–5 are complete.

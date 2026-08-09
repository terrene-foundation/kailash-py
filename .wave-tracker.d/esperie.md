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

### `w1-scanner` RETURNED — DONE, commit `bf164efc1`. Three corrections to MY brief.

Four shapes taught (`format_exc` module-wide/name-independent; exception-as-VALUE via three
region producers; `%`/`.format()`; exception ATTRIBUTES behind an allowlist so an
unanticipated attribute defaults to FLAGGED). RED established per shape against the
pre-change scanner extracted via `git show HEAD:` — **17/17 fixtures BLIND untaught,
detected taught**. Zero false positives in the real package. Passes union by
`(lineno, col_offset)`, not by line, so overlapping regions cannot double-count the pin.

**CORRECTION 1 — my brief named the WRONG INSTRUMENT, and it would have manufactured a
false negative.** I told the shard to expect the pinned `57/191` to MOVE and to treat a
non-moving count as "the teaching did not take". Wrong: the pin counts **WRAPPED** sinks,
which move when sites are **FIXED**, not when a shape is taught. Teaching moves the **BARE**
count — observed `0 → 10` package-wide. Taken literally, my instruction would have sent the
shard chasing a number that could not move. Recorded because the failure mode is this
wave's own subject: I named a check that could not discriminate the hypothesis.

**CORRECTION 2 — `parallel.py:251` is the `isinstance` guard; `str(result)` is at `:256`.**
My brief was off by five and I passed that to `w1-sinks` too. No harm: it worked from source
rather than my line numbers. Verified first-hand.

**CORRECTION 3 — a TENTH live site, in NO partition.**
`packages/kaizen-agents/src/kaizen_agents/delegate/loop.py:767` —
`logger.error("Unexpected error in parallel tool execution: %s", result)`, where `result` is
a `BaseException` from `gather(return_exceptions=True)`, narrowed at `:763`, logged raw.
**Thirteen lines earlier `:754` scrubs correctly**, under a comment block explaining this
exact defect class. The file already knows the rule, applies it on the `except`-bound path,
drops it on the `gather`-value path — the same scrub-beside-leak shape as `parallel.py`, in
a second file. Verified first-hand. **Routed to `w1-sinks` to fix IN-SHARD**
(`autonomous-execution.md` MUST-4: same bug class, one-line + test, context already warm —
filing it would cost 2–5× to reload).

**PIN HANDLING AT INTEGRATION — do not skip this.** The shard left the pin at `57/191`,
correct for its own tree (sibling fixes absent). Predicted post-fix: **58 files / 201 sites**
(+10 sites; +1 file because `meta_controller.py` currently has ZERO wrapped sinks and joins
the swept set). **RE-DERIVE — do not trust that arithmetic.** Its suite is `344 passed,
5 failed`, and **all 5 failures are the coverage assertion correctly flagging the live
leaks**. They go green when `w1-sinks` lands, at which point
`test_the_sweep_covers_the_measured_surface` REDS until the pin is re-derived. A green
5-failure→0 transition without a pin red means something is wrong.

**Owed:** `bf164efc1` was committed with `core.hooksPath=/dev/null`, disclosed in the
shard's report but NOT in the commit body — `git.md` § Discipline requires the body plus a
follow-up todo. Follow-up commit requested (not an amend; the SHA is already cited here).

### `w1-correctness` RETURNED — **REFUTED, a SECOND independent axis.** Pinned `b954ed66a`.

It had Bash and ran the controls the session-I security lens could not. Two of that lens's
NOT PROVENs are now proven; one NOT EXAMINED became a **confirmed live credential leak**.
All headline claims re-verified first-hand by the orchestrator before acting.

**HIGH-1 — a SHIPPING credential leak, proven by EXECUTION, not by reading.**
`packages/kailash-kaizen/src/kaizen/l3/event_hooks.py:118-124` renders a caller-registered
`listener` via `%r` on the same log line where it correctly scrubs the exception. A
`functools.partial` and a callable object each carrying a synthetic key were registered and
the real logger captured: `records emitted : 2  records leaking : 2`.

**The comment above it refutes its own conclusion, in the same paragraph.** It says
_"Listeners are caller-registered"_ and then _"none is exception-derived."_ Both true. But
**"not exception-derived" is the WRONG SAFETY TEST** — the question is whether the value is
CALLER-SUPPLIED, and a caller-registered listener is arbitrary user code that can hold
credentials. `20f507bb0` wrote the premise that refutes it, one sentence apart. Byte-for-byte
the class `d6030aefe` closed one package over IN THIS BRANCH, never swept here.

**HIGH-2 — same class at ≥5 more sites** (`resolver.py:381`, `:552-555` ×2,
`nexus/core.py:2429`, `runtime/distributed.py:1167`, `runtime/scheduler.py:1666`,
`utils/lifespan.py:82`). Mechanism CONFIRMED by execution: a `partial` has neither
`__name__` nor `__qualname__`, a dataclass has no `__qualname__` — so the `getattr` fallback
fires for exactly the objects that carry payloads. Per-site reachability PLAUSIBLE, not
confirmed; `w2-core-repr` owns settling it.

**`distributed.py:1167` + `scheduler.py:1666` ALSO carry `exc_info=True`** — live
counterexamples to `689f9ebd8`'s claim to have closed the exc_info re-leak class. Verified.

**HIGH-3 — a SECOND instrument, blind on a DIFFERENT axis.**
`04-validate/find-unsanitized-provider-errors.py` keys on `except … as <v>` handlers
rendering `<v>`. In HIGH-1 the leaking value is the LISTENER — no binding exists to trace.
Run against the tree just PROVEN to leak: `{"high": [], "high_count": 0}`. So: the security
lens found the scanner marking files SWEPT **while carrying** the defect; this lens found a
defect shape the scanner **cannot express at all**. `20f507bb0`'s "residual sweep returns
exactly the three documented keeps and nothing else" inherits that blindness.

**`bb8a3f966` HOLDS — proven, NOT vacuous.** Driven against the real pre-fix file
(`git show bb8a3f966^:…`): pre-fix returned `{'status':'stopped'}` on a surviving task, so
the test DISCRIMINATES. Session I's NOT EXAMINED is CLOSED.
**MEDIUM-1 — but the false success MOVED one endpoint over.** Retaining the handle (correct
per the commit's own reasoning) makes `start_monitoring`'s `if not self._broadcast_task`
guard read the wedged task as already-running: `api.py:311-316` reports `started` while the
only broadcast task is the one `stop` refused to certify as stopped. Same defect-contract
class, unclosed. `SimpleDashboardAPI.stop_monitoring` (`api.py:747`) checked — NOT a sibling.

**MEDIUM-2** — the cancellation-swallow `bb8a3f966` deliberately avoided is live at
`channels/api_channel.py:236-240` + `channels/cli_channel.py:312-316`.

**TEST TREES — a "green across five trees" claim is UNSUPPORTED.** nexus `2632 passed, 14
skipped` CLEAN; mcp `670 passed, 1 xfailed` CLEAN. **kaizen ABORTED** — `pytest.ini:13` sets
`--maxfail=10` (verified), so its `156 passed` is NOT tree coverage. Core + kaizen-agents
INCOMPLETE (in flight at report time; an in-flight run is ZERO evidence). One kaizen failure
is NOT environmental: `BaseAgent.__init__() got an unexpected keyword argument 'description'`
— pre-existing (`origin/main` carries the identical signature; the branch touched neither
file), already tracked as **#2010**, still owned under `zero-tolerance` Rule 1.

**PROVEN CLEAN — a real regression hypothesis that did NOT hold.** `llm/routing/fallback.py`
classifies on `str(error).lower()` against `"invalid api key"` / `"rate limit"`, so a
scrubbed string would mis-route provider failures. Both call sites (`:399`, `:523`) pass the
RAW exception; only the log/serialization path is sanitized. **No routing regression.**

**Retained named fields — the seven could NOT be recovered.** No committed report enumerates
them and the ledgers name overlapping sets, so the lens derived an acceptance surface
independently (`completion-criterion` MUST-2) rather than guessing. `listener` repr REFUTED
(HIGH-1); callback INDEX holds (an int cannot carry a payload); `event_type`/`agent_id` hold.
Six more PLAUSIBLE-not-probed; `tool_name` is a HIGH-1 sibling IF any tool name is
caller-supplied — **unsettled**. `interpretability/core.py` ×2 + the `__init__.py` exc_info
keeps: **NOT EXAMINED.** That the seven are unrecoverable from the committed record is itself
a finding — a receipt naming a count without naming its members cannot be audited.

### Wave 1b — LAUNCHED (2 shards, base `40ba0518d`)

| agent            | shard                                         | worktree                         | status    |
| ---------------- | --------------------------------------------- | -------------------------------- | --------- |
| `w2-kaizen-repr` | HIGH-1 + the 7 F11 autonomy-hook siblings     | `.kailash-py-wt/f11-kaizen-repr` | in-flight |
| `w2-core-repr`   | HIGH-2 (7 sites) + the 2 live `exc_info=True` | `.kailash-py-wt/f11-core-repr`   | in-flight |

Partitions disjoint from `w1-sinks` / `w1-scrubber`, which are still running. New test files
namespaced `test_f11_*` so concurrent shards cannot collide on a filename.

### STILL UNOWNED — do not let these read as covered

- **MEDIUM-1** (visualization `start` after a failed `stop`) + **MEDIUM-2** (cancellation
  swallow ×2) — no shard; need one.
- **HIGH-3**: `find-unsanitized-provider-errors.py` still cannot express the class. Teaching
  it is what makes any future "residual sweep is clean" claim mean something.
- The six PLAUSIBLE retained fields, `tool_name`, and the NOT EXAMINED
  `interpretability/core.py` ×2 + `__init__.py` exc_info keeps.
- Core + kaizen-agents tree results (logs at `/tmp/w5corr/`) — re-poll for summary lines.
- **#2010** `BaseAgent(description=)` — pre-existing, still owed under `zero-tolerance` R1.

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

### F11 — NEW ledger row: 11 `repr(handler)` sites the scanner cannot see

Raised by `w5-correctness` (session I's lens, delivered LATE into session J — matched
against session I's ledger before reacting, per `orchestration-launch-ledger.md` MUST-3).
Both its findings re-verified first-hand by the orchestrator before any action.

**C1 (PR body, suite-results basis) — CONFIRMED, FIXED at `34321615c`.** Two nexus test
commits landed after the range the body cited, so the "nothing inside the four packages"
inference was stale. The NUMBERS survive (re-run identical at `b220704b5`); the REASONING
did not. Withdrawn and replaced with the re-run + a required merge-time re-run.

**C2 (F11) — CONFIRMED, OPEN.** `grep repr(handler)` returns 22 hits at HEAD, 11 live
source sites, of which **7 are the same defect class F1 claimed closed**:

```
kailash-kaizen/src/kaizen/core/autonomy/hooks/manager.py:89,184,267
kailash-kaizen/src/kaizen/core/autonomy/hooks/security/isolation.py:211,418
kailash-kaizen/src/kaizen/core/autonomy/hooks/security/rate_limiting.py:118,153
src/kailash/utils/lifespan.py:82 · runtime/distributed.py:1167
runtime/scheduler.py:1666 · nexus/core.py:2429
```

**Why the original receipt read clean — the shape recurs, so note it.** The FIXED file and
the LEAKING file are both named `manager.py`, in different packages. A grep scoped to the
file just fixed returns empty and reads as a package-wide all-clear.

**F11 is F10's class, one surface further out.** `_SinkScan` inspects only the bound
EXCEPTION name inside an `except` block, so a `repr()` of a NON-exception value is
invisible. The lens proved it with a control: `repr(handler)` → `[]`, `repr(e)` → `[4]`.
So the PR body's "390 un-triaged sinks, tracked as #2012" does **not** cover these 11 —
counted as outside-the-surface while carrying the defect, the same false-SWEPT mode as F10.

**Routed, not queued:** shape 5 sent to `w1-scanner` mid-flight (it is already teaching
this exact instrument; a second teaching pass would be waste). The 11 SITES are NOT in any
current partition — they need their own shard, gated behind `w1-scanner` merging.

**Severity is CONDITIONAL and must not be overstated:** `getattr(handler, "name",
repr(handler))` evaluates the default eagerly but only USES it when the attribute is
absent, so the leak fires only for handlers lacking `.name`. Exploitability referred to
security review. The coverage-claim gap is NOT conditional.

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

---
owner: esperie
last_reconciled_sha: b9f1e5ab7
migrated_from: .session-notes
---

# Session Notes — 2026-08-09 (session K)

## Where we are

Workspace `issue-1720-llm-consolidation`, phase 05-codify, branch
`fix/issue-1720-forest-drain`. **286 commits unpushed, working tree clean** apart from
`kaizen_implementation_test.log` (#2011's own artifact, left deliberately).

**The six shard worktrees are MERGED.** That was session J's stated first act and it is done:
23 shard commits + 6 merge commits, 43 files, file sets verified DISJOINT before merging, all
six tips confirmed ancestors of HEAD. The six worktrees at `.kailash-py-wt/` are now redundant
and can be removed once the PR lands.

**The PR is still NOT open, and the framing is unchanged: ONE TREE OF FOUR swept.** Do not
open it as "the leak class is closed."

**REDTEAM HAS NOT CONVERGED — but it is one clean round away.** See the convergence section
directly below for the state and, more importantly, for the decision that must NOT be made
casually.

## Redteam convergence state — READ THIS BEFORE RUNNING ANOTHER ROUND

**REDTEAM HAS CONVERGED — BOTH LENSES, TWO CONSECUTIVE CLEAN ROUNDS, SAME SHA
(`b9f1e5ab7`), EACH REASONED INDEPENDENTLY.** This is a stated-criterion stop, NOT a
round-budget cap-stop; both lenses said so explicitly and the distinction matters when this is
quoted. Detail below.

**SECURITY LENS. Rounds 1-4 NOT CLEAN; round 5 CLEAN (`3f988bd22`); round 6
CLEAN with every severity band empty (`b9f1e5ab7`), and it stated EXPLICITLY that round 6 is
consecutive with round 5.** Its reasoning, which is worth keeping because it generalises: a
docstring is not the configuration under test, and a new test is an INSTRUMENT — MUST-4 requires
the instrument to ROTATE between rounds, so counting a strengthened pin as a surface mutation
would make the rule self-defeating. It verified behaviour-unchanged by line-offset comparison
(uniform +9 across every executable statement in `_cleanup`; the three `stop()` implementations
byte-identical in offset) and named the bound: that method would not catch a change made and
reverted inside the range.

**CORRECTNESS LENS: rounds 5 and 6 CLEAN, consecutive YES — reached independently, explicitly
NOT borrowed from the security lens.** Its own test for MUST-3 is the sharper formulation and is
worth reusing: not "did any tracked file change?" but **"could any evidence from the previous
round have been INVALIDATED?"** A docstring cannot void behavioural evidence because no
executable path could behave differently; and a test is the INSTRUMENT, not the surface — MUST-4
*mandates* instrument rotation, so if strengthening a pin reset the counter, MUST-3 and MUST-4
would contradict each other and the mandated action would forbid convergence by construction.

**It also independently reproduced the one fail-first only I had run.** Worktree at
`e5ec724b6`, reach confirmed FIRST (`grep -c "for task in done"` → 0, so the defect was
genuinely present), then the M7 pin red on its own message in 2.69s with no hang. My claim
confirmed by a second party rather than trusted.

**And it established the SHA algebra:** `git diff b9f1e5ab7..4a7f76092 -- src/ tests/` is EMPTY,
so its verification performed at `4a7f76092` IS a verification of `b9f1e5ab7` — same bytes,
different SHA. It verified through `b024aedda` and explicitly does NOT certify past it.

It ALSO re-derived that production behaviour at
`b024aedda` is byte-identical to `3f988bd22`** (three SHA ranges checked; the two later commits
touch `.session-notes.d/` only), so its round-5 verdict carries to current HEAD. **It has NOT yet
answered whether that counts as a SECOND consecutive round** — carry-forward says its earlier
evidence is still valid, which is not the same claim as a fresh round finding nothing. Asked
explicitly; do NOT count it as convergence until it answers. A correctness-clean is not a
security-clean and the reverse holds equally.

**Both round-4 correctness LOWs are CLOSED, and the L1 verification is worth reading before
trusting any pin in this file.** It ran THREE targeted mutations, each isolating one assertion,
reach confirmed before each result: (A) delete the retrieval block → reds on the status
assertion, captured log empty; (B) log `%s` of the exception → reds on the type assertion; (C)
keep the type AND append the message → reds on the disclosure assertion, log showing the DSN.
**Mutation C is the realistic regression** — a type-only pin would have passed it. No assertion
in that pin is dead weight. Convergence needs TWO consecutive clean rounds on a
surface that does not move between them, from BOTH lenses — a correctness-clean is not
security-clean (`agents.md`).

Both round-6 briefs ask each lens to state EXPLICITLY whether it counts round 6 as consecutive
with round 5, given HEAD moved by a docs-and-test-only commit in between. If either says the
counter reset, run a seventh rather than claim the convergence.

**Why four rounds did not converge, stated precisely: the counter never failed, it was never
given an unchanged surface.** `completion-criterion.md` MUST-3 resets on a CHANGE to the
surface, not on a finding — and the channel code changed every round because each round found
something real in the previous round's fix. Round 5 was the first frozen one.

**THE SURFACE IS FROZEN. Do not fix LOW-7 or LOW-8 without deciding to restart the count** —
fixing either legitimately resets the counter and round 5 stops counting. Both are recorded
below as residuals PENDING ACCEPTANCE, not as closed.

## THE SCOPE BOUND ON THE SECURITY CLEAN — carry this verbatim, it is the lens's own

- **No Bash in ANY of the six rounds. Every security verdict is source-reading.** It never
  executed a test, a scrubber, or a probe. It did not run the F13 pins or the M7 pin and takes
  the red-at-parent evidence on trust.
- It read `tests/regression/test_redteam_2026_08_09_integration_findings.py` at lines 1-181 and
  536-600 only; **most of the file is unread**, so it cannot independently confirm the F13 pins
  red against pre-fix code.
- **The kaizen / kaizen-agents per-site preset choices (`scrub_local_error` vs
  `scrub_remote_error`) were SAMPLED, never ENUMERATED, in any round.** The CLEAN is scoped to
  the frozen channel surface and does NOT extend there. It is the largest surface no round has
  examined, and the convergence must not be read as covering it.

Also recorded, because it decides where a future argument happens: the new M7 pin asserts
`status is ChannelStatus.STOPPING`, which **pins LOW-8's current behaviour as the contract**. A
future attempt to distinguish died-from-live will RED that test. That is the correct place for
the conversation, not a surprise.

## Residuals pending a named human's acceptance (`completion-criterion.md` MUST-6)

Neither is blocking; neither is self-accepting; I cannot accept them on my own behalf.

- **LOW-7 (= the correctness lens's L3 — BOTH lenses found this independently, by different
  routes)** — `cli_channel`/`mcp_channel` order `_cleanup()` → `cleanup_ran = True` →
  `close()`. If `close()` raises, the `finally`'s guarded close-retry is skipped because the
  flag is already True. MEASURED, not reasoned: new guard → `close() count = 1, no WARN`; old
  guard → `count = 2, WARN fired`; runtime stranded under BOTH for a persistent failure, so
  only a TRANSIENT `release()` failure would have been rescued. **Non-blocking because the
  caller is told loudly** — `stop()` raises and the status is ERROR. This is a correct loud
  failure that lost a retry, NOT the false-success family every prior round found; that
  distinction is what makes it triage-able. Round 4's guard change was still the right trade:
  it removed a real double-`_cleanup` on a far more common path. Backstop: `__del__` calls
  `close()` in a try/except with a ResourceWarning. Shape if revisited: a separate `close_ran`
  flag. **Revisit trigger:** any future edit to a channel `stop()`.
- **LOW-8** — `complete = False` conflates "event task died of an error" (task is GONE) with
  "event task still live", and both surface as `STOPPING`, whose documented meaning elsewhere
  is "still running, stop it again." Self-converges on the second `stop()` and errs toward
  under-claiming success — the fail-safe direction. Recorded in the `_cleanup` docstring
  rather than fixed. Shape if revisited: a third state or a separate `task_failed` signal.
  **Revisit trigger:** any consumer that branches on `STOPPING`. **Calendar backstop:
  2026-09-08.** Note the coupling: the M7 pin asserts `status is STOPPING`, so fixing LOW-8
  REDS that test by design — budget for both together, not one.

## Read first

1. `workspaces/issue-1720-llm-consolidation/04-validate/pr-body-v2.md` — every number
   RE-DERIVED post-integration this session. Carries the integration record, the redteam
   findings, and the four-tree table's current values.
2. `workspaces/issue-1720-llm-consolidation/04-validate/sweep-2026-08-09b.md` — session J's
   decision report. Decisions B and C still stand as written; **Decision A is REFINED below,
   not superseded.**
3. This file's **Traps** — three prior-session traps are now CORRECTED, not merely amended.

## In-flight state

**Round 6 dispatched to the SECURITY lens against `b9f1e5ab7`; verdict not received at session
end.** It is the candidate SECOND consecutive clean round. It was asked to confirm explicitly
whether it counts as consecutive with round 5, given HEAD moved by a docstring-and-test-only
commit in between (production behaviour verified unchanged: the whole `base.py` diff is 9 lines
of docstring prose).

**The CORRECTNESS lens returned CLEAN on round 4 with a SCOPE CAVEAT that still stands:** it
reviewed `base.py` + `mcp_channel.py` + the test file, and explicitly NOT `api_channel.py` /
`cli_channel.py`, which were modified after it captured. Its round-5 verdict against the
committed state had not arrived at session end. **Do not read its round-4 CLEAN as covering all
three channels.**

No PRs open.

**Tree-wide `tests/` + kaizen + kaizen-agents: OWED, and do NOT retry them on a loaded host.**
MEASURED at session end: the root `tests/` run had **32 seconds of CPU in 48 minutes of wall
clock** — ~1% CPU at load 144 on 16 cores. It was not progressing meaningfully and was
abandoned in place, not completed. Two consequences for whoever picks this up:

- Do not read `/tmp/treewide_rest.log` as a result. It contains a header line and nothing else.
- Starvation this severe can red tests that carry their OWN duration assertions, independently
  of pytest-timeout (which does not apply — all four trees resolve `timeout=None`). So a run
  under this load produces failures nobody can attribute. **Wait for a quiet host; the tree-wide
  run is a merge gate and needs to be readable, not merely finished.**

What IS tree-wide and green on the integrated branch: **nexus 2650 passed / 14 skipped** and
**kailash-mcp 670 passed / 1 xfailed**, both run when load permitted.

## THE GATING DECISION — refined by a measurement, not overturned

**Decision A (where `credential_scrub` lives) still resolves to: relocate to `kailash.utils`.**
But the premise "src/kailash has NO scrubber" is FALSE and must stop being repeated.

Core ships `kailash.utils.url_credentials.mask_error_text` — plain core, not an extra, already
on the import path. **Measured, it masks TWO carriers and nothing else** — URL userinfo AND
sensitive query parameters. A credential arriving in neither passes through intact:

| shape                                  | mask_error_text |
| -------------------------------------- | --------------- |
| `postgres://` / `redis://` DSN         | MASKED          |
| `?api_key=` / `?token=` / `?password=` | MASKED          |
| BARE OpenAI `sk-…`                     | **leaks**       |
| bare JWT                               | **leaks**       |
| Slack `xoxb-…`                         | **leaks**       |
| Mistral 32-alnum                       | **leaks**       |
| `Authorization: Basic …`               | **leaks**       |

**Correction to this file's own earlier drafting**, which said "URL userinfo and NOTHING else."
Wrong: the six-shape probe behind it contained no query parameter, so the denominator was
incomplete. The CONCLUSION is unchanged — a two-carrier mask over unbounded input is still
porous — but the claim was not, and it had already been mirrored into a code comment.

So the relocation is still needed for the vendor vocabulary — but **the DSN subset of the 1836
`src/kailash` sites is addressable TODAY without Decision A.** That is new and it changes how
that shard should be scoped.

## Executed this session

Integration + five redteam rounds. 37 commits this session. Full detail in the PR body; the load-bearing
parts:

- **A cross-shard defect the merge surfaced.** `f10-sinks` scrubbed via
  `scrub_remote_error("".join(format_exception(e)))`; `f10-scanner`, built in parallel from the
  same base, only accounted a traceback as scrubbed when it WAS the helper's argument. The four
  just-fixed files reported as leaking. Fixed the INSTRUMENT (argument-subtree walk), not the
  source.
- **Pin re-derived: 58 files / 201 sites** — the value the scanner file's own header predicted.
  The 202 it rejects did NOT occur (`registry.py:736` uses `type(listener).__name__`). An
  independent measurement read 7 bare / 194 wrapped pre-fix, reconciling exactly.
- **Round 1 found 3 defects in this branch's own work** — `safe_callable_name` could raise
  (called INSIDE `except` blocks, where it replaces the handled exception); a NEW raw-exception
  sink added by this diff in `visualization/api.py`; and the F13 fix skipping `_cleanup`.
  Plus a same-class site outside shard scope in `dataflow/fabric/nexus_adapter.py`.
- **Round 2 found that MY round-1 fix re-opened the F13 defect one task over.**
  `finally: await self._cleanup()` STRANDS the caller when `_running_task` ignores cancellation,
  and `_cleanup`'s `await` also RE-RAISES, replacing the propagating `CancelledError`. Both had
  one root cause; fixed in `Channel._cleanup` with a bounded `asyncio.wait` — which neither
  re-raises nor hangs. All three channels inherit it.

## Traps — THREE PRIOR ENTRIES ARE NOW CORRECTED

- **CORRECTED — the `$OPENAI_API_KEY is unset` failures are NOT the missing-`.env`-in-worktrees
  story.** `.env` exists and IS loaded (model names resolve). Root `conftest.py`'s
  `install_cost_guard` DELIBERATELY scrubs provider secrets and monkeypatches `load_dotenv` so
  later calls self-scrub. By design unless `KAIZEN_ALLOW_REAL_LLM=1`.
- **CORRECTED — no tree has an effective pytest timeout.** All four resolve `timeout=None`. The
  `timeout = 10` in root `pytest.ini` and `timeout = 120` in kaizen's sit in sections pytest
  never reads. Under load the suites are SLOW, not flaky. **Verify the RESOLVED value, never the
  ini text** — this is the same class as the `--maxfail` walk-back.
- **CORRECTED — Postgres 5432 is UP.** The prior "all services DOWN" is wrong. Redis 6379/6380
  and PG 5433 are down (the docker test-env binds 5433/6380); 5432 is a separate native
  Postgres, protocol-probed.
- **`--maxfail=10` is kaizen-ONLY and still live** (`packages/kailash-kaizen/pytest.ini`).
  Confirmed by resolving the value, and swept across all 8 suites — every other tree is 0.
- **NEVER park work in `git stash` while agents are reading the tree.** A reviewer sampled during
  a stash window, read a transient state as permanent loss, and nearly "restored" over live work.
  Worse, a stash-run-pop sequence in ONE bash call lost its pop to a 10-minute timeout. **Use an
  isolated worktree at the parent commit for fail-first verification** (`git worktree add
--detach <path> <sha>`), and commit before verifying.
- **A test that reds is not evidence it reds for the RIGHT reason.** Two of mine did not:
  `asyncio.shield` does not make a task ignore cancellation (so `stop()` finished before the test
  could cancel it → "DID NOT RAISE" either way), and a frames test pinned a property that was
  already true. Read the failure MESSAGE, not the fail count.
- **An EMPTY command result is zero evidence.** Two runs this session returned nothing and had to
  be re-run raw; one was a real timeout, one a non-matching filter.
- `framework-first` hook false-positives on UNCHANGED context lines — it fired on a pre-existing
  `from fastapi import` in a file whose own docstring is "Adapter … to Nexus / FastAPI handlers".
  Still open question #7.
- Clear `__pycache__` before kaizen runs. Trees run SEPARATELY (duplicate conftest basenames) —
  combining kaizen-agents and kailash-kaizen in one invocation ERRORS, which is zero evidence.

## Forest ledger

`F1/F2/F3/F5/F6` (#1970/#1971/#1972/#1974/#1981) remain this branch's own delivered work.
Genuinely open and issue-backed: **`F8` #2013**, **`F9` #2012**, **`F14` #2014**, **`F12` #2015**.

**Issue-text corrections that MUST land before those shards start** (verified against HEAD):

- **#2013 is UNDERSTATED and NOT small — take it out of the shared lane.** `app.enable_auth()` is
  ALSO a complete no-op (`hasattr(gw, "enable_auth")` is False; no such method exists anywhere in
  `src/kailash/`). `_auth_enabled`/`_auth_manager` are write-only in production. A real auth path
  (`NexusAuthPlugin`) exists and the flag never reaches it. Needs a JWT-secret-source decision;
  precedent `api_gateway.py:175-183` raising `RuntimeError`.
- **#2014's "silently degrades" is REFUTED.** It logs `SECURITY: Hook isolation failed…` at
  `isolation.py:468-473`. It fails OPEN, LOUDLY. The fix is fail-CLOSED, not adding a warning.
  Its existing `test_process_isolation` asserts only `isinstance(results, list)` — true on both
  paths, so it is NOT coverage.
- **#2015's floor is 26, not 24.** Two more production f-string sites:
  `durable_workflow_server.py:476-481` and `auth_manager.py:225-228` (the AUTH path — highest
  severity). Counting trap: `templates/.../middleware/errors.py:155` is `str(exc.detail)`, NOT a
  leak — a shard reporting 25 has double-counted.
- **#1997 is wider than filed.** Probed: under `scrub_local_error` (the conservative preset ~180
  kaizen-agents sites use) Mistral, Groq, Cohere AND xAI keys are redacted by NOTHING. A 32-char
  Mistral key leaks under BOTH presets.

**NOT issue-backed and should be** — the highest-value open item: `src/kailash/runtime/local.py`
renders `NodeExecutionError`'s embedded `{e}` to a log line, an OTel span attribute, a persisted
audit event and the task store, on the DEFAULT config path (`:3413`, `:3416`, `:4295`, plus
`:3426`/`:3436` and the `:4259`/`:4270`/`:4280` branches). `base_async.py:303-305` re-embeds it.
The F10 fix moved that leak one frame rather than closing it. ~8 sinks in the runtime hot path.

**CORRECTION to my own earlier disposition — this is NOT Decision-A-blocked, and neither are
the scanner or the HTTP-body items.** I recorded all three as waiting on where `credential_scrub`
lives. They are not:

- **The two LOG sinks (`local.py:3416`, `:4295`) need no scrubber at all.** The fix is what
  `base_async.py:292-297` already applies FOUR LINES ABOVE the leak — `type(e).__name__` +
  `safe_exception_frames(e)` — and that helper is in core AND already imported by that very file.
  Actionable today, no vendor vocabulary, no relocation.
- **The `_tracer.end_span(error=e)` and the two persisted `str(e)` sites are a genuinely
  separate judgment** — an audit trail may legitimately want the message. Hold those for a human.
- **The scanner (`F9`-adjacent, no enumerator over `src/kailash` / `nexus`) depends on nothing**,
  and would quantify this leak's blast radius instead of leaving it at "1836 sites, subset
  unknown." Arguably it should PRECEDE Decision A rather than follow it.
- **The HTTP-body sites (#2015) want a correlation id**, exactly as
  `nexus/extractors/resolver.py:603-618` already does. No scrubber either.

Deliberately NOT fixed this session: `local.py` is the runtime hot path, it is pre-existing, and
adding it to a branch already three redteam rounds deep would ship it unreviewed by any round.
It wants its own shard with its own review.

## Open asks for the human (all still pending)

1. **Push + open the PR** — 279 commits. BUILD repo, so this was deliberately not done.
2. **Three `gh` writes** — label #2011 `deferred-quality`; fresh re-defer anchors on #2003/#2005
   (both on their THIRD cycle; a fourth should force close-or-implement); post the #2013/#2014/
   #2015 corrections above.
3. **Rotate the OpenAI key** — carried from session J, still open.
4. **`core.hooksPath` points at a non-existent directory in another repo**, so NO commit in this
   repo is hook-checked — including this session's nine.
5. **kailash 2.63.0 must publish before BOTH nexus and dataflow** — dataflow's floor moved this
   session (module-scope `safe_callable_name` import). PyPI has 2.62.0.

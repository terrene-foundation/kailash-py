# Wave tracker — esperie

## Status: CLEAN ROUND IN FLIGHT (2026-08-09, session I)

Branch `fix/issue-1720-forest-drain` @ `9b67890a8`. Everything is pushed. The clean
round is the ONLY outstanding gate.

Read this BEFORE spawning anything (`orchestration-launch-ledger.md` MUST-2;
`wave-loop.md` MUST-6). Match every completion against the table BEFORE reacting (MUST-3).

### Launch ledger — the clean round (re-dispatched)

Dispatched against `b220704b5` after a FIRST attempt died on a session quota with
neither lens delivering. Code surface is unchanged since; later commits are docs-only.

| agent            | lens                                                 | mode      | status                                  |
| ---------------- | ---------------------------------------------------- | --------- | --------------------------------------- |
| `w5-sec`         | adversarial security — REFUTE the leak-class closure | read-only | **RETURNED — REFUTED; round NOT clean** |
| `w5-correctness` | correctness + closure-parity; 5 test trees           | read-only | **in-flight at wrapup**                 |

Both READ-ONLY: no branch, no PR, no commit expected. Findings route to the orchestrator.

### `w5-sec` VERDICT — the branch's security work does NOT hold (ledger row F10)

**The round is NOT clean. Convergence is NOT met. Do NOT open the PR.** 2 of 6 REFUTED.

**HIGH (a) — VERIFIED FIRST-HAND by the orchestrator** (the lens had no Bash). Seven
`traceback.format_exc()` return surfaces in `kaizen-agents/src/patterns/patterns/`
(`parallel.py`, `blackboard.py`, `ensemble.py`, `meta_controller.py`). At `parallel.py:143`
the message is scrubbed; at `:147` the raw traceback is returned **in the same dict**.
**The scrubbed line makes the file register SWEPT — counted as covered while carrying the
defect.** Byte-for-byte the CLASS-2 defect `689f9ebd8` fixed for `exc_info=True`, one shape over.

**HIGH (b)** — 2 wholly unscrubbed `str()` returns: `parallel.py:256` (exception from
`gather(return_exceptions=True)`, never in an except handler) and `meta_controller.py:243`
(exception arrives as a PARAMETER, so no `ExceptHandler` exists in the function at all).
Both invisible to the scanner by construction.

**MEDIUM (c)** `_SinkScan` blind to `%`-format, `.format()`, exception ATTRIBUTES
(`e.args`, `e.response.text`), `format_exc()`, and any exception that is a VALUE not a
caught binding. **(d)** `secret_key=` / `passphrase=` absent from `_CREDENTIAL_KEY_NAMES`
— leak under BOTH presets. **(e)** `claude_code.py:398-401` kills without reaping then
drops the handle; `:356` in the SAME file does it correctly, so the reading discriminates.

**LOW (f)** the `kaizen/__init__.py` KEEP rests on a false premise about imports; no leak
demonstrated, but the rationale needs rewriting to a checkable claim.

**Method caveat, stated by the lens — honour it.** It had **NO Bash**: could not run the
`git show` controls, could not execute `_SinkScan`, could not run the scrubber. It marked
NOT PROVEN rather than HOLDS wherever it could not control a claim. **NOT EXAMINED:**
`bb8a3f966` (monitoring stop) and four of seven retained named fields. **Someone with Bash
owes those** — the next round must not treat them as covered.

**Minimum to close F10:** scrub or drop every `format_exc()` return field; route
`parallel.py:256` + `meta_controller.py:243` through `scrub_remote_error`; teach
`_SinkScan` the `format_exc` shape and the non-except-bound exception value — then re-run
it and **expect the pinned 57/191 counts to MOVE.** A count that does not move means the
teaching did not take.

**If they returned after this was written**, their reports ARE the convergence evidence —
read them. **If they did not return, or returned errored/empty: that is ZERO evidence,
NOT a clean round** (`agents.md` § Redteam Reviewer Dispatch; `evidence-first-claims.md`
MUST-3). Re-dispatch from scratch. Do NOT record convergence without reading them.

### Stood down this session — all committed, no orphan worktrees

Security (`w1-rt5-secD`), test-hygiene (`w2-testfix`), nexus (`w1-nexus-hang`),
verification/PR-body (`w1-rt5-testcontract`). Three hit context or quota limits and
handed over cleanly with everything needed to continue.

## Standing operational notes (carried, all re-confirmed this session)

**Agents go idle WITHOUT delivering.** Confirmed repeatedly again. **Root cause is now
KNOWN:** a reviewer reported it had COMPLETED its round and written the report as plain
assistant text without ever calling SendMessage. **The failure is DELIVERY, not
execution.** Query, never re-dispatch — every re-ping this session returned substantial
finished work on the first retry. Re-dispatching would have thrown that away.

**An idle signal is not a completion signal — check the ARTIFACT.** `git log <base>..HEAD`
plus `git diff --stat` over the agent's partition. Both empty ⇒ not started. This caught
unstarted work twice and a false alarm once.

**Session-limit death kills every in-flight agent at once** — account-scoped, distinct
from the server-side concurrency throttle (no `not your usage limit` string). The
recovery unit is the WHOLE wave. Happened again this session: four lanes died together.

**Cold-start ~3 concurrent Opus agents** (`worktree-isolation.md` Rule 4). Ran 4 for most
of this session with no throttle signal.

**A shard that dies mid-flight may have COMPLETE work on disk** — verify the tree before
assuming a task needs re-running.

## Prior waves

Wave 8 (session D) and Wave 7 are CLOSED; their reconciliation detail is superseded by
the committed record — see `04-validate/launch-ledger-sessionI.md` and the sweep reports.
Rounds 2–5 of the redteam are complete.

# Wave tracker — esperie

## Status: CLEAN ROUND IN FLIGHT (2026-08-09, session I)

Branch `fix/issue-1720-forest-drain` @ `9b67890a8`. Everything is pushed. The clean
round is the ONLY outstanding gate.

Read this BEFORE spawning anything (`orchestration-launch-ledger.md` MUST-2;
`wave-loop.md` MUST-6). Match every completion against the table BEFORE reacting (MUST-3).

### Launch ledger — the clean round (re-dispatched)

Dispatched against `b220704b5` after a FIRST attempt died on a session quota with
neither lens delivering. Code surface is unchanged since; later commits are docs-only.

| agent            | lens                                                 | mode      | status                  |
| ---------------- | ---------------------------------------------------- | --------- | ----------------------- |
| `w5-sec`         | adversarial security — REFUTE the leak-class closure | read-only | **in-flight at wrapup** |
| `w5-correctness` | correctness + closure-parity; 5 test trees           | read-only | **in-flight at wrapup** |

Both READ-ONLY: no branch, no PR, no commit expected. Findings route to the orchestrator.

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

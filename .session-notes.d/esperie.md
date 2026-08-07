---
owner: esperie
last_reconciled_sha: 98e83dfbe
migrated_from: .session-notes
---

# Session Notes — 2026-08-06/07 (session G)

Workspace `issue-1720-llm-consolidation`, phase 05-codify, branch
`fix/issue-1720-forest-drain` — **161 ahead of `main`, 93 UNPUSHED, working tree CLEAN.**

Session F's risk was uncommitted work. **That is closed** — all 63 files committed in 13
slices. Session G's risk is UNPUSHED work.

## Read first, in order

1. **`workspaces/issue-1720-llm-consolidation/04-validate/sweep-2026-08-07.md`** — the current
   decision report. PCF-triaged queue, 6 decision points, ordered next steps. **Start here.**
2. **`04-validate/launch-ledger-sessionG.md`** — the authoritative record. Every finding, all
   EIGHT of my orchestrator errors, every named residual. Long, and the § headers are navigable.
3. This file's **Traps** below before touching anything.

## THE ONE THING BLOCKED ON THE CO-OWNER

**The push is rejected by GitHub secret scanning.** 93 commits, no off-machine copy. Two
SYNTHETIC Stripe fixtures (`sk_live_` + 24 lowercase chars, sequential alphabet, siblings of
AWS's own `AKIAIOSFODNN7EXAMPLE`) in unpushed commit `943278479`. Verified synthetic; absent
from `main`. Co-owner chose allowlist-via-URL over history rewrite (a rewrite would invalidate
`45ccac417`, cited publicly in the #1996 closure). Fixed forward in `5cf1fd8bc`.

The two unblock URLs are in the session transcript. **Do not attempt a history rewrite** — that
decision was made and the reasoning is in the ledger.

## Convergence position — state it honestly

**Counter ZERO.** Rounds 2, 3, and 4 all ran with rotated lenses; **round 4 was NOT clean**
(2 branch-caused regressions, both now fixed). Round 5 is required, then a clean round.

Do NOT read "all findings closed" as convergence. `completion-criterion.md` MUST-4: a cap-stop
is abnormal termination, never done.

## VERIFICATION STATUS — read before citing ANY suite number

**Every suite number produced before the protocol change is UNSOUND**, including ones earlier
session-G reports called orchestrator-verified. Four lanes ran concurrently in ONE checkout; a
sibling could have had a module neutered mid-run (one was caught: `AccessMetadata.deny()`
returning a full `execute` grant, restored 11s later).

**Protocol now: fingerprint `git status --porcelain` BEFORE and AFTER each run; the numbers are
VOID unless both match.**

| Tree                                 | Result                                | Verdict           |
| ------------------------------------ | ------------------------------------- | ----------------- |
| root `tests/unit/`                   | 4798 passed, 4 skipped                | **VALID**         |
| root `tests/regression/`             | 1567 passed, 2 skipped, 22 deselected | **VALID**         |
| `tests/unit/mcp_server/`             | 645 passed                            | **VALID**         |
| `packages/kailash-mcp/`              | 649 passed, 1 skipped                 | **VALID**         |
| nexus / kaizen-agents / kaizen regr. | —                                     | **UNESTABLISHED** |

UNESTABLISHED = not run to completion (10-min cap under lane contention), **NOT failing.**
Lanes are idle now; re-running them is mechanical and is step 2 of the sweep's recommendation.

## What landed (all committed)

Round 2 (7 HIGH + 6 MED), round 3 (3 HIGH + 4 MED + 2 LOW), round 4 (2 REGRESSION + 3 STALE) —
all fixed, each with an individually established RED→GREEN, most driven end to end.

Highlights worth knowing:

- **#1720 closed on the public route** (`568036906`, `2d2563d81`). The envelope guard's tree
  list now carries an explicit INCLUSION CRITERION + every candidate tree with a verdict and
  measured count — a future reader audits the CRITERION, not the list.
- **MCP auth bypass** (`8f8577c36`): `disable_tool` → re-register → `enable_tool` restored a
  stale UNGATED entry. Uncredentialed `tools/call` returned `V1-EXECUTED`. Fixed at all THREE
  sites that can break the invariant.
- **A hardening probe was itself disclosing** (`b1ac06e5b`) — the liveness sentinel was visible
  to concurrent `tools/list`. Removed because the window could not be proven unreachable.
- **Rate limiter fail-OPEN** (`98e83dfbe`): 2 of 4 write surfaces never coerced; a typo'd minus
  silently disabled it. The corpus sweep found the 4th surface before the partial fix shipped.
- **Finalizer guard restored** (`9f3e69de8`): `__del__` raised inside GC, reddening rotating
  unrelated tests — the flaky-nexus explanation.

Issues: **#1996 CLOSED**. **FILED: #2001 #2002 #2003 #2004 #2005.** **#2006 is NOT mine** —
another session filed it.

## THE DURABLE LESSON — eight non-discriminating instruments

Every real finding this session was an instrument that returned the same answer whether or not
the defect existed. Eight of them. Two reached DURABLE artifacts (a shipped CHANGELOG
all-clear; two committed docstrings). The transferable rules:

1. **"N sites swept" is a claim about the PATTERN, not the code.** State the pattern so the
   reader sees what it could not match. (A grep matching only f-string interpolation reported
   "14 of 14 fixed" having missed an entire syntactic form.)
2. **A name rebind is INERT once the object is captured** into a collection, a default argument,
   or another module's import. Verify the patch changes observable behaviour WHILE APPLIED.
3. **Prove the mutation REACHES the code** before reading a non-red as vacuity — otherwise you
   have two live hypotheses.
4. **A bare line anchor manufactures PHANTOM FINDINGS in the verifier**, who cannot tell "the
   fix moved this" from "the report was sloppy." Cite `<file>::<symbol>`.

## Traps (carried + new)

- **`.venv/bin/python -m pytest` ALWAYS**; `--timeout=120`. Bare python dies at conftest with
  `ImportError: Node`.
- Root `tests/` and `packages/kailash-nexus/tests/` **cannot** be collected together (duplicate
  basenames). `kailash-kaizen` and `kaizen-agents` likewise. **Run every tree separately.**
- Clear `__pycache__` before kaizen runs.
- Do NOT `pkill -f pytest` — kills sibling suites.
- `cd` PERSISTS between Bash calls. Use absolute paths.
- **NEVER `git checkout --` / `reset` / `stash` / `clean`** in a shared tree.
- **NEW — commit with a PATHSPEC**: `git commit -F <msg> -- <paths>`. `git add` publishes to an
  index every lane shares; a bare commit already swept a sibling's staged files once.
- **NEW — a pathspec commit must still leave HEAD GREEN.** One lane committed a test without its
  implementation; a fresh clone failed 12 tests silently.
- **NEW — compose the commit body from `git diff --cached --stat` AT COMMIT TIME**, not an
  earlier tree read. That race produced an over-claiming message.
- **NEW — mutation testing is INCOMPATIBLE with concurrent suite runs in a shared tree.** Use a
  dedicated SHORT-LIVED process (not merely "in-process") or a copy. Ownership prevents write
  CONFLICTS, not transient invalid STATES.
- **NEW — never delete `.git/index.lock`.** Wait it out; a lane hit it and it cleared in ~1s.

## My orchestrator errors (8) — full detail in the ledger

Recorded because the pattern matters: **the orchestrator was again the least reliable source of
claims.** Tool-inventory mismatch (asked a read-only agent to write a file); FOUR wrong
fix-recommendations, every one refuted by a lane's measurement or reproduction; a duplicate lane
spawn (ledger tracked spawns, not task-list claims); an over-claiming commit body; a wrong
worktree-deviation justification that made every suite number suspect; and repeated
`symbol-anchored-citations` MUST-3 violations. **Standing correction: name the INVARIANT, let
the lane choose the shape.**

Posture: recorded, NOT self-assessed. The citation violations are past the cumulative threshold
and route through gate-review adjudication — `/codify` should adjudicate rather than discover.

## Next steps (from the sweep, in order)

1. **Co-owner allowlists the two URLs → push.** Only unrecoverable risk.
2. Re-run the 3 UNESTABLISHED trees under the fingerprint protocol.
3. **Round 5**, rotated lens, over the round-4 fix surface; then a clean round.
4. Close **#1998** (fixed by `cdfdc2f7e`/`8f8577c36`/`b1ac06e5b`, still open); label #2003/#2005
   `deferred-quality`.
5. Open the PR (draft body at `04-validate/pr-body-draft.md` — **re-derive its numbers first**).
6. **`/release`**: mcp 0.5.0 → kaizen 2.46.0 → kaizen-agents 0.13.0 → dataflow/nexus/ml →
   kailash 2.63.0 LAST. Then raise root extras floors.
7. BUG queue — **#2006 and #2002 first**.

**Owed to the co-owner and unanswered:** the semver question (BREAKING changes in MINOR bumps;
recommendation = ship as-is, decide policy separately), and #1995's FOURTH Sweep-N gate.

---
owner: esperie
last_reconciled_sha: 82480af19
migrated_from: .session-notes
---

# Session Notes — 2026-08-08/09 (session I)

Workspace `issue-1720-llm-consolidation`, phase 05-codify, branch
`fix/issue-1720-forest-drain` @ `82480af19` — **210 ahead of `origin/main`, 6 behind,
49 UNPUSHED, working tree clean.**

## READ THIS FIRST — two things are at risk and one claim is NOT true

**1. ALL 49 COMMITS OF THIS SESSION ARE UNPUSHED.** They exist in exactly one place.
Sessions F and G both closed this way and it is the single most expensive failure this
repo repeats. `git log --oneline origin/fix/issue-1720-forest-drain..HEAD | wc -l` → 49.
**Push is a shared-state action and was NOT taken** — surfaced to the co-owner, not
self-authorized. Carried trap: **GitHub secret-scanning unblock URLs ROTATE on every push
attempt** and the page is a FORM (pick a reason, confirm) — visiting does nothing. Ask
whether the forms are submitted, THEN push; a speculative retry invalidates the links.

**2. THE CLEAN ROUND DID NOT RUN. CONVERGENCE IS NOT MET.** Two lenses were dispatched
against `82480af19` — an adversarial security lens (`w4-clean-sec`) and a
correctness/closure lens (`w1-rt5-testcontract`). **BOTH DIED ON A SESSION QUOTA LIMIT
before delivering** (`failureReason: You've hit your session limit · resets 12:10am
Asia/Singapore`). A failed agent is ZERO evidence, never a clean round
(`agents.md` § Redteam Reviewer Dispatch + `evidence-first-claims.md` MUST-3).
**Do not record a clean round. Do not upgrade the PR body's "NOT converged".**
The round must be re-dispatched from scratch after the quota resets.

**3. The PR body is FROZEN and correct at `eb7f9ae01` content.** Do not edit it without
naming a SHA — it went through three reversals on one paragraph because an instruction
described prose state without pinning a commit. Every figure in it is pinned to the SHA
it was measured at; the counts are perishable and the body says to re-derive at merge.

## What landed — 49 commits, 19 product fixes

| commit                                          | defect                                                                                 |
| ----------------------------------------------- | -------------------------------------------------------------------------------------- |
| `1df4df166`                                     | 5th rate-limit write surface — silent fail-open, guarded only by an annotation         |
| `689f9ebd8`                                     | **credential leak** — 18 sinks; message scrubbed, traceback re-leaking it              |
| `a50fb78c6`                                     | **shutdown wedge** — pooled executor worker joined at interpreter exit                 |
| `7333e90de`                                     | Redis cache `clear()` did nothing and logged success                                   |
| `62d6cf6f3`                                     | entire sync cache surface non-functional on Redis                                      |
| `e13339c02`                                     | `__del__` did cleanup work that can deadlock                                           |
| `04f7c6258` `90899764a` `20f507bb0` `934d5f8ae` | 40+ further leak sinks incl. 3 RETURN surfaces feeding the model                       |
| `d6030aefe`                                     | hook-name fallback rendered a caller-supplied `repr` — re-opened the leak class        |
| `6a6e54541`                                     | sink scanner taught 2 blind shapes — **found 6 more sinks on first run**               |
| `4036b4c96`                                     | labelled histogram percentiles unscrapeable by Prometheus                              |
| `4772d0c48`                                     | orphaned subprocess reported disconnected, handle dropped                              |
| `bb8a3f966`                                     | monitoring stop returned `status: stopped` with nothing stopped                        |
| `fdfa8cbc4`                                     | rate-limit test converted from wall-clock to a structural entry count                  |
| `4c5f7c5b2` `82480af19`                         | backoff test measured other transports' sleeps; assertion depended on `PYTHONHASHSEED` |

## Issues filed — #2008–#2013, co-owner approved

- **#2008** MCPChannel shutdown wedge — FIXED here; filed because PRE-EXISTING and
  production-side: first shipped `v0.8.6` (2025-07-22), every 2.x through `v2.62.0`, ~382 days.
- **#2009** discovery authz fail-open — deliberate deferral, Rule 1b tracking receipt.
- **#2010** stale `BaseAgent(description=)` E2E — git-proven pre-existing.
- **#2011** a test writes into the repo root, voiding run fingerprints.
- **#2012** 390 un-triaged exception sinks in kailash-kaizen. **NOT 390 leaks** — an
  un-triaged surface. Start at the **28 sites in 8 files that already import a scrubber**;
  a half-swept file's import reads as evidence it was handled.
- **#2013** **`Nexus(enable_auth=True)` and `app.enable_auth()` are INERT** — a documented
  production security control that installs nothing. Enabling auth is indistinguishable
  from not enabling it. `NexusAuthPlugin` works; the README-documented facade does not.
  ≥140 days. **Approval for filing was extended by the agent to this sixth finding** —
  flagged to the co-owner; not silently assumed.

## The two findings worth more than any single bug

**Components confirming actions they never performed** — 4 instances (cache logged
"Cleared" without clearing; channel reported STOPPED while serving; a debug line claimed
a cache store on the skipped path; a test logged "PRODUCTION READY" asserting nothing).
The worst were RETURN VALUES an orchestrator acts on, not log lines.

**The fix landing where someone was looking** — 7 instances, each a sibling left behind.
The seventh is on a security surface: `enable_monitoring()` had the identical dead branch
as `enable_auth()`, was rescued with a second path, and its sibling three lines away was
left (#2013).

## The instrument class — and why it is NOT a new rule

**12 instrument failures across 5 lanes, in BOTH directions** (false clears AND false
alarms). The property that catches them is **already `instrument-discipline.md`, baseline
priority, loaded in every session — and CITED BY CLAUSE in sessions F, G, H and I**,
including the sessions where the violations happened. Verified with a negative control.

So this is an **enforcement gap, not a knowledge gap**:

> A rule can be baseline-priority, loaded, cited by clause and correctly understood, and
> still not bind — because understanding a test is not the same as having a second
> instrument to run it with.

Corroboration the rule supplies about itself: its Detection block defers a hook detector
because _"a regex detector would itself instance this class"_ — and this session produced
**two confirmations of that exact prediction, in opposite directions** (a grep defeated by
shell word-splitting; a grep defeated by ANSI colour codes).

**The operational form the rule lacks** — a sweep needs a POSITIVE CONTROL; a scanner needs
NEGATIVE controls; a test needs an OUTCOME-shaped assertion (not mechanism-shaped); a claim
needs a NAMED FALSIFYING RESULT. Evidence: `codify-evidence-sessionI.md` (§0/§1/§2,
provenance-graded [V]/[R]).

Four of the 12 were committed by agents actively fixing the class; two were the
orchestrator's, one while auditing that very document. **Anyone reading it as "be more
careful" has read a performance review, not a finding.**

## Next steps, in order

1. **PUSH** (co-owner gate; check the secret-scanning forms first).
2. **RE-DISPATCH THE CLEAN ROUND** after quota reset — 2 lenses minimum, adversarial
   security + correctness/closure, scoped to `7aeb61d5e..HEAD`, both with genuine
   ran-signals. Convergence counter is ZERO.
3. Re-derive the git counts (perishable; suite numbers are stable) and open the PR.
4. `/release` — mcp → kaizen → kaizen-agents → dataflow/nexus/ml → kailash LAST; raise the
   FIVE extras floors between sub-package publishes and the core tag.
5. #2013 fix — security-reviewed partition + adversarial round. Interim: a loud one-time
   WARN naming it a no-op and pointing at `NexusAuthPlugin`.
6. After merge: the #1995 repo-wide reformat, own PR.

## Known-uncovered, recorded so a zero is not over-read

- **45 untriaged `.cancel()` sites** — unread, not clean; inflated by a known
  `for t in <coll>: t.cancel()` + `gather(*coll)` false-positive class, extent unmeasured.
- **136 `asyncio.to_thread` sites** — adjacent to the executor-future class, mechanically
  different, not swept.
- The executor-future sweep's zero IS structural (precursor count is also 0: not one
  executor future stored on a `self` attribute in 2076 files) but covers intra-function
  plus named indirect forms only.

## Traps (carried + new)

- `.venv/bin/python -m pytest --timeout=120 -p no:cacheprovider`; run trees SEPARATELY.
- **READ THE SUMMARY LINE, NEVER THE EXIT CODE** — and note `a50fb78c6` fixed the nexus
  hang, so that tree now exits 0 on its own (`2632 passed`, EXIT=0).
- `pkill -f pytest` is BLOCKED — ~10 concurrent suites from other operators on this host.
- **`git status` has no vocabulary for duration.** A clean read is a millisecond
  observation, not a standing property. Pin a SHA; re-check the pin holds afterwards.
- **Version archaeology has FOUR traps**, each producing a confidently wrong
  affected-versions line: `--contains` noise under reused namespaces (667/697); a commit
  subject naming a release ≠ the tag containing it; `--follow` + `-S` do not compose
  (returned a file-move as a security defect's origin); and same-version tags two days
  apart with opposite answers. Method that survives all four: pickaxe the exact string over
  the owning file, expect a small definite commit set, sort tags by COMMIT DATE and read
  the clean→CONTAINS boundary. Two independent strings agreeing is the bar for a claim
  that ships.
- **"Passes alone, fails in the full suite" is equally consistent with host contention and
  with per-process nondeterminism** — only the second is fixable. Sweep `PYTHONHASHSEED`
  before blaming the box. (One of each occurred this session; the second was 2/200 seeds,
  matching C(6,5)/C(11,5) = 1.3%.)

---
type: AMENDMENT
date: 2026-07-13
author: agent
project: mops-onboarding
topic: re-convergence #13 — redteam the landed #1694 re-strand to 2-consecutive-clean; complete the #16 citation class to loom
phase: redteam
relates_to: 0044-DECISION-re-strand-1694-fix-21-22-plus-fullsuite-audit
tags:
  [
    redteam,
    convergence,
    1694,
    citation-vs-wired,
    handoff-completion,
    loom-gate-1,
    throttle-backoff,
  ]
---

# AMENDMENT — re-convergence #13: #1694 re-strand redteamed to convergence + #16 class completed

Extends `journal/0044` (the #1694 re-strand: #21/#22 landed via PR #1704, 7 stranded entries routed to loom). This session redteamed the LANDED #21/#22 work to full 2-consecutive-clean convergence and, in doing so, found the loom handoff of one finding class was under-enumerated — completed it.

## Result

**CONVERGED** at L5_DELEGATED. The 4 landed edits (45-genesis DIRECT set + `runEnrollmentCeremony` `record?`; 43-ecosystem STATE_PATH_RX hedge + 45-genesis sibling) are **byte-accurate against wired source** — re-verified independently across 3 genuine reviewer rounds. **0 CRIT / 0 HIGH.** No BUILD-side code change was needed (the edits were already correct).

## The one finding (F1) — #16 citation class was under-enumerated in the loom handoff

The bare `detectStateFileMutation`-cited-as-Layer-3-guard class (wired call is `detectStateFileMutationSegmentAware`, `validate-bash-command.js:458/:527`; bare primitive is `violation-patterns.js:821`) was flagged by loom's #16 at **2 sites** (`whoami.md:47`, `42-certify:153`). An **exhaustive tree-wide grep** found the class is **6 sites** — 4 more: `45-genesis:143`, `45-genesis:190`, `43-ecosystem:117`, and `agents/onboarding/coc-onboarding-specialist.md:80`. The last was missed by two of my own narrower sweeps and caught by the R2 reviewer (my glob covered `skills/`+`commands/`, not `agents/`) — a lesson in "grep the WHOLE tree, not a subset" for completeness claims.

**Disposition:** loom Gate-1, not BUILD-fixed — F1 is #16-class (`#10-16` group: a BUILD session cannot classify loom-canonical-applies vs absent-at-loom; anti-churn guidance holds), distinct from #21/#22 (`absent at BUILD AND loom → files-present`). The complete 6-site CLASS-A list + a CLASS-B carve-out (the `violation-patterns.js::detectStateFileMutation` primitive citations that are CORRECT and must NOT be touched) was surfaced on **#1694** (`issuecomment-4952183654`).

## Throttle-backoff (process receipt)

The first round dispatched 3 parallel adversarial agents; all three hit the synchronized server-throttle signal (`(not your usage limit) · Rate limited`, near-zero tokens) — the exact `worktree-isolation.md` Rule 4 pattern. Per the redteam evidence gate (`agents.md` § Redteam Reviewer Dispatch + `evidence-first-claims.md` MUST-3), a throttled reviewer is ZERO evidence and MUST NOT count as clean. Backed off to **serial** dispatch (R2/R3/R4, one at a time) — each ran genuinely (92k/112k/224k tokens). Convergence was NOT claimed until every counted round genuinely ran.

## Receipts

- Round verdicts: R2 (reviewer, confirmed 6 verdicts + surfaced 6th site), R3 (general-purpose, CLEAN, tree-wide grep), R4 (cc-architect, CLEAN) — this session's transcript.
- Report: `workspaces/mops-onboarding/04-validate/redteam-2026-07-13-reconvergence13-1694-restrand.md` (assertion tables).
- Loom handoff: `#1694` `issuecomment-4952183654` (complete 6-site CLASS-A enumeration).
- Pending-journal hygiene: discarded the CWD-misrouted duplicate 2.48.1 RISK candidate (already codified `sdk-backlog/journal/0026`).

---
type: AMENDMENT
date: 2026-07-09
author: co-authored
project: mops-onboarding
topic: re-convergence #10 — /onboard DEFER phantom journal-type found + fixed; convergence receipt
phase: redteam
relates_to: 0040-AMENDMENT-reconvergence9-disclosure-risk-closure
tags:
  [
    redteam,
    reconvergence10,
    onboard,
    journal-type,
    citation-accuracy,
    command-skill-parity,
    self-referential-codify,
  ]
---

# AMENDMENT — re-convergence #10 converged (1 MED found + fixed)

Extends the re-convergence arc (amends the #9 closure `journal/0040`). A fresh `/redteam` to
convergence over the #9 state merged on main (PR #1629) + the #9 close-out (PR #1630 / `925e37c07`).

## Disposition

**CONVERGED — 0 CRITICAL / 0 HIGH; 2 consecutive clean rounds.** 4 rounds: R1 mechanical (clean) →
R2 two parallel adversarial agents (**1 MED found**) → fix → R3 3-agent self-referential-codify
gate (reviewer + security-reviewer + cc-architect; clean) → R4 mechanical (clean). Full audit:
`04-validate/redteam-2026-07-09-reconvergence10.md`.

## The finding (MED, FIXED)

The `/onboard` read-path cited **`DEFER` as a canonical journal type** — a token that is NOT in
`journal-reserve.js::VALID_TYPES` (`{DECISION, DISCOVERY, TRADE-OFF, RISK, CONNECTION, GAP,
AMENDMENT}`), NOT in `rules/journal.md`'s enum, and explicitly disclaimed by the sibling `/certify`
artifacts ("DEFER is NOT a canonical journal type"). Two mirror sites:

- `.claude/commands/onboard.md` — filtered `DECISION-` / `DISCOVERY-` / `DEFER-` entries.
- `.claude/skills/41-onboard/SKILL.md` — `types=["DECISION","DISCOVERY","DEFER"]`.

The `DEFER-` branch was **dead code** (real deferrals are `DECISION`-typed with "defer" in the
topic slot → zero `DEFER`-typed files exist), so no operator-visible data loss → MED, not HIGH.
It survived 9 rounds because the token resolves (passes grep / dangling-ref sweeps) yet contradicts
the wired vocabulary; only cross-artifact verification against the sibling `/certify` pair surfaced it.

## Fix

Dropped `DEFER` from both filters (same-shard command↔skill mirror edit per `command-skill-parity.md`
MUST-1); added a ground-truth-cited note (`journal-reserve.js::VALID_TYPES` / `rules/journal.md`)
that deferrals are `DECISION`-typed and already surfaced by the `DECISION-` filter. `onboard.md` is on
the `self-referential-codify.md` Rule-2 allowlist, so the fix cleared the Rule-1 multi-agent
redteam-with-tests gate (R3: 3 independent agents, all clean). Routed to loom via the BUILD→loom
proposal (`latest.yaml`) for cross-SDK + downstream distribution — the onboard suite is loom-synced,
so every downstream copy carried the same phantom.

## Net

Re-convergence #10 CLOSED. The #9 disclosure closure (journal/0040) + its guard-symbol fixes all
re-verified holding on merged main; the #9 close-out receipts (journal/0040 + sweep) verified
accurate against ground truth; one new MED (onboard DEFER phantom) found, fixed, and routed to loom.

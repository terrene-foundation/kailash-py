---
type: DECISION
date: 2026-06-25
author: co-authored
project: mops-onboarding
topic: codify the /sweep + /wrapup forest-ledger blindness as a BUILD->loom proposal
phase: codify
verified_id: SHA256:ZJJ4B
person_id: pid-esperie-2b8cb994
display_id: esperie
tags: [sweep, wrapup, forest-ledger, codify, loom-proposal, cross-repo]
relates_to: 0004-esperie-AUTHORIZATION-cross-repo-loom-sweep-ledger-issue
---

# DECISION — codify the /sweep + /wrapup forest-ledger gap (proposal-only)

## What

Appended ONE `command_update` change to `.claude/.proposals/latest.yaml`
(status stays `pending_review`; now 6 changes) describing the two-coupled-gap
fix for `/sweep` + `/wrapup` forest-ledger blindness:

1. **Sweep side** — a tool-backed `/sweep` step reading every
   `workspaces/*/.session-notes` `## Outstanding ledger (forest)` section,
   rolling open rows up deduped by ID regardless of MTIME / issue state.
2. **Reconciliation side** — extend `validate-forest-ledger.mjs` from
   within-file `--git-prior` to a workspace→root no-vanish aggregation.

Target files (loom-owned canonical): `commands/sweep.md`, `commands/wrapup.md`,
`hooks/lib/validate-forest-ledger.mjs`. Suggested classification: global.

## Why

A user-`/sweep` challenge surfaced that 4 dormant workspaces (issues all CLOSED)
held OPEN forest-ledger follow-on items invisible to every one of the 8 sweeps:
`grep -n "ledger\|forest" commands/sweep.md` = 0 hits. Root cause matches
`sweep-completeness.md` Rule 3 (recurring sweep gap → tighten command text into
a tool invocation). Evidence + dispositions in `SWEEP-2026-06-25.md`.

## Routing / discipline

- BUILD→loom proposal (Step 7a): proposal-only, NO local edit to the loom-owned
  canonical artifacts (a local edit is clobbered by `/sync-to-build`).
- Also cross-filed as a tracked issue `esperie-enterprise/loom#669`
  (user-authorized, journaled at `0004`); proposal `context` flags Gate-1 to
  dedupe against #669.
- NOT self-referential in this repo (no `self-referential-codify` Rule-2
  allowlist file edited — a proposal description only) → mandatory multi-agent
  gate does not fire. No new rule authored → no Trust-Posture-Wiring needed.
- Gate review: first-party (gap diagnosis verified via grep; disclosure scrub
  confirmed — generic, public refs only; YAML re-parses, status preserved).
  Authoritative review is loom Gate-1 (`/sync-from-build` + proposal-intake-trust).
- Codify lease: refused `scope-dirty` (own session journal artifacts in scope —
  NOT a concurrent-operator `conflict`); solo session; `coordination-mode.js`
  absent (partial substrate). Proceeded on branch
  `codify/esperie-2026-06-25-sweep-ledger` with explicit-path commit.

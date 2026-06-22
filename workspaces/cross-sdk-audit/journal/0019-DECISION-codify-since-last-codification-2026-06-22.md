---
type: DECISION
date: 2026-06-22
author: agent
project: cross-sdk-audit
topic: /codify cycle since the 2026-06-19 codification — 3 cross-SDK/trust-plane rule clauses authored, appended to the pending BUILD->loom proposal
phase: codify
tags:
  [
    codify,
    cross-sdk,
    trust-plane,
    nan-inf,
    canonical-encoder,
    integrity-manifest,
    build-to-loom-proposal,
  ]
relates_to: 0011-DISCOVERY-canonical-encoder-family-sweep-broadens-cross-sdk-lockstep, 0015-DECISION-fresh-redteam-caught-two-gaps-pr1411-converged, 0017-DECISION-naninf-bug-class-closure-convergence-and-2.43.1-release
---

# DECISION — /codify since the last codification (2026-06-19 → 2026-06-22)

User directive: "please /codify, not just the last session, but since the last codification."

Last codification was **2026-06-19** (`learning-codified.json::last_codified`); a `pending_review`
BUILD→loom proposal from that date carries the `agents.md` redteam-dispatch clause. This cycle
codifies the genuinely-new pattern-level learnings from the **2.43.1 / 2.44.x** work since then
(NaN/Inf trust-plane sweep, async-SQL streaming, #1406 stub-gap closure, canonical-encoder
cross-SDK lockstep, JWT revocation parity) and APPENDS them to the same proposal.

## What was authored (3 clauses across 2 path-scoped rules)

1. **`trust-plane-security.md` MUST clause 8 — Signing/Hash Pre-Images MUST Reject NaN/Inf
   (`allow_nan=False`).** The SERIALIZATION-axis NaN/Inf failure mode. Verified against ground
   truth: `grep "allow_nan"` across `.claude/rules/` returned ZERO hits pre-cycle. DISTINCT from
   the existing value-comparison NaN guards (this file's Rule 3 + MUST-NOT-5; `pact-governance.md`
   Rule 6). Origin: 2.43.1 sweep (PR #1411 + #1412; journal/0015 + 0017).

2. **`cross-sdk-inspection.md` Rule 4b — Byte-CHANGING Canonical-Encoder Switches Are Cross-SDK
   Lockstep, Not Single-SDK.** Classify a canonical-encoder migration byte-NEUTRAL vs
   byte-CHANGING by EMPIRICAL byte-diff; byte-CHANGING where the sibling mirrors current bytes →
   lockstep + pin-current-bytes tripwire; byte-NEUTRAL → may ship single-SDK. Distinct from the
   existing Rule 4 (parity byte-vectors). Origin: journal/0011 (97-site classification) +
   `specs/trust-canonical-encoders.md`.

3. **`cross-sdk-inspection.md` Rule 4c — Conformance-Vector Changes Re-Pin Their Integrity
   Manifest In The Same Commit** (+ `/redteam` integrity-manifest-sweep lens). `grep` confirmed
   no rule covered manifest re-pin. Origin: PR #1411 Gap 1 (the `PACT_VECTORS.sha256` re-pin
   omission a "converged" redteam missed because no round ran `shasum -c`; journal/0015).

Each new clause ships clause-scoped 8-field Trust Posture Wiring (both rules grandfathered with no
prior wiring; clause-scoped wiring per the `artifact-flow.md` "Intake Disclosure Scrub" precedent).

## Process / gates honored

- **Repo class = BUILD** → `/codify` writes the rule clauses locally for immediate use AND appends
  to `.claude/.proposals/latest.yaml` (status stays `pending_review`; 3 changes total) for loom
  Gate-1 classification (all suggested GLOBAL — the failure modes are the cross-SDK conformance
  contract both SDKs share). No cross-repo sync from this BUILD session (repo-scope-discipline).
- **Self-referential gate:** neither `trust-plane-security.md` nor `cross-sdk-inspection.md` is on
  the `self-referential-codify.md` Rule 2 allowlist → the MANDATORY multi-agent redteam-with-tests
  round does NOT fire. Both rules are `priority:10/path-scoped` → `rule-authoring.md` Rule 10
  proximity-band gate does NOT fire.
- **Branch:** `codify/esperie-2026-06-22` (integrity-guard requires `.claude/` writes off a
  `codify/*` branch). PR + admin-merge per `coc-sync-landing.md` MUST-3.

## What was NOT codified (and why)

- The stale `journal/.pending/` auto-captures (NaN/Inf sweep, reseal_only test, vault gates) are
  SessionEnd captures of already-merged commits, several CWD-misrouted DUPLICATES — the exact
  failure the 2026-06-19 journal-hygiene candidate (#1086 candidate 2+4) targets; the real remedy
  is the loom-side dedup-by-source_commit hook (#1086 candidate 3). Left for that fix.
- reseal_only multi-anchor test pin / JWT-revocation rs parity / canonical-spec LOW citation fixes
  are INSTANCES of already-codified patterns (testing.md regression; cross-sdk-inspection Rule 1;
  zero-tolerance 3e) — no new rule.

---
type: DECISION
date: 2026-06-25
author: agent
project: kailash-py
topic: Enforcement-Surface Parity codify (pact-0.14.3 redteam follow-on)
phase: codify
verified_id: SHA256:ZJJ4BzXTDOS2WMGbNmesXb5K2VGzSvk3O30DmKacml0
person_id: pid-esperie-2b8cb994
display_id: esperie
tags:
  [
    codify,
    security,
    pact,
    enforcement-surface-parity,
    build-to-loom,
    proposal-only,
  ]
relates_to: 0002-DECISION-cross-repo-authorized-loom
---

# 0003 — DECISION: Codify "Enforcement-Surface Parity" (pact-0.14.3 redteam follow-on)

**User direction (this session):** asked "do we need to /codify?"; on the agent's
recommendation, replied **"approved. /codify"**. Agent recorded this entry.

## Decision

Codify ONE insight from the prior session's pact-0.14.3 redteam work — **Enforcement-Surface
Parity** — as a BUILD→loom proposal append. The `/sweep` earlier this session found the repo
fully converged; the only genuinely-uncaptured institutional learning was the generalizable
shape of the `#1456 → 0.14.3` privilege-escalation the redteam caught.

## What is codified (the insight)

When a fix promotes a field to an enforced **fail-closed authorization control at the
EVALUATION surface**, every **INDEPENDENT** validation surface for the same control —
especially a monotonic-tightening / re-registration / admission validator — MUST learn the
new dimension in the **same PR**, even when the surfaces share **no callee**. The existing
`security.md` § "Multi-Site Kwarg Plumbing" rule covers _one helper, N call sites_ and its
defense is `grep -rn 'helper_name('`; that grep **structurally cannot reach** a second
enforcement surface that shares no helper. This is the gap the new sub-section closes.
Prescribes a **single shared ordering function** consumed by both surfaces (can't drift) +
unrecognized→tightest fail-closed + a mechanical detection sweep.

## Disposition: proposal-only (not a local rule edit)

This is a **BUILD repo** → the codify deliverable is a `.claude/.proposals/latest.yaml`
append (Step 7a), which flows to loom Gate-1. I did **NOT** edit the local `security.md` /
`pact-governance.md` because `security.md` is `priority:0` baseline — a local edit would
trigger (a) `rule-authoring.md` Rule-10 proximity-band budget check (needs loom's
aggregate-emission `emit.mjs --dry-run` headroom, unrunnable here), (b) the Trust-Posture-Wiring
grandfather decision, and (c) the global-vs-variant placement call — all **loom Gate-1
responsibilities**. The proposal carries the **full proposed clause text** + these decisions
flagged for Gate-1.

## Not self-referential

`security.md` and `pact-governance.md` are **not** on `self-referential-codify.md` Rule 2's
allowlist (they govern SDK code behavior, not codify machinery) → the mandatory
posture-independent multi-agent redteam-with-tests round did **not** fire. The **recommended**
`/codify` gate review ran instead.

## Gate review (recommended, parallel)

- **reviewer** (`ae664655d99ca2236`) + **security-reviewer** (`a7057bb749cad9d12`), parallel.
- Both **verified the Origin against `enforcer.py` @ `146b754e1`**: `_check_clearance`
  (`:376`, eval) and `_validate_monotonic_tightening` (`:269`, registration) are independent
  functions sharing no callee; `_clearance_restrictiveness` rank `None→-1` (widest) /
  unrecognized→`len()` (tightest) at `:74-80`, consumed by the validator; 6 behavioral
  re-registration tests at `test_issue_1456_mcp_clearance_before_cost_flag.py:360-428`.
- Verdict: **APPROVE-WITH-FIXES**. All fixes applied to the proposed text BEFORE this commit:
  - **HIGH (disclosure):** scrubbed the **private** `esperie-enterprise/kailash-rs#1513`
    reference (the rule syncs to 30+ consumers) → generic "the kailash-rs Rust binding (same
    shape)". Per `upstream-issue-hygiene.md` MUST-2.
  - **C1 (correctness):** the `pact-governance.md` Rule 2 cross-ref now states MCP
    re-registration is a **DISTINCT mechanism** from envelope-intersection monotonicity (Rule
    2's actual subject), not that Rule 2 already covers it.
  - **MED/LOW (strengthen):** prescribe a single shared ordering function over
    match-by-convention; state unrecognized→recognized is a _widening_ that must raise; add a
    mechanical detection sweep; format as a `rule-authoring.md` MUST clause.

## Loom Gate-1 follow-ups (forwarded in the proposal)

1. Run the Rule-10 proximity-band headroom check (security.md is baseline) — extract-pair OR
   named-rationale OR adopt the pact-governance-primary placement alternative (path-scoped →
   Rule 10 does not fire).
2. Decide the Trust-Posture-Wiring grandfather retrofit for `security.md`.
3. Classify global-vs-variant + final placement (security.md-primary recommended).
4. **Scrub note:** the prior cycle's `coc-onboarding-specialist` proposal entry carries a
   private org slug in its context prose — scrub at Intake Disclosure Scrub.

## Receipts

- Codify lease: `lease_1782376834925_11f5adcc`, branch `codify/esperie-2026-06-25`, signed
  `codify-lease` record seq 3.
- Journal slot reservation: signed `journal-slot-reservation` record seq 4.
- Proposal: `.claude/.proposals/latest.yaml` — 5th `changes[]` entry (artifact: security),
  status `pending_review` (append per artifact-flow Append-Never-Overwrite; no reset needed).
- Codify-state: `.claude/learning/learning-codified.json` — `proposal_append` + `gate_review`
  actions (cycle 2026-06-25).
- Origin (ground truth): kailash-py #1456 → kailash-pact 0.14.3, PR #1459, commit `146b754e1`.

## For Discussion

1. **Placement counterfactual:** the proposal recommends security.md-primary (global) on
   principle-generality grounds, but the pact-governance-primary alternative (path-scoped, no
   baseline-budget pressure) is the budget-safe fallback. If Gate-1's headroom check shows
   codex-rs/gemini-rs inside the 15% proximity band, does the generality argument still win,
   or does the budget tension flip the decision to pact-governance-primary?
2. **Detection-sweep efficacy:** the codified mechanical sweep is "grep the tightening
   validator for the promoted field name." Would that have caught #1456 pre-redteam — or does
   it only work once you already know a field was promoted at the eval surface (i.e. is the
   real trigger still a human/redteam noticing the eval-surface promotion)?
3. **Cross-SDK parity:** the kailash-rs sibling (`#1513`, private) is the same shape. Should
   the loom-distributed rule carry an rs variant note, or stay language-neutral and let the rs
   BUILD repo's own redteam surface its instance?

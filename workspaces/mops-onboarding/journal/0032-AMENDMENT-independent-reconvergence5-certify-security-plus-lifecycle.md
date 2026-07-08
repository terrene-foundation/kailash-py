---
type: AMENDMENT
date: 2026-07-08
slug: independent-reconvergence5-certify-security-plus-lifecycle
relates_to: 0031-DECISION-ship-public-repo-unenrolled-plus-certify-gate-wiring
---

# AMENDMENT — Independent re-convergence #5: certify no-assist SECURITY divergence + lifecycle-walk gaps

Extends journal/0031. A fresh `/autonomize` + `/redteam`-to-convergence pass over the
mops-onboarding suite (7 rounds, ~18 parallel adversarial agents, distinct lenses per round). The
prior two convergences (PR #1622, #1623) had walked registration/symbol/prose surfaces; this pass
added the **operator-lifecycle user-flow walk** and the **command↔skill parity** lenses, which
surfaced what the earlier lenses structurally could not. All findings fixed to 0 CRIT/0 HIGH/0 MED
across 2 consecutive clean rounds. 13 edits across 8 files — working tree, UNCOMMITTED (BUILD-repo
commit gate).

## The one SECURITY-relevant finding (MED, fixed) — certify no-assist gate had a skill↔command divergence

`probe-phase-guard.js` (PR #355 security HIGH-1 closure, wired into committed settings.json in
PR #1623) blocks orchestrator `Read/Grep/Glob/WebFetch` while `.certify-in-probe-<vid>.lock`
exists, so an operator cannot be COACHED through the SOLO gate. The **command** (`certify.md`)
kept the lockfile through Phase C — "Probe exit (Phase C complete OR abandoned mid-gate)". The
**skill** (`42-certify`, the procedure-of-record) removed it "end of Phase B before transition to
Phase C", rationalizing "Phase C does not require retrieval". But Phase C's gate loop RE-RUNS the
probe on failed questions (`re-run probe on q`) — so an orchestrator following the skill tore down
the structural no-assist guard exactly during the retry loop the gate exists to protect, leaving
only prose refusal. Fix: the skill now states the lockfile PERSISTS through Phase C with a single
removal at Phase C exit (pass OR abandon), matching the command. The security gate PR #355/#1623
established was inert-during-retries on the skill-followed path; it now has teeth end-to-end.

## The other findings (all fixed + verified)

- **MED — enroll B3 premature "Enrolled" before roster PR merges** → "Enrollment PR opened. Once it
  merges to main, run /onboard" + branch-vs-main roster-visibility note; propagated to skill 44.
- **MED — MUST-7 cited for the grace/pending_verification mechanism** (defined in trust-posture
  MUST-6 § Grace Period Semantics) → re-pointed onboard.md + skill 41 to MUST-6.
- **LOW cluster** — 43→45 genesis-bootstrap cross-link; ecosystem C5 "TEAMMATE"/owner clarity
  (propagated to skill 43); `<id>`→`<display_id>`; certify footer stale line-count dropped;
  skills 43/44 raw `02-plans/` path genericized to `(loom-internal reference)`; certify receipt
  `::version`→`::bank_version` (schema-int vs operator-visible dated tag).
- **Verified NON-defects** (dispositioned, NOT edited): F4 onboard nag (resolveIdentity returns a
  solo identity when coordination OFF — no `blocked_into`, no nag); F5 certify "if not already
  rostered" (defensive conditional, not vestigial).

## Institutional lessons (do NOT regress)

- **command↔skill parity is its own lens.** The certify security divergence + the enroll/ecosystem
  print-string divergences (one pair introduced by fixing the command but not the skill) all lived
  in the command-vs-backing-skill delta — invisible to single-file review. When a command edit
  changes a print string / gate / precondition, the backing skill's mirror MUST move in the same
  shard (the security.md Multi-Site-Plumbing bug class, one abstraction up).
- **A wired security hook can still be inert on one execution path.** probe-phase-guard was
  correctly registered (PR #1623) yet the skill removed its trigger before the gate retry loop —
  "the hook is registered" ≠ "the guard covers the whole gated window". Verify the guard's
  lifecycle spans the ENTIRE protected activity, not just its opening.
- **Distributable invariant re-confirmed intact AFTER all edits** — the 13 doc edits touched no
  roster/settings/state surface; clones still resolve coordination OFF (roster PLACEHOLDER,
  root_commit 0000000, 0/6 enforcement hooks committed, probe-phase-guard=1, disclosure scan exit 0).

## Landing

Working-tree edits only (BUILD repo — commit stays with the user). Recommended: land on
`codify/esperie-2026-07-08` (or a fresh date-terminal codify branch) → PR → admin-merge, matching
the #1622/#1623 pattern. All 8 files are self-referential-codify surface, so the 7-round
multi-agent redteam-with-tests IS the self-referential gate (self-referential-codify.md Rule 1).

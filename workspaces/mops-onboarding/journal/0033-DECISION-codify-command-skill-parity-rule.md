---
type: DECISION
date: 2026-07-08
slug: codify-command-skill-parity-rule
relates_to: 0032-AMENDMENT-independent-reconvergence5-certify-security-plus-lifecycle
---

# DECISION — /codify: new rule `command-skill-parity.md` + BUILD→loom proposal

Codifies the institutional knowledge from re-convergence #5 (journal/0032). The security-relevant
`/certify` no-assist gate divergence + the two sibling print-string divergences all lived in the
delta between a command and its backing skill — a bug class no existing rule named. This /codify
extracts that lesson into a durable, cross-SDK-distributable rule.

## What was codified

1. **NEW rule `rules/command-skill-parity.md`** (`priority: 10`, `scope: path-scoped`, paths
   `.claude/commands/**` + `.claude/skills/**`, CLI-neutral). Three MUSTs: (1) a shared-step edit
   (Print/hand-off string, STOP/gate predicate, precondition, ordering, cited name, or guard
   lifecycle) MUST update the command↔skill mirror in the SAME shard; (2) `/redteam` MUST run a
   command↔skill parity sweep; (3) a cited security guard's lifecycle MUST span the ENTIRE protected
   window — "registered ≠ covers the whole window". Canonical 8-field Trust Posture Wiring; named
   length rationale (~214 lines). Origin scrubbed of the workspace slug + the cross-repo-ambiguous
   PR number for cross-SDK/public distribution.
2. **`rules/self-referential-codify.md`** — added `command-skill-parity` to the Rules allowlist
   (Rule 2 same-codify obligation). See § For Discussion for the adjudication.
3. **`commands/redteam.md`** — wired MUST-2's parity sweep into § 1 "Spec compliance audit" (kept
   ≤150 lines by extending the existing mechanical-checks line, no new line).
4. **`.claude/.proposals/latest.yaml`** — appended 2 entries (the new rule + the re-convergence #5
   onboarding-suite fixes) for BUILD→loom Gate-1 → cross-SDK + downstream distribution, status stays
   `pending_review` (append-never-overwrite per artifact-flow.md).

## Self-referential gate (self-referential-codify.md Rule 1) — converged

The proposal touches allowlisted surfaces (`self-referential-codify.md`, `redteam.md`, + the new
allowlisted rule) → the MANDATORY multi-agent redteam-with-tests ran regardless of posture: reviewer

- security-reviewer + cc-architect in parallel. R1: reviewer confirmed the rule accurate (Origin +
  9 cross-refs + DO/DO-NOT examples all ground-truth-verified); security-reviewer confirmed MUST-3
  sound + the `probe-phase-guard` mechanism real + no remaining fail-open + distributable invariant
  intact; cc-architect FAILED on 2 HIGH (missing `priority`/`scope` frontmatter; allowlist omission)
- 2 MED (length; redteam wiring) + LOWs. All fixed; cc-architect R2 = AUDIT PASS (one MED anchor
  mismatch, fixed same-shard). Converged.

## Alternatives considered

- **Extend an existing rule instead of a new one** — REJECTED. No existing rule covers command↔skill
  shared-step drift: cc-artifacts § No-Dangling-Cross-References governs reference RESOLUTION not
  content parity; security.md Multi-Site-Plumbing is code-kwarg-scoped. A distinct rule is warranted.
- **Allowlist disposition** — the author initially reasoned NOT-allowlisted (like
  `symbol-anchored-citations.md`); cc-architect overturned it by construction (the paths ARE the
  machinery surface, MUSTs fire on /codify output, it keeps allowlisted pairs in sync, its Origin is
  a guard-drop on an allowlisted command). Resolved TOWARD the gate per Rule 2 tiebreaker. The stale
  "not-allowlisted" text in the proposal was corrected (verify-claims-before-write — a now-false
  durable claim).
- **Length: trim <200 vs named rationale** — trimmed intro/Origin/Distinct-From first; the residual
  is the irreducible 3-MUSTs + mandatory 8-field wiring (~214), so added the precedented named
  rationale rather than cut load-bearing content.

## For Discussion

1. Counterfactual: the certify guard-drop was graded MED at redteam time, but the new rule's MUST-2
   escalates a guard-dropping divergence to HIGH. Should the go-forward HIGH grading be applied
   retroactively to reclassify the incident, or is the retrospective MED (what actually shipped) the
   honest record? (Left as MED in journal/0032; the rule prescribes HIGH going forward.)
2. The rule ships to loom for cross-SDK distribution because the same `/certify` skill/hook pair
   almost certainly exists in the Rust SDK + loom with the same pre-fix lockfile-timing bug. Should
   the certify security FIX itself (not just the rule) be filed as a cross-SDK issue now, or does the
   loom proposal carrying the onboarding-suite-fixes entry suffice to propagate it?
3. `emit.mjs` cannot run in this public un-enrolled repo (pre-existing absent
   `codex-mcp-guard/extract-policies.mjs`), so the frontmatter's Phase-0 emit-validation defers to
   loom. Is a BUILD-repo emit smoke-test worth restoring, or is loom-side validation the right single
   gate?

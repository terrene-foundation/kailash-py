# DECISION — /codify of kailash 2.27.0 release-drive learnings

**Date:** 2026-05-27
**Phase:** /codify (post-release)
**Session:** from_brief #1125 + delegate #1035 → redteam convergence → 2.27.0 release

## Context

The 2.27.0 release-drive shipped the from_brief default-deny security model
(#1125) + delegate hardening (#1035) to production PyPI, then surfaced two
CHANGELOG-accuracy defects during the TestPyPI rehearsal + post-publish verify.
This /codify captures the genuinely-new institutional knowledge.

## Decisions

1. **Appended two candidates to the BUILD→loom proposal** (`.claude/.proposals/latest.yaml`,
   preserving the existing #1086 + delegate-arc entries per artifact-flow.md
   append-not-overwrite):
   - `verify-claims-before-durable-write` (rule_update — git.md extension or
     new baseline rule): verify code-claims against ground truth before writing
     to CHANGELOG/commit/docs/rule; never trust a context-boundary-reconstructed
     claim or truncated output.
   - `from-brief-default-deny-security-pattern` (skill_update —
     skills/18-security-patterns): positive-allowlist ∩ registry + choke-point
     enforcement + inverse-completeness AST/MRO test + NaN/inf confidence gate;
     reusable cross-SDK.

2. **Wrote auto-memory** `feedback_verify_claims_before_durable_write.md` as the
   immediate in-repo stopgap (effective next session without waiting for the
   loom round-trip).

3. **Withdrew one candidate** (redteam cross-agent disagreement resolution) —
   already covered by self-referential-codify.md MUST-1 + agents.md
   closure-parity + redteam-integration.md; authoring would trip cc-artifacts.md
   Rule 10 duplicate-rule prevention.

## Why these and not more

The release-drive's substantive technical work (default-deny allowlist, NaN/inf
gate) was already codified in the shipped code + CHANGELOG + redteam receipts —
a future session reading the code inherits it. The verification-discipline
lesson is the one genuinely-new, not-derivable-from-code behavioral signal, and
it directly caused rework this session (2 correction PRs).

## Receipts

PRs #1184/#1186/#1187/#1188; tag v2.27.0; commits 5abc806f8 / b9b0a71ed /
ec2c99163 / 1a3dab318; proposal `.claude/.proposals/latest.yaml` changes[7,8]

- deferred[2].

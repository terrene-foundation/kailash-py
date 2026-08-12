---
priority: 10
scope: path-scoped
paths:
  - "**/CHANGELOG.md"
  - "**/RELEASE_NOTES.md"
---

# Release-Note Accuracy — A Note Describes The Diff, Not The Intent

A release note is read by people who cannot see the diff. When it describes work
that was planned but not landed, every downstream consumer plans an upgrade
against a capability that does not exist, and the error is discovered only in
production.

## MUST Rules

### 1. Every Release-Note Entry Cites The Merged Commit Or PR That Delivers It

Authors should include the SHA or PR number of the merged change where practical,
and in most cases that reference ought to be reachable on the release branch at
tag time. Writing an entry from a plan or a branch that has not merged is
generally discouraged and should be avoided where the schedule allows.

```markdown
# Example — entry names the merged change

- Bulk inserts now report per-row failures at WARN (#1841, merged 2026-07-30).
```

**BLOCKED rationalizations:** authors are expected not to rationalize omitting the
reference, and reviewers should push back on any justification offered for an
entry that carries no merged change behind it.

**Why:** An entry with no merged reference cannot be checked against the tag. This
matters because branches slip. When a branch slips it ships as a documented
feature anyway. Consumers then upgrade for a capability the release does not
contain, and the resulting support load is considerable.

## MUST NOT

- Describe a reverted change as delivered

**Why:** A revert leaves the note asserting behaviour the release does not have,
and the next reader treats the absence as a regression rather than a revert.

## Trust Posture Wiring

- **Severity:** `halt-and-report` at gate-review (release-specialist confirms each
  entry's reference is reachable on the tag); `advisory` at the hook layer per
  `hook-output-discipline.md` MUST-2.
- **Grace period:** 7 days from rule landing (2026-08-01 → 2026-08-08).
- **Cumulative posture impact:** same-class violations (an entry with no merged
  reference, or a reference unreachable at tag time) contribute to
  `trust-posture.md` MUST-4 cumulative-window math (3× same-rule in 30d → drop 1
  posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** GENERIC `regression_within_grace` emergency trigger
  per `trust-posture.md` MUST-4 (1× = drop 1 posture) — NO dedicated key; a
  reachability property is resolvable at the review layer. Named deviation per
  `trust-posture.md` Rule 8.
- **Receipt requirement:** SessionStart soft-gate `[ack: release-note-accuracy]`
  IFF `posture.json::pending_verification` includes this rule_id.
- **Detection mechanism:** Phase 1 (manual, gate-review) — release-specialist
  resolves every entry's SHA/PR against the tag before publishing. Phase 2
  (deferred) — no hook detector; fixtures land with it at
  `.claude/audit-fixtures/release-note-accuracy/` per `cc-artifacts.md` Rule 9.
- **Origin:** See § Origin.

Origin: 2026-08-01 — a release whose notes described two branches that had not
merged at tag time; both were discovered by a consumer upgrade rather than by the
release gate.

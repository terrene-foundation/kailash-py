---
type: DECISION
date: 2026-05-18
created_at: 2026-05-18T00:00:00Z
author: co-authored
session_id: codify-1086
session_turn: 1
project: _hygiene-2026-05-18
topic: /codify of issue #1086 — three MUST clauses from the Wave C SessionEnd-hook noise audit
phase: codify
tags:
  [codify, deployment, journal, sessionend-hook, trust-posture, artifact-flow]
---

# DECISION — /codify issue #1086: three root-cause rule clauses

## Context

Issue #1086 ("4 root-cause fixes from Wave C SessionEnd hook noise audit")
tracked 4 codify candidates surfaced by
`workspaces/_hygiene-2026-05-18/02-issue-835-journal-triage.md` — the triage
of issue-835's 33 `.pending/` journal entries, 28 of which were discarded as
SessionEnd-hook auto-captures unrelated to #835.

## Decision

This `/codify` (kailash-py BUILD repo → loom proposal, per `artifact-flow.md`
Step 7a) lands **candidates 1, 2, 4 only** — three MUST clauses across two
existing rule files. The deliverable is `.claude/.proposals/latest.yaml`
(status `pending_review`); the local `.claude/rules/` edits are the
"immediate local use" copy per `artifact-flow.md` BUILD Repo Rules.

| Candidate | Rule file             | Clause                                                                                       |
| --------- | --------------------- | -------------------------------------------------------------------------------------------- |
| 1         | `rules/deployment.md` | `## MUST: Eagerly-Imported Transitive Dependencies Are Declared By The Importing Package`    |
| 2         | `rules/journal.md`    | `### 1. Workspace journal/.pending/ MUST Be Gitignored At Repo Root`                         |
| 4         | `rules/journal.md`    | `### 2. SessionEnd Auto-Capture Routes By The Commit's Issue Trailer, Not The CWD Workspace` |

Each clause carries a Trust Posture Wiring section per `trust-posture.md`
MUST Rule 7.

## Scope decisions (user-gated this session)

- **Split-version rule excluded.** The prior `.session-notes` described F1 as
  including a `deployment.md` "split-version rule" (live evidence: a
  `kailash 2.22.0` PyPI≠source mismatch). Issue #1086 contains no such
  candidate. User chose "#1086's 4 candidates only" — the split-version rule
  is filed as its own issue with its own evidence rather than smuggled into
  this proposal's provenance.
- **Candidate 3 (hook code) deferred loom-side.** SessionEnd hook
  dedup-by-source_commit is hook CODE (`.claude/hooks/lib/`); per #1086's own
  acceptance criterion 2 it lands as a loom-side change. Candidate 4's rule
  clause is the paired _contract_ the candidate-3 hook must satisfy; the
  clause can ship ahead of the hook.

## Not self-referential

`deployment.md` and `journal.md` are NOT on the `self-referential-codify.md`
Rule 2 allowlist, so the multi-agent redteam-with-tests gate does not apply.
Standard validation ran: cc-architect (artifact-quality) + reviewer
(accuracy), both in parallel.

## Validation findings addressed

- cc-architect MED-2: journal.md clauses 1+2 lacked `**BLOCKED
rationalizations:**` blocks → added (4 verbatim phrases each).
- cc-architect LOW-1: journal.md Origin line was a bare date → expanded to
  cite the triage-report path.
- reviewer HIGH: candidate-4 §Why over-attributed all 28 discarded entries to
  CWD-misrouting → reworded to "discarded 28 as unrelated auto-captures"
  (the duplicate subset is a _dedup_ problem = candidate 3, not routing).
- reviewer MED: proposal's "#911/#912/#913/#917 (3 issues)" copied the source
  triage report's own internal inconsistency → corrected to the
  `1778398316957-*` cluster = #911/#912/#917.

## Gate-1 finding forwarded to loom (non-blocking)

`deployment.md` is now 296 lines, over `rule-authoring.md`'s 200-line limit.
The file never adopted the `guides/rule-extracts/<rule>.md` extract pattern.
The candidate-1 clause is authored compactly; the overage pre-existed this
codify (~240 lines before). RECOMMENDATION in the proposal: loom partitions
`deployment.md` into a neutral body + a `rule-extracts/deployment.md` guide as
a separate artifact-quality change (loom-side, out of #1086 scope).

## For Discussion

1. Counterfactual: if candidate 4's rule clause ships but candidate 3's hook
   never lands loom-side, the contract is documented but unenforced — does the
   advisory-severity wiring make that an acceptable interim state, or should
   the clause be held until the hook is ready?
2. The proposal forwards the deployment.md 200-line breach to loom rather than
   fixing it here. Is "BUILD repo flags, loom partitions" the right division,
   given the breach is now live in every session that loads deployment.md
   until loom acts?
3. Three of the four #1086 candidates are journal/hook-hygiene; only candidate
   1 is a release-pipeline rule. Does bundling them in one proposal help
   Gate-1 classification, or would two proposals (one per rule file) have been
   cleaner provenance?

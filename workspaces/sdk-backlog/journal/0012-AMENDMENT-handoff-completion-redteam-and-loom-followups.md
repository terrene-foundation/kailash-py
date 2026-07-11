# AMENDMENT — handoff-completion redteam results + loom Gate-1 follow-ups

**Date:** 2026-07-11
**Phase:** 05-codify
**Type:** AMENDMENT
**relates_to:** 0011-DECISION-codify-handoff-completion-and-rs1732-receipt

## Redteam (reviewer + cc-architect, parallel)

- **reviewer:** SUFFICIENT-WITH-FIXES — the rule prevents the target failure; distinct from siblings; baseline scope justified (fires in completion-reporting reasoning, no file-path anchor).
- **cc-architect:** COMPLIANT-WITH-FIXES — 8-field wiring, frontmatter pair, Rule-10 named-rationale, `global` classification all PASS.

## Fixes APPLIED this amendment (in `rules/handoff-completion.md`)

1. MUST-2 gained a 5-phrase BLOCKED corpus (rule-authoring Rule 2 — the clause targets a rationalizable behavior).
2. MUST-3 gained a 5-phrase BLOCKED corpus, incl. the standing-authorization phrase ("i already authorize you" still needs the per-action ask + journal per `repo-scope-discipline.md`).
3. MUST-1 BLOCKED list gained the local-todo/backlog variant (2 phrases).
4. MUST-1 body: the surface obligation now attaches to the moment done is CLAIMED (not deferred to a wrap-up that may not run); option (a) EXECUTE now binds the five `repo-scope-discipline.md` User-Authorized-Exception conditions (execute ≠ self-authorize).
5. Cross-refs: added `verify-resource-existence.md` MUST-2 alongside `verify-claims-before-write.md` for MUST-2's unverified-reference half.

## Durable-claim correction (verify-claims-before-write MUST-1)

The proposal context asserted the rule is "~130 lines"; verified actual is **98 lines** (pre-fix). Corrected in `.claude/.proposals/latest.yaml`. (An unverified count in a durable artifact — the exact class Rule 4d + verify-claims-before-write block; caught by cc-architect.)

## Loom Gate-1 follow-ups (loom-canonical design decisions — NOT made BUILD-side)

`self-referential-codify.md` + `verify-claims-before-write.md` are loom-canonical codify-discipline artifacts; their structure is loom's to decide when it ingests this proposal. Two flagged decisions:

1. **MUST-2 home.** reviewer Finding 7: MUST-2 (cross-repo artifact referenced-as-existing) is a durable-write-surface claim that could relocate to the path-scoped `verify-claims-before-write.md` (recovers baseline budget) OR stay here (it is integral to the handoff failure — the `rs#1714` misreference was half the incident). Kept here BUILD-side; loom decides at Gate-1.
2. **Self-ref allowlist membership.** cc-architect Finding 4: MUST-2 fires on codify-class output (journal/session-notes/PR bodies) — the same predicate that admitted `verify-claims-before-write.md` to the `self-referential-codify.md` Rule 2 allowlist. Genuine boundary case (center of gravity is session-completion, OUT; MUST-2 overlap points IN). Editing that allowlist is itself a self-referential codify (loom-canonical); flagged for loom to resolve explicitly at Gate-1 rather than resolved by silence.

## NOT done here (surfaced, per handoff-completion itself)

- **Eval-harness validation:** no rule eval-harness exists in this BUILD repo (`.claude/test-harness/` absent); it is loom-side. UNTESTED behaviorally; loom's `/codify` eval is the validation surface.
- **Loom ingestion:** the proposal is queued (`pending_review`); loom's `/sync-from-build` → `/codify` redteam → eval → Gate-1 classify → `/sync-to-use` is the pending downstream action. Tracking issue filed to make it a real surface, not a note.

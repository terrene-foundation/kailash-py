# DECISION: three-layer CI gate (pre-commit + script + regression test) for TODO-NNN reintroduction

**Date:** 2026-05-03
**Phase:** /implement (T5 of #781)
**Source commit:** `20f3fc20` — feat(ci): block reintroduction of untracked TODO-NNN markers (T5 of #781)
**Merged via:** PR #808

## What was decided

The cleanup workstream (T1–T4) scrubbed 272 markers across 5 packages. Without a gate, regression is one careless PR away. Three layers of enforcement land together so a regression slips through ONLY if BOTH local + CI fail simultaneously:

1. **Pre-commit hook** (`.pre-commit-config.yaml::no-untracked-todo-nnn`) — runs locally on every commit AND in pre-commit-ci on every PR (`ci.skip` list intentionally excludes this hook).
2. **Tier-2 regression test** (`tests/regression/test_no_untracked_todo_nnn.py`) — belt-and-suspenders against pre-commit/CI drift; asserts the same condition the hook enforces.
3. **Shared bash script** (`scripts/check_no_untracked_todo_nnn.sh`) — the SINGLE source of truth for the canonical regex + exclusion list. Both layers above call this script.

## Why this shape (alternatives considered)

- **Inline pre-commit `entry:` regex (rejected)** — pre-commit's YAML parser fragments on embedded colons (`:\\s*///`) in regex strings. Extracting to a script file dodges the YAML-parser fragility AND gives layer 2 a single import target.
- **GitHub Actions workflow (rejected)** — per `feedback_no_auto_cicd.md`, no auto-created CI workflows without explicit user approval. Pre-commit-ci's existing infrastructure carries the gate without a new workflow.
- **Tier-1 unit test (rejected)** — TODO-NNN scrub is a repo-wide invariant, not a unit. Tier-2 regression matches the scope.

## Canonical exclusion list

The script excludes by deliberate choice (every entry justified, no surface accidents):

| Pattern        | Reason                                                                          |
| -------------- | ------------------------------------------------------------------------------- |
| `:\\s*///`     | Rust doc-comments (defense-in-depth; out-of-language for Python source)         |
| `:\\s*//!`     | Rust inner doc-comments                                                         |
| `/build/`      | Transient build artifacts                                                       |
| `tracked:`     | Explicit `(tracked: gh#NNN)` link — Class 2 exception per zero-tolerance Rule 6 |
| `\\.egg-info/` | setuptools-generated SOURCES.txt — references filenames, not code comments      |

## Validation protocol (synthetic-PR)

Recorded inline in PR body and re-runnable:

1. Insert `# TODO-999: synthetic gate test` into `src/kailash/__init__.py` → BOTH hook + test fail.
2. Append `(tracked: gh#999)` to the same line → BOTH pass.
3. Revert.

The inverse-then-revert proves the gate cannot be silently bypassed (a one-direction check could match by accident).

## What this unlocks / blocks

**Unlocks:**

- Closing #781 with a permanent ratchet, not just a one-time scrub.
- Reusable methodology — codified to `.claude/skills/16-validation-patterns/validate-codebase-hygiene-markers.md` (per journal `0005-DECISION-codified-hygiene-marker-skill.md`) for any future canonical-regex hygiene gate.

**Blocks:**

- New TODO-NNN marker reintroduction without a `(tracked: gh#NNN)` annotation. Authors discover at pre-commit time, not at PR review time.

## Cross-refs

- `briefs/01-issue-781.md` — original 244-hit grep recipe + acceptance criteria.
- `02-plans/01-cleanup-architecture.md` — 4-class disposition catalog.
- `journal/0004-RISK-class-4-pattern-blind-spot.md` — risk register (did NOT manifest; all 89 T1 hits classified into 1a/1b/3).
- `.claude/skills/16-validation-patterns/validate-codebase-hygiene-markers.md` — codified methodology for reuse.

Per `rules/zero-tolerance.md` Rule 2 + Rule 6.

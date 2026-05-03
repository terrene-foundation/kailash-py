# DECISION: codify TODO-NNN methodology + three-layer gate as validation-patterns sub-file

**Date:** 2026-05-03
**Phase:** /codify (post-release)

## What was codified

Created `.claude/skills/16-validation-patterns/validate-codebase-hygiene-markers.md` — a reusable methodology for scrubbing internal-tracker markers from production source AND preventing future reintroduction via a three-layer canonical-regex gate.

The skill captures, as institutional knowledge:

1. **4-class disposition catalog** — Class 1a (header banner / inline-shipped), Class 1b (docstring provenance / see-also), Class 2 (active iterative TODO), Class 3 (mid-comment cross-reference). Per-class disposition rules + the ambiguous-Class-1/2 boundary heuristic (read ±10–30 lines after the marker).
2. **Three-layer hygiene gate pattern** — `.pre-commit-config.yaml` `local` hook + `scripts/check_<name>.sh` shared bash script + `tests/regression/test_no_untracked_<name>.py` Tier-2 regression test. Single source of truth (the script) so the canonical regex + exclusion list lives in one file.
3. **Synthetic-PR validation protocol** — inject + verify-fail + add-tracker + verify-pass + revert. The inverse-then-revert sequence proves the gate cannot be silently bypassed.
4. **Multi-shard cleanup strategy** — per-package sharding, comment-only edits cannot introduce import / signature / unbound-variable errors per `rules/zero-tolerance.md` Rule 1c (SHA-grounded provenance required for any pyright diagnostics that surface).
5. **Authoring gotchas** — YAML scalar fragility with embedded colons in pre-commit `entry:` (resolution: extract to script file); `grep -I` for binary-skip; `\.egg-info/` exclusion shape (NOT `/egg-info/` because the path segment is preceded by `_kaizen.`, not `/`).
6. **Release-cycle integration checklist** — patch bump per touched package, SDK dep pin sweep across all framework packages, single release-prep PR on `release/v*` branch, sequential tag pushes, clean-venv install verification.

## What was updated

- `.claude/skills/16-validation-patterns/SKILL.md` — added "Codebase Hygiene Validations" section in the sub-file index and extended the description's keyword list (`'codebase hygiene'`, `'TODO marker scrub'`, `'marker cleanup'`, `'three-layer gate'`, `'regex gate'`).
- Sub-file index also surfaces `orphan-audit-playbook.md` which was previously not indexed (companion validation pattern).

## Why these and not others

The session shipped a 6-package release. Most "patterns" surfaced during execution were already codified:

- Sibling-package release sweep: already in `rules/build-repo-release-discipline.md` Rule 1.
- SHA-grounded pre-existing diagnostic disposition: already in `rules/zero-tolerance.md` Rule 1c.
- Single release-prep PR for N packages: already in `rules/git.md` § Release-Prep PRs.
- Sequential tag pushes: already in `rules/deployment.md` § "Multi-Package Release Tags Pushed Individually".
- TestPyPI-skip exception for patch releases: already in `rules/deployment.md` § "TestPyPI Validation".

The genuinely-novel + reusable institutional knowledge is the marker-scrubbing methodology + gate pattern (above). Everything else was textbook execution against existing rules.

## Where this lands in the artifact flow

This is a BUILD-repo `/codify` writing to local `.claude/`. Per `rules/artifact-flow.md`:

- New skill sub-file is immediately usable in this BUILD repo.
- Proposal manifest (`.claude/.proposals/latest.yaml`) is appended for the next loom `/sync` cycle to classify (global vs Python-variant) and distribute to USE templates.
- Per `rules/cc-artifacts.md` Rule 6 — `/codify` MUST deploy `cc-architect` for validation. The new sub-file is 250 LOC (under 400-line skill limit), description extension is non-CLAUDE.md duplication.

## Cross-SDK note

The 4-class disposition catalog is language-agnostic — `TODO-NNN` markers are equally pervasive in Rust / Ruby / Go codebases. The three-layer gate translates directly:

- Pre-commit hook → identical (pre-commit is multi-language).
- Shared bash script → identical (shell is portable).
- Regression test → translate to `cargo test` / `rspec` / equivalent — same canonical-grep + assertion shape.

This warrants cross-SDK propagation when kailash-rs or future kailash-rb hits a similar marker-cleanup workstream. NOT auto-filed per `rules/upstream-issue-hygiene.md` Rule 1.

## Origin

Closes the codify loop for issue #781 (TODO-NNN cleanup workstream, May 2026, 272 markers triaged, 6 packages released).

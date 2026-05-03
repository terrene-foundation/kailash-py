# DISCOVERY: skills/project/ is a USE-repo pattern — wrong for BUILD repos

**Date**: 2026-04-12
**Workspace**: platform-architecture-convergence

## Finding

Previous `/codify` sessions wrote 5 skills to `.claude/skills/project/` in kailash-py (a BUILD repo). The `/codify` command says "canonical locations" — `project/` is a USE-repo pattern for downstream repos that can't upstream. BUILD repos should write directly to numbered skill directories and propose upstream via `.claude/.proposals/latest.yaml`.

## Root Cause

Multiple loom artifacts (`commands/sync.md`, `skills/management/sync-architecture-design.md`, `skills/management/coc-sync-mapping.md`) explicitly instructed `/codify` to output to `skills/project/`. These instructions conflated USE-repo and BUILD-repo behavior. Loom is fixing the source artifacts.

## Action Taken

- 4 project skills relocated to canonical directories (29-pact, 02-dataflow, 34-kailash-ml)
- 1 project skill deleted (duplicate of `rules/connection-pool.md`)
- `skills/project/` directory removed
- Proposal updated for loom `/sync py`

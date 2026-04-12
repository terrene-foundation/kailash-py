# DECISION — Single 2.0.0 release, not three-release split

**Date**: 2026-04-08
**Phase**: 02-todos → 03-implement

## What was decided

The red team recommended a three-release strategy: 1.8.1 (security patch, 1-2 cycles) → 1.9.0 (fabric cache from `workspaces/issue-354/`, 3-4 cycles) → 2.0.0 (remaining 12 PRs, 20-24 cycles). This would ship urgent security fixes to impact-verse within days.

The user overrode this: **"go with the full release, i want best cleanest most performant pristine implementation path and objective"**. Single branch, single commit series, single release.

## Why this is cleaner

The three-release split would have required:
- Three merge windows (each with conflict risk on shared files like `multi_tenancy.py`)
- Three changelogs, three TestPyPI validations, three downstream migration windows
- Rebasing `fix/dataflow-2.0` onto each merged release
- Coordinating with issue #354's existing branch

A single `fix/dataflow-2.0` branch with ordered phases (delete → secure → consolidate → build → wire → observe → test → ship) avoids all of that. The tradeoff: impact-verse waits until 2.0.0 lands instead of getting a 1.8.1 security patch sooner.

## Implementation order (followed in session)

```
Phase 0: Foundation (version, warning gates, lazy imports)        ← clean canvas
Phase 1: Delete dead code (~14,500 LOC)                           ← remove noise
Phase 2: Security fixes (9 CRITICAL vectors)                      ← close vectors
Phase 3: Consolidate (dialect, adapters, cache invalidation)      ← one of everything
Phase 4: Build real managers (transactions, connection)           ← replace façades
Phase 5-9: Wiring, async, observability, tests, ship              ← remaining
```

Each phase works on the output of the previous. Deletions precede additions — no merge conflicts between phases. Phases 0-4 shipped in 2 commits on 2026-04-08.

## Trade-off acknowledged

impact-verse (the primary production consumer) continues running on 1.7.1 with the known latent bugs until 2.0.0 lands. The user explicitly accepted this: security fixes are shipping in the same release as the architectural rewrite, which means longer cycle time but zero intermediate releases to maintain.

## Related

- `workspaces/dataflow-perfection/04-validate/03-amendments-applied.md` (Amendment 1)
- `workspaces/dataflow-perfection/02-plans/01-master-fix-plan.md`

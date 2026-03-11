# Kaizen Dependency Inversion — Rollback Plan

## Git Strategy

All M8 (Kaizen dependency inversion) work occurs on branch `feat/eatp-dependency-inversion`.

## Phased Approach

| Phase | Branch | What Changes | Rollback Action |
|-------|--------|-------------|----------------|
| 1 | `feat/eatp-dependency-inversion` | Add `eatp>=0.1.0` dependency | Remove from `pyproject.toml` |
| 2 | Same branch | Import rewrites + compatibility shims | `git revert` import change commits |
| 3 | Same branch | Hub file adapters | `git revert` adapter commits |
| 4 | Same branch | Full test verification | No rollback needed (verification only) |
| 5 | Separate PR (post-M8) | Remove original files + shims | Do not merge this PR until Phase 4 passes |

## Decision Criteria

| Test Failures | Action |
|--------------|--------|
| 0 failures | Proceed to merge |
| 1-10 failures | Triage individually, fix in eatp SDK or adapters |
| >10 failures | Revert branch, file bugs against eatp SDK |

## Escalation Path

1. Developer runs full Kaizen test suite after each phase
2. If failures > 10, revert to main and document issues
3. Original `kaizen/trust/` files are NOT deleted during M8
4. Shims (`from eatp.X import *`) preserve backward compatibility

## Pre-Migration Baseline

Before starting M8, record:
```bash
cd packages/kailash-kaizen
pytest tests/ --tb=no -q | tail -3 > /tmp/kaizen-baseline.txt
```

Compare after each phase:
```bash
pytest tests/ --tb=no -q | tail -3 > /tmp/kaizen-post-phase-N.txt
diff /tmp/kaizen-baseline.txt /tmp/kaizen-post-phase-N.txt
```

## Critical Rule

**Original trust files are preserved until Phase 5 (separate PR).** This ensures rollback is always possible by simply reverting the import changes.

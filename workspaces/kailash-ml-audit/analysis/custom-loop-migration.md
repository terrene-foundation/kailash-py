# Custom Training-Loop Migration Audit — Downstream Consumers

**Status:** COMPLETE, no migration needed.
**Audited:** 2026-04-17
**Scope:** `/Users/esperie/repos/dev/aegis/`, `/Users/esperie/repos/dev/aether/`, `/Users/esperie/repos/loom/kz-engage/`
**Auditor:** Explore agent, read-only

## Summary

**Zero production custom training loops** found across the three downstream consumers. The `specs/ml-engines.md` §3 MUST 2 clause (custom training loops BLOCKED outside research notebooks) will cause **no break** at the `kailash-ml 2.0` cut.

| Workspace | Torch imports | Lightning imports | Custom loops | pl.Trainer subclass | Status |
| --------- | ------------- | ----------------- | ------------ | ------------------- | ------ |
| aegis     | 0             | 0                 | 0            | 0                   | Clean  |
| aether    | 0             | 0                 | 0            | 0                   | Clean  |
| kz-engage | 0             | 0                 | 0            | 0                   | Clean  |

## What these workspaces actually are

- **aegis** (`/Users/esperie/repos/dev/aegis/`) — Agentic OS, FastAPI backend, governance + EATP integration. Not an ML training codebase.
- **aether** (`/Users/esperie/repos/dev/aether/`) — Kailash SDK docs / vibe layer. No ML code.
- **kz-engage** (`/Users/esperie/repos/loom/kz-engage/`) — Herald, multi-platform AI engagement engine (Telegram/Discord/Slack), Kaizen delegate + governance. No ML training code.

## Impact on the 2.0 break

The other 2.0 break concern — **primitive demotion to `kailash_ml.legacy.*`** (FeatureStore, ModelRegistry, TrainingPipeline, etc.) — ALSO does not affect these three workspaces, because they don't import `kailash_ml` symbols at all per the Explore agent's grep.

## Remaining migration scope

The `kailash-ml 2.0` break is now scoped to:

1. **Direct kailash-ml users** outside this audit (unknown, commercial consumers per `rules/independence.md`). These users migrate on their own schedule via release notes + `legacy/` shim + `DeprecationWarning`.
2. **Kailash-ml's own test suite** — internal tests that import the 18-engine surface will need updates as part of Phase F (2.0 cut, primitive relocation).

No blocking pre-requisite for Phase 3 (Lightning integration) from this audit.

## Disposition

**Proceed with Phase 3 without staging migration PRs for aegis/aether/kz-engage.**

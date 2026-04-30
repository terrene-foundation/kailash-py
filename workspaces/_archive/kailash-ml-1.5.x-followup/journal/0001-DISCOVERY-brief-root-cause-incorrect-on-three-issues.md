# 0001 — DISCOVERY — Brief Root-Cause Framing Incorrect On Three Issues

**Type:** DISCOVERY
**Date:** 2026-04-28
**Phase:** /analyze
**Workstream:** kailash-ml-1.5.x-followup

## What was discovered

The workspace brief at `briefs/01-context.md` had THREE distinct factual inaccuracies, each surfaced by a different parallel deep-dive agent:

### Inaccuracy 1 (Issue #699 root cause)

**Brief claim:** "ExperimentTracker (`packages/kailash-ml/src/kailash_ml/engines/experiment_tracker.py`) creates `_kml_model_versions` with the tenant-aware schema; ModelRegistry's CREATE uses an un-tenanted schema."

**Verified reality:** ExperimentTracker does NOT create `_kml_model_versions` at all. It creates `kailash_experiments / kailash_runs / kailash_run_metrics`. The canonical creator of `_kml_model_versions` is **numbered migration `src/kailash/tracking/migrations/0002_kml_prefix_tenant_audit.py:253`** with the tenant-aware shape. ExperimentTracker.create() triggers the migration as a side effect, which is what the user observed and conflated with direct creation. ModelRegistry's inline `CREATE TABLE IF NOT EXISTS` at `model_registry.py:204` is the drifted side, AND that inline DDL is itself a violation of `rules/schema-migration.md` Rule 1 (DDL outside migrations is BLOCKED).

**Source of correction:** Issue-#699 deep-dive analyst + my own grep verification of `_kml_model_versions` references across the entire codebase (`grep -rn '_kml_model_versions' packages/kailash-ml/src/ src/kailash/tracking/migrations/`).

### Inaccuracy 2 (Issue #700 file location)

**Brief claim:** `packages/kailash-ml/src/kailash_ml/engines/inference_server.py`

**Verified reality:** File is at `packages/kailash-ml/src/kailash_ml/serving/server.py:254`. The `engines/inference_server.py` path was deleted by W6-004 without a deprecation shim — confirmed via `__init__.py:611–613` comment in the kailash-ml package.

**Source of correction:** Issue-#700 deep-dive analyst.

### Inaccuracy 3 (Issue #701 silent-drop scope)

**Brief claim:** "Multiple 1.1.x kwargs (`title`, `n_batches`, `train_losses`, `val_losses`, `forward_returns_tuple`) dropped without replacement; `data=` silently ignored on `kind='dl'`."

**Verified reality:** The 1.1.x kwargs raise `TypeError` (signature is fixed-arity, not `**kwargs` — verified at `_wrappers.py:449–457`). The silent-drop is ONLY on `data=` when `kind="dl"`. The brief conflated three different behaviors (raised, silent-dropped, never-supported) into one.

**Bonus finding from same analyst:** `_wrappers.py:474–485` accepts FOUR additional `kind` literals (`clustering`, `alignment`, `llm`, `agent`) that have NO dispatch branch — every one falls through to `DLDiagnostics(subject)`. Same Rule 3 (silent fallback) violation class. Per `rules/autonomous-execution.md` § 4 "Fix-Immediately When Review Surfaces A Same-Class Gap Within Shard Budget", folded into the same fix scope.

**Source of correction:** Issue-#701 deep-dive analyst.

## Why this matters

Three independent factual inaccuracies in one brief is not a coincidence. The pattern: brief was authored from issue bodies + cross-SDK audit + general framing, without independent file:line verification. Without parallel deep-dives, `/analyze` would have inherited the brief's framing into `/todos` — every shard would have implemented the wrong fix on the wrong file with the wrong scope.

The structural defense is parallel verification: three deep-dive agents in parallel, each tasked to flag brief inaccuracies inline. The cost was bounded (4 analyst delegations); the benefit was three corrections that would have caused at least one shard re-launch in `/implement`.

## Implications for the architecture plan

- ADR-1 (#699) reframed: schema convergence is **migration-vs-application-code drift**, not engine-vs-engine. The fix is to DELETE the inline DDL (no replacement) and plumb tenant_id through ModelRegistry queries. Per `rules/schema-migration.md` Rule 1, the inline DDL was always wrong.
- ADR-2 (#700) file path corrected; no scope change.
- ADR-3 (#701) scope EXPANDED to cover the 4 unhandled `kind` literals. Same shard budget, same fix-immediately discipline.

## Codify candidate

Surfaced for codify (`02-plans/03-codify-candidates.md` § 3): **brief-claim verification protocol** — `/analyze` MUST run parallel deep-dive verification when issue count ≥ 3, with brief inaccuracies recorded in journal AND architecture plan as the gate before `/todos`.

## References

- `briefs/01-context.md` (uncorrected; left as historical artifact)
- `02-plans/01-architecture-plan.md` § Brief corrections (corrected synthesis)
- `01-analysis/04-issue-699-schema-fork-analysis.md` (analyst output)
- `01-analysis/05-issue-700-inferenceserver-analysis.md` (analyst output)
- `01-analysis/06-issue-701-diagnose-analysis.md` (analyst output)
- `01-analysis/cross-sdk-rs-audit.md` (cross-SDK clean verdict)

# DISCOVERY — Wave 2 self-verification: tenant isolation + a materialize round-trip limitation

**Date:** 2026-06-12
**Phase:** /implement → Wave 2 inter-wave gate G1 (INCOMPLETE — see below)
**Type:** DISCOVERY (orchestrator-run repros; the reviewer agents hit the account session limit)

## Why this is a self-verification, not a redteam receipt

Both Wave 2 redteam agents (reviewer `a013cc20b5403e5ef`, security-reviewer `addd6af0abfb185d7`)
**terminated on the account session limit** (resets 3pm Asia/Singapore) WITHOUT producing a verdict.
Wave 2 is therefore **implemented + orchestrator-self-verified, NOT formally redteam-converged.**
The next session MUST run the Wave 2 redteam to convergence before the wave is declared done.

## Blocking question RESOLVED by repro: NO cross-tenant read leak

Concern (orchestrator-found): the materialiser's dynamic `@db.model` has no `tenant_id` column
(annotations = `{id, entity_id, timestamp, fields, derived}`), so it looked like
`get_features` could not isolate tenants.

Repro (`/tmp/fm2_tenant_repro.py`, real file-backed SQLite): one `FeatureStore`, materialize
`tenant_id="acme"` (amounts [10,20]) AND `tenant_id="globex"` (amounts [777,888]) into the same
schema/table, then `get_features(schema, tenant_id="acme")`.
→ **Result: `[10.0, 20.0]` — ISOLATED.** globex rows NOT returned.

Mechanism: DataFlow's own tenant-context layer scopes both the materialiser's `express.upsert`
writes and the `get_features` → `ml_feature_source` reads (the `tenant_id` column is injected by
DataFlow's multi-tenancy, not by kailash-ml's `@db.model` annotations). The suspected leak is
**REFUTED.** The Shard-F agent's "returns globex rows" walk was its own self-diagnosed stale
express-cache artifact, not a real leak.

## New finding (NON-security): materialize→get_features round-trip is same-DataFlow-instance only

Repro (`/tmp/fm2_reopen_repro.py`): materialize on one `DataFlow` instance, close it, open a FRESH
`DataFlow` over the same SQLite file, `get_features(...)`.
→ **Raises** `FeatureSourceError: Node UserFeatListNode not found. Ensure model 'UserFeat' is
registered with DataFlow.` (reproduces WITHOUT erase — so it is not erase-related).

Root cause: the materialiser auto-registers a dynamic `@db.model` only in ITS OWN DataFlow
instance. A different instance (separate serving process, or re-construction) has not registered
the model, so `get_features` / `SchemaFeatureGroup` cannot read the persisted table. In the normal
single-process flow (materialize then get_features on the same store) it works (repro 1 passed).

**Disposition for next session's Wave 2 redteam (candidate severity MED/HIGH — usability/correctness,
NOT security):** options — (a) `get_features` / the store re-registers the materialiser's model on
demand when reading a materialised table; (b) the materialiser persists enough metadata for a fresh
store to re-register; (c) document the same-process constraint explicitly in the spec + raise a
clearer error. This is the existing 1.x `SchemaFeatureGroup` convention ("schema.name == a model the
USER registered") surfacing at the new write path; it predates this wave in spirit but the
materialize surface is what makes it user-reachable. NEEDS a redteam disposition, not a silent pass.

## Wave 2 commit state (on `feat/fm2-wave1-authoring-registry`)
- `fb434d40e` Shard B (`FeatureStore.materialize` + `FeatureMaterialiser`)
- `adb0a6b70` Shard B fix (drop vestigial `point_in_time`, zero-tolerance 3c — orchestrator self-review)
- `1e56ab123` Shard F (GDPR `erase_tenant`; also fixed a pre-existing registry `_ensure_model` DF-501 bug)
- `62b5fee57` probe-import pyright suppression touch-up

## Next-session resume plan (after 3pm reset)
1. Run Wave 2 redteam (reviewer + security-reviewer) to convergence; disposition the
   fresh-reopen model-registration limitation above; cite repros in this entry.
2. G2–G5 (learning, spec/todo, re-rank), then Wave 3: Shard C (online-store adapter) + Shard S6
   (graduate `dataflow-ml-integration.md`, correct stale `§11.2` citation paths, close #693).
3. Holistic terminal redteam across all merged shards (≥3-wave plan, `agents.md`).
4. PR + admin-merge to main, then `/release` (BUILD-repo discipline).

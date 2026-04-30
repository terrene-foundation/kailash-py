# Brief — kailash-ml 1.5.x Migration-Debt Followup

Filed 2026-04-28 from MLFP M5 notebook smoke-test sweep findings. Three GitHub issues (#699, #700, #701) surfaced same day, all rooted in the same 1.5.x release migration debt: half-finished schema migration, public-API deletion without deprecation, and silently-broken kwargs. 14 of 43 MLFP notebooks blocked by #699 alone; ex_2/03 + ex_7/05 hard-broken by #700; 14+ notebooks across ex_2/3/4 affected by #701.

Cross-SDK audit (`01-analysis/cross-sdk-rs-audit.md`, 2026-04-28) determined ZERO of three issues are present in `esperie/kailash-rs` — the Rust crate uses trait-object backends (no SQL), retains multi-model `InferenceServer { models: DashMap<...> }`, and has no `diagnose()` dispatcher. Python-only workstream.

## What the user reported

External MLFP M5 lesson sweep against `kailash-ml 1.5.1` produced three distinct hard-failure modes in canonical, documented patterns:

1. **`_kml_model_versions` schema fork (#699, CRIT).** `ExperimentTracker.create(store_url=db)` and `ModelRegistry(ConnectionManager(db))` pointed at the same SQLite store — the documented "track + register on one DB" pattern. ExperimentTracker's `CREATE TABLE IF NOT EXISTS _kml_model_versions` uses tenant-aware columns (`tenant_id, model_name, version, stage, run_id, ...`); ModelRegistry's CREATE uses un-tenanted columns (`name, version, stage, ...`). Whichever initializes first wins; the other's INSERT fails: `OperationalError: table _kml_model_versions has no column named name`. Half-finished migration: tracker moved to tenant-aware schema; registry's registration path did not. Source: `packages/kailash-ml/src/kailash_ml/engines/model_registry.py:197+`. The same file contains TWO query column-set conventions: lines 240/250/509/732/909 query `name = ?`; lines 997/1004 query `model_name = ?`.

2. **`InferenceServer` hard break (#700, CRIT).** 1.5.x dropped `InferenceServer(registry=, cache_size=)` + `await server.warm_cache([names])` + `await server.load_model(name, model)` and replaced with `InferenceServer.from_registry(name, registry=)` + `InferenceServerConfig` — no deprecation cycle, no shim, no migration doc. Every 1.1.x call-site hard-breaks: `TypeError: InferenceServer.__init__() got an unexpected keyword argument 'cache_size'`. Architectural shift (one-server-many-models → one-server-one-model) requires K8s topology rethink, not just call-site rewrite.

3. **`diagnose()` PyTorch + DataLoader silently dropped (#701, HIGH).** The 1.5.x `diagnose()` entry-point accepts a `data=` kwarg. When `kind="dl"`, the function returns a bare `DLDiagnostics` object and `data=` is silently ignored — documented kwarg with zero effect. `kind="classifier"` rejected (must be `kind="classical_classifier"`); aliases unsupported. Multiple 1.1.x kwargs (`title`, `n_batches`, `train_losses`, `val_losses`, `forward_returns_tuple`) dropped without replacement. DLDiagnostics has no public method that consumes a DataLoader. Worst class of API smell — a parameter with no effect.

## Issues bundled into this workspace

| #       | Severity | Title                                                                                | Surface                                                                             |
| ------- | -------- | ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| **699** | CRIT     | `_kml_model_versions` schema fork — tracker tenant-aware, registry un-tenanted       | `packages/kailash-ml/src/kailash_ml/engines/model_registry.py:197+, :240, :997`     |
| **700** | CRIT     | `InferenceServer` removed `cache_size` + `warm_cache` + `load_model` w/o deprecation | `packages/kailash-ml/src/kailash_ml/engines/inference_server.py`                    |
| **701** | HIGH     | `diagnose(kind="dl", data=...)` silently drops `data`; old kwargs gone               | `packages/kailash-ml/src/kailash_ml/diagnostics/__init__.py`, `…/dl_diagnostics.py` |

## Why one workspace

- **Shared specialist** — every fix belongs to ml-specialist + analyst.
- **Shared bug class** — three faces of one root cause: 1.5.x release shipped without preserving 1.1.x → 1.5.x migration discipline. #699 = forgot to migrate the second writer. #700 = forgot to ship a deprecation adapter. #701 = forgot to wire the new dispatch param OR raise on unknown.
- **Shared release cycle** — all three land in `kailash-ml`. One release-prep PR. Likely 1.5.2 (regression patches) for #699; 1.6.0 (deprecation adapter is additive but signals architectural shift) for #700; #701 splits — `data=` wiring is regression-class (1.5.2), alias additions are minor (1.6.0).
- **Shared test-discipline lesson** — all three were caught by external smoke-test, not by the SDK's own Tier-2 coverage. Tells us the canonical "tracker + registry on one store", "multi-model server", and "PyTorch + DataLoader diagnose" pipelines lack DOCS-EXACT regression tests per `rules/testing.md` § "End-to-End Pipeline Regression".

## What "done" looks like

1. **#699 closed** — single canonical schema for `_kml_model_versions` (tenant-aware everywhere; matches what ExperimentTracker already creates). `ModelRegistry._create_registry_tables` + `register_model` + `_get_version_row` + `set_stage` + every query in the file moved to `(tenant_id, model_name, ...)`. Numbered migration if the schema is on-disk for existing users. Tier-2 regression test running BOTH engines against the same `store_url` — DOCS-EXACT pipeline per `rules/testing.md` § "End-to-End Pipeline Regression".

2. **#700 closed** — deprecation adapter accepts 1.1.x signature: `InferenceServer(registry=, cache_size=)` + `warm_cache([names])` + `load_model(name, model)`. Internally lazy-constructs one `InferenceServer.from_registry(name, registry=)` per model. Emits `DeprecationWarning` with explicit migration path. Plus `from_registry_many(names, registry=)` helper returning `dict[str, InferenceServer]` for the canonical multi-model use case. CHANGELOG entry documenting both the architectural shift and the migration steps. Tier-2 regression covering BOTH the deprecated and canonical surfaces.

3. **#701 closed** —
   - `kind="dl"` MUST consume `data=` end-to-end: pass to `DLDiagnostics(subject, data=dataloader, tracker=tracker)`; expose `.report(data=loader)` (or `.evaluate()`) producing the diagnostic.
   - Add `kind="classifier"` → `classical_classifier` and `kind="regressor"` → `classical_regressor` aliases; both common in user code.
   - Either (a) accept the 1.1.x kwargs (`title`, `n_batches`, `train_losses`, `val_losses`, `forward_returns_tuple`) and route through to `DLDiagnostics`, OR (b) raise `TypeError` on unknown kwargs (no silent drop) AND document equivalents in CHANGELOG migration section.
   - Tier-2 regression covering PyTorch model + DataLoader through `diagnose(kind="dl", data=loader)` end-to-end, asserting the diagnostic actually consumed the loader.

4. **Release of `kailash-ml 1.5.2` + `1.6.0`** — 1.5.2 patches the regression-class bugs (#699 schema, #701 silent-drop wiring); 1.6.0 ships the deprecation adapter (#700) and `kind=` aliases (#701). PyPI-published; clean-venv install verified.

5. **Cross-SDK inspection signed off** — already complete (`01-analysis/cross-sdk-rs-audit.md`); no kailash-rs followup work owed for this workstream.

6. **CHANGELOG entries** documenting (a) what 1.5.x dropped and (b) the canonical 1.1.x → 1.5.x migration path for every removed surface.

## Constraints

- **No silent fallbacks** (`rules/zero-tolerance.md` Rule 3) — `diagnose(data=...)` ignoring its arg IS the silent-fallback bug. Fix must either consume `data` or raise.
- **No half-implementations** (`rules/zero-tolerance.md` Rule 6) — `_kml_model_versions` is half-migrated. ModelRegistry's two query column-sets in one file IS the half-implementation. Either both writers use one schema, or the schema fork is acknowledged with a structural assertion at construction time (raise if both engines target same store).
- **No workarounds for SDK bugs** (`rules/zero-tolerance.md` Rule 4) — these are SDK source bugs; fix at the SDK, not in MLFP lesson code.
- **No mocking in Tier 2/3 tests** (`rules/testing.md` § 3-Tier Testing) — the regression tests MUST exercise real SQLite + real torch.nn modules + real DataLoader.
- **End-to-End Pipeline Regression** (`rules/testing.md` MUST) — every canonical pipeline the docs/tutorials teach (tracker+registry shared store; multi-model server; PyTorch diagnose) MUST have a Tier-2+ test executing DOCS-EXACT code.
- **Tenant isolation preserved** (`rules/tenant-isolation.md`) — schema unification picks the tenant-aware variant; multi-tenant is non-negotiable.
- **Specs authority** (`rules/specs-authority.md`) — `specs/ml-tracking.md`, `specs/ml-registry.md`, `specs/ml-serving.md`, `specs/ml-diagnostics.md` are touched. Per §5b, edits to any one trigger sibling re-derivation across the `ml-*.md` family if the change is structural; #699 schema convergence IS structural; expect a sweep.
- **Deprecation discipline** — #700 introduces the meta-lesson "public-API deletion without deprecation cycle." Must encode in `/codify` as a rule candidate (likely an `api-deprecation.md` rule) — see Codify Candidates below.

## Out of scope (sibling workstreams)

- **kailash-rs cross-SDK fixes** — verified ABSENT in `01-analysis/cross-sdk-rs-audit.md`. No follow-up at `esperie/kailash-rs`.
- **DataFlow connection-lifecycle hardening** — already shipped in `dataflow-prod-incident` workspace (kailash 2.12.0, kailash-dataflow 2.4.0, PRs #702/#703/#704).
- **Pre-existing pyright diagnostics on `dataflow/core/engine.py`** — deferred per `dataflow-prod-incident/journal/0006-GAP`. New workspace candidate (`dataflow-engine-pyright-cleanup`) flagged but not opened.
- **kailash-ml 1.5.0 W7-001 lineage** — already shipped (#657 closed in 1.5.0). Out of scope unless lineage tests touch the unified `_kml_model_versions` schema.

## Codify candidates (preview — confirm at `/codify` after redteam)

Three institutional learnings worth examining for promotion to global rules:

1. **API deprecation cycle discipline** (#700 origin). Public-API removal without `DeprecationWarning` shim for ≥1 minor cycle is the failure mode. Existing rules cover stubs and silent fallbacks but no rule encodes deprecation discipline. Likely candidate: extend `rules/zero-tolerance.md` with a "no public-API deletion without shim" clause, OR file a new `rules/api-deprecation.md` rule. Cross-SDK audit suggests the same gap could surface in Rust if `pub fn` removal happens without `#[deprecated(since=...)]` — global classification.

2. **Shared-table schema-fork detection** (#699 origin). Two writers, one table, two CREATE schemas, IF-NOT-EXISTS guard masks the second's failure to create. Existing rules cover identifier safety and migration ordering but not "two writers initializing the same table differently." Likely candidate: extend `rules/schema-migration.md` with a "single CREATE TABLE owner per table" clause + Tier-2 test mandate that initializes every paired writer pair.

3. **Silent-drop kwargs as zero-tolerance violation** (#701 origin). A documented kwarg that silently does nothing IS the silent-fallback failure mode at API surface level. Already covered by `rules/zero-tolerance.md` Rule 3 in spirit; worth an explicit clause naming "kwarg accepted with zero effect" as BLOCKED. Likely small extension to existing rule.

These are noted now so `/codify` has the trail; final classification + drafting happens at `/codify` after `/redteam` confirms the learnings hold.

## References

- Issue #699 — https://github.com/terrene-foundation/kailash-py/issues/699
- Issue #700 — https://github.com/terrene-foundation/kailash-py/issues/700
- Issue #701 — https://github.com/terrene-foundation/kailash-py/issues/701
- Cross-SDK audit — `01-analysis/cross-sdk-rs-audit.md` (this workspace)
- MLFP M5 trigger — referenced in all three issue bodies; sweep date 2026-04-28
- Sibling workspace — `workspaces/dataflow-prod-incident/` (closed; same MLFP M5 trigger, different package)

# kailash-ml Changelog

## [2.2.2] — 2026-06-23 — numba floor fixes Python 3.12+ fresh-install (#1430)

Patch release. Dependency-constraint fix — no public API change.

### Fixed

- **`numba>=0.61` floor added** so a fresh `pip install kailash-ml` on Python
  3.12/3.13/3.14 no longer backtracks to `numba 0.53.1` → `llvmlite 0.36.0`
  (which has no wheel for those Pythons and fails to build from source with
  `RuntimeError: Cannot install on Python version 3.x`). `numba` is pulled
  transitively by `umap-learn`/`pynndescent` for `UMAPTrainable`; the floor
  forces `llvmlite>=0.44` (wheels for all supported Pythons). Minimum version
  floor per `rules/dependencies.md` (NOT a cap). Verified: 3.12/3.13/3.14
  fresh-resolve → `llvmlite 0.47.0`, real install + import OK. (#1430)

## [2.2.1] — 2026-06-13 — URL credential masking consolidated onto core helper

Patch release. Internal refactor — no public API change. Replaces three
hand-rolled URL-masking helpers with the canonical core `mask_url`.

### Changed

- **URL credential masking consolidated onto the core single-source-of-truth.**
  The three internal URL-masking helpers (`features.online_store._mask_redis_url`,
  `dashboard.cli._mask_db_url`, `tracking.tracker._mask_url`) are removed in favor of
  `kailash.utils.url_credentials.mask_url` (`rules/security.md` § Credential Decode Helpers;
  `rules/observability.md` Rule 6). Masking is identical for credentialed URLs
  (`redis://u:p@host:port/db` → `redis://***@host:port/db`) and now additionally masks
  credentials passed via URL query parameters. One subtle change: a **credential-less**
  URL on a log/error surface (e.g. `redis://127.0.0.1:1/0`) now renders **verbatim**
  (nothing to mask) instead of the prior forced `redis://***@127.0.0.1:1/0`.

## [2.2.0] — 2026-06-13 — Feature-store M2 Wave 3: online-store adapter + spec graduation (#693)

Minor release. Completes the M2 feature-store (FM2 Wave 3 of 3): the Redis-backed
online feature-store read path and the self-healing model re-registration that lets
a fresh `FeatureStore` instance recover a previously-registered model. Backward-compatible —
purely additive public API; the 2.0.0 canonical read surface (`FeatureStore.get_features`)
and the 2.1.0 authoring/registry/materialize surfaces are unchanged.

### Added

- **Online feature-store adapter** (`kailash_ml.features.online_store.OnlineFeatureStore`) —
  graduates spec §11.4: low-latency online reads backed by Redis, with the offline store
  as the durable source of truth. Raises `OnlineStoreUnavailableError` when the backend is
  unreachable so serving code can `try/except` and degrade to the offline read path.
- **`OnlineStoreUnavailableError`** re-exported from `kailash_ml.errors` (canonical source:
  `kailash.ml.errors`, requires `kailash>=2.31.0`).
- **Self-healing model re-registration** — a fresh `FeatureStore` instance re-registers a
  model on first read against an existing registry row instead of failing, so serving
  processes that did not author the model can still read it.

### Changed

- Core dependency floor raised to **`kailash>=2.31.0`** (was `>=2.30.0`) — 2.2.0 imports the
  new `OnlineStoreUnavailableError` first published in `kailash` 2.31.0.

## [2.1.1] — 2026-06-13 — Fix core dependency floor (feature-store error classes)

Patch release. Corrects the `kailash` dependency floor so the feature-store
surface installs and imports correctly.

### Fixed

- **`kailash>=2.30.0` dependency floor** (was `kailash>=2.16.0`). The 2.1.0
  feature-store surface re-exports the ML error hierarchy from
  `kailash.ml.errors` (via `kailash_ml/errors.py`), including the feature-store
  subclasses `FeatureStoreError`, `FeatureGroupNotFoundError`,
  `FeatureVersionImmutableError`, `FeatureVersionNotFoundError`,
  `FeatureEvolutionError`, `CrossTenantReadError`, `UnsupportedFamily`, and
  `UnsupportedPrecision`. Those classes were added to core by the FM2 Wave 1+2
  merge and first published in **`kailash` 2.30.0** — which was released after
  `kailash-ml` 2.1.0. With the old `>=2.16.0` floor, `pip install
kailash-ml==2.1.0` against any core in `[2.16.0, 2.29.4]` raised `ImportError`
  on first touch of the feature store. The corrected floor pins the version that
  actually carries the symbols. (`kailash-ml` 2.1.0 is yanked from PyPI.)

## [2.1.0] — 2026-06-13 — Feature-store M2: authoring, registry, materialize, GDPR erase (#1302)

Minor release. Adds the M2 feature-store authoring + materialization + governance
surfaces (FM2 Waves 1+2 of 3). Backward-compatible — purely additive public API; the
2.0.0 canonical read surface (`FeatureStore.get_features`) is unchanged. Wave 3
(online-store adapter + spec graduation closing #693) follows in a later release.

### Added

- **`@feature` decorator + public `FeatureGroup`** (`kailash_ml.features`, re-exported
  from `kailash_ml`). `@feature` wraps a function returning a `polars.Expr` into a
  frozen, content-addressed `FeatureDefinition` (declarative — no compute at decoration).
  `FeatureGroup` is the user-facing authoring object (HAS-A `FeatureSchema`; satisfies
  the `dataflow.ml_feature_source` duck-type via `.name` / `.multi_tenant` /
  `.classification` / `.materialize`). Raises `FeatureGroupNotFoundError`.
- **`FeatureRegistry`** (`kailash_ml.features.FeatureRegistry`) — DataFlow-backed durable
  store of authored groups with **per-tenant version immutability** enforced two ways:
  DB-level `UNIQUE(tenant_id, name, version)` (via `@db.model` auto-migrate) + content-hash
  cross-check. Raises `FeatureVersionImmutableError` / `FeatureVersionNotFoundError` /
  `FeatureEvolutionError`. Tenant-isolated; forward version-bump evolution via
  `FeatureSchema.with_features(bump_version=True)`.
- **`FeatureStore.materialize(group, data, *, tenant_id)`** + composed `FeatureMaterialiser`
  — write-through materialization. Computes `@feature`-derived columns via `dataflow.transform`,
  persists through DataFlow Express `upsert` against an auto-migrated `@db.model` (no raw SQL),
  registers the dataset lineage hash via `dataflow.hash`. Idempotent re-materialise (deterministic
  content-addressed row id); per-row event-time read from the schema `timestamp_column` for
  point-in-time-correct reads. Cross-tenant materialise raises `CrossTenantReadError`; REDACT-classified
  columns are redacted on the return frame while the backing store holds real values.
- **`FeatureStore.erase_tenant(*, tenant_id=None, force=False)`** — GDPR tenant erasure. Deletes
  every materialized feature-table row + every `FeatureRegistry` row for a tenant through DataFlow
  Express (no raw SQL); fail-closed on partial erase (`FeatureStoreError` flagging PARTIAL ERASE,
  never silent half-erase); reuses the canonical `ErasureRefusedError`; emits a tenant-fingerprinted
  audit log line (no raw tenant id / PII). Idempotent re-erase returns zero counts.

### Changed

- **`kailash-dataflow` dependency floor `>=2.0.11` → `>=2.11.3`.** `FeatureStore.materialize` /
  `get_features` route through `dataflow.transform` / `dataflow.hash` / `ml_feature_source`
  (in `dataflow.ml`), which ship in kailash-dataflow 2.11.3. Installing kailash-ml 2.1.0
  against an older dataflow would fail at materialize/read time.

### Notes

- Tenant scope is **fingerprinted** (never raw) on every feature-store log + exception surface
  (observability Rule 4/8). Wave-2 redteam converged over 2 consecutive clean rounds (reviewer +
  security-reviewer). 66 feature-store integration tests + 146 unit tests pass.

## [2.0.1] — 2026-06-08 — `kailash-kaizen` floor consistency (#1183)

Patch release. **No source changes** — diff is strictly `pyproject.toml` dependency-floor edits + `__version__` anchor + this CHANGELOG entry.

### Changed

- **`[kaizen-judges]` and `[kaizen-observability]` extras: `kailash-kaizen>=2.7.5`** (was `kailash-kaizen>=2.7`). The two extras drifted from the `>=2.7.5` floor used elsewhere in the same manifest (`[agents]`); `>=2.7.5` is the consistent floor and additionally pins past the known-bad kaizen 2.7.0–2.7.4 clean-venv `ModuleNotFoundError` class.

### Notes

- No public-API changes; no behavior changes. Surfaced by the new `tools/check_pin_consistency.py` first-party pin-drift gate (#1183).

## [2.0.0] — 2026-06-07 — BREAKING: FeatureStore canonical cutover (#643 step 3)

Top-level `from kailash_ml import FeatureStore` now resolves to the **canonical
1.0+ read surface** `kailash_ml.features.FeatureStore`, completing the issue #643
migration whose deprecation bridge shipped in 1.7.2 and whose retrieval blocker
was fixed in 1.7.5/1.7.6 (#1241). The legacy write-capable engine is **not
removed** — it remains importable via its explicit module path.

### Changed (BREAKING)

- **`from kailash_ml import FeatureStore` resolves to `kailash_ml.features.FeatureStore`.**
  Constructor changes from the legacy `FeatureStore(conn: ConnectionManager, *,
table_prefix=...)` to the canonical `FeatureStore(dataflow: DataFlow, *,
default_tenant_id=None)`. Any caller constructing the top-level symbol with a
  `ConnectionManager` now raises `TypeError`. The canonical surface is
  **read-only** (`get_features` + cache-key helpers); the legacy write/registry/
  training-set operations are not present on it.

### Removed

- **The 1.7.2 bridge `DeprecationWarning`** emitted on top-level `FeatureStore`
  access is removed — the warning has served its deprecation cycle (1.7.2 →
  1.7.6) and the resolution it warned about has now flipped.

### Migration

- **Reads:** swap the construction site — `FeatureStore(df, default_tenant_id=...)`
  (or `default_tenant_id=CANONICAL_SINGLE_TENANT_SENTINEL` for single-tenant) and
  call `get_features(schema, timestamp=None, *, tenant_id=None)`.
- **Writes:** the canonical store owns no DDL. Materialise features as a
  `@db.model` whose name equals `schema.name`, write rows with `express.create`,
  and read them back through `get_features`. Full recipe in `MIGRATION.md`.
- **`get_training_set` / `get_features_lazy` / `list_schemas`** (and all legacy
  write ops) have no canonical equivalent yet (M2-deferred per
  `specs/ml-feature-store.md` § 11). Callers that need them keep the explicit
  import `from kailash_ml.engines.feature_store import FeatureStore`, which is
  retained and unchanged.

### Fixed

- **README FeatureStore section** documented three phantom methods (`ingest`,
  `get_features_at_time`, `list_feature_sets`) that exist on neither surface;
  corrected to the real canonical + legacy operation sets. `docs/guides/02-feature-pipelines.md`
  rewritten from a fictional `put`/`get` API to the validated canonical pattern.

## [1.7.6] — 2026-06-03 — fix: get_features without a timestamp returns latest-per-entity (#1241 follow-up)

Follow-up to 1.7.5. The 1.7.5 `SchemaFeatureGroup` adapter gated its latest-per-entity dedup on `point_in_time is not None`, so `get_features(schema)` with **no** timestamp returned **every historical row** (duplicate entities) instead of the latest row per entity. The `get_features` contract is "when timestamp is None the latest values are returned" — one feature vector per entity. Caught by the 1.7.5 published-wheel end-to-end verification walk (the unit/integration tests had used one row per entity, so the dedup gap was unobservable).

### Fixed

- **`get_features(schema)` (no timestamp) now returns the latest row per entity (#1241).** Dedup-to-latest now runs whenever the schema declares a `timestamp_column`, realising both halves of the contract: `point_in_time` given → as-of-T value (window-bounded then deduped, unchanged); `point_in_time` None → latest value per entity. Happy-path + regression tests strengthened to use multiple observations per entity (a guard the prior tests lacked).

## [1.7.5] — 2026-06-03 — fix: canonical FeatureStore.get_features now retrieves features (#1241)

The canonical 1.x feature-retrieval surface, `FeatureStore.get_features(...)`, previously raised on **every** call and is now functional. This unblocks the 2.0.0 cutover (#643 step 3), which depends on a working canonical retrieval surface.

### Fixed

- **`FeatureStore.get_features(...)` retrieves features instead of always raising (#1241).** `get_features` forwarded a declarative `FeatureSchema` to `dataflow.ml_feature_source`, but that binding duck-types on a FeatureGroup-shaped `.materialize()` the schema does not expose (the `FeatureGroup` class is M2-deferred per `ml-feature-store.md §11`). The schema therefore failed the binding's shape check and every call raised `FeatureStoreError`. The store now wraps the schema in an internal `SchemaFeatureGroup` read adapter that reads the backing DataFlow table named after the schema (`schema.name` == `@db.model` name, per the spec §1.1 "thin bridge, owns no DDL" framing). **No public-API change** — `get_features`'s signature is unchanged; the adapter is internal.
  - **Point-in-time correctness (`§6.2 MUST-1`)** is realised framework-first with no raw SQL: the DataFlow read pushes the `timestamp_column <= point_in_time` window down via the MongoDB `$lte` operator, and polars computes the latest-row-per-entity as-of dedup (`sort(ts, descending, nulls_last).unique(subset=entity, keep="first")`).
  - **Multi-tenant scoping** binds the DataFlow tenant context (`db.tenant_context.switch(...)`) so `express.list` auto-scopes — the DataFlow-native mechanism, correct under both the `schema` and `row` isolation strategies.

### Changed

- **Spec correction (`specs/dataflow-ml-integration.md`, `specs/ml-feature-store.md §4.1`):** retracted a phantom "consumed end-to-end (verified positive at audit finding F-E2-23)" claim — `get_features` had never worked before #1241 — and reframed the point-in-time contract to describe the real DataFlow-window-filter + polars-as-of split.

### Notes

- **Scale bound (documented):** the polars-dedup as-of materialises the full `timestamp <= T` candidate window in memory — correct for 1.x-scale tables. DB-side windowed as-of (no in-memory cap) is M2; it needs a DataFlow aggregation primitive not yet exposed without raw SQL.
- **Cross-SDK:** the kailash-rs `FeatureStore` is a `save`/`load` artifact store (no `get_features` / `FeatureGroup` / DataFlow-bridge), so the #1241 bug class is structurally impossible there — no cross-SDK issue filed.

## [1.7.4] — 2026-05-09 — hotfix: aiosqlite restored to core deps

Hotfix release closing a pre-existing latent dependency gap exposed by the 1.7.3 clean-venv install verification (`pip install kailash-ml==1.7.3` → `ModuleNotFoundError: No module named 'aiosqlite'` at module-import time).

The bug existed in 1.7.2 as well — anyone who installed kailash-ml against a venv without aiosqlite transitively present would have hit the same import failure. Most users were unaffected because they install kailash-dataflow with the `[sqlite]` extra or kailash with `[db-sqlite]` first.

### Fixed

- **`pip install kailash-ml` now imports cleanly** — `aiosqlite>=0.19.0` is now a **core** dependency. `kailash_ml.tracking.storage.__init__` imports `SqliteTrackerStore` at module-scope, which transitively chains through `kailash.core.pool.sqlite_pool` to a bare `import aiosqlite`. The chain is unconditional from `import kailash_ml`, so aiosqlite is effectively required. The kailash 2.18.0 `[db-sqlite]` extra and the kailash-dataflow 2.9.0 `[sqlite]` extra both declare aiosqlite, but kailash-ml does not consume those variants — it must declare aiosqlite directly per `dependencies.md` § "Declared = Imported".

### Notes

- **1.7.3 superseded.** `pip install kailash-ml` now resolves to 1.7.4 by default.
- **Follow-up tracked**: kailash core's `core/pool/__init__.py` eagerly re-exports `sqlite_pool` symbols (forcing aiosqlite at module-import time for any consumer touching `kailash.core.pool.*`). Migrating that to a lazy `__getattr__` pattern per `orphan-detection.md` Rule 6b would let consumers import `kailash.core.pool` without paying the aiosqlite tax. Out of hotfix scope; kailash core 2.18.x patch concern.

## [1.7.3] — 2026-05-09 — kailash floor bump for #890 slim-core alignment

Patch release pairing kailash-ml with the kailash 2.18.0 / #890 slim-core layout. **No source changes** — diff is strictly `pyproject.toml` floor bump + `__version__` anchor + this CHANGELOG entry.

### Changed

- **`kailash` floor: 2.16.0** (was `2.13.4`) — aligns with the kailash 2.18.0 slim-core layout.

### Notes

- No public-API changes; no behavior changes; wheel content is identical to 1.7.2 except for the `__version__` constant.

## [1.7.2] — 2026-05-06 — FeatureStore deprecation-warning bridge (#643)

Per `rules/zero-tolerance.md` Rule 6a (Public-API Removal Requires Deprecation
Cycle), this bridge release emits a `DeprecationWarning` on first access of
top-level `kailash_ml.FeatureStore` to surface the upcoming cutover before it
lands. The legacy resolution path itself is unchanged — every existing 1.x
caller keeps working — and the canonical surface at `kailash_ml.features` has
been the documented destination since the 1.0 cut (see
`specs/ml-feature-store.md` § 1.1). Closes #643 step 1.

### Deprecated

- Top-level `from kailash_ml import FeatureStore` now emits a
  `DeprecationWarning` on first access. The attribute resolves through
  `__getattr__` to the legacy module
  `kailash_ml.engines.feature_store.FeatureStore` whose constructor is
  `FeatureStore(conn: ConnectionManager, *, table_prefix="kml_feat_")`. The
  canonical 1.0+ surface is
  `from kailash_ml.features import FeatureStore` whose constructor is
  `FeatureStore(dataflow: DataFlow, *, default_tenant_id=None)`. The legacy
  resolution path will be removed in kailash-ml 2.0.0; downstream callers MUST
  migrate to the canonical import path AND switch the constructor signature
  before that cutover. See `MIGRATION.md` for the recipe.

### Added

- Tier-2 wiring test
  `packages/kailash-ml/tests/integration/test_feature_store_wiring.py`
  exercises the canonical `kailash_ml.features.FeatureStore` end-to-end
  against a real `DataFlow(...)` instance backed by file-based SQLite
  (real infrastructure per `rules/testing.md` § Tier 2 — no mocks). Closes
  the Wave-6 follow-up at `specs/ml-feature-store.md` § 7.2 and satisfies
  `rules/facade-manager-detection.md` MUST 1 (every `*Store` manager exposed
  via the public surface MUST have a Tier-2 test imported through the
  framework facade) AND MUST 2 (file name
  `test_<lowercase_manager_name>_wiring.py`). The test covers the 15
  conformance assertions enumerated in `specs/ml-feature-store.md` § 10.

### Migration (1.x → 2.0.0)

```python
# Before (1.x — emits DeprecationWarning at 1.x bridge release; raises in 2.0.0)
from kailash.db.connection import ConnectionManager
from kailash_ml import FeatureStore

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()
store = FeatureStore(conn, table_prefix="kml_feat_")

# After (canonical 1.0+ surface — works today, will be the only path in 2.0.0)
from dataflow import DataFlow
from kailash_ml.features import FeatureStore

df = DataFlow("sqlite:///ml.db", auto_migrate=True)
store = FeatureStore(df, default_tenant_id="acme")
```

The constructor change is intentional: the canonical FeatureStore is a
DataFlow-bridge primitive (one tenant-scoped store per request), not a
ConnectionManager-coupled singleton. Migration only affects the FeatureStore
construction site — `get_features` / cache-key helpers retain compatible
return shapes.

## [1.7.1] — 2026-05-01 — Re-export `MultiModelAdapter` from `kailash_ml.serving`: closes #741

`MultiModelAdapter` (the 1.5.0 → 1.6.0 hard-break recovery shim, GH
#700) is now re-exported through `kailash_ml.serving.__init__` and
listed in `kailash_ml.serving.__all__`. The class previously existed
at `kailash_ml.serving.multi_model_adapter.MultiModelAdapter` and was
also exported from top-level `kailash_ml.MultiModelAdapter`, but the
spec-documented import path

```python
from kailash_ml.serving import MultiModelAdapter
```

raised `ImportError` on a fresh install, contradicting
`specs/ml-serving.md` § 2.6.1.

Per `rules/orphan-detection.md` § 6 every public module-scope import
in a package's `__init__.py` MUST appear in that module's `__all__`;
this release closes the orphan with no behavioural change beyond the
re-export.

### Fixed

- `kailash_ml/serving/__init__.py`: re-export `MultiModelAdapter`;
  add `"MultiModelAdapter"` to `__all__`.

### Tests

- `tests/regression/test_issue_741_multi_model_adapter_serving_export.py`
  (Tier 1) — pins the re-export, structural `ast.parse` verification of
  `__all__`, and identity check `kailash_ml.serving.MultiModelAdapter
is kailash_ml.MultiModelAdapter`.

## [1.7.0] — 2026-05-01 — Lightning quarantine migration: closes #752

Migrates kailash-ml's PyTorch Lightning dependency from the umbrella
`lightning` package to the standalone `pytorch-lightning` distribution.
The umbrella `lightning` package was QUARANTINED on PyPI in 2026-04
(`pypi:project-status="quarantined"` on
https://pypi.org/simple/lightning/), breaking every fresh
`pip install kailash-ml` at dep resolution.
[`pytorch-lightning`](https://pypi.org/project/pytorch-lightning/) (latest
2.6.1) is the authoritative active distribution from Lightning-AI with
full API parity at every call site this package uses (`Trainer`,
`LightningModule`, `Callback`, `ModelCheckpoint`, `Trainer.fit` —
`__init__` signatures and method surfaces are byte-for-byte identical).

### Changed

- **Base + `[dl]` dep**: `lightning>=2.2` → `pytorch-lightning>=2.2` in
  `pyproject.toml` (lines 56 + 75 of the manifest).
- **Source imports**: every `import lightning.pytorch as <alias>` and
  `from lightning.pytorch[.callbacks] import <X>` in `src/kailash_ml/`
  rewritten to the `pytorch_lightning` import path. Six source files
  touched: `engine.py`, `trainable.py`, `engines/training_pipeline.py`,
  `diagnostics/dl.py`, `tracking/runner.py`, `autolog/_lightning.py`.
- **Test imports**: same rewrite across 11 test files (unit + integration).
- **`pytest.importorskip("lightning")` /
  `pytest.importorskip("lightning.pytorch")`** rewritten to
  `pytest.importorskip("pytorch_lightning")` in 3 test files.
- **`_seed.py` lightning seed-everything fallback chain**: now tries
  `pytorch_lightning` first, then `lightning.pytorch`, then `lightning`
  — so users with the (still-installed) umbrella package keep working
  while clean installs resolve to `pytorch_lightning`.
- **Specs**: `specs/ml-autolog.md`, `specs/ml-engines-v2.md`,
  `specs/ml-diagnostics.md`, `specs/ml-tracking.md` — every
  `lightning.pytorch.*` reference rewritten to the `pytorch_lightning`
  path. Framework integration string keys (e.g.,
  `km.autolog("lightning")`) remain unchanged — they are stable
  user-facing identifiers, not import paths.

### Added

- **Tier-2 regression test**:
  `tests/regression/test_issue_752_pytorch_lightning_install.py` asserts
  `pytorch_lightning.Trainer` / `pytorch_lightning.LightningModule` /
  `pytorch_lightning.callbacks.{Callback,ModelCheckpoint}` are
  importable. If a future quarantine of `pytorch-lightning` happens, CI
  surfaces it before users hit broken installs.

### Migration notes

- **No public API breaks** for kailash-ml callers. Users who only use
  `kailash_ml.*` symbols see no change.
- **Direct `import lightning.pytorch` users** (i.e., users who imported
  the umbrella package directly in their own code) MUST migrate to
  `import pytorch_lightning`. The umbrella was already broken on PyPI
  before 1.7.0 ships, so any 1.6.x consumer doing this had already lost
  the ability to `pip install` cleanly.
- **Frozen requirements files** pinning `lightning>=2.2` will conflict
  with kailash-ml 1.7.0's `pytorch-lightning>=2.2` declaration. Users
  MUST update their requirements files to `pytorch-lightning>=2.2`.

## [1.6.0] — 2026-04-29 — 1.5.x follow-up: closes #699, #700, #701

Closes three production issues surfaced by the MLFP M5 notebook smoke-test
on 2026-04-28. All three trace to the same `1.5.x release-migration-debt`
class (1.5.0 hard-removed surfaces without deprecation cycle, schema
drifted across migration + inline DDL + spec, accepted-literals fell
through silently). Shipped via PR
[#708](https://github.com/terrene-foundation/kailash-py/pull/708) on a
single integration branch with 25 commits across S1/S2/S3a/S3b shards
and three /redteam rounds.

This 1.6.0 minor supersedes the originally-scoped 1.5.2 patch — `#700`
adds new public API (`MultiModelAdapter` + `InferenceServer.__new__`
deprecation routing) so semver mandates a minor bump. `#700` is strictly
additive: 1.5.x callers using `InferenceServer.from_registry(name,
registry=)` get bit-identical behavior in 1.6.0; only 1.1.x-shape
callers (`InferenceServer(registry=, cache_size=)`) trigger the new
deprecation routing.

### Added

- **`MultiModelAdapter`** at
  `kailash_ml/serving/multi_model_adapter.py` (closes
  [#700](https://github.com/terrene-foundation/kailash-py/issues/700)).
  Back-compat shim restoring the 1.1.x `InferenceServer(registry=,
cache_size=)` signature behind a `DeprecationWarning`. Lazy-constructs
  one canonical `InferenceServer` per model name via
  `InferenceServer.from_registry`. Surfaces `warm_cache(names)`,
  `predict(name, payload)`, and refuses `load_model(name, model)` with
  a typed migration hint per `rules/zero-tolerance.md` Rule 6
  (Implement Fully). Wired through
  `InferenceServer.__new__` deprecation routing — 1.1.x kwargs
  (`cache_size is not None` OR `config is None and registry is not
None`) route to the adapter; canonical 1.5.x callers fall through to
  `__init__` unchanged.
- **`InferenceServer.from_registry_many(names, *, registry)` helper**
  — additive convenience for bulk per-model server construction. The
  canonical migration path away from `MultiModelAdapter` for users who
  want N servers without going through the deprecation surface.
- **`diagnose(kind="classifier"/"regressor")` aliases** (part of
  [#701](https://github.com/terrene-foundation/kailash-py/issues/701)).
  Resolve to the same `ClassicalDiagnostics` engine as
  `kind="classical"`. Documented as "convenience aliases for the most
  common task names" in `specs/ml-diagnostics.md §3`.
- **Cross-package dispatch in `km.diagnose`** for
  `kind="alignment"` / `kind="llm"` / `kind="agent"` (rest of #701).
  Routes to `kailash_align.diagnostics.alignment.AlignmentDiagnostics`,
  `kaizen.judges.llm_diagnostics.LLMDiagnostics`, and
  `kaizen.observability.agent_diagnostics.AgentDiagnostics`
  respectively. Sibling-package not installed → `ImportError` with
  explicit install hint naming the kailash-ml extra. Per
  `rules/dependencies.md` § BLOCKED Anti-Patterns silent fallback is
  BLOCKED. `kind="clustering"` raises `ValueError` with explicit
  "no dispatch" message per `rules/zero-tolerance.md` Rule 2 (no fake
  dispatch).
- **Optional extras `[alignment]`, `[kaizen-judges]`,
  `[kaizen-observability]`** in `pyproject.toml` declaring the
  cross-package dispatch dependencies.
- **`MultiModelAdapterProtocol`** + widened
  **`InferenceServerProtocol`** in `kailash_ml/serving/_types.py`.
  Type-only protocol layer that breaks the static
  `serving/server.py` ↔ `serving/multi_model_adapter.py` cycle CodeQL
  `py/unsafe-cyclic-import` flagged after #700 landed; runtime imports
  stay scoped to method bodies (`__new__`, `warm_cache`).

### Fixed

- **`_kml_model_versions` schema 3-way drift** (closes
  [#699](https://github.com/terrene-foundation/kailash-py/issues/699)).
  Migration `0002_kml_models` shipped a 7-column schema, ModelRegistry
  inline DDL added 6 data columns the migration never had, and
  `specs/ml-engines.md §5A.2` declared a 13-column shape neither
  matched. Resolution per ADR-1 (revised post-redteam Round 1):
  numbered migration
  `0005_kml_model_versions_data_columns` adds the 6 missing columns
  (`metrics_json`, `signature_json`, `onnx_status`, `onnx_error`,
  `artifact_path`, `model_uuid`) with reversible up/down SQL; inline
  DDL deleted from `ModelRegistry`. All `WHERE name = ?` queries in
  `model_registry.py` plumbed `tenant_id` + `model_name` per Option B
  (multi-tenant safe). Includes `tenant_id` parameter on
  `_lineage_walker_query` and `ModelRegistry.delete_model_version`.
- **`DLDiagnostics` silent `data=` drop** (part of #701). 1.5.x
  `km.diagnose(kind="dl", data=loader)` silently dropped the
  `DataLoader` — the report reflected only the records the caller
  pumped manually via `record_batch`. Now `.report(data=loader)`
  consumes the loader once in `torch.no_grad()` mode, runs the model
  forward on each batch, and records `record_batch(loss=...)` per
  batch using a default loss heuristic (`F.cross_entropy` when output
  rank is 2 AND targets are integer-typed; otherwise `F.mse_loss`).
  Model train/eval state preserved via `try/finally`. Resolution
  order: argument-supplied `data=` wins over construction-time
  `data=`. Permissive batch contract — non-conforming batches skipped
  with structured WARN log per `observability.md` MUST 2. Adds
  `n_batches` + `n_samples` keys to the report dict.
- **Tenant sentinel `"default"` → `"_single"`** across
  `model_registry.py`, `tracker.py`, and the lineage walker (#699
  redteam Round 2 finding F-1). Aligns with the spec sentinel for
  single-tenant deployments and matches `kailash-rs` posture per
  `rules/cross-sdk-inspection.md` Rule 3 (EATP D6 semantic parity).
- **Spec drift gate compliance** — added
  `<!-- spec-assert-skip: class:DataLoader -->` directive at
  `specs/ml-diagnostics.md §5.1a` for the `torch.utils.data.DataLoader`
  external symbol cite per `specs/spec-drift-gate.md §3.2`.
- **CodeQL `py/empty-except` at `dl.py:1257`** — heuristic-loss
  broadcast path's `except RuntimeError: pass` now carries an
  explanatory comment documenting the fall-through-to-`mse_loss`
  intent per `rules/zero-tolerance.md` Rule 3.

### Tests

- **14 new regression tests** — one per acceptance criterion across
  the three issues. All DOCS-EXACT pipeline tests per
  `rules/testing.md` § "End-to-End Pipeline Regression":
  - `test_issue_699_*` (3 tests): tenant-aware schema, lineage walker
    parity, registry round-trip on shared store.
  - `test_issue_700_*` (4 tests): canonical-per-model predict path,
    legacy multi-model adapter predict path, deprecation routing
    detection, `from_registry_many` bulk construction.
  - `test_issue_701_*` (7 tests): `data=` wiring, alias dispatch,
    cross-package dispatch (alignment/llm/agent), clustering rejection,
    extras-gating ImportError messages.
- **Tier-2 wiring tests** for `MultiModelAdapter` per
  `rules/facade-manager-detection.md` MUST Rule 2.
- **Spec sibling re-derivation** across 16 `ml-*.md` specs (Round 2 +
  Round 3) per `rules/specs-authority.md` § 7.

### Migration notes

`@db.model`-driven schemas pick up the migration automatically on
first connect. Shared databases require running the numbered migration
explicitly: `MigrationManager.apply_migration(0005, dataflow)`. The
`down_sql` is reversible but drops the 6 added columns — pass
`force_downgrade=True` per `rules/schema-migration.md` Rule 7.

`MultiModelAdapter` is a deprecation shim — new code SHOULD construct
one `InferenceServer` per model via `InferenceServer.from_registry` or
the new `from_registry_many` helper. The shim will be removed in 1.7.0
per the deprecation warning's stated removal version.

### Cross-SDK posture

Verified ABSENT in the Rust SDK — Rust uses trait-object backends

- `DashMap` `InferenceServer` + no `diagnose()` dispatcher, so none of
  the three Python issues have a Rust analog (per
  `rules/cross-sdk-inspection.md` Rule 1 cross-check).

## [1.5.1] — 2026-04-28 — W7 follow-up: ModelNotFoundError canonical identity

### Fixed

- **Duplicate `ModelNotFoundError` class** at
  `kailash_ml/engines/model_registry.py:56` removed. The local
  `class ModelNotFoundError(Exception)` was distinct from the canonical
  `kailash.ml.errors.ModelNotFoundError` (subclass of
  `ModelRegistryError → MLError`). User code catching `ModelNotFoundError`
  via either import path silently caught one OR the other — never both.
  All raise sites now route through the canonical class via
  `from kailash_ml.errors import ModelNotFoundError`. Surfaced by W7-001
  agent (lineage walker raised canonical; `get_model` raised local).
- **Regression tests** at
  `tests/regression/test_model_not_found_error_canonical_identity.py`:
  pin class identity, MLError subclass invariant, AST-level invariant
  blocking re-introduction of a local class.

### Closed (no code change in this release)

- Issue [#672](https://github.com/terrene-foundation/kailash-py/issues/672)
  (`format_record_id_for_event` parity with kailash-rs BP-048) closed
  with delivered-code references — helper already shipped at
  `dataflow.classification.event_payload.format_record_id_for_event`
  via `kailash-dataflow>=2.3.2`.

## [1.5.0] — 2026-04-27 — W7-001: cross-engine LineageGraph (closes #657)

Implements the cross-engine lineage surface deferred at 1.0.0. Closes
GitHub issue [#657](https://github.com/terrene-foundation/kailash-py/issues/657)
and the deferral disposition declared at `specs/ml-tracking.md §6.3`.

### Added

- **`kailash_ml.engines.lineage` module** — frozen `LineageGraph` /
  `LineageNode` / `LineageEdge` dataclasses per
  `specs/ml-engines-v2-addendum.md §E10.2`. Reachable through the
  top-level namespace as `kailash_ml.LineageGraph` (eager import; not
  in canonical `__all__` per the same convention as `DeviceReport` /
  `ServeResult` / `MetricSpec`).
- **`build_lineage_graph(conn, *, name, version, tenant_id, max_depth)`
  walker** — BFS traversal of `_kml_lineage` via
  `ConnectionManager.fetch`. Materialises `model_version`, `run`,
  `dataset`, `feature_version`, and `model_version` (parent) nodes
  with the canonical `produced_by` / `consumed` / `used_features` /
  `derived_from` edges. Bounded by `max_depth`.
- **`ModelRegistry.build_lineage_graph(*, ref, tenant_id, max_depth)`
  facade** — accepts both bare model names (latest version resolves
  via `_kml_models.latest_version`) and the canonical `model@vN`
  form. Raises `ModelNotFoundError` for unknown refs.
- **`ModelRegistry.record_lineage(*, name, version, tenant_id,
tracker_run_id, ...)`** — canonical write path for `_kml_lineage`
  rows. Idempotent on PK `(tenant_id, model_name, version)` via
  `DELETE` + `INSERT` in one transaction (dialect-portable; avoids
  `ON CONFLICT` divergence).
- **Numbered migration `0004_kml_lineage_table`** at
  `src/kailash/tracking/migrations/`. 8-column DDL per
  `specs/ml-tracking.md §6.3` + audit-correlation index
  `idx_kml_lineage_tracker_run_id`. Reversible upgrade/downgrade with
  `force_downgrade=True` gate per `rules/schema-migration.md` Rule 7.
- **Tier 2 wiring test** at
  `packages/kailash-ml/tests/integration/test_lineage_graph_wiring.py`
  per `rules/facade-manager-detection.md` MUST Rule 2. 10 cases
  covering migration probe, materialised graph shape, cross-tenant
  defense (WHERE filter + monkeypatched fetcher), cache key shape,
  unknown-model error, bare-name resolution, and frozen-dataclass
  identity.
- **Tier 3 regression** at
  `packages/kailash-ml/tests/regression/test_readme_lineage_quickstart.py`
  per `rules/testing.md` § "End-to-End Pipeline Regression". 3 cases
  covering the canonical Quick Start, top-level dataclass exposure,
  async-surface consistency, and the `LineageNotImplementedError`
  removal sweep.

### Changed

- **`km.lineage(ref, *, tenant_id=None, max_depth=10)`** now returns
  a real `LineageGraph` via the registry walker instead of raising
  `LineageNotImplementedError`. Fall-through tenant resolution per
  `specs/ml-tracking.md §7.2` — explicit `tenant_id` arg, then
  `get_current_tenant_id()`, then the canonical `"_single"`
  sentinel.
- **`specs/ml-tracking.md §6.3`** — deferral block replaced with the
  W7-001 implementation contract.
- **`specs/ml-engines-v2-addendum.md §E10.2`** — header flipped from
  DEFERRED to IMPLEMENTED.
- **`specs/ml-engines-v2.md §15` + §15.8** — wrapper table row and
  signature block updated to reflect the shipped surface.

### Removed (BREAKING for callers catching the deferral error)

- **`kailash_ml.errors.LineageNotImplementedError`** class deleted
  per `rules/orphan-detection.md` Rule 3 (Removed = Deleted, Not
  Deprecated). Class no longer reachable through `kailash.ml.errors`
  or `kailash_ml.errors` in any form.

  **Migration**: callers handling the deferral path with
  `except LineageNotImplementedError` MUST switch to handling a real
  `LineageGraph` return value. The Quick Start `await km.lineage(...)`
  no longer raises this error class. If your code was a deferred
  pass-through that re-raised the error, delete the `try/except`
  block — `km.lineage` succeeds against any DB whose migration is
  applied.

## [1.4.2] — 2026-04-27 — W6 round-3 MED-1 catch-up: `__version__` in canonical `__all__`

Atomic version bump to pair with the public-API addition landed in PR #674
(commit `6e106d13`). Per `rules/zero-tolerance.md` Rule 5, version must be
bumped atomically with the public-API surface change — that bump was missed
at merge time and is caught up here.

### Added

- **`__version__` in canonical `__all__`** (Group 0 — Package metadata) —
  `from kailash_ml import *` now exports the package version string per
  `rules/orphan-detection.md` §6 (every eagerly-imported module-scope symbol
  MUST appear in `__all__`). Closes W6 round-3 finding MED-1. Landed in PR #674
  (commit `6e106d13`); version bump caught up in this release.

## [1.4.1] — 2026-04-27 — W8 wave: FeatureStore wiring test + spec hygiene

Bundles two Wave 6 follow-ups (W6-022 + W6-023) into one W8-wave
patch release. Test-only addition + minor source/comment cleanups —
no breaking changes, no public-API surface drift.

### Added

- **W6-022 Tier-2 wiring test** at
  `packages/kailash-ml/tests/integration/test_feature_store_wiring.py`
  — closes the `rules/facade-manager-detection.md` MUST 1 + MUST 2 gap
  for the canonical 1.0+ `kailash_ml.features.FeatureStore`. Fifteen
  test cases, one per § 10 conformance assertion in
  `specs/ml-feature-store.md`, exercised against a real `DataFlow(...)`
  instance backed by file-based SQLite (Tier 2 per `rules/testing.md`
  — NO mocks). Imports through the `kailash_ml.features` facade per
  Rule 1.

### Changed

- **W6-023** — stripped the `W31 31b` workspace-artifact reference
  from `kailash_ml/features/store.py` (module docstring + class
  docstring + comment) AND from the runtime `ImportError` message
  raised by `_import_ml_feature_source` when the DataFlow polars
  binding is absent. The new error message cites the canonical
  sibling spec `specs/dataflow-ml-integration.md §1.1` per
  `rules/specs-authority.md` § 1 (specs are durable cross-references;
  workspace identifiers are not). Unit test
  `tests/unit/test_feature_store_unit.py::test_get_features_raises_import_error_when_binding_missing`
  updated to match the new assertion shape.
- **`_import_ml_feature_source` resolution** — extended the deferred
  binding resolver to also probe `dataflow.ml.ml_feature_source`
  (the current canonical export location in DataFlow ≥ 2.1) in
  addition to the legacy `dataflow.ml_integration.ml_feature_source`
  fallback. The top-level `from dataflow import ml_feature_source`
  remains the first-priority probe for forward compatibility. This
  closes a wiring drift between the canonical FeatureStore surface
  and the actual `dataflow.ml` binding location — `get_features` now
  reaches the real polars binding under DataFlow 2.1+ instead of
  raising the loud `ImportError` that masked downstream wiring.

### Notes

- **W6-021 (Tier-3 e2e for AutoML + FeatureStore)** is unblocked by
  this release and queued as the next-session work — it
  `depends_on: [W6-018, W6-022]` and could not land in parallel with
  W6-022 (which it depends on).

## [1.4.0] — 2026-04-27 — W7 wave: AutoML migration discipline + canonical surface

Bundles three Wave 6 follow-ups (W6-018 + W6-019 + W6-020) into one
W7-wave release. The dominant change is the W6-020 schema-migration
discipline for the AutoML audit table — the engine no longer emits
`CREATE TABLE IF NOT EXISTS` inline at first use; operators MUST run a
numbered migration ahead of every sweep.

### Added

- **Migration `0003_automl_trials_schema_alignment`** at
  `kailash.tracking.migrations.0003_automl_trials_schema_alignment` —
  brings persisted `_kml_automl_trials` schema up to the engine's
  19-column runtime form. Idempotent + reversible (`force_downgrade=True`
  required for rollback per `rules/schema-migration.md` Rule 7);
  detects the 0002 placeholder shape via the `hyperparams` sentinel
  column; refuses to drop a populated placeholder via
  `PlaceholderTablePopulatedError`. Append-only — does NOT edit 0002
  per Rule 4.
- **`kailash.ml.errors.MigrationRequiredError`** — typed error raised by
  engines that detect a required schema object is absent at first use.
  Sibling of `MigrationFailedError` (which fires on a migration's own
  apply failure) and `MigrationImportError` (which fires when a
  migration module cannot be loaded). Re-exported through
  `kailash_ml.errors` and `kailash_ml.MigrationRequiredError` per the
  W33 6-group canonical **all** structure.
- **W6-020 Tier-2 regression test** at
  `packages/kailash-ml/tests/integration/test_kml_automl_trials_migration.py`
  — covers fresh-DB → typed error path, post-migration write-then-read
  path, idempotent re-apply, populated-placeholder rejection, and
  `force_downgrade=True` rollback discipline. Real SQLite via
  `kailash.db.connection.ConnectionManager` per `rules/testing.md` §
  Tier 2.

### Changed

- **`AutoMLEngine._ensure_audit_ready`** now probes the audit table
  via `_probe_trials_table` and raises typed `MigrationRequiredError`
  when the canonical schema is absent, instead of emitting
  `CREATE TABLE IF NOT EXISTS` inline. The probe is dialect-portable
  (PostgreSQL / SQLite / MySQL) using `information_schema` or
  `sqlite_master`, with a SELECT-against-sentinel fallback when the
  dialect helper isn't reachable. The sentinel column `trial_number`
  unambiguously distinguishes the canonical 19-column form from
  migration 0002's seven-column placeholder.
- **`kailash_ml.AutoMLEngine`** now resolves to the canonical surface
  at `kailash_ml.automl.engine.AutoMLEngine` (W6-018). The legacy
  `engines/automl_engine.py` import path is removed; downstream
  callers using `from kailash_ml.engines.automl_engine import ...`
  MUST migrate to `from kailash_ml.automl import AutoMLEngine`. The
  Tier-1 identity test at
  `packages/kailash-ml/tests/unit/test_automl_engine_canonical.py`
  pins this contract going forward.
- **`kailash_ml.automl.engine.AutoMLEngine` docstring** stripped the
  stale `FeatureSchema` auto-derivation claim (W6-019) — the engine
  has never auto-derived a `ParamSpec` list from a `FeatureSchema`;
  callers always supply `space=` explicitly.

### Removed

- `_ensure_trials_table` helper from `automl/engine.py` — the inline
  `CREATE TABLE IF NOT EXISTS` path is fully retired. Callers MUST
  apply migration 0003 ahead of every sweep
  (`rules/schema-migration.md` MUST Rule 1).
- Legacy `kailash_ml/engines/automl_engine.py` module (W6-018).

### Migration

When upgrading from kailash-ml 1.3.x:

1. Apply migration 0003 against your tracking DB:
   ```python
   from kailash.tracking.migrations._registry import get_registry
   await get_registry().apply_pending(_MigrationConnAdapter(conn))
   ```
   `ExperimentTracker.create()` does this automatically on first open.
2. Update any imports of `kailash_ml.engines.automl_engine.AutoMLEngine`
   to `kailash_ml.automl.AutoMLEngine`.

### Spec references

- `specs/ml-automl.md` §8A.2 — first-use DDL discipline + Wave 6
  numbered-migration mandate.
- `specs/kailash-core-ml-integration.md` §4 — migration framework
  contract.
- `workspaces/portfolio-spec-audit/todos/active/W6-020-numbered-migration-kml-automl-trials.md`
- `workspaces/portfolio-spec-audit/todos/active/W6-018-flip-getattr-canonical-automl.md`
- `workspaces/portfolio-spec-audit/todos/active/W6-019-strip-stale-feature-schema-docstring.md`

### Rules cited

- `rules/schema-migration.md` MUST Rule 1 (numbered migrations only),
  Rule 3 (reversible), Rule 4 (append-only — 0002 untouched), Rule 5
  (real PG + SQLite test), Rule 7 (force_downgrade=True for
  destructive rollback).
- `rules/dataflow-identifier-safety.md` MUST Rule 1 (every dynamic
  DDL identifier through `quote_identifier`).
- `rules/zero-tolerance.md` Rule 2 (no stubs / fake DDL).
- `rules/testing.md` § Tier 2 (real DB, no mocks for migration tests).

## [1.3.0] — 2026-04-27 — W6-016: shared trajectory schema (F-E1-50)

Closes W5-E1 finding F-E1-50 (HIGH): the spec-mandated shared trajectory
schema between `kailash-ml.rl` and `kailash-align` was named in
`specs/ml-rl-align-unification.md` §3.2 + §4 but had no concrete
dataclass exposing the bridge contract. Builds on W6-015's
`EpisodeRecord` / `EvalRecord` records and the W30 `RLLineage`
provenance type.

### Added

- **`kailash_ml.rl.TrajectorySchema`** — frozen dataclass bundling a
  completed RL or RLHF training run for cross-SDK handoff. Fields:
  `episodes: tuple[EpisodeRecord, ...]`, `lineage: RLLineage`,
  `eval_history: tuple[EvalRecord, ...]`, `metadata: Mapping[str, Any]`
  (read-only `MappingProxyType`). Single-source-in-ml per spec §7 — the
  type lives here; kailash-align re-exports it from
  `kailash_align.ml.TrajectorySchema` and never defines a parallel.
- **`TrajectorySchema.to_dict()` / `from_dict()`** — byte-stable
  round-trip serialisation. Carries a schema discriminator
  (`"kailash_ml.rl.TrajectorySchema"`) and `schema_version=1`; foreign
  payloads or unsupported versions raise `ValueError`. Datetime fields
  serialise via `isoformat()`. Round-trip JSON is byte-identical under
  `json.dumps(sort_keys=True)` so cross-process / cross-machine
  handoff is sound without bespoke serialisers.
- **`RLTrainer.collect_trajectories(result, *, metadata=None)`** —
  canonical RL-side bridge entry: bundles a completed
  `RLTrainingResult` into a `TrajectorySchema`. Auto-populates schema
  metadata from the result (algorithm, env_spec, total_timesteps,
  total_env_steps, elapsed_seconds, device_used, tenant_id) and merges
  caller-supplied metadata on top. Raises typed `RLError(reason=
"missing_lineage")` when `result.lineage is None` — no silent
  fabrication of provenance per `rules/zero-tolerance.md` Rule 2.

### Spec references

- `specs/ml-rl-align-unification.md` v1.0.0 §3.2 (result-type parity),
  §4 (Tier-2 conformance test), §5 (lineage immutability promise
  extended to trajectory state), §7 (single-source-in-ml mandate).
- `workspaces/portfolio-spec-audit/04-validate/W5-E1-findings.md`
  F-E1-50 (HIGH closure).

### Notes

- `TrajectorySchema` is intentionally NOT a parallel `RLLineage`. It is
  a bundle that _contains_ an `RLLineage` plus the actual episode +
  eval data. The W30 0.6.0 changelog note ("no parallel Trajectory
  class would violate spec §7 single-source mandate") still holds:
  `TrajectorySchema` lives in kailash-ml only; kailash-align re-exports.
- The bundle is frozen by construction. `metadata` is normalised to a
  `MappingProxyType` at `__post_init__`; mutating the caller's original
  dict after construction MUST NOT mutate the trajectory's view.

## [1.2.0] — 2026-04-27 — W5 wave: schema parity + scope cleanup

W6-015 is the version owner for the W5 wave. This release batches three
ml todos:

- **W6-015 — `RLTrainingResult` schema parity (F-E1-38).** Realises the
  `specs/ml-rl-core.md` §3.2 subset relationship `RLTrainingResult ⊂
TrainingResult` by mirroring every `TrainingResult` field on the
  RL envelope AND adding the 8 spec-required RL-specific fields:
  `episodes` (list[`EpisodeRecord`]), `policy_entropy`, `value_loss`,
  `kl_divergence`, `explained_variance`, `replay_buffer_size`,
  `total_env_steps`, `policy_artifact` (`PolicyArtifactRef`).
- **W6-013 — `CatBoostTrainable` adapter (F-E1-01).** W5-wave batch
  coordination — the adapter ships in this release-wave window;
  parallel todos populate the trainable layer separately while W6-015
  owns the version + CHANGELOG.
- **W6-014 — `LineageGraph` deferral (F-E1-09).** Tracked through the
  Wave 6.5b roadmap per `rules/zero-tolerance.md` Rule 1b. Marker entry
  for the W5-wave batch coordination — `km.lineage()` raises typed
  `LineageNotImplementedError` rather than returning fake data, and the
  full graph DDL + traversal lands in a follow-up release.

### Added

- **`kailash_ml.rl.EpisodeRecord` + `kailash_ml.rl.EvalRecord`** — typed
  per-episode + per-eval records per `specs/ml-rl-core.md` §3.2 +
  §10.2. Both are frozen dataclasses with no SB3 / Gymnasium imports
  so the `[rl]` extra remains optional.
- **`RLTrainingResult` 8 spec-required fields** per spec §3.2:
  - `algorithm: str`, `env_spec: str`, `total_timesteps: int`
    (replacing the legacy positional-only attributes)
  - `episode_reward_mean: float`, `episode_reward_std: float`,
    `episode_length_mean: float`
  - `policy_entropy: float | None`, `value_loss: float | None`,
    `kl_divergence: float | None`, `explained_variance: float | None`
    (all `None` when not applicable to the algorithm — never
    hallucinated zero per `rules/zero-tolerance.md` Rule 2)
  - `replay_buffer_size: int | None` (`None` for on-policy algos)
  - `total_env_steps: int`
  - `episodes: list[EpisodeRecord]` (non-empty when ≥1 rollout completed)
  - `eval_history: list[EvalRecord]`
  - `policy_artifact: PolicyArtifactRef | None` (path + sha256 + algo)
- **`RLTrainingResult` mirrors of `TrainingResult` fields** for spec §3.2
  subset relationship: `model_uri`, `device_used`, `accelerator`,
  `precision`, `elapsed_seconds`, `tracker_run_id`, `tenant_id`,
  `artifact_uris`, `lightning_trainer_config`. Defaults preserve
  back-compat for callers that only set the legacy positional fields.
- **Tier-2 e2e regression** at
  `tests/regression/test_rl_train_register_e2e.py` exercises the
  canonical `km.rl_train(env="CartPole-v1", algo="ppo", ...)` pipeline
  end-to-end against real SB3 + Gymnasium and asserts every spec §3.2
  field is populated correctly. Per `rules/testing.md` § "End-to-End
  Pipeline Regression".

### Changed

- **`RLTrainingResult` field-level rename** with back-compat aliases:
  - `mean_reward` → `episode_reward_mean` (legacy kwarg accepted; alias
    property reads the canonical field)
  - `std_reward` → `episode_reward_std` (legacy kwarg accepted; alias
    property reads the canonical field)
  - `training_time_seconds` → `elapsed_seconds` (legacy kwarg accepted;
    alias property reads the canonical field)
  - `env_name` → `env_spec` (legacy kwarg accepted; alias property
    reads the canonical field)

  Pre-1.2.0 callers that read the legacy attributes continue to work via
  back-compat properties on the dataclass; new callers MUST use the
  canonical spec §3.2 field names. The wire-format `to_dict()` payload
  emits BOTH canonical and legacy keys during the deprecation window.

- **5 `RLTrainingResult(...)` construction sites swept** to populate the
  new schema:
  - `packages/kailash-ml/src/kailash_ml/rl/trainer.py::RLTrainer.train`
  - `packages/kailash-align/src/kailash_align/rl_bridge/_dpo.py`
  - `packages/kailash-align/src/kailash_align/rl_bridge/_online_dpo.py`
  - `packages/kailash-align/src/kailash_align/rl_bridge/_rloo.py`
  - `packages/kailash-align/src/kailash_align/rl_bridge/_ppo_rlhf.py`

  Per `rules/security.md` § "Multi-Site Kwarg Plumbing" — every
  construction site updates in the same release wave.

- **`RLTrainer._register_trained` reads canonical field names**
  (`result.episode_reward_mean` / `result.episode_reward_std` /
  `result.env_spec`) instead of the legacy aliases. The
  `PolicyVersion` storage shape itself is unchanged for cross-SDK
  parity.
- **`km.rl_train` structured-log key** for the success line uses
  `episode_reward_mean` (canonical) instead of `mean_reward` (legacy).

### Compatibility

The legacy positional / kwarg interface continues to work for all
existing callers — the dataclass accepts both the canonical spec §3.2
field names AND the legacy aliases. The `to_dict()` payload carries
both during the deprecation window so cross-SDK consumers (kailash-rs
registry readers) see both surfaces.

A future major release MAY remove the legacy aliases once the cross-SDK
ecosystem has fully migrated; the deprecation timeline lives in the
W6.5b lineage roadmap.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

## [1.1.2] — 2026-04-27 — W6-004: legacy InferenceServer deletion (F-E1-28)

### Removed

- **`kailash_ml.engines.inference_server`** module deleted per `rules/orphan-detection.md` Rule 3 ("removed = deleted, not deprecated"). The legacy class duplicated the canonical 1.0+ surface at `kailash_ml.serving.server::InferenceServer`. Closes finding F-E1-28 of the W5-E1 portfolio audit.

### Changed

- **`kailash_ml.engines.registry`** — `InferenceServer` `EngineInfo` entry now points at `kailash_ml.serving.server` with W25 lifecycle method signatures (`from_registry`, `start`, `predict`, `stop`).
- **`kailash_ml.__init__`** — lazy-load map for `InferenceServer` redirected to the canonical surface.
- **`kailash_ml.engine.MLEngine.evaluate`** — replaced its dependency on the deleted legacy class with an inlined in-process scoring helper (`_score_records_for_evaluate`). The canonical `serving.server.InferenceServer` has a deployment-oriented lifecycle (config envelope, channels) that does not match `evaluate()`'s per-row scoring need; the helper performs the minimal load-artifact + predict path.
- **Documentation** — README, quickstart guide, ONNX export guide, and the inference-server guide now reference the canonical `serving.server` surface. `specs/ml-serving.md`, `specs/ml-engines-v2-addendum.md`, and `specs/nexus-ml-integration.md` updated to canonical paths.
- **Tests** — `tests/unit/test_inference_server.py` and `tests/integration/test_inference_server.py` deleted (per `rules/orphan-detection.md` Rule 4 — API removal sweeps tests in same PR). The legacy `test_10_inference_server` and the corresponding "Step 5" of the lifecycle test in `tests/examples/test_pycaret_comparison.py` were removed; restoration against the canonical surface is tracked as a follow-up.

## [1.1.1] — 2026-04-24 — Cyclic-import refactor (issue #612)

### Changed

- **CodeQL `py/unsafe-cyclic-import` hardening** — extracted `_types.py` modules for three sub-packages to break static import cycles (runtime was already TYPE_CHECKING-safe). Nine cycle-flagged findings closed.
  - `kailash_ml.serving._types` — `ServeStatus`, `ServeHandle`, `InferenceServerProtocol` moved out of the `server.py` ↔ `serve_handle.py` cycle. `serve_handle.py` now a thin re-export shim.
  - `kailash_ml.drift._types` — `FeatureDriftResult`, `DriftReport` moved out of the `engines/drift_monitor.py` ↔ `drift/alerts.py` cycle. Both sides import from the leaf; `drift/__init__.py` re-exports for backward compatibility.
  - `kailash_ml.autolog._types` — `AutologConfig`, `FrameworkIntegration` moved out of the `autolog/config.py` ↔ `autolog/_registry.py` cycle.

No public-API surface changes — every previous import path still resolves.

## [1.1.0] - 2026-04-23 — M1 Wave W30 Shard 1: cross-SDK RL Protocol + align-bridge dispatch + lineage

Lands the ml-side of the kailash-ml <-> kailash-align Protocol bridge per `specs/ml-rl-align-unification.md` (v1.0.0, promoted 2026-04-23). Shard 1 of 3 in W30 — Shard 2 (kailash-align 0.5.0 bridge adapters) and Shard 3 (integration tests) follow after this ships. Concrete RLHF adapters (DPO, PPO-RLHF, RLOO, OnlineDPO, KTO, SimPO, CPO, GRPO, ORPO, BCO) ship with kailash-align 0.5.0 behind the `[rl-bridge]` extra.

### Added

- **`kailash_ml.rl.protocols.RLLifecycleProtocol`** — `@runtime_checkable` Protocol describing the shared cross-SDK contract every RL adapter satisfies (classical SB3/d3rlpy AND RLHF TRL via kailash-align). Class-level attrs: `name`, `paradigm`, `buffer_kind`. Instance attrs: `run_id`, `tenant_id`, `device`. Lifecycle methods: `build`, `learn`, `save`, `load`, `checkpoint`, `resume`. Telemetry: `emit_metric`. See spec §2.1.
- **`kailash_ml.rl.protocols.PolicyArtifactRef`** — frozen dataclass referenced by `save`/`load` round-trip. Fields: `path`, `sha`, `algorithm`, `policy_class`, `created_at`, `tenant_id`. See spec §2.1.
- **`kailash_ml.rl._lineage.RLLineage`** — frozen dataclass for run provenance (spec §5.1). Fields: `run_id`, `experiment_name`, `tenant_id`, `base_model_ref`, `reference_model_ref`, `reward_model_ref`, `dataset_ref`, `env_spec`, `algorithm`, `paradigm`, `parent_run_id`, `sdk_source`, `sdk_version`, `created_at`. `paradigm` and `sdk_source` are `Literal`-enforced at runtime via `__post_init__`. Round-trips cleanly through `to_dict()` + `from_dict()` (datetime via ISO-8601). Exported at module scope as `kailash_ml.rl.RLLineage`.
- **`kailash_ml.rl.align_adapter`** — lazy bridge-dispatch module per spec §3.1 + §7. Provides:
  - `BRIDGE_ADAPTERS: dict[str, type[RLLifecycleProtocol]]` — module-scope registry; starts empty. `kailash_align.rl_bridge` populates it at its own import time via `register_bridge_adapter`.
  - `register_bridge_adapter(name, cls)` — idempotent insert; raises `ValueError` when re-registering a different class under the same name (cross-SDK drift guard).
  - `resolve_bridge_adapter(name)` — returns the adapter class; lazily imports `kailash_align.rl_bridge` on first access. Raises `FeatureNotAvailableError` with `"kailash-align[rl-bridge]"` in the message when align is not installed, per `rules/dependencies.md` § "Optional Extras with Loud Failure".
  - `FeatureNotAvailableError` — typed error carrying `algo_name`; named after the missing extra. NOT a `RLError` subclass — cross-cutting infrastructure concern, not an RL-algorithm failure.
- **`kailash_ml.rl.RLTrainingResult.lineage` + `.device`** — two new Optional fields on `RLTrainingResult` per spec §3.2 (result parity) + §5.2 (tracker parity). Both default to `None` so existing classical callers continue working unmodified; the W30 dispatcher populates them for new runs. `to_dict()` serialises both when present.
- **Bridge dispatch wired into `km.rl_train`** (spec §3.1): algorithm-name resolution is now classical-first (`kailash_ml.rl.algorithms.load_adapter_class`) then bridge (`kailash_ml.rl.align_adapter.resolve_bridge_adapter`). Successful runs populate `RLLineage` with `sdk_source="kailash-ml"` (classical) or `"kailash-align"` (bridge). `km.rl_train` gains RLHF kwargs (`reference_model`, `reward_model`, `preference_dataset`, `device`, `experiment_name`, `parent_run_id`) per spec §3.1 step 2. Missing-required-kwarg validation (e.g. `algo="dpo"` without `preference_dataset`) raises `ValueError` with an actionable message; silent fallback is blocked per `rules/zero-tolerance.md` Rule 3.
- **27 Tier-1 unit tests** at `packages/kailash-ml/tests/unit/rl/`:
  - `test_rl_protocols.py` — `@runtime_checkable` validation, duck-typed `isinstance` conformance, `PolicyArtifactRef` frozen invariant.
  - `test_rl_lineage.py` — `to_dict`/`from_dict` round-trip, Literal enforcement, JSON compatibility, frozen invariant.
  - `test_align_adapter_dispatch.py` — registry idempotency + conflict guard, `FeatureNotAvailableError` shape, end-to-end `km.rl_train` dispatch through `resolve_bridge_adapter` (behavioural test, not grep — satisfies `rules/orphan-detection.md` §2).

### Observability

- `rl.bridge.register`, `rl.bridge.resolve.start`, `rl.bridge.resolve.ok`, `rl.bridge.resolve.fail` structured log events with `algo`, `adapter_cls`, `tenant_id` fields (per `rules/observability.md` §2 + §3).
- `rl_train.dispatch.classical` / `rl_train.dispatch.bridge` events at `km.rl_train` entry so operators can tell classical and RLHF runs apart in log aggregators.
- Every log line carries `mode="real"` per `rules/observability.md` §3.

### Dependency topology

No new runtime deps in kailash-ml. `kailash_ml.rl.align_adapter` imports `kailash_align` LAZILY inside `resolve_bridge_adapter`; module-scope grep for `^from kailash_align\|^import kailash_align` across `packages/kailash-ml/src/` returns empty. Users who install only `pip install kailash-ml[rl]` and call `algo="dpo"` get a typed `FeatureNotAvailableError` naming the `[rl-bridge]` extra. See spec §7.

### Breaking changes

None. `RLTrainingResult.lineage` and `.device` default to `None`; existing classical callers that construct `RLTrainingResult(...)` positionally continue working. The `km.rl_train` kwarg additions are all keyword-only and optional.

### Spec

- `specs/ml-rl-align-unification.md` v1.0.0 (promoted 2026-04-23) — §2 (Protocol), §3.1 (dispatch), §3.2 (result parity), §3.3 (DPO-family kwarg validation), §5 (lineage), §7 (dependency topology).

## [0.17.0] - 2026-04-20 — RAGDiagnostics adapter for retrieval + generation evaluation

PR#2 of 7 for the MLFP diagnostics donation plan (kailash-py #567). Lands the second concrete `Diagnostic` Protocol adapter, extending `DLDiagnostics` (0.16.0) with retrieval-augmented-generation evaluation: IR metrics, LLM-as-judge faithfulness, retriever leaderboards, and an extras-gated ragas / trulens-eval backend.

### Added

- **`kailash_ml.diagnostics.RAGDiagnostics`** — context-manager adapter for retrieval + generation evaluation. Satisfies `kailash.diagnostics.protocols.Diagnostic` at runtime (`@runtime_checkable` Protocol with `run_id` + `__enter__` + `__exit__` + `report()`). Provides:
  - **IR metrics**: `recall@k`, `precision@k`, `reciprocal_rank` (MRR), `ndcg@k` — all pure-Python deterministic helpers with no LLM cost.
  - **`evaluate()`** — end-to-end scoring over a batch of `(query, retrieved_contexts, answer, retrieved_ids, ground_truth_ids)` tuples. Returns a `polars.DataFrame` with one row per query and columns `idx, recall_at_k, precision_at_k, context_utilisation, faithfulness, k, mode`. Automatically selects backend: `ragas` (when `[rag]` installed) → configured `JudgeCallable` → deterministic `metrics_only` fallback.
  - **`compare_retrievers()`** — leaderboard over N retrievers on the same eval set. Returns a MRR-sorted polars DataFrame with `retriever, recall_at_k, precision_at_k, mrr, ndcg_at_k, n, k`.
  - **`report()`** — structured dict keyed by `run_id` with `retrieval` / `faithfulness` / `context_utilisation` / `retriever_leaderboard` findings, each a `{severity, message, ...}` triple. Severities: `HEALTHY` / `WARNING` / `CRITICAL` / `UNKNOWN`.
  - **DataFrame accessors** (`metrics_df`, `leaderboard_df`) return `polars.DataFrame` on the base install (no plotly needed).
  - **Plot methods** (`plot_recall_curve`, `plot_faithfulness_scatter`, `plot_retriever_leaderboard`, `plot_rag_dashboard`) return `plotly.graph_objects.Figure`; require `pip install kailash-ml[dl]`.
  - **Bounded memory** via `deque(maxlen=N)` on `max_history` / `max_leaderboard_history` kwargs — streaming RAG eval loops stay under fixed memory.
  - **Sensitive mode** — `sensitive=True` replaces query bodies with `"<redacted>"` in the DataFrame and fingerprints raw queries via `sha256:<8-hex>` per the cross-SDK event-payload-classification contract.
- **`[rag]` optional extra** — `ragas>=0.1`, `trulens-eval>=0.20`, `datasets>=2.0`. Without `[rag]`, `RAGDiagnostics.evaluate()` falls back to the configured `JudgeCallable` + deterministic heuristic (logged at WARN per `rules/dependencies.md`). `RAGDiagnostics.ragas_scores()` and `RAGDiagnostics.trulens_scores()` raise `ImportError` naming the `[rag]` extra when the backend is absent.
- **`specs/ml-diagnostics.md`** — appended `§11. RAGDiagnostics` section documenting the full public API, Protocol conformance, extras-gating contract, observability events, test discipline, and MLFP donation attribution.

### Changed

- **`kailash_ml.diagnostics.__init__`** — `RAGDiagnostics` exported through the package facade. Package docstring expanded to document both `DLDiagnostics` and `RAGDiagnostics` usage patterns + the `[dl]` / `[rag]` extras gating.

### Porting notes (MLFP donation cleanup)

The MLFP `Lens 3 — Retrieval Diagnostics (the Endoscope)` (`shared/mlfp06/diagnostics/retrieval.py`, 705 LOC) was re-authored into `packages/kailash-ml/src/kailash_ml/diagnostics/rag.py`:

- Medical metaphors (endoscope / prescription pad) stripped from every docstring, plot title, and log field.
- All LLM-as-judge calls routed through `kailash.diagnostics.protocols.JudgeCallable` — no raw `openai.*` per `rules/framework-first.md`. Callers supply their judge via constructor kwarg; MLFP's bespoke `JudgeCallable` wrapper (which instantiated a Kaizen `Delegate` internally) is replaced with the cross-SDK Protocol contract.
- Bounded-memory `deque(maxlen=N)` storage replaces MLFP's unbounded `list[dict]` so streaming evaluation loops cannot grow without limit (see rules/patterns.md analysis §1.4).
- `ragas` and `trulens-eval` import sites wrapped with `try/except ImportError` + loud-fail contract per `rules/dependencies.md` "Optional Extras with Loud Failure".
- Structured log fields carry `rag_` prefix to avoid `LogRecord` reserved-attribute collisions per `rules/observability.md` MUST Rule 9.
- `run_id` is a UUID4-defaulted public attribute so `isinstance(rag, Diagnostic)` holds at runtime.
- Sensitive-mode query bodies are hashed via `sha256:<8-hex>` matching the cross-SDK `format_record_id_for_event` fingerprint contract from `rules/event-payload-classification.md`.

### Tests

- `packages/kailash-ml/tests/unit/test_rag_diagnostics_unit.py` — Tier 1 unit tests (43 tests, <1s). Covers input validation, Protocol `isinstance` check, IR-metric math on known-answer fixtures, evaluate() end-to-end in metrics-only mode, bounded-memory eviction, compare_retrievers leaderboard math, report() empty + CRITICAL severity paths, plotly / ragas / trulens extras-gating loud-fail, and JudgeCallable dispatch + error-fallback paths.
- `packages/kailash-ml/tests/integration/test_rag_diagnostics_wiring.py` — Tier 2 wiring tests (13 tests). Imports through `kailash_ml.diagnostics` facade per `rules/orphan-detection.md` §1. Uses in-process `_ScriptedJudge` conforming to `JudgeCallable` (no mocks per `rules/testing.md`). Asserts `isinstance(rag, Diagnostic)`, end-to-end `evaluate()` with real Protocol dispatch across 3 queries, `run_id` propagation, leaderboard MRR ordering, sensitive-mode redaction, and `__exit__` non-swallowing semantics.

### Cross-SDK alignment

The `JudgeCallable` + `JudgeInput` + `JudgeResult` data contract used here is defined in `src/kailash/diagnostics/protocols.py` (PR#0, kailash 2.8.10). Python and Rust SDKs implement independently with matching semantics per EATP D6. No planned kailash-rs equivalent of `RAGDiagnostics` itself (RAG evaluation depends on `ragas` / `trulens-eval`, neither of which has a stable Rust binding); cross-SDK agreement is at the Protocol level, not the adapter.

## [0.16.0] - 2026-04-20 — DLDiagnostics adapter for the cross-SDK Diagnostic Protocol

PR#1 of 7 for the MLFP diagnostics donation plan (kailash-py #567). Lands the first concrete `Diagnostic` Protocol adapter in the kailash-ml surface, providing a drop-in training-loop diagnostic session for any `torch.nn.Module`.

### Added

- **`kailash_ml.diagnostics.DLDiagnostics`** — context-manager adapter for PyTorch training diagnostics. Satisfies `kailash.diagnostics.protocols.Diagnostic` at runtime (`@runtime_checkable` Protocol with `run_id` + `__enter__` + `__exit__` + `report()`). Installs forward/backward hooks on a user-supplied `nn.Module` to collect:
  - per-batch **gradient flow**: L2 norm, per-element RMS (scale-invariant), and update-ratio (`‖∇W‖ / ‖W‖`).
  - per-batch **activation statistics**: mean/std/min/max + activation-type-aware `inactivity_fraction` (ReLU family: `|x| < 1e-6`; Tanh: `|x| > 0.99`; Sigmoid: dual-tail saturation).
  - per-batch **dead-neuron tracking** with memory-bounded rolling-window counts.
  - per-batch scalars (`loss`, `lr`) and per-epoch summaries (`train_loss`, `val_loss`, arbitrary extras).
  - `report()` returns a dict keyed by `run_id` with `gradient_flow` / `dead_neurons` / `loss_trend` findings, each a `{severity, message}` pair. Severities: `HEALTHY` / `WARNING` / `CRITICAL` / `UNKNOWN`.
  - All DataFrame accessors (`gradients_df`, `activations_df`, `dead_neurons_df`, `batches_df`, `epochs_df`) return `polars.DataFrame`.
- **`kailash_ml.diagnostics.run_diagnostic_checkpoint` / `diagnose_classifier` / `diagnose_regressor`** — module-level helpers that attach every instrument and run a short read-only diagnostic pass on a trained model; optional epoch-level history replay for viewers to see the real training trajectory.
- **`DLDiagnostics.lr_range_test`** static method — Leslie Smith learning-rate range test with fastai-style EMA smoothing (beta=0.98). Returns BOTH `safe_lr` (steepest-descent LR / 10, the recommended optimizer setting) AND `min_loss_lr` (edge of instability). Model weights are restored on exit so calling the test is non-destructive.
- **`DLDiagnostics.grad_cam`** — Grad-CAM heatmap for explaining classifier predictions from a named conv layer; preserves the model's train/eval state across the call.
- **`specs/ml-diagnostics.md`** — new spec documenting the full `DLDiagnostics` public API, protocol conformance, extras-gating contract, and the MLFP donation attribution (Apache 2.0). Registered in `specs/_index.md`.

### Changed

- **`[dl]` extras pin `plotly>=5.18`** — plotly is currently in base deps so the pin is redundant today, but `DLDiagnostics.plot_*()` methods route through a `_require_plotly()` helper that raises `ImportError` naming `pip install kailash-ml[dl]` when the extra is absent. The duplication future-proofs the contract for the eventual demotion of plotly from base (per SYNTHESIS-proposal "Plotly blast radius" mitigation).

### Porting notes (MLFP donation cleanup)

The 1,679-LOC MLFP `DLDiagnostics` helper was re-authored into `packages/kailash-ml/src/kailash_ml/diagnostics/dl.py` with the full cleanup burden the SYNTHESIS plan called for:

- Medical metaphors (stethoscope / blood-test / x-ray / prescription / flight-recorder / ecg) stripped from every docstring, method name, log field, print line, and plot title.
- `plotly` + `plotly.subplots` imported lazily inside each `plot_*` method body via `_require_plotly()`; `report()` and every `*_df()` accessor work on the base install with zero plotly dependency.
- Device resolution routes through `kailash_ml._device.detect_backend()` (the package's canonical single-point resolver per `specs/ml-backends.md §2`) rather than MLFP's `shared.kailash_helpers.get_device` import (which does not exist in this tree).
- `run_id` is a documented UUID4-defaulted instance attribute (optional kwarg) so `isinstance(diag, Diagnostic)` holds at runtime.
- Structured log fields carry a `dl_` prefix to avoid collision with `LogRecord` reserved attribute names (`module`, `args`, `msg`, etc.) per `rules/observability.md` MUST Rule 9.

### Tests

- `packages/kailash-ml/tests/integration/test_dl_diagnostics_wiring.py` — Tier 2 wiring tests against real torch: Protocol conformance (`isinstance(diag, Diagnostic)`), real 3-batch training step records gradient + activation + dead-neuron data, `run_id` correlation across record → report.
- `packages/kailash-ml/tests/unit/test_dl_diagnostics_unit.py` — Tier 1 unit tests: `__init__` validation (type, threshold range, window floor, empty `run_id`), `run_id` auto-generation uniqueness, `plot_*` methods raise `ImportError` naming `[dl]` when plotly is absent.

### Cross-SDK alignment

- Python surface: `kailash_ml.diagnostics.DLDiagnostics` — lands in this release.
- Rust surface: no planned kailash-rs equivalent; DL diagnostics are Python-native (torch hook API has no stable Rust binding). The `Diagnostic` Protocol itself is documented cross-SDK in `schemas/trace-event.v1.json` + `src/kailash/diagnostics/protocols.py`.

### Related

- [issue kailash-py#567](https://github.com/terrene-foundation/kailash-py/issues/567) — MLFP diagnostics donation (PR#1 of 7).
- `workspaces/issue-567-mlfp-diagnostics/02-plans/SYNTHESIS-proposal.md` — approved architecture (Option E: protocols + adapters + engine-extension + GovernanceDiagnostics reject).

## [0.15.2] - 2026-04-20 — bundled audit-finding hotfix (log hygiene + identifier safety)

Resolves four deferred audit findings from the 2026-04-20 late-session `/redteam` that were intentionally held over for next-session disposition per `workspaces/kailash-ml-gpu-stack/.session-notes`. All four live in `kailash-ml/` and ship in this one bundled patch.

### Fixed

- **M1 — `engine.py:2787-2794` WARN log leaked raw onnx-export `cause` string** (post-release security-reviewer MED-1): the WARN-level log emitted the full chained exception message verbatim, which could contain ONNX framework internals and schema-revealing strings. Per `rules/observability.md` §8 (schema-revealing field names at DEBUG or hashed), the raw `cause` now logs at DEBUG and the WARN emits a 4-hex fingerprint (`fingerprint(cause) & 0xFFFF:04x`) suitable for correlation without leaking content. Regression: `tests/regression/test_issue_m1_onnx_cause_hygiene.py`.
- **M2 — `model_name` across 7 non-DEBUG `engine.py` log sites** (post-release security-reviewer MED-2 + post-reviewer MED-3): the `model_name` field (a schema-revealing identifier) appeared unhashed at INFO/WARN/ERROR in seven log sites: `evaluate.ok` (INFO), `evaluate.drift.no_monitor_configured` (INFO), `evaluate.drift.no_reference` (INFO), `engine.register.error` (ERROR via `logger.exception`), `engine.register.ok` (INFO), `engine.register.audit_write_failed` (WARN), and `engine.register.onnx_partial_failure` (WARN). Per `rules/observability.md` §8 the rule applies to all non-DEBUG levels — not just WARN. Each site now emits `model_name_fingerprint` (an 8-hex SHA-256 slice matching the canonical cross-SDK contract in `rules/event-payload-classification.md` §2) and partitions a sibling `logger.debug(<event>.detail, ...)` call carrying the raw `model_name` for investigation. A new `_hash_model_name()` helper near the module top centralizes the fingerprint algorithm (SHA-256 is deterministic across processes; Python's built-in `hash()` is PYTHONHASHSEED-randomized and defeats cross-process correlation). Regression: `tests/regression/test_issue_m2_model_name_hygiene.py` — 5 tests (behavioral WARN exercise + AST invariant across all non-DEBUG levels + DEBUG-sibling guard + fingerprint-format invariant + 7-site coverage check).
- **L1 — `engines/_feature_sql.py` used `_validate_identifier` instead of canonical `quote_identifier` at 5 DDL sites** (post-release gold-standards LOW-1): per `rules/dataflow-identifier-safety.md` MUST Rule 1, every dynamic DDL identifier MUST route through `dialect.quote_identifier()` (which BOTH validates AND quotes), not `_validate_identifier()` (which validates only). Migrated five sites: `create_feature_table` (CREATE TABLE + CREATE INDEX), `get_features_latest` (SELECT + ROW_NUMBER), `get_features_as_of`, `get_features_range`, and `upsert_batch`. Regression: `tests/regression/test_issue_l1_feature_sql_quote_identifier.py`.
- **L2 — `tracking/sqlite_backend.py:150` ALTER TABLE hardcoded list missing `_validate_identifier`** (post-release gold-standards LOW-2): the `_COLUMNS_ADDED_IN_0_14` hardcoded list was interpolated into `f"ALTER TABLE experiment_runs ADD COLUMN {name} {sql_type}"` without routing through `_validate_identifier`. Per `rules/dataflow-identifier-safety.md` MUST Rule 5 (Hardcoded Identifier Lists MUST Still Validate), "the list is hardcoded" is BLOCKED as a rationalization — the validation call is a permanent marker of intent that survives any future refactor that makes the list dynamic. The loop now calls `_validate_identifier(name)` before interpolation. Regression: `tests/regression/test_issue_l2_sqlite_backend_alter_table_validation.py`.

## [0.15.1] - 2026-04-20 — post-release audit hotfix (tenant-isolation + spec sync)

Post-release `/redteam` audit of 0.15.0 (security-reviewer + reviewer + gold-standards-validator) surfaced one HIGH security finding and one HIGH spec-staleness finding. Both fixed in this patch.

### Fixed

- **Cross-tenant bypass in `_check_tenant_match`** (security-reviewer HIGH-1): `MLEngine._check_tenant_match` silently permitted an unscoped engine (`tenant_id=None`) to load a tenant-scoped model. Per `specs/ml-engines.md §5.1 MUST 3` and `rules/tenant-isolation.md` Rule 2 ("Missing tenant_id Is a Typed Error"), the unscoped-engine branch against a tenant-scoped model MUST raise `TenantRequiredError`, not pass silently. Fix: the check now raises with an actionable message naming `MLEngine(tenant_id=...)` as the fix. Regression test at `tests/regression/test_tenant_isolation_unscoped_engine.py` (5 cases) locks all four combinations of (engine tenant ∈ {None, "acme"}) × (model tenant ∈ {None, "acme"}).

### Changed

- **`specs/ml-engines.md §12.1` updated** (reviewer HIGH-1 / gold-standards MED-1): Phase status table now reflects shipped state — header bumped to "kailash-ml 0.15.0", 7-row Phase 3/4/5 table replaced with the 2 remaining intentional deferrals (non-holdout split strategies + grpc extras-guard). §12.2 2.0.0 gate items now marked `[x]` for the five satisfied by 0.15.0 (8-method surface, typed dataclass returns, TrainingResult 10-field contract, cache-key "default" forbidden, OnnxExportError on failure).

## [0.15.0] - 2026-04-20 — MLEngine Phase 3/4/5 complete (specs/ml-engines.md §12.1)

Closes the full Phase 3/4/5 punch list from `specs/ml-engines.md §12.1`. All eight documented `MLEngine` methods (`setup`, `compare`, `fit`, `predict`, `finalize`, `evaluate`, `register`, `serve`) now have production implementations. Landed via four parallel worktree shards (PRs #561/#562/#563/#564) + prep commit (7 frozen result dataclasses in `_results.py`).

### Added — Phase 3 (`setup` + `compare` + `finalize`)

- **`MLEngine.setup()`** (PR #561): polars-native data profiling, `schema_hash` idempotency key per §2.1 MUST 6, task-type inference (classification/regression), deterministic holdout split, FeatureStore schema registration with tenant_id persistence. Phase 3.1 (kfold/stratified/walk_forward split strategies) deferred with a loud `NotImplementedError` naming the follow-up.
- **`MLEngine.compare()`** (PR #562): multi-family Lightning sweep. Every family routed through `self.fit()` so Lightning-as-spine holds by construction per §2.1 MUST 7. Default family set derived from task_type (sklearn/xgboost/lightgbm for classification/regression). Best-first leaderboard via `_HIGHER_IS_BETTER_METRICS` / `_LOWER_IS_BETTER_METRICS` sets. Partial-result on timeout + structured WARN log. `ComparisonResult.tenant_id` propagates from engine, every inner `TrainingResult` echoes tenant_id.
- **`MLEngine.finalize()`** (PR #562): retrain on train+holdout (`full_fit=True`) or re-wrap without retrain (`full_fit=False`). Accepts either a `TrainingResult` or a `models://name/v<N>` URI string.

### Added — Phase 4 (`predict` + `evaluate` + `register`)

- **`MLEngine.predict()`** (PR #563): registry hydration + three-channel dispatch (`direct` = in-process onnxruntime, `rest` = Nexus-bound endpoint, `mcp` = stdio transport). Typed `TenantRequiredError` when engine tenant_id does not match the registered model's tenant_id. `ModelNotFoundError` with actionable message when rest/mcp channels are requested without prior `serve()`. Structured entry/exit logs per `rules/observability.md`.
- **`MLEngine.evaluate()`** (PR #562): three modes (holdout/shadow/live). Holdout = offline scoring with default metric set from task_type. Shadow = score + audit as `shadow_evaluate` without drift-monitor update. Live = score + audit as `evaluate` AND update DriftMonitor. Typed `TargetNotFoundError` when target column missing from data.
- **`MLEngine.register()`** (PR #561): 6-framework ONNX-default export via existing `OnnxBridge` (sklearn/xgboost/lightgbm/catboost/torch/lightning). Typed `OnnxExportError` on default-path failure — silent pickle fallback BLOCKED per §4.2 MUST 4. Tenant-aware `(tenant_id, name, version)` primary key on `_kml_model_versions`. `§5.2` audit row written even on failure.

### Added — Phase 5 (`serve`)

- **`MLEngine.serve()`** (PR #563): REST + MCP + gRPC multi-channel bind from a single call per §2.1 MUST 10. REST channel via Nexus, MCP channel via kailash-mcp stdio transport. Per-channel URIs returned in `ServeResult.uris`. Partial-failure rollback — if MCP bind fails after REST bind succeeds, REST is shut down and a typed error is raised (no partial `ServeResult`). Tenant-id propagated to each channel's auth context. gRPC channel requires the `[grpc]` optional extra (loud-failure pattern per `rules/dependencies.md` § Exception).

### Added — new infrastructure

- **7 frozen result dataclasses** in `kailash_ml._results` (`SetupResult`, `ComparisonResult`, `PredictionResult`, `RegisterResult`, `EvaluationResult`, `ServeResult`, `FinalizeResult`). Field shapes are a contract — shards imported them rather than redefining, preventing the parallel-ownership race `rules/agents.md` § "Parallel-Worktree Package Ownership Coordination" documents.
- **`kailash_ml.engines._engine_sql`** (PR #561): identifier-validated DDL helper module for MLEngine auxiliary tables (`_kml_engine_versions`, `_kml_engine_audit`) per `rules/dataflow-identifier-safety.md`.
- **22 new Tier 2 integration test files** across four shards, covering idempotency, tenant propagation, ONNX matrix, export-failure → typed-error path, multi-family compare, shadow/live evaluate modes, direct/rest/mcp predict channels, multi-channel serve, partial-failure rollback, REST tenant-isolation.

### Known deferrals (intentional)

- **`split_strategy != "holdout"` in `setup()`**: kfold / stratified_kfold / walk_forward raise `NotImplementedError` naming Phase 3.1 as the follow-up. Tracked at `workspaces/kailash-ml-gpu-stack/journal/.pending/`.
- **`serve(channels=["grpc"])`**: requires `pip install kailash-ml[grpc]`. Loud-failure `NotImplementedError` naming the extra per `rules/dependencies.md` § Exception.
- **`PredictionResult.device`**: nullable; populated in kailash-ml 0.12.1+ only after fit → immediate-predict. Restored-from-registry predictions carry `None` until 0.15.1 per `specs/ml-engines.md §4.2 MUST 6`.

### Changed

- `kailash_ml.__all__` now exports the 7 new result dataclasses (eager-imported per `rules/orphan-detection.md` §6).
- `MLEngine.engine.py` grew from 676 LOC → ~1800 LOC; helpers split across `_engine_sql.py` (267 LOC) + module-level serve/predict plumbing.

## [0.14.0] - 2026-04-20 — km.doctor + km.track spec completion (ml-backends.md §7, ml-tracking.md §2.4)

Closes the two HIGH findings from the 2026-04-20 /redteam audit: km.doctor shipped 4 of 14 spec items (§7) and km.track persisted 10 of 17 auto-capture fields (§2.4). Both surfaces now ship the full spec-mandated coverage.

### Added — `km.doctor` full §7.1 diagnostic surface (closes #547 follow-up)

- **XPU + TPU probes** — `km.doctor()` now probes all six first-class backends per `specs/ml-backends.md` §1 (adds `xpu` via native `torch.xpu` at torch ≥ 2.5, and `tpu` via `torch_xla`). Status `"missing"` on non-Intel / non-TPU hosts.
- **`precision_matrix`** — per-backend auto-selected precision via `kailash_ml._device.detect_backend` + `resolve_precision`. Matches the concrete precision strings the training pipeline would pass to `L.Trainer(precision=...)`.
- **`extras`** — installed status for `[cuda]`, `[rocm]`, `[xpu]`, `[tpu]`, `[dl]`, `[agents]`, `[explain]`, `[imbalance]` with per-module version probing so "why is this extra missing?" is answerable without shelling out to pip.
- **`family_probes`** — `torch`, `lightning`, `sklearn`, `xgboost`, `lightgbm`, `catboost`, `onnxruntime`, `onnxruntime-gpu` each report installed version or `"not installed"`. `onnxruntime-gpu` uses `importlib.metadata.version` so it distinguishes CPU vs GPU wheel.
- **`onnx_eps`** — enumerates `onnxruntime.get_available_providers()` (CoreML / CUDA / CPU / Azure EPs) when onnxruntime is importable.
- **`sqlite_path`** — default `~/.kailash_ml/ml.db` (or `KAILASH_ML_STORE` override) with writability probe via a throwaway `.km-doctor-probe.sqlite` file; never touches a live ml.db.
- **`cache_paths`** — data_root + cache directories with recursive byte size AND filesystem total/free via `shutil.disk_usage`.
- **`tenant_mode`** — single-tenant vs multi-tenant, derived from `KAILASH_ML_DEFAULT_TENANT` (primary) with `KAILASH_TENANT_ID` fallback.
- **`gotchas`** — `specs/ml-backends.md` §1.1 entries surfaced per detected `status=ok` backend so operators see backend-specific caveats (MPS CPU fallback, XLA 30s compile pause, CUDA_VISIBLE_DEVICES hint, etc.).
- **`selected_default`** — the backend `detect_backend(None)` would return, derived from priority walk over ok-status probes.
- **14 additional Tier 2 tests** at `tests/integration/test_km_doctor.py` verifying every new JSON section has the spec-required shape.

### Added — `km.track` auto-capture completes §2.4 17-field envelope (closes #548 follow-up)

- **7 new persisted columns** added to `experiment_runs`: `kailash_ml_version`, `lightning_version`, `torch_version`, `cuda_version`, `device_used`, `accelerator`, `precision`. Every `km.track()` run now persists the full reproducibility envelope `specs/ml-tracking.md` §2.4 mandates.
- **`_capture_versions()` helper** — probes `kailash_ml.__version__` (always), `torch.__version__` + `torch.version.cuda` (when importable), `lightning.__version__` (when importable). Each probe is wrapped separately so a partial stack still yields as many fields as possible.
- **`ExperimentRun.attach_training_result`** extended to mirror `TrainingResult.device_used` / `.accelerator` / `.precision` (top-level reproducibility fields) in addition to the existing `device.*` `DeviceReport` envelope. Never stores `"auto"` — fields pass through as concrete strings.
- **Additive schema migration** — `initialize()` now probes `PRAGMA table_info(experiment_runs)` and runs `ALTER TABLE ADD COLUMN` for each 0.14 column missing from pre-0.14 databases. Existing `~/.kailash_ml/ml.db` files keep working; historical rows carry SQL `NULL` for the new fields.
- **2 new Tier 2 tests** at `tests/integration/test_km_track.py`:
  - `test_km_track_all_17_auto_capture_fields_present` — mechanical whitelist check that every §2.4 field is a persisted column.
  - Extended trainable-integration test to assert `row["device_used"] == result.device_used`, `row["accelerator"] == result.accelerator`, `row["precision"] == result.precision` with the explicit "never `auto`" guard.

### Fixed

- **Partial-implementation orphans** — both km.doctor (`10/14` checks) and km.track (`10/17` fields) shipped as partial MVPs in 0.13.0. 0.14.0 closes each to the full spec-mandated surface; no deferred sub-items remain.

## [0.13.0] - 2026-04-20 — ONNX bridge matrix completion + km.track + km.doctor

Three spec-compliance issues resolved in one minor release: #546 (ONNX matrix), #547 (km.doctor), #548 (km.track Phase 6).

### Added — ONNX bridge matrix completion (closes #546)

- **`OnnxBridge._export_torch`** — torch.nn.Module -> ONNX via `torch.onnx.export` with opset 17 and `dynamic_axes` on the batch dimension. Accepts `np.ndarray`, `polars.DataFrame`, or `torch.Tensor` for `sample_input`.
- **`OnnxBridge._export_lightning`** — `LightningModule` -> ONNX. Routes through `model.to_onnx()` when available, with direct `torch.onnx.export` fallback. Same opset / dynamic_axes contract as torch.
- **`OnnxBridge._export_catboost`** — native `model.save_model(path, format="onnx")` branch. Uses `NamedTemporaryFile` round-trip when no `output_path` is supplied.
- **`OnnxBridge.export(sample_input=...)` kwarg** — required for torch / lightning exports (torch.onnx.export traces the forward pass with a concrete tensor). Tabular branches continue to use `n_features`.
- **6 Tier 2 ONNX round-trip regression tests** at `tests/integration/test_onnx_roundtrip_{sklearn,xgboost,lightgbm,catboost,torch,lightning}.py` — each trains a minimal model, exports via `OnnxBridge.export`, re-imports via `onnxruntime.InferenceSession`, asserts prediction parity within `np.allclose(rtol=1e-3, atol=1e-5)`. XGBoost / LightGBM skip on darwin-arm + py3.13 per pre-existing segfault pattern. CatBoost skips gracefully when the `[catboost]` extra is not installed. Torch additionally covers dynamic-batch-size inference. Resolves `specs/ml-engines.md` §6.1 MUST 3.
- **`_COMPAT_MATRIX` entries for `"torch"`, `"lightning"`, `"catboost"`**.

### Added — `km.track()` Phase 6 (closes #548)

- **`km.track(experiment, ...) -> AsyncContextManager[ExperimentRun]`** — replaces the previous `NotImplementedError` stub. Async-context entry point per `specs/ml-tracking.md §2.1`; on enter creates a run and auto-sets status `RUNNING`, on exit auto-sets `COMPLETED` / `FAILED` / `KILLED`.
- **16 auto-capture fields** per `specs/ml-tracking.md §2.4` — `host`, `python_version`, `git_sha`, `git_branch`, `git_dirty`, `wall_clock_start`, `wall_clock_end`, `duration_seconds`, `status`, `tenant_id`, `run_id`, `parent_run_id`, `device_family`, `device_backend`, `device_fallback_reason`, `device_array_api`. Git metadata captured via subprocess with graceful fallback on no-git environments. `tenant_id` resolves from explicit kwarg or `KAILASH_TENANT_ID` env. `parent_run_id` propagates via `contextvars` for nested `km.track()` calls. `device_*` fields populate from the most recent `TrainingResult.device` when a Trainable runs inside the context.
- **Run-status auto-set** per `specs/ml-tracking.md §2.2` — `COMPLETED` on clean exit, `FAILED` on exception (captures `exc_type.__name__` + traceback), `KILLED` on SIGINT/SIGTERM via `signal.signal` handler installed at `__aenter__` and restored at `__aexit__`.
- **`SQLiteTrackerBackend`** — default async SQLite backend at `~/.kailash_ml/ml.db` with WAL journal mode. 20-column `experiment_runs` schema. All SQL uses `?` placeholders; identifiers are fixed literals.
- **9 Tier 2 integration tests** at `tests/integration/test_km_track.py`.

### Added — `km.doctor()` backend diagnostic (closes #547)

- **`km.doctor(require=None, as_json=False) -> int`** — diagnostic probe per `specs/ml-backends.md §7`. Exit codes: `0` all-green, `1` warnings, `2` failures. Probes `cpu`, `cuda`, `mps`, `rocm`.
- **`--require=<backend>`** — fails-fast with exit 2 when the named backend is absent. CI-lane gate for training-job prerequisites.
- **`--json`** — structured report per spec §7.2 (`backend`, `status`, `version`, `devices`, `warnings`, `failures`).
- **`km-doctor` console script** — registered in `[project.scripts]` as `km-doctor = "kailash_ml.doctor:main"`. Operators run `km-doctor --require=cuda` to gate training jobs.
- **7 Tier 2 integration tests** at `tests/integration/test_km_doctor.py`.

### Fixed

- **ONNX compatibility matrix orphan** — prior to this release, `_COMPAT_MATRIX` advertised `pytorch` as exportable but `OnnxBridge.export()` fell through to the generic "Export not implemented" skip path for torch / lightning / catboost. Every framework key in the matrix now has an implemented export branch AND a Tier 2 round-trip regression test exercising that branch through `onnxruntime` (orphan guard per `rules/orphan-detection.md` §2a).
- **`km.track` / `km.doctor` NotImplementedError / missing-symbol orphans** — both spec-documented entry points now ship with real implementations, public-symbol exports in `__all__`, and Tier 2 coverage.

## [0.12.1] - 2026-04-20 — Predictions.device field + kailash>=2.8.9 floor bump

### Added

- **`Predictions.device: Optional[DeviceReport]` field** — Completes the predict-side half of the GPU-first Phase 1 transparency contract that 0.12.0 deferred. Every Phase 1 family adapter (`SklearnTrainable`, `XGBoostTrainable`, `LightGBMTrainable`, `TorchTrainable`, `LightningTrainable`, `UMAPTrainable`, `HDBSCANTrainable`) now caches the fit-time `DeviceReport` on `self._last_device_report` and stamps the same instance onto every `Predictions` returned until the next `fit()` call. Callers can now programmatically distinguish a CUDA-resolved predict from a CPU-fallback predict via `pred.device.backend` / `pred.device.fallback_reason` without inspecting the prior `TrainingResult`. Direct constructors that don't carry `device=` keep the backward-compat `None` default. Resolves `workspaces/kailash-ml-gpu-stack/journal/0005-GAP-predictions-device-field-missing.md`.
- **`tests/regression/test_predictions_device_invariant.py`** — 3 mechanical AST guards that fail loudly if a future refactor drops the `device=` kwarg from a `Predictions(...)` constructor inside `predict()`, fails to cache `self._last_device_report` in `fit()`, or removes the `_device` slot / `device` property on `Predictions`.
- **`tests/integration/test_predictions_device_matrix.py`** — 9 Tier 2 backend-matrix tests (7 pass on this host; 2 skipped per the darwin-arm XGBoost/LightGBM segfault pattern from 0.12.0) that exercise `fit → predict` end-to-end and assert `pred.device is result.device` (identity, not equality) for every family.

### Changed

- **`kailash>=2.8.9` floor bump** — Picks up the `app.router.startup()` / `.shutdown()` fix that shipped in kailash 2.8.9 via issue #538. Staggered adoption per issue #541 — each sibling package bumps its floor on its next natural minor release rather than a coordinated bundle. kailash-ml's floor bump lands here bundled with the `Predictions.device` work.

### Fixed

- **Removes the 0.12.0 Known Limitation for `Predictions.device`.** 0.12.0's changelog disclosed that the predict-side transparency contract was incomplete; 0.12.1 closes that gap.

## [0.12.0] - 2026-04-19 — GPU-first Phase 1 punch list: Trainable adapters + transparency

### Added

- **`SklearnTrainable` Array-API auto-dispatch** — When the caller passes a non-CPU `TrainingContext.backend` AND the wrapped estimator is on the Phase 1 allowlist (`Ridge`, `LogisticRegression`, `LinearRegression`, `LinearDiscriminantAnalysis`, `KMeans`, `PCA`, `StandardScaler`, `MinMaxScaler`), the inner Lightning fit runs inside `sklearn.config_context(array_api_dispatch=True)` with X/y moved to a torch tensor on the resolved device. Emits INFO `sklearn.array_api.engaged` log. Off-allowlist estimators on a non-CPU backend log WARN `sklearn.array_api.offlist` and proceed on CPU numpy. (Item 3 of revised-stack.md)
- **`SklearnTrainable` runtime fallback for scipy env-var gate** — `sklearn.config_context(array_api_dispatch=True)` requires `SCIPY_ARRAY_API=1` to be set BEFORE any sklearn/scipy import. When that precondition isn't met, the call raises at enter-time. The adapter now catches that and falls back to the CPU numpy path with WARN `sklearn.array_api.runtime_unavailable` so the deployment gap surfaces in log aggregators rather than as a hard failure.
- **`XGBoostTrainable` GPU OOM single-retry fallback** — A GPU OOM during `trainer.fit` is intercepted; the adapter logs WARN `xgboost.gpu.oom_fallback`, rebuilds on CPU, and returns a `TrainingResult` whose `device.fallback_reason="oom"` and `device.backend="cpu"`. Non-OOM exceptions re-raise unchanged. (Item 4)
- **`LightGBMTrainable` GPU OOM single-retry fallback** — Same pattern as XGBoost; logs WARN `lightgbm.gpu.oom_fallback` on the fallback path.
- **`UMAPTrainable` (CPU-only Phase 1)** — New `kailash_ml.UMAPTrainable` wraps `umap-learn` as a Trainable. Phase 1 is CPU-only per the cuML eviction decision (revised-stack.md CRITICAL-1). When called with a non-CPU `TrainingContext.backend`, logs INFO `umap.cuml_eviction` (not WARN — this is the documented Phase 1 design) and runs on CPU. The returned `DeviceReport.fallback_reason="cuml_eviction"` so callers can distinguish this from an OOM or driver-missing fallback. Phase 2 adds torch-native UMAP across MPS/ROCm/XPU. (Item 5)
- **`HDBSCANTrainable` (CPU-only Phase 1)** — New `kailash_ml.HDBSCANTrainable` wraps `sklearn.cluster.HDBSCAN` (sklearn 1.3+) as a Trainable. Same cuml_eviction logging contract as `UMAPTrainable`.
- **`TrainingResult.device: Optional[DeviceReport]` field** — Append-only optional field that every Phase 1 Trainable family adapter populates. Carries family / backend / device_string / precision / fallback_reason / array_api so callers can distinguish a CUDA execution from a silent CPU fallback. Required for the orphan-detection §6 contract — `DeviceReport` is now wired into the production hot path of every Phase 1 family.
- **Tier 2 backend-matrix tests** — `tests/integration/test_trainable_backend_matrix.py` exercises every Phase 1 Trainable across CPU + (where available) MPS / CUDA with real estimators, real Lightning Trainer, no mocking. (Item 7)

### Removed

- **`kailash-ml[rapids]` extra** — Verified absent. Phase 1 cuML eviction is complete; users who need cuML on NVIDIA install it themselves and swap it in via the Trainable layer. (Item 8)

### Fixed

- **`UMAPTrainable.__init__` warning hygiene** — Pre-set `n_jobs=1` so umap-learn's "n_jobs overridden by random_state" UserWarning doesn't fire.
- **`HDBSCANTrainable.__init__` warning hygiene** — Pre-set `copy=True` so sklearn 1.5+ FutureWarning about the `copy` default change to 1.10 doesn't fire.
- **`engines/dim_reduction.py::_reduce_umap` warning hygiene** — Same `n_jobs=1` preset (resolves a pre-existing warning that was outside the Phase 1 scope but caught under zero-tolerance Rule 1 ownership).

### Known Limitations

- **`Predictions.device` field not yet populated.** The spec's "Transparency contract" mandates that every `predict()` return carry a `DeviceReport`, but the `Predictions` class in 0.12.0 exposes only `raw` / `column` / `to_polars()`. Callers can inspect the FIT-time `TrainingResult.device` (wired across all 7 family adapters in this release) to identify the device that executed the model. Scheduled for 0.12.1 — requires an API addition to `Predictions` plus per-family `predict()` updates. See journal entry `0005-GAP-predictions-device-field-missing.md` for the 0.12.1 plan.

### Test counts

- 957 passed / 5 skipped / 0 warnings in the unit + regression + Tier 2 suites (943 unit + 6 Tier 2 + 2 new regression invariants + 6 new sklearn array-API).
- 4 Tier 2 skips on darwin-arm (XGBoost / LightGBM segfault on darwin-arm + py3.13 — Tier 2 ships on Linux CI; SCIPY_ARRAY_API=1 precondition skip when env-var unset).

## [0.11.0] - 2026-04-19 — GPU-first Phase 1: DeviceReport + km.device()/use_device() (#523)

### Added

- **`DeviceReport` dataclass (#523)**: `kailash_ml.DeviceReport` captures the full hardware inventory at import or call time — CUDA device list (name, memory, compute capability), MPS availability (Apple Silicon), CPU count, and a `best_device` recommendation (`"cuda:0"`, `"mps"`, or `"cpu"`). Constructed via `km.device()` or `DeviceReport.probe()`.
- **`km.device()` factory function (#523)**: `import kailash_ml as km; report = km.device()` probes and returns a `DeviceReport`. Zero-argument convenience wrapper over `DeviceReport.probe()`.
- **`km.use_device(device=None)` context manager (#523)**: Activates a PyTorch device context for the duration of the `with` block. Accepts a string device specifier (e.g. `"cuda:0"`, `"mps"`, `"cpu"`), a `torch.device`, or `None` (auto-selects `DeviceReport.probe().best_device`). Raises `DeviceNotAvailableError` if the requested device is not present.
- **`DeviceNotAvailableError` typed exception (#523)**: Raised by `km.use_device()` when the requested device is not present on the host. Carries `requested_device` and `available_devices` attributes for programmatic handling.

## [0.10.0] - 2026-04-19 — Pipeline, FeatureUnion, ColumnTransformer + register_estimator (#479 #488)

### Added

- **`Pipeline` + `FeatureUnion` + `ColumnTransformer` estimators (#479 #488, PR #506)**: Three sklearn-compatible compositing estimators now ship in `kailash_ml.estimators`. `Pipeline` chains ordered `(name, estimator)` steps where each step's `transform` output feeds the next step's input; the final step may be a classifier or regressor and exposes `fit`, `predict`, `predict_proba`. `FeatureUnion` runs multiple transformers in parallel and concatenates their outputs column-wise. `ColumnTransformer` applies per-column transformer lists and handles remainder columns via `passthrough` or `drop`. All three are registered with the `kailash_ml` estimator registry and exported from `kailash_ml.__init__`.
- **`register_estimator` / `unregister_estimator` public API (#488)**: `kailash_ml.register_estimator(name, cls)` and `unregister_estimator(name)` expose the estimator registry for user-defined or third-party sklearn-compatible estimators. Registered estimators are reachable by name inside `Pipeline` / `FeatureUnion` / `ColumnTransformer` step lists and via `AutoMLEngine` hyperparameter search. `register_estimator` raises `ValueError` on name collision unless `force=True` is passed.

## [0.7.0] - 2026-04-07

### Added

- **ModelExplainer engine** — SHAP-based model explainability with global, local, and dependence explanations; plotly visualizations; optional `[explain]` extra (`shap>=0.44`)
- **Model calibration** — `TrainingPipeline.calibrate()` wraps classifiers in `CalibratedClassifierCV` (Platt scaling, isotonic regression)
- **Auto-logging** — `TrainingPipeline.train(tracker=...)`, `HyperparameterSearch.search(tracker=...)`, and `AutoMLEngine.run(tracker=...)` automatically log params, metrics, and artifacts to ExperimentTracker
- **Nested experiment runs** — `ExperimentTracker.start_run(parent_run_id=...)` for hierarchical run organization; HPO trials log as children of the search run
- **Inference signature validation** — `InferenceServer.predict()` validates required features against model signature instead of silently defaulting missing features to 0.0
- **Preprocessing: 4 normalization methods** — `normalize_method` parameter: zscore, minmax, robust, maxabs
- **Preprocessing: KNN and iterative imputation** — `imputation_strategy="knn"` and `"iterative"` via sklearn imputers
- **Preprocessing: multicollinearity removal** — `remove_multicollinearity=True` drops highly correlated features using Pearson correlation
- **Preprocessing: class imbalance handling** — `fix_imbalance=True` with SMOTE, ADASYN (optional `[imbalance]` extra), or `class_weight` method
- **New optional extras** — `[imbalance]` (imbalanced-learn>=0.12), `[explain]` (shap>=0.44)

### Fixed

- **Stratified k-fold** — `split_strategy="stratified_kfold"` now uses `sklearn.model_selection.StratifiedKFold` instead of silently falling back to regular k-fold
- **Successive halving** — `strategy="successive_halving"` now uses Optuna's `SuccessiveHalvingPruner` with progressive resource allocation instead of silently falling back to random search
- **K-fold shuffling** — `_kfold_first_fold` now shuffles data via `sklearn.model_selection.KFold` instead of naively slicing
- Silent `except: pass` on `predict_proba` replaced with `logger.debug`
- Schema migration `except Exception: pass` narrowed to check for "duplicate column"
- `BaseException` catch in run context manager changed to `Exception`
- Path traversal guard added to `delete_run` artifact cleanup
- String target + multicollinearity no longer crashes (falls back to index-based dropping)
- AutoML deep search now passes `parent_run_id` to nested HPO search

### Changed

- **Breaking**: `scikit-learn>=1.5` (was >=1.4) — required for `FrozenEstimator` in calibration
- `asyncio.get_event_loop()` replaced with `asyncio.get_running_loop()` (Python 3.12+ deprecation fix)

### Security

- R1 red team converged: 0 CRITICAL, 0 HIGH findings after fixes
- Inference server no longer silently produces wrong predictions for missing features
- Experiment tracker artifact deletion has path containment validation
- 750 tests passing (677 unit + 60 integration + 13 examples), 0 regressions

## [0.6.0] - 2026-04-07

### Added

- **PreprocessingPipeline cardinality guard** — `max_cardinality=50` threshold with `exclude_columns` parameter; mixed one-hot + ordinal encoding for high-cardinality categoricals
- **ModelVisualizer EDA charts** — `histogram()`, `scatter()`, `box_plot()` methods accepting polars DataFrame
- **ExperimentTracker factory** — `ExperimentTracker.create()` convenience constructor
- **`training_history()` y_label parameter** — customizable y-axis label for training history plots

### Fixed

- Corrected HyperparameterSearch README example to match actual API
- Removed stale `tracker.initialize()` from README Engine Initialization section

## [0.2.0] - 2026-04-02

### Added

- **13 ML engines**: FeatureStore, ModelRegistry, TrainingPipeline, InferenceServer, DriftMonitor, HyperparameterSearch, AutoMLEngine, DataExplorer, FeatureEngineer, EnsembleEngine, ExperimentTracker, PreprocessingPipeline, ModelVisualizer
- **6 Kaizen agents**: DataScientistAgent, FeatureEngineerAgent, ModelSelectorAgent, ExperimentInterpreterAgent, DriftAnalystAgent, RetrainingDecisionAgent with LLM-first reasoning
- **RL module**: RLTrainer (SB3 wrapper), EnvironmentRegistry, PolicyRegistry
- **Agent guardrails**: AgentGuardrailMixin with LLM cost tracking, approval gates, audit trails
- **Interop module**: polars-native with sklearn, LightGBM, Arrow, pandas, HuggingFace converters
- **Shared utilities**: `_shared.py` (NUMERIC_DTYPES, ALLOWED_MODEL_PREFIXES, compute_metrics_by_name)
- **SQL encapsulation**: `_feature_sql.py` — all raw SQL in one auditable module

### Fixed

- SQL type injection prevention via `_validate_sql_type()` allowlist
- FeatureStore `_table_prefix` validated in constructor
- `ModelRegistry.register_model()` no longer accesses private `_root` on ArtifactStore
- `AutoMLConfig.max_llm_cost_usd` validated with `math.isfinite()`
- `_compute_metrics` duplication eliminated via shared module
- Dead `_types.py` removed (duplicate ModelSpec/EvalSpec/TrainingResult)
- 29+ dataclasses now have `to_dict()`/`from_dict()` per EATP convention

### Security

- R1+R2+R3 red team converged: 0 CRITICAL, 0 HIGH findings
- NaN/Inf validation on all financial fields
- Bounded collections (deque maxlen) on all long-running stores
- Model class allowlist for dynamic imports
- 508 tests passing, 0 regressions

## [0.1.0] - 2026-03-30

### Added

- Initial release with package skeleton and interop module

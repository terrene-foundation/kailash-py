# Kailash ML Model Registry Specification (v1.0 Draft)

Version: 1.0.0 (draft)

**Status:** DRAFT — shard 4A of round-2 spec authoring. Resolves round-1 CRIT "two parallel registries" (T5) and the round-1 CRIT "no actor_id / audit on mutations" finding.
**Sibling specs:** `ml-engines.md` §3–§6 (MLEngine primitives, multi-tenancy, ONNX-default), `ml-serving.md` (consumes registry), `ml-drift.md` (consumes registry aliases), `ml-tracking.md` (run-level lineage source).
**Scope:** ONE canonical tenant-scoped model registry with actor+audit on every mutation. Replaces `engines/model_registry.py::ModelRegistry` (single-tenant production) AND deletes `engines/_engine_sql.py::_kml_engine_versions` + `engine.py::MLEngine._kml_engine_versions` scaffold (tenant-aware but `NotImplementedError`).

---

## 1. Scope and Non-Goals

### 1.1 What the ModelRegistry IS

The model registry is the canonical, tenant-scoped, audit-trailed persistence layer for trained-model metadata, versioned artifacts, and promotion state. Every kailash-ml engine that trains, serves, monitors, diagnoses, or explains a model MUST resolve the model through this registry and MUST NOT bypass it with filesystem paths or pickle handles.

The registry owns four concerns:

1. **Versioning** — integer-monotonic versions per `(tenant_id, name)` pair.
2. **Aliases** — semantic pointers (`@production`, `@staging`, `@champion`, `@challenger`, user-defined) that resolve to a specific version.
3. **Lineage** — every version MUST link back to its training run_id, dataset hash, and code SHA. Models without lineage are BLOCKED.
4. **Audit** — every mutation (register, promote, demote, delete, alias change) writes a row to `_kml_model_audit` persisting `(occurred_at, tenant_id, actor_id, resource, version, operation, prev_state, new_state, reason)`.

### 1.2 What the ModelRegistry IS NOT

- Not a training engine (lives in `ml-engines.md` + `training_pipeline.py`).
- Not a serving engine (lives in `ml-serving.md`).
- Not a feature store (lives in `ml-engines.md` §5 `FeatureStore`).
- Not a tracking backend (lives in `ml-tracking.md` `ExperimentTracker`). The registry persists **model lineage pointers to runs**; the tracker persists run metrics and params.
- Not an artifact byte store — artifacts are offloaded to a content-addressed `ArtifactStore` (§10). The registry persists the CAS digest and the format dispatcher, not the bytes.

### 1.3 Non-Goals as MUST NOT

- **MUST NOT** expose two parallel registry classes in the public package surface. `MLEngine._kml_engine_versions` + `_engine_sql.py` scaffold are DELETED in the same PR that lands this spec per `rules/orphan-detection.md` §3.
- **MUST NOT** accept a registration without `tenant_id` + `actor_id` + `lineage`. Anonymous or lineage-less registrations are BLOCKED (typed error, §13).
- **MUST NOT** use pickle as the default artifact format. Pickle is opt-in with a loud warning at load time; ONNX is the default (§11).
- **MUST NOT** persist model bytes inside the `_kml_model_versions` row. Bytes live in the artifact store; the row holds the digest.

---

## 2. Resolution Decision — Two Registries Collapse Into One

### 2.1 The Two-Registry Problem

Round-1 MLOps audit §"Severity Matrix" row 1 grounded the finding mechanically:

- `packages/kailash-ml/src/kailash_ml/engines/model_registry.py:473` — writes `_kml_models` (no tenant, no actor, no audit, single-tenant).
- `packages/kailash-ml/src/kailash_ml/engines/_engine_sql.py:93` — defines `_kml_engine_versions` with `PRIMARY KEY (tenant_id, name, version)` + `_kml_engine_audit` with `actor_id`. Tenant-aware but the `MLEngine.register()` consumer raises `NotImplementedError` at `engine.py:75-80`.

The two paths do not converge. A user calling `ModelRegistry.register_model(...)` today writes to `_kml_models`; the tenant-aware tables + audit surface are orphan per `rules/orphan-detection.md` §1. This is the exact Phase 5.11 `TrustAwareQueryExecutor` failure pattern.

### 2.2 The Decision

**DELETE** `MLEngine._kml_engine_versions` scaffold + the `_PHASE_4` sentinel + `_engine_sql.py::_kml_engine_versions` in the same PR.

**PROMOTE** `ModelRegistry` as the SOLE path AND backfill the three missing dimensions the scaffold exposed but never consumed:

1. `tenant_id` required on every constructor + op (§5.1 already mandated in `ml-engines.md` §5.1 MUST 1).
2. `actor_id` required on every mutation (register, promote, demote, alias set).
3. Audit row per mutation, indexed on `(tenant_id, occurred_at, actor_id)`.

Migration for existing `_kml_models` rows:

- Add columns: `tenant_id TEXT NOT NULL DEFAULT '_single'`, `actor_id TEXT NOT NULL DEFAULT 'legacy-migration'`, `lineage_run_id TEXT`, `lineage_dataset_hash TEXT`, `lineage_code_sha TEXT`.
- Backfill `tenant_id='_single'` for every existing row (canonical cross-spec sentinel per `ml-tracking.md §7.2`).
- Unique key migrates from `(name, version)` to `(tenant_id, name, version)`.
- One-shot audit row per backfilled version: `(occurred_at=now, tenant_id='_single', actor_id='legacy-migration', resource='model', operation='backfill', prev_state=null, new_state=version_json, reason='v2.0 schema upgrade')`.

Migration is a numbered schema migration per `rules/schema-migration.md` — not an inline `ALTER TABLE`.

### 2.3 BLOCKED Rationalizations

- "Keep both registries and let users pick" — both writing to the same underlying SQLite produces interleaved versions, per-row race conditions, and non-deterministic promotion order. `rules/zero-tolerance.md` Rule 2 fake-feature.
- "Deprecate `MLEngine._kml_engine_versions` over 2 releases" — `rules/orphan-detection.md` §3: removed = deleted, not deprecated.
- "The scaffold is for the Phase 4 future, leave it" — a scaffold with `NotImplementedError` + no production call site IS the failure mode. Delete before release.
- "Preserve the `_kml_engine_audit` table for the future" — `_kml_model_audit` is the future. Collapse, don't parallel-track.

### 2.4 Why

The two-registry state is the textbook Phase 5.11 orphan that `rules/facade-manager-detection.md` Rule 1 exists to prevent: the tenant-aware path is exposed as a public surface with zero production call sites, while the production path quietly single-tenants every user. Collapsing to one registry closes the orphan AND closes the three dimensions the scaffold pretended to cover in one shard.

---

## 3. Model Names and Versions

### 3.1 Uniqueness Key

Every model version row is uniquely identified by the composite key `(tenant_id, name, version)`. The table-level unique index MUST enforce this. Single-tenant deployments use the literal string `"_single"` as `tenant_id` — the canonical cross-spec sentinel per `ml-tracking.md §7.2`. The strings `"default"` and `"global"` are BLOCKED.

```python
# DO — tenant in the uniqueness key
# CREATE UNIQUE INDEX _kml_models_uk ON _kml_model_versions (tenant_id, name, version);

# DO NOT — name-only uniqueness (current single-tenant production)
# CREATE UNIQUE INDEX _kml_models_uk ON _kml_model_versions (name, version);
```

### 3.2 Integer-Monotonic Versions

Versions are integers starting at 1 and monotonically increasing WITHIN a `(tenant_id, name)` scope. Two tenants each registering `"fraud"` independently get their own `v1, v2, v3, …` sequences.

The registry MUST compute the next version inside the same transaction as the row insert:

```sql
-- DO — next version computed atomically
INSERT INTO _kml_model_versions (tenant_id, name, version, ...)
VALUES (
  :tenant_id, :name,
  COALESCE((SELECT MAX(version) FROM _kml_model_versions
            WHERE tenant_id = :tenant_id AND name = :name), 0) + 1,
  ...
) RETURNING version;
```

```python
# DO NOT — two-round-trip compute-then-insert (race: two concurrent registrations collide)
v = await conn.fetchval("SELECT MAX(version) FROM ... WHERE name=$1", name)
await conn.execute("INSERT INTO ... (version) VALUES ($1)", v + 1)
```

**Why:** A two-round-trip sequence loses the serializability guarantee of the database; two agents registering a new version in the same millisecond collide at the unique index. Computing in one statement moves the race into the database's conflict-resolution path where it always resolves correctly.

### 3.3 Reserved Name Patterns

Model names MUST match `^[a-zA-Z][a-zA-Z0-9_-]{0,127}$` and MUST NOT start with any of the reserved prefixes:

- `_kml_` — internal tables (see `rules/dataflow-identifier-safety.md` MUST 2).
- `system_` — reserved for operational controls.
- `internal_` — reserved for kailash-ml internal state.
- `__` (double underscore) — reserved for framework-internal models.

Registration with a reserved-prefix name MUST raise `InvalidModelNameError`. Single-underscore-prefix (`_my_model`) is permitted but emits a DEBUG log noting the convention.

### 3.4 Aliases Scope Rule

An alias (e.g. `@production`) resolves only within `(tenant_id, name)` scope. Tenant A's `fraud@production` and tenant B's `fraud@production` are disjoint pointers. Resolution through the registry MUST carry `tenant_id` on every call per `rules/tenant-isolation.md` MUST 1.

---

## 4. Aliases — Semantic Pointers to Versions

### 4.1 MUST Rules

#### 1. Aliases Are Mutable Pointers, Not Strings Baked Into Metadata

An alias is a `(tenant_id, name, alias, version)` row in `_kml_model_aliases`. A model version does NOT carry a `stage` column — stage assignment lives in the alias table only. This replaces the `_kml_models.current_stage` column from the single-tenant scaffold.

```python
# DO — alias is a named pointer; the version row is immutable
await registry.set_alias(
    name="fraud", version=7, alias="@production",
    tenant_id="acme", actor_id="agent-42", reason="promotion sign-off",
)
# _kml_model_aliases row: ("acme", "fraud", "@production", 7)

# DO NOT — stage stored on the version row (single-tenant legacy)
await conn.execute("UPDATE _kml_models SET current_stage='production' WHERE version=7")
```

**Why:** A version may simultaneously hold multiple aliases (e.g. `@production` AND `@champion`). Storing stage on the version row forces single-valued stage semantics, which is strictly weaker.

#### 2. Reserved Aliases

The following alias strings are reserved and MUST be resolvable by default resolution:

- `@production` — the version currently serving live production traffic.
- `@staging` — the version under pre-production validation.
- `@champion` — the current-best model per the team's evaluation criteria.
- `@challenger` — the model attempting to unseat `@champion`.
- `@shadow` — the version currently receiving shadow traffic (see `ml-serving.md` §6).
- `@archived` — sentinel alias automatically set by `demote_model`.

User-defined aliases MUST start with `@` and match `^@[a-zA-Z][a-zA-Z0-9_-]{0,63}$`.

#### 3. Alias Mutations Are Atomic

Setting an alias (e.g. `@production`) MUST be atomic per `(tenant_id, name, alias)`. Two concurrent `set_alias("fraud", "@production", ...)` calls produce exactly one winning version; the other call may either (a) retry with `AliasConcurrentUpdateError` raised if strict or (b) last-writer-wins behind a monotonic `sequence_num` column — the implementation MUST pick one and document it.

Recommended: last-writer-wins with `sequence_num` bump on every set, so the audit trail contains every intermediate state.

#### 4. Every Alias Mutation Writes An Audit Row

`set_alias`, `clear_alias`, `promote_model`, `demote_model` each write an audit row (§8) with `operation="alias_set"` or `"alias_clear"` or `"promote"` or `"demote"`, `prev_state` containing the previous `(alias, version)` if any, and `new_state` containing the new mapping.

#### 5. Alias Deletions Are Soft

Clearing an alias MUST NOT delete the row; it sets `cleared_at = now` and emits an audit row. The previous pointer is recoverable via the audit trail.

### 4.2 Non-Reserved Aliases Are User-Defined But Tenant-Scoped

Teams MAY define custom aliases (e.g. `@friday-release`, `@iberia-region`) subject to the naming regex in §4.1 MUST 2. All alias operations carry `tenant_id` and are never cross-tenant.

---

## 5. Signatures

### 5.1 Every Version MUST Have A Signature

Every `_kml_model_versions` row MUST persist a non-null `signature` JSONB column containing:

- `inputs` — list of `(name, dtype, nullable, shape_or_null)` tuples. `dtype` uses polars-native type names (`Float64`, `Int64`, `Utf8`, `Categorical`, `Datetime`, …) per `ml-engines.md` §4.
- `outputs` — same shape for the prediction.
- `params` — optional dict of hyperparameters (framework-dependent).

Registration without an explicit signature MUST attempt schema inference from the attached `TrainingResult.feature_schema + target_schema` per `ml-engines.md` §4.2. If inference fails (no training result attached or schema unknown), MUST raise `SignatureMismatchError` with an actionable message.

### 5.2 Signature Enforcement On Serving And Drift

The signature is the contract the serving layer (`ml-serving.md` §12) and the drift monitor (`ml-drift.md` §3) enforce on inputs. A mismatch at serve time is `InvalidInputSchemaError`; a mismatch at drift-check time is a drift-reference error.

### 5.3 Signature Versioning On Retrain

When a new version is registered for the same `(tenant_id, name)` with a changed signature (columns added/removed, dtype changed), the registry MUST:

1. Persist the new signature as-is.
2. Emit an audit row with `operation="register"` AND `signature_changed=True` + a JSON diff in the audit row's `metadata`.
3. Leave old aliases pointing at their old versions unchanged — upstream callers consuming `@production` transparently keep the old signature until the alias is explicitly repointed.

**Why:** Silent signature mutation on `set_alias("@production", new_version)` is the textbook "I promoted and now every request fails" failure. Making the mutation explicit + audited turns the failure into a pre-flight check.

### 5.6 ONNX Export Probe

Resolves Round-4 HIGH B11' + A10-3: `ml-serving §2.5.1` references "the ONNX-export probe in `ml-registry §4`" but §4 is the Aliases chapter. The probe actually lives here as §5.6. Every `register_model(..., format="onnx")` call MUST exercise the probe below at registration time — the registry, NOT the serving layer, is where unsupported-op enumeration is discovered and persisted, so the serving layer can refuse at load time instead of crashing mid-request.

#### 5.6.1 Probe Contract (MUST)

When `format="onnx"` is passed to `register_model(...)`, the registry MUST:

1. **Attempt strict export** — call `torch.onnx.export(training_result.trainable.model, example_inputs, buf, strict=True, ...)` (torch families) or the framework-equivalent strict exporter. The `strict=True` flag is non-negotiable — permissive mode silently drops unsupported ops and produces a model that loads but mis-evaluates.
2. **On export failure due to unsupported ops** — catch the framework's typed unsupported-op exception (torch: `torch.onnx.errors.UnsupportedOperatorError`, tensorflow/onnx: equivalent), collect the op names into a sorted deduplicated list, and populate `_kml_model_versions.onnx_unsupported_ops` as a JSON array. Emit a `model_registry.onnx.unsupported_ops` WARN log line with `model_name`, `version`, `unsupported_ops`, and `tenant_id`. Registration MUST still proceed (the version row is written) so the serving layer can refuse cleanly with enumerated ops instead of crashing on a partially-exported artifact.
3. **On export success** — populate `_kml_model_versions.onnx_opset_imports` from the exported `onnx.ModelProto.opset_import` field: a JSON object `{domain: version}` where `domain` is `""` for the default ai.onnx domain AND any custom-op domains declared by the model (e.g. `"com.microsoft"`). Leave `onnx_unsupported_ops = NULL`.
4. **ort-extensions detection** — if ANY domain other than the default `""` appears in `opset_imports` (i.e. a custom-op domain is encountered), the registry MUST resolve the required `ort-extensions`-family package names (e.g. `"onnxruntime_extensions"` for the `com.microsoft` domain) and populate `_kml_model_versions.ort_extensions` as a JSON array of package names. When the default domain is the only domain present, `ort_extensions` remains `NULL`.

#### 5.6.2 RegisterResult `onnx_status` Value Semantics

The canonical `RegisterResult.onnx_status: Optional[Literal["clean", "custom_ops", "legacy_pickle_only"]]` field is declared in §7.1 (the canonical dataclass). This subsection specifies the value semantics the probe MUST produce when populating it. Consumers (e.g. `ml-serving §2.5.1`, `ml-engines-v2 §6`) read the probe's persisted columns from `_kml_model_versions` (§5A.2) rather than `RegisterResult.onnx_status` directly — see `§5.6.3` cross-references. The `artifact_uris` dict-to-DDL aggregation under the single-format-per-row invariant is specified in `§7.1.2`.

Value semantics populated by the probe:

- `"clean"` — `onnx_unsupported_ops` is NULL AND `ort_extensions` is NULL. No custom ops, no extension packages required. Serving loads directly via vanilla `onnxruntime`.
- `"custom_ops"` — `onnx_unsupported_ops` is NULL AND `ort_extensions` is non-empty. Model exported successfully BUT requires one or more ort-extensions packages to run. Serving loads via `onnxruntime` with the extensions attached.
- `"legacy_pickle_only"` — `onnx_unsupported_ops` is non-empty. ONNX export failed on unsupported ops; the registered artifact itself is whatever format the caller supplied (pickle / torch / torchscript), and the `onnx_unsupported_ops` column serves as the signal that serving must use a fallback format (per `ml-serving §2.5`). In this path, `RegisterResult.artifact_uris["pickle"]` (or `"torch"` / `"torchscript"`) is populated; `artifact_uris["onnx"]` is absent.
- `None` — `format != "onnx"` was passed to `register_model(...)`. The ONNX probe did not run, no probe-columns were populated, and no ONNX-related inference can be made from the registered version.

#### 5.6.3 Cross-References

- `ml-serving-draft.md §2.5.1` — consumer. The load-time resolver reads `onnx_opset_imports`, `ort_extensions`, and `onnx_unsupported_ops` from `_kml_model_versions` and raises `OnnxOpsetMismatchError` / `OnnxExtensionNotInstalledError` / `OnnxExportUnsupportedOpsError` before the first request touches the wire.
- `ml-serving-draft.md §2.5.3` — `allow_pickle` fallback gate is the disposition when `onnx_status="legacy_pickle_only"` is persisted here.

---

## 5A. Schema DDL (Registry Tables)

Resolves Round-3 HIGH B14: DDL blocks for the four registry tables the spec references (`_kml_model_versions`, `_kml_model_aliases`, `_kml_model_audit`, `_kml_cas_blobs`) but did not define. All four carry `tenant_id` per `rules/tenant-isolation.md` MUST Rule 5 and — where applicable — `actor_id` per `rules/event-payload-classification.md`.

### 5A.1 Identifier Discipline

All dynamic table names written by DDL-emitting code MUST route through `kailash.db.dialect.quote_identifier()` per `rules/dataflow-identifier-safety.md` MUST Rule 1. The `_kml_` table prefix (leading underscore marks these as internal tables users should not query directly) MUST be validated in the caller's `__init__` against the regex `^[a-zA-Z_][a-zA-Z0-9_]*$` per `rules/dataflow-identifier-safety.md` MUST Rule 2. Every identifier interpolated at runtime (table-name, index-name, per-tenant sub-prefix) MUST stay within the Postgres 63-char limit (Decision 2 approved); total prefix+table-name length is enforced in the helper.

### 5A.2 Postgres DDL

```sql
-- _kml_model_versions
CREATE TABLE _kml_model_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id VARCHAR(255) NOT NULL,
  name VARCHAR(255) NOT NULL,
  version INTEGER NOT NULL,
  format VARCHAR(16) NOT NULL,  -- 'onnx' | 'torch' | 'sklearn' | 'gguf'
  artifact_uri TEXT NOT NULL,
  artifact_sha256 VARCHAR(72) NOT NULL,
  signature_json JSONB NOT NULL,
  lineage_run_id UUID NOT NULL,
  lineage_dataset_hash VARCHAR(72) NOT NULL,
  lineage_code_sha VARCHAR(72) NOT NULL,
  is_golden BOOLEAN NOT NULL DEFAULT FALSE,  -- CI release-gate flag per §7 registration rules
  -- ONNX export probe columns (§5.6). All three are nullable; populated only when format='onnx'.
  onnx_unsupported_ops JSONB,     -- list[str] of op names that failed torch.onnx.export(strict=True); NULL when format != 'onnx'
  onnx_opset_imports JSONB,        -- dict[domain: str, version: int] from ModelProto.opset_import; NULL when format != 'onnx'
  ort_extensions JSONB,            -- list[str] of required ort-extensions packages (e.g. ["onnxruntime_extensions"]); NULL when none required
  actor_id VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, name, version)
);
CREATE INDEX idx_model_versions_tenant_name ON _kml_model_versions(tenant_id, name);
CREATE INDEX idx_model_versions_golden ON _kml_model_versions(tenant_id, is_golden) WHERE is_golden = TRUE;

-- _kml_model_aliases
CREATE TABLE _kml_model_aliases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id VARCHAR(255) NOT NULL,
  model_name VARCHAR(255) NOT NULL,
  alias VARCHAR(64) NOT NULL,
  model_version_id UUID NOT NULL REFERENCES _kml_model_versions(id),
  actor_id VARCHAR(255) NOT NULL,
  set_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, model_name, alias)
);

-- _kml_model_audit
CREATE TABLE _kml_model_audit (
  id BIGSERIAL PRIMARY KEY,
  tenant_id VARCHAR(255) NOT NULL,
  model_name VARCHAR(255) NOT NULL,
  actor_id VARCHAR(255) NOT NULL,
  action VARCHAR(32) NOT NULL,  -- register | promote | demote | delete | set_alias | clear_alias
  prev_version INTEGER,
  new_version INTEGER,
  prev_alias VARCHAR(64),
  new_alias VARCHAR(64),
  reason TEXT,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_model_audit_tenant_time ON _kml_model_audit(tenant_id, occurred_at DESC);

-- _kml_cas_blobs
CREATE TABLE _kml_cas_blobs (
  sha256 VARCHAR(72) PRIMARY KEY,
  tenant_id VARCHAR(255) NOT NULL,
  size_bytes BIGINT NOT NULL,
  mime_type VARCHAR(255),
  storage_uri TEXT NOT NULL,
  encryption_kind VARCHAR(32) NOT NULL DEFAULT 'aes-256-gcm',
  ref_count INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_accessed_at TIMESTAMPTZ
);
```

### 5A.3 SQLite-Compatible Variant

SQLite does not support `UUID`, `JSONB`, `TIMESTAMPTZ`, `BIGSERIAL`, `BIGINT`, or `BOOLEAN` as distinct types. The SQLite subset MUST substitute:

- `UUID` → `TEXT` (canonical 36-char hyphenated string; caller generates via `uuid.uuid4()`)
- `JSONB` → `TEXT` (JSON-serialized string; caller `json.dumps()` / `json.loads()`)
- `TIMESTAMPTZ` → `TEXT` (ISO-8601 UTC string, e.g. `2026-04-21T12:34:56.789Z`; caller normalizes to UTC before write)
- `BIGSERIAL` → `INTEGER PRIMARY KEY AUTOINCREMENT`
- `BIGINT` → `INTEGER`
- `BOOLEAN` → `INTEGER` (0/1; caller normalizes at read/write)
- `DEFAULT gen_random_uuid()` → omitted; caller supplies UUID at insert
- `DEFAULT NOW()` → omitted; caller supplies ISO-8601 UTC string at insert
- `DEFAULT FALSE` → `DEFAULT 0`
- `REFERENCES ... (id)` → kept verbatim (SQLite supports FK syntax; enforcement requires `PRAGMA foreign_keys = ON`)
- Partial indexes (`WHERE is_golden = TRUE`) — SQLite supports them verbatim since 3.8.0; when the storage type is `INTEGER`, the predicate MUST be rewritten to `WHERE is_golden = 1`

### 5A.4 Tier-2 Schema-Migration Tests

- `test__kml_model_versions_schema_migration.py` — applies §5A.2 + §5A.3 DDL to a fresh Postgres (via `ConnectionManager`) AND a fresh SQLite (`:memory:`); asserts `pragma_table_info` / `information_schema.columns` match the declared shape (including the three ONNX-probe columns from §5.6); asserts the `UNIQUE(tenant_id, name, version)` constraint rejects a duplicate row on both backends; asserts the partial index `idx_model_versions_golden` exists (Postgres) AND is rewritten to `WHERE is_golden = 1` on SQLite.
- `test__kml_model_aliases_schema_migration.py` — same contract; additionally asserts the `UNIQUE(tenant_id, model_name, alias)` constraint and the FK reference to `_kml_model_versions(id)` on both backends.
- `test__kml_model_audit_schema_migration.py` — same contract; additionally asserts the `action` vocab round-trips `register | promote | demote | delete | set_alias | clear_alias`.
- `test__kml_cas_blobs_schema_migration.py` — same contract; additionally asserts `ref_count` default is `1` and `encryption_kind` default is `'aes-256-gcm'` on both backends.
- `test_model_registry_onnx_probe_wiring.py` — Tier-2 wiring test for the §5.6 ONNX-export probe. Builds a registry-backed `_kml_model_versions` row via `register_model(format="onnx")` against a torch model that uses a non-exportable op (e.g. `FlashAttentionForward`); asserts `onnx_unsupported_ops` is a non-empty JSON array naming the op; asserts a WARN line `model_registry.onnx.unsupported_ops` was emitted. Companion case: a torch model that IS exportable asserts `onnx_unsupported_ops IS NULL` AND `onnx_opset_imports` is a non-empty JSON object matching `ModelProto.opset_import`. Companion case for `ort_extensions`: a model declaring a `com.microsoft` custom-op domain populates `ort_extensions` with the required package name.

Each test MUST use `quote_identifier()` when referencing the table name by string for validation queries, closing the `rules/dataflow-identifier-safety.md` Rule 5 loop even for hardcoded test fixtures.

---

## 6. Lineage

### 6.1 Every Version MUST Persist Lineage

Every version row MUST persist:

- `lineage_run_id` — foreign-key-like reference to a `_kml_runs` row from `ml-tracking.md`. MUST NOT be null.
- `lineage_dataset_hash` — SHA-256 of the training dataset (computed from the polars DataFrame's canonical serialization, or from the feature-store snapshot hash if trained from a `FeatureStore`).
- `lineage_code_sha` — the git SHA of the repo at training time, or `"no-git"` if not in a git checkout (single-user dev flow). If a git repo exists and the working tree is dirty, `lineage_code_sha` is `"<sha>-dirty"` — registration emits a WARN.
- `lineage_parent_version` — optional `(tenant_id, name, version)` pointing at the fine-tune parent (for transfer-learning lineage).

### 6.2 Registration Without Lineage Is BLOCKED

`register_model` without an explicit `lineage` kwarg AND without an attached `training_result` capable of resolving the three fields above MUST raise `LineageRequiredError`.

The error message MUST point to the `km.track()` context manager (from `ml-tracking.md`) as the canonical source of `run_id`:

```
LineageRequiredError: register_model requires lineage.run_id — either
  pass lineage=Lineage(run_id=..., dataset_hash=..., code_sha=...)
  or attach a TrainingResult produced inside a `with km.track(): ...` block.
```

### 6.3 Cross-Tenant Lineage MUST NOT Resolve

A lineage pointing at `(tenant_id="bob", name="fraud", version=3)` registered from under `tenant_id="acme"` MUST raise `CrossTenantLineageError`. Cross-tenant fine-tuning requires explicit administrative export/import, not silent cross-scope resolution.

---

## 7. Registration Operations

### 7.1 Full Surface

```python
async def register_model(
    self,
    *,
    tenant_id: str,
    actor_id: str,
    name: str,
    training_result: TrainingResult | None = None,  # canonical lineage source
    lineage: Lineage | None = None,                 # explicit alternative
    signature: ModelSignature | None = None,        # inferred from TrainingResult if None
    format: Literal["onnx", "torchscript", "gguf", "pickle"] = "onnx",
    artifact_bytes: bytes | None = None,            # required if training_result is None
    metadata: dict[str, Any] | None = None,
    framework: str | None = None,                   # "sklearn" | "xgboost" | "lightgbm" | "torch" | "lightning"
    framework_version: str | None = None,
    python_version: str | None = None,
    platform: str | None = None,
    is_golden: bool = False,                        # release-CI-only; see §7.5
) -> RegisterResult:
    ...
```

`RegisterResult` is a named dataclass per `ml-engines.md` §2.1 MUST 4. This is the **canonical return shape** of `km.register` / `ModelRegistry.register_model`; every downstream consumer (`ml-engines-v2 §16.3` Tier-2 test, `ml-readme-quickstart-body §2`, `ml-serving §2.5.1` ONNX probe reader) MUST consume these field names — any deviation is a cross-spec-drift HIGH per `rules/specs-authority.md` Rule 5b.

```python
@dataclass(frozen=True, slots=True)
class RegisterResult:
    """Canonical return shape of `km.register` / `ModelRegistry.register_model`."""
    tenant_id: str
    model_name: str
    version: int
    actor_id: str
    registered_at: datetime
    artifact_uris: dict[str, str]   # {format: uri} — plural dict; keys e.g. "onnx", "torch", "pickle".
                                    # v1.0.0 invariant: single-format-per-row (len == 1); see §7.1.2.
                                    # Multi-format dicts (len > 1) are reserved for v1.1+ when DDL §5A.2
                                    # adopts either composite UNIQUE (tenant_id, name, version, format) or
                                    # JSONB consolidation. Current DDL UNIQUE (tenant_id, name, version)
                                    # constrains v1.0.0 to single-format rows; aggregate across formats at
                                    # query time via: `artifact_uris = dict(format ↔ artifact_uri for all
                                    # rows matching (tenant_id, name, version))`.
    signature_sha256: str            # content hash of the signature spec
    lineage_run_id: str              # cross-ref to tracker run
    lineage_dataset_hash: str        # sha256:<64hex> per dataflow-ml-integration §X
    lineage_code_sha: str            # git SHA at fit-time
    onnx_status: Optional[Literal["clean", "custom_ops", "legacy_pickle_only"]] = None
    is_golden: bool = False
```

**Field semantics:**

- `tenant_id` — tenant boundary per `rules/tenant-isolation.md` MUST Rule 5; never defaults, always explicit.
- `model_name` — the logical model name (not the row `id`). Matches `_kml_model_versions.name` column.
- `version` — the auto-bumped integer version number (monotonic within `(tenant_id, model_name)`).
- `actor_id` — the subject that performed the registration; propagates to `_kml_model_audit` per `rules/event-payload-classification.md`.
- `registered_at` — UTC timestamp of the transaction commit (matches `_kml_model_versions.created_at`).
- `artifact_uris` — `dict[format, uri]` where each key is a persisted artifact format (`"onnx"`, `"torch"`, `"torchscript"`, `"gguf"`, `"pickle"`, `"checkpoint"`, etc.) and each value is its CAS digest URI (`"cas://sha256:..."` or `"file://..."`). ONNX-first registration (Decision 8) MUST populate `artifact_uris["onnx"]` on successful export; see `ml-engines-v2 §6 MUST 4`. When ONNX export fails on unsupported ops and `allow_pickle_fallback=True`, `artifact_uris["pickle"]` is populated instead AND `onnx_status="legacy_pickle_only"` is set.
- `signature_sha256` — content hash (64 hex chars) of the canonical JSON-serialized `ModelSignature` spec. Enables fast equality checks across versions without re-parsing the signature.
- `lineage_run_id` — cross-reference to the tracker run that produced this version; matches `TrainingResult.tracker_run_id` per `ml-engines-v2 §4.1`.
- `lineage_dataset_hash` — `"sha256:<64hex>"` content hash of the training entity DataFrame per `dataflow-ml-integration §X`.
- `lineage_code_sha` — git SHA at fit-time; resolved from the tracker run's environment capture per `ml-tracking §6`.
- `onnx_status` — optional ONNX export-probe outcome per §5.6.2; `None` when `format != "onnx"`. Values: `"clean"` (no custom ops, no extensions required), `"custom_ops"` (exported but requires ort-extensions), `"legacy_pickle_only"` (ONNX export failed on unsupported ops, pickle fallback persisted).
- `is_golden` — release-CI flag per §7.5; `True` only when the registering path supplied `is_golden=True` AND validation gates passed.

#### 7.1.1 Back-Compat Shim For Legacy Singular `artifact_uri` (v1.x Only)

Legacy v0.x code read `result.artifact_uri` (singular string). The canonical v1.x shape is `artifact_uris` (plural dict). Per Decision 11 (legacy sunset), a read-only back-compat shim is retained through v1.x and REMOVED at v2.0:

```python
@dataclass(frozen=True, slots=True)
class RegisterResult:
    # ... canonical fields as above ...

    @property
    def artifact_uri(self) -> str:
        """DEPRECATED v1.x back-compat shim. Removed at v2.0.

        Returns artifact_uris["onnx"] (the default format per Decision 8 ONNX-first).
        Raises KeyError if ONNX was not persisted (use artifact_uris directly).
        """
        warnings.warn(
            "RegisterResult.artifact_uri (singular) is deprecated; use "
            "RegisterResult.artifact_uris[format] (plural dict). The singular "
            "accessor returns artifact_uris['onnx'] and is removed at v2.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.artifact_uris["onnx"]
```

**Sunset path (Decision 11):**

- **v1.x** — `artifact_uri` property emits `DeprecationWarning` on access; returns `artifact_uris["onnx"]`. `KeyError` if ONNX not persisted (e.g. pickle-only legacy path).
- **v2.0** — property REMOVED. `AttributeError: 'RegisterResult' object has no attribute 'artifact_uri'`. All downstream consumers MUST read `artifact_uris[format]`.

No field-level (non-property) `artifact_uri: str` is exposed — pickle round-trips of `RegisterResult` across v0.x boundaries are out of scope per Decision 11.

#### 7.1.2 Single-Format-Per-Row Invariant (v1.0.0)

`RegisterResult.artifact_uris: dict[str, str]` is a **dict-shaped return type** per Phase-F F3. The v1.0.0 DDL at §5A.2 persists **one row per (tenant_id, name, version)** with a single `format VARCHAR(16)` column and a single `artifact_uri TEXT` column, constrained by `UNIQUE (tenant_id, name, version)`. The dict shape on the Python side is therefore an **aggregated projection** of one or more rows matching `(tenant_id, name, version)` in the registry table:

```python
# Reader side — aggregate rows into the dict shape
rows = registry.list_versions(tenant_id=t, name=n, version=v)   # 1+ rows
artifact_uris = {row.format: row.artifact_uri for row in rows}
```

**v1.0.0 invariant:** `len(RegisterResult.artifact_uris) == 1`. `register_model(...)` takes a single `format=` kwarg per call; each call produces one row. Downstream consumers (`ml-engines-v2 §16.3` Tier-2 test, `ml-readme-quickstart-body §2`, `ml-serving §2.5.1`) MUST NOT assume multi-format dicts in v1.0.0 — the ONNX-first path writes one `format="onnx"` row; the pickle-fallback path writes one `format="pickle"` (or `"torch"` / `"torchscript"`) row; never both in one call.

**v1.1+ roadmap:** Multi-format support becomes possible when either:

- **Shape B (UNIQUE extension)** — DDL `UNIQUE` becomes `(tenant_id, name, version, format)` and a single `register_model(...)` call can optionally persist multiple format rows atomically; the Python dict then aggregates N formats per `(tenant_id, name, version)` — OR —
- **Shape C (JSONB consolidation)** — `artifact_uri TEXT + format VARCHAR(16)` is replaced by `artifact_uris JSONB` holding `{format: uri}` directly, eliminating the aggregation step.

Neither shape ships in v1.0.0 (invariant freeze; see Decision 11 legacy-sunset discipline). The v1.0.0 contract is: **Python returns a dict because the API is forward-compatible with v1.1 multi-format; the DDL constrains to single-format rows until v1.1 adopts Shape B or C.**

**Rationale for choosing Shape A (dict + single-row invariant) over directly shipping Shape B or C:** Shape A lets downstream consumers (`ml-serving §2.5.1`, `ml-engines-v2 §16.3`) adopt the dict-shaped Python contract today without a DDL migration, AND preserves back-compat with the legacy singular `artifact_uri` shim at §7.1.1. A v1.1 migration to Shape B or C is then a pure DDL addition (new UNIQUE or new JSONB column) that does NOT require re-shaping the Python return type — zero caller migration at v1.1.

### 7.2 Atomicity

A single `register_model` call is atomic:

1. Compute next version (§3.2).
2. Write artifact to CAS (§10) — failure here aborts without a row write.
3. Write `_kml_model_versions` row inside a transaction.
4. Write `_kml_model_audit` row in the same transaction.
5. Commit.

Failure at any step MUST leave NO row in `_kml_model_versions` (the transaction rollback ensures this). The CAS write IS idempotent — a half-written CAS artifact with no version row is orphan but recoverable via periodic GC on `_kml_cas_blobs` that are not referenced by any version after a grace period.

### 7.3 Idempotence By Dataset + Code Hash

An optional `idempotency_key` (default: `sha256(dataset_hash + code_sha + hyperparams)`) MAY be supplied. If a version with that key already exists for the `(tenant_id, name)`, `register_model` returns the existing `RegisterResult` instead of creating a new version. Emits a DEBUG log noting dedup.

**Why:** Reproducible training on unchanged inputs should not inflate the version table. MLflow + W&B both ship this; kailash-ml parity requires it.

### 7.4 Top-Level `km.register` Convenience Wrapper

In addition to `ModelRegistry.register_model(...)` (§7.1), `kailash-ml` exports a package-level `km.register(...)` wrapper that dispatches to the tenant-scoped cached default engine's registry (per `ml-engines-v2.md §15.4`). This is the verb-first entry point used in the canonical Quick Start (`ml-engines-v2.md §16`).

#### 7.4.1 Signature

```python
async def register(
    training_result: TrainingResult,
    *,
    name: str,
    alias: str | None = None,                         # e.g. "@production"; None = no alias set
    tenant_id: str | None = None,
    actor_id: str | None = None,                      # required if tenant_id present; else "km.register"
    format: Literal["onnx", "torchscript", "gguf", "pickle"] = "onnx",
    stage: Literal["staging", "shadow", "production", "archived"] = "staging",
    metadata: dict | None = None,
) -> RegisterResult: ...
```

#### 7.4.2 Behaviour (MUST)

1. Validate `training_result` is fully populated — all eight required fields from `ml-engines-v2.md §4.1` + `§4.2 MUST 1`. `IncompleteTrainingResultError` raises if `device`, `tracker_run_id`, `artifact_uris`, or `lightning_trainer_config` is None. (The back-compat mirrors `device_used` / `accelerator` / `precision` auto-populate from `device` and do NOT require their own None-check.)
2. Resolve cached engine via `kailash_ml._get_default_engine(tenant_id)` (from `ml-engines-v2.md §15.2 MUST 1`).
3. Delegate to `engine._model_registry.register_model(...)` with the full signature:
   - `tenant_id=tenant_id or "_single"` per `ml-tracking.md §7.2` (canonical cross-spec sentinel).
   - `actor_id=actor_id` — raises `ActorRequiredError` if `tenant_id is not None` AND `actor_id is None` (per §6.2 `register_model without lineage is BLOCKED`).
   - `name=name`, `training_result=training_result`, `format=format`, `metadata=metadata`.
   - `lineage` auto-populated from `training_result.lineage` (per §6.1 `every version MUST persist lineage`). If `training_result.lineage` is None, raises `LineageRequiredError` — no silent defaulting.
4. If `alias is not None`, chain `engine._model_registry.set_alias(name=name, version=result.version, alias=alias, actor_id=actor_id or "km.register", reason=f"km.register alias={alias}")` in the same atomic transaction window as the register.
5. Return the `RegisterResult` unchanged.

#### 7.4.3 Usage

```python
import kailash_ml as km

# DO — one-line registration after training
async with km.track("demo") as run:
    result = await km.train(df, target="y")
    registered = await km.register(result, name="demo")
# registered.artifact_uris["onnx"] -> "cas://sha256:abc123..." (ONNX-first per Decision 8)
# registered.version -> 1 (first version for this model_name+tenant)

# DO — register + set alias atomically
registered = await km.register(
    result, name="fraud", alias="@production",
    tenant_id="acme", actor_id="agent-42",
)

# DO — explicit format (onnx is the default; this shows the opt-in to pickle)
registered = await km.register(result, name="fraud", format="pickle")
# ↑ triggers the pickle-opt-in warning per §11
```

#### 7.4.4 MUST: No New Engine Method

`km.register` is a package-level function. It MUST NOT be added as a ninth method on `MLEngine` — the eight-method surface at `ml-engines-v2.md §2.1 MUST 5` already includes `engine.register(training_result, name=..., ...)` as one of the eight. The `km.register` wrapper delegates INTO that existing engine method via the cached default engine.

```python
# DO — wrapper dispatches to the EXISTING engine.register method
async def register(training_result, *, name, alias=None, tenant_id=None, actor_id=None, **kw):
    engine = _get_default_engine(tenant_id)
    result = await engine.register(
        training_result, name=name, actor_id=actor_id or "km.register", **kw,
    )
    if alias is not None:
        await engine._model_registry.set_alias(
            name=name, version=result.version, alias=alias,
            actor_id=actor_id or "km.register", reason=f"km.register alias={alias}",
        )
    return result

# DO NOT — introduce a `km_register` method on Engine in addition to `engine.register`
class Engine:
    async def km_register(self, training_result, *, name, alias=None): ...  # BLOCKED
```

**Why:** The eight-method surface is the spec-level invariant from `ml-engines-v2.md §2.1 MUST 5`; `engine.register(...)` IS one of the eight. A ninth `km_register` method would double-book the verb. `km.register` the package function is the structural mechanism for adding newbie-UX discovery without breaking the engine contract.

---

### 7.5 Golden-Reference Registrations (`is_golden`)

Every kailash-ml release ships a "golden" reference run registered at package-import time with `is_golden=True`. `km.reproduce(golden_reference_id, verify=True)` MUST pass before the release is promoted per `ml-engines-v2.md §12.1 MUST 3`. This section is the registry-side contract for the `is_golden` flag.

#### 7.5.1 Schema

`_kml_model_versions` persists the flag as a NOT-NULL boolean column defaulting to FALSE:

```sql
ALTER TABLE _kml_model_versions
  ADD COLUMN is_golden BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX _kml_model_versions_golden_idx
  ON _kml_model_versions (tenant_id, name, is_golden)
  WHERE is_golden = TRUE;
```

A partial index on `is_golden = TRUE` keeps the index small (golden rows are rare) while supporting "list all golden references for tenant X" in O(1).

#### 7.5.2 `register_model(..., is_golden=True)` Semantics

`is_golden=True` is a write-once flag: once set to `TRUE` for a given `(tenant_id, name, version)` row, it MUST NOT be flipped to `FALSE` by any subsequent mutation. Attempting to update a row where `is_golden=TRUE` raises `ImmutableGoldenReferenceError(ModelRegistryError)` with:

```
ImmutableGoldenReferenceError:
  row (tenant_id={tenant}, name={name}, version={version}) has is_golden=TRUE
  and is immutable. Register a new version as the updated golden reference
  instead of mutating this row.
```

Updates to OTHER columns on a golden row (e.g. metadata key/value additions, alias pointer changes) are also BLOCKED — the row is fully immutable from the moment `is_golden=TRUE` is written. The ONLY legal mutation path is to register a NEW version and mark the new version as golden.

```python
# DO — CI registers a golden on verified reproduction
await registry.register_model(
    tenant_id="_single",
    actor_id="release-ci@2026.04.25",
    name="kailash-ml-golden",
    training_result=golden_result,
    is_golden=True,
    metadata={"release": "1.0.0", "commit_sha": "abc123..."},
)

# DO NOT — attempt to mutate an existing golden row
await registry.update_metadata(
    tenant_id="_single", name="kailash-ml-golden", version=1,
    patch={"new_key": "new_value"},
)
# → ImmutableGoldenReferenceError
```

#### 7.5.3 `list_golden_references(tenant_id, *, limit=100)`

The registry MUST expose a listing API for golden-reference queries:

```python
async def list_golden_references(
    self,
    tenant_id: str,
    *,
    name: str | None = None,        # None = all names
    limit: int = 100,
) -> "polars.DataFrame":
    """Return every is_golden=TRUE row for the tenant.

    Columns: (tenant_id, name, version, registered_at, actor_id,
              lineage_run_id, lineage_code_sha, artifact_uri, metadata)
    Ordered: registered_at DESC.
    """
```

#### 7.5.4 `km.reproduce` Resolves `is_golden` Lineage

The `km.reproduce(run_id)` entry from `ml-engines-v2.md §12` MUST resolve `is_golden` status on the target run via a registry query:

```python
# kailash_ml/reproduce.py (pseudo-code)
async def reproduce(run_id, *, verify=True, ...):
    row = await registry.get_model_version_by_run_id(run_id)
    if row.is_golden:
        # Tighter numerical tolerance for golden-reference verification
        verify_rtol = min(verify_rtol, 1e-5)
        verify_atol = min(verify_atol, 1e-7)
    ...
```

The tightened tolerance for golden-reference reproduction is a release-gate invariant — if tolerances are loosened in a later spec amendment, every golden's CI gate is loosened at the same time.

#### 7.5.5 Audit Row Requirement

Writing `is_golden=TRUE` on a `_kml_model_versions` row MUST write an accompanying `_kml_model_audit` row with:

- `operation = "register"` (unchanged)
- `new_state` includes `{"is_golden": true, "release": <metadata.release>}`
- `reason = "golden_reference_registration"`

A golden registration without the matching audit row is BLOCKED at the transaction layer (§7.2 atomicity).

**Why:** Golden references are the structural defense against silent numerical drift across upstream library bumps (torch, lightning, lightgbm). An immutable, audited, queryable golden row is the only structural answer to "did version 1.0.0 drift against its pinned golden reference when we upgraded torch?"

---

## 8. Alias Operations — `promote`, `demote`, `set_alias`, `clear_alias`

### 8.1 `promote_model`

```python
async def promote_model(
    self,
    *,
    tenant_id: str,
    actor_id: str,
    name: str,
    version: int,
    alias: str = "@production",
    reason: str,                 # required for audit clarity
    force: bool = False,         # bypass soft gate on existing alias
) -> PromoteResult:
    ...
```

Semantics:

1. Verify the `(tenant_id, name, version)` row exists and is not archived.
2. If the alias currently points at a different version AND `force=False`, raise `AliasOccupiedError` pointing at the current occupant. Forces the caller to acknowledge the replacement.
3. Replace the alias pointer.
4. Write audit row with `operation="promote"`, `prev_state={"version": old_version}`, `new_state={"version": new_version}`, `reason`.
5. Emit an `on_model_promoted` event to the ambient tracker contextvar (`ml-tracking.md` §"Engine events") so the dashboard + drift monitor can react.

### 8.2 `demote_model`

```python
async def demote_model(
    self,
    *,
    tenant_id: str,
    actor_id: str,
    name: str,
    alias: str = "@production",
    reason: str,
) -> DemoteResult:
    ...
```

Clears the alias (soft delete per §4.1 MUST 5) AND automatically sets `@archived` on the previously-pointed version if no other alias still points at it. Writes audit row.

### 8.3 `set_alias` / `clear_alias`

Generic surfaces for non-promotion alias management. Same audit + event emission contract as promote/demote.

### 8.4 Every Mutation Emits A Log And An Event

Per `rules/observability.md` Mandatory Log Points §1-3:

```python
logger.info("registry.promote.start",
    extra={"tenant_id": tenant_id, "actor_id": actor_id, "model": name,
           "version": version, "alias": alias, "request_id": request_id})
# ... operation ...
logger.info("registry.promote.ok",
    extra={"tenant_id": tenant_id, "actor_id": actor_id, "model": name,
           "version": version, "alias": alias, "duration_ms": dt,
           "mode": "real", "request_id": request_id})
```

On error, `registry.promote.error` with `exc_type`, `exc_msg_fingerprint`, `duration_ms`.

---

## 9. Query Operations

### 9.1 `get_model`

```python
async def get_model(
    self,
    *,
    tenant_id: str,
    name: str,
    version: int | None = None,   # exact version OR
    alias: str | None = None,      # alias resolution OR
    # both None = latest version
) -> ModelHandle:
    ...
```

`ModelHandle` carries the signature, lineage, and a lazy artifact loader (loading bytes is expensive; the handle defers until `.load()` is called).

Resolution order:

1. If `version` given, fetch directly.
2. Else if `alias` given, resolve `(tenant_id, name, alias)` to a version, then fetch.
3. Else fetch the highest version for `(tenant_id, name)`.
4. If nothing resolves, raise `ModelNotFoundError` with the tenant + name + attempted resolution mode.

### 9.2 `list_models`

```python
async def list_models(
    self,
    *,
    tenant_id: str,
    name: str | None = None,     # filter by name
    alias: str | None = None,    # only versions currently holding this alias
    limit: int = 100,
    offset: int = 0,
) -> pl.DataFrame:
    ...
```

Returns a polars DataFrame per `ml-engines.md` §4 (polars-native). Columns: `name`, `version`, `registered_at`, `actor_id`, `format`, `aliases` (list of currently-held alias strings), `lineage_run_id`, `signature_summary`.

### 9.3 `search_models`

```python
async def search_models(
    self,
    *,
    tenant_id: str,
    filter: str | None = None,        # SQL-fragment, validated identifier-safe
    order_by: list[str] | None = None,
    limit: int = 100,
) -> pl.DataFrame:
    ...
```

`filter` supports a restricted DSL (NOT raw SQL) — similar to MLflow's `filter_string`: `"name='fraud' AND version > 3"`, `"tags.team='ops'"`. Per `rules/dataflow-identifier-safety.md` the parser MUST validate every identifier via the dialect helper; raw SQL interpolation is BLOCKED.

### 9.4 `diff_versions`

```python
async def diff_versions(
    self,
    *,
    tenant_id: str,
    name: str,
    version_a: int,
    version_b: int,
) -> ModelDiff:
    ...
```

Returns a structured diff: `signature_diff` (added/removed/changed columns), `lineage_diff` (run_id, dataset_hash, code_sha deltas), `metric_diff` (pulled from the linked runs via `ExperimentTracker.compare_runs`), `format_diff`.

**Why:** "Which version changed the signature" and "why does v8 predict differently than v7" are the two most common post-incident questions; answering them cheaply is table-stakes competitive with MLflow's compare UI.

---

## 10. Artifact Store — Content-Addressed With Per-Tenant Quotas

### 10.1 Content Addressing

Every registered artifact is stored under `cas://sha256:<hex>` where the digest is computed over the canonical serialization of the format (ONNX proto bytes, TorchScript archive bytes, GGUF bytes, pickle bytes). The `_kml_model_versions.artifact_uri` column stores this URI; the actual bytes live in the `ArtifactStore` backend.

**Why:** Content addressing gives free dedup across versions that share bytes (a hyperparameter change that produces a bit-identical serialization reuses the same CAS blob). It also enables cryptographic integrity verification — a tampered blob produces a different digest.

### 10.2 Backends

The `ArtifactStore` is a pluggable interface:

- `LocalFileArtifactStore(root_dir)` — default for single-user dev.
- `S3ArtifactStore(bucket, prefix, client)` — production cloud.
- `GCSArtifactStore(bucket, prefix)` — GCP variant.
- `AzureBlobArtifactStore(container, prefix)` — Azure variant.

Every backend implements `put(digest, bytes) -> None`, `get(digest) -> bytes`, `exists(digest) -> bool`, `delete(digest) -> None`, `list_tenant(tenant_id) -> Iterator[digest]`.

Store-URL resolution for the registry's own metadata backing store (the `_kml_model_versions` / `_kml_model_aliases` / `_kml_model_audit` / `_kml_cas_blobs` tables owned by the `ModelRegistry` that `MLEngine` constructs — see §14 cross-ref to `ml-engines.md §2` and `ml-engines-v2.md §15.4` default-engine cache) routes through `kailash_ml._env.resolve_store_url(explicit=...)` per `ml-engines-v2.md §2.1 MUST 1b` (single shared helper; hand-rolled `os.environ.get(...)` is BLOCKED per `rules/security.md` § Multi-Site Kwarg Plumbing). `ArtifactStore` backend URIs (`LocalFileArtifactStore(root_dir)`, `S3ArtifactStore(bucket, prefix, client)`, etc.) are orthogonal — they address the CAS blob byte layer, not the registry metadata SQL layer — but are subject to the same single-helper discipline when a store-URL-style kwarg is plumbed.

### 10.3 Encryption At Rest

The `ArtifactStore` MUST support optional encryption-at-rest via AES-256-GCM with a per-tenant key provided at construction. When the key is present, bytes are encrypted on `put` and decrypted on `get`. The digest is computed on PLAINTEXT so dedup still works across tenants that happen to hold identical artifacts.

Note: cross-tenant dedup means a tenant B's encrypted byte read from a shared S3 bucket needs tenant B's key. The CAS blob key cannot leak tenant A's secret. `rules/zero-tolerance.md` Rule 2: a `ArtifactStore(encryption_key=k)` that does nothing with `k` is BLOCKED (fake encryption).

### 10.4 Per-Tenant Size Quotas

The registry tracks `_kml_tenant_quotas(tenant_id, max_bytes_total, current_bytes_total, max_models, current_models, retention_days)`. Exceeding a quota on `register_model` MUST raise `TenantQuotaExceededError`. Operators override via an admin API.

### 10.5 Retention Per-Alias

A retention rule is `(tenant_id, name, alias, keep_n_versions, max_age_days)`. A periodic compaction job deletes version rows + CAS blobs that are:

- not currently held by any alias, AND
- older than `max_age_days` for any alias retention rule pointing at `(tenant_id, name)`, AND
- not within the last `keep_n_versions`.

Default: `@production` keeps last 10 versions forever; other aliases keep last 5 versions for 365 days; versions held by no alias for 90 days are eligible for compaction.

**Why:** `rules/tenant-isolation.md` MUST Rule 5 requires audit rows to persist tenant_id; here the retention rule requires tenant_id on every compaction decision to prevent cross-tenant deletion bugs.

---

## 11. Export Formats

### 11.1 Format Registry

Formats are registered through a small plugin system:

```python
kailash_ml.registry.formats.register(
    name="onnx",
    serialize=onnx_bridge.export,
    deserialize=onnx_bridge.load,
    default=True,
)
```

### 11.2 Format Priority

1. **ONNX (default)** — ml-engines.md §6.1 MUST 1. Cross-runtime serving (Python, Rust, browser, edge).
2. **TorchScript** — for PyTorch-native callers that need autograd or custom ops ONNX can't express.
3. **GGUF** — reserved for kailash-align fine-tuned LLMs (quantized weights). Cross-registry reference to `alignment-training.md`.
4. **Pickle (discouraged)** — opt-in, emits a WARN at registration AND at load time citing cross-version / cross-platform risks per `rules/zero-tolerance.md` Rule 2 extended example "Pickle bombs load-time".

Registration with a format not in the registry raises `UnsupportedFormatError`.

### 11.3 Cross-Format Round-Trip

For every registered format, a Tier 2 integration test per `ml-engines.md` §6.1 MUST 3 verifies native-vs-serialized prediction parity (`max_abs_diff <= 1e-4`). Formats without a round-trip test are BLOCKED from being set as default.

### 11.4 Format Metadata Per Version

Every version row persists `format`, `framework`, `framework_version`, `python_version`, `platform`. On `ModelHandle.load()`, the loader MUST verify the current environment is compatible with the version's metadata:

- `framework_version` major mismatch → load succeeds with a WARN (sklearn 1.3 → 1.4 is usually fine).
- `python_version` major mismatch on a pickle format → raise `IncompatibleArtifactError`. Python 3.11-pickle loading under 3.12 is a known hazard.
- `platform` mismatch (linux-x86_64 → darwin-arm64) on a TorchScript-with-custom-ops → WARN; on ONNX → silent (ONNX is portable by design).

---

## 12. Industry Parity

### 12.1 Feature Matrix vs Competitors

| Capability                        |  kailash-ml (v2.0)   |   MLflow Model Registry   |    W&B Artifacts    |           SageMaker MR            | Kubeflow/KServe |
| --------------------------------- | :------------------: | :-----------------------: | :-----------------: | :-------------------------------: | :-------------: |
| Tenant-scoped registry            |   **Y** (required)   |   Y\* (experiment-tag)    |     Y (project)     |              Y (IAM)              |  Y (namespace)  |
| Actor+audit on mutation           |   **Y** (required)   |        Y (user_id)        |    Y (run.user)     |              Y (IAM)              |     partial     |
| Aliases (multi-alias per version) |        **Y**         | Y (stages + aliases 2.0+) |     Y (aliases)     | Y (ModelPackageGroupName + alias) |   Y (canary)    |
| Integer-monotonic versions        |          Y           |             Y             | Y (version + alias) |                 Y                 |        Y        |
| Mandatory signature               |   **Y** (required)   |       Y (optional)        |    Y (optional)     |           Y (optional)            |     partial     |
| Mandatory lineage                 |   **Y** (required)   |       Y (optional)        |    Y (optional)     |           Y (optional)            |        Y        |
| Content-addressed artifacts       |        **Y**         |          partial          |  Y (content-addr)   |              partial              |     partial     |
| Per-tenant quotas                 |        **Y**         |             N             |          Y          |                 Y                 |     partial     |
| Format dispatcher (ONNX/TS/GGUF)  | **Y** (ONNX default) |     Y (pyfunc/custom)     |     Y (generic)     |                 Y                 |        Y        |
| Polars-native return              |        **Y**         |        N (pandas)         |          N          |                 N                 |        N        |
| Cross-tenant lineage refused      |        **Y**         |   N (not tenant-scoped)   |          N          |                 N                 |        N        |
| Retention per-alias               |        **Y**         |          partial          |          Y          |           Y (lifecycle)           |        Y        |
| CAS encryption-at-rest per-tenant |        **Y**         |             N             |          N          |              Y (KMS)              |     Y (KMS)     |

### 12.2 Competitive Differentiators

kailash-ml claims these as v2.0 differentiators:

1. **Mandatory lineage** — every other registry treats lineage as optional; the cost is losing "which model used which data" forever. We make it required.
2. **Mandatory tenant + actor** — forces multi-tenant correctness up front rather than bolted on as per-org sugar.
3. **Polars-native listing** — `list_models` returns a DataFrame the caller can immediately `.filter()` / `.join()` against experiment tables.
4. **Cross-registry lineage refusal** — refuses silent cross-tenant fine-tune chaining.

### 12.3 Gaps We Know

- No Sigstore / model signing in v2.0 (round-1 LOW finding). Planned post-1.0.
- No gRPC / OTel tracing spans in the registry (round-1 LOW). Planned post-1.0.
- No rich UI for alias-promotion (dashboard is read-only per `MLDashboard` today). `ml-serving.md` §13 covers the canary deploy UX that eventually feeds back here.

---

## 13. Error Taxonomy

All errors inherit from `kailash_ml.errors.ModelRegistryError`, which inherits from the canonical root `kailash_ml.errors.MLError` per `ml-tracking §9.1` (CRIT-3 — canonical hierarchy authoritative). Cross-domain errors (`TenantRequiredError`, `ActorRequiredError`, `LineageRequiredError`, `AliasNotFoundError`) are re-exported from `kailash_ml.errors` where they live under `TrackingError`. Cross-cutting errors sitting at the `MLError` root (`MultiTenantOpError` per Decision 12) are ALSO re-exported from `kailash_ml.errors` so registry callers may write `except MultiTenantOpError` without importing the `kailash.ml.errors` module directly.

| Error                       | Raised When                                                                                                                                                                                                                                                                                                                                                                                                                     |          Retry safe?          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :---------------------------: |
| `ModelNotFoundError`        | `get_model` / `list_models` fails to resolve `(tenant_id, name[, version][, alias])`                                                                                                                                                                                                                                                                                                                                            |              No               |
| `AliasNotFoundError`        | Alias resolution fails (no pointer for that alias on that name)                                                                                                                                                                                                                                                                                                                                                                 |              No               |
| `AliasOccupiedError`        | `promote_model` without `force=True` when alias already occupied                                                                                                                                                                                                                                                                                                                                                                |              No               |
| `InvalidModelNameError`     | Name violates regex or uses reserved prefix                                                                                                                                                                                                                                                                                                                                                                                     |              No               |
| `LineageRequiredError`      | `register_model` without lineage AND without a training_result capable of resolving lineage                                                                                                                                                                                                                                                                                                                                     |              No               |
| `SignatureMismatchError`    | Registered version's signature cannot be inferred from training result AND was not explicitly supplied                                                                                                                                                                                                                                                                                                                          |              No               |
| `CrossTenantLineageError`   | Attempted fine-tune registration with parent lineage from another tenant                                                                                                                                                                                                                                                                                                                                                        |              No               |
| `TenantRequiredError`       | Any op missing `tenant_id` when multi-tenant mode is active                                                                                                                                                                                                                                                                                                                                                                     |              No               |
| `ActorRequiredError`        | Mutation without `actor_id`                                                                                                                                                                                                                                                                                                                                                                                                     |              No               |
| `TenantQuotaExceededError`  | Registration would exceed per-tenant size/count quota                                                                                                                                                                                                                                                                                                                                                                           | No (requires operator action) |
| `IncompatibleArtifactError` | `ModelHandle.load` detects fatal environment mismatch (pickle across Python majors, etc.)                                                                                                                                                                                                                                                                                                                                       |  Maybe (switch environment)   |
| `UnsupportedFormatError`    | Registration with a `format=` not in the registry                                                                                                                                                                                                                                                                                                                                                                               |              No               |
| `IdentifierError`           | Per `rules/dataflow-identifier-safety.md` — DDL identifier validation failure (model name passes name regex but table identifier fails dialect check)                                                                                                                                                                                                                                                                           |              No               |
| `MultiTenantOpError`        | (Decision 12, cross-cutting, post-1.0) `export_tenant_snapshot()` / `import_tenant_snapshot()` called without PACT D/T/R clearance for cross-tenant admin export/import. Root inherits `MLError`, NOT `ModelRegistryError`, so `except MLError` catches uniformly across registry + feature-store + serving + tracking. See `ml-tracking-draft.md §9.1.1` + `supporting-specs-draft/kailash-core-ml-integration-draft.md §3.3`. |              No               |

Each error MUST carry:

- A fingerprint (first 8 hex of SHA-256 over a stable tuple) to aid log correlation.
- A non-echoing message — raw user input (model name, tenant id, alias string) MUST be fingerprinted, not echoed, per `rules/dataflow-identifier-safety.md` MUST 2.
- An actionable "how to fix" sentence.

---

## 14. Test Contract

### 14.1 Tier 1 (Unit) — Per Op

Every registry op (`register_model`, `promote_model`, `demote_model`, `set_alias`, `clear_alias`, `get_model`, `list_models`, `search_models`, `diff_versions`) MUST have a Tier 1 test covering:

- Happy path.
- Missing `tenant_id` raises `TenantRequiredError`.
- Missing `actor_id` on mutations raises `ActorRequiredError`.
- Reserved name prefix raises `InvalidModelNameError`.
- Boundary inputs (empty name, max-length name, version=0).

### 14.2 Tier 2 (Integration) — Wiring Through MLEngine Facade

Per `rules/facade-manager-detection.md` Rule 1, the wiring test MUST import the registry through the MLEngine facade:

```python
@pytest.mark.integration
async def test_registry_wiring_register_promote_audit(test_suite):
    engine = km.Engine(store=test_suite.url, tenant_id="acme")
    # 1. Train and register inside a tracked run
    async with km.track(run_name="fraud-v1"):
        train_result = await engine.fit(family="sklearn", model_class=RandomForestClassifier)
    reg = await engine.register(train_result, name="fraud", actor_id="agent-42")
    assert reg.version == 1
    assert reg.lineage.run_id is not None

    # 2. Promote to @production
    prom = await engine.promote(name="fraud", version=1, alias="@production",
                                 actor_id="agent-42", reason="CI sign-off")

    # 3. Audit row exists and is tenant-scoped
    audit = await engine._conn.fetch(
        "SELECT * FROM _kml_model_audit WHERE tenant_id=$1 AND resource='model' ORDER BY occurred_at DESC LIMIT 2",
        "acme",
    )
    assert [r["operation"] for r in audit] == ["promote", "register"]
    assert all(r["actor_id"] == "agent-42" for r in audit)

    # 4. Cross-tenant query returns nothing
    cross = await engine._conn.fetch(
        "SELECT * FROM _kml_model_versions WHERE tenant_id=$1 AND name=$2",
        "bob", "fraud",
    )
    assert cross == []
```

The file MUST be named `test_model_registry_wiring.py` per `rules/facade-manager-detection.md` Rule 2.

### 14.3 Tier 2 — Cross-Run Promote / Demote / Rollback Sequence

```python
@pytest.mark.integration
async def test_registry_wiring_promote_demote_rollback(test_suite):
    engine = km.Engine(store=test_suite.url, tenant_id="acme")

    # Register v1, v2, v3
    v1 = await _train_and_register(engine, "fraud", actor_id="alice")
    v2 = await _train_and_register(engine, "fraud", actor_id="alice")
    v3 = await _train_and_register(engine, "fraud", actor_id="alice")

    # Promote v2 to @production
    await engine.promote(name="fraud", version=v2.version, alias="@production",
                          actor_id="alice", reason="canary sign-off")

    # Promote v3 over v2 (force)
    await engine.promote(name="fraud", version=v3.version, alias="@production",
                          actor_id="alice", reason="v3 beats v2", force=True)

    # Rollback: demote current @production, re-promote v2
    await engine.demote(name="fraud", alias="@production", actor_id="alice",
                         reason="v3 caused p99 regression")
    await engine.promote(name="fraud", version=v2.version, alias="@production",
                          actor_id="alice", reason="v3 rollback")

    # Audit: 5 ops (3 register + 2 promote + 1 demote + 1 promote = 7)
    audit = await engine._conn.fetch(
        "SELECT operation FROM _kml_model_audit WHERE tenant_id=$1 ORDER BY occurred_at",
        "acme",
    )
    assert [r["operation"] for r in audit] == [
        "register", "register", "register", "promote", "promote", "demote", "promote",
    ]

    # Current @production points at v2
    m = await engine.get_model(name="fraud", alias="@production")
    assert m.version == v2.version
```

### 14.4 Tier 2 — Multi-Tenant Isolation

Two tenants each register `"fraud"` and run `@production` promotions. Assert:

1. `tenant_id="acme"` listing never returns `tenant_id="bob"` rows.
2. Invalidating `acme`'s cache does not evict `bob`'s keys.
3. An audit-row query for `bob` never returns `acme`'s rows.
4. Artifact CAS blobs are dedup'd across tenants when bytes match (efficiency check).
5. Cross-tenant lineage explicitly raises `CrossTenantLineageError`.

### 14.5 Tier 2 — Format Round-Trips

Per `ml-engines.md` §6.1 MUST 3, one round-trip test per format (`sklearn → onnx`, `torch → onnx`, `lightning → torchscript`, etc.) verifying `max_abs_diff <= 1e-4`.

### 14.6 Regression Tests (Permanent)

- `tests/regression/test_issue_T5_two_registries_collapsed.py` — asserts `MLEngine._kml_engine_versions` attribute no longer exists; `engine.register(...)` does NOT raise `NotImplementedError`; `_kml_engine_*` SQL tables have been migrated away.
- `tests/regression/test_issue_mlops_CRIT3_actor_required.py` — asserts every mutation without `actor_id` raises `ActorRequiredError`.
- `tests/regression/test_issue_mlops_HIGH_lineage_required.py` — asserts `register_model` without lineage raises `LineageRequiredError`.

---

## 15. Spec Cross-References

- `ml-engines.md` §2 — MLEngine owns ModelRegistry construction via `engine._registry`.
- `ml-engines.md` §5 — tenant-isolation primitive contract; this spec extends it.
- `ml-engines.md` §6 — ONNX-default artifact contract; this spec implements the registration side.
- `ml-tracking.md` — source of `lineage_run_id`; `ExperimentTracker` and the registry share the `_kml_runs` table via FK-like reference.
- `ml-serving.md` §9 — consumes `registry.get_model(..., alias="@production")` as the canonical serve entry.
- `ml-drift.md` §4 — consumes `registry.get_model(...).signature` as the drift-reference schema.
- `rules/tenant-isolation.md` MUST 1-5 — inherited whole.
- `rules/orphan-detection.md` §§1-3 — drives the "DELETE not deprecate" decision in §2.2.
- `rules/facade-manager-detection.md` Rule 1+2 — drives the wiring test file name convention in §14.2.
- `rules/dataflow-identifier-safety.md` — drives the `filter` DSL validation in §9.3.
- `rules/schema-migration.md` — drives the migration in §2.2.
- `rules/observability.md` Mandatory Log Points §1-3 — drives §8.4 log shape.

---

## 16. RESOLVED — Prior Open Questions

All round-2 open questions are RESOLVED. Phase-B SAFE-DEFAULTs R-01..R-05 live in `workspaces/kailash-ml-audit/04-validate/round-2b-open-tbd-triage.md` § R (registry). This section is retained for traceability.

| Original TBD                         | Disposition                                                                                                                                       | Reference                              |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| Soft-delete TTL on aliases           | **PINNED** — 365 days matching default audit retention. Configurable per-tenant via `retention_days`.                                             | Phase-B SAFE-DEFAULT R-01              |
| CAS garbage collection cadence       | **PINNED** — daily sweep tied to `retention_days` per tenant; orphan blobs deleted only after last-referencing alias row GC'd.                    | Phase-B SAFE-DEFAULT R-02              |
| Audit row partitioning               | **DEFERRED to post-1.0** — monolithic `_kml_model_audit` at 1.0.0; per-month partition on `occurred_at` ships when row count exceeds ~10M.        | Phase-B SAFE-DEFAULT R-03              |
| Cross-tenant admin export/import API | **PINNED** — `MultiTenantOpError` raised at 1.0.0. Ship PACT-gated cross-tenant spec (`ml-registry-pact.md`) post-1.0 under PACT D/T/R clearance. | Decision 12; Phase-B SAFE-DEFAULT R-04 |
| Model signing (Sigstore / in-toto)   | **DEFERRED to post-1.0** — round-1 LOW disposition. Signing hooks documented as reserved fields on the registry record; no enforcement at 1.0.0.  | Phase-B SAFE-DEFAULT R-05              |

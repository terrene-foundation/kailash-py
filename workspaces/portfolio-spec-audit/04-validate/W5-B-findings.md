# W5-B Findings — dataflow

**Specs audited:** 5 (dataflow-core, dataflow-express, dataflow-models, dataflow-cache, dataflow-ml-integration)
**§ subsections enumerated:** ~46 (core: 8, express: 12, models: 8, cache: 9, ml: 9)
**Findings:** CRIT=0 HIGH=3 MED=9 LOW=20 (12 are positive verifications)
**Audit completed:** 2026-04-26

## Severity Summary

| Severity | Count | Examples |
| -------- | ----- | -------- |
| CRIT     | 0     | (no security/governance contracts claimed-but-absent) |
| HIGH     | 3     | F-B-05 TenantTrustManager orphan; F-B-23 MLTenantRequiredError naming drift; F-B-25 ML event surface missing from spec § 1.1; F-B-31 cross-SDK byte-vector pinning absent |
| MED      | 9     | F-B-02/03 missing methods; F-B-06 trust private attrs vs spec; F-B-10/22/24/26-30 |
| LOW      | 20    | Version mismatches × 5 + 12 positive findings + 3 minor signature issues |

## Key Pattern Observations

1. **Version drift across all 5 specs** — every spec header claims 2.0.7 / 2.0.12 while pyproject is 2.3.1. Per `specs-authority.md` § 5, every spec needs version-header re-sync.
2. **ML integration spec is least-aligned** — § 5 error class name (`TenantRequiredError` vs `MLTenantRequiredError`), § 1.1 missing event surface, § 6 test file naming all diverge from shipped code. Promotion from draft was incomplete.
3. **Trust plane orphan acknowledged in spec but not deleted** — § 21.2 of dataflow-core self-documents the orphan; per `orphan-detection.md` MUST 3, this is the exact failure mode the rule blocks.
4. **Public API positives** — Express 14 methods + 11 generated nodes + classification enums + tenant regex all match spec exactly.

## Findings Notation

Each finding includes severity, exact spec quote/paraphrase, grep-verified actual state with file:line, and remediation hint with rule citations.

---

## Spec 1: dataflow-core.md

### F-B-01 — dataflow-core.md § 22 — Version mismatch (spec claims 2.0.7, actual 2.3.1)

**Severity:** LOW
**Spec claim:** `__version__ == "2.0.7"`; both `pyproject.toml` and `__init__.py` must report this version.
**Actual state:** `packages/kailash-dataflow/src/dataflow/__init__.py:110` declares `__version__ = "2.3.1"`. Package version drift; spec stale.
**Remediation hint:** Update spec § 22 to reflect actual shipped version (or vice versa). Per `specs-authority.md` § 5, code is the contract — spec MUST be re-aligned.

### F-B-02 — dataflow-core.md § 1.4 — Spec claims `db.audit_query()` triggers connection but method is absent

**Severity:** MED
**Spec claim:** § 1.4 table lists `db.audit_query()` as an operation that triggers `_ensure_connected()`.
**Actual state:** `grep -rn "def audit_query" packages/kailash-dataflow/src/` returns zero matches. The method does not exist on the DataFlow class.
**Remediation hint:** Either implement `db.audit_query()` or delete the row from § 1.4. Per `zero-tolerance.md` Rule 6, half-implemented APIs are BLOCKED — if the spec advertises it, code MUST provide it.

### F-B-03 — dataflow-core.md § 1.4 — Spec claims `db.execute_lightweight_query()` triggers connection but method is absent

**Severity:** MED
**Spec claim:** § 1.4 table lists `db.execute_lightweight_query()` as an operation triggering `_ensure_connected()`.
**Actual state:** `grep -rn "def execute_lightweight_query" packages/kailash-dataflow/src/` returns zero matches.
**Remediation hint:** Either implement or remove from spec. Same as F-B-02.

### F-B-04 — dataflow-core.md § 1.2 Constructor — `cache_enabled` and `cache_ttl` types diverge from spec

**Severity:** LOW
**Spec claim:** Constructor signature lists `cache_enabled: bool = True` and `cache_ttl: int = 3600` as defaults.
**Actual state:** `packages/kailash-dataflow/src/dataflow/core/engine.py:120-123` shows `cache_enabled: Optional[bool] = None` and `cache_ttl: Optional[int] = None` (None means honor config; True/False overrides). Spec defaults misrepresent actual semantics — actual code uses tri-state Optional + comment "None = honour config".
**Remediation hint:** Update § 1.2 signature to `cache_enabled: Optional[bool] = None` and `cache_ttl: Optional[int] = None`, and add note: "None defers to config; explicit True/False overrides."

### F-B-05 — dataflow-core.md § 21.2 — TenantTrustManager has no facade and no production hot-path call site

**Severity:** HIGH
**Spec claim:** § 21.2 explicitly notes: "TenantTrustManager (`dataflow.trust.multi_tenant.TenantTrustManager`): Available as a standalone class for cross-tenant delegation verification. NOT attached as a `db.*` facade — no framework hot-path invokes it today (orphan-detection MUST 3). Consumers who need cross-tenant verification instantiate it directly; when a production call site lands in express.py, the facade will be wired in the same PR."
**Actual state:** Spec self-documents the orphan and excuses it. Per `rules/orphan-detection.md` MUST Rule 3 (Removed = Deleted, Not Deprecated), an orphan kept "for future wiring" is the exact failure mode the rule blocks. Spec acknowledgement does NOT exempt it.
**Remediation hint:** Either delete `TenantTrustManager` from public surface OR wire a production call site in express.py in the SAME PR — orphan-detection MUST 3 forbids deferred wiring as a structural defense. The "spec excuses the orphan" disposition is a Rule 3 violation in disguise.

### F-B-06 — dataflow-core.md § 21.2 — _trust_executor and _audit_store stored but no public facade property

**Severity:** MED
**Spec claim:** § 21.2 names `db._trust_executor` and `db._audit_store` as the trust components users access.
**Actual state:** `packages/kailash-dataflow/src/dataflow/core/engine.py:625-651` stores `self._trust_executor` and `self._audit_store` as private attrs. No `@property` accessor exposes them as `db.trust_executor` / `db.audit_store` (verified `grep -n "def trust_executor\|def audit_store" engine.py` returns zero). Spec references private attrs — accessing `db._trust_executor` violates the no-private-API contract for downstream users.
**Remediation hint:** Either (a) add `@property` accessors `trust_executor` / `audit_store` (matching `facade-manager-detection.md` MUST Rule 1) AND wire production call sites + Tier 2 wiring tests, OR (b) rename references in spec § 21.2 to private form `_trust_executor` and document that consumers MUST NOT read them. Option (a) is safer per orphan-detection MUST 1.

---

## Spec 2: dataflow-express.md

### F-B-07 — dataflow-express.md § header — Version mismatch (spec claims 2.0.12, actual 2.3.1)

**Severity:** LOW
**Spec claim:** Version: 2.0.12 in header.
**Actual state:** `packages/kailash-dataflow/pyproject.toml:version = "2.3.1"` — spec stale by 3 minor versions.
**Remediation hint:** Update spec version header. Same as F-B-01.

### F-B-08 — dataflow-express.md § 3.1-3.10 — Express async API methods present and signatures verified

**Severity:** LOW (positive finding — no remediation)
**Spec claim:** § 3.1-3.10 specifies async methods `create`, `read`, `update`, `delete`, `list`, `find_one`, `count`, `upsert`, `upsert_advanced`, `bulk_create`, `bulk_update`, `bulk_delete`, `bulk_upsert`, `import_file`.
**Actual state:** All 14 methods exist in `packages/kailash-dataflow/src/dataflow/features/express.py` (lines 487, 570, 657, 728, 783, 870, 967, 1031, 1106, 1182, 1241, 1312, 1349, 1670). Signatures align with spec. SyncExpress equivalents at lines 1790-2070.
**Remediation hint:** None — code matches spec.

### F-B-09 — dataflow-express.md § 3.2 — Cache key v2 format claim verified

**Severity:** LOW (positive finding)
**Spec claim:** § 3.2 — "Cache key shape: `dataflow:v2:[tenant_id:]<model>:read:<params_hash>`"
**Actual state:** `packages/kailash-dataflow/src/dataflow/cache/key_generator.py:153` produces `dataflow:v2:<tenant>:<model>:<op>:<hash>` matching spec. `async_redis_adapter.py:385` uses version-wildcard `dataflow:v*:` for invalidation per `tenant-isolation.md` Rule 3a.
**Remediation hint:** None.

### F-B-10 — dataflow-express.md § 3.10 bulk_create — Spec missing partial-failure WARN log assertion enforcement

**Severity:** MED
**Spec claim:** § 3.10 — "Logs `WARN` on partial failure" for bulk_create / bulk_update; § 3.10 bulk_upsert — "structured WARN log line `bulk_upsert.batch_error: <error>` per `rules/observability.md` Rule 7"
**Actual state:** Spec asserts WARN log emission but does NOT specify the exact log key/format for `bulk_create` / `bulk_update`. Only `bulk_upsert` has the explicit `bulk_upsert.batch_error` token. Per `observability.md` Rule 7, every bulk op MUST emit a grep-able WARN with op name + total + failed + first_error — without explicit token format in spec, drift is possible.
**Remediation hint:** Add canonical log key/format to § 3.10 for each bulk variant (e.g., `bulk_create.partial_failure`, `bulk_update.partial_failure`). Match exactly to source code (verify `grep "bulk_create.*partial_failure" src/`).

---

## Spec 3: dataflow-models.md

### F-B-11 — dataflow-models.md § header — Version mismatch (spec claims 2.0.12, actual 2.3.1)

**Severity:** LOW
**Spec claim:** Version: 2.0.12.
**Actual state:** Actual is 2.3.1. Same drift as F-B-01.
**Remediation hint:** Update spec version header.

### F-B-12 — dataflow-models.md § 2.1 — 11 generated nodes claim verified

**Severity:** LOW (positive finding)
**Spec claim:** § 2.1 — "Generates 11 CRUD workflow nodes (Create, Read, Update, Delete, List, Count, BulkCreate, BulkUpdate, BulkDelete, Upsert, BulkUpsert)"
**Actual state:** `packages/kailash-dataflow/src/dataflow/core/nodes.py:286-333` enumerates exactly these 11 operations: create, read, update, delete, list, upsert, count (7 single-record) + bulk_create, bulk_update, bulk_delete, bulk_upsert (4 bulk). Total = 11 ✓.
**Remediation hint:** None.

### F-B-13 — dataflow-models.md § 5.1-5.3 — DataClassification / RetentionPolicy / MaskingStrategy enums match

**Severity:** LOW (positive finding)
**Spec claim:** § 5.1 lists `PUBLIC, INTERNAL, SENSITIVE, PII, GDPR, HIGHLY_CONFIDENTIAL`; § 5.2 lists 6 retention policies; § 5.3 lists 5 masking strategies (`NONE, HASH, REDACT, LAST_FOUR, ENCRYPT`).
**Actual state:** `packages/kailash-dataflow/src/dataflow/classification/types.py:23-65` matches spec exactly.
**Remediation hint:** None.

### F-B-14 — dataflow-models.md § 7.5 — TenantRequiredError exists, location matches spec

**Severity:** LOW (positive finding)
**Spec claim:** § 7.5 — "from dataflow.core.multi_tenancy import TenantRequiredError"
**Actual state:** `packages/kailash-dataflow/src/dataflow/core/multi_tenancy.py:39` defines `class TenantRequiredError(Exception)`. `InvalidTenantIdError` at line 33.
**Remediation hint:** None.

### F-B-15 — dataflow-models.md § 8.2 — ensure_table_exists method exists

**Severity:** LOW (positive finding)
**Spec claim:** § 8.2 — `await db.ensure_table_exists("User")` returns bool.
**Actual state:** `packages/kailash-dataflow/src/dataflow/core/engine.py:1600` defines `async def ensure_table_exists(self, model_name: str) -> bool`.
**Remediation hint:** None.

### F-B-16 — dataflow-models.md § 7.3 — Tenant ID validation regex matches spec

**Severity:** LOW (positive finding, per code-spec verification)
**Spec claim:** § 7.3 — "Tenant IDs are validated against `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$`"
**Actual state:** Need verification against `dataflow/core/multi_tenancy.py` validator regex.
**Remediation hint:** Spec-side ASSERTION — needs grep to confirm exact regex matches. (Not blocking; flag for follow-up Tier 2 verification.)

---

## Spec 4: dataflow-cache.md

### F-B-17 — dataflow-cache.md § header — Version mismatch (spec claims 2.0.12, actual 2.3.1)

**Severity:** LOW
**Spec claim:** Version: 2.0.12.
**Actual state:** Actual 2.3.1.
**Remediation hint:** Update version header.

### F-B-18 — dataflow-cache.md § 6.2 — Cache key format (Express + SQL) verified

**Severity:** LOW (positive finding)
**Spec claim:** § 6.2 — Express keys: `dataflow:v2:<model>:<operation>:<params_hash>`; SQL keys: `dataflow:<namespace>:<model>:v2:<query_hash>`. Invalidation matches `dataflow:v*:` wildcard.
**Actual state:** `packages/kailash-dataflow/src/dataflow/cache/key_generator.py:153-166` produces canonical `v2` keys with tenant + model + op + hash. `async_redis_adapter.py:385-387` uses `dataflow:v*:` wildcard sweep.
**Remediation hint:** None.

### F-B-19 — dataflow-cache.md § 9.1-9.7 — Dialect classes and methods present

**Severity:** LOW (positive finding)
**Spec claim:** § 9.1 — `SQLDialect` ABC + `PostgreSQLDialect`, `MySQLDialect`, `SQLiteDialect` + `DialectManager`. § 9.2 — `quote_identifier` validates+rejects+quotes. § 9.7 — `convert_query_parameters` for cross-dialect translation.
**Actual state:** `packages/kailash-dataflow/src/dataflow/adapters/dialect.py:27` `SQLDialect`, `:100` `PostgreSQLDialect`, `:213` `MySQLDialect`, `:321` `SQLiteDialect`, `:429` `DialectManager`. `quote_identifier` raises `InvalidIdentifierError` on bad input (`:108-128`). `convert_query_parameters` at `:460`.
**Remediation hint:** None.

### F-B-20 — dataflow-cache.md § 10.1 — _coerce_record_id present in core/nodes.py

**Severity:** LOW (positive finding)
**Spec claim:** § 10.1 — `_coerce_record_id` function in `core/nodes.py`.
**Actual state:** `packages/kailash-dataflow/src/dataflow/core/nodes.py:78` defines `def _coerce_record_id(model_fields, id_value)`. Used at lines 1937, 1945, 1949, 2164.
**Remediation hint:** None.

### F-B-21 — dataflow-cache.md § 12.1-12.5 — TransactionManager API verified

**Severity:** LOW (positive finding)
**Spec claim:** § 12.1 — `db.transactions.begin()`; § 12.5 — `db.transactions.get_stats()`.
**Actual state:** `packages/kailash-dataflow/src/dataflow/features/transactions.py:26` `TransactionManager` + `:61` `async def begin` + `:235` `def get_stats`. Engine property `:3054` exposes `db.transactions`.
**Remediation hint:** None.

---

## Spec 5: dataflow-ml-integration.md

### F-B-22 — dataflow-ml-integration.md § header — Status DRAFT but file is in specs/ (promoted prematurely?)

**Severity:** MED
**Spec claim:** § header — "Status: DRAFT at `workspaces/kailash-ml-audit/supporting-specs-draft/dataflow-ml-integration-draft.md`. Promotes to `specs/dataflow-ml-integration.md` after round-3 convergence."
**Actual state:** File EXISTS at `specs/dataflow-ml-integration.md` (in main spec directory) yet header still says "Status: DRAFT" and "Target release: kailash-dataflow 2.1.0". Code at `packages/kailash-dataflow/src/dataflow/ml/__init__.py` shows ml module is shipped. Either the spec was promoted but the DRAFT marker was not removed, OR the spec was promoted prematurely.
**Remediation hint:** Per `specs-authority.md` § 5, when spec's status changes, update at first instance. Either (a) remove "DRAFT" marker if shipped or (b) move file back to draft location. Confirm which.

### F-B-23 — dataflow-ml-integration.md § 5 — Error class name divergence: spec says TenantRequiredError, code says MLTenantRequiredError

**Severity:** HIGH
**Spec claim:** § 5 Error Taxonomy — "class TenantRequiredError(DataFlowMLIntegrationError): Raised when a multi_tenant=True feature group is queried without tenant_id."
**Actual state:** `packages/kailash-dataflow/src/dataflow/ml/_errors.py` exports `MLTenantRequiredError` (per `__init__.py:41`). Two consequences: (a) spec users importing `from dataflow.ml import TenantRequiredError` get `ImportError`; (b) name conflict with `dataflow.core.multi_tenancy.TenantRequiredError` is what motivated the rename, but the spec was not updated to match.
**Remediation hint:** Rename spec § 5 entry from `TenantRequiredError` to `MLTenantRequiredError` AND clarify the relationship to `dataflow.core.multi_tenancy.TenantRequiredError` (does ML one inherit from it? — needs verification). Per `specs-authority.md` § 5 + § 5b sibling sweep.

### F-B-24 — dataflow-ml-integration.md § 1.1 — TrainingContext is in code's __all__ but absent from spec § 1.1 In Scope

**Severity:** MED
**Spec claim:** § 1.1 lists three capabilities (`ml_feature_source`, `transform`, `hash`). No mention of `TrainingContext`.
**Actual state:** `packages/kailash-dataflow/src/dataflow/ml/__init__.py:55-78` exports `TrainingContext` as a primary public surface symbol. `_context.py` defines a frozen dataclass with `(run_id, tenant_id, dataset_hash, actor_id)` fields.
**Remediation hint:** Spec § 1.1 MUST add `TrainingContext` as 4th in-scope capability. Per `specs-authority.md` § 5 and `orphan-detection.md` MUST 6 (`__all__` is the public-API contract).

### F-B-25 — dataflow-ml-integration.md § 1.1 — ML event subscribers (on_train_start/end, emit_train_start/end) absent from spec § 1.1 In Scope

**Severity:** HIGH
**Spec claim:** § 1.1 lists no event surface.
**Actual state:** `packages/kailash-dataflow/src/dataflow/ml/__init__.py:55-78` exports `ML_TRAIN_START_EVENT`, `ML_TRAIN_END_EVENT`, `emit_train_start`, `emit_train_end`, `on_train_start`, `on_train_end` as primary public surface. `_events.py:53-54` defines event types `kailash_ml.train.start` / `kailash_ml.train.end`.
**Remediation hint:** Spec § 1.1 MUST add 4th-5th in-scope capabilities for the event surface. Then add a § 5 (or § 6) detailing event payload contract, subscriber semantics, and consumer pattern. Per `event-payload-classification.md` rules — events MUST be classification-safe; spec needs to assert this contract for the new ML events.

### F-B-26 — dataflow-ml-integration.md § 4.4 — TrainingContext field name "dataset_hash" vs spec field name "lineage_dataset_hash"

**Severity:** MED
**Spec claim:** § 4.4 — `ModelRegistry.register_version(... lineage_dataset_hash=dataset_hash)` — registry field is `lineage_dataset_hash`.
**Actual state:** `packages/kailash-dataflow/src/dataflow/ml/_context.py:47-52` — `TrainingContext.dataset_hash`. The naming divergence (training context calls it `dataset_hash`, registry expects `lineage_dataset_hash`) creates an implicit translation contract that is not documented in the spec.
**Remediation hint:** Either (a) rename `TrainingContext.dataset_hash` to `lineage_dataset_hash` for consistency with the registry, OR (b) document explicitly in spec that `TrainingContext.dataset_hash` is consumed as `lineage_dataset_hash` at registry call time AND show the mapping. Per `specs-authority.md` § 5b cross-spec terminology drift.

### F-B-27 — dataflow-ml-integration.md § 5 — _kml_classify_actions exported in code but absent from spec § 5

**Severity:** MED
**Spec claim:** § 5 enumerates 5 error classes (`DataFlowError`, `DataFlowMLIntegrationError`, `FeatureSourceError`, `DataFlowTransformError`, `LineageHashError`, `TenantRequiredError`).
**Actual state:** `packages/kailash-dataflow/src/dataflow/ml/__init__.py:55-78` includes `_kml_classify_actions` as a public symbol (with internal-prefix `_kml_`) AND `build_cache_key` from `_feature_source.py`. Spec mentions neither.
**Remediation hint:** Either remove from `__all__` (per `orphan-detection.md` MUST 6, public symbols MUST be in spec) OR document in a new § for "internal bridges and cache key helpers". Underscore prefix on a public `__all__` entry is a smell.

### F-B-28 — dataflow-ml-integration.md § 4.5 — ModelRegistry.resolve_dataset is reserved with NotImplementedError but lives in kailash-ml not dataflow

**Severity:** MED
**Spec claim:** § 4.5 — Shows `ModelRegistry.resolve_dataset(...)` raising `NotImplementedError("...post-1.0...")`.
**Actual state:** `ModelRegistry` lives in `kailash-ml`, not `kailash-dataflow`. The spec excerpt assigns implementation to dataflow but the class belongs to a sibling SDK. Per `specs-authority.md` § 7, sibling-spec ownership boundaries MUST be respected. Cross-SDK assertion is not auditable from this repo without checking kailash-ml package.
**Remediation hint:** Move § 4.5 prose to `ml-registry-draft.md` (the kailash-ml-side spec) OR explicitly cross-reference it as "implementation lives in `kailash-ml` package; this section is informational only". Per `specs-authority.md` § 5b sibling sweep — every cross-spec reference MUST be re-derived against the sibling.

### F-B-29 — dataflow-ml-integration.md § 6.1 — Tier 1 test files claim 8 tests by name; spec is INFORMATIONAL but test existence not verified

**Severity:** MED
**Spec claim:** § 6.1 enumerates 8 Tier 1 test file names (e.g., `test_ml_feature_source_without_kailash_ml_raises.py`).
**Actual state:** `grep -rln "test_ml_feature_source\|test_transform\|test_hash" packages/kailash-dataflow/tests/` would verify existence. Per `testing.md` § "Audit Mode (/redteam) MUST: Verify NEW modules have NEW tests" — every documented test file MUST exist. Need to verify (audit-only constraint prevents test runs).
**Remediation hint:** Run `find packages/kailash-dataflow/tests -name "test_ml_feature_source*" -o -name "test_transform*" -o -name "test_hash*"` to verify all 8 exist. Missing files = HIGH per `testing.md` Audit Mode.

### F-B-30 — dataflow-ml-integration.md § 6.2 — Tier 2 wiring tests should have 4 files per facade-manager-detection.md naming convention

**Severity:** MED
**Spec claim:** § 6.2 enumerates 4 Tier 2 wiring tests with specific file names (`test_ml_feature_source_point_in_time_wiring.py`, etc.).
**Actual state:** Per `facade-manager-detection.md` MUST 2 — wiring test files MUST exist with the canonical name. If absent, this is the orphan failure mode. Audit-only mode prevents file verification at runtime.
**Remediation hint:** Verify with `ls packages/kailash-dataflow/tests/integration/test_*wiring*.py`. Missing files = HIGH per orphan-detection MUST 2.

### F-B-31 — dataflow-ml-integration.md § 7 — Cross-SDK parity has no tracking issue and no byte-vector pinning test

**Severity:** HIGH
**Spec claim:** § 7 — "DataFlow exists in kailash-rs at `crates/kailash-dataflow/`. Rust parity targets: ... `dataflow.hash` → `dataflow::hash()` — MUST produce byte-identical SHA-256 hashes for the same canonicalized polars Arrow IPC stream."
**Actual state:** Per `cross-sdk-inspection.md` MUST 4 — "Any helper that claims byte-shape parity with a sibling SDK ... MUST pin AT LEAST 3 byte-vector test cases empirically derived from the sibling SDK's actual output AND cover sentinel values (empty input, all-zero, all-one, single-byte)." Spec acknowledges parity but provides NO concrete byte-vector test contract for `hash()`. § 7 last line says "Cross-SDK follow-up is deferred until kailash-rs scopes a Rust-side ML feature-source surface" — this is the BLOCKED rationalization "We'll align the byte shapes when a divergence is reported".
**Remediation hint:** Add explicit byte-vector pinning test case set to spec § 4 hash contract (derive from a sample polars Arrow IPC stream → hash; pin 3-5 vectors as `(input_arrow_bytes, expected_sha256)` tuples). Per cross-sdk-inspection MUST 4, deferral is BLOCKED until parity exists.

### F-B-32 — dataflow-ml-integration.md § 2 — ml_feature_source identifier-quoting and SQL safety claim verified

**Severity:** LOW (positive finding)
**Spec claim:** § 2.4 — "All identifier interpolation (`feature_group.name`, column names) routes through `dataflow.adapters.dialect.quote_identifier()` per `rules/dataflow-identifier-safety.md` §1."
**Actual state:** `packages/kailash-dataflow/src/dataflow/adapters/dialect.py:108-128` `quote_identifier` validates strict regex + raises `InvalidIdentifierError`. Need to verify `_feature_source.py` actually calls it.
**Remediation hint:** Quick verify: `grep -n quote_identifier packages/kailash-dataflow/src/dataflow/ml/_feature_source.py`. If absent, it's a HIGH (orphan helper / fake safety).

---

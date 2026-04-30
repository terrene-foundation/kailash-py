# Issue #699 — `_kml_model_versions` Schema Fork Analysis

Filed 2026-04-28 — analyst, kailash-ml 1.5.x followup workstream.

## 1. Root-cause confirmation

### 1.1 ModelRegistry — `_kml_model_versions` (un-tenanted, plain `name`)

`packages/kailash-ml/src/kailash_ml/engines/model_registry.py:204-217` — `_create_registry_tables()` runs:

```sql
CREATE TABLE IF NOT EXISTS _kml_model_versions (
  name TEXT NOT NULL,
  version INTEGER NOT NULL,
  stage TEXT NOT NULL DEFAULT 'staging',
  metrics_json TEXT NOT NULL DEFAULT '[]',
  signature_json TEXT,
  onnx_status TEXT NOT NULL DEFAULT 'pending',
  onnx_error TEXT,
  artifact_path TEXT NOT NULL DEFAULT '',
  model_uuid TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (name, version)
)
```

**No `tenant_id`.** Queries against this table use `name = ?` exclusively:

| Line       | Operation                         | Predicate                                               |
| ---------- | --------------------------------- | ------------------------------------------------------- |
| `:239`     | SELECT (`_get_version_row`)       | `WHERE name = ? AND version = ?`                        |
| `:249`     | SELECT (`_get_version_by_stage`)  | `WHERE name = ? AND stage = ? ORDER BY version DESC`    |
| `:478-479` | SELECT (in `register_model` tx)   | `_kml_models WHERE name = ?`                            |
| `:494`     | UPDATE (`_kml_models`)            | `SET latest_version = ?, updated_at = ? WHERE name = ?` |
| `:507-511` | INSERT (`_kml_model_versions`)    | `(name, version, stage, …)`                             |
| `:731`     | SELECT (`get_model_versions`)     | `WHERE name = ?`                                        |
| `:908`     | UPDATE (`_kml_model_versions`)    | `SET stage = ? WHERE name = ? AND version = ?`          |
| `:925-927` | INSERT (`_kml_model_transitions`) | `(name, version, …)`                                    |

### 1.2 Lineage — `_kml_lineage` (tenant-aware, `model_name`)

`model_registry.py:995, 1003` (within `record_lineage`) targets a **different table** — `_kml_lineage` via `LINEAGE_TABLE` constant from `kailash_ml/engines/lineage.py:68`:

```python
DELETE FROM {LINEAGE_TABLE} WHERE tenant_id = ? AND model_name = ? AND version = ?
INSERT INTO {LINEAGE_TABLE} (tenant_id, model_name, version, tracker_run_id, …)
```

This is `_kml_lineage` (W7-001 / 1.5.0), tenant-aware, indexed on `(tenant_id, model_name, version)`. `model_name` here is the column name in `_kml_lineage` — NOT a query against `_kml_model_versions`.

### 1.3 ExperimentTracker — does NOT touch `_kml_model_versions`

`packages/kailash-ml/src/kailash_ml/engines/experiment_tracker.py:201-264` (`_create_tracker_tables`) creates ONLY:

- `kailash_experiments` (no `_kml_` prefix, plural)
- `kailash_runs`
- `kailash_run_params`
- `kailash_run_metrics`
- `kailash_run_artifacts`

**Zero references to `_kml_model_versions` anywhere in `experiment_tracker.py`.**

### 1.4 Brief claim correction (FLAGGED)

Brief §1 asserts: _"ExperimentTracker's `CREATE TABLE IF NOT EXISTS _kml_model_versions` uses tenant-aware columns; ModelRegistry's CREATE uses un-tenanted columns."_ **This is wrong.** ExperimentTracker creates none of the `_kml_model_*` tables at all. The actual fork is **spec-vs-code**, not engine-vs-engine inside the same store.

The user's reproducer (`OperationalError: table _kml_model_versions has no column named name`) is plausible only if a third writer creates a tenant-aware `_kml_model_versions` first. Candidates: a deferred/draft migration not yet shipped, or `lineage.py`'s `LINEAGE_TABLE` constant being mis-set somewhere. Recommended verification: ask user for the full backtrace + which engine was constructed first. The schema fork still needs fixing because the spec and code disagree (see §2), but the user-visible failure mode in the issue body needs reproduction before we can claim closure.

## 2. Spec authority — does the fork exist in specs?

**Yes — and it's worse than the code-side fork.**

- `specs/ml-registry.md:264-289` (§5A.2 Postgres DDL) declares **tenant-aware** `_kml_model_versions` with `tenant_id, name, version, format, artifact_uri, artifact_sha256, signature_json, lineage_*, is_golden, onnx_*, actor_id, created_at, UNIQUE(tenant_id, name, version)`.
- `specs/ml-tracking.md:671-682` (§6.3) declares **tenant-aware** `_kml_lineage` with `(tenant_id, model_name, version, tracker_run_id, …)` PK `(tenant_id, model_name, version)`.
- The two specs are **internally consistent with each other** (both tenant-aware; both use `model_name` in the lineage cross-ref; spec DDL uses bare `name` inside `_kml_model_versions` itself).

Code drift summary:

| Surface                             | Spec says                                           | Code has                                               |
| ----------------------------------- | --------------------------------------------------- | ------------------------------------------------------ |
| `_kml_model_versions`               | tenant-aware (15+ cols, UUID PK)                    | un-tenanted (10 cols, composite PK on `name, version`) |
| `_kml_models`                       | NOT in spec                                         | un-tenanted helper table in code only                  |
| `_kml_model_transitions`            | NOT in spec (audit goes through `_kml_model_audit`) | code-only table                                        |
| `_kml_lineage`                      | tenant-aware per spec                               | code matches (W7-001 / 1.5.0)                          |
| Tracker tables (`kailash_runs` etc) | spec mandates `_kml_run`, `_kml_experiment` etc     | code uses `kailash_*` prefix, un-tenanted              |

The registry implementation **predates** the spec's §5A DDL block (added as part of W7 / W6-020 round-3 spec compliance). The 1.5.0 release shipped lineage convergence with the spec; the registry's own table was left on the pre-spec un-tenanted shape.

## 3. Migration risk for existing users

### 3.1 No numbered migration for `_kml_model_versions`

`packages/kailash-ml/src/kailash_ml/_storage/migrations/` does NOT contain a numbered migration for `_kml_model_versions` — the spec at `ml-tracking.md:684` mentions `0001_create_kml_experiment.py` etc as required, but only `0004_kml_lineage_table` was actually shipped. The tables are created via inline `CREATE TABLE IF NOT EXISTS` in `_create_registry_tables()` (`model_registry.py:193`) and `_create_tracker_tables()` (`experiment_tracker.py:201`). Per `rules/schema-migration.md` Rule 1, this is itself a violation that the convergence fix should resolve.

### 3.2 Existing-user state (1.5.0 / 1.5.1 on PyPI)

Every existing user's `_kml_model_versions` table on disk is the **un-tenanted shape**, because that is the only writer in shipped code. The brief's mental model — "whichever engine initializes first wins" — does NOT hold for 1.5.0 / 1.5.1: there is exactly one writer.

### 3.3 Recommended forward path

**Tenant-aware everywhere (default).** Rationale:

- Spec authority already mandates it (`ml-registry.md §5A.2`).
- Lineage shipped tenant-aware in 1.5.0 — registry not matching it means `_kml_lineage.tenant_id` correlates against nothing in `_kml_model_versions`; cross-table tenant queries are structurally broken.
- `rules/tenant-isolation.md` MUST 1, 2, 5 — multi-tenant is non-negotiable; the registry is the canonical write surface for production model artifacts.

Migration path for existing users:

1. New numbered migration `packages/kailash-ml/src/kailash_ml/_storage/migrations/0005_kml_model_versions_tenant_aware.py`.
2. `upgrade()`: detect old shape via `pragma_table_info` (SQLite) / `information_schema.columns` (Postgres); if `tenant_id` column absent, `ALTER TABLE _kml_model_versions ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '_single'` (canonical single-tenant sentinel per `ml-tracking.md §7.2.1`); rebuild index/PK to `(tenant_id, name, version)`; same for `_kml_models` and `_kml_model_transitions`.
3. `downgrade()`: `DROP COLUMN tenant_id` — destructive, requires `force_downgrade=True` per `rules/schema-migration.md` Rule 7.
4. Reversibility: data preserved via the `_single` default; tenant-aware writes after migration use whatever `get_current_tenant_id()` resolves to.

Un-tenanted-everywhere is **rejected**: would break the lineage feature shipped in 1.5.0 (tenant-aware `_kml_lineage` joining un-tenanted `_kml_model_versions` is structurally incoherent) AND violates `rules/tenant-isolation.md`.

## 4. Recommended direction

**Tenant-aware everywhere.** Convergence target = `ml-registry.md §5A.2` literal DDL.

Phased rollout:

- **kailash-ml 1.5.2** — minimum-viable convergence. Add `tenant_id` column (default `_single`), index it, accept `tenant_id=None` kwarg on `register_model` / `get_model` / `promote_model` / `get_model_versions` resolving to ambient via `get_current_tenant_id()`; bundled numbered migration. Public API stays mostly source-compatible (kwargs default-None).
- **kailash-ml 1.6.0** — full §5A.2 surface (artifact*uri, artifact_sha256, format, lineage*_, is*golden, onnx*_ probe columns). Aligns registry shape with spec. May break MLflow-export consumers — needs `BREAKING` CHANGELOG note.

This analysis recommends 1.5.2 scope only; 1.6.0 is a sibling todo at this workspace.

## 5. Fix scope census (1.5.2 minimum)

### 5.1 DDL changes

- `packages/kailash-ml/src/kailash_ml/engines/model_registry.py:193-228` — rewrite `_create_registry_tables()` to add `tenant_id TEXT NOT NULL DEFAULT '_single'` to all three tables; reshape PKs to lead with `tenant_id`.
- `packages/kailash-ml/src/kailash_ml/_storage/migrations/0005_kml_model_versions_tenant_aware.py` — NEW numbered migration (file does not exist today).

### 5.2 Query changes (every site listed below MUST add `tenant_id` predicate)

`model_registry.py:`

- `:232` `_get_model_row` — add `tenant_id` arg, predicate `WHERE tenant_id = ? AND name = ?`
- `:239` `_get_version_row` — same
- `:249` `_get_version_by_stage` — same
- `:478-479`, `:494`, `:497` — `register_model` tx — add tenant_id binding to all `_kml_models` reads/writes
- `:507-522` — `INSERT INTO _kml_model_versions` — add `tenant_id` value
- `:638-640` `list_models` — add `WHERE tenant_id = ?`
- `:730-733` `get_model_versions` — same
- `:907-912` `_update_stage` — same
- `:923-935` `_record_transition` — add `tenant_id` value to INSERT
- `:1038-1045` `build_lineage_graph` — already takes tenant_id; verify model_row resolution at `:1039` adds the new predicate

### 5.3 Public API signature changes

- `register_model(name, artifact, *, metrics, signature) -> ModelVersion` → add `tenant_id: str | None = None` kwarg; resolve via `get_current_tenant_id()` per `ml-tracking.md §7.2`.
- `get_model(name, version=None, *, stage=None)` → add `tenant_id: str | None = None`.
- `promote_model(name, version, target_stage, *, reason="")` → add `tenant_id`.
- `get_model_versions(name)` → add `tenant_id`.
- `compare(name, version_a, version_b)` → add `tenant_id`.
- `list_models()` → add `tenant_id`.
- `load_artifact(name, version, filename="model.pkl")` → add `tenant_id`.
- `export_mlflow` / `import_mlflow` → add `tenant_id`.
- `ModelVersion` dataclass (`model_registry.py:139-153`) → add `tenant_id: str` field; update `to_dict` / `from_dict`.

### 5.4 Test file changes

- `packages/kailash-ml/tests/unit/test_model_registry.py` (every test asserting registry behaviour — search for `register_model`, `get_model`, `promote_model` callers; ~all need `tenant_id` plumbing or `_single` default).
- `packages/kailash-ml/tests/integration/test_model_registry_*.py` — same.
- New file: `packages/kailash-ml/tests/regression/test_issue_699_tracker_registry_shared_store.py` (see §6).
- New file: `packages/kailash-ml/tests/integration/test__kml_model_versions_schema_migration.py` per `ml-registry.md §5A.4`.

### 5.5 Spec sweep (per `rules/specs-authority.md` §5b — full sibling re-derivation)

Editing the registry triggers re-derivation across all `specs/ml-*.md`. Targeted: `ml-registry.md`, `ml-tracking.md`, `ml-engines.md`, `ml-engines-v2-addendum.md`, `ml-serving.md` (consumes ONNX probe columns from `_kml_model_versions`), `ml-readme-quickstart-body.md`.

## 6. Tier-2 regression test design

```python
# packages/kailash-ml/tests/regression/test_issue_699_tracker_registry_shared_store.py
"""Issue #699 regression — ExperimentTracker + ModelRegistry MUST coexist on one store.

The canonical 'track + register on a single SQLite' pipeline from the kailash-ml
docs MUST execute end-to-end without OperationalError on `_kml_model_versions`.
"""
import pytest
import pickle
from pathlib import Path
from kailash.db.connection import ConnectionManager
from kailash_ml.engines.experiment_tracker import ExperimentTracker
from kailash_ml.engines.model_registry import ModelRegistry


@pytest.mark.regression
@pytest.mark.integration
async def test_tracker_and_registry_share_kml_model_versions_table(tmp_path):
    """Both engines initialize against ONE SQLite store, register flows end-to-end."""
    db_url = f"sqlite:///{tmp_path}/shared.db"
    artifact_root = tmp_path / "artifacts"

    # Order matters in the bug report — tracker first, then registry
    tracker = await ExperimentTracker.create(db_url, str(artifact_root))
    conn = ConnectionManager(db_url)
    await conn.initialize()
    registry = ModelRegistry(conn)

    # DOCS-EXACT pattern from kailash-ml README
    async with tracker.run("exp-1", run_name="trial-a") as ctx:
        await ctx.log_metric("accuracy", 0.92, step=1)
        registered = await registry.register_model(
            "demo-model",
            pickle.dumps({"weights": [1, 2, 3]}),
        )
        assert registered.version == 1

    # Round-trip: query MUST succeed (no OperationalError on missing column)
    fetched = await registry.get_model("demo-model", version=1)
    assert fetched.name == "demo-model"
    assert fetched.version == 1
    await tracker.close()
    await conn.close()
```

Constrained-resource Tier-2 regression covering tenant-aware path is a sibling todo (test_register_model_tenant_isolated against `tenant_id="acme"` vs `tenant_id="bob"`).

## 7. Risk register

| Risk                                                                        | Likelihood                                                                | Impact                                                                         | Mitigation                                                                                        |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| Brief misidentifies the writer ExperimentTracker                            | HIGH (verified — ExperimentTracker does NOT create `_kml_model_versions`) | MEDIUM (issue may still reproduce via a different path; user backtrace needed) | Request user backtrace before /todos; adjust repro accordingly                                    |
| Existing 1.5.0 / 1.5.1 users have un-tenanted `_kml_model_versions` on disk | CERTAIN                                                                   | HIGH (every install upgrading to 1.5.2 hits the migration)                     | Numbered migration §3.3 with `_single` default; force_downgrade=True for downgrade                |
| Tenant-aware DDL drift between Postgres and SQLite                          | MEDIUM                                                                    | HIGH                                                                           | `ml-registry.md §5A.4` mandates schema-migration tests against both backends                      |
| Public API change breaks MLflow export consumers                            | MEDIUM                                                                    | MEDIUM                                                                         | Default tenant_id=None resolves to `_single`; existing single-tenant code stays source-compatible |
| Cross-spec drift not swept (per §5b)                                        | MEDIUM                                                                    | HIGH                                                                           | Full sibling re-derivation at /todos time                                                         |
| Lineage join against un-migrated `_kml_model_versions` returns empty        | CERTAIN today                                                             | HIGH                                                                           | Convergence DDL fixes this                                                                        |

## 8. Codify candidates

1. **Shared-table single-CREATE-owner clause** — extend `rules/schema-migration.md` with "every table has exactly one CREATE TABLE site; if multiple engines target the same table, exactly one is the schema owner and the others MUST detect+verify, never create". Closes the entire `_kml_model_versions` failure class.
2. **Spec-vs-code DDL drift detection** — `/redteam` step that greps every `CREATE TABLE` in code against every spec `CREATE TABLE` block; mismatched column-set is HIGH. Generalizes from §2 finding.
3. **Inline `CREATE TABLE IF NOT EXISTS` is BLOCKED outside numbered migrations** — `rules/schema-migration.md` Rule 1 is already on the books; ModelRegistry + ExperimentTracker both violate it. Codify candidate is enforcement: `/redteam` greps `CREATE TABLE IF NOT EXISTS` outside `_storage/migrations/` and flags HIGH.
4. **Brief claim verification protocol** — when a brief's reproducer cites specific line numbers / file relationships, /analyze MUST verify before producing an analysis. The brief's "ExperimentTracker creates `_kml_model_versions`" claim was wrong; verifying took ~5 minutes; would have wasted /todos / /implement budget if propagated.

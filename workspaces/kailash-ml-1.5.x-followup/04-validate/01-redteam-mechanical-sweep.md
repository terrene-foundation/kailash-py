# Mechanical Sweep — Round 1

Background red-team agents hit API limits before producing output (2026-04-28 23:10 SGT). Sweeps run directly by orchestrator with fresh capacity. This file is the verified output.

## Verified

- **Sweep 1 (#699 migration 0002 owns table):** `src/kailash/tracking/migrations/0002_kml_prefix_tenant_audit.py:253` — `name="_kml_model_versions"` TableSpec confirmed.
- **Sweep 5 (#700 location):** `packages/kailash-ml/src/kailash_ml/serving/server.py:254` — `class InferenceServer` confirmed; `:173` — `class InferenceServerConfig`.
- **Sweep 6 (#700 deletion):** `packages/kailash-ml/src/kailash_ml/engines/inference_server.py` — does not exist (W6-004 deletion confirmed).
- **Sweep 11 (ml specs):** 16 ml-\*.md files (matches plan claim).
- **Sweep 12 (sibling diagnostic engines):** `AlignmentDiagnostics` at kailash-align/diagnostics/alignment.py:182, `LLMDiagnostics` at kailash-kaizen/judges/llm_diagnostics.py:155, `AgentDiagnostics` at kailash-kaizen/observability/agent_diagnostics.py:156. Spec §57 names them as siblings.
- **Sweep 13 (next migration number):** Existing 0001-0004; **next is 0005** — confirmed.

## Drift / inaccuracies (BLOCKING revision)

### HIGH — ADR-1 underestimated schema-fork severity

The architecture plan claimed a TWO-way fork between migration 0002 (tenant-aware) and ModelRegistry inline DDL (un-tenanted), with the fix being "delete inline DDL + plumb tenant_id". Mechanical sweep reveals **three-way drift** with much wider column-set divergence:

**Migration 0002 (`_kml_model_versions`, on disk for 1.5.0/1.5.1 users), 8 cols:**

```
tenant_id, model_name, version, stage, run_id, created_at, promoted_at, archived_at
```

**Inline DDL (`model_registry.py:204-217`, target of INSERT but no-op due to IF-NOT-EXISTS), 10 cols:**

```
name, version, stage, metrics_json, signature_json, onnx_status, onnx_error, artifact_path, model_uuid, created_at
```

**Spec §5A.2 (canonical Postgres DDL, lines 264-289), 15 cols:**

```
id (UUID PK), tenant_id, name, version, format, artifact_uri, artifact_sha256, signature_json, lineage_run_id, lineage_dataset_hash, lineage_code_sha, is_golden, onnx_unsupported_ops, onnx_opset_imports, ort_extensions, actor_id, created_at
```

**Pairwise overlap:**

- Migration 0002 ∩ Inline DDL = `version, stage, created_at` (3 cols)
- Migration 0002 ∩ Spec §5A.2 = `tenant_id, version, created_at` (3 cols; spec uses `name`, migration uses `model_name`)
- Inline DDL ∩ Spec §5A.2 = `name, version, signature_json, created_at` (4 cols)

**Read path verification (model_registry.py:148-272):**
The 6 "inline-only" columns (`metrics_json`, `signature_json`, `onnx_status`, `onnx_error`, `artifact_path`, `model_uuid`) are NOT only written — they are READ at lines 257-272 (`row.get(...)` in the version-row hydration helper). Dropping them from the INSERT is BLOCKED — the read path depends on them.

**Column-name divergence:**
Migration 0002 uses `model_name`; inline DDL uses `name`; spec §5A.2 uses `name`. The user's reproducer surfaces the mismatch as `OperationalError: no column named name`. Fixing JUST the column name surfaces the next 6 missing columns.

### Implications for ADR-1 fix scope

- **Cannot ship as code-only 1.5.2 patch.** Requires migration 0005 to ADD the 6 inline-DDL data columns to migration 0002's table.
- **Column-name reconciliation needed.** Three options:
  - (A) Migration 0005 renames `model_name` → `name` (matches spec §5A.2 + ModelRegistry code; high blast radius — sibling tables `_kml_aliases` use `model_name` too).
  - (B) Migration 0005 keeps `model_name`; ModelRegistry queries change `WHERE name = ?` → `WHERE model_name = ?` (matches migration; pragmatic; spec amended to acknowledge the SQLite reality).
  - (C) Migration 0005 adds `name` as additional column, keeping `model_name` (backwards-compat layer; doubles the column count; not recommended).
- **Recommended: Option B.** Pragmatic; touches only ModelRegistry code; spec amendment per `rules/specs-authority.md` Rule 5 (spec follows code when code is the canonical reality of an established migration).
- **PK divergence parked for 1.6.0.** Spec PK is UUID `id`; migration PK is `(tenant_id, model_name, version)`. Spec §5A.2 acknowledged as the long-term canonical; 1.5.2 patch ships with migration 0002's PK shape.

### Sweep 14 (spec ml-registry §5A.2 line range claim)

Plan claimed §5A.2 at lines 264-289. Verified: §5A.2 starts at line 264 (`### 5A.2 Postgres DDL`) and the `_kml_model_versions` DDL block runs lines 268-289. Plan citation is accurate.

## Open questions

- **Sweep 15 (ClusteringDiagnostic):** Direct grep for `class\s+(Cluster|Clustering)Diagnostic` returned no matches. There IS a `clustering` engine at `packages/kailash-ml/src/kailash_ml/engines/clustering.py` but no diagnostic adapter class. Confirms GAP 1's open sub-question: `kind="clustering"` route should refuse with "not yet implemented" message, OR a clustering diagnostic class needs to be authored. Defer decision to /todos.
- **Spec §5A.2 vs migration 0002 column-name drift:** is this a known/accepted divergence, or did migration 0002 ship with a typo? `git log --grep='_kml_model_versions'` may reveal the history. Defer to /implement; not a blocker for /todos.

## Net verdict

**ADR-1 requires revision.** Specifically:

1. Migration 0005 mandatory (not "conditional" as plan stated).
2. Column-name reconciliation: Option B (queries → `model_name`, spec amended) recommended.
3. 1.5.2 patch class is correct release classification (regression-class, additive-only column adds via migration 0005 are patch-class), but with migration 0005 included.
4. Spec §5A.2 needs amendment per `rules/specs-authority.md` Rule 5 to acknowledge the migration-canonical column naming.

**ADR-2 and ADR-3 verifications** — both mechanically clean per Sweeps 5, 6, 12; no revision needed.

**Cross-cutting** — sibling diagnostic engines (AlignmentDiagnostics / LLMDiagnostics / AgentDiagnostics) confirmed; cross-package dispatch wiring in ADR-3 is buildable.

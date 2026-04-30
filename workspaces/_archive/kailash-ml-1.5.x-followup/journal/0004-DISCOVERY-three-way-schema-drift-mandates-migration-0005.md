# 0004 — DISCOVERY — Three-Way Schema Drift Mandates Migration 0005

**Type:** DISCOVERY
**Date:** 2026-04-29
**Phase:** /redteam (Round 1, on /analyze output)
**Workstream:** kailash-ml-1.5.x-followup

## What was discovered

The Round-1 mechanical-sweep red team (run by orchestrator after both background agents hit API limits) revealed **three-way schema drift** on `_kml_model_versions`, not the two-way fork the architecture plan described:

| Source                                                        | Column count | Distinguishing columns                                                                                      |
| ------------------------------------------------------------- | ------------ | ----------------------------------------------------------------------------------------------------------- |
| Migration 0002 (on disk for 1.5.0/1.5.1 users)                | 8            | `tenant_id`, `model_name`, `run_id`, `promoted_at`, `archived_at`                                           |
| Inline DDL (`model_registry.py:204-217`, IF-NOT-EXISTS no-op) | 10           | `name` (NOT `model_name`), `metrics_json`, `signature_json`, `onnx_*`, `artifact_path`, `model_uuid`        |
| Spec §5A.2 (canonical Postgres DDL)                           | 15           | `id` UUID PK, `format`, `artifact_uri`, `artifact_sha256`, `lineage_*`, `is_golden`, ONNX-export probe cols |

**Pairwise overlap:**

- 0002 ∩ Inline = `version, stage, created_at` (3 cols)
- 0002 ∩ §5A.2 = `tenant_id, version, created_at` (3 cols; spec uses `name`, migration uses `model_name`)
- Inline ∩ §5A.2 = `name, version, signature_json, created_at` (4 cols)

## Why the original ADR-1 was wrong

The original architecture plan said "delete inline DDL + plumb tenant_id; fix is code-only." This was based on the assumption that the 6 inline-DDL-only columns (`metrics_json`, `signature_json`, `onnx_status`, `onnx_error`, `artifact_path`, `model_uuid`) were write-only — so deleting them would just lose write paths that nothing reads.

**Mechanical sweep at `model_registry.py:148-272` proves the assumption wrong.** All 6 columns are READ by the version-row hydration helper (`row.get("metrics_json", "[]")` at L257, etc.). The read path depends on them. Deleting them from the INSERT would surface as `KeyError`/`None` in every `get_model()` call — same severity as the original bug.

## Implications

1. **Migration 0005 is mandatory** — adds 6 backwards-compatible columns with defaults to migration 0002's table. Reversible via `DROP COLUMN` (destructive; requires `force_downgrade=True` per `rules/schema-migration.md` Rule 7).
2. **Column-name reconciliation needed**. Three options identified by sweep; **Option B chosen**: queries change `name = ?` → `model_name = ?` (matches migration 0002, NOT spec §5A.2). Pragmatic: migration is on-disk-canonical; spec amended per `rules/specs-authority.md` Rule 5 (spec follows code when code is the canonical reality).
3. **Spec §5A.2 amendment** required to acknowledge SQLite/migration-0002 column naming. Per `rules/specs-authority.md` Rule 5b, this triggers full sibling re-derivation across `ml-*.md` (16 specs).
4. **9 spec columns deferred** to 1.6.0/1.7.0 (`id` UUID PK, `format`, `artifact_uri`, `artifact_sha256`, `lineage_*`, `is_golden`, `onnx_unsupported_ops`, `onnx_opset_imports`, `ort_extensions`, `actor_id`). Ship the minimum viable convergence; track full §5A.2 alignment as a sibling workstream.

## Why this matters institutionally

The original ADR claimed "code-only fix" because the analyst grep'd `_kml_model_versions` references in the kailash-ml package and found inline DDL + queries — but DID NOT cross-reference against migration 0002's schema OR against spec §5A.2's canonical column set. Three-way drift is invisible at single-source grep.

**The structural defense** is what `rules/specs-authority.md` Rule 4 and Rule 5b mandate together: every analysis MUST read the canonical spec section AND verify the on-disk migration shape AND check the application code, then triangulate. The codify candidate "spec-vs-code DDL drift detection" (Candidate 2 in `02-plans/03-codify-candidates.md`) is now load-bearing — a `/redteam` mechanical sweep that grep's CREATE TABLE outside `migrations/` directories AND compares column-sets to the canonical spec is the structural defense.

## Codify candidate update

Candidate 2 (Inline DDL outside migrations) is **strengthened**: not just "DDL outside migrations is BLOCKED" but also "every workstream touching a migrated table MUST run a 3-way drift check (spec ↔ migration ↔ application code) at /analyze gate". The mechanical sweep prompt belongs in `skills/16-validation-patterns/` and as a /redteam grep command.

## References

- `02-plans/01-architecture-plan.md` § ADR-1 (revised post-redteam)
- `04-validate/01-redteam-mechanical-sweep.md` (mechanical findings)
- `02-plans/03-codify-candidates.md` § 2 (strengthened)
- `rules/schema-migration.md` Rules 1, 3, 7 (DDL discipline + reversible + force_downgrade)
- `rules/specs-authority.md` Rules 4, 5, 5b (spec authority, first-instance update, sibling re-derivation)

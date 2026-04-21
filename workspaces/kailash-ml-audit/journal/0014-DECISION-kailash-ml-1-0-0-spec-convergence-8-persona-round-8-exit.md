# 0014 DECISION — kailash-ml 1.0.0 spec convergence (8-persona Round 8 exit)

**Type:** DECISION
**Date:** 2026-04-21
**Status:** closed (this session)

## Context

User directive (2026-04-21): "/redteam with a team of experts, developers, users, data scientists to fully re-audit our implementation in kailash-ml and diagnostics across the entire ML/DL/RL lifecycle. Engine-first; seamless to new scientists; benchmark best-in-class; converge specs with NO gaps; no convergence, no continuing ANY work."

Entry state: kailash-ml 0.17.0, patchwork of v1.x primitive APIs (FeatureStore + ModelRegistry + TrainingPipeline + InferenceServer imports at Quick Start), no canonical engine surface, no Kaizen agent-tool-discovery contract, 12 CRITs + ~47 HIGHs across spec surface.

## Decision

Ship kailash-ml 1.0.0 as a 7-package atomic wave release built on a **completely rewritten spec set** produced through an iterative 8-round /redteam convergence:

- **8-persona panel**: cross-spec / closure / newbie-UX / feasibility / industry-parity / TBD-triage / senior-practitioner / spec-compliance
- **4-by-4 batch dispatch** per round to avoid agent rate-limiting
- **Phase-A → Phase-H progression**: spec authoring → DDL completion → cross-spec sweep → dataclass completion → Phase-E meta (README + _index diff) → Phase-F (DDL unification + RegisterResult field shape + kaizen-ml §2.4) → Phase-G (kaizen-ml kml_agent_\* sweep + ClearanceRequirement propagation + DDL-vs-dataclass reconciliation) → Phase-H (2 one-line descriptive fixes)

**Round 8 exit criterion met**: 0 CRIT + 0 HIGH + 0 MED across all 8 personas, 2 consecutive clean rounds (R7 + R8).

Narrowing trajectory (senior-practitioner): A10-3 HIGH (R4) → A11-NEW-1 MED (R5) → A11-NEW-2 MED (R6) → MED-R7-1 MED (R7) → ∅ (R8). Severity monotonically decreasing; scope monotonically narrowing (cross-spec → sibling → within-file MUST → within-file descriptive → terminated).

## 14 User-Approved Decisions (pinned 2026-04-21 "approve all 14")

1. Status vocabulary — `FINISHED` only (hard-migrate SUCCESS/COMPLETED at install, no accept-on-read bridge).
2. GDPR erasure — audit rows IMMUTABLE (sha256:<8hex> fingerprints).
3. Cross-SDK Rust status enum parity — 4-member {RUNNING, FINISHED, FAILED, KILLED} byte-identical.
4. DDP/FSDP/DeepSpeed thread-safety — rank-0-only hardcoded (`torch.distributed.get_rank() == 0`).
5. XPU dual-path — `torch.xpu.is_available()` native + `intel_extension_for_pytorch` fallback.
6. GPU architecture cutoff — `backend-compat-matrix.yaml` as data in `packages/kailash-ml/data/`.
7. GPU CI runner — CPU + MPS BLOCKING now, CUDA BLOCKING when self-hosted lands.
8. Lightning hard lock-in — NO escape hatch, raw loops raise `UnsupportedTrainerError`.
9. Rust `ExperimentTracker` — explicit `start_run()`/`end_run()` (AsyncDrop not stable).
10. Single-spec vs split-spec — single canonical per domain, Rust-specific via `loom/.claude/variants/rs/`.
11. Legacy namespace sunset — at kailash-ml 3.0; 2.x DeprecationWarning; 1.x back-compat shim.
12. Cross-tenant admin export — `MultiTenantOpError` in 1.0.0; PACT-gated post-1.0.
13. Extras naming — hyphens across all 15 drafts.
14. Package version at merge — kailash-ml 1.0.0 MAJOR (SQLiteTrackerBackend deleted, two registries merged, status vocab migration, top-level `km.*` wrappers, mandatory tenant_id + actor_id + audit).

## 21 Specs Promoted

Core 15 at `specs/ml-*.md`:
ml-engines-v2, ml-engines-v2-addendum, ml-backends, ml-diagnostics, ml-tracking, ml-registry, ml-serving, ml-autolog, ml-automl, ml-drift, ml-feature-store, ml-dashboard, ml-rl-core, ml-rl-algorithms, ml-rl-align-unification.

Integrations 6 at `specs/*-ml-integration.md`:
kailash-core-ml-integration, dataflow-ml-integration, nexus-ml-integration, kaizen-ml-integration, align-ml-integration, pact-ml-integration.

Retained: `specs/ml-integration.md` (DEPRECATED, 3.0 sunset).
Deleted: `specs/ml-engines.md` (replaced by ml-engines-v2 + addendum per `rules/specs-authority.md §8` 300-line split rule).

`specs/_index.md` updated to 4 ML sub-sections (Engine Core, Experiment-Registry-Serving, AutoML-Drift-Feature-Dashboard, RL) + NEW ML Integrations section (6 rows) + Legacy row.

## Canonical Artefacts

- Quick Start SHA-256 fingerprint: `c962060cf467cc732df355ec9e1212cfb0d7534a3eed4480b511adad5a9ceb00` (Tier-2 regression test specified at `ml-engines-v2.md §16.3`).
- `packages/kailash-ml/README.md` Quick Start rewritten from 6-import primitive form to 6-line engine-first canonical body.
- DDL prefix unified on `_kml_*` (24 CREATE TABLE statements across 7 specs; 0 bare `kml_*` residuals except user-configurable `table_prefix` config).

## Release Wave

kailash 2.9.0 + kailash-pact 0.10.0 + kailash-nexus 2.2.0 + kailash-kaizen 2.12.0 + kailash-align 0.5.0 + kailash-dataflow 2.1.0 + kailash-ml 1.0.0.

Cross-SDK: kailash-rs#502 parity issue updated with wave context + 14-decision body + cross-SDK overlay path via `loom/.claude/variants/rs/specs/ml-*.md` post `/sync`.

## Convergence evidence

See `workspaces/kailash-ml-audit/04-validate/round-1-SYNTHESIS.md` through `round-8-SYNTHESIS.md`. Full 8-persona reports per round at `round-N-<persona>.md`.

## Consequences

1. `/implement` can now proceed against pinned specs (next phase).
2. 34-wave shard plan (per `rules/autonomous-execution.md` capacity bands) is the implementation vehicle.
3. Any spec edit post-codify MUST trigger full sibling-spec re-derivation per `rules/specs-authority.md §5b`.
4. v1.1 deferrals (explicit, accepted): SystemMetricsCollector, ModelCard generator, cost dashboard, DatasetVersion, inference-time explainability, quantization/pruning/distillation, BYO-judge leaderboard, identity-provider binding.

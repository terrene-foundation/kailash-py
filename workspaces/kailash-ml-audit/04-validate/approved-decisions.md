# Approved Decisions — kailash-ml 1.0.0

**Approved:** 2026-04-21 by user ("approve all 14", at-any-cost framing).
**Scope:** Every spec draft under `workspaces/kailash-ml-audit/specs-draft/` MUST conform.

## Decisions

1. **Status vocabulary** — `FINISHED` only. Hard-migrate existing `SUCCESS` / `COMPLETED` rows to `FINISHED` at 1.0.0 install via numbered migration; drop accept-on-read bridge entirely. Write-only `FINISHED`; read-only `FINISHED`.
2. **GDPR erasure** — Audit rows are IMMUTABLE. Delete run content + artifact content + model content; audit persists with `sha256:<8hex>` fingerprints per `rules/event-payload-classification.md §2`. Never delete an audit row.
3. **Cross-SDK Rust status enum parity** — 4-member enum `{RUNNING, FINISHED, FAILED, KILLED}`. Byte-identical across kailash-py and kailash-rs. No variants. No aliases.
4. **DDP / FSDP / DeepSpeed thread-safety** — MUST clause: autolog + DLDiagnostics emit ONLY when `torch.distributed.get_rank() == 0`. Rank-0-only is hardcoded not configurable. Tier-2 test against mocked distributed cluster required.
5. **XPU path** — Accept both `torch.xpu.is_available()` (torch ≥ 2.5 native) AND `intel_extension_for_pytorch` (ipex fallback). Native-first probe order. No sole-dependency lock-in.
6. **GPU architecture cutoff** — `backend-compat-matrix.yaml` as data in `packages/kailash-ml/data/backend-compat-matrix.yaml`. `km.doctor` subcommand reads it. Update without SDK release.
7. **GPU CI runner policy** — CPU + MPS (macos-14) BLOCKING now. CUDA becomes BLOCKING the day a self-hosted runner lands. Track runner acquisition as explicit infra todo.
8. **Lightning hard lock-in** — NO escape hatch. Lightning is THE training protocol for DL families. Raw training loops raise `UnsupportedTrainerError`. Custom trainers must wrap as `LightningModule` at the engine boundary (`ml-engines-v2 §3.2 MUST 1/2`).
9. **Rust `ExperimentTracker` async contract** — Python: `async with run:` context manager (idiomatic). Rust: explicit `start_run()` / `end_run()` (AsyncDrop not stable). Same observable behavior; different syntactic surface per language idiom.
10. **Single-spec vs split-spec for cross-SDK** — One canonical spec per domain. Rust-specific clauses (when divergent) live in `loom/.claude/variants/rs/specs/ml-*.md` overlay once `/sync` lands. Do NOT pre-split.
11. **Legacy namespace sunset** — Remove at `kailash-ml 3.0`. `kailash-ml 2.x` emits `DeprecationWarning` on legacy-namespace import. `kailash-ml 1.x` keeps back-compat shim.
12. **Cross-tenant admin export** — `MultiTenantOpError` raised in 1.0.0. Ship PACT-gated cross-tenant spec (`ml-registry-pact.md`) post-1.0 under PACT D/T/R clearance.
13. **Extras naming convention** — Hyphens across all 15 drafts. Multi-word: `[rl-offline]`, `[rl-envpool]`, `[rl-distributed]`, `[rl-bridge]`, `[autolog-lightning]`, `[autolog-transformers]`, `[feature-store]`, `[reinforcement-learning]` alias for `[rl]`, `[deep-learning]` alias for `[dl]`. Single-word: `[rl]`, `[dl]`, `[ray]`, `[dask]`, `[grpc]`, `[onnx]`, `[dashboard]`.
14. **Package version at merge** — `kailash-ml 1.0.0` MAJOR. Breaking-change list: SQLiteTrackerBackend deleted, two registries merged (MLEngine.\_kml_engine_versions scaffold deleted), status vocab `COMPLETED`→`FINISHED`, top-level `km.*` convenience wrappers added, mandatory tenant_id + actor_id + audit on every engine. 1.0.0 signals API stability. Migration doc ships in the same PR.

## Propagation mandate

Every Phase-C spec-fix shard MUST sweep ALL 15 drafts for consistency with these 14 decisions. Any deviation = HIGH finding in Round 3.

## Implications summary

- `Version:` header across every `specs-draft/ml-*.md` MUST read `Version: 1.0.0 (draft)`.
- `MLError` hierarchy is canonical: `TrackingError`, `AutologError`, `RLError`, `BackendError`, `DriftMonitorError`, `InferenceServerError`, `ModelRegistryError`, `FeatureStoreError`, `AutoMLError`, `DiagnosticsError`, `DashboardError` all inherit from `MLError`. `MLError(Exception)` lives in `kailash_ml.errors`.
- Cache keyspace `kailash_ml:v1:{tenant_id}:{resource}:{id}` — every spec uses this form for cache/Redis keys. Postgres tables use `_kml_` prefix (leading underscore distinguishes framework-owned internal tables from user-facing tables; all names stay within Postgres 63-char identifier limit). See `ml-tracking.md §6.3` + `rules/dataflow-identifier-safety.md` Rule 2 for the canonical convention; per-spec sweeps in `ml-tracking`, `ml-registry`, `ml-serving`, `ml-feature-store`, `ml-automl`, `ml-diagnostics`, `ml-drift`, `ml-autolog`, and the cross-domain `kaizen-ml-integration §5.2` trace tables all unify on `_kml_*` as of Phase-G (2026-04-21).
- `ExperimentRun` = async-context wrapper; `ExperimentTracker` = engine. All sibling-spec `tracker=` kwargs MUST annotate `Optional[ExperimentRun]` (the user-visible handle), NOT `Optional[ExperimentTracker]`.
- Contextvar accessor: `kailash_ml.tracking.get_current_run() -> Optional[ExperimentRun]`. Internal ContextVar lives at `kailash_ml.tracking.runner._current_run` but public reads go through the helper.
- Default tracker store: `~/.kailash_ml/ml.db` (single canonical path; every spec references this).

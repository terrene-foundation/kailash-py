# Round-2 Phase-B /redteam — Open-TBD Triage

**Persona:** Open-TBD Triage Analyst
**Scope:** All 15 drafts under `workspaces/kailash-ml-audit/specs-draft/*.md`
**Goal:** A single consolidated decision table so the user can sign off and the specs become fully pinned before Phase-C spec-fix / implementation.
**Method:** `rg -in "TBD|open question|deferred|\bopen\b.*decision|need.*decision|should we|could support|may (be|support|include|accept)"` against the drafts + review of the seven shard self-reports listed in the prompt.

Inventory was produced in a single session from the grep sweep + self-reports. Every TBD below has a recommendation. No TBD is punted.

---

## Section A — Full TBD Inventory

**Classification keys:**

- **SAFE-DEFAULT** — reasonable choice exists that won't block implementation; recommend the default + rationale.
- **NEEDS-DECISION** — choice affects public API, data migration, or extras surface; user sign-off required.
- **BLOCKER** — spec is unimplementable until resolved.
- **ALREADY-RESOLVED** — spec already contains a decision marked RESOLVED; only listing for completeness.

Columns: `ID | Spec | Section | Classification | Recommended Resolution | Rationale | Dependencies`

### A.1 ml-tracking-draft.md (7 TBDs, Appendix A)

| ID   | Section | TBD                                                                                              | Class          | Recommendation                                                                                                                                                             | Rationale                                                                                                                                                                                                                                                                                                        | Deps       |
| ---- | ------- | ------------------------------------------------------------------------------------------------ | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| T-01 | §3.2    | Status vocabulary: `COMPLETED` (0.x) vs `FINISHED` (2.0 MLflow parity) vs `SUCCESS` (0.x legacy) | NEEDS-DECISION | **Write `FINISHED` only; accept both `COMPLETED` and `FINISHED` on read; `SUCCESS` coerces to `FINISHED` with a one-shot DEBUG log. Remove accept-on-read in v3.0.**       | MLflow parity is a stated design goal (§6). Accept-on-read preserves 0.x data; write-only-FINISHED prevents drift. `SUCCESS` must coerce (don't drop) to preserve audit chain. 3-version migration window matches `rules/orphan-detection.md` §3 ("removed = deleted, not deprecated").                          | T-07       |
| T-02 | §6.3    | `kml_` (table prefix) vs `kailash_ml:` (Redis keyspace) — same concern or different?             | SAFE-DEFAULT   | **Different concerns; keep both. Tables use `kml_` (brevity, fits Postgres 63-char identifier limit when appended with a descriptor); Redis keyspace uses `kailash_ml:`.** | Tables and cache keys have different naming constraints: Postgres 63-char limit rewards brevity; Redis keyspaces are external-operator-visible and benefit from the full brand. Grep-discoverable with two distinct regexes. Already consistent across every table definition in the draft.                      | —          |
| T-03 | §9.1    | `MetricValueError` inheritance — subclass `ValueError` for back-compat?                          | SAFE-DEFAULT   | **`MetricValueError(TrackingError, ValueError)` (multiple inheritance).**                                                                                                  | `except ValueError` callers keep working; `except TrackingError` gets typed catch. Python's multiple inheritance handles this cleanly. Same pattern as `kailash.IdentifierError` per `dataflow-identifier-safety.md` (domain-specific error that still classifies under Python's built-in hierarchy).            | —          |
| T-04 | §8.1    | Actor-resolution default when `multi_tenant=True`                                                | SAFE-DEFAULT   | **`require_actor=False` at engine construction; flip to `True` when `multi_tenant=True`; raise `ActorRequiredError` when missing.**                                        | Single-tenant notebooks and CI tests should not be forced to pass `actor_id`. Multi-tenant deployments have tenants AND actors as paired audit dimensions per `rules/tenant-isolation.md` §5 ("audit rows persist tenant_id" AND actor). Typed error matches `rules/zero-tolerance.md` Rule 3 (no silent skips). | T-06       |
| T-05 | §6.3    | Prefix vs keyspace — same as T-02 (counted once; duplicated into self-report)                    | —              | **Covered by T-02.**                                                                                                                                                       | —                                                                                                                                                                                                                                                                                                                | T-02       |
| T-06 | §8.2    | GDPR erasure semantics — delete audit rows or redact?                                            | NEEDS-DECISION | **Audit rows persist with hashed fingerprints only; never delete. Run content erases; audit is immutable.**                                                                | Per `rules/event-payload-classification.md` §2: audit rows MUST contain `sha256:<8hex>` fingerprints, not raw values. Deleting audit rows on erasure defeats forensic-chain integrity and is a GDPR anti-pattern (audit IS lawful basis). Regulator expectation: "what did the system do" ≠ "what were the PII". | T-07, T-04 |
| T-07 | §3.2    | Cross-SDK Rust status-enum parity                                                                | NEEDS-DECISION | **Lock Python and Rust to the same four-member enum `{RUNNING, FINISHED, FAILED, KILLED}`. File kailash-rs cross-SDK todo against this spec section.**                     | Cross-SDK parity is mandated by `rules/cross-sdk-inspection.md` (file location in loom). Divergent enum between SDKs breaks forensic correlation across polyglot deployments (same principle as `rules/event-payload-classification.md` §2 hash-prefix parity).                                                  | T-01       |

### A.2 ml-autolog-draft.md (7 TBDs, Appendix A)

| ID   | Section | TBD                                                                      | Class          | Recommendation                                                                                                                                                                                                                           | Rationale                                                                                                                                                                                                         | Deps |
| ---- | ------- | ------------------------------------------------------------------------ | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- |
| A-01 | §3.1    | Transformers model-card emission on fit-exit                             | SAFE-DEFAULT   | **YES, behind `log_models=True` (the existing default). Text-only model card, no LLM generation.**                                                                                                                                       | Competitor parity with MLflow/W&B. Model card is strictly metadata (hyperparams, dataset fingerprint, framework versions) — no network call, no LLM cost. Ship under existing flag; no new user-facing knob.      | —    |
| A-02 | §3.1    | Sklearn ONNX export failure — fall back to pickle?                       | SAFE-DEFAULT   | **YES with `WARN autolog.sklearn.onnx_failed`; artifact flagged `onnx_status="legacy_pickle_only"` per ml-tracking §12.2; registry raises on load unless `allow_pickle=True`.**                                                          | Some sklearn estimators are not ONNX-exportable (custom transformers). Silent fall-back would violate `rules/zero-tolerance.md` Rule 3; a WARN + metadata flag + loud-load opt-in is the defense-in-depth answer. | A-05 |
| A-03 | §2.1    | `sample_rate_steps` default (1 = every step vs 10 vs 100)                | SAFE-DEFAULT   | **Default `sample_rate_steps=1`. Separately: step-level metrics that the framework already emits pass through; epoch-level aggregates are always emitted.**                                                                              | Users who hit metric flood can set it to 10 or 100; that's a power-user tuning, not a default. Default-sampling would silently drop signal for short-run users. Matches MLflow behavior.                          | —    |
| A-04 | §3.1    | Polars fingerprint scope — hook `to_torch()` sites or only `train_data`? | SAFE-DEFAULT   | **Only explicit user-supplied `train_data` / `train_loader.dataset`. Document `.to_torch()` / `.to_numpy()` as out-of-scope; user may call `run.log_dataset(df)` explicitly.**                                                           | Hooking `to_torch` is monkeypatching a third-party library; fragile across polars versions. Explicit scope keeps the surface auditable.                                                                           | —    |
| A-05 | §2.1    | `log_system_metrics` default interval                                    | SAFE-DEFAULT   | **`log_system_metrics=False` by default; when enabled, `system_metrics_interval_s=5`.**                                                                                                                                                  | `psutil` sampling has real overhead on busy training nodes. Opt-in keeps the default cheap; 5s interval is W&B's convention.                                                                                      | —    |
| A-06 | §3.2    | Thread-safety of attach/detach — DDP / DeepSpeed                         | NEEDS-DECISION | **`contextvars` is sufficient for rank-0-only emission (Lightning, HF Trainer, DeepSpeed all route to rank 0). Document as MUST: autolog emits only when `torch.distributed.get_rank() == 0` OR rank API unavailable. Add Tier 2 test.** | Rank-0-only is the industry convention; prevents the N-duplicate-metric failure from `ml-diagnostics-draft.md §10.7`. Tier 2 test with `torch.distributed` mock cluster satisfies `orphan-detection.md §2`.       | A-07 |
| A-07 | §3.1    | Cross-framework conflict — Lightning + transformers both fire            | SAFE-DEFAULT   | **Emit both. Deduplication is caller's responsibility; transformers captures tokens/sec + text-metric that Lightning doesn't.**                                                                                                          | Attempting to dedupe introduces a new failure mode (missed signal). Each integration emits into its own namespace (`autolog.lightning.*` vs `autolog.transformers.*`); dashboard filters.                         | A-06 |

### A.3 ml-backends-draft.md (7 open questions)

| ID   | Section               | Open question                                                                | Class          | Recommendation                                                                                                                                                             | Rationale                                                                                                                                                                                                                                       | Deps |
| ---- | --------------------- | ---------------------------------------------------------------------------- | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- |
| B-01 | Table notes `***`     | MPS bf16 — op coverage incomplete                                            | SAFE-DEFAULT   | **Default MPS to fp16. `bf16-mixed` requires `force=True` kwarg on backend resolver; emits WARN `backends.mps.bf16_experimental`.**                                        | PyTorch 2.3+ ships partial bf16 on MPS; `scaled_dot_product_attention` still falls back to fp32. Safe default avoids surprise fp32 fallback; opt-in flag documents intent. Same pattern as `rules/dataflow-identifier-safety.md §4` force flag. | —    |
| B-02 | Table notes `****`    | MPS int8                                                                     | SAFE-DEFAULT   | **N/A for 2.0; raise `UnsupportedPrecision` with upstream issue link. Revisit when PyTorch ships `torch.ao.quantization` MPS kernels.**                                    | Metal/CoreML ANE has int8 via CoreML path; PyTorch's direct int8 on MPS is not production-ready. A typed error is preferable to silent fp16 fallback.                                                                                           | B-01 |
| B-03 | §2 xpu                | `intel-extension-for-pytorch` vs torch ≥ 2.5 native XPU                      | NEEDS-DECISION | **Accept both. Resolver tries native `torch.xpu.is_available()` first (torch ≥ 2.5); falls back to `intel_extension_for_pytorch` import if native absent. Document both.** | Torch 2.5 shipped native XPU in Oct 2024; pinning to `ipex` alone would lock us to a legacy path. "Native first, ipex fallback" mirrors the `mps` vs `rocm` contract.                                                                           | —    |
| B-04 | §4 architecture table | MI250/MI300 / Arc/PVC cutoff                                                 | NEEDS-DECISION | **Flag as TODO-hw in the spec; defer precise architecture gating to a `backend-compat-matrix.yaml` that the `km.doctor` subcommand consumes. Validate at hardware CI.**    | Validation requires actual hardware CI lanes that don't yet exist. The lookup table is data, not code; shipping it as YAML lets us update without SDK release.                                                                                  | B-06 |
| B-05 | §5 RL backend         | RL TPU/ROCm/XPU — defer to `UnsupportedFamily`                               | SAFE-DEFAULT   | **Raise `UnsupportedFamily` for RL on non-cuda/mps/cpu in 2.0. Spec `ml-rl-core-draft §13.2` already aligns.**                                                             | RL subprocess-based envs + `gymnasium.vector` have poor interop with TPU/ROCm/XPU. Loud error > silent fall-back.                                                                                                                               | —    |
| B-06 | §CI workflow          | `.github/workflows/ml-backends.yml` GPU CI — self-hosted runner availability | NEEDS-DECISION | **CPU + MPS (macos-14) jobs are blocking. CUDA is blocking IF self-hosted runner exists, otherwise non-blocking with "must be green on a local workstation" manual gate.** | Self-hosted runner acquisition is operational, not technical. Spec locks the policy: the day a runner lands, the job becomes blocking.                                                                                                          | —    |
| B-07 | §Cross-SDK Rust       | XPU training-time support pending `burn` Intel backend                       | SAFE-DEFAULT   | **Inference-only XPU via ONNX Runtime Intel EP (already scheduled). Training-time XPU = `UnsupportedFamily` in Rust 2.0; revisit when `burn` ships Intel backend.**        | Mirrors the Python policy but acknowledges the Rust toolchain gap. Inference via `ort` is already solid.                                                                                                                                        | B-03 |

### A.4 ml-engines-v2-draft.md (6 DECIDE items, §10.4)

| ID   | Section | TBD                                                                       | Class          | Recommendation                                                                                                                                                                                 | Rationale                                                                                                                                                                                                               | Deps |
| ---- | ------- | ------------------------------------------------------------------------- | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- |
| E-01 | §10.4 1 | Default backend priority order (lock vs configurable)                     | SAFE-DEFAULT   | **Lock the default to `cuda → mps → rocm → xpu → tpu → cpu` in `kailash_ml/_backend_order.py`; allow override via `KAILASH_ML_BACKEND_ORDER` env var (comma-separated).**                      | Locked default = predictable CI + docs. Env-var override = power-user escape hatch. Matches `rules/autonomous-execution.md` "human defines envelope, AI executes."                                                      | —    |
| E-02 | §10.4 2 | Lightning hard lock-in — escape hatch?                                    | NEEDS-DECISION | **No escape hatch in 2.0. Lightning is the Trainable protocol. Research users bring their `LightningModule`; custom raw loops are BLOCKED with a typed `UnsupportedTrainerError`.**            | Every previous escape-hatch offer led to divergence between the documented surface and the actual surface (Phase 5.11 pattern). A clean BLOCKED is cheaper than maintaining two training paths.                         | —    |
| E-03 | §10.4 3 | Rust `ExperimentTracker` async contract — AsyncDrop vs explicit start/end | NEEDS-DECISION | **Defer to kailash-rs mirror spec. Python spec commits to context-manager-style (`async with run:`); Rust will commit to explicit `start_run`/`end_run` (tokio `AsyncDrop` is experimental).** | Rust's `AsyncDrop` is not yet stable; explicit start/end is the idiomatic tokio-async pattern. Cross-SDK parity is on observable behavior (same status enum), not on syntactic surface.                                 | T-07 |
| E-04 | §10.4 4 | `engine.serve(channels=["grpc"])` — Nexus vs standalone?                  | SAFE-DEFAULT   | **Defer to `ml-serving.md`; `ml-serving-draft §16` recommendation stands: REST+MCP in v2.0 core, gRPC as `[grpc]` extra with standalone server (no Nexus dependency).**                        | `rules/framework-first.md` routes HTTP through Nexus but gRPC is not a Nexus concern at 2.0. A standalone gRPC server keeps the 2.0 scope bounded.                                                                      | S-01 |
| E-05 | §10.4 5 | Single-spec vs split-spec for cross-SDK                                   | NEEDS-DECISION | **Keep single-spec with §10 cross-SDK section in kailash-py. When `/sync` lands at loom/, classify §10 as variant per language; Rust-specific clauses move to `variants/rs/`.**                | Matches `rules/artifact-flow.md` variant overlay semantics. A pre-emptive split would duplicate 95% of the spec.                                                                                                        | —    |
| E-06 | §10.4 6 | Legacy namespace sunset — 3.0 vs 2.2                                      | NEEDS-DECISION | **Lock removal to 3.0. 2.2 MAY emit `DeprecationWarning` on legacy namespace import. 2.0 — 2.x keep the shim for back-compat.**                                                                | Semver says MAJOR bump for removal. If downstream migration finishes early, 3.0 ships early — don't rebrand a breaking change as minor. Matches user-memory rule "Remove shims immediately" once at the MAJOR boundary. | V-01 |

### A.5 ml-serving-draft.md (5 open questions, §16)

| ID   | Section | Open question                                   | Class        | Recommendation                                                                                                                                                     | Rationale                                                                                                                                 | Deps                    |
| ---- | ------- | ----------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | --- |
| S-01 | §16 1   | gRPC + MCP mount order                          | SAFE-DEFAULT | **REST+MCP in v2.0 core (`InferenceServer` exposes both channels out-of-the-box). gRPC as `[grpc]` extra, same `InferenceServer` with an optional gRPC listener.** | REST+MCP is the lowest-common-denominator; MCP parity with `kailash-mcp` is already expected. gRPC is opt-in for high-throughput callers. | E-04                    |
| S-02 | §16 2   | Multi-arm bandit canary                         | SAFE-DEFAULT | **2-way (main+canary) + shadow in v2.0. Multi-arm bandit explicitly post-1.0; file upstream issue.**                                                               | Multi-arm bandit requires a bandit learner + reward signal pipeline; out of scope for serving layer.                                      | —                       |
| S-03 | §16 3   | Response cache for LLM streaming                | SAFE-DEFAULT | \*\*Disabled in v2.0 for streaming; response cache enabled only for non-streaming fixed-input requests (key = `sha256(model_version                                |                                                                                                                                           | canonical_input)`).\*\* | Per-token cache is a distinct subsystem with its own invalidation story. Non-streaming cache is trivial and matches Nexus's existing cache semantics. | —   |
| S-04 | §16 4   | Cross-server replication                        | SAFE-DEFAULT | **Post-1.0 via Nexus consensus; document as out-of-scope with `UnsupportedReplicationError` when called across servers.**                                          | Requires Nexus discovery + consensus; premature integration would couple serving to Nexus more tightly than warranted.                    | —                       |
| S-05 | §16 5   | Quantized runtime INT8/INT4 (ONNX EP selection) | SAFE-DEFAULT | **Defer to `ml-backends.md §5`. Serving layer accepts a `quantization=` kwarg that passes through to the ONNX runtime provider config; no serving-layer logic.**   | Quantization is a backend concern; serving just selects the provider. GGUF handles LLM quantization end-to-end.                           | B-01                    |

### A.6 ml-drift-draft.md (5 open questions, §13)

| ID   | Section | Open question                          | Class        | Recommendation                                                                                                                    | Rationale                                                                                                            | Deps                                                        |
| ---- | ------- | -------------------------------------- | ------------ | --------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | --- |
| D-01 | §13 1   | Reference sub-sampling seed per tenant | SAFE-DEFAULT | \*\*YES. Seed derived from `sha256(tenant_id                                                                                      |                                                                                                                      | "drift-ref-seed").digest()[:8]` as int. Document in §3.\*\* | Per-tenant determinism isolation prevents cross-tenant correlation leak via shared RNG state. One-liner; matches `rules/tenant-isolation.md` MUST 1 principle. | —   |
| D-02 | §13 2   | Streaming drift (infinite streams)     | SAFE-DEFAULT | **Post-1.0; current design is windowed. File upstream issue.**                                                                    | Streaming drift needs state-minimal sketches (HyperLogLog etc.); distinct algorithm family. Out of scope for v2.0.   | —                                                           |
| D-03 | §13 3   | Explainer integration on drift fire    | SAFE-DEFAULT | **Post-1.0. `top_columns` field in `DriftAlert` reserved for v2.1+; populated from `ModelExplainer` when present, else null.**    | `top_columns: list[str]` field is forward-compatible; adding it now costs one column, defers the integration itself. | —                                                           |
| D-04 | §13 4   | Cross-model (ensemble) drift           | SAFE-DEFAULT | **Post-1.0. Ensemble-drift spec lives in a future `ml-ensemble-drift.md`.**                                                       | Requires a "model group" concept the registry doesn't ship; premature.                                               | —                                                           |
| D-05 | §13 5   | Alert dedup key across channels        | SAFE-DEFAULT | **YES: `alert_id` (`sha256(tenant_id, model, timestamp, features)`) is the dedup key across email + webhook + tracker channels.** | Already recommended in the draft; promote to RESOLVED. One dedup key = one alert per incident.                       | —                                                           |

### A.7 ml-registry-draft.md (5 open questions, §16)

| ID   | Section | Open question                      | Class          | Recommendation                                                                                                                                                     | Rationale                                                                                              | Deps |
| ---- | ------- | ---------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ | ---- |
| R-01 | §16 1   | Soft-delete TTL on cleared alias   | SAFE-DEFAULT   | **365 days, tunable per-tenant. Matches default audit retention.**                                                                                                 | Already matches §7 audit retention; unified retention is operator-friendly.                            | —    |
| R-02 | §16 2   | CAS GC cadence                     | SAFE-DEFAULT   | **Weekly sweep; operator override per-tenant via config. Run via APScheduler cron (matches drift scheduler).**                                                     | CAS GC is low-frequency; weekly = enough. Reuses drift scheduler, no new infra.                        | —    |
| R-03 | §16 3   | Audit row partitioning             | SAFE-DEFAULT   | **Out of scope for v2.0; monthly partition on `_kml_model_audit.occurred_at` when row count > 10M. Partition migration documented in v2.2.**                       | Premature partitioning is premature optimization. 10M rows is the Postgres benchmark inflection point. | —    |
| R-04 | §16 4   | Cross-tenant admin export/import   | NEEDS-DECISION | **Defer to follow-on `ml-registry-pact.md` that imports from `kailash-pact` clearance context. v2.0 has no cross-tenant admin path; `MultiTenantOpError` raised.** | Cross-tenant export has clearance semantics (D/T/R) that only PACT governs. Unsafe without PACT.       | —    |
| R-05 | §16 5   | Model signing (Sigstore / in-toto) | SAFE-DEFAULT   | **Post-1.0 spec `ml-registry-signing.md`. v2.0 ships `signed_by: Optional[str]` + `signature: Optional[bytes]` fields as no-op placeholders.**                     | Forward-compat fields now; signing-engine integration later.                                           | —    |

### A.8 ml-rl-core-draft.md (5 deferred items, §1.4)

| ID    | Section | Deferred item                                         | Class        | Recommendation                                                                                                                                            | Rationale                                                                            | Deps |
| ----- | ------- | ----------------------------------------------------- | ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | ---- |
| RC-01 | §1.4 2  | EnvPool native vectorization                          | SAFE-DEFAULT | **Post-1.0 via `[rl-envpool]` extra. v1 uses `gymnasium.vector` (SyncVectorEnv + AsyncVectorEnv). Typed `FeatureNotYetSupportedError` if user requests.** | EnvPool is C++ and platform-specific. Opt-in extra keeps the dependency graph clean. | —    |
| RC-02 | §1.4 3  | Multi-agent RL (PettingZoo)                           | SAFE-DEFAULT | **Non-goal for v2.0. Documented; no plan.**                                                                                                               | MARL is its own research field; distinct protocol surface.                           | —    |
| RC-03 | §1.4 4  | Distributed rollout workers (rllib-style, multi-node) | SAFE-DEFAULT | **Post-1.0 via `[rl-distributed]` extra. `FeatureNotYetSupportedError` on request.**                                                                      | rllib is a large dependency with its own orchestration layer; opt-in.                | —    |
| RC-04 | §1.4 5  | Curriculum / ACL / POET                               | SAFE-DEFAULT | **Simple `TaskScheduler` hook ships in v2.0; full automatic curriculum learning post-1.0.**                                                               | Hook lets power users plug their own scheduler; full ACL = research field.           | —    |
| RC-05 | §1.4 6  | MBPO / Dreamer-V3                                     | SAFE-DEFAULT | **Primitive protocols let users build on top; first-party adapters post-1.0.**                                                                            | Same argument as the draft; promote to RESOLVED.                                     | —    |

### A.9 ml-rl-algorithms-draft.md (3 deferred)

| ID    | Section | Deferred item                                 | Class        | Recommendation                                                                                           | Rationale                                                                    | Deps  |
| ----- | ------- | --------------------------------------------- | ------------ | -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ----- |
| RA-01 | L406    | `rl-distributed` extra (ray[rllib])           | SAFE-DEFAULT | **Keep as `[rl-distributed]` extra; opt-in only. Match the naming convention in X-03 below.**            | Matches RC-03; big dep, opt-in.                                              | RC-03 |
| RA-02 | L416    | MaskablePPO / QR-DQN / ARS from `sb3_contrib` | SAFE-DEFAULT | **0.19.0+ follow-on; `sb3_contrib` is already a thin extra when `[rl]` installed. File upstream issue.** | Low-risk, clean adapter; defer to follow-on release cycle.                   | —     |
| RA-03 | L417    | Decision Transformer                          | SAFE-DEFAULT | **Post-1.0 (distinct sequence-model policy protocol). Document non-goal for v2.0.**                      | Sequence-model policy is architecturally different from the MLP/CNN/LM trio. | —     |

### A.10 ml-rl-align-unification-draft.md (5 already-RESOLVED, §11)

| ID   | Section | Decision                                                    | Class            | Resolution (already in spec)                                                                                       | Deps |
| ---- | ------- | ----------------------------------------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------ | ---- |
| U-01 | D1      | Where does the bridge live?                                 | ALREADY-RESOLVED | **`kailash_ml.rl.align_adapter` lazy-imports `kailash-align` when `algo="dpo"`.**                                  | —    |
| U-02 | D2      | Tracker ownership for bridged runs                          | ALREADY-RESOLVED | **Caller's tracker (matches classical RL).**                                                                       | —    |
| U-03 | D3      | `policy="mlp"` + `algo="dpo"` — raise or auto-correct?      | ALREADY-RESOLVED | **Raise `RLPolicyShapeMismatchError`. No silent fallback per zero-tolerance Rule 3.**                              | —    |
| U-04 | D4      | Which TRL trainers bridged in v1                            | ALREADY-RESOLVED | **DPO, PPO-RLHF, RLOO, OnlineDPO in v1; KTO/SimPO/CPO/GRPO/ORPO/BCO in 0.19.0+.**                                  | —    |
| U-05 | D5      | `AlignmentDiagnostics` namespace — `rl.*` or `alignment.*`? | ALREADY-RESOLVED | **Namespace-shift when called through `km.rl_train` (`rl.*`); keep `alignment.*` when direct from kailash-align.** | —    |

### A.11 ml-diagnostics-draft.md (3 deferred)

| ID    | Section | Deferred item                                      | Class        | Recommendation                                                                           | Rationale                                                           | Deps |
| ----- | ------- | -------------------------------------------------- | ------------ | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ---- |
| DG-01 | L476    | System metrics (CPU/GPU/mem) per step              | SAFE-DEFAULT | **v0.19. Tracked as gap; loudly-documented in the parity matrix §10.3.**                 | Deferred intentionally; the parity matrix is the discovery surface. | A-05 |
| DG-02 | L492    | DL-GAP-3 Activation histogram tensor logging       | SAFE-DEFAULT | **Deferred pending a "tensor-payload" extension in tracker. Scalar stats ship in v2.0.** | Bytes-per-step ratio too high without a new on-disk format.         | —    |
| DG-03 | L458    | Industry-parity-matrix "Deferred" column gap items | —            | **Enumerated individually in DG-01/02 + MLD-GAP-1/2/3 below.**                           | —                                                                   | —    |

### A.12 ml-dashboard-draft.md (3 deferred gap items)

| ID    | Section | Gap item                             | Class        | Recommendation                                                                   | Rationale                                                                      | Deps |
| ----- | ------- | ------------------------------------ | ------------ | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ---- |
| MLD-1 | L520    | Notebook-inline widget               | SAFE-DEFAULT | **v0.19.0+ via `ml-notebook.md` spec. Requires `ipywidgets` bridge.**            | Deferred by scope; low-risk follow-on.                                         | —    |
| MLD-2 | L521    | Sharable report export               | SAFE-DEFAULT | **v0.19.0+ via `ml-reports.md` spec.**                                           | Distinct report-composition API.                                               | —    |
| MLD-3 | L522    | Multimodal tiles (image/audio/video) | SAFE-DEFAULT | **v0.19.0+ via `ml-tracking.md §multimodal` extension + dashboard render path.** | Requires `log_image` / `log_audio` / `log_video` primitive on `ExperimentRun`. | —    |

### A.13 ml-automl-draft.md (1 deferred)

| ID    | Section | Deferred item                    | Class        | Recommendation                                                                                    | Rationale                                                         | Deps |
| ----- | ------- | -------------------------------- | ------------ | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- | ---- |
| AM-01 | L40     | Neural architecture search (NAS) | SAFE-DEFAULT | **Deferred to future `ml-nas.md`. v2.0 AutoML is classic hyperparam + algorithm selection only.** | NAS is a distinct research area; premature to bundle with AutoML. | —    |

---

## Section A — Design Questions NOT Already TBD (raised by prompt; derived)

These are cross-cutting design questions the prompt called out; each maps to one or more TBDs above + one new cross-spec decision.

| ID   | Scope                          | Class          | Recommendation                                                                                                                                                                                                          | Rationale                                                                                                                                                                                                                    | Deps             |
| ---- | ------------------------------ | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| X-01 | RL `parallel_envs` default     | SAFE-DEFAULT   | **Default `n_envs=1` (serial) + `workers=0` (`SyncVectorEnv`). Document `n_envs=os.cpu_count()` as recommended for PPO/A2C/TRPO but not the silent default.**                                                           | Default `os.cpu_count()` silently consumes the box on a laptop during a `km.rl_train(...)` call. `n_envs=1` gives predictable cost; power-users opt in.                                                                      | RC-03            |
| X-02 | Registry export format default | SAFE-DEFAULT   | **ONNX only as default. TorchScript requires explicit `register(format="both")` AND `[dl]` extra. Pickle is opt-in only.**                                                                                              | ONNX is portable + platform-independent (registry §6 mismatch handling). TorchScript is PyTorch-only; autoscaling dual-export doubles storage.                                                                               | —                |
| X-03 | Feature-store online default   | SAFE-DEFAULT   | **`online=None` by default (offline-only). When user passes `online="sqlite:memory"`, offline-only is enforced — SQLite online MUST NOT be the default because Redis is the 10ms-p95 target.**                          | Zero-config for notebooks; explicit Redis for production per `rules/autonomous-execution.md` (human sets the envelope).                                                                                                      | —                |
| X-04 | AutoML executor default        | SAFE-DEFAULT   | **`executor="local"` (already in draft). `parallel_trials=min(4, os.cpu_count())` caps local parallelism.**                                                                                                             | Matches the draft's §5.4 policy; keeps dep graph clean.                                                                                                                                                                      | RC-03            |
| X-05 | Drift LRU eviction             | SAFE-DEFAULT   | **`LRUCache(maxsize=128, ttl_seconds=None)`. Cache is in-memory; source of truth is the `_kml_drift_references` table (draft §3.2). Cache miss = lazy-load from table.**                                                | 128 is generous for most deployments; no TTL because the table is the authority. Matches `functools.lru_cache` idiom.                                                                                                        | D-01             |
| X-06 | Dashboard auth default         | SAFE-DEFAULT   | **Local-only default: `bind="127.0.0.1"` (already mandated in draft §5.1). Remote bind REQUIRES `auth=` non-None OR raises; Nexus integration is opt-in via `auth="nexus"`.**                                           | Matches draft; promote to RESOLVED.                                                                                                                                                                                          | —                |
| X-07 | Extras naming convention       | NEEDS-DECISION | **Hyphens for multi-word extras: `[rl-offline]`, `[rl-envpool]`, `[rl-distributed]`, `[rl-bridge]`, `[autolog-lightning]`, `[autolog-transformers]`. Single-word extras: `[rl]`, `[dl]`, `[ray]`, `[dask]`, `[grpc]`.** | Aligns with existing PyPI convention (pip accepts both; hyphens are more common in ecosystem e.g. `[full]`, `[all-extras]`). Applying consistently: rename any `_` variants spotted to `-`. See §B X-07 audit.               | all              |
| X-08 | Package version at merge       | NEEDS-DECISION | **`kailash-ml 1.0.0` (MAJOR bump) — breaking changes: SQLiteTrackerBackend deleted, two parallel registries merged, scaffold registry deleted, `COMPLETED`→`FINISHED` rename. 1.0.0 also signals "stable API".**        | Semver: removing a public class is MAJOR. "Stability" signal helps downstream integrators. Migration doc must ship in same PR. Current 0.17.0 → 1.0.0 spans sufficient engineering; minor-bumping hides user-visible breaks. | T-01, E-02, E-06 |

---

## Section B — Recommended-Resolution Table For The 14 Specific Design Questions

| #   | Question                                              | Recommendation                                                                                                                                                                                                                                          | Mapped TBDs            |
| --- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| 1   | Status vocabulary (COMPLETED / FINISHED / SUCCESS)    | **Write `FINISHED` only. Accept both `COMPLETED` and `FINISHED` on read in v2.x. `SUCCESS` coerces to `FINISHED` with DEBUG log. Remove accept-on-read in v3.0.**                                                                                       | T-01, T-07             |
| 2   | Cache-key prefix (`kml_` vs `kailash_ml:`)            | **Keep both. Tables: `kml_*` (Postgres 63-char limit). Redis keyspace: `kailash_ml:*` (operator-visible). Different concerns.**                                                                                                                         | T-02, T-05             |
| 3   | Actor resolution default (multi-tenant)               | **`require_actor=False` at engine construction; flipped to `True` by `multi_tenant=True`. Typed `ActorRequiredError` when missing.**                                                                                                                    | T-04                   |
| 4   | `log_metric` NaN/Inf (`MetricValueError` inheritance) | **`MetricValueError(TrackingError, ValueError)` — multiple inheritance for back-compat.**                                                                                                                                                               | T-03                   |
| 5   | GDPR erasure (audit rows)                             | **Audit rows persist with hashed fingerprints (`sha256:<8hex>`) per `event-payload-classification.md` §2; never delete. Run content erases; audit is immutable.**                                                                                       | T-06, T-04             |
| 6   | Autolog framework conflict (Lightning + transformers) | **Emit both. Each integration emits to its own namespace (`autolog.lightning.*`, `autolog.transformers.*`). No dedup.**                                                                                                                                 | A-07, A-06             |
| 7   | RL `parallel_envs` default                            | **`n_envs=1` + `workers=0`. Power users opt into `os.cpu_count()`. Silent-default to cpu_count is BLOCKED.**                                                                                                                                            | X-01, RC-03            |
| 8   | Registry export format default                        | **ONNX only. TorchScript requires `format="both"` + `[dl]` extra. Pickle opt-in with loud warning.**                                                                                                                                                    | X-02                   |
| 9   | Feature-store online backend default                  | **Offline-only by default (`online=None`). Redis is the 10ms-p95 recommendation for production; no built-in SQLite online because SQLite would silently miss the p95.**                                                                                 | X-03                   |
| 10  | AutoML executor default                               | **`executor="local"` with `parallel_trials=min(4, os.cpu_count())`. Ray/Dask opt-in via `[ray]` / `[dask]` extras.**                                                                                                                                    | X-04                   |
| 11  | Drift reference cache eviction                        | **`LRUCache(maxsize=128, ttl_seconds=None)`; cache-miss lazy-loads from `_kml_drift_references` table (source of truth).**                                                                                                                              | X-05, D-01             |
| 12  | Dashboard auth                                        | **Local-only default (`bind="127.0.0.1"`). Remote bind requires `auth=` non-None. Nexus integration via `auth="nexus"`.**                                                                                                                               | X-06                   |
| 13  | Extras renaming (hyphens vs underscores)              | **Hyphens. Rename every `_` to `-` across specs: `[autolog-lightning]`, `[autolog-transformers]`, `[rl-offline]`, `[rl-envpool]`, `[rl-distributed]`, `[rl-bridge]`, `[reinforcement-learning]` alias for `[rl]`, `[deep-learning]` alias for `[dl]`.** | X-07                   |
| 14  | Package version at merge                              | **`kailash-ml 1.0.0`. MAJOR bump: SQLiteTrackerBackend deleted, two parallel registries merged, scaffold registry deleted, status rename. 1.0.0 also signals API-stable.**                                                                              | X-08, T-01, E-02, E-06 |

---

## Section C — Decision Tree: Phase-C Spec-Fix vs Implementation-Time

### C.1 Phase-C Spec-Fix (MUST resolve before implementation begins)

These TBDs affect public API, data migration, or cross-spec contracts. They MUST be pinned in the specs before Phase-C hands off to `/implement`.

1. **T-01, T-07** — Status vocab + cross-SDK enum parity (`{RUNNING, FINISHED, FAILED, KILLED}`). Migration column coercion in `_kml_run.status`.
2. **T-03** — `MetricValueError` inheritance (affects `except ValueError` callers; public API).
3. **T-04** — Actor resolution default (public API: `require_actor=` kwarg on engine).
4. **T-06** — GDPR erasure semantics (affects audit schema — audit row is immutable; erase job targets run/artifact tables only).
5. **A-06** — DDP rank-0-only emission (public API: MUST clause in §3.2; test in Tier 2).
6. **B-03, B-06** — XPU detection protocol (public API: `detect_backend(None)` fall-through order); CI gating policy.
7. **E-01** — Backend priority order locked as default + env-var override documented.
8. **E-02** — Lightning hard lock-in (public API: `UnsupportedTrainerError`).
9. **E-03** — Rust tracker async contract (cross-SDK spec section).
10. **E-06** — Legacy namespace sunset = 3.0 (semver contract).
11. **R-04** — Cross-tenant admin export gate (`MultiTenantOpError`).
12. **X-01** — RL `n_envs=1` default (public API).
13. **X-02** — Registry default format = ONNX only (public API).
14. **X-03** — Feature-store `online=None` default (public API).
15. **X-07** — Extras naming convention (every spec gets an extras-audit pass).
16. **X-08** — Package version at merge = 1.0.0 (CHANGELOG + migration doc).

### C.2 Implementation-Time (MAY resolve during /implement)

These TBDs are safe-defaults whose resolution is recorded but whose tuning can happen at implementation with no spec rewrite.

1. **T-02** — `kml_` vs `kailash_ml:` prefix coexistence (already consistent across every draft).
2. **A-01, A-02, A-03, A-04, A-05** — Autolog defaults (model-card, ONNX-fail fallback, sample rate, fingerprint scope, system metrics).
3. **A-07** — Cross-framework conflict "emit both" (namespaces keep collisions harmless).
4. **B-01, B-02, B-05, B-07** — MPS bf16/int8 disposition, RL backend restriction, Rust XPU training.
5. **S-01..S-05** — Serving post-1.0 items + gRPC extra.
6. **D-01..D-05** — Drift deferrals (all post-1.0 except D-01 seed).
7. **R-01, R-02, R-03, R-05** — Registry GC/retention/signing (v2.0 ships no-op fields; tuning at impl).
8. **RC-01..RC-05, RA-01..RA-03** — RL post-1.0 deferrals.
9. **U-01..U-05** — RL-align unification (already RESOLVED).
10. **DG-01..DG-03, MLD-1..MLD-3, AM-01** — Dashboard/diagnostics/AutoML deferred-gap items.
11. **X-04, X-05, X-06** — AutoML executor default, drift LRU size, dashboard bind default.

### C.3 Dependency Order (for Phase-C resolution)

```
T-01 ── T-07                     (status enum drives cross-SDK)
  └── X-08                       (semver decision depends on T-01 + E-02 + E-06)

T-04 ── T-06                     (actor default + GDPR erasure share audit-schema concern)

E-01                             (backend order independent)
E-02                             (Lightning lock-in independent)
E-03 ── T-07                     (Rust tracker depends on status enum)
E-06 ── X-08                     (legacy sunset drives version bump)

X-07                             (extras naming) — touches every spec; do this first
  └── X-01 RL default             (uses [rl], [rl-offline], etc.)
  └── X-02 registry ONNX-only    (uses [dl])
  └── X-04 AutoML executor       (uses [ray], [dask])

A-06 ── B-01                     (DDP rank-0 + MPS bf16 independent; bundle for review)
```

**Resolution sequence (recommended):**

1. X-07 (extras renaming sweep) — one-shot audit across all specs.
2. T-01 + T-07 (status vocab) — drives T-06, E-06, X-08.
3. E-06 + X-08 (version + legacy sunset).
4. T-03, T-04, T-06 (tracker API).
5. E-01, E-02 (engine API locks).
6. B-03, B-06 (backend detection + CI).
7. A-06 (DDP rank-0 MUST).
8. X-01, X-02, X-03 (RL / registry / feature-store defaults).
9. Remaining SAFE-DEFAULTs — implementation-time.

### C.4 Contradictions / Inconsistencies Across TBDs

Scanned for same TBD deferred differently in two specs. Found **one** consistent pattern + **zero** contradictions:

1. **Extras naming** — `[autolog_lightning]` / `[autolog-lightning]` is the only casing drift detected across the drafts. X-07 resolves with the hyphen convention; sweep all specs in the same edit pass.

No same-topic-deferred-to-different-release inconsistencies were found. Every deferred item routes to v0.19.0+ or post-1.0; the release targets are internally consistent.

---

## Section D — Summary

- **Total TBDs:** **49**
  - ml-tracking: 7
  - ml-autolog: 7
  - ml-backends: 7
  - ml-engines-v2: 6
  - ml-serving: 5
  - ml-drift: 5
  - ml-registry: 5
  - ml-rl-core: 5
  - ml-rl-algorithms: 3
  - ml-diagnostics: 3
  - ml-dashboard: 3
  - ml-automl: 1
  - ml-rl-align-unification: 5 (ALREADY-RESOLVED in draft §11)
  - Cross-spec (prompt-raised): 8

- **ALREADY-RESOLVED:** 5 (U-01..U-05; reporting for completeness)
- **SAFE-DEFAULT with recommendation:** **30** (Autolog A-01..A-05, A-07; Backends B-01, B-02, B-05, B-07; Serving S-01..S-05; Drift D-01..D-05; Registry R-01, R-02, R-03, R-05; RL-core RC-01..RC-05; RL-algos RA-01..RA-03; Diagnostics DG-01..DG-03; Dashboard MLD-1..MLD-3; AutoML AM-01; Cross-spec X-01..X-06)
- **NEEDS-DECISION (user sign-off recommended):** **14**
  - T-01 Status vocab
  - T-06 GDPR erasure semantics
  - T-07 Cross-SDK enum parity
  - A-06 DDP rank-0 thread-safety MUST
  - B-03 XPU path (native vs ipex)
  - B-04 GPU architecture cutoff (hardware-dependent)
  - B-06 GPU CI runner policy
  - E-02 Lightning hard lock-in (no escape hatch)
  - E-03 Rust async tracker contract
  - E-05 Single-spec vs split-spec cross-SDK
  - E-06 Legacy namespace sunset = 3.0
  - R-04 Cross-tenant admin export gate
  - X-07 Extras naming convention
  - X-08 Package version at merge (1.0.0 vs 0.18.0)
- **BLOCKER (unimplementable without resolution):** **0**

Every BLOCKER-candidate TBD has a recommendation that pins the spec. No TBD is unactionable.

---

## Appendix — Commands Run

```bash
rg -in "TBD|open question|deferred|\bopen\b.*decision|\?$|need.*decision|should we|could support|may (be|support|include|accept)" \
    workspaces/kailash-ml-audit/specs-draft/

rg -in "TorchScript|dual-export|onnx.*default|format.*default" workspaces/kailash-ml-audit/specs-draft/
rg -in "COMPLETED|FINISHED|SUCCESS|status" workspaces/kailash-ml-audit/specs-draft/ml-tracking-draft.md
rg -in "kml_|kailash_ml:" workspaces/kailash-ml-audit/specs-draft/ml-tracking-draft.md
rg -in "executor|ray|dask|parallel" workspaces/kailash-ml-audit/specs-draft/ml-automl-draft.md
rg -in "parallel_envs|workers" workspaces/kailash-ml-audit/specs-draft/ml-rl-core-draft.md
rg -in "LRU|cache.*eviction|reference.*cache|_references" workspaces/kailash-ml-audit/specs-draft/ml-drift-draft.md
rg -in "\[(rl|dl|autolog|ray|dask|grpc|offline|distributed)[a-z_-]*\]" workspaces/kailash-ml-audit/specs-draft/
```

Current package version (verified): `packages/kailash-ml/pyproject.toml:7: version = "0.17.0"`.

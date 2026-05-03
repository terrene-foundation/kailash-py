# Spec (draft) — `specs/_index.md` Amendments for Phase-C+D+E ML Spec Promotion

Version: 1.0.0 (draft)
Status: DRAFT — Phase-E sub-shard E3 artifact. Prep-step for /codify gate. The actual promotion of drafts to `specs/` happens at /codify time; this file authors the index-table diff in advance so the /codify agent can drop it in mechanically.
Package: `kailash-ml` (target: 1.0.0).
Purpose: Canonical `_index.md` row additions / replacements for the 15 Phase-C+D+E ML spec drafts once they promote from `workspaces/kailash-ml-audit/specs-draft/ml-*-draft.md` to `specs/ml-*.md`.
Companion specs: all 15 Phase-C+D+E drafts under `workspaces/kailash-ml-audit/specs-draft/ml-*-draft.md`.
Related rule: `rules/specs-authority.md §1` (`_index.md` is the lean lookup table; phases read targeted spec files).

---

## 1. Scope

This file lists every Phase-C+D+E ML draft that will promote to `specs/` at /codify time. Each row follows the existing `specs/_index.md` format (one-line description, domain-tagged) per `rules/specs-authority.md §1`. Format: `| [filename.md](filename.md) | Description |` — two-column, matching the `## ML Lifecycle` section in `specs/_index.md` (see lines 73-79 of the current index for the existing shape).

The current `specs/_index.md` `## ML Lifecycle (2.0 — clean-sheet contracts)` section contains 5 rows (ml-engines, ml-backends, ml-tracking, ml-diagnostics, ml-integration). After promotion, that section grows by 15 new rows (13 new specs + 2 REPLACE for ml-engines → ml-engines-v2 + ml-engines-v2-addendum merged, and ml-tracking → ml-tracking rewritten). The new ML Lifecycle section becomes 18 rows (13 new + 3 retained from the current pre-v2 set + 2 replaced). The new spec set spans four sub-sections: ML Engines 2.0, ML Experiment + Registry + Serving, ML AutoML + Drift + Feature Store + Dashboard, ML Reinforcement Learning.

---

## 2. Proposed Diff (apply at /codify gate)

The diff below assumes the current `specs/_index.md` shape (confirmed by Read at sub-shard E3 authoring time). The diff REPLACES the entire `## ML Lifecycle (2.0 — clean-sheet contracts)` section with the expanded form. Applied via a full-section replace, not line-by-line edit, because the section structure itself changes (one section becomes four sub-sections).

```diff
--- a/specs/_index.md
+++ b/specs/_index.md
-## ML Lifecycle (2.0 — clean-sheet contracts)
-
-| File                                   | Description                                                                                                                           |
-| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
-| [ml-engines.md](ml-engines.md)         | **MLEngine single-point Engine contract**, `Trainable` protocol, `TrainingResult`, multi-tenancy, ONNX-default, migration shim (v2.0) |
-| [ml-backends.md](ml-backends.md)       | **6 first-class backends** (cpu/cuda/mps/rocm/xpu/tpu), `detect_backend()`, precision auto, Lightning integration, hardware-gated CI  |
-| [ml-tracking.md](ml-tracking.md)       | **ExperimentTracker/ModelRegistry/ArtifactStore** (MLflow-replacement), async-context, MCP surface, GDPR erasure, MLflow import       |
-| [ml-diagnostics.md](ml-diagnostics.md) | **DLDiagnostics adapter** (cross-SDK Diagnostic Protocol), torch-hook training instrumentation, plotly gated by `[dl]` extra (PR#1)   |
-| [ml-integration.md](ml-integration.md) | (DEPRECATED — superseded by ml-engines/backends/tracking trio above; retained for 1.x legacy-namespace reference until 3.0 cut)       |
+## ML Lifecycle 2.0 — Engine Core
+
+| File                                                     | Description                                                                                                                                                                             |
+| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
+| [ml-engines-v2.md](ml-engines-v2.md)                     | **MLEngine single-point Engine contract (1.0.0)**, 8-method surface, `Trainable` protocol, `TrainingResult` + `DeviceReport`, `km.*` convenience wrappers, canonical README Quick Start |
+| [ml-engines-v2-addendum.md](ml-engines-v2-addendum.md)   | **Engine addendum**: classical-ML surface, scikit-learn / lightgbm / xgboost / catboost trainables, legacy v1 namespace migration, Pydantic-to-DataFrame adapter                         |
+| [ml-backends.md](ml-backends.md)                         | **6 first-class backends** (cpu/cuda/mps/rocm/xpu/tpu), `detect_backend()`, precision auto, Lightning integration, hardware-gated CI matrix                                             |
+| [ml-diagnostics.md](ml-diagnostics.md)                   | **DLDiagnostics adapter** (cross-SDK Diagnostic Protocol), torch-hook training instrumentation, plotly gated by `[dl]` extra (PR#1 of #567)                                             |
+
+## ML Lifecycle 2.0 — Experiment, Registry, Serving
+
+| File                                                     | Description                                                                                                                                                                             |
+| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
+| [ml-tracking.md](ml-tracking.md)                         | **ExperimentTracker** (MLflow-replacement), async-context ambient-run scope, nested runs, auto-logging, GDPR erasure, MLflow import bridge                                              |
+| [ml-registry.md](ml-registry.md)                         | **ModelRegistry** (staging → shadow → production → archived lifecycle), alias resolution, `ArtifactStore` abstraction (LocalFile / CAS sha256), ONNX-default serialisation              |
+| [ml-serving.md](ml-serving.md)                           | **Inference server + ServeHandle**, REST / MCP channels, model-signature input validation, batch mode, Nexus integration, `km.serve()` dispatch                                         |
+| [ml-autolog.md](ml-autolog.md)                           | **Auto-logging contract**: sklearn / lightgbm / PyTorch Lightning / torch training loops, ambient-run detection, metric namespace discipline, non-intrusive patching                    |
+
+## ML Lifecycle 2.0 — AutoML, Drift, Feature Store, Dashboard
+
+| File                                                     | Description                                                                                                                                                                             |
+| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
+| [ml-automl.md](ml-automl.md)                             | **AutoMLEngine** (agent-infused with LLM guardrails), search strategies (grid / random / bayesian / successive-halving), cost budget, human-approval gate, audit trail                  |
+| [ml-drift.md](ml-drift.md)                               | **DriftMonitor** (KS / chi2 / PSI / Jensen-Shannon), reference-vs-current comparison, scheduled monitoring, feature-level + overall drift reports, drift-triggered retraining hooks     |
+| [ml-feature-store.md](ml-feature-store.md)               | **FeatureStore** (polars-native, ConnectionManager-backed), point-in-time queries, schema enforcement, feature versioning, tenant-scoped keys                                           |
+| [ml-dashboard.md](ml-dashboard.md)                       | **MLDashboard** (`kailash-ml-dashboard` CLI + `km.dashboard()` launcher), runs / models / serving visualisation, plotly-based, notebook-friendly background-thread launch               |
+
+## ML Lifecycle 2.0 — Reinforcement Learning
+
+| File                                                           | Description                                                                                                                                                                             |
+| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
+| [ml-rl-core.md](ml-rl-core.md)                                 | **RL core surface**: `RLTrainer`, `EnvironmentRegistry`, `PolicyRegistry`, `km.rl_train()`, Stable-Baselines3 + Gymnasium integration, `[rl]` extra                                     |
+| [ml-rl-algorithms.md](ml-rl-algorithms.md)                     | **RL algorithms catalog**: PPO / SAC / DQN / A2C / TD3 / DDPG baselines, MaskablePPO, Decision Transformer, hyperparameter presets, algorithm-family contracts                          |
+| [ml-rl-align-unification.md](ml-rl-align-unification.md)       | **RL + Alignment unification**: shared trajectory schema, GRPO / RLOO / PPO-LM cross-framework interop, reward-hacking signal, kailash-align <-> kailash-ml.rl bridge                    |
+
+## ML Lifecycle (Legacy)
+
+| File                                     | Description                                                                                                                                    |
+| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
+| [ml-integration.md](ml-integration.md)   | (DEPRECATED — superseded by the ml-engines-v2 / ml-backends / ml-tracking trio above; retained for 1.x legacy-namespace reference until 3.0 cut) |
```

---

## 3. Row-by-Row Authoring Rationale (one-liner per new row)

For sync-reviewer convenience at /codify Gate 1, the rationale for each new row:

### Engine Core (4 rows)

- **ml-engines-v2.md** — replaces `ml-engines.md`; the 1.0.0 engine contract with 8-method surface, `DeviceReport`, `km.*` wrappers, canonical Quick Start (§16 fingerprint contract).
- **ml-engines-v2-addendum.md** — NEW; classical-ML surface + Pydantic adapter + v1 migration; split from engines-v2 per `rules/specs-authority.md §8` (300-line split rule).
- **ml-backends.md** — RETAINED (promoted from draft to production); 6-backend catalog expanded with hardware-gated CI matrix.
- **ml-diagnostics.md** — RETAINED; DLDiagnostics adapter stays in its current position.

### Experiment, Registry, Serving (4 rows)

- **ml-tracking.md** — REPLACED; async-context ambient-run scope + nested runs + auto-logging now canonical.
- **ml-registry.md** — NEW; was embedded in ml-tracking at 1.x, split out for v2 per `rules/specs-authority.md §8`.
- **ml-serving.md** — NEW; split from v1 ml-integration; REST / MCP channels via Nexus.
- **ml-autolog.md** — NEW; per-framework auto-log contract for sklearn / lightgbm / Lightning / torch.

### AutoML, Drift, Feature Store, Dashboard (4 rows)

- **ml-automl.md** — NEW; agent-infused search with guardrails (cost budget, human-approval gate, audit trail).
- **ml-drift.md** — NEW; KS / chi2 / PSI / Jensen-Shannon drift detection + scheduled monitoring.
- **ml-feature-store.md** — NEW; polars-native FeatureStore with ConnectionManager backend, point-in-time queries.
- **ml-dashboard.md** — NEW; `kailash-ml-dashboard` CLI + `km.dashboard()` non-blocking launcher.

### Reinforcement Learning (3 rows)

- **ml-rl-core.md** — NEW; `RLTrainer` + registries + `km.rl_train()` dispatch (Stable-Baselines3 / Gymnasium).
- **ml-rl-algorithms.md** — NEW; algorithm catalog (PPO / SAC / DQN / A2C / TD3 / DDPG / MaskablePPO / DT).
- **ml-rl-align-unification.md** — NEW; kailash-ml.rl <-> kailash-align bridge (GRPO / RLOO / PPO-LM interop).

### Legacy (1 row RETAINED)

- **ml-integration.md** — RETAINED as DEPRECATED; removed at 3.0 per the current deprecation note.

---

## 4. Total Row Count

Current `## ML Lifecycle (2.0 — clean-sheet contracts)` section: **5 rows**.
New ML Lifecycle sub-sections (4 × sub-section + 1 legacy): **16 rows total** split across 5 h2 sections.

Breakdown:

- Engine Core: 4 rows
- Experiment, Registry, Serving: 4 rows
- AutoML, Drift, Feature Store, Dashboard: 4 rows
- Reinforcement Learning: 3 rows
- Legacy: 1 row

Delta: **+11 net rows** in `_index.md`, **+12 new spec files** promoting from drafts (13 drafts total; 1 is an addendum-rename, 2 are retained).

---

## 5. Promotion Mapping (draft → spec filename)

| Draft Filename (workspaces/kailash-ml-audit/specs-draft/) | Promoted Spec Filename (specs/) | Disposition                                             |
| --------------------------------------------------------- | ------------------------------- | ------------------------------------------------------- |
| ml-engines-v2-draft.md                                    | ml-engines-v2.md                | REPLACE `ml-engines.md` (carry-forward the name v2)     |
| ml-engines-v2-addendum-draft.md                           | ml-engines-v2-addendum.md       | NEW                                                     |
| ml-backends-draft.md                                      | ml-backends.md                  | UPDATE in place (existing file rewritten from v2 draft) |
| ml-diagnostics-draft.md                                   | ml-diagnostics.md               | UPDATE in place                                         |
| ml-tracking-draft.md                                      | ml-tracking.md                  | UPDATE in place (v2 rewrite)                            |
| ml-registry-draft.md                                      | ml-registry.md                  | NEW (split from 1.x ml-tracking)                        |
| ml-serving-draft.md                                       | ml-serving.md                   | NEW (split from 1.x ml-integration)                     |
| ml-autolog-draft.md                                       | ml-autolog.md                   | NEW                                                     |
| ml-automl-draft.md                                        | ml-automl.md                    | NEW                                                     |
| ml-drift-draft.md                                         | ml-drift.md                     | NEW                                                     |
| ml-feature-store-draft.md                                 | ml-feature-store.md             | NEW                                                     |
| ml-dashboard-draft.md                                     | ml-dashboard.md                 | NEW                                                     |
| ml-rl-core-draft.md                                       | ml-rl-core.md                   | NEW                                                     |
| ml-rl-algorithms-draft.md                                 | ml-rl-algorithms.md             | NEW                                                     |
| ml-rl-align-unification-draft.md                          | ml-rl-align-unification.md      | NEW                                                     |

`ml-integration.md` is NOT in the draft set — it stays as-is (DEPRECATED retained row).

---

## 6. Format Compliance With `rules/specs-authority.md`

Per `rules/specs-authority.md §1`: "\_index.md is a lean lookup table" with "one-line description". Each proposed row complies:

- One-line description per file (all rows fit on one line; longer descriptions wrap at 180 chars which matches existing `kaizen-observability.md` and `pact-absorb-capabilities.md` rows).
- Domain-tagged via sub-section headers (Engine Core / Experiment / AutoML / RL / Legacy) per existing precedent (Core SDK / DataFlow / Nexus / Kaizen / PACT / Trust Plane / ML Lifecycle / Alignment / MCP / Infrastructure / Security / Runtime Extensions / Reference).
- NO spec bodies in the index (§1 MUST NOT: "\_index.md contains the actual specifications").

---

## 7. Apply-Time Protocol (for /codify agent)

1. Read current `specs/_index.md` at /codify time.
2. Verify the `## ML Lifecycle (2.0 — clean-sheet contracts)` section still matches the pre-diff shape in § 2 above (if drifted, halt and notify).
3. Apply the diff in § 2 as a full-section replace.
4. Verify row-by-row against § 3 rationale and § 5 promotion mapping.
5. Run `ls specs/ml-*.md` and cross-check every row has a matching file on disk after draft promotion.
6. Run `grep -c '^| \[ml-' specs/_index.md` — expected count: 16 (4 + 4 + 4 + 3 + 1).

---

## 8. Non-Scope

- The actual draft → spec promotion (copying `workspaces/kailash-ml-audit/specs-draft/ml-*-draft.md` to `specs/ml-*.md` with the `-draft` suffix stripped and the `Status: DRAFT` header flipped to `Status: AUTHORITATIVE`) is /codify's job, NOT this file's.
- Other non-ML sections of `_index.md` (Core SDK, DataFlow, Nexus, Kaizen, PACT, Trust Plane, Alignment, MCP, Infrastructure, Security, Runtime Extensions, Reference) are OUT OF SCOPE for this amendment — unchanged by Phase-C+D+E.
- This file only covers `_index.md` row additions. Cross-spec references INSIDE other specs (e.g. `kaizen-*.md` referencing `ml-tracking` → `ml-autolog`) are handled by the respective spec-edit PRs, NOT this amendments file.

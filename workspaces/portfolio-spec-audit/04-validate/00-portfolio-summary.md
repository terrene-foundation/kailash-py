# Wave 5 Portfolio Spec Audit — Cross-Shard Summary

**Audited:** 2026-04-26
**Coverage:** 71 of 72 specs across 7 shards (Wave 1: A/B/C; Wave 2: D/E1/F; Wave 3: E2). Diagnostics-catalog covered by W5-E2.
**Base SHA:** `6142ea52` (kailash 2.11.1 main HEAD at audit start)
**Authors:** pattern-expert, dataflow-specialist, nexus-specialist, kaizen-specialist, ml-specialist, align-specialist, pact-specialist (one shard each)

## Executive verdict

The portfolio splits cleanly into compliant and overstated regions. **Compliant:** core SDK + infra (W5-A clean, 0 CRIT/HIGH/MED across 7 specs / 270 assertions), trust + PACT + security + MCP (W5-F clean apart from F-F-32 and CRITs in flight), alignment package (W5-E2 best-in-audit — only 1 HIGH on async/sync consistency). **Overstated specs vs implementation:** DataFlow ML integration (W5-B), Nexus auth + ML integration (W5-C — fixed in PR #637), Kaizen public surface (W5-D — hardcoded models violate `env-models.md`), ML core/RL (W5-E1 — schema divergence + orphan placeholders), and most starkly **ML AutoML + DriftMonitor + FeatureStore + Dashboard** (W5-E2 — 18 HIGH; 8 HIGH alone on AutoML where the 1.0 spec describes capabilities not yet built).

**Net remediation backlog after PR #637 ships:** 36 HIGH + 59 MED + 186 LOW. AutoML and FeatureStore alone account for 13 of 36 HIGHs and warrant a focused Wave 6.5 cycle.

## Severity totals (all 7 shards aggregate)

| Severity      | Total | After PR #637 ships | Notes                                                      |
| ------------- | ----- | ------------------- | ---------------------------------------------------------- |
| CRIT          | 3     | **0**               | All 3 are duplicates of F-C-35 + F-C-10 — fixed in PR #637 |
| HIGH          | 38    | **36**              | F-C-10 + F-C-40 close with PR #637                         |
| MED           | 59    | 59                  | Carried to Wave 6                                          |
| LOW           | 186   | 186                 | Mostly version-stale spec headers — bulk doc cleanup       |
| KNOWN-BLOCKED | 2     | 2                   | Mint dependencies (#599 / #596)                            |

## CRIT findings (3 — all 1 unique)

| ID              | Title                                                                                                           | Status                            |
| --------------- | --------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| F-C-35 = F-F-22 | `api_gateway.py` hardcoded JWT default secret `"api-gateway-secret"` (18 chars, public OSS) — universal forgery | **FIXED** in PR #637 (issue #636) |

## HIGH findings — 36 remaining for Wave 6 after PR #637 ships

Ranked by blast radius:

### Cross-SDK / security (highest blast radius)

| ID                       | Domain              | Title                                                                         | Disposition                       |
| ------------------------ | ------------------- | ----------------------------------------------------------------------------- | --------------------------------- |
| F-C-10 / F-C-40 / F-F-21 | trust + nexus + mcp | JWT iss-claim presence not enforced in `kailash.trust.auth.jwt::JWTValidator` | **FIXED** in PR #637 (issue #635) |

### Public-API divergence (next-highest blast)

| ID      | Domain      | Title                                                                                                                | Wave 6 effort                                  |
| ------- | ----------- | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| F-B-23  | dataflow-ml | `MLTenantRequiredError` vs spec `TenantRequiredError` — `ImportError` for spec-following users                       | 1 shard (rename + alias for back-compat)       |
| F-C-25  | nexus-ml    | `JWTValidator.from_nexus_config()` classmethod absent                                                                | 1 shard (implement or delete from spec)        |
| F-C-26  | nexus-ml    | `nexus.register_service()` / `InferenceServer.as_nexus_service()` absent — code uses `mount_ml_endpoints()` instead  | 1 shard (reconcile API to one path)            |
| F-C-39  | nexus       | Spec/code package naming asymmetry: `kailash_nexus` (spec) vs `nexus` (code) — every cross-package import broken     | 1 shard (decide canonical, update either side) |
| F-D-02  | kaizen      | `CoreAgent` hardcodes `model="gpt-3.5-turbo"` — direct `env-models.md` violation                                     | quick win (env-var lookup, ~10min)             |
| F-D-50  | kaizen      | `GovernedSupervisor` hardcodes `model="claude-sonnet-4-6"` — direct `env-models.md` violation                        | quick win (env-var lookup, ~10min)             |
| F-E1-28 | ml          | Dual `InferenceServer` classes (`engines/inference_server.py` + `serving/server.py`) — orphan-detection §3 violation | 1 shard (delete legacy)                        |
| F-E1-38 | ml-rl       | `RLTrainingResult` does NOT inherit from `TrainingResult`; 8 spec-required fields missing                            | 1 shard (rewrite dataclass)                    |

### Orphan / wiring gaps

| ID      | Domain        | Title                                                                                                                                           | Wave 6 effort                                                   |
| ------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| F-B-05  | dataflow      | `TenantTrustManager` exposed but no production hot-path call site — orphan-detection §1                                                         | 1 shard (wire it OR delete per §3)                              |
| F-B-25  | dataflow-ml   | ML event surface (`emit_train_start/end`, `on_train_start/end`, `ML_TRAIN_*_EVENT`) shipped in `dataflow.ml.__all__` but absent from spec § 1.1 | 1 shard (update spec or strip API)                              |
| F-B-31  | dataflow      | Cross-SDK `dataflow.hash()` parity claim has no byte-vector pinning test — `cross-sdk-inspection.md` §4 violation                               | 1 shard (add ≥3 byte-vector cases from kailash-rs output)       |
| F-D-25  | kaizen-judges | Spec asserts 24 Tier-1 unit tests at `tests/unit/judges/`; directory does NOT exist                                                             | 1 shard (add tests or update spec)                              |
| F-D-55  | kaizen-ml     | `MLAwareAgent` + `km.list_engines()` discovery surface mandated by spec; ZERO production code consumes it — orphan pattern                      | 1 shard (wire BaseAgent tool construction OR delete spec § 2.4) |
| F-E1-01 | ml            | `CatBoostTrainable` adapter absent — spec requires it as first-class non-Torch family                                                           | 1 shard (implement OR remove `[catboost]` extra + spec)         |
| F-E1-09 | ml            | `LineageGraph` placeholder behind `try/except ImportError`; canonical engine module never landed; `km.lineage()` returns hollow data            | 1 shard (implement OR document as deferred)                     |
| F-E1-50 | ml-rl-align   | Shared trajectory schema (`EpisodeRecord` / `TrajectorySchema`) not implemented — closes cited HIGH-1 only on paper                             | 1 shard (implement schema or revise spec)                       |
| F-F-32  | mcp           | `tests/integration/mcp_server/test_elicitation_integration.py` named in spec but absent — orphan-detection §1                                   | quick win (add Tier 2 test)                                     |

### W5-E2 — ML extras + alignment (19 HIGH)

| ID      | Domain       | Title                                                                                               | Wave 6 effort                                                                              |
| ------- | ------------ | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| F-E2-01 | ml-automl    | Two divergent `AutoMLEngine` implementations — choose one                                           | 1 shard (consolidate, delete loser)                                                        |
| F-E2-02 | ml-automl    | `tracker=` kwarg + ambient `km.track()` not in canonical engine                                     | 1 shard (wire ambient context)                                                             |
| F-E2-03 | ml-automl    | BOHB / CMA-ES / ASHA / PBT search strategies absent (only 4/7)                                      | 2 shards (implement OR strip from spec § 4.1)                                              |
| F-E2-04 | ml-automl    | `executor=` kwarg absent — Ray/Dask not wired                                                       | 1 shard (implement OR mark deferred in spec § 5.x)                                         |
| F-E2-05 | ml-automl    | `Ensemble.from_leaderboard()` symbol absent                                                         | 1 shard (implement OR remove spec § 7.x)                                                   |
| F-E2-06 | ml-automl    | 11 typed exceptions absent from `ml.automl.exceptions`                                              | 1 shard (add exception hierarchy)                                                          |
| F-E2-08 | ml-automl    | `MLEngine.fit_auto()` signature absent                                                              | 1 shard (add facade method)                                                                |
| F-E2-09 | ml-automl    | TOKEN-LEVEL backpressure on LLM cost not enforced — only post-hoc cap (spec § 8.3 MUST 2 violation) | 1 shard (token-level pre-cap implementation)                                               |
| F-E2-10 | ml-automl    | Baseline-parallel-with-agent absent (spec § 8.3 MUST 1 violation)                                   | 1 shard (parallel baseline runner)                                                         |
| F-E2-11 | ml-drift     | `drift_type` taxonomy diverges (spec: covariate/concept/prior/label; code: none/moderate/severe)    | 1 shard (semantic alignment — pick canonical)                                              |
| F-E2-13 | ml-drift     | `MLEngine.monitor()` facade absent                                                                  | 1 shard (add facade method)                                                                |
| F-E2-18 | ml-feature   | `FeatureStore` constructor signature divergent (spec URL-based vs implementation DataFlow-bridge)   | 1 shard (reconcile to DataFlow-bridge in spec)                                             |
| F-E2-19 | ml-feature   | Online store / Redis support absent (spec § 2.1 MUST 1 violation)                                   | 1 shard (implement OR strip from spec)                                                     |
| F-E2-20 | ml-feature   | `@feature` decorator absent                                                                         | 1 shard (implement OR strip § 3.1)                                                         |
| F-E2-21 | ml-feature   | `FeatureGroup` class absent                                                                         | 1 shard (implement OR strip § 4.x)                                                         |
| F-E2-22 | ml-feature   | Materialization API absent                                                                          | 1 shard (implement OR strip § 5.x)                                                         |
| F-E2-27 | ml-dashboard | SSE endpoint absent                                                                                 | 1 shard (implement OR strip § 4.x)                                                         |
| F-E2-30 | ml-dashboard | Default `db_url` divergence from canonical `~/.kailash_ml/ml.db` store path                         | quick win (path constant alignment)                                                        |
| F-E2-39 | align        | `AlignmentPipeline.train()` is async; canonical pair `train`/`deploy` async-ness MUST be consistent | 1 shard (verify deploy is also async OR fix per `rules/patterns.md` Paired Public Surface) |

## Notable LOW patterns (recurring across shards)

- **Spec version headers stale** — every dataflow spec (W5-B), every kaizen spec (W5-D), every ml spec (W5-E1) has `**Version:**` claiming an older release than `__version__` actually shipped. Single bulk doc-cleanup PR per package.
- **Spec/code module path drift** — kaizen and ml repeat the same pattern (W5-D + W5-E1).
- **Spec marked DRAFT but lives in `specs/`** — W5-B F-B-22 dataflow-ml-integration; W5-D F-D-51 kaizen-ml-integration. `specs-authority.md` § 5 violation.

## Disposition update needed

- **#599** (`McpGovernanceEnforcer` blocked on mint ISS-17) — W5-F finding F-F-16 confirms `McpGovernanceEnforcer` IS shipped at `packages/kailash-pact/src/pact/mcp/enforcer.py` (512 lines, 5 declared security invariants). Issue may be partially-resolvable; recommend re-triage by `pact-specialist`.

## Wave 6 remediation plan (proposed)

**Quick wins (single session, ≤4 shards parallel):**

1. F-D-02 + F-D-50: hardcoded model removal → kailash-kaizen patch (~30 min)
2. F-F-32: add Tier 2 test for ElicitationSystem (~15 min)
3. F-B-23: rename `MLTenantRequiredError` → `TenantRequiredError` with alias (~20 min)
4. F-E1-28: delete legacy `engines/inference_server.py` (~20 min)
5. Bulk LOW doc-cleanup: spec version headers across dataflow + kaizen + ml + align (~30 min, single PR)

**Architecture work (1 shard each, sequential per package — touch shared invariants):** 6. F-B-05: TenantTrustManager wiring decision (wire or delete) 7. F-B-25: ML event surface — spec update OR strip API 8. F-C-25 + F-C-26: nexus-ml-integration API reconciliation 9. F-C-39: nexus package naming canonicalization 10. F-D-25: kaizen judges Tier 1 test directory 11. F-D-55: MLAwareAgent wiring decision 12. F-E1-01: CatBoostTrainable implementation OR removal 13. F-E1-09: LineageGraph implementation OR explicit deferral 14. F-E1-38: RLTrainingResult schema alignment 15. F-E1-50: trajectory schema implementation

**Cross-SDK invariant tests:** 16. F-B-31: byte-vector pinning for `dataflow.hash()` parity claim

## Wave 6.5 — AutoML / FeatureStore re-spec (proposed separate cycle)

W5-E2 surfaced a structural pattern: the AutoML 1.0 spec and FeatureStore spec both describe capabilities not yet built (8 + 5 = 13 HIGH between them). Rather than implementing-to-spec under Wave 6 pressure, recommend a **spec re-derivation cycle**: `analyst` agent re-reads the implementations, drafts a v2 spec aligned to actual shipped surface, with a clear "deferred" section for genuinely-postponed capabilities (Ray/Dask, online store, BOHB/PBT). Then choose: ship as-is + revise spec, OR implement the gap.

## Outstanding

- **kailash-rs cross-SDK audit** — every finding flagged "cross-SDK" needs sibling check at `esperie/kailash-rs`. Defer to post-Wave-6.

## Origin

Wave 5 launched 2026-04-26 per `briefs/01-wave5-brief.md` after Wave 3 `/redteam` + Wave 4 hotfix bundle landed. Seven shards parallelized in three waves (Wave 1: A/B/C; Wave 2: D/E1/F; Wave 3: E2) per `worktree-isolation.md` Rule 4 cap. PR #637 (kailash 2.11.2 hotfix) addresses all 3 CRITs and 2 HIGHs in flight; remaining 36 HIGHs queue for Wave 6 + 6.5.

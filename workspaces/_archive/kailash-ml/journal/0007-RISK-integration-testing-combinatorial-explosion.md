---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T16:34:00Z
author: agent
session_turn: 3
project: kailash-ml
topic: Integration testing combinatorial explosion across engines, frameworks, and backends
phase: analyze
tags: [ml, testing, integration, combinatorics, risk, ci]
---

# Risk: Integration Testing Matrix Is Combinatorial and No Prioritization Strategy Exists

## Context

The kailash-ml brief specifies a 5-tier testing strategy (Tier 0 through Tier 4) with clear timing budgets per test. However, the strategy does not address the combinatorial explosion created by the intersection of 9 engines, 3 ML frameworks, 3 database backends, and 2 ONNX paths. Without a prioritization strategy, the test suite will either be incomplete (missing critical combinations) or prohibitively slow (testing everything).

## The Risk

### Quantified test dimensions

- 9 engines x 3 ML frameworks (sklearn, LightGBM, PyTorch) = 27 engine-framework combinations
- ~15 engine-to-engine integration points (TrainingPipeline->FeatureStore, InferenceServer->ModelRegistry, DriftMonitor->InferenceServer, etc.)
- 3 DataFlow backends (SQLite, PostgreSQL, in-memory) for persistence tests
- 2 ONNX paths per model type (export + inference validation)
- ~30 model type combinations for ONNX compatibility (per `07-onnx-bridge-feasibility.md`)

### Full matrix estimate

~80 distinct test dimensions. At Tier 3 timing (up to 5 minutes per test), the full matrix takes 6.5 hours. This is too slow for PR-level testing and borderline for nightly runs when factoring in GPU tests (Tier 4).

### The real danger

Without explicit prioritization, developers will write tests for the combinations they happen to think of, leading to:

- Over-testing common paths (sklearn + SQLite) and under-testing critical paths (PyTorch + PostgreSQL + ONNX)
- Gaps in engine-to-engine integration (the DriftMonitor->InferenceServer->ModelRegistry chain may never be tested end-to-end)
- False confidence from high test counts that do not cover the important combinations

## Proposed Mitigation

### Critical path matrix (runs on every PR, <15 minutes)

15-20 combinations covering the core lifecycle on the default backend:

- TrainingPipeline x {sklearn RandomForest, LightGBM, PyTorch MLP} x SQLite
- FeatureStore x polars x SQLite (register, compute, retrieve with point-in-time)
- ModelRegistry x {sklearn, LightGBM} x SQLite (register, promote, ONNX export + validate)
- InferenceServer x {native sklearn, native LightGBM, ONNX runtime} x SQLite
- DriftMonitor x sklearn x SQLite (PSI + KS detection)
- End-to-end chain: train -> register -> serve -> check drift (sklearn + SQLite)

### Full matrix (runs nightly, <2 hours)

All engine-framework combinations on SQLite, plus core engines on PostgreSQL, plus all ONNX export paths.

### GPU matrix (runs weekly, <30 minutes)

PyTorch CUDA training, Lightning distributed, mixed precision.

### What to document

Which combinations are tested at which tier, and which are best-effort. Users deploying on PostgreSQL with PyTorch models need to know their combination is tested nightly, not on every PR.

## Implications

- The testing strategy must be finalized before implementation begins -- test fixtures and helpers will be shared across the matrix
- If the MVP is 5 engines (per RT-R1-07 recommendation), the test matrix drops from ~80 to ~35 dimensions, which is far more manageable
- The DataFlow backend dimension (SQLite vs PostgreSQL) adds the most combinatorial pressure because it affects all engines with persistence

## For Discussion

1. The critical path matrix uses SQLite exclusively. PostgreSQL is relegated to nightly runs. Given that production deployments typically use PostgreSQL, is this acceptable? What class of bugs would be missed by testing only on SQLite in the PR cycle?
2. If the 5-engine MVP (Finding 7) is adopted, the test matrix drops significantly. Does this testing argument strengthen the case for shipping 5 engines in v1.0 instead of 9?
3. ONNX validation (predict on 10 samples, compare native vs ONNX within tolerance) is a Tier 3 test. Should it be promoted to Tier 2 for the "v1 guaranteed" model types (sklearn all, LightGBM, XGBoost, CatBoost, PyTorch feedforward) so that ONNX regressions are caught on every PR?

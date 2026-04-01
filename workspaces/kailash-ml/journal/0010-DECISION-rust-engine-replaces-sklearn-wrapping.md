---
type: DECISION
date: 2026-04-01
created_at: 2026-04-01T14:00:00+08:00
author: human
session_turn: 1
project: kailash-ml
topic: kailash-ml Python package will use Rust engine instead of wrapping scikit-learn
phase: analyze
tags:
  - kailash-ml
  - rust-engine
  - architecture-change
  - scikit-learn
  - pyO3
---

# kailash-ml Will Use the Rust ML Engine, Not Wrap scikit-learn

## Decision

kailash-ml (Python package) will become a PyO3 binding over kailash-ml-rs (the Rust ML compute engine) instead of wrapping scikit-learn/LightGBM/XGBoost/CatBoost as Python dependencies.

## Context

A comprehensive Rust ML compute engine (kailash-ml-rs) is being built in kailash-rs. It reimplements ALL scikit-learn algorithms + LightGBM + XGBoost + CatBoost natively in Rust. The architecture was analyzed (500KB of research), red-teamed (2 rounds to convergence), and approved with 179 implementation todos.

Full analysis: `loom/workspaces/kailash-ml-rs/01-analysis/`
Architecture decisions: `loom/journal/0043-DECISION-kailash-ml-rs-redteam-resolutions.md`

## What Changes

### Before (current plan in this workspace)
- kailash-ml = Python package wrapping scikit-learn, LightGBM, XGBoost, CatBoost
- Dependencies: scikit-learn, lightgbm, xgboost, catboost, torch, numpy, scipy (~500MB-5GB)
- Four-tier install model to manage dependency weight
- Circular dependency between kailash-ml and kailash-kaizen (required kailash-ml-protocols interface package)
- Python-only

### After (when kailash-ml-rs is ready)
- kailash-ml = thin PyO3 binding over kailash-ml-rs (Rust wheel via maturin)
- Dependencies: just the compiled Rust wheel (~50-100MB, zero Python ML deps)
- No install tiers needed — single package, everything included
- No circular dependency — Rust engine has no Python deps, Kaizen integration via MCP tools
- Same engine powers Python + Ruby + WASM + Go + Java bindings

## What Stays the Same

- The Python API surface (fit/predict/transform, Pipeline, etc.)
- The ML engine concepts (ModelRegistry, ExperimentTracker, AutoML, InferenceServer)
- The Kaizen agent integration (ML-aware agents, AutoML with agent infusion)
- The Nexus integration (InferenceServer auto-exposure)

## What to Do When kailash-ml-rs Is Ready

1. **Check kailash-rs milestone progress**: The Rust engine has 16 milestones (179 todos). MVP (V0.1) delivers linear models + preprocessing + Pipeline. V0.2 adds gradient boosting. Check which milestone is complete.

2. **Replace Python sklearn wrappers with PyO3 bindings**: For each algorithm that exists in the Rust engine, replace the Python sklearn wrapper class with a PyO3 binding class. The Rust engine's Milestone 14 (KML-155 to KML-161) builds the PyO3 infrastructure.

3. **Keep kailash-ml-protocols for now**: The thin interface package for Kaizen ↔ ML integration may still be useful for the transition period. Once all ML algorithms are in Rust, the protocols can be simplified.

4. **Update the install story**: Remove scikit-learn, lightgbm, xgboost, catboost from dependencies. The Rust wheel includes everything.

5. **Update the four-tier install model**: No longer needed. Single `pip install kailash-ml` includes all algorithms.

6. **Validate numerical parity**: The Rust engine has a CI pipeline (KML-175) that validates numerical agreement with sklearn. Verify the Python bindings produce identical results.

## Timeline

kailash-ml-rs is in early development (Milestone 0: Foundation). This decision does NOT block current kailash-ml Python work — the current sklearn-wrapping plan can proceed as a TEMPORARY implementation that will be replaced by Rust bindings when ready. However, avoid deep investment in Python-specific ML algorithm code that the Rust engine will supersede.

## What to Avoid Until Rust Engine Is Ready

- Do NOT build complex Python-native ML algorithm implementations (they'll be thrown away)
- Do NOT optimize Python ML performance (Rust will handle this)
- DO build the engine-layer API (ModelRegistry, ExperimentTracker, AutoML orchestration) — these Python-level orchestration patterns will survive the Rust transition
- DO build the Kaizen agent integration (agent-augmented AutoML) — this stays in Python regardless
- DO build the Nexus integration (InferenceServer) — the Rust engine plugs into this

## For Discussion

1. Should the current kailash-ml Python package proceed with sklearn wrapping as a temporary measure (allowing users to start using the API now), or should it wait for the Rust engine (cleaner but slower to ship)?

2. The Rust engine's Python bindings (Milestone 14) are designed to feel natural to data scientists. Should the kailash-ml Python package's current API design be used as the target for the Rust bindings, or should the Rust engine's optimal API drive the Python surface?

3. The circular dependency problem (kailash-ml ↔ kailash-kaizen) was solved by kailash-ml-protocols. With the Rust engine, ML tools are exposed via MCP (not Python imports), potentially eliminating the need for protocols entirely. Should kailash-ml-protocols be kept for backward compatibility or removed?

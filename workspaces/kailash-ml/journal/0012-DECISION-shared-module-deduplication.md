---
type: DECISION
date: 2026-04-01
created_at: 2026-04-01T13:35:00+08:00
author: agent
session_id: session-16
session_turn: 55
project: kailash-ml
topic: Extracted shared constants into _shared.py to eliminate cross-engine duplication
phase: redteam
tags: [architecture, deduplication, maintainability, red-team]
---

# Shared Module Deduplication

## Decision

Created `engines/_shared.py` as the single source of truth for constants and validation functions used across multiple engines. Specifically:

- `NUMERIC_DTYPES` — polars numeric dtype tuple (was in 3 files: data_explorer, feature_engineer, preprocessing)
- `ALLOWED_MODEL_PREFIXES` + `validate_model_class()` — security allowlist (was in 2 files: training_pipeline, ensemble)
- SB3 `_SB3_ALGORITHMS` map — trainer.py now imports from policy_registry.py

## Rationale

Red team H4 finding: 4 duplicated definitions across 7 files. The security allowlist duplication was particularly dangerous — adding a new allowed model prefix (e.g., `catboost.`) would require updating both files independently, risking divergence.

## Alternatives Considered

1. **Leave duplicated** — rejected; security risk from allowlist drift
2. **Put in `_types.py`** — rejected; `_types.py` already has its own duplication problem (defines ModelSpec/EvalSpec that shadow training_pipeline's versions)
3. **Put in `interop.py`** — rejected; interop handles data conversion, not engine constants

## For Discussion

1. Should `_compute_metrics` also be unified? The training_pipeline version accepts metric names as a list while the ensemble version auto-detects from task type — different enough to warrant separate implementations?
2. If `_types.py` is dead code (its dataclasses shadow the training_pipeline versions), should it be removed entirely?

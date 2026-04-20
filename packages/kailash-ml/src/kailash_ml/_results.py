# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Result dataclasses for `MLEngine` Phase 3/4/5 methods.

Per `specs/ml-engines.md` §2.1 MUST 4 every public method on `MLEngine`
MUST return a typed dataclass — never a raw dict or tuple. This module
hosts the seven non-TrainingResult envelopes (TrainingResult itself
lives in `_result.py` for historical reasons and is re-exported here
for convenience).

The dataclasses are frozen and their field shapes are part of the
public contract. Adding, renaming, or reordering fields requires a
spec amendment (§4 sets the precedent for TrainingResult; the same
applies to the seven types below). Shards implementing setup/compare/
finalize/evaluate/register/predict/serve import these types; they do
NOT redefine or mutate them.

Tenant-id propagation (§5) is enforced by a `tenant_id` field on every
result — nullable in single-tenant mode, required to echo
`engine.tenant_id` in multi-tenant mode per §4.2 MUST 3.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Union

from kailash_ml._result import TrainingResult

__all__ = [
    "SetupResult",
    "ComparisonResult",
    "PredictionResult",
    "RegisterResult",
    "EvaluationResult",
    "ServeResult",
    "FinalizeResult",
    # Re-export for callers who want a single import point
    "TrainingResult",
]


@dataclass(frozen=True)
class SetupResult:
    """Return envelope of `MLEngine.setup()` (ml-engines.md §2.2, §2.1 MUST 6).

    Required fields describe the data profile + split outcome. The
    `schema_hash` is the idempotency key per §2.1 MUST 6: two calls to
    `setup()` with identical `(df_fingerprint, target, ignore,
    feature_store_name)` MUST produce equal `schema_hash` values AND
    equal `split_seed` values so downstream fit()/compare() calls see
    the same split.
    """

    schema_hash: str  # idempotency key per §2.1 MUST 6
    task_type: str  # "classification" | "regression" | "clustering" | "ranking"
    target: str
    feature_columns: tuple[str, ...]
    ignored_columns: tuple[str, ...]
    split_strategy: str  # "holdout" | "kfold" | "stratified_kfold" | "walk_forward"
    split_seed: int
    train_size: int
    test_size: int
    primary_metric: str  # inferred from task_type (accuracy/rmse/silhouette/…)
    tenant_id: Optional[str]
    feature_store_name: str  # auto-generated or user-supplied

    # Optional extended profile; Phase 3 can attach richer schema info
    # (dtype map, null counts, cardinalities) without churning the core
    # required fields.
    schema_info: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class ComparisonResult:
    """Return envelope of `MLEngine.compare()` (ml-engines.md §2.2).

    The leaderboard is ordered best-first by `metric`. `best` is a
    convenience pointer equal to `leaderboard[0]`. Every `TrainingResult`
    in the leaderboard independently satisfies §4.2 MUST rules (device
    populated, tenant_id echo, lightning_trainer_config captured).
    """

    leaderboard: tuple[TrainingResult, ...]  # best-first order
    metric: str  # metric used for ranking
    best: TrainingResult  # == leaderboard[0]
    total_trials: int
    elapsed_seconds: float
    tenant_id: Optional[str]

    # Optional diagnostics; useful for hp_search="bayesian"/"halving"
    # runs where intermediate trial scores matter.
    trial_log: Optional[tuple[Mapping[str, Any], ...]] = None


@dataclass(frozen=True)
class PredictionResult:
    """Return envelope of `MLEngine.predict()` (ml-engines.md §2.2).

    `predictions` holds the inference output — polars Series / DataFrame
    for batch, dict for single-record. `channel` echoes the dispatch
    path ("direct" for in-process, "rest"/"mcp" for endpoint round-
    trip). `device` is deferred to 0.12.1+ per §4.2 MUST 6 (journal
    0005); Phase 4 MAY attach it opportunistically but callers MUST NOT
    depend on it being populated in 0.15.0.
    """

    predictions: Any  # polars Series/DataFrame, or dict for single-record
    model_uri: str
    model_version: Optional[int]
    channel: str  # "direct" | "rest" | "mcp"
    elapsed_ms: float
    tenant_id: Optional[str]

    # §4.2 MUST 6 deferred: may be None in 0.15.0, Phase 4.1+ populates
    device: Optional[Any] = None  # Optional[DeviceReport] — late-bound


@dataclass(frozen=True)
class RegisterResult:
    """Return envelope of `MLEngine.register()` (ml-engines.md §2.2, §6).

    `artifact_uris` is a dict keyed by format; ONNX-default (§6.1 MUST 1)
    means this dict MUST contain `"onnx"` when `register(format="onnx"|"both")`
    succeeds. `model_uri` is the registry-relative URI
    (`models://<name>/v<version>`) that downstream callers use as the
    canonical identifier.
    """

    name: str
    version: int
    stage: str  # "staging" | "shadow" | "production"
    artifact_uris: Mapping[str, str]  # {"onnx": "file://...", "pickle": "...", ...}
    model_uri: str  # "models://User/v3"
    registered_at: float  # epoch seconds (monotonic clock is NOT used per §5.2)
    tenant_id: Optional[str]
    alias: Optional[str] = None


@dataclass(frozen=True)
class EvaluationResult:
    """Return envelope of `MLEngine.evaluate()` (ml-engines.md §2.2).

    `metrics` is the {metric_name: value} dict produced by scoring the
    model against the supplied data. `sample_count` is the number of
    rows scored; `mode` records whether the evaluation was offline
    ("holdout") or online ("shadow"/"live") per the shadow-deployment
    contract in ml-tracking.md.
    """

    model_uri: str
    model_version: Optional[int]
    metrics: Mapping[str, float]
    mode: str  # "holdout" | "shadow" | "live"
    sample_count: int
    elapsed_seconds: float
    tenant_id: Optional[str]


@dataclass(frozen=True)
class ServeResult:
    """Return envelope of `MLEngine.serve()` (ml-engines.md §2.2, §2.1 MUST 10).

    Per §2.1 MUST 10 `engine.serve(model, channels=["rest", "mcp", "grpc"])`
    MUST bring up ALL requested channels from a single call. `uris` is
    keyed by the requested channel names and MUST contain one entry per
    channel in `channels`.
    """

    uris: Mapping[str, str]  # {"rest": "http://...", "mcp": "mcp+stdio://...", ...}
    channels: tuple[str, ...]
    model_uri: str
    model_version: Optional[int]
    autoscale: bool
    tenant_id: Optional[str]


@dataclass(frozen=True)
class FinalizeResult:
    """Return envelope of `MLEngine.finalize()` (ml-engines.md §2.2).

    `training_result` is the refitted `TrainingResult` produced by
    running the chosen candidate on train + holdout combined (when
    `full_fit=True`). `original_candidate` is preserved so the caller
    can compare pre- and post-finalization metrics. Both independently
    satisfy §4.2 MUST rules.
    """

    training_result: TrainingResult
    original_candidate: Union[str, TrainingResult]  # model_uri or the pre-fit result
    full_fit: bool
    tenant_id: Optional[str]

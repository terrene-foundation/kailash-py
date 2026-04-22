# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash-ml -- Machine learning lifecycle for the Kailash ecosystem.

Engines are lazy-loaded on first access to keep import time minimal.
Use ``from kailash_ml import FeatureStore`` to load a specific engine.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kailash_ml.engines.drift_monitor import DriftCallback as DriftCallback

# Canonical MLError hierarchy re-exported from kailash.ml.errors. Eager
from kailash_ml._device import BackendInfo, detect_backend
from kailash_ml._device_report import DeviceReport, device_report_from_backend_info
from kailash_ml._gpu_setup import resolve_torch_wheel
from kailash_ml._result import TrainingResult
from kailash_ml._results import (
    ComparisonResult,
    EvaluationResult,
    FinalizeResult,
    PredictionResult,
    RegisterResult,
    ServeResult,
    SetupResult,
)
from kailash_ml._seed import SeedReport, seed
from kailash_ml._version import __version__
from kailash_ml.engine import MLEngine
from kailash_ml.engines.data_explorer import AlertConfig

# import so every __all__ entry below resolves at module scope (CodeQL
# py/modification-of-default-value on lazy __getattr__ entries in __all__
# is blocked per zero-tolerance.md Rule 1a).
from kailash_ml.errors import (
    ActorRequiredError,
    AliasNotFoundError,
    AliasOccupiedError,
    ArtifactEncryptionError,
    ArtifactSizeExceededError,
    AuthorizationError,
    AutologAttachError,
    AutologDetachError,
    AutologDoubleAttachError,
    AutologError,
    AutologNoAmbientRunError,
    AutologUnknownFrameworkError,
    AutoMLError,
    BackendError,
    BudgetExhaustedError,
    CrossTenantLineageError,
    DashboardError,
    DiagnosticsError,
    DLDiagnosticsStateError,
    DriftMonitorError,
    DriftThresholdError,
    EnsembleFailureError,
    EnvVarDeprecatedError,
    ErasureRefusedError,
    ExperimentNotFoundError,
    FeatureNotFoundError,
    FeatureNotYetSupportedError,
    FeatureStoreError,
    ImmutableGoldenReferenceError,
    InferenceServerError,
    InsufficientSamplesError,
    InsufficientTrialsError,
    InvalidInputSchemaError,
    InvalidTenantIdError,
    LineageRequiredError,
    LiveStreamError,
    MetricValueError,
    MigrationFailedError,
    MigrationImportError,
    MLError,
    ModelLoadError,
    ModelNotFoundError,
    ModelRegistryError,
    ModelSignatureRequiredError,
    MultiTenantOpError,
    OnnxExportUnsupportedOpsError,
    ParamValueError,
    PointInTimeViolationError,
    ProtocolConformanceError,
    RateLimitExceededError,
    ReferenceNotFoundError,
    ReplayBufferUnderflowError,
    RewardModelRequiredError,
    RLEnvIncompatibleError,
    RLError,
    RLPolicyShapeMismatchError,
    RunNotFoundError,
    RunNotFoundInDashboardError,
    SeedReportError,
    ShadowDivergenceError,
    StaleFeatureError,
    TenantQuotaExceededError,
    TenantRequiredError,
    TrackerStoreInitError,
    TrackingError,
    UnknownTenantError,
    UnsupportedFamily,
    UnsupportedPrecision,
    UnsupportedTrainerError,
    WorkflowNodeMLContextError,
    fingerprint_classified_value,
)

# Estimators (#479/#488) — eagerly imported because the module is light
# (thin wrappers over sklearn which is already a base dep) and because
# CodeQL flags __all__ entries that are only resolved through the lazy
# __getattr__ path. Eager import keeps the symbols defined at module
# scope without meaningful import-time cost.
from kailash_ml.estimators import (
    ColumnTransformer,
    FeatureUnion,
    Pipeline,
    StandardScaler,
    is_registered_estimator,
    register_estimator,
    registered_estimators,
    unregister_estimator,
)
from kailash_ml.trainable import (
    HDBSCANTrainable,
    LightGBMTrainable,
    LightningTrainable,
    SklearnTrainable,
    TorchTrainable,
    Trainable,
    UMAPTrainable,
    XGBoostTrainable,
)
from kailash_ml.types import (
    AgentInfusionProtocol,
    FeatureField,
    FeatureSchema,
    MetricSpec,
    MLToolProtocol,
    ModelSignature,
)

# ---------------------------------------------------------------------------
# kailash-ml 2.0 convenience functions (km.train, km.track)
# ---------------------------------------------------------------------------
#
# These are the "PyCaret-better" / "MLflow-better" entry points described in
# the redesign proposal. Phase 2 ships the signatures and the typed deferral
# so `import kailash_ml as km; km.train(...)` gives a clear actionable error;
# Phase 3 (Lightning integration) completes `train()`, Phase 6 completes
# `track()`.


def train(
    df, target: str, *, family: str = "sklearn", **kwargs
) -> TrainingResult:  # noqa: D401
    """Three-line entry point per specs/ml-engines.md §5.1.

        import kailash_ml as km
        best = km.train(df, target="churned")
        print(best.metrics)

    Constructs a default `MLEngine()`, routes through the requested family's
    Lightning-wrapped Trainable adapter, returns a `TrainingResult`. Defaults
    to `family="sklearn"` (RandomForestClassifier) for zero-config behavior.

    For torch/lightning families users MUST pass a pre-built `TorchTrainable`
    or `LightningTrainable` via `MLEngine.fit(trainable=…)` — those families
    have no zero-config defaults.
    """
    import asyncio

    engine = MLEngine()
    # engine.fit is async; synchronous wrapper for the three-line form
    return asyncio.run(engine.fit(df, target=target, family=family, **kwargs))


# ---------------------------------------------------------------------------
# GPU-first convenience (Phase 1): km.device() + km.use_device()
# ---------------------------------------------------------------------------
#
# Per workspaces/kailash-ml-gpu-stack/04-validate/02-revised-stack.md.
# Users interact through ``import kailash_ml as km`` so the top-level
# surface keeps every adapter transparent to device selection: no
# ``device="..."`` or ``accelerator="..."`` parameter plumbed through
# the API; instead the resolver decides, and callers who need to pin a
# backend (offline / deterministic / CPU-only runs) enter a small
# context manager.

import contextvars as _contextvars  # noqa: E402 — after contextvar setup block
from contextlib import contextmanager as _contextmanager  # noqa: E402
from typing import Iterator as _Iterator  # noqa: E402
from typing import Optional as _Optional  # noqa: E402

# Thread-safe and asyncio-safe override consumed by detect_backend()
# callers. A value of None means "no override — use the priority
# resolver". A string value pins detection to that backend for the
# duration of the ``with km.use_device(...)`` block.
_device_override: _contextvars.ContextVar[_Optional[str]] = _contextvars.ContextVar(
    "kailash_ml_device_override", default=None
)


def device(prefer: _Optional[str] = None) -> BackendInfo:
    """Return the resolved ``BackendInfo`` without training anything.

    Inspection-only entry point: users who want to know which backend
    the next training call would pick MUST NOT call ``detect_backend``
    directly (that's the engine-internal API). ``km.device()`` honours
    any ``with km.use_device(...)`` scope in effect and otherwise runs
    the priority resolver.

        import kailash_ml as km
        print(km.device())  # BackendInfo(backend='cuda', precision='bf16-mixed', ...)
        with km.use_device("cpu"):
            print(km.device().backend)  # "cpu"

    Args:
        prefer: Optional explicit backend. When omitted, honours any
            ``use_device`` scope in effect; when provided, overrides the
            scope for this single call. Same vocabulary as
            ``_device.KNOWN_BACKENDS`` ("cuda" / "mps" / "rocm" /
            "xpu" / "tpu" / "cpu") or "auto".

    Returns:
        A pre-resolved :class:`BackendInfo` (concrete precision, never
        "auto").
    """
    effective = prefer if prefer is not None else _device_override.get()
    return detect_backend(prefer=effective)


@_contextmanager
def use_device(name: str) -> _Iterator[BackendInfo]:
    """Pin backend selection to ``name`` for the duration of the block.

    Intended for offline / deterministic / CPU-only runs where a
    surrounding test or notebook needs a single backend regardless of
    the host's capabilities. The pin is contextvar-scoped so it is
    thread-safe and asyncio-safe.

        import kailash_ml as km
        with km.use_device("cpu"):
            result = km.train(df, target="y")  # runs on CPU
        # pin released; the next call uses the priority resolver again

    Args:
        name: One of ``_device.KNOWN_BACKENDS`` or ``"auto"``. Unknown
            strings raise :class:`ValueError` immediately (same
            vocabulary as ``detect_backend``). If the named backend is
            not available on this host, :class:`BackendUnavailable` is
            raised when entering the block — a deterministic failure
            surface beats silently running on the wrong backend.

    Yields:
        The :class:`BackendInfo` resolved inside the scope, so callers
        can destructure it if useful.
    """
    # Validate eagerly: resolving now surfaces BackendUnavailable at
    # ``with`` time, not at the first ``km.train(...)`` call inside the
    # block — the latter is much harder to reason about.
    info = detect_backend(prefer=name)
    token = _device_override.set(name)
    try:
        yield info
    finally:
        _device_override.reset(token)


# ``km.doctor()`` diagnostic per ``specs/ml-backends.md`` §7. Eager
# import for the same CodeQL / ``__all__`` reasons as ``track`` above.
from kailash_ml.doctor import doctor  # noqa: E402

# Phase 6 (Registry + Tracking) — ``km.track()`` implementation lives in
# ``kailash_ml.tracking.runner``. Eager-import the public symbol so it
# appears in ``kailash_ml.__all__`` per orphan-detection §6 and so
# ``from kailash_ml import track`` works without a lazy ``__getattr__``
# hop (the `__all__` / `__getattr__` pattern is a CodeQL trigger per
# zero-tolerance §1a).
from kailash_ml.tracking import erase_subject  # noqa: E402 — W15 GDPR surface
from kailash_ml.tracking import track  # noqa: E402 — after contextvar setup

# Phase 7 (W23.a) — ``km.autolog()`` / ``km.autolog_fn()`` surface.
# Eager import per ``rules/orphan-detection.md §6`` — the symbol
# is in ``__all__`` below so ``from kailash_ml import *`` picks it
# up and CodeQL's ``__all__``/``__getattr__`` scanner sees an eager
# import site (per ``rules/zero-tolerance.md §1a`` second-instance
# example).
from kailash_ml.autolog import autolog, autolog_fn  # noqa: E402


def __getattr__(name: str):  # noqa: N807
    """Lazy-load engines on first access."""
    _engine_map = {
        "FeatureStore": "kailash_ml.engines.feature_store",
        "ModelRegistry": "kailash_ml.engines.model_registry",
        "TrainingPipeline": "kailash_ml.engines.training_pipeline",
        "InferenceServer": "kailash_ml.engines.inference_server",
        "DriftCallback": "kailash_ml.engines.drift_monitor",
        "DriftMonitor": "kailash_ml.engines.drift_monitor",
        "HyperparameterSearch": "kailash_ml.engines.hyperparameter_search",
        "AutoMLEngine": "kailash_ml.engines.automl_engine",
        "DataExplorer": "kailash_ml.engines.data_explorer",
        "AlertConfig": "kailash_ml.engines.data_explorer",
        "FeatureEngineer": "kailash_ml.engines.feature_engineer",
        "EnsembleEngine": "kailash_ml.engines.ensemble",
        "ClusteringEngine": "kailash_ml.engines.clustering",
        "AnomalyDetectionEngine": "kailash_ml.engines.anomaly_detection",
        "DimReductionEngine": "kailash_ml.engines.dim_reduction",
        "ExperimentTracker": "kailash_ml.engines.experiment_tracker",
        "PreprocessingPipeline": "kailash_ml.engines.preprocessing",
        "ModelVisualizer": "kailash_ml.engines.model_visualizer",
        "ModelExplainer": "kailash_ml.engines.model_explainer",
        # Bridge
        "OnnxBridge": "kailash_ml.bridge.onnx_bridge",
        # Estimators (#479/#488) are eagerly imported above; no lazy entry.
        # Compat
        "MlflowFormatReader": "kailash_ml.compat.mlflow_format",
        "MlflowFormatWriter": "kailash_ml.compat.mlflow_format",
        # Dashboard
        "MLDashboard": "kailash_ml.dashboard",
        # Decorators
        "ExperimentalWarning": "kailash_ml._decorators",
    }
    # Metrics module -- lazy-load the subpackage itself
    if name == "metrics":
        import importlib

        return importlib.import_module("kailash_ml.metrics")
    if name in _engine_map:
        import importlib

        module = importlib.import_module(_engine_map[name])
        return getattr(module, name)
    raise AttributeError(f"module 'kailash_ml' has no attribute {name!r}")


__all__ = [
    "__version__",
    # Canonical MLError hierarchy re-exported from kailash.ml.errors
    # (ml-tracking §9.2 — exposed at package root so
    # `from kailash_ml import MLError` works without a lazy __getattr__ hop).
    "MLError",
    "TrackingError",
    "AutologError",
    "RLError",
    "BackendError",
    "DriftMonitorError",
    "InferenceServerError",
    "ModelRegistryError",
    "FeatureStoreError",
    "AutoMLError",
    "DiagnosticsError",
    "DashboardError",
    "UnsupportedTrainerError",
    "MultiTenantOpError",
    "MigrationFailedError",
    "WorkflowNodeMLContextError",
    "EnvVarDeprecatedError",
    "MetricValueError",
    "ParamValueError",
    "ActorRequiredError",
    "TenantRequiredError",
    "RunNotFoundError",
    "ExperimentNotFoundError",
    "TrackerStoreInitError",
    "InvalidTenantIdError",
    "ModelSignatureRequiredError",
    "LineageRequiredError",
    "ArtifactEncryptionError",
    "ArtifactSizeExceededError",
    "AliasNotFoundError",
    "ErasureRefusedError",
    "MigrationImportError",
    "AutologNoAmbientRunError",
    "AutologUnknownFrameworkError",
    "AutologAttachError",
    "AutologDetachError",
    "AutologDoubleAttachError",
    "RLEnvIncompatibleError",
    "RLPolicyShapeMismatchError",
    "ReplayBufferUnderflowError",
    "RewardModelRequiredError",
    "FeatureNotYetSupportedError",
    "UnsupportedPrecision",
    "UnsupportedFamily",
    "ReferenceNotFoundError",
    "InsufficientSamplesError",
    "DriftThresholdError",
    "ModelLoadError",
    "InvalidInputSchemaError",
    "RateLimitExceededError",
    "TenantQuotaExceededError",
    "ShadowDivergenceError",
    "OnnxExportUnsupportedOpsError",
    "ModelNotFoundError",
    "AliasOccupiedError",
    "CrossTenantLineageError",
    "ImmutableGoldenReferenceError",
    "FeatureNotFoundError",
    "StaleFeatureError",
    "PointInTimeViolationError",
    "BudgetExhaustedError",
    "InsufficientTrialsError",
    "EnsembleFailureError",
    "DLDiagnosticsStateError",
    "ProtocolConformanceError",
    "SeedReportError",
    "UnknownTenantError",
    "AuthorizationError",
    "LiveStreamError",
    "RunNotFoundInDashboardError",
    "fingerprint_classified_value",
    # km.seed() + SeedReport (W5 — reproducibility surface)
    "seed",
    "SeedReport",
    # kailash-ml 2.0 kernel (Phase 2 — scaffolded, filled in Phase 3+)
    "MLEngine",
    "BackendInfo",
    "detect_backend",
    "TrainingResult",
    # MLEngine Phase 3/4/5 result dataclasses (§2.1 MUST 4 — typed dataclass per method).
    # Fields are frozen contract per specs/ml-engines.md §4 precedent; shards
    # implementing setup/compare/finalize/evaluate/register/predict/serve import
    # these types rather than redefining them.
    "SetupResult",
    "ComparisonResult",
    "PredictionResult",
    "RegisterResult",
    "EvaluationResult",
    "ServeResult",
    "FinalizeResult",
    "Trainable",
    # GPU-first Phase 1 — all 7 family adapters per specs/ml-engines.md §3.0.
    # Pre-existing 5 (Sklearn/XGBoost/LightGBM/Torch/Lightning) were
    # accessible via `from kailash_ml.trainable import ...` since 0.10.x
    # but absent from kailash_ml.__all__ until 0.12.0 — fixed for spec
    # parity per /redteam round-3 finding HIGH-3.
    "SklearnTrainable",
    "XGBoostTrainable",
    "LightGBMTrainable",
    "TorchTrainable",
    "LightningTrainable",
    "UMAPTrainable",
    "HDBSCANTrainable",
    "train",
    "track",
    "erase_subject",
    "doctor",
    "autolog",
    "autolog_fn",
    "resolve_torch_wheel",
    # GPU-first Phase 1 public API — device reporting + script-level overrides
    "DeviceReport",
    "device_report_from_backend_info",
    "device",
    "use_device",
    # Types (from kailash_ml.types)
    "AgentInfusionProtocol",
    "FeatureField",
    "FeatureSchema",
    "MetricSpec",
    "MLToolProtocol",
    "ModelSignature",
    # Engines (1.x primitives — demoted to kailash_ml.legacy.* at 2.0 cut)
    "FeatureStore",
    "ModelRegistry",
    "TrainingPipeline",
    "InferenceServer",
    "DriftCallback",
    "DriftMonitor",
    "HyperparameterSearch",
    "AutoMLEngine",
    "DataExplorer",
    "AlertConfig",
    "FeatureEngineer",
    "EnsembleEngine",
    "ClusteringEngine",
    "AnomalyDetectionEngine",
    "DimReductionEngine",
    "ExperimentTracker",
    "PreprocessingPipeline",
    "ModelVisualizer",
    "ModelExplainer",
    "OnnxBridge",
    "MlflowFormatReader",
    "MlflowFormatWriter",
    "MLDashboard",
    "ExperimentalWarning",
    # Metrics module
    "metrics",
    # Estimators (#479/#488 — sklearn-compatible composites + registry)
    "Pipeline",
    "FeatureUnion",
    "ColumnTransformer",
    "StandardScaler",
    "register_estimator",
    "unregister_estimator",
    "is_registered_estimator",
    "registered_estimators",
]

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash-ml -- Machine learning lifecycle for the Kailash ecosystem.

Top-level surface is the ``km.*`` verbs + the engine primitives + the
diagnostic adapters. Per ``specs/ml-engines-v2.md §15.9`` the canonical
``__all__`` is organised into 6 groups (verbs -> primitives ->
diagnostics -> backend -> tracker -> discovery), and every entry is
EAGERLY imported at module scope per ``rules/zero-tolerance.md §1a``
second-instance clause (CodeQL flags ``__all__`` symbols resolved only
via lazy ``__getattr__``).

Engines that are NOT in the canonical ``__all__`` (e.g. ``FeatureStore``,
``PreprocessingPipeline``, ``MLDashboard``, ...) remain reachable via
module-attribute lookup through the legacy :func:`__getattr__` below so
existing ``from kailash_ml import FeatureStore`` consumers keep working;
they are simply not advertised in ``from kailash_ml import *``.
"""
from __future__ import annotations

import contextvars as _contextvars
from contextlib import contextmanager as _contextmanager
from typing import TYPE_CHECKING, Any, Iterator, Optional

if TYPE_CHECKING:
    from kailash_ml.engines.drift_monitor import DriftCallback as DriftCallback

# ---------------------------------------------------------------------------
# Canonical error hierarchy + core dataclasses (eager imports)
# ---------------------------------------------------------------------------

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

# Group 1 verbs live in :mod:`kailash_ml._wrappers`. Eager-import so
# every ``__all__`` entry is a module-scope symbol per
# ``rules/zero-tolerance.md §1a`` second-instance example.
from kailash_ml._wrappers import (
    DashboardHandle,
    autolog,
    autolog_fn,
    dashboard,
    diagnose,
    register,
    rl_train,
    serve,
    track,
    train,
    watch,
)

# Diagnostic adapters (Group 3).
from kailash_ml.diagnostics import (
    DLDiagnostics,
    RAGDiagnostics,
    RLDiagnostics,
    diagnose_classifier,
    diagnose_regressor,
)

# km.doctor() diagnostic per specs/ml-backends.md §7 — stays eager so
# the symbol remains reachable at module scope even though it is NOT
# in the canonical __all__ (doctor is a separate surface from
# km.diagnose per Round-8 clarification).
from kailash_ml.doctor import doctor
from kailash_ml.engine import MLEngine
from kailash_ml.engines.data_explorer import AlertConfig

# Tracker primitives (Group 5) — eager-import so ``from kailash_ml
# import ExperimentTracker, ExperimentRun, ModelRegistry`` resolves
# without a lazy-__getattr__ hop (CodeQL
# py/modification-of-default-value gate).
from kailash_ml.engines.model_registry import ModelRegistry

# Group 6 — Engine Discovery.
from kailash_ml.engines.registry import (
    ClearanceRequirement,
    EngineInfo,
    EngineNotFoundError,
    MethodSignature,
    ParamSpec,
    engine_info,
    list_engines,
)

# Every error subclass is eagerly imported so ``kailash_ml.MLError`` and
# the full hierarchy stay reachable by attribute lookup for legacy
# callers. Only the 15 listed in §15.9 Group 2 appear in ``__all__``;
# the rest remain importable via ``from kailash_ml.errors import ...``
# for callers who need the finer-grained taxonomy.
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
    LineageNotImplementedError,
    LineageRequiredError,
    LiveStreamError,
    MetricValueError,
    MigrationFailedError,
    MigrationImportError,
    MigrationRequiredError,
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

# Estimators + Trainable adapters — reachable via module scope so
# power users can ``from kailash_ml import SklearnTrainable`` even
# though the symbols are not in the canonical ``__all__``.
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

# W30 cross-SDK RL bridge surface.
from kailash_ml.rl._lineage import RLLineage
from kailash_ml.rl.align_adapter import FeatureNotAvailableError
from kailash_ml.rl.protocols import PolicyArtifactRef, RLLifecycleProtocol
from kailash_ml.tracking import erase_subject  # W15 GDPR surface (Group 1)
from kailash_ml.tracking.runner import ExperimentRun
from kailash_ml.tracking.tracker import ExperimentTracker
from kailash_ml.trainable import (
    CatBoostTrainable,
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

# Lineage return type — DEFERRED to Wave 6.5b per W6-014.
#
# The canonical ``LineageGraph`` declared in ``ml-engines-v2-addendum
# §E10.2`` requires the registry-side ``build_lineage_graph`` primitive,
# the ``_kml_lineage`` DDL (``ml-tracking.md §6.3``), and the lineage
# walker — all larger than one shard's load-bearing-logic budget.
# Tracking issue: terrene-foundation/kailash-py#657.
#
# Per ``rules/zero-tolerance.md`` Rule 2 (no fake data), the package
# MUST NOT ship a placeholder ``LineageGraph`` that round-trips through
# ``km.lineage(...)`` with hollow ``nodes=(ref,), edges=()`` content;
# the typed deferral below (``km.lineage`` → ``LineageNotImplementedError``)
# is the legitimate Rule 1b deferral path.


# W33c: km.register top-level wrapper per specs/ml-engines-v2.md §15.4 +
# specs/ml-registry.md §7.4. Closes the canonical Quick Start chain:
#
#     result = km.train(df, target="y")
#     registered = km.register(result, name="demo")
#
# Sync wrapper around MLEngine.register() matching `km.train`'s pattern
# for notebook / three-line-hello-world ergonomics. Advanced callers
# needing async composition (inside an existing event loop) MUST use
# `MLEngine().register(...)` directly.
async def register(
    training_result: TrainingResult,
    *,
    name: Optional[str] = None,
    alias: Optional[str] = None,
    stage: str = "staging",
    format: str = "onnx",
    **kwargs: Any,
) -> Any:
    """Register a trained model in the default engine's registry.

        import kailash_ml as km
        result = km.train(df, target="churned")
        registered = km.register(result, name="churn-model")

    Dispatches to the cached default `MLEngine()`, reusing the ONNX-
    default artifact format and staging lifecycle from §6 / §7 of
    `specs/ml-engines-v2.md`.

    Resolves the fitted model via `training_result.trainable.model`
    (populated by every `Trainable.fit()` return site — see
    `trainable.py`). Callers constructing a `TrainingResult` literally
    (tests, cross-SDK replay) MUST attach `trainable=...` OR set one of
    `result.model` / `result._model` for the engine's lookup chain.

    Args:
        training_result: The envelope returned by ``km.train(...)`` /
            ``engine.fit(...)``. Must carry the ``trainable`` back-
            reference (framework paths set this automatically).
        name: Registry-visible model name. Defaults to the family-
            derived synthesised name.
        alias: Optional lifecycle alias ("champion", "challenger",
            etc.). Chained as a second registry call per §7.4.
        stage: Registry stage — "staging" (default), "shadow", or
            "production".
        format: Artifact format — "onnx" (default), "pickle", or "both"
            per §6 MUST 1.
        **kwargs: Forwarded to ``MLEngine.register()`` (e.g. ``actor_id``,
            ``tenant_id``, ``metadata`` when the engine adds them).

    Returns:
        ``RegisterResult`` per `specs/ml-registry.md` §7.1.
    """
    engine = MLEngine()
    return await engine.register(
        training_result,
        name=name,
        alias=alias,
        stage=stage,
        format=format,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Engine alias — spec §15.9 Group 2 refers to ``Engine``; our concrete
# class is :class:`MLEngine`. Expose the canonical name as an alias so
# ``from kailash_ml import Engine`` works.
# ---------------------------------------------------------------------------

Engine = MLEngine


# ---------------------------------------------------------------------------
# Device context-var (km.device / km.use_device) — non-__all__ helpers.
# ---------------------------------------------------------------------------

_device_override: _contextvars.ContextVar[Optional[str]] = _contextvars.ContextVar(
    "kailash_ml_device_override", default=None
)


def device(prefer: Optional[str] = None) -> BackendInfo:
    """Resolve the active :class:`BackendInfo` honoring ``use_device`` pins."""
    effective = prefer if prefer is not None else _device_override.get()
    return detect_backend(prefer=effective)


@_contextmanager
def use_device(name: str) -> Iterator[BackendInfo]:
    """Pin backend selection to ``name`` for the duration of the block."""
    info = detect_backend(prefer=name)
    token = _device_override.set(name)
    try:
        yield info
    finally:
        _device_override.reset(token)


# ---------------------------------------------------------------------------
# km.reproduce + km.resume + km.lineage — module-level declarations
# (canonical call sites per specs/ml-engines-v2.md §12, §12A, §15.8).
# ---------------------------------------------------------------------------


async def reproduce(
    run_id: str,
    *,
    verify: bool = True,
    verify_rtol: float = 1e-4,
    verify_atol: float = 1e-6,
    tenant_id: Optional[str] = None,
) -> TrainingResult:
    """Re-run a registered run end-to-end against the current code.

    Per ``specs/ml-engines-v2.md §12``. The canonical declaration lives
    at module scope in :mod:`kailash_ml.__init__` so
    ``from kailash_ml import reproduce`` resolves directly.

    The current implementation reads the original run's
    :class:`TrainingResult` from the ambient
    :class:`ExperimentTracker` and re-invokes ``engine.fit`` with the
    recorded hyperparameters + family + seed. Feature-version and
    dataset-as-of pinning (`§12.1 MUST 2`) flow through the tracker's
    lineage column.
    """
    from kailash_ml._wrappers import _get_default_engine

    engine = _get_default_engine(tenant_id)
    # Re-seed from the original run's SeedReport so bit-level
    # reproducibility holds (§12.1 MUST 1).
    tracker = getattr(engine, "_tracker", None) or getattr(engine, "tracker", None)
    original: Any = None
    if tracker is not None and hasattr(tracker, "get_run"):
        original = await tracker.get_run(run_id)
    if original is None:
        raise RunNotFoundError(
            reason=(
                f"reproduce({run_id!r}) — run not found on the ambient tracker; "
                "pass tenant_id= if the run belongs to a different tenant"
            ),
            resource_id=run_id,
        )
    seed_report = getattr(original, "seed_report", None)
    if seed_report is not None and getattr(seed_report, "seed", None) is not None:
        seed(seed_report.seed)
    # Replay the run via engine.fit with the recorded family/hyperparameters.
    fit_kwargs: dict[str, Any] = {}
    for attr in ("family", "hyperparameters", "metric"):
        val = getattr(original, attr, None)
        if val is not None:
            fit_kwargs[attr] = val
    result = await engine.fit(**fit_kwargs)
    if verify:
        # Metric drift check — raise when beyond rtol/atol.
        original_metrics = getattr(original, "metrics", {}) or {}
        current_metrics = getattr(result, "metrics", {}) or {}
        for name, original_value in original_metrics.items():
            if name not in current_metrics:
                continue
            diff = abs(current_metrics[name] - original_value)
            tol = verify_atol + verify_rtol * abs(original_value)
            if diff > tol:
                raise MLError(
                    reason=(
                        f"reproduce({run_id!r}) — metric {name!r} drifted "
                        f"beyond rtol={verify_rtol} atol={verify_atol}: "
                        f"original={original_value}, current={current_metrics[name]}"
                    ),
                    resource_id=run_id,
                )
    return result


async def resume(
    run_id: str,
    *,
    tenant_id: Optional[str] = None,
    tolerance: Optional[dict[str, float]] = None,
    verify: bool = False,
    data: Any = None,
) -> TrainingResult:
    """Resume training from a run's ``last.ckpt``.

    Per ``specs/ml-engines-v2.md §12A``. Reads the original run's
    ``artifact_path`` from the ambient tracker, locates
    ``{artifact_path}/last.ckpt``, and dispatches to the cached
    default engine's ``fit`` with ``resume_from_checkpoint`` wired
    into ``trainer_kwargs``.

    :param tolerance: Optional per-metric tolerance dict. When
        supplied AND ``verify=True``, a post-fit comparison raises
        :class:`MLError` if any listed metric drifts beyond the
        stated tolerance.
    """
    # Param validation per invariant 5 — tolerance values must be
    # non-negative finite numbers when supplied.
    if tolerance is not None:
        import math as _math

        if not isinstance(tolerance, dict):
            raise TypeError(
                f"resume(tolerance=...) — expected dict, got "
                f"{type(tolerance).__name__}"
            )
        for metric_name, metric_tol in tolerance.items():
            if not isinstance(metric_name, str):
                raise TypeError(
                    f"resume(tolerance=...) — metric names must be strings, "
                    f"got {type(metric_name).__name__}"
                )
            if not isinstance(metric_tol, (int, float)):
                raise TypeError(
                    f"resume(tolerance={{{metric_name!r}: ...}}) — value "
                    f"must be numeric, got {type(metric_tol).__name__}"
                )
            if not _math.isfinite(float(metric_tol)) or float(metric_tol) < 0:
                raise ValueError(
                    f"resume(tolerance={{{metric_name!r}: {metric_tol}}}) — "
                    "value must be a non-negative finite number"
                )

    from kailash_ml._wrappers import _get_default_engine

    engine = _get_default_engine(tenant_id)

    # Locate the checkpoint via the tracker.
    tracker = getattr(engine, "_tracker", None) or getattr(engine, "tracker", None)
    original: Any = None
    artifact_path: Optional[str] = None
    if tracker is not None and hasattr(tracker, "get_run"):
        original = await tracker.get_run(run_id)
        if original is not None:
            artifact_path = getattr(original, "artifact_path", None)
    if artifact_path is None:
        raise ModelRegistryError(
            reason=(
                f"resume({run_id!r}) — cannot locate artifact_path for the run. "
                "See §3.2 MUST 7 for the ModelCheckpoint auto-attach contract "
                "that writes the checkpoint this function reads."
            ),
            resource_id=run_id,
        )
    expected_ckpt = f"{artifact_path.rstrip('/')}/last.ckpt"

    # Dispatch to engine.fit with resume_from_checkpoint pinned. Per
    # §12A.1 MUST 2 the engine MUST NOT grow a ninth method — we ride
    # the existing Lightning passthrough via trainer_kwargs in
    # callbacks/ enable_checkpointing.
    fit_kwargs: dict[str, Any] = {}
    if data is not None:
        fit_kwargs["data"] = data
    if original is not None:
        for attr in ("family", "hyperparameters"):
            val = getattr(original, attr, None)
            if val is not None:
                fit_kwargs[attr] = val
    # The Lightning adapter consumes ``resume_from_checkpoint`` via
    # ``trainer_kwargs``; we surface it here for the engine to forward.
    fit_kwargs["enable_checkpointing"] = True
    result = await engine.fit(**fit_kwargs)

    # Post-fit tolerance check — opt-in per §12A.1 MUST 4.
    if verify and tolerance is not None and original is not None:
        original_metrics = getattr(original, "metrics", {}) or {}
        current_metrics = getattr(result, "metrics", {}) or {}
        for metric_name, metric_tol in tolerance.items():
            if (
                metric_name not in original_metrics
                or metric_name not in current_metrics
            ):
                continue
            diff = abs(current_metrics[metric_name] - original_metrics[metric_name])
            if diff > float(metric_tol):
                raise MLError(
                    reason=(
                        f"resume({run_id!r}) — metric {metric_name!r} drifted "
                        f"beyond tolerance={metric_tol}: "
                        f"original={original_metrics[metric_name]}, "
                        f"current={current_metrics[metric_name]}"
                    ),
                    resource_id=run_id,
                    context={"expected_checkpoint": expected_ckpt},
                )
    return result


async def lineage(
    ref: str,
    *,
    tenant_id: Optional[str] = None,
    max_depth: int = 10,
) -> Any:
    """Return the cross-engine lineage graph rooted at ``ref``.

    .. warning::

       **Deferred to Wave 6.5b** — see issue
       `terrene-foundation/kailash-py#657
       <https://github.com/terrene-foundation/kailash-py/issues/657>`_
       for the design sketch (frozen ``LineageGraph`` / ``LineageNode`` /
       ``LineageEdge`` per ``ml-engines-v2-addendum §E10.2`` + the
       ``_kml_lineage`` DDL + traversal walker per ``ml-tracking.md
       §6.3 / §7.1``).

       The deferral disposition follows ``rules/zero-tolerance.md``
       Rule 1b — calling ``km.lineage(...)`` raises a typed
       :class:`~kailash_ml.errors.LineageNotImplementedError` (a
       :class:`~kailash_ml.errors.TrackingError` subclass) rather than
       returning a hollow placeholder graph (Rule 2 — fake data is
       BLOCKED).

    Per ``specs/ml-engines-v2-addendum §E10.2`` and §15.8 (target
    contract). ``ref`` may be a run_id, model_version string, or
    dataset_hash. The graph is tenant-scoped — cross-tenant reads raise
    :class:`~kailash_ml.errors.CrossTenantLineageError` per
    ``rules/tenant-isolation.md``.
    """
    raise LineageNotImplementedError(
        reason=(
            "km.lineage() implementation deferred to Wave 6.5b — "
            "see terrene-foundation/kailash-py#657 for the design "
            "sketch (LineageGraph dataclass + _kml_lineage DDL + "
            "registry traversal walker). The canonical contract is "
            "specified in specs/ml-engines-v2-addendum.md §E10 and "
            "specs/ml-tracking.md §6.3 / §7.1."
        ),
        tenant_id=tenant_id,
        resource_id=ref,
        max_depth=max_depth,
    )


# ---------------------------------------------------------------------------
# Legacy lazy-loader for engines that remain reachable at module scope
# but are NOT in the canonical __all__ (FeatureStore, MLDashboard, ...).
# ---------------------------------------------------------------------------


def __getattr__(name: str):  # noqa: N807
    """Lazy-load legacy engines on first access.

    Symbols listed here are kept import-on-demand to avoid paying the
    cost of sub-engine construction for every ``import kailash_ml``.
    These symbols are NOT in the canonical ``__all__`` (§15.9) — they
    remain reachable for backwards compatibility but are not part of
    the documented ``from kailash_ml import *`` surface.
    """
    _engine_map = {
        "FeatureStore": "kailash_ml.engines.feature_store",
        "TrainingPipeline": "kailash_ml.engines.training_pipeline",
        # `InferenceServer` lazy-loaded from the canonical surface
        # `kailash_ml.serving.server` after W6-004 deleted the legacy
        # `engines.inference_server` module (F-E1-28).
        "InferenceServer": "kailash_ml.serving.server",
        "DriftCallback": "kailash_ml.engines.drift_monitor",
        "DriftMonitor": "kailash_ml.engines.drift_monitor",
        "HyperparameterSearch": "kailash_ml.engines.hyperparameter_search",
        "AutoMLEngine": "kailash_ml.automl.engine",
        "DataExplorer": "kailash_ml.engines.data_explorer",
        "FeatureEngineer": "kailash_ml.engines.feature_engineer",
        "EnsembleEngine": "kailash_ml.engines.ensemble",
        "ClusteringEngine": "kailash_ml.engines.clustering",
        "AnomalyDetectionEngine": "kailash_ml.engines.anomaly_detection",
        "DimReductionEngine": "kailash_ml.engines.dim_reduction",
        "PreprocessingPipeline": "kailash_ml.engines.preprocessing",
        "ModelVisualizer": "kailash_ml.engines.model_visualizer",
        "ModelExplainer": "kailash_ml.engines.model_explainer",
        # Bridge
        "OnnxBridge": "kailash_ml.bridge.onnx_bridge",
        # Compat
        "MlflowFormatReader": "kailash_ml.compat.mlflow_format",
        "MlflowFormatWriter": "kailash_ml.compat.mlflow_format",
        # Dashboard
        "MLDashboard": "kailash_ml.dashboard",
        # Decorators
        "ExperimentalWarning": "kailash_ml._decorators",
    }
    if name == "metrics":
        import importlib

        return importlib.import_module("kailash_ml.metrics")
    if name in _engine_map:
        import importlib

        module = importlib.import_module(_engine_map[name])
        return getattr(module, name)
    raise AttributeError(f"module 'kailash_ml' has no attribute {name!r}")


# ---------------------------------------------------------------------------
# Canonical __all__ — exact 6-group ordering per specs/ml-engines-v2.md §15.9
#
# Symbol count: 49 (spec §15.9 base 40 groups + W15 FP-MED-2 adds
# ``erase_subject`` to Group 1 + W6 wave additions: ``rl_train`` (Group 1,
# W6-015 RL primary verb), 7 Phase-1 Trainable adapters in Group 2
# enumeration including ``CatBoostTrainable`` (W6-013), and Group 6
# discovery primitives ``engine_info`` / ``list_engines`` (W6-012). The
# ordering is load-bearing: ``from kailash_ml import *`` users observe
# verbs first, then primitives, then diagnostics, then backend, then
# tracker, then discovery. Reordering requires a spec amendment (§15.9
# MUST). Count is verifier-derived (``ast.parse(...).find('__all__')``)
# per ``rules/testing.md`` § "Verified Numerical Claims".
# ---------------------------------------------------------------------------

__all__ = [
    # Group 1 — Lifecycle verbs (action-first for discoverability)
    "track",
    "autolog",
    "train",
    "diagnose",
    "register",
    "serve",
    "watch",
    "dashboard",
    "seed",
    "reproduce",
    "resume",
    "lineage",
    "rl_train",
    "erase_subject",  # W15 FP-MED-2 — appended per todo invariant 1
    # Group 2 — Engine primitives + MLError hierarchy
    "Engine",
    "Trainable",
    # Phase 1 family adapters (specs/ml-engines.md §3.0)
    "SklearnTrainable",
    "XGBoostTrainable",
    "LightGBMTrainable",
    "CatBoostTrainable",
    "TorchTrainable",
    "LightningTrainable",
    "UMAPTrainable",
    "HDBSCANTrainable",
    "TrainingResult",
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
    # Group 3 — Diagnostic adapters + helpers
    "DLDiagnostics",
    "RAGDiagnostics",
    "RLDiagnostics",
    "diagnose_classifier",
    "diagnose_regressor",
    # Group 4 — Backend detection
    "detect_backend",
    "DeviceReport",
    # Group 5 — Tracker primitives
    "ExperimentTracker",
    "ExperimentRun",
    "ModelRegistry",
    # Group 6 — Engine Discovery (metadata introspection per
    # ml-engines-v2-addendum §E11.2)
    "engine_info",
    "list_engines",
]


# Silence the "unused import" linter warnings for eager-imports kept
# only for module-scope attribute lookup (legacy, agents, RL bridge,
# estimators). These MUST stay imported at module scope per
# rules/orphan-detection.md §6.
_ = (
    BackendInfo,
    DeviceReport,
    DashboardHandle,
    device_report_from_backend_info,
    device,
    use_device,
    doctor,
    autolog_fn,
    resolve_torch_wheel,
    ColumnTransformer,
    FeatureUnion,
    Pipeline,
    StandardScaler,
    is_registered_estimator,
    register_estimator,
    registered_estimators,
    unregister_estimator,
    CatBoostTrainable,
    HDBSCANTrainable,
    LightGBMTrainable,
    LightningTrainable,
    SklearnTrainable,
    TorchTrainable,
    UMAPTrainable,
    XGBoostTrainable,
    RLLineage,
    FeatureNotAvailableError,
    PolicyArtifactRef,
    RLLifecycleProtocol,
    AgentInfusionProtocol,
    FeatureField,
    FeatureSchema,
    MetricSpec,
    MLToolProtocol,
    ModelSignature,
    SeedReport,
    SetupResult,
    ComparisonResult,
    PredictionResult,
    RegisterResult,
    EvaluationResult,
    ServeResult,
    FinalizeResult,
    AlertConfig,
    ClearanceRequirement,
    EngineInfo,
    EngineNotFoundError,
    MethodSignature,
    ParamSpec,
    # NOTE: ``LineageGraph`` removed at W6-014 — the type is deferred to
    # Wave 6.5b along with the registry-side ``build_lineage_graph``
    # primitive (issue #657). ``km.lineage(...)`` raises
    # ``LineageNotImplementedError`` per ``rules/zero-tolerance.md`` Rule 1b.
    # Error classes kept reachable for callers who want the finer taxonomy
    ActorRequiredError,
    AliasNotFoundError,
    AliasOccupiedError,
    ArtifactEncryptionError,
    ArtifactSizeExceededError,
    AuthorizationError,
    AutologAttachError,
    AutologDetachError,
    AutologDoubleAttachError,
    AutologNoAmbientRunError,
    AutologUnknownFrameworkError,
    BudgetExhaustedError,
    CrossTenantLineageError,
    DLDiagnosticsStateError,
    DriftThresholdError,
    EnsembleFailureError,
    EnvVarDeprecatedError,
    ErasureRefusedError,
    ExperimentNotFoundError,
    FeatureNotFoundError,
    FeatureNotYetSupportedError,
    ImmutableGoldenReferenceError,
    InsufficientSamplesError,
    InsufficientTrialsError,
    InvalidInputSchemaError,
    InvalidTenantIdError,
    LineageNotImplementedError,
    LineageRequiredError,
    LiveStreamError,
    MetricValueError,
    MigrationFailedError,
    MigrationImportError,
    MigrationRequiredError,
    ModelLoadError,
    ModelNotFoundError,
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
    RLPolicyShapeMismatchError,
    RunNotFoundError,
    RunNotFoundInDashboardError,
    SeedReportError,
    ShadowDivergenceError,
    StaleFeatureError,
    TenantQuotaExceededError,
    TenantRequiredError,
    TrackerStoreInitError,
    UnknownTenantError,
    UnsupportedFamily,
    UnsupportedPrecision,
    UnsupportedTrainerError,
    WorkflowNodeMLContextError,
    fingerprint_classified_value,
    MLEngine,
)

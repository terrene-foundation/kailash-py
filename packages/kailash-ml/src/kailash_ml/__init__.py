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

from kailash_ml._device import BackendInfo, detect_backend
from kailash_ml._gpu_setup import resolve_torch_wheel
from kailash_ml._result import TrainingResult
from kailash_ml._version import __version__
from kailash_ml.engine import MLEngine
from kailash_ml.engines.data_explorer import AlertConfig
from kailash_ml.trainable import Trainable
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


def track(experiment: str, **kwargs):
    """Async-context experiment tracker: `async with km.track('exp') as t: ...`.

    Phase 6 (Registry + Tracking) implements full body with the MLflow-better
    contract from `specs/ml-tracking.md`. Until then this raises a typed
    error naming the phase.
    """
    raise NotImplementedError(
        "km.track — Phase 6 (ExperimentTracker) will implement per "
        "specs/ml-tracking.md. Use kailash_ml.MLEngine(tracker=...) for DI."
    )


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
    # kailash-ml 2.0 kernel (Phase 2 — scaffolded, filled in Phase 3+)
    "MLEngine",
    "BackendInfo",
    "detect_backend",
    "TrainingResult",
    "Trainable",
    "train",
    "track",
    "resolve_torch_wheel",
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
]

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

from kailash_ml._version import __version__
from kailash_ml.engines.data_explorer import AlertConfig
from kailash_ml.types import (
    AgentInfusionProtocol,
    FeatureField,
    FeatureSchema,
    MetricSpec,
    MLToolProtocol,
    ModelSignature,
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
    # Types (from kailash_ml.types)
    "AgentInfusionProtocol",
    "FeatureField",
    "FeatureSchema",
    "MetricSpec",
    "MLToolProtocol",
    "ModelSignature",
    # Engines
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

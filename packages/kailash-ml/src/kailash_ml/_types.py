# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Internal shared types for kailash-ml engines.

These types are NOT part of the public API. Use kailash-ml-protocols
for cross-package contracts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ModelSpec:
    """Internal specification for a model to be trained."""

    name: str
    model_type: str  # "classifier", "regressor", "ranker"
    algorithm: str  # "lightgbm", "sklearn.RandomForestClassifier", etc.
    hyperparameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalSpec:
    """Internal specification for model evaluation."""

    metrics: list[str]  # ["accuracy", "f1", "auc"]
    split_strategy: str = "holdout"  # "holdout", "kfold", "stratified_kfold"
    n_splits: int = 5
    test_size: float = 0.2


@dataclass
class TrainingResult:
    """Internal result from a training run."""

    model_name: str
    version: int
    artifact_path: str
    metrics: dict[str, float]
    training_duration_seconds: float
    trained_at: datetime = field(default_factory=datetime.utcnow)

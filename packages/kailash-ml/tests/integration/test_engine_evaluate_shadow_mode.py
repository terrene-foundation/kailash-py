# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration: MLEngine.evaluate(mode='shadow') emits shadow_evaluate audit.

Tier 2 — shadow mode records the evaluation as ``operation=
"shadow_evaluate"`` in the structured log AND explicitly skips
drift-monitor updates so the shadow run does not poison the baseline.
"""
from __future__ import annotations

import logging
import pickle
from types import SimpleNamespace

import pytest

import polars as pl
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml import MLEngine
from kailash_ml.engines.model_registry import (
    LocalFileArtifactStore,
    ModelRegistry,
)
from kailash_ml.types import (
    FeatureField,
    FeatureSchema,
    MetricSpec,
    ModelSignature,
)


@pytest.fixture
async def registry(tmp_path):
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    reg = ModelRegistry(cm, artifact_store=store)
    yield reg
    await cm.close()


@pytest.fixture
def sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "x1": list(range(40)),
            "x2": [i * 2 for i in range(40)],
            "y": [i % 2 for i in range(40)],
        }
    )


@pytest.fixture
async def registered_classifier(registry: ModelRegistry, sample_df: pl.DataFrame):
    sig = ModelSignature(
        input_schema=FeatureSchema(
            "input",
            [FeatureField("x1", "float64"), FeatureField("x2", "float64")],
            "id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )
    model = RandomForestClassifier(n_estimators=5, random_state=42)
    model.fit(sample_df.select(["x1", "x2"]).to_numpy(), sample_df["y"].to_numpy())
    return await registry.register_model(
        "clf_shadow",
        pickle.dumps(model),
        metrics=[MetricSpec("accuracy", 0.95)],
        signature=sig,
    )


@pytest.mark.integration
async def test_evaluate_shadow_emits_shadow_operation_audit(
    registry: ModelRegistry,
    registered_classifier,
    sample_df: pl.DataFrame,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """shadow mode writes an audit log line with operation=shadow_evaluate."""
    engine = MLEngine(registry=registry)
    engine._setup_result = SimpleNamespace(target="y", task_type="classification")

    with caplog.at_level(logging.INFO, logger="kailash_ml.engine"):
        result = await engine.evaluate(registered_classifier, sample_df, mode="shadow")

    assert result.mode == "shadow"
    audit_records = [
        r
        for r in caplog.records
        if r.name == "kailash_ml.engine"
        and r.message == "evaluate.ok"
        and getattr(r, "operation", None) == "shadow_evaluate"
    ]
    assert audit_records, (
        "shadow evaluate() MUST emit an 'evaluate.ok' INFO log with "
        "operation='shadow_evaluate'. See rules/tenant-isolation.md Rule 5."
    )


class _RecordingDriftMonitor:
    """Minimal drift monitor recording whether check_drift was invoked."""

    def __init__(self) -> None:
        self.check_drift_called = False

    async def check_drift(self, model_name: str, current_data):
        self.check_drift_called = True


@pytest.mark.integration
async def test_evaluate_shadow_does_not_update_drift_monitor(
    registry: ModelRegistry,
    registered_classifier,
    sample_df: pl.DataFrame,
) -> None:
    """shadow mode MUST NOT trigger drift-monitor updates."""
    engine = MLEngine(registry=registry)
    engine._setup_result = SimpleNamespace(target="y", task_type="classification")
    recorder = _RecordingDriftMonitor()
    engine._drift_monitor = recorder

    await engine.evaluate(registered_classifier, sample_df, mode="shadow")

    assert not recorder.check_drift_called, (
        "shadow mode MUST NOT update drift monitor stats — the whole "
        "point of shadow/live split is that shadow does not poison the "
        "live baseline."
    )

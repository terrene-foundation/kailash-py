# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 test: serve() partial-failure triggers full rollback, no partial result.

Per specs/ml-engines.md §2.1 MUST 10, a failure binding one channel in a
multi-channel serve() call MUST tear down every channel bound earlier
in the same call — no partial ServeResult is returned.
"""
from __future__ import annotations

import pickle

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml import MLEngine
from kailash_ml.engines.model_registry import LocalFileArtifactStore, ModelRegistry
from kailash_ml.types import FeatureField, FeatureSchema, ModelSignature


@pytest.fixture
async def engine(tmp_path):
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    registry = ModelRegistry(cm, artifact_store=store)

    rng = np.random.default_rng(seed=5)
    X = rng.random((20, 2), dtype=np.float64)
    y = (X[:, 0] > 0.5).astype(int)
    model = RandomForestClassifier(n_estimators=2, random_state=0)
    model.fit(X, y)

    signature = ModelSignature(
        input_schema=FeatureSchema(
            "input",
            [FeatureField("a", "float64"), FeatureField("b", "float64")],
            "id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )
    await registry.register_model(
        "rollback_model", pickle.dumps(model), signature=signature
    )

    eng = MLEngine(registry=registry)
    yield eng
    await cm.close()


@pytest.mark.integration
async def test_serve_mcp_bind_failure_rolls_back_rest(engine, monkeypatch):
    """If MCP bind fails after REST succeeds, the REST binding MUST also be torn down."""
    shutdowns_called: list[str] = []

    original_bind_rest = engine._bind_rest

    async def instrumented_bind_rest(name, version, *, autoscale, options):
        binding = await original_bind_rest(
            name, version, autoscale=autoscale, options=options
        )
        # Intercept the shutdown callback so we can observe it firing during rollback.
        original_shutdown = binding.shutdown

        async def tracked_shutdown():
            shutdowns_called.append("rest")
            await original_shutdown()

        binding.shutdown = tracked_shutdown
        return binding

    async def failing_bind_mcp(name, version, *, autoscale, options):
        raise RuntimeError("simulated MCP bind failure (port conflict)")

    monkeypatch.setattr(engine, "_bind_rest", instrumented_bind_rest)
    monkeypatch.setattr(engine, "_bind_mcp", failing_bind_mcp)

    with pytest.raises(RuntimeError, match="simulated MCP bind failure"):
        await engine.serve("models://rollback_model/v1", channels=["rest", "mcp"])

    # REST shutdown MUST have fired.
    assert "rest" in shutdowns_called, (
        "Partial-failure rollback did NOT tear down the REST binding — "
        "violates ml-engines.md §2.1 MUST 10."
    )
    # No active_serves should remain for the failed call.
    active = getattr(engine, "_active_serves", {})
    assert all(
        channel not in ("rest", "mcp") for (_, _, channel) in active.keys()
    ), "active_serves leaked despite rollback"


@pytest.mark.integration
async def test_serve_first_channel_failure_raises_with_no_bindings(engine, monkeypatch):
    """If the FIRST channel fails, no bindings exist to roll back — still raises."""

    async def failing_bind_rest(name, version, *, autoscale, options):
        raise RuntimeError("first-channel failure")

    monkeypatch.setattr(engine, "_bind_rest", failing_bind_rest)

    with pytest.raises(RuntimeError, match="first-channel failure"):
        await engine.serve("models://rollback_model/v1", channels=["rest", "mcp"])

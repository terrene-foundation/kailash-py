# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: W33c — README Quick Start km.train -> km.register pipeline.

Before W33c, `km.register(result, ...)` raised:

    ValueError: register(result=...) could not locate the trained model.
    Attach the fitted model on result.model or pass a TrainingResult
    whose trainable exposes .model.

Root cause: `TrainingResult` is a frozen dataclass with no `trainable`
or `model` field, so every framework Trainable's `fit()` return site
dropped the fitted-model handle on the floor. `MLEngine.register()` then
had no way to locate the model object for ONNX export, and the canonical
3-line Quick Start documented in `specs/ml-engines-v2.md` §16 could not
execute end-to-end.

The fix attaches `trainable=self` to every `TrainingResult` returned
by a Trainable, exposes `.model` as a canonical property on every
Trainable class, and simplifies `MLEngine.register()` to resolve the
fitted model via `result.trainable.model` (with legacy fallbacks for
test paths that construct TrainingResult literally).

These tests REPRODUCE the failure mode and verify the fix.
"""
from __future__ import annotations

import polars as pl
import pytest


@pytest.mark.regression
@pytest.mark.asyncio
async def test_readme_quickstart_km_train_then_km_register_executes() -> None:
    """Regression: the canonical 3-line Quick Start must execute end-to-end.

    Per `specs/ml-engines-v2.md` §16:

        import kailash_ml as km
        result = await km.train(df, target="churned")
        registered = await km.register(result, name="demo")

    Before W33c this raised ValueError because `result.trainable` was
    not populated. After W33c the pipeline completes and returns a
    RegisterResult with an ONNX artifact URI.
    """
    import kailash_ml as km

    # Synthetic binary classification data — sklearn RandomForestClassifier
    # (the km.train sklearn default) handles this trivially.
    df = pl.DataFrame(
        {
            "feature_a": [0.1, 0.9, 0.2, 0.8, 0.15, 0.85, 0.25, 0.75] * 8,
            "feature_b": [1.0, 0.1, 0.9, 0.2, 0.95, 0.05, 0.85, 0.15] * 8,
            "churned": [0, 1, 0, 1, 0, 1, 0, 1] * 8,
        }
    )

    # Step 1: train — must succeed and produce a TrainingResult whose
    # `.trainable` field is a fitted SklearnTrainable.
    result = await km.train(df, target="churned")
    assert result is not None, "km.train returned None"
    assert result.trainable is not None, (
        "W33c regression: result.trainable is None — framework training "
        "path dropped the Trainable back-reference"
    )
    assert result.trainable.model is not None, (
        "W33c regression: result.trainable.model is None — Trainable "
        "did not expose its fitted estimator"
    )

    # Step 2: register — must succeed and return a RegisterResult with
    # an ONNX artifact URI populated (default format="onnx").
    registered = await km.register(result, name="w33c_readme_quickstart")
    assert registered is not None, "km.register returned None"
    assert registered.name == "w33c_readme_quickstart"
    assert registered.version >= 1
    assert registered.stage == "staging"
    # ONNX artifact is mandatory per §6.1 MUST 2 for the sklearn branch.
    assert "onnx" in registered.artifact_uris, (
        f"expected ONNX artifact URI in registered.artifact_uris, "
        f"got keys: {list(registered.artifact_uris.keys())}"
    )


@pytest.mark.regression
def test_readme_quickstart_engine_fit_then_engine_register_executes() -> None:
    """Regression: the async engine-method chain must also execute.

    The `km.*` wrappers and the `engine.*` methods are two faces of the
    same pipeline per `specs/ml-engines-v2.md` §15.3. If one chain works
    and the other fails, a structural invariant is broken. This test
    proves the async-engine form works end-to-end too.
    """
    import asyncio

    from kailash_ml import MLEngine

    df = pl.DataFrame(
        {
            "x1": [0.1, 0.9, 0.2, 0.8, 0.15, 0.85, 0.25, 0.75] * 8,
            "x2": [1.0, 0.1, 0.9, 0.2, 0.95, 0.05, 0.85, 0.15] * 8,
            "y": [0, 1, 0, 1, 0, 1, 0, 1] * 8,
        }
    )

    async def _chain():
        engine = MLEngine()
        result = await engine.fit(df, target="y", family="sklearn")
        assert result.trainable is not None, (
            "engine.fit path also dropped result.trainable — cross-path "
            "regression (both km.* and engine.* must attach)"
        )
        registered = await engine.register(result, name="w33c_async_chain")
        return registered

    registered = asyncio.run(_chain())
    assert registered.name == "w33c_async_chain"
    assert registered.version >= 1
    assert "onnx" in registered.artifact_uris

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W6-013 Tier-2 integration test — CatBoostTrainable end-to-end.

Per ``rules/testing.md`` § Tier 2: NO mocking. The test gates on
the ``[catboost]`` extra (``pytest.importorskip("catboost")``) and
exercises the full ``Trainable`` contract — construction → fit →
predict → TrainingResult — against a real CatBoost estimator
through the Lightning-routed single-epoch wrapper.

Per ``rules/orphan-detection.md`` §2 every wired manager / family
adapter MUST have at least one Tier 2 test that imports through
the framework facade and asserts the externally-observable effect
(fitted model, populated TrainingResult fields). This test fills
that role for ``CatBoostTrainable``.

Skipped on darwin-arm + py3.13 mirroring the existing onnx
roundtrip matrix (``test_engine_register_onnx_matrix.py``) where
catboost + onnx deps are unstable on that host.
"""
from __future__ import annotations

import platform
import sys

import pytest

# Tier-2 gating — extras + heavy deps + polars are required.
pytest.importorskip("catboost")
pytest.importorskip("lightning.pytorch")
pytest.importorskip("polars")

# Mirror the host-skip gate from test_engine_register_onnx_matrix.py.
_SEGFAULT_HOST = (
    sys.platform == "darwin"
    and platform.machine() == "arm64"
    and sys.version_info[:2] >= (3, 13)
)


@pytest.mark.integration
@pytest.mark.skipif(
    _SEGFAULT_HOST,
    reason=(
        "catboost + lightning unstable on darwin-arm + py3.13; "
        "Tier 2 coverage runs on Linux CI."
    ),
)
def test_catboost_trainable_fit_predict_classification_round_trip() -> None:
    """End-to-end: construct → fit → predict on a small classifier task.

    Asserts:

    1. ``TrainingResult.family == 'catboost'``
    2. ``TrainingResult.device`` is populated (W8 invariant 7).
    3. ``TrainingResult.trainable`` back-reference is the adapter
       (W33b ``km.train → km.register`` handoff).
    4. ``TrainingResult.metrics`` contains an accuracy value > 0.5
       (sanity — separable synthetic data).
    5. ``predict()`` returns Predictions with the same length as inputs.
    """
    import numpy as np
    import polars as pl
    from sklearn.datasets import make_classification

    from kailash_ml import CatBoostTrainable

    X, y = make_classification(
        n_samples=120,
        n_features=6,
        n_informative=4,
        n_redundant=1,
        random_state=42,
    )
    df = pl.DataFrame({f"x{i}": X[:, i].astype(np.float32) for i in range(X.shape[1])})
    df = df.with_columns(pl.Series("y", y.astype(np.int64)))

    trainable = CatBoostTrainable(
        target="y",
        task="classification",
        iterations=10,
        depth=3,
        random_seed=42,
        verbose=False,
    )

    result = trainable.fit(df, hyperparameters=None, context=None)

    assert result.family == "catboost"
    assert result.device is not None, (
        "TrainingResult.device MUST be populated per W8 invariant 7 "
        "(every TrainingResult return site passes device=)."
    )
    assert result.device.family == "catboost"
    assert result.trainable is trainable, (
        "TrainingResult.trainable back-reference MUST point at the adapter "
        "for the km.train → km.register handoff (W33b regression)."
    )

    # Accuracy on the training data should be well above chance for a
    # 10-iteration CatBoost on separable synthetic data.
    metrics = result.metrics
    assert metrics, f"expected non-empty metrics, got {metrics!r}"
    metric_value = next(iter(metrics.values()))
    assert metric_value > 0.5, f"expected accuracy > 0.5, got {metric_value}"

    # Predict round-trip — same row count.
    preds = trainable.predict(df)
    assert preds is not None
    raw = preds.raw
    assert len(raw) == len(df)


@pytest.mark.integration
@pytest.mark.skipif(
    _SEGFAULT_HOST,
    reason=(
        "catboost + lightning unstable on darwin-arm + py3.13; "
        "Tier 2 coverage runs on Linux CI."
    ),
)
def test_catboost_trainable_fit_regression_round_trip() -> None:
    """Regression task — task='regression' constructs CatBoostRegressor."""
    import numpy as np
    import polars as pl
    from sklearn.datasets import make_regression

    from kailash_ml import CatBoostTrainable

    X, y = make_regression(
        n_samples=120,
        n_features=6,
        n_informative=4,
        noise=0.5,
        random_state=42,
    )
    df = pl.DataFrame({f"x{i}": X[:, i].astype(np.float32) for i in range(X.shape[1])})
    df = df.with_columns(pl.Series("y", y.astype(np.float32)))

    trainable = CatBoostTrainable(
        target="y",
        task="regression",
        iterations=10,
        depth=3,
        random_seed=42,
        verbose=False,
    )

    result = trainable.fit(df, hyperparameters=None, context=None)

    assert result.family == "catboost"
    assert result.trainable is trainable
    assert result.metrics, "expected at least one regression metric (r2)"

    # The default classifier is a CatBoostClassifier; for task='regression'
    # the constructor should have built a CatBoostRegressor.
    estimator_cls = type(trainable.model).__name__
    assert (
        estimator_cls == "CatBoostRegressor"
    ), f"task='regression' should yield CatBoostRegressor, got {estimator_cls}"


@pytest.mark.integration
def test_catboost_trainable_resolves_through_engine_family_alias() -> None:
    """family='catboost' on MLEngine resolves to a CatBoostTrainable instance.

    Walks the same dispatch path the public ``km.train(family='catboost')``
    surface uses, ensuring the W6-013 wire reaches end-users (not just an
    isolated import). Construction-only — does NOT call fit() — so the
    darwin-arm + py3.13 segfault host gate does not apply.
    """
    from kailash_ml import CatBoostTrainable
    from kailash_ml.engine import _build_trainable_from_family

    trainable = _build_trainable_from_family("catboost", target="label")
    assert isinstance(trainable, CatBoostTrainable)
    assert trainable.family_name == "catboost"

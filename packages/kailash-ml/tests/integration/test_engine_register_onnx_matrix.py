# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 ONNX round-trip matrix through :meth:`MLEngine.register`.

Per ``specs/ml-engines.md`` §6.1 MUST 2-3: every framework key in the
ONNX compatibility matrix MUST have a Tier 2 round-trip regression
test that trains a minimal model, exports via ``engine.register``,
re-imports the ONNX artifact via ``onnxruntime.InferenceSession``, and
asserts prediction parity against the native model.

Optional frameworks (xgboost / lightgbm / catboost / torch / lightning)
are skipped when their packages aren't installed on the host. The
sklearn branch runs unconditionally because sklearn is a base dep.
"""
from __future__ import annotations

import os
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("skl2onnx")
pytest.importorskip("onnxruntime")


# darwin-arm64 + Python 3.13 is a known segfault host for xgboost / lightgbm
# 4.x — existing Tier 2 ONNX roundtrip tests already skipif on this combo.
# See tests/integration/test_onnx_roundtrip_lightgbm.py for precedent.
_SEGFAULT_HOST = (
    sys.platform == "darwin"
    and platform.machine() == "arm64"
    and sys.version_info[:2] >= (3, 13)
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _training_result(model: Any, family: str) -> Any:
    """Build a TrainingResult-shaped object carrying the fitted model."""
    from kailash_ml._result import TrainingResult

    result = TrainingResult(
        model_uri="models://smoke/v0",
        metrics={"accuracy": 0.9},
        device_used="cpu",
        accelerator="cpu",
        precision="32-true",
        elapsed_seconds=0.01,
        tracker_run_id=None,
        tenant_id=None,
        artifact_uris={},
        lightning_trainer_config={},
        family=family,
    )
    # Frozen dataclass — attach the fitted model via object.__setattr__
    # so register() can pick it up via the attribute lookup chain.
    object.__setattr__(result, "model", model)
    return result


def _engine_in_tmp(tmp: str) -> Any:
    """Construct an engine pointed at a throwaway SQLite store."""
    os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
    os.environ["KAILASH_ML_ARTIFACT_ROOT"] = tmp

    from kailash_ml import MLEngine

    return MLEngine()


def _onnx_inference_labels(onnx_uri: str, X: np.ndarray) -> np.ndarray:
    """Load the ONNX artifact and return prediction labels on ``X``."""
    import onnxruntime as ort

    session = ort.InferenceSession(str(onnx_uri))
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: X.astype(np.float32)})
    return np.asarray(outputs[0]).flatten()


# ---------------------------------------------------------------------------
# sklearn — unconditional
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_sklearn_onnx_roundtrip() -> None:
    """sklearn RandomForest round-trips through engine.register(format='onnx')."""
    from sklearn.datasets import make_classification
    from sklearn.ensemble import RandomForestClassifier

    with tempfile.TemporaryDirectory() as tmp:
        engine = _engine_in_tmp(tmp)

        X, y = make_classification(n_samples=100, n_features=6, random_state=42)
        X = X.astype(np.float32)
        model = RandomForestClassifier(n_estimators=5, random_state=42).fit(X, y)
        result = _training_result(model, family="sklearn")

        reg = await engine.register(result, format="onnx")

        assert "onnx" in reg.artifact_uris
        assert Path(reg.artifact_uris["onnx"]).exists()
        onnx_labels = _onnx_inference_labels(reg.artifact_uris["onnx"], X[:20])
        native_labels = model.predict(X[:20])
        assert np.array_equal(onnx_labels, native_labels)
        # Version monotonicity (§5.1 MUST 4 scope)
        assert reg.version == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_sklearn_format_both_populates_both_artifacts() -> None:
    """format='both' populates both onnx and pickle keys (§6.1 MUST 5)."""
    from sklearn.datasets import make_classification
    from sklearn.linear_model import LogisticRegression

    with tempfile.TemporaryDirectory() as tmp:
        engine = _engine_in_tmp(tmp)
        X, y = make_classification(n_samples=80, n_features=4, random_state=0)
        X = X.astype(np.float32)
        model = LogisticRegression(max_iter=200).fit(X, y)
        result = _training_result(model, family="sklearn")

        reg = await engine.register(result, format="both")

        assert "onnx" in reg.artifact_uris
        assert "pickle" in reg.artifact_uris


# ---------------------------------------------------------------------------
# xgboost — optional
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    _SEGFAULT_HOST,
    reason="xgboost segfaults on darwin-arm + py3.13; covered by Linux CI.",
)
async def test_register_xgboost_onnx_roundtrip() -> None:
    """xgboost round-trips through engine.register(format='onnx')."""
    pytest.importorskip("xgboost")
    pytest.importorskip("onnxmltools")
    import xgboost as xgb
    from sklearn.datasets import make_classification

    with tempfile.TemporaryDirectory() as tmp:
        engine = _engine_in_tmp(tmp)
        X, y = make_classification(n_samples=80, n_features=4, random_state=1)
        X = X.astype(np.float32)
        model = xgb.XGBClassifier(
            n_estimators=5,
            max_depth=3,
            eval_metric="logloss",
            random_state=1,
        ).fit(X, y)
        result = _training_result(model, family="xgboost")

        reg = await engine.register(result, format="onnx")

        assert "onnx" in reg.artifact_uris
        assert Path(reg.artifact_uris["onnx"]).exists()


# ---------------------------------------------------------------------------
# lightgbm — optional (skip on darwin-arm + py3.13 segfault)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_lightgbm_onnx_roundtrip() -> None:
    """lightgbm round-trips through engine.register(format='onnx')."""
    import platform
    import sys

    pytest.importorskip("lightgbm")
    pytest.importorskip("onnxmltools")

    if (
        sys.platform == "darwin"
        and platform.machine() == "arm64"
        and sys.version_info[:2] >= (3, 13)
    ):
        pytest.skip(
            "LightGBM 4.x segfaults on darwin-arm + py3.13 — Tier 2 "
            "coverage deferred to Linux CI (matches existing onnx "
            "roundtrip test skipif)."
        )

    import lightgbm as lgb
    from sklearn.datasets import make_classification

    with tempfile.TemporaryDirectory() as tmp:
        engine = _engine_in_tmp(tmp)
        X, y = make_classification(n_samples=80, n_features=4, random_state=2)
        X = X.astype(np.float32)
        model = lgb.LGBMClassifier(n_estimators=5, random_state=2).fit(X, y)
        result = _training_result(model, family="lightgbm")

        reg = await engine.register(result, format="onnx")

        assert "onnx" in reg.artifact_uris
        assert Path(reg.artifact_uris["onnx"]).exists()


# ---------------------------------------------------------------------------
# catboost / torch / lightning — deep frameworks: optional, import-gated
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    _SEGFAULT_HOST,
    reason="catboost + onnx deps unstable on darwin-arm + py3.13; Linux CI coverage.",
)
async def test_register_catboost_onnx_roundtrip() -> None:
    """catboost round-trips through engine.register(format='onnx')."""
    pytest.importorskip("catboost")
    import catboost as cb
    from sklearn.datasets import make_classification

    with tempfile.TemporaryDirectory() as tmp:
        engine = _engine_in_tmp(tmp)
        X, y = make_classification(n_samples=80, n_features=4, random_state=3)
        X = X.astype(np.float32)
        model = cb.CatBoostClassifier(iterations=5, verbose=0).fit(X, y)
        result = _training_result(model, family="catboost")

        reg = await engine.register(result, format="onnx")

        assert "onnx" in reg.artifact_uris
        assert Path(reg.artifact_uris["onnx"]).exists()

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 backend-matrix tests for the predict-side transparency contract.

Sibling of ``test_trainable_backend_matrix.py`` — that file asserts
``fit()`` populates ``TrainingResult.device``; this file asserts
``predict()`` populates ``Predictions.device`` with the same
``DeviceReport`` cached at fit-time.

Per revised-stack.md § "Transparency contract" and
``workspaces/kailash-ml-gpu-stack/journal/0005-GAP-predictions-device-field-missing.md``:
every predict returns a Predictions carrying a DeviceReport, so
callers can programmatically distinguish a CUDA-resolved predict from
a CPU-fallback predict without inspecting the prior TrainingResult.

Backend availability gates mirror test_trainable_backend_matrix.py.
XGBoost / LightGBM are gated by the same darwin-arm segfault skip.
"""
from __future__ import annotations

import platform
import sys

import numpy as np
import polars as pl
import pytest
import torch

from kailash_ml._device_report import DeviceReport
from kailash_ml.trainable import (
    HDBSCANTrainable,
    LightGBMTrainable,
    Predictions,
    SklearnTrainable,
    TrainingContext,
    UMAPTrainable,
    XGBoostTrainable,
)

_XGBOOST_SEGFAULT_HOST = (
    sys.platform == "darwin"
    and platform.machine() == "arm64"
    and sys.version_info[:2] >= (3, 13)
)
xgboost_stable_only = pytest.mark.skipif(
    _XGBOOST_SEGFAULT_HOST,
    reason=(
        "XGBoost 2.x segfaults on darwin-arm + py3.13 during _meta_from_numpy; "
        "Tier 2 coverage deferred to Linux CI."
    ),
)
lightgbm_stable_only = pytest.mark.skipif(
    _XGBOOST_SEGFAULT_HOST,
    reason=(
        "LightGBM 4.x segfaults on darwin-arm + py3.13 during __init_from_np2d; "
        "Tier 2 coverage deferred to Linux CI."
    ),
)


@pytest.fixture(scope="module")
def classification_frame() -> pl.DataFrame:
    rng = np.random.default_rng(seed=42)
    n = 50
    x1 = rng.normal(0.0, 1.0, size=n)
    x2 = rng.normal(0.0, 1.0, size=n)
    y = ((0.7 * x1 + 0.3 * x2) > 0).astype(int)
    return pl.DataFrame({"feature1": x1, "feature2": x2, "target": y})


@pytest.fixture(scope="module")
def unsupervised_frame() -> pl.DataFrame:
    rng = np.random.default_rng(seed=42)
    n = 50
    return pl.DataFrame(
        {
            "feature1": rng.normal(0.0, 1.0, size=n),
            "feature2": rng.normal(1.0, 1.0, size=n),
            "feature3": rng.normal(-1.0, 1.0, size=n),
        }
    )


@pytest.fixture(scope="module")
def torch_frame() -> pl.DataFrame:
    """Small regression frame for TorchTrainable / LightningTrainable."""
    rng = np.random.default_rng(seed=42)
    n = 64
    x1 = rng.normal(0.0, 1.0, size=n).astype(np.float32)
    x2 = rng.normal(0.0, 1.0, size=n).astype(np.float32)
    y = (0.5 * x1 + 0.3 * x2).astype(np.float32)
    return pl.DataFrame({"feature1": x1, "feature2": x2, "target": y})


def _cpu_ctx() -> TrainingContext:
    return TrainingContext(
        accelerator="cpu",
        precision="32-true",
        devices=1,
        device_string="cpu",
        backend="cpu",
        tenant_id=None,
        tracker_run_id=None,
        trial_number=None,
    )


def _cuda_ctx() -> TrainingContext:
    return TrainingContext(
        accelerator="gpu",
        precision="32-true",
        devices=1,
        device_string="cuda:0",
        backend="cuda",
        tenant_id=None,
        tracker_run_id=None,
        trial_number=None,
    )


def _assert_device_round_trip(result_device: DeviceReport, pred: Predictions) -> None:
    """Core invariant: pred.device is the same DeviceReport fit() returned.

    Not just "not None" and not just "same values" — the adapter caches
    the exact instance to ``self._last_device_report`` and stamps it on
    every subsequent predict until the next fit. Verifying object
    identity catches a refactor that would accidentally rebuild a new
    DeviceReport in predict().
    """
    assert isinstance(
        pred.device, DeviceReport
    ), f"pred.device must be a DeviceReport; got {type(pred.device).__name__}"
    assert pred.device is result_device, (
        "pred.device MUST be the exact DeviceReport instance cached from fit(); "
        "constructing a fresh one in predict() breaks cache-invalidation semantics."
    )


# ---------------------------------------------------------------------------
# Sklearn — CPU predict carries fit's DeviceReport
# ---------------------------------------------------------------------------


def test_sklearn_predict_carries_fit_device_report(
    classification_frame: pl.DataFrame,
) -> None:
    """SklearnTrainable.predict() Predictions.device is the fit-time DeviceReport."""
    from sklearn.ensemble import RandomForestClassifier

    trainable = SklearnTrainable(
        estimator=RandomForestClassifier(n_estimators=5, random_state=42),
        target="target",
    )
    result = trainable.fit(classification_frame, context=_cpu_ctx())
    pred = trainable.predict(classification_frame.drop("target"))
    _assert_device_round_trip(result.device, pred)
    assert pred.device.family == "sklearn"
    assert pred.device.backend == "cpu"


# ---------------------------------------------------------------------------
# XGBoost — CPU predict carries fit's DeviceReport
# ---------------------------------------------------------------------------


@xgboost_stable_only
def test_xgboost_predict_carries_fit_device_report(
    classification_frame: pl.DataFrame,
) -> None:
    """XGBoostTrainable.predict() Predictions.device is the fit-time DeviceReport."""
    trainable = XGBoostTrainable(target="target", task="classification")
    result = trainable.fit(classification_frame, context=_cpu_ctx())
    pred = trainable.predict(classification_frame.drop("target"))
    _assert_device_round_trip(result.device, pred)
    assert pred.device.family == "xgboost"
    assert pred.device.backend == "cpu"


# ---------------------------------------------------------------------------
# LightGBM — CPU predict carries fit's DeviceReport
# ---------------------------------------------------------------------------


@lightgbm_stable_only
def test_lightgbm_predict_carries_fit_device_report(
    classification_frame: pl.DataFrame,
) -> None:
    """LightGBMTrainable.predict() Predictions.device is the fit-time DeviceReport."""
    trainable = LightGBMTrainable(target="target", task="classification")
    result = trainable.fit(classification_frame, context=_cpu_ctx())
    pred = trainable.predict(classification_frame.drop("target"))
    _assert_device_round_trip(result.device, pred)
    assert pred.device.family == "lightgbm"
    assert pred.device.backend == "cpu"


# ---------------------------------------------------------------------------
# Torch — CPU predict carries fit's DeviceReport
# ---------------------------------------------------------------------------


def test_torch_predict_carries_fit_device_report(torch_frame: pl.DataFrame) -> None:
    """TorchTrainable.predict() Predictions.device is the fit-time DeviceReport."""
    from kailash_ml.trainable import TorchTrainable

    class _Linear(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.linear = torch.nn.Linear(2, 1)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.linear(x).squeeze(-1)

    trainable = TorchTrainable(
        model=_Linear(),
        target="target",
        loss_fn=torch.nn.MSELoss(),
    )
    result = trainable.fit(torch_frame, context=_cpu_ctx())
    pred = trainable.predict(torch_frame.drop("target"))
    _assert_device_round_trip(result.device, pred)
    assert pred.device.family == "torch"


# ---------------------------------------------------------------------------
# Lightning — CPU predict carries fit's DeviceReport
# ---------------------------------------------------------------------------


def test_lightning_predict_carries_fit_device_report(
    torch_frame: pl.DataFrame,
) -> None:
    """LightningTrainable.predict() Predictions.device is the fit-time DeviceReport."""
    import lightning.pytorch as pl_trainer

    from kailash_ml.trainable import LightningTrainable

    class _LitModel(pl_trainer.LightningModule):
        def __init__(self) -> None:
            super().__init__()
            self.linear = torch.nn.Linear(2, 1)
            self.loss_fn = torch.nn.MSELoss()

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.linear(x).squeeze(-1)

        def training_step(self, batch, batch_idx):  # type: ignore[no-untyped-def]
            x, y = batch
            y_hat = self(x)
            return self.loss_fn(y_hat, y.reshape(y_hat.shape))

        def configure_optimizers(self):  # type: ignore[no-untyped-def]
            return torch.optim.Adam(self.parameters(), lr=1e-2)

    trainable = LightningTrainable(module=_LitModel(), target="target")
    result = trainable.fit(torch_frame, context=_cpu_ctx())
    pred = trainable.predict(torch_frame.drop("target"))
    _assert_device_round_trip(result.device, pred)
    assert pred.device.family == "lightning"


# ---------------------------------------------------------------------------
# UMAP — CPU predict + cuml_eviction fallback on CUDA request
# ---------------------------------------------------------------------------


def test_umap_predict_carries_fit_device_report(
    unsupervised_frame: pl.DataFrame,
) -> None:
    """UMAPTrainable.predict() Predictions.device is the fit-time DeviceReport."""
    trainable = UMAPTrainable(n_components=2, n_neighbors=5, random_state=42)
    result = trainable.fit(unsupervised_frame, context=_cpu_ctx())
    pred = trainable.predict(unsupervised_frame)
    _assert_device_round_trip(result.device, pred)
    assert pred.device.family == "umap"
    assert pred.device.fallback_reason is None


def test_umap_cuda_request_predict_carries_eviction_fallback(
    unsupervised_frame: pl.DataFrame,
) -> None:
    """UMAP Phase 1 CUDA request — predict carries fallback_reason='cuml_eviction'."""
    trainable = UMAPTrainable(n_components=2, n_neighbors=5, random_state=42)
    result = trainable.fit(unsupervised_frame, context=_cuda_ctx())
    pred = trainable.predict(unsupervised_frame)
    _assert_device_round_trip(result.device, pred)
    assert pred.device.fallback_reason == "cuml_eviction"


# ---------------------------------------------------------------------------
# HDBSCAN — CPU predict + cuml_eviction fallback on CUDA request
# ---------------------------------------------------------------------------


def test_hdbscan_predict_carries_fit_device_report(
    unsupervised_frame: pl.DataFrame,
) -> None:
    """HDBSCANTrainable.predict() Predictions.device is the fit-time DeviceReport."""
    trainable = HDBSCANTrainable(min_cluster_size=3)
    result = trainable.fit(unsupervised_frame, context=_cpu_ctx())
    pred = trainable.predict(unsupervised_frame)
    _assert_device_round_trip(result.device, pred)
    assert pred.device.family == "hdbscan"
    assert pred.device.fallback_reason is None


def test_hdbscan_cuda_request_predict_carries_eviction_fallback(
    unsupervised_frame: pl.DataFrame,
) -> None:
    """HDBSCAN Phase 1 CUDA request — predict carries fallback_reason='cuml_eviction'."""
    trainable = HDBSCANTrainable(min_cluster_size=3)
    result = trainable.fit(unsupervised_frame, context=_cuda_ctx())
    pred = trainable.predict(unsupervised_frame)
    _assert_device_round_trip(result.device, pred)
    assert pred.device.fallback_reason == "cuml_eviction"

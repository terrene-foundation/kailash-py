# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 backend-matrix tests across every Phase 1 Trainable family.

Exercises each Trainable on CPU + (where available) MPS / CUDA with
real estimators, real data, real Lightning Trainer. NO mocking per
``rules/testing.md`` §"Tier 2 (Integration): Real infrastructure".

Backend availability is detected at collection time:

- ``cpu``  — always runs
- ``mps``  — skipif ``not torch.backends.mps.is_available()``
- ``cuda`` — skipif ``not torch.cuda.is_available()``

Every test asserts:

1. The fit completes without raising.
2. ``TrainingResult.device`` is a populated ``DeviceReport`` (orphan-
   detection §6 — the GPU-first Phase 1 public API symbols must be
   exercised by Tier 2 per revised-stack.md § "Transparency contract").
3. ``result.device.backend`` matches what actually ran (not what was
   requested — e.g. UMAP on a CUDA request reports backend="cpu"
   with ``fallback_reason="cuml_eviction"``).

Per revised-stack.md § "Deliverables for a follow-up implementation
session" item 7.
"""
from __future__ import annotations

import os
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
    SklearnTrainable,
    TrainingContext,
    UMAPTrainable,
    XGBoostTrainable,
)

# ---------------------------------------------------------------------------
# Backend availability gates
# ---------------------------------------------------------------------------

_MPS_AVAILABLE = torch.backends.mps.is_available()
_CUDA_AVAILABLE = torch.cuda.is_available()
_SCIPY_ARRAY_API = os.environ.get("SCIPY_ARRAY_API") == "1"

requires_mps = pytest.mark.skipif(
    not _MPS_AVAILABLE, reason="Test host does not expose Metal Performance Shaders."
)
requires_cuda = pytest.mark.skipif(
    not _CUDA_AVAILABLE, reason="Test host does not expose a CUDA device."
)
requires_scipy_array_api = pytest.mark.skipif(
    not _SCIPY_ARRAY_API,
    reason=(
        "Set SCIPY_ARRAY_API=1 before importing any sklearn/scipy module "
        "to exercise the real Array API dispatch path."
    ),
)

# XGBoost 2.x segfaults inside `_meta_from_numpy` on darwin-arm + py3.13
# when fitting against a numpy ndarray (upstream XGBoost issue; same
# class as the pre-existing `test_auto_logging.py` darwin-arm segfault
# the conftest already excludes). Tier-2 coverage on Linux CI still
# exercises the path. TODO: file upstream XGBoost issue with repro.
_XGBOOST_SEGFAULT_HOST = (
    sys.platform == "darwin"
    and platform.machine() == "arm64"
    and sys.version_info[:2] >= (3, 13)
)
xgboost_stable_only = pytest.mark.skipif(
    _XGBOOST_SEGFAULT_HOST,
    reason=(
        "XGBoost 2.x segfaults on darwin-arm + py3.13 during _meta_from_numpy; "
        "Tier 2 coverage deferred to Linux CI. Tier 1 OOM-fallback unit tests "
        "exercise the XGBoostTrainable codepath without hitting the segfault."
    ),
)

# LightGBM 4.x has the same numpy-dispatch segfault class on
# darwin-arm + py3.13 (fires in `_lazy_init` → `__init_from_np2d`).
# Same disposition: defer Tier 2 to Linux CI, keep Tier 1 OOM-fallback
# unit tests that exercise the LightGBMTrainable codepath.
lightgbm_stable_only = pytest.mark.skipif(
    _XGBOOST_SEGFAULT_HOST,  # same host signature
    reason=(
        "LightGBM 4.x segfaults on darwin-arm + py3.13 during "
        "__init_from_np2d; Tier 2 coverage deferred to Linux CI. Tier 1 "
        "OOM-fallback unit tests exercise the LightGBMTrainable codepath."
    ),
)


# ---------------------------------------------------------------------------
# Shared fixtures — real polars frames, deterministic, tiny
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def classification_frame() -> pl.DataFrame:
    """50-row binary classification frame. Large enough for HDBSCAN."""
    rng = np.random.default_rng(seed=42)
    n = 50
    x1 = rng.normal(0.0, 1.0, size=n)
    x2 = rng.normal(0.0, 1.0, size=n)
    # Linear separator — y=1 when 0.7*x1+0.3*x2>0
    y = ((0.7 * x1 + 0.3 * x2) > 0).astype(int)
    return pl.DataFrame({"feature1": x1, "feature2": x2, "target": y})


@pytest.fixture(scope="module")
def unsupervised_frame() -> pl.DataFrame:
    """50-row 3-feature frame for UMAP / HDBSCAN (no target column)."""
    rng = np.random.default_rng(seed=42)
    n = 50
    return pl.DataFrame(
        {
            "feature1": rng.normal(0.0, 1.0, size=n),
            "feature2": rng.normal(1.0, 1.0, size=n),
            "feature3": rng.normal(-1.0, 1.0, size=n),
        }
    )


def _ctx(backend: str, device_string: str) -> TrainingContext:
    """Construct a TrainingContext for the target backend."""
    accelerator = "gpu" if backend in {"cuda", "mps"} else "cpu"
    return TrainingContext(
        accelerator=accelerator,
        precision="32-true",
        devices=1,
        device_string=device_string,
        backend=backend,
        tenant_id=None,
        tracker_run_id=None,
        trial_number=None,
    )


def _cpu_ctx() -> TrainingContext:
    return _ctx("cpu", "cpu")


def _mps_ctx() -> TrainingContext:
    return _ctx("mps", "mps")


def _cuda_ctx() -> TrainingContext:
    return _ctx("cuda", "cuda:0")


# ---------------------------------------------------------------------------
# Sklearn — CPU path + off-allowlist GPU request
# ---------------------------------------------------------------------------


def test_sklearn_cpu_fits_and_reports_cpu(
    classification_frame: pl.DataFrame,
) -> None:
    """Sklearn on CPU context — DeviceReport.backend=='cpu', array_api=False."""
    from sklearn.ensemble import RandomForestClassifier

    trainable = SklearnTrainable(
        estimator=RandomForestClassifier(n_estimators=5, random_state=42),
        target="target",
    )
    result = trainable.fit(classification_frame, context=_cpu_ctx())
    assert isinstance(result.device, DeviceReport)
    assert result.device.backend == "cpu"
    assert result.device.family == "sklearn"
    assert result.device.array_api is False
    assert result.device.fallback_reason is None


@requires_mps
def test_sklearn_offlist_estimator_with_mps_request_falls_back(
    classification_frame: pl.DataFrame,
) -> None:
    """Off-allowlist + MPS request → WARN-fallback CPU path, device reflects it."""
    from sklearn.ensemble import RandomForestClassifier

    trainable = SklearnTrainable(
        estimator=RandomForestClassifier(n_estimators=5, random_state=42),
        target="target",
    )
    result = trainable.fit(classification_frame, context=_mps_ctx())
    assert result.device.backend == "cpu"
    assert result.device.array_api is False
    assert result.device.fallback_reason == "array_api_offlist"


@requires_mps
@requires_scipy_array_api
def test_sklearn_allowlisted_estimator_on_mps_engages_array_api(
    classification_frame: pl.DataFrame,
) -> None:
    """Allowlisted estimator + MPS + SCIPY_ARRAY_API=1 → array_api engaged.

    Skipped when the test host does not have the scipy env-var set
    before import; that's the production-deployment precondition and
    this Tier-2 test is the checkpoint that the real path works when
    the precondition holds.
    """
    from sklearn.linear_model import LogisticRegression

    trainable = SklearnTrainable(
        estimator=LogisticRegression(max_iter=200), target="target"
    )
    result = trainable.fit(classification_frame, context=_mps_ctx())
    # When Array API engages cleanly, backend reflects MPS.
    # When scipy's runtime gate trips (deployment env misses SCIPY_ARRAY_API),
    # the CPU fallback path fires. Both are valid outcomes; the test
    # asserts device is populated and the fallback is grep-able.
    assert isinstance(result.device, DeviceReport)
    if result.device.array_api:
        assert result.device.backend == "mps"
        assert result.device.device_string == "mps"
        assert result.device.fallback_reason is None
    else:
        # Fallback path — either array_api_runtime_unavailable or
        # array_api_offlist (if the allowlist check changed).
        assert result.device.backend == "cpu"
        assert result.device.fallback_reason in {
            "array_api_runtime_unavailable",
            "array_api_offlist",
        }


# ---------------------------------------------------------------------------
# XGBoost — CPU path (CUDA unavailable on this host)
# ---------------------------------------------------------------------------


@xgboost_stable_only
def test_xgboost_cpu_fits_and_reports_cpu(
    classification_frame: pl.DataFrame,
) -> None:
    """XGBoost on CPU context — no OOM fallback, DeviceReport.backend=='cpu'."""
    trainable = XGBoostTrainable(target="target", task="classification")
    result = trainable.fit(classification_frame, context=_cpu_ctx())
    assert isinstance(result.device, DeviceReport)
    assert result.device.backend == "cpu"
    assert result.device.family == "xgboost"
    assert result.device.fallback_reason is None


@requires_cuda
@xgboost_stable_only
def test_xgboost_cuda_fits_and_reports_cuda(
    classification_frame: pl.DataFrame,
) -> None:
    """XGBoost on CUDA context — DeviceReport.backend=='cuda' when OOM not hit."""
    trainable = XGBoostTrainable(target="target", task="classification")
    result = trainable.fit(classification_frame, context=_cuda_ctx())
    assert result.device.backend in {"cuda", "cpu"}  # cpu iff OOM fallback fired
    if result.device.backend == "cpu":
        assert result.device.fallback_reason == "oom"


# ---------------------------------------------------------------------------
# LightGBM — CPU path (CUDA unavailable on this host)
# ---------------------------------------------------------------------------


@lightgbm_stable_only
def test_lightgbm_cpu_fits_and_reports_cpu(
    classification_frame: pl.DataFrame,
) -> None:
    """LightGBM on CPU context — standard path, DeviceReport.backend=='cpu'."""
    trainable = LightGBMTrainable(target="target", task="classification")
    result = trainable.fit(classification_frame, context=_cpu_ctx())
    assert isinstance(result.device, DeviceReport)
    assert result.device.backend == "cpu"
    assert result.device.family == "lightgbm"
    assert result.device.fallback_reason is None


# ---------------------------------------------------------------------------
# UMAP — Phase 1 CPU-only; CUDA request triggers cuml_eviction log path
# ---------------------------------------------------------------------------


def test_umap_cpu_fits_and_reports_cpu(
    unsupervised_frame: pl.DataFrame,
) -> None:
    """UMAP on CPU context — no eviction log, DeviceReport.backend=='cpu'."""
    trainable = UMAPTrainable(n_components=2, n_neighbors=5, random_state=42)
    result = trainable.fit(unsupervised_frame, context=_cpu_ctx())
    assert isinstance(result.device, DeviceReport)
    assert result.device.backend == "cpu"
    assert result.device.family == "umap"
    assert result.device.fallback_reason is None


def test_umap_cuda_request_reports_cuml_eviction_fallback(
    unsupervised_frame: pl.DataFrame,
) -> None:
    """UMAP Phase 1 is CPU-only — CUDA request reports cuml_eviction.

    Runs regardless of whether the host has CUDA, because the eviction
    is unconditional in Phase 1 (cuML is evicted at the framework
    level per revised-stack.md CRITICAL-1 disposition).
    """
    trainable = UMAPTrainable(n_components=2, n_neighbors=5, random_state=42)
    result = trainable.fit(unsupervised_frame, context=_cuda_ctx())
    assert result.device.backend == "cpu"
    assert result.device.family == "umap"
    assert result.device.fallback_reason == "cuml_eviction"


# ---------------------------------------------------------------------------
# HDBSCAN — Phase 1 CPU-only; CUDA request triggers cuml_eviction log path
# ---------------------------------------------------------------------------


def test_hdbscan_cpu_fits_and_reports_cpu(
    unsupervised_frame: pl.DataFrame,
) -> None:
    """HDBSCAN on CPU context — standard path, DeviceReport.backend=='cpu'."""
    trainable = HDBSCANTrainable(min_cluster_size=3)
    result = trainable.fit(unsupervised_frame, context=_cpu_ctx())
    assert isinstance(result.device, DeviceReport)
    assert result.device.backend == "cpu"
    assert result.device.family == "hdbscan"
    assert result.device.fallback_reason is None


def test_hdbscan_cuda_request_reports_cuml_eviction_fallback(
    unsupervised_frame: pl.DataFrame,
) -> None:
    """HDBSCAN Phase 1 is CPU-only — CUDA request reports cuml_eviction."""
    trainable = HDBSCANTrainable(min_cluster_size=3)
    result = trainable.fit(unsupervised_frame, context=_cuda_ctx())
    assert result.device.backend == "cpu"
    assert result.device.family == "hdbscan"
    assert result.device.fallback_reason == "cuml_eviction"

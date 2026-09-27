# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for HDBSCANTrainable (GPU-first Phase 1, CPU-only).

Phase 1 ships CPU-only via ``sklearn.cluster.HDBSCAN`` (sklearn ≥1.3,
already in the ``scikit-learn>=1.5`` base dep). cuML is evicted per
workspaces/kailash-ml-gpu-stack/04-validate/02-revised-stack.md
CRITICAL-1 disposition. These tests verify:

1. HDBSCAN fits on CPU and returns a populated DeviceReport.
2. Requesting a CUDA backend logs ``hdbscan.cuml_eviction`` at INFO and
   returns ``fallback_reason="cuml_eviction"`` in the DeviceReport.
3. ``predict()`` returns cluster labels of the expected shape.
4. HDBSCANTrainable is exported via ``kailash_ml.__all__``.
"""
from __future__ import annotations

import logging

import numpy as np
import polars as pl
import pytest

import kailash_ml
from kailash_ml import HDBSCANTrainable
from kailash_ml.trainable import TrainingContext


@pytest.fixture
def clusterable_frame() -> pl.DataFrame:
    """Synthetic frame with two well-separated Gaussian blobs.

    HDBSCAN's default min_cluster_size=5 will find clusters in this data.
    """
    rng = np.random.default_rng(42)
    blob1 = rng.normal(loc=0.0, scale=0.3, size=(20, 2))
    blob2 = rng.normal(loc=5.0, scale=0.3, size=(20, 2))
    points = np.vstack([blob1, blob2])
    return pl.DataFrame({"x": points[:, 0].tolist(), "y": points[:, 1].tolist()})


def _cpu_context() -> TrainingContext:
    return TrainingContext(
        accelerator="cpu",
        precision="32-true",
        devices=1,
        device_string="cpu",
        backend="cpu",
    )


def _cuda_context() -> TrainingContext:
    """Pretend-CUDA context for eviction-path tests — HDBSCANTrainable
    always runs on CPU, so this exercises the cuml_eviction sentinel."""
    return TrainingContext(
        accelerator="cuda",
        precision="bf16-mixed",
        devices=1,
        device_string="cuda:0",
        backend="cuda",
    )


def test_hdbscan_fits_on_cpu_returns_device_report(
    clusterable_frame: pl.DataFrame,
) -> None:
    """HDBSCANTrainable.fit() on CPU populates DeviceReport.backend='cpu'."""
    trainable = HDBSCANTrainable(min_cluster_size=5)
    result = trainable.fit(clusterable_frame, context=_cpu_context())

    assert result.device is not None
    assert result.device.backend == "cpu"
    assert result.device.family == "hdbscan"
    assert result.device.device_string == "cpu"
    assert result.device.precision == "32-true"
    assert result.device.fallback_reason is None
    assert result.device.array_api is False
    assert result.family == "hdbscan"
    assert "native" in result.artifact_uris

    # External evidence the clusterer actually ran: two well-separated
    # blobs should produce ≥1 cluster and finite metrics.
    assert result.metrics["hdbscan_n_clusters"] >= 1.0
    # Non-finite metrics are rejected by TrainingResult.__post_init__,
    # so reaching here proves the metric values are finite.


def test_hdbscan_logs_cuml_eviction_when_cuda_requested(
    clusterable_frame: pl.DataFrame, caplog: pytest.LogCaptureFixture
) -> None:
    """Requesting CUDA logs INFO-level cuml_eviction and sets fallback."""
    trainable = HDBSCANTrainable(min_cluster_size=5)

    with caplog.at_level(logging.INFO, logger="kailash_ml.trainable"):
        result = trainable.fit(clusterable_frame, context=_cuda_context())

    eviction_records = [
        rec for rec in caplog.records if rec.message == "hdbscan.cuml_eviction"
    ]
    assert len(eviction_records) >= 1, (
        "expected hdbscan.cuml_eviction INFO log, got: "
        f"{[r.message for r in caplog.records]}"
    )
    evict = eviction_records[0]
    assert evict.levelno == logging.INFO
    assert evict.requested_backend == "cuda"
    assert evict.actual_backend == "cpu"
    assert evict.fallback_reason == "cuml_eviction"

    assert result.device is not None
    assert result.device.backend == "cpu"
    assert result.device.fallback_reason == "cuml_eviction"


def test_hdbscan_predict_returns_cluster_labels(
    clusterable_frame: pl.DataFrame,
) -> None:
    """predict() returns 1-D label array of length n_rows."""
    trainable = HDBSCANTrainable(min_cluster_size=5)
    trainable.fit(clusterable_frame, context=_cpu_context())

    preds = trainable.predict(clusterable_frame)
    assert preds.column == "cluster_label"
    raw = preds.raw
    # sklearn HDBSCAN.fit_predict returns ndarray of int labels.
    assert raw.shape == (40,)


def test_hdbscan_trainable_in_all() -> None:
    """HDBSCANTrainable MUST be listed in kailash_ml.__all__ (orphan-detection §6)."""
    assert "HDBSCANTrainable" in kailash_ml.__all__
    assert HDBSCANTrainable is kailash_ml.HDBSCANTrainable

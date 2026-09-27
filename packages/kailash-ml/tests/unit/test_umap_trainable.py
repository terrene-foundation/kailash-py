# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for UMAPTrainable (GPU-first Phase 1, CPU-only).

Phase 1 ships CPU-only via the ``umap-learn`` package. cuML is evicted
per workspaces/kailash-ml-gpu-stack/04-validate/02-revised-stack.md
CRITICAL-1 disposition. These tests verify:

1. UMAP fits on CPU and returns a populated DeviceReport.
2. Requesting a CUDA backend logs ``umap.cuml_eviction`` at INFO and
   returns ``fallback_reason="cuml_eviction"`` in the DeviceReport.
3. ``predict()`` returns an embedding of the expected shape.
4. UMAPTrainable is exported via ``kailash_ml.__all__``.
5. The ``[rapids]`` extra is absent from ``pyproject.toml``.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import polars as pl
import pytest

import kailash_ml
from kailash_ml import UMAPTrainable
from kailash_ml.trainable import TrainingContext


@pytest.fixture
def small_frame() -> pl.DataFrame:
    """Synthetic numeric frame suitable for UMAP (≥ n_neighbors rows)."""
    rng = np.random.default_rng(42)
    return pl.DataFrame(
        {
            "f1": rng.standard_normal(30).tolist(),
            "f2": rng.standard_normal(30).tolist(),
            "f3": rng.standard_normal(30).tolist(),
        }
    )


def _cpu_context() -> TrainingContext:
    return TrainingContext(
        accelerator="cpu",
        precision="32-true",
        devices=1,
        device_string="cpu",
        backend="cpu",
    )


def _cuda_context() -> TrainingContext:
    """A pretend-CUDA context for eviction-path tests — we don't actually
    require CUDA to be available because UMAPTrainable always runs on
    CPU (cuml_eviction fires unconditionally for non-cpu)."""
    return TrainingContext(
        accelerator="cuda",
        precision="bf16-mixed",
        devices=1,
        device_string="cuda:0",
        backend="cuda",
    )


def test_umap_fits_on_cpu_returns_device_report(small_frame: pl.DataFrame) -> None:
    """UMAPTrainable.fit() on CPU populates DeviceReport.backend='cpu'."""
    trainable = UMAPTrainable(n_components=2, n_neighbors=5, random_state=0)
    result = trainable.fit(small_frame, context=_cpu_context())

    assert result.device is not None
    assert result.device.backend == "cpu"
    assert result.device.family == "umap"
    assert result.device.device_string == "cpu"
    assert result.device.precision == "32-true"
    # No fallback when caller already on CPU.
    assert result.device.fallback_reason is None
    assert result.device.array_api is False
    assert result.family == "umap"
    assert "native" in result.artifact_uris


def test_umap_logs_cuml_eviction_when_cuda_requested(
    small_frame: pl.DataFrame, caplog: pytest.LogCaptureFixture
) -> None:
    """Requesting CUDA logs INFO-level cuml_eviction and sets fallback."""
    trainable = UMAPTrainable(n_components=2, n_neighbors=5, random_state=0)

    with caplog.at_level(logging.INFO, logger="kailash_ml.trainable"):
        result = trainable.fit(small_frame, context=_cuda_context())

    # The log event name (grep-able sentinel).
    eviction_records = [
        rec for rec in caplog.records if rec.message == "umap.cuml_eviction"
    ]
    assert len(eviction_records) >= 1, (
        "expected umap.cuml_eviction INFO log, got: "
        f"{[r.message for r in caplog.records]}"
    )
    evict = eviction_records[0]
    assert evict.levelno == logging.INFO
    assert evict.requested_backend == "cuda"
    assert evict.actual_backend == "cpu"
    assert evict.fallback_reason == "cuml_eviction"

    # Runtime evidence the call ran on CPU with the eviction sentinel.
    assert result.device is not None
    assert result.device.backend == "cpu"
    assert result.device.fallback_reason == "cuml_eviction"


def test_umap_predict_returns_embedding(small_frame: pl.DataFrame) -> None:
    """predict() returns a 2-D embedding of shape (n_rows, n_components)."""
    trainable = UMAPTrainable(n_components=2, n_neighbors=5, random_state=0)
    trainable.fit(small_frame, context=_cpu_context())

    preds = trainable.predict(small_frame)
    assert preds.column == "embedding"
    raw = preds.raw
    # umap.UMAP.transform returns ndarray (n_samples, n_components).
    assert raw.shape == (30, 2)


def test_umap_trainable_in_all() -> None:
    """UMAPTrainable MUST be listed in kailash_ml.__all__ (rules/orphan-detection §6)."""
    assert "UMAPTrainable" in kailash_ml.__all__
    # Eager import — no lazy __getattr__ path.
    assert UMAPTrainable is kailash_ml.UMAPTrainable


def test_no_rapids_extra_in_pyproject() -> None:
    """pyproject.toml MUST NOT expose a [rapids] extra (cuML evicted)."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:  # pragma: no cover - 3.10 fallback
        import tomli as tomllib  # type: ignore[no-redef]

    # Find pyproject relative to this test file — works in worktrees + main checkout.
    pkg_root = Path(__file__).resolve().parents[2]
    pyproject = pkg_root / "pyproject.toml"
    assert pyproject.exists(), f"pyproject.toml not found at {pyproject}"

    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)

    extras = data.get("project", {}).get("optional-dependencies", {})
    assert "rapids" not in extras, (
        "[rapids] extra is BLOCKED — cuML was evicted per Phase 1 revised-stack.md; "
        "use umap-learn + sklearn.cluster.HDBSCAN."
    )
    # The eviction is structural: no rapids, cuml, or cudf deps anywhere.
    for extra_name, deps in extras.items():
        for dep in deps:
            lowered = dep.lower()
            assert (
                "rapids" not in lowered
            ), f"extras[{extra_name}] contains '{dep}' — rapids is evicted."
            assert (
                "cuml" not in lowered
            ), f"extras[{extra_name}] contains '{dep}' — cuml is evicted."
            assert (
                "cudf" not in lowered
            ), f"extras[{extra_name}] contains '{dep}' — cudf is evicted."

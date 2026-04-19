# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for LightGBMTrainable GPU OOM → CPU fallback.

Covers the Phase 1 punch list item 4 (revised-stack.md §"No-config
contract" — lightgbm row): a GPU OOM inside ``trainer.fit`` MUST log a
single WARN, retry on CPU, and return a TrainingResult whose
``device.fallback_reason`` is ``"oom"`` with ``device.backend == "cpu"``.
Non-OOM exceptions MUST re-raise unchanged. LightGBM probes the GPU
build at ``set_params(device_type='gpu')`` time, so the test must stub
that probe out.

Tests patch ``lightning.pytorch.Trainer`` so no GPU / Lightning runtime
is required (Tier 1 per rules/testing.md §"3-Tier Testing").
"""
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from kailash_ml._device_report import DeviceReport
from kailash_ml._result import TrainingResult
from kailash_ml.trainable import LightGBMTrainable, TrainingContext, _is_gpu_oom_error

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_classification_data() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "feature1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "feature2": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5],
            "target": [0, 1, 0, 1, 0, 1, 0, 1],
        }
    )


@pytest.fixture
def cuda_context() -> TrainingContext:
    return TrainingContext(
        accelerator="gpu",
        precision="32-true",
        devices=1,
        device_string="cuda:0",
        backend="cuda",
    )


@pytest.fixture
def cpu_context() -> TrainingContext:
    return TrainingContext(
        accelerator="cpu",
        precision="32-true",
        devices=1,
        device_string="cpu",
        backend="cpu",
    )


class _FakeLightGBMError(RuntimeError):
    """Stand-in for lightgbm.basic.LightGBMError."""


class _FakeOutOfMemoryError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("")


_FakeOutOfMemoryError.__name__ = "OutOfMemoryError"


def _make_estimator() -> MagicMock:
    """Build a lightgbm estimator stub.

    The production path probes GPU support via ``set_params(device_type=
    'gpu', gpu_use_dp=False)`` BEFORE the Lightning Trainer runs. For the
    test we let set_params succeed so the fit path is reached; the
    trainer stub then raises the OOM that triggers the fallback.
    """
    est = MagicMock(spec=["set_params", "fit", "predict"])
    est.predict.return_value = [0, 1, 0, 1, 0, 1, 0, 1]
    return est


# ---------------------------------------------------------------------------
# _is_gpu_oom_error helper — independent of Trainable
# ---------------------------------------------------------------------------


def test_oom_helper_recognizes_common_messages() -> None:
    """_is_gpu_oom_error recognises the standard OOM phrasings (lgb variant)."""
    assert _is_gpu_oom_error(_FakeLightGBMError("CUDA error: out of memory"))
    assert _is_gpu_oom_error(RuntimeError("CUDA out of memory. Tried to allocate 2 GB"))
    assert _is_gpu_oom_error(RuntimeError("lightgbm kernel OOM allocating GPU buffer"))
    assert _is_gpu_oom_error(_FakeOutOfMemoryError())
    assert not _is_gpu_oom_error(ValueError("missing column 'target'"))
    assert not _is_gpu_oom_error(KeyError("foo"))
    assert not _is_gpu_oom_error(RuntimeError("kernel launch failed"))


# ---------------------------------------------------------------------------
# LightGBMTrainable fit-path OOM fallback
# ---------------------------------------------------------------------------


def _install_oom_then_ok_trainer(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    import lightning.pytorch as pl_trainer

    state: dict[str, Any] = {"calls": 0, "instances": []}

    def fit_side_effect(module: Any) -> None:
        state["calls"] += 1
        if state["calls"] == 1:
            raise _FakeLightGBMError(
                "Check failed: (size) >= ((alloc_size)) at cuda: out of memory"
            )
        module.on_train_start()

    def fake_trainer_ctor(*args: Any, **kwargs: Any) -> MagicMock:
        trainer = MagicMock(name=f"Trainer#{len(state['instances']) + 1}")
        trainer.fit.side_effect = fit_side_effect
        state["instances"].append(trainer)
        return trainer

    monkeypatch.setattr(pl_trainer, "Trainer", fake_trainer_ctor)
    return state


def _install_non_oom_trainer(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    import lightning.pytorch as pl_trainer

    state: dict[str, Any] = {"calls": 0, "instances": []}

    def fit_side_effect(module: Any) -> None:
        state["calls"] += 1
        raise RuntimeError("totally unrelated bug — missing column 'target'")

    def fake_trainer_ctor(*args: Any, **kwargs: Any) -> MagicMock:
        trainer = MagicMock(name=f"Trainer#{len(state['instances']) + 1}")
        trainer.fit.side_effect = fit_side_effect
        state["instances"].append(trainer)
        return trainer

    monkeypatch.setattr(pl_trainer, "Trainer", fake_trainer_ctor)
    return state


def _install_always_oom_trainer(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    import lightning.pytorch as pl_trainer

    state: dict[str, Any] = {"calls": 0}

    def fit_side_effect(module: Any) -> None:
        state["calls"] += 1
        raise _FakeLightGBMError("CUDA error: out of memory on CPU-path stub")

    def fake_trainer_ctor(*args: Any, **kwargs: Any) -> MagicMock:
        trainer = MagicMock(name="Trainer")
        trainer.fit.side_effect = fit_side_effect
        return trainer

    monkeypatch.setattr(pl_trainer, "Trainer", fake_trainer_ctor)
    return state


def test_oom_on_cuda_falls_back_to_cpu_with_warn(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sample_classification_data: pl.DataFrame,
    cuda_context: TrainingContext,
) -> None:
    """GPU OOM on lightgbm path → WARN log + CPU retry + device.backend=='cpu'."""
    state = _install_oom_then_ok_trainer(monkeypatch)
    caplog.set_level(logging.WARNING, logger="kailash_ml.trainable")

    estimator = _make_estimator()
    trainable = LightGBMTrainable(
        estimator=estimator, target="target", task="classification"
    )
    result = trainable.fit(sample_classification_data, context=cuda_context)

    assert state["calls"] == 2, "expected one OOM + one CPU retry"
    assert len(state["instances"]) == 2

    warn_records = [
        r
        for r in caplog.records
        if r.name == "kailash_ml.trainable" and r.levelno == logging.WARNING
    ]
    assert any(
        "lightgbm.gpu.oom_fallback" in r.getMessage() for r in warn_records
    ), f"missing lightgbm.gpu.oom_fallback in {[r.getMessage() for r in warn_records]}"
    fallback_rec = next(
        r for r in warn_records if "lightgbm.gpu.oom_fallback" in r.getMessage()
    )
    assert fallback_rec.fallback_reason == "oom"
    assert fallback_rec.fallback_backend == "cpu"
    assert fallback_rec.requested_backend == "cuda"
    assert fallback_rec.error_class == "_FakeLightGBMError"

    assert isinstance(result, TrainingResult)
    assert result.device is not None
    assert result.device.backend == "cpu"
    assert result.device.fallback_reason == "oom"
    assert result.device_used == "cpu"
    assert result.accelerator == "cpu"
    # Estimator was re-pointed at cpu for the retry.
    estimator.set_params.assert_any_call(device_type="cpu")


def test_non_oom_exception_does_not_trigger_fallback(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sample_classification_data: pl.DataFrame,
    cuda_context: TrainingContext,
) -> None:
    """Non-OOM exceptions propagate; zero WARN log; no second Trainer."""
    state = _install_non_oom_trainer(monkeypatch)
    caplog.set_level(logging.WARNING, logger="kailash_ml.trainable")

    estimator = _make_estimator()
    trainable = LightGBMTrainable(
        estimator=estimator, target="target", task="classification"
    )

    with pytest.raises(RuntimeError, match="totally unrelated bug"):
        trainable.fit(sample_classification_data, context=cuda_context)

    assert state["calls"] == 1
    assert len(state["instances"]) == 1
    fallback_warns = [
        r
        for r in caplog.records
        if r.name == "kailash_ml.trainable"
        and r.levelno == logging.WARNING
        and "lightgbm.gpu.oom_fallback" in r.getMessage()
    ]
    assert fallback_warns == [], "no fallback WARN should fire on non-OOM"


def test_cpu_request_oom_does_not_retry(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sample_classification_data: pl.DataFrame,
    cpu_context: TrainingContext,
) -> None:
    """If ctx.backend=='cpu' the fallback target is the same — propagate."""
    state = _install_always_oom_trainer(monkeypatch)
    caplog.set_level(logging.WARNING, logger="kailash_ml.trainable")

    estimator = _make_estimator()
    trainable = LightGBMTrainable(
        estimator=estimator, target="target", task="classification"
    )

    with pytest.raises(_FakeLightGBMError, match="out of memory"):
        trainable.fit(sample_classification_data, context=cpu_context)

    assert state["calls"] == 1, "CPU-requested OOM must NOT retry"
    fallback_warns = [
        r
        for r in caplog.records
        if r.name == "kailash_ml.trainable"
        and r.levelno == logging.WARNING
        and "lightgbm.gpu.oom_fallback" in r.getMessage()
    ]
    assert fallback_warns == [], "no fallback WARN when already on CPU"


def test_device_report_post_fallback_carries_oom_reason(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sample_classification_data: pl.DataFrame,
    cuda_context: TrainingContext,
) -> None:
    """Full DeviceReport shape after OOM→CPU fallback (revised-stack §54-78)."""
    _install_oom_then_ok_trainer(monkeypatch)
    caplog.set_level(logging.WARNING, logger="kailash_ml.trainable")

    estimator = _make_estimator()
    trainable = LightGBMTrainable(
        estimator=estimator, target="target", task="classification"
    )
    result = trainable.fit(sample_classification_data, context=cuda_context)

    report = result.device
    assert isinstance(report, DeviceReport)
    assert report.family == "lightgbm"
    assert report.backend == "cpu"
    assert report.device_string == "cpu"
    assert report.precision == "32-true"
    assert report.fallback_reason == "oom"
    assert report.array_api is False

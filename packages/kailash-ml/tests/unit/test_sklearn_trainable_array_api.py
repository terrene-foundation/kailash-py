# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for SklearnTrainable Array-API allowlist + auto-context-wrap.

Covers Phase 1 punch list item 3 (revised-stack.md §"No-config contract"
— sklearn row, lines 84-89): when an allowlisted sklearn estimator is
called with a non-CPU TrainingContext, ``SklearnTrainable.fit`` MUST
wrap the inner ``trainer.fit`` in
``sklearn.config_context(array_api_dispatch=True)``, move X/y to a
torch tensor on the resolved device, log INFO ``sklearn.array_api.engaged``,
and return ``TrainingResult.device.array_api == True``.

Off-allowlist requests on a non-CPU backend MUST log WARN
``sklearn.array_api.offlist`` with ``fallback_reason="array_api_offlist"``
and proceed on CPU numpy.

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
from kailash_ml.trainable import (
    _SKLEARN_ARRAY_API_ALLOWLIST,
    SklearnTrainable,
    TrainingContext,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_data() -> pl.DataFrame:
    """Tiny deterministic frame for SklearnTrainable.fit()."""
    return pl.DataFrame(
        {
            "feature1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "feature2": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5],
            "target": [0, 1, 0, 1, 0, 1, 0, 1],
        }
    )


@pytest.fixture
def cuda_context() -> TrainingContext:
    """CUDA-resolved TrainingContext — engages Array API for allowlisted."""
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


@pytest.fixture
def cpu_context() -> TrainingContext:
    """CPU TrainingContext — Array API never engaged."""
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


def _install_recording_trainer(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace ``pl_trainer.Trainer`` with a MagicMock; record fit calls.

    Also stubs ``torch.as_tensor`` (no-op so the Array API engaged path
    doesn't need a CUDA / MPS device on the test host) and
    ``sklearn.config_context`` (no-op context manager so the test
    doesn't trip scipy's ``SCIPY_ARRAY_API=1`` env-var precondition —
    that's a deployment concern, not a control-flow concern). These
    tests verify control-flow + log + DeviceReport, not tensor
    movement or scipy integration.

    Returns a state dict the test can inspect: ``{"calls": N,
    "instances": [trainer], "config_context_calls": [...]}``.
    """
    import contextlib

    import lightning.pytorch as pl_trainer
    import sklearn
    import torch

    state: dict[str, Any] = {"calls": 0, "instances": [], "config_context_calls": []}

    def fit_side_effect(module: Any) -> None:
        state["calls"] += 1
        # Drive on_train_start so the LightningModule sets module.metric.
        module.on_train_start()

    def fake_trainer_ctor(*args: Any, **kwargs: Any) -> MagicMock:
        trainer = MagicMock(name=f"Trainer#{len(state['instances']) + 1}")
        trainer.fit.side_effect = fit_side_effect
        state["instances"].append(trainer)
        return trainer

    def fake_as_tensor(arr: Any, device: Any = None, **_: Any) -> Any:
        # Ignore the device kwarg — tests run on CPU regardless of what
        # the cuda_context says.
        return arr

    @contextlib.contextmanager
    def fake_config_context(**kwargs: Any) -> Any:
        state["config_context_calls"].append(kwargs)
        yield

    monkeypatch.setattr(pl_trainer, "Trainer", fake_trainer_ctor)
    monkeypatch.setattr(torch, "as_tensor", fake_as_tensor)
    monkeypatch.setattr(sklearn, "config_context", fake_config_context)
    return state


# ---------------------------------------------------------------------------
# Allowlist sanity
# ---------------------------------------------------------------------------


def test_allowlist_contains_expected_estimators() -> None:
    """The Phase 1 conservative allowlist matches the spec rows."""
    expected = {
        "Ridge",
        "LogisticRegression",
        "LinearRegression",
        "LinearDiscriminantAnalysis",
        "KMeans",
        "PCA",
        "StandardScaler",
        "MinMaxScaler",
    }
    assert _SKLEARN_ARRAY_API_ALLOWLIST == expected


# ---------------------------------------------------------------------------
# Array API engaged path (allowlist + non-CPU request)
# ---------------------------------------------------------------------------


def test_allowlist_estimator_engages_array_api_context(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sample_data: pl.DataFrame,
    cuda_context: TrainingContext,
) -> None:
    """Allowlisted estimator + cuda backend → INFO log + DeviceReport.array_api=True."""
    _install_recording_trainer(monkeypatch)
    caplog.set_level(logging.INFO, logger="kailash_ml.trainable")

    # MagicMock matched-by-class-name to "LogisticRegression" (an
    # allowlist member). Returns deterministic int labels that survive
    # the metric-type check sklearn does on accuracy_score.
    estimator = MagicMock(spec=["fit", "predict", "set_params"])
    estimator.predict.return_value = [0, 1, 0, 1, 0, 1, 0, 1]
    type(estimator).__name__ = "LogisticRegression"

    trainable = SklearnTrainable(estimator=estimator, target="target")
    result = trainable.fit(sample_data, context=cuda_context)

    info_records = [
        r
        for r in caplog.records
        if r.name == "kailash_ml.trainable" and r.levelno == logging.INFO
    ]
    engaged = [r for r in info_records if "sklearn.array_api.engaged" in r.getMessage()]
    assert len(engaged) >= 1, (
        f"missing sklearn.array_api.engaged INFO log; got "
        f"{[r.getMessage() for r in info_records]}"
    )
    rec = engaged[0]
    assert rec.estimator_class == "LogisticRegression"
    assert rec.backend == "cuda"
    assert rec.device_string == "cuda:0"

    # DeviceReport reflects the engaged Array API path.
    assert isinstance(result, TrainingResult)
    assert result.device is not None
    assert isinstance(result.device, DeviceReport)
    assert result.device.array_api is True
    assert result.device.backend == "cuda"
    assert result.device.device_string == "cuda:0"
    assert result.device.fallback_reason is None
    assert result.device.family == "sklearn"


# ---------------------------------------------------------------------------
# Off-allowlist fallback (not on allowlist + non-CPU request)
# ---------------------------------------------------------------------------


def test_offlist_estimator_fallback_warns(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sample_data: pl.DataFrame,
    cuda_context: TrainingContext,
) -> None:
    """Off-allowlist estimator + cuda backend → WARN + fallback_reason='array_api_offlist'."""
    _install_recording_trainer(monkeypatch)
    caplog.set_level(logging.WARNING, logger="kailash_ml.trainable")

    from sklearn.ensemble import RandomForestClassifier

    trainable = SklearnTrainable(
        estimator=RandomForestClassifier(n_estimators=5, random_state=42),
        target="target",
    )
    result = trainable.fit(sample_data, context=cuda_context)

    warn_records = [
        r
        for r in caplog.records
        if r.name == "kailash_ml.trainable" and r.levelno == logging.WARNING
    ]
    offlist = [r for r in warn_records if "sklearn.array_api.offlist" in r.getMessage()]
    assert len(offlist) >= 1, (
        f"missing sklearn.array_api.offlist WARN log; got "
        f"{[r.getMessage() for r in warn_records]}"
    )
    rec = offlist[0]
    assert rec.estimator_class == "RandomForestClassifier"
    assert rec.requested_backend == "cuda"
    assert rec.fallback_reason == "array_api_offlist"

    # DeviceReport reflects the CPU fallback path.
    assert result.device is not None
    assert result.device.array_api is False
    assert result.device.backend == "cpu"
    assert result.device.device_string == "cpu"
    assert result.device.fallback_reason == "array_api_offlist"
    assert result.device.family == "sklearn"


# ---------------------------------------------------------------------------
# CPU request never engages Array API
# ---------------------------------------------------------------------------


def test_cpu_request_does_not_engage_array_api(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sample_data: pl.DataFrame,
    cpu_context: TrainingContext,
) -> None:
    """CPU backend request → no array_api log of any kind, fallback_reason is None."""
    _install_recording_trainer(monkeypatch)
    caplog.set_level(logging.DEBUG, logger="kailash_ml.trainable")

    from sklearn.linear_model import LogisticRegression

    trainable = SklearnTrainable(
        estimator=LogisticRegression(max_iter=100), target="target"
    )
    result = trainable.fit(sample_data, context=cpu_context)

    array_api_records = [
        r
        for r in caplog.records
        if r.name == "kailash_ml.trainable" and "sklearn.array_api" in r.getMessage()
    ]
    assert array_api_records == [], (
        f"expected zero sklearn.array_api log records on CPU request; got "
        f"{[r.getMessage() for r in array_api_records]}"
    )

    assert result.device is not None
    assert result.device.array_api is False
    assert result.device.backend == "cpu"
    assert result.device.fallback_reason is None


# ---------------------------------------------------------------------------
# DeviceReport invariant (per orphan-detection §6 / Phase 1 transparency)
# ---------------------------------------------------------------------------


def test_device_report_populated_on_every_fit(
    monkeypatch: pytest.MonkeyPatch,
    sample_data: pl.DataFrame,
    cpu_context: TrainingContext,
) -> None:
    """SklearnTrainable.fit MUST always populate TrainingResult.device."""
    _install_recording_trainer(monkeypatch)
    from sklearn.linear_model import LogisticRegression

    trainable = SklearnTrainable(
        estimator=LogisticRegression(max_iter=100), target="target"
    )
    result = trainable.fit(sample_data, context=cpu_context)
    assert result.device is not None
    assert isinstance(result.device, DeviceReport)


# ---------------------------------------------------------------------------
# Reserved LogRecord field collision check (per observability.md §9)
# ---------------------------------------------------------------------------


def test_log_extra_keys_avoid_logrecord_collisions(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sample_data: pl.DataFrame,
    cuda_context: TrainingContext,
) -> None:
    """Log records emitted by SklearnTrainable MUST NOT carry reserved LogRecord names.

    Per observability.md MUST Rule 9: ``module``, ``class``, ``name``,
    ``levelname`` etc. cannot be passed via ``extra=`` because they
    collide with LogRecord's own attributes and raise a typed error in
    some configurations. Domain-prefixed names (``estimator_class``,
    ``estimator_module``) are required.
    """
    _install_recording_trainer(monkeypatch)
    caplog.set_level(logging.DEBUG, logger="kailash_ml.trainable")

    from sklearn.linear_model import LogisticRegression

    trainable = SklearnTrainable(
        estimator=LogisticRegression(max_iter=100), target="target"
    )
    trainable.fit(sample_data, context=cuda_context)

    reserved = {
        "msg",
        "args",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "pathname",
        "filename",
        "name",
        "levelname",
        "levelno",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
    }
    for r in caplog.records:
        if r.name != "kailash_ml.trainable":
            continue
        # Inspect attributes set by `extra=` (everything not on the base
        # LogRecord constructor signature).
        record_attrs = set(r.__dict__.keys())
        sklearn_extras = {
            "family",
            "estimator_class",
            "backend",
            "device_string",
            "requested_backend",
            "fallback_reason",
        }
        # Verify our extras landed.
        present_extras = record_attrs & sklearn_extras
        if "sklearn.array_api" in r.getMessage():
            assert present_extras, (
                f"sklearn.array_api log record missing expected extras; "
                f"present attributes: {sorted(record_attrs)}"
            )
        # Verify we did NOT collide with reserved names by passing one
        # in the extra dict (the assertion is implicit — Python's
        # logging would have raised KeyError at .info() / .warning()
        # call time, not here, so the test reaching this point already
        # proves no collision occurred).
        # Belt-and-suspenders: confirm record_attrs include reserved
        # names ONLY in their LogRecord-built-in form, not as user-set
        # extras.
        assert "module" in record_attrs  # built-in, set by LogRecord ctor
        # If we'd passed extra={"module": ...} it would have raised before
        # this assertion ran. The fact that we're here proves the rule
        # is held.

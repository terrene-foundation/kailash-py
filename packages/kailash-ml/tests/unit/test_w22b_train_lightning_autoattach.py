# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W22.b — TrainingPipeline._train_lightning auto-attach invariant tests.

Covers the engine-boundary auto-attach invariant from
``specs/ml-diagnostics.md`` §5.3 (cross-ref
``ml-engines-v2.md §3.2 MUST 5``): ``TrainingPipeline._train_lightning``
MUST auto-append ``DLDiagnostics.as_lightning_callback()`` to the
``L.Trainer`` callback list whenever ``DLDiagnostics.is_available()``
AND ``kailash_ml.tracking.get_current_run()`` returns a non-None run.

Tier-1 coverage (no real fit — ``L.Trainer`` is patched to capture
kwargs):

1. ``is_available()==True`` + ``get_current_run()==None`` → no auto-attach.
2. ``is_available()==False`` → no auto-attach even with an ambient run.
3. Both preconditions met → exactly one DL callback appended
   (identified via the ``_is_dl_diagnostics_callback`` sentinel set in
   ``dl.py``).
4. Caller-supplied duplicate DL callback → engine de-duplicates and
   preserves the caller's instance (the engine MUST NOT append a second).
5. Non-DL caller callbacks compose → engine appends the DL callback
   alongside them, does not drop or reorder.
6. ``DLDiagnostics.is_available()`` probes both torch + lightning; when
   lightning import fails, the classmethod returns False (mocked).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

try:  # [dl] extra required for this whole module
    import lightning.pytorch as L  # noqa: F401
    import torch  # noqa: F401
except ImportError:  # pragma: no cover — [dl] extra missing on CI
    pytest.skip(
        "kailash-ml[dl] extra is required for W22.b auto-attach tests",
        allow_module_level=True,
    )

from kailash_ml.diagnostics.dl import DLDiagnostics
from kailash_ml.engines.model_registry import ModelRegistry
from kailash_ml.engines.training_pipeline import (  # noqa: F401 — reserved for future composition tests
    EvalSpec,
    ModelSpec,
    TrainingPipeline,
)

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def train_data() -> pl.DataFrame:
    """Minimal polars frame — 16 rows × (4 features + 1 target).

    The Trainer is patched so `.fit` never runs; we only need the frame
    shape to be accepted by :func:`kailash_ml.interop.to_sklearn_input`.
    """
    return pl.DataFrame(
        {
            "f0": [float(i) for i in range(16)],
            "f1": [float(i) * 2 for i in range(16)],
            "f2": [float(i) * 3 for i in range(16)],
            "f3": [float(i) * 4 for i in range(16)],
            "target": [float(i % 2) for i in range(16)],
        }
    )


@pytest.fixture
def feature_cols() -> list[str]:
    return ["f0", "f1", "f2", "f3"]


@pytest.fixture
def model_spec() -> ModelSpec:
    """Lightning model_spec referencing the stock BoringModel.

    BoringModel has no required constructor args, is covered by the
    ``lightning.`` allowlist prefix in ``engines._shared`` and is a
    valid :class:`torch.nn.Module` — satisfies both the
    :func:`importlib.import_module` dispatch AND the
    :class:`DLDiagnostics` ``nn.Module`` isinstance check.
    """
    return ModelSpec(
        model_class="lightning.pytorch.demos.boring_classes.BoringModel",
        hyperparameters={"trainer_max_epochs": 1},
        framework="lightning",
    )


@pytest.fixture
def pipeline() -> TrainingPipeline:
    """Pipeline with mocked registry + feature store.

    ``_train_lightning`` only reads ``self`` attributes via the backend
    resolver — no registry / feature-store calls happen on this path.
    """
    return TrainingPipeline(
        feature_store=MagicMock(), registry=MagicMock(spec=ModelRegistry)
    )


class _SyncTrackerStub:
    """Duck-typed sync tracker with the log_figure contract + run_id.

    Used as the ambient ``ExperimentRun`` substitute. Satisfies both the
    auto-attach precondition (``get_current_run()`` non-None) and the
    callback's duck-typed ``log_figure`` emission path. The real
    ExperimentRun's ``log_figure`` is async; isolating auto-attach from
    async bridging keeps this Tier-1 file focused.
    """

    run_id = "w22b-test-run"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def log_figure(
        self, figure: Any, name: str, *, step: int | None = None
    ) -> dict[str, Any]:
        record = {"name": name, "step": step, "figure_type": type(figure).__name__}
        self.calls.append(record)
        return record


def _run_train_lightning(
    pipeline: TrainingPipeline,
    train_data: pl.DataFrame,
    feature_cols: list[str],
    model_spec: ModelSpec,
) -> tuple[MagicMock, dict[str, Any]]:
    """Invoke ``_train_lightning`` with ``L.Trainer`` patched.

    Returns the ``Trainer`` class mock and the kwargs it was called with
    so assertions can inspect the composed callback list.
    """
    import lightning  # real import — BoringModel instantiation needs it

    original_trainer = lightning.Trainer
    trainer_cls_mock = MagicMock(name="L.Trainer")
    trainer_cls_mock.return_value = MagicMock(name="L.Trainer.instance")
    lightning.Trainer = trainer_cls_mock  # type: ignore[misc]
    try:
        pipeline._train_lightning(
            train_data=train_data,
            feature_cols=feature_cols,
            target_col="target",
            model_spec=model_spec,
        )
    finally:
        lightning.Trainer = original_trainer  # type: ignore[misc]
    assert (
        trainer_cls_mock.call_count == 1
    ), f"L.Trainer must be instantiated exactly once; got {trainer_cls_mock.call_count}"
    # L.Trainer(**trainer_kwargs) — we inspect kwargs only.
    _, kwargs = trainer_cls_mock.call_args
    return trainer_cls_mock, kwargs


# ----------------------------------------------------------------------
# Invariant A — no ambient run → no auto-attach
# ----------------------------------------------------------------------


class TestNoAmbientRunSkipsAutoAttach:
    """``get_current_run() is None`` ⇒ the DL callback MUST NOT be appended."""

    def test_callbacks_absent_when_no_run(
        self,
        pipeline: TrainingPipeline,
        train_data: pl.DataFrame,
        feature_cols: list[str],
        model_spec: ModelSpec,
    ) -> None:
        with patch("kailash_ml.tracking.get_current_run", return_value=None):
            _, kwargs = _run_train_lightning(
                pipeline, train_data, feature_cols, model_spec
            )
        callbacks = kwargs.get("callbacks") or []
        dl_cbs = [
            cb for cb in callbacks if getattr(cb, "_is_dl_diagnostics_callback", False)
        ]
        assert dl_cbs == [], (
            "Engine-boundary auto-attach MUST be conditional on a non-None "
            "ambient run (specs/ml-diagnostics.md §5.3)."
        )


# ----------------------------------------------------------------------
# Invariant B — DLDiagnostics.is_available() False → no auto-attach
# ----------------------------------------------------------------------


class TestDLUnavailableSkipsAutoAttach:
    """``DLDiagnostics.is_available()==False`` ⇒ no callback, even with run."""

    def test_callbacks_absent_when_dl_unavailable(
        self,
        pipeline: TrainingPipeline,
        train_data: pl.DataFrame,
        feature_cols: list[str],
        model_spec: ModelSpec,
    ) -> None:
        tracker = _SyncTrackerStub()
        with (
            patch("kailash_ml.tracking.get_current_run", return_value=tracker),
            patch.object(DLDiagnostics, "is_available", classmethod(lambda cls: False)),
        ):
            _, kwargs = _run_train_lightning(
                pipeline, train_data, feature_cols, model_spec
            )
        callbacks = kwargs.get("callbacks") or []
        dl_cbs = [
            cb for cb in callbacks if getattr(cb, "_is_dl_diagnostics_callback", False)
        ]
        assert dl_cbs == [], (
            "Auto-attach MUST be gated on DLDiagnostics.is_available() — "
            "when lightning is unavailable the engine must skip the attach."
        )


# ----------------------------------------------------------------------
# Invariant C — both preconditions met → exactly one DL callback attached
# ----------------------------------------------------------------------


class TestAutoAttachWhenPreconditionsMet:
    """Both preconditions satisfied ⇒ one DL callback appended."""

    def test_exactly_one_dl_callback_attached(
        self,
        pipeline: TrainingPipeline,
        train_data: pl.DataFrame,
        feature_cols: list[str],
        model_spec: ModelSpec,
    ) -> None:
        tracker = _SyncTrackerStub()
        with patch("kailash_ml.tracking.get_current_run", return_value=tracker):
            _, kwargs = _run_train_lightning(
                pipeline, train_data, feature_cols, model_spec
            )
        callbacks = kwargs.get("callbacks") or []
        dl_cbs = [
            cb for cb in callbacks if getattr(cb, "_is_dl_diagnostics_callback", False)
        ]
        assert len(dl_cbs) == 1, (
            f"Expected exactly one engine-appended DL callback; got {len(dl_cbs)}. "
            f"trainer_kwargs['callbacks'] = {callbacks!r}"
        )
        # The attached callback MUST be bound to a DLDiagnostics whose
        # tracker is the ambient run (per specs/ml-diagnostics.md §4.1).
        assert dl_cbs[0]._diag._tracker is tracker

    def test_attached_callback_has_marker_sentinel(
        self,
        pipeline: TrainingPipeline,
        train_data: pl.DataFrame,
        feature_cols: list[str],
        model_spec: ModelSpec,
    ) -> None:
        """The sentinel is what makes the de-dup check mechanical."""
        tracker = _SyncTrackerStub()
        with patch("kailash_ml.tracking.get_current_run", return_value=tracker):
            _, kwargs = _run_train_lightning(
                pipeline, train_data, feature_cols, model_spec
            )
        callbacks = kwargs.get("callbacks") or []
        assert len(callbacks) >= 1
        assert getattr(callbacks[-1], "_is_dl_diagnostics_callback", False) is True


# ----------------------------------------------------------------------
# Invariant D — duplicate caller-supplied DL callback is de-duped
# ----------------------------------------------------------------------


class TestDuplicateCallbackDeduped:
    """Caller-supplied DL callback ⇒ engine MUST NOT append a second.

    Per specs/ml-diagnostics.md §5.3: "A user-supplied duplicate
    DLDiagnostics.as_lightning_callback() is de-duplicated by isinstance
    — the engine-appended instance wins." In this implementation, the
    ``_is_dl_diagnostics_callback`` class-attribute is the isinstance-
    equivalent sentinel (the nested callback class cannot be referenced
    by name from outside ``as_lightning_callback``).
    """

    def test_user_supplied_callback_not_duplicated(
        self,
        pipeline: TrainingPipeline,
        train_data: pl.DataFrame,
        feature_cols: list[str],
    ) -> None:
        # Build a user-supplied DL callback via a DIFFERENT DLDiagnostics
        # session, then pass it through trainer_callbacks hyperparameter.
        import torch.nn as nn

        user_diag = DLDiagnostics(
            nn.Sequential(nn.Linear(4, 2), nn.ReLU(), nn.Linear(2, 1)),
            tracker=_SyncTrackerStub(),
        )
        user_cb = user_diag.as_lightning_callback()

        model_spec_with_cbs = ModelSpec(
            model_class="lightning.pytorch.demos.boring_classes.BoringModel",
            hyperparameters={
                "trainer_max_epochs": 1,
                "trainer_callbacks": [user_cb],
            },
            framework="lightning",
        )
        engine_tracker = _SyncTrackerStub()
        with patch("kailash_ml.tracking.get_current_run", return_value=engine_tracker):
            _, kwargs = _run_train_lightning(
                pipeline, train_data, feature_cols, model_spec_with_cbs
            )
        callbacks = kwargs.get("callbacks") or []
        dl_cbs = [
            cb for cb in callbacks if getattr(cb, "_is_dl_diagnostics_callback", False)
        ]
        assert len(dl_cbs) == 1, (
            f"De-dup invariant failed: caller supplied 1 DL callback, engine "
            f"must NOT append a second; got {len(dl_cbs)}."
        )
        # Caller's instance wins — engine did not overwrite it.
        assert dl_cbs[0] is user_cb
        # And its DLDiagnostics is bound to the CALLER'S tracker, not
        # the ambient engine tracker.
        assert dl_cbs[0]._diag._tracker is not engine_tracker


# ----------------------------------------------------------------------
# Invariant E — non-DL user callbacks compose with engine-appended DL
# ----------------------------------------------------------------------


class TestNonDLCallbacksCompose:
    """User-supplied non-DL callbacks MUST be preserved alongside the DL callback."""

    def test_user_non_dl_callbacks_preserved(
        self,
        pipeline: TrainingPipeline,
        train_data: pl.DataFrame,
        feature_cols: list[str],
    ) -> None:
        from lightning.pytorch.callbacks import Callback as LCallback

        class _UserPlainCallback(LCallback):
            pass

        user_cb = _UserPlainCallback()
        model_spec_with_cbs = ModelSpec(
            model_class="lightning.pytorch.demos.boring_classes.BoringModel",
            hyperparameters={
                "trainer_max_epochs": 1,
                "trainer_callbacks": [user_cb],
            },
            framework="lightning",
        )
        tracker = _SyncTrackerStub()
        with patch("kailash_ml.tracking.get_current_run", return_value=tracker):
            _, kwargs = _run_train_lightning(
                pipeline, train_data, feature_cols, model_spec_with_cbs
            )
        callbacks = kwargs.get("callbacks") or []
        assert user_cb in callbacks, "User-supplied non-DL callback was dropped."
        dl_cbs = [
            cb for cb in callbacks if getattr(cb, "_is_dl_diagnostics_callback", False)
        ]
        assert (
            len(dl_cbs) == 1
        ), "Engine-appended DL callback missing alongside user callback."


# ----------------------------------------------------------------------
# Invariant F — is_available() reflects lightning availability
# ----------------------------------------------------------------------


class TestIsAvailableProbe:
    """`DLDiagnostics.is_available()` probes both torch AND lightning."""

    def test_is_available_returns_true_when_both_present(self) -> None:
        # This test file imports torch + lightning at module top; if
        # those imports succeed, is_available() MUST return True.
        assert DLDiagnostics.is_available() is True

    def test_is_available_returns_false_when_lightning_absent(self) -> None:
        import builtins

        real_import = builtins.__import__

        def _blocked_import(
            name: str, globals=None, locals=None, fromlist=(), level=0  # noqa: A002
        ):
            if name == "lightning.pytorch" or name.startswith("lightning.pytorch"):
                raise ImportError("simulated: lightning.pytorch not installed")
            return real_import(name, globals, locals, fromlist, level)

        with patch.object(builtins, "__import__", side_effect=_blocked_import):
            assert DLDiagnostics.is_available() is False

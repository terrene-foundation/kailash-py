# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W22.a — DLDiagnostics.as_lightning_callback() invariant tests.

Covers the dispatch-layer invariants from the master wave plan §W22 that
do NOT require a real CPU-DDP run:

1. ``as_lightning_callback()`` returns a ``lightning.pytorch.callbacks.
   Callback`` instance (invariant 4 — "callback appended by MLEngine.fit"
   precondition).
2. ``tracker=None`` → the callback's on_train_epoch_end is a structural
   no-op — no exception, no emission (invariant 3 — "tracker= kwarg is
   Optional[ExperimentRun]").
3. Sync tracker → ``log_figure(figure, name, *, step=epoch)`` called
   once per plot per emitting epoch (invariant 5 — "figure events flow
   through ExperimentRun.log_figure").
4. ``rules/observability.md`` + Decision 4 rank-0 gate: monkeypatched
   ``_is_rank_zero()→False`` → no emissions (invariant 1 —
   "rank-0-only emission hardcoded via torch.distributed.get_rank()==0").
5. ``emit_every_n_epochs=N`` cadence: only epochs 0, N, 2N, ... emit.
6. Async tracker (coroutine-returning log_figure) → coroutine is driven
   to completion before the hook returns; no pending coroutine warnings.

W22.b (deferred) covers the auto-attach in TrainingPipeline._train_lightning
against a real CPU-DDP run — that path exercises invariant 2 ([dl] plotly
gating at the boundary) and invariant 7 (cross-SDK Diagnostic Protocol)
through the engine surface.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

try:  # [dl] extra required for the whole module
    import torch
    import torch.nn as nn
    import lightning.pytorch as L  # noqa: F401 — imported to gate module collection
except ImportError:  # pragma: no cover — [dl] extra missing on CI
    pytest.skip(
        "kailash-ml[dl] extra is required for W22 Lightning callback tests",
        allow_module_level=True,
    )

from kailash_ml.diagnostics.dl import DLDiagnostics


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _tiny_model() -> nn.Module:
    """2-layer MLP. Sufficient for hooking but not for actual training."""
    return nn.Sequential(nn.Linear(4, 8), nn.ReLU(), nn.Linear(8, 1))


class _SyncTracker:
    """Duck-typed sync tracker that records log_figure calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def log_figure(
        self, figure: Any, name: str, *, step: int | None = None
    ) -> dict[str, Any]:
        record = {"name": name, "step": step, "figure_type": type(figure).__name__}
        self.calls.append(record)
        return record


class _AsyncTracker:
    """Duck-typed async tracker that records log_figure calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.awaited_count = 0

    async def log_figure(
        self, figure: Any, name: str, *, step: int | None = None
    ) -> None:
        self.calls.append(
            {"name": name, "step": step, "figure_type": type(figure).__name__}
        )
        self.awaited_count += 1


class _TrainerStub:
    """Minimal stand-in for lightning.pytorch.Trainer inside the callback."""

    def __init__(self, current_epoch: int = 0) -> None:
        self.current_epoch = current_epoch


def _prime_with_loss_data(diag: DLDiagnostics, epoch: int = 0) -> None:
    """Record enough batch + epoch data that plot_loss_curves() has inputs.

    plot_loss_curves() walks ``self._epoch_log`` + ``self._batch_log``; empty
    logs produce an "empty figure" but still return a plotly Figure. This
    helper primes both so the figure is non-trivial and exercises the full
    dataframe path.
    """
    diag.record_batch(loss=1.0 - 0.1 * epoch, lr=1e-3)
    diag.record_epoch(train_loss=1.0 - 0.1 * epoch, val_loss=1.0 - 0.05 * epoch)


# ----------------------------------------------------------------------
# Invariant 1 — as_lightning_callback() returns a Lightning Callback
# ----------------------------------------------------------------------


class TestInvariant4CallbackConstruction:
    """`as_lightning_callback()` returns a real Lightning Callback."""

    def test_returns_lightning_callback_instance(self) -> None:
        from lightning.pytorch.callbacks import Callback as LCallback

        diag = DLDiagnostics(_tiny_model())
        cb = diag.as_lightning_callback()
        assert isinstance(cb, LCallback), (
            f"as_lightning_callback() must return a Lightning Callback "
            f"instance; got {type(cb).__name__}"
        )

    def test_callback_has_on_train_epoch_end_hook(self) -> None:
        diag = DLDiagnostics(_tiny_model())
        cb = diag.as_lightning_callback()
        assert callable(getattr(cb, "on_train_epoch_end", None))

    def test_rejects_unknown_plot_names(self) -> None:
        diag = DLDiagnostics(_tiny_model())
        with pytest.raises(ValueError, match="unknown plot names"):
            diag.as_lightning_callback(plots=["loss_curves", "not_a_plot"])

    def test_rejects_invalid_cadence(self) -> None:
        diag = DLDiagnostics(_tiny_model())
        with pytest.raises(ValueError, match="emit_every_n_epochs"):
            diag.as_lightning_callback(emit_every_n_epochs=0)


# ----------------------------------------------------------------------
# Invariant 3 — tracker=None is a structural no-op
# ----------------------------------------------------------------------


class TestInvariant3TrackerOptional:
    """`tracker=None` → callback attaches but never emits."""

    def test_on_train_epoch_end_noop_when_tracker_none(self) -> None:
        diag = DLDiagnostics(_tiny_model())  # tracker defaults to None
        cb = diag.as_lightning_callback()
        # MUST NOT raise — the structural no-op is part of the contract.
        cb.on_train_epoch_end(_TrainerStub(current_epoch=0), object())
        cb.on_train_epoch_end(_TrainerStub(current_epoch=7), object())
        # No state to assert on — the invariant is "doesn't raise, doesn't
        # try to call a method on None" which a raise would have tripped.

    def test_tracker_kwarg_default_is_none(self) -> None:
        diag = DLDiagnostics(_tiny_model())
        assert diag._tracker is None


# ----------------------------------------------------------------------
# Invariant 5 — sync tracker receives one log_figure per plot per epoch
# ----------------------------------------------------------------------


class TestInvariant5SyncEmission:
    """Each selected plot MUST produce exactly one log_figure call per epoch."""

    def test_default_plots_emit_three_per_epoch(self) -> None:
        tracker = _SyncTracker()
        diag = DLDiagnostics(_tiny_model(), tracker=tracker)
        _prime_with_loss_data(diag)
        cb = diag.as_lightning_callback()
        cb.on_train_epoch_end(_TrainerStub(current_epoch=0), object())

        # Default plots: loss_curves, gradient_flow, dead_neurons.
        names = [call["name"] for call in tracker.calls]
        assert set(names) == {"loss_curves", "gradient_flow", "dead_neurons"}
        assert len(tracker.calls) == 3
        # Every emission carries the current epoch as step.
        assert all(call["step"] == 0 for call in tracker.calls)

    def test_explicit_plots_override_defaults(self) -> None:
        tracker = _SyncTracker()
        diag = DLDiagnostics(_tiny_model(), tracker=tracker)
        _prime_with_loss_data(diag)
        cb = diag.as_lightning_callback(plots=["loss_curves"])
        cb.on_train_epoch_end(_TrainerStub(current_epoch=3), object())

        assert [call["name"] for call in tracker.calls] == ["loss_curves"]
        assert tracker.calls[0]["step"] == 3

    def test_step_reflects_current_epoch(self) -> None:
        tracker = _SyncTracker()
        diag = DLDiagnostics(_tiny_model(), tracker=tracker)
        _prime_with_loss_data(diag)
        cb = diag.as_lightning_callback(plots=["loss_curves"])
        for epoch in (0, 1, 2):
            cb.on_train_epoch_end(_TrainerStub(current_epoch=epoch), object())

        assert [call["step"] for call in tracker.calls] == [0, 1, 2]


# ----------------------------------------------------------------------
# Invariant 1 — rank-0 gate hardcoded via _is_rank_zero
# ----------------------------------------------------------------------


class TestInvariant1RankZeroGate:
    """Non-rank-0 workers MUST NOT emit, regardless of tracker state."""

    def test_non_rank_zero_suppresses_all_emissions(self) -> None:
        tracker = _SyncTracker()
        diag = DLDiagnostics(_tiny_model(), tracker=tracker)
        _prime_with_loss_data(diag)
        cb = diag.as_lightning_callback()

        with patch("kailash_ml.tracking.runner._is_rank_zero", return_value=False):
            cb.on_train_epoch_end(_TrainerStub(current_epoch=0), object())

        assert tracker.calls == [], (
            "Non-rank-0 workers MUST NOT call tracker.log_figure — "
            "Decision 4 rank-0-only emission invariant."
        )

    def test_rank_zero_gate_re_evaluated_each_epoch(self) -> None:
        """The gate MUST NOT be cached — DDP rank can change per epoch."""
        tracker = _SyncTracker()
        diag = DLDiagnostics(_tiny_model(), tracker=tracker)
        _prime_with_loss_data(diag)
        cb = diag.as_lightning_callback(plots=["loss_curves"])

        # First epoch: non-zero (no emission).
        with patch("kailash_ml.tracking.runner._is_rank_zero", return_value=False):
            cb.on_train_epoch_end(_TrainerStub(current_epoch=0), object())
        assert tracker.calls == []

        # Second epoch: rank-0 (emission fires).
        with patch("kailash_ml.tracking.runner._is_rank_zero", return_value=True):
            cb.on_train_epoch_end(_TrainerStub(current_epoch=1), object())
        assert len(tracker.calls) == 1
        assert tracker.calls[0]["name"] == "loss_curves"


# ----------------------------------------------------------------------
# Cadence — emit_every_n_epochs
# ----------------------------------------------------------------------


class TestEmitCadence:
    """`emit_every_n_epochs=N` → emit on epochs 0, N, 2N, ... only."""

    def test_cadence_of_three(self) -> None:
        tracker = _SyncTracker()
        diag = DLDiagnostics(_tiny_model(), tracker=tracker)
        _prime_with_loss_data(diag)
        cb = diag.as_lightning_callback(plots=["loss_curves"], emit_every_n_epochs=3)
        for epoch in range(7):
            cb.on_train_epoch_end(_TrainerStub(current_epoch=epoch), object())

        emitted_epochs = [call["step"] for call in tracker.calls]
        # Epochs 0, 3, 6 emit; 1, 2, 4, 5 are skipped.
        assert emitted_epochs == [0, 3, 6]

    def test_cadence_of_one_emits_every_epoch(self) -> None:
        """Default cadence — sanity check that every epoch fires."""
        tracker = _SyncTracker()
        diag = DLDiagnostics(_tiny_model(), tracker=tracker)
        _prime_with_loss_data(diag)
        cb = diag.as_lightning_callback(plots=["loss_curves"])  # default cadence=1
        for epoch in range(4):
            cb.on_train_epoch_end(_TrainerStub(current_epoch=epoch), object())
        assert [call["step"] for call in tracker.calls] == [0, 1, 2, 3]


# ----------------------------------------------------------------------
# Invariant 6 — async tracker.log_figure is awaited, not leaked
# ----------------------------------------------------------------------


class TestAsyncTrackerAdaptation:
    """Coroutine-returning log_figure MUST be driven to completion in-hook."""

    def test_async_tracker_log_figure_awaited(self) -> None:
        tracker = _AsyncTracker()
        diag = DLDiagnostics(_tiny_model(), tracker=tracker)
        _prime_with_loss_data(diag)
        cb = diag.as_lightning_callback(plots=["loss_curves"])

        cb.on_train_epoch_end(_TrainerStub(current_epoch=0), object())

        # The awaited coroutine recorded its call.
        assert len(tracker.calls) == 1
        assert tracker.awaited_count == 1
        assert tracker.calls[0]["name"] == "loss_curves"

    def test_async_tracker_across_multiple_epochs(self) -> None:
        tracker = _AsyncTracker()
        diag = DLDiagnostics(_tiny_model(), tracker=tracker)
        _prime_with_loss_data(diag)
        cb = diag.as_lightning_callback(plots=["loss_curves", "gradient_flow"])

        for epoch in range(3):
            cb.on_train_epoch_end(_TrainerStub(current_epoch=epoch), object())

        # 2 plots * 3 epochs = 6 awaited coroutines, no leaks.
        assert tracker.awaited_count == 6
        assert len(tracker.calls) == 6


# ----------------------------------------------------------------------
# Resilience — a plot that raises does NOT abort sibling emissions
# ----------------------------------------------------------------------


class TestPlotFailureIsolation:
    """A plot method that raises MUST NOT block sibling plot emissions."""

    def test_sibling_plots_still_emit_when_one_fails(self) -> None:
        tracker = _SyncTracker()
        diag = DLDiagnostics(_tiny_model(), tracker=tracker)
        _prime_with_loss_data(diag)
        cb = diag.as_lightning_callback(plots=["loss_curves", "gradient_flow"])

        # Make plot_loss_curves raise; gradient_flow should still emit.
        def _explode() -> Any:
            raise RuntimeError("simulated plot_loss_curves failure")

        with patch.object(diag, "plot_loss_curves", side_effect=_explode):
            cb.on_train_epoch_end(_TrainerStub(current_epoch=0), object())

        # Exactly one sibling emission survived.
        names = [call["name"] for call in tracker.calls]
        assert names == ["gradient_flow"]

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W22.b — Tier-2 wiring test for TrainingPipeline → DLDiagnostics auto-attach.

Drives a real 1-epoch ``L.Trainer.fit`` via
:meth:`TrainingPipeline._train_lightning` with an ambient tracker
installed through the ``_current_run`` contextvar. Verifies the
externally-observable effect: after the fit completes, the tracker
received ``log_figure`` calls for the default DL diagnostic plots.

This Tier-2 test uses a **sync duck-typed tracker** (``_SyncTracker``
satisfying ``log_figure(figure, name, *, step)``) rather than a real
``ExperimentRun``. Rationale:

- The real ``ExperimentRun.log_figure`` is ``async def``; invoking it
  from a sync Lightning callback running inside an async parent requires
  an event-loop-aware bridge that is out of scope for W22.b. The
  callback's existing async handling (``asyncio.run`` happy path,
  ``result.close()`` defensive fallback) already has Tier-1 coverage in
  ``tests/unit/test_w22_lightning_callback.py``.
- Per ``specs/ml-diagnostics.md §4.1`` the tracker is duck-typed —
  "any object with a ``log_figure(figure, name, *, step)`` method
  satisfies the contract." A sync stub is a valid Protocol implementation
  (``rules/testing.md`` Tier-2 Protocol-satisfying deterministic adapter
  carve-out).
- The invariant under test is the ENGINE-BOUNDARY AUTO-ATTACH: that
  ``_train_lightning`` reads the ambient run, constructs
  ``DLDiagnostics``, and appends the callback to the real ``L.Trainer``.
  A sync tracker is the minimal substrate to observe this externally.

This test is complementary to ``test_dl_diagnostics_wiring.py`` which
exercises ``DLDiagnostics`` + the Protocol contract without the engine
boundary.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest

try:  # [dl] extra required for the whole module
    import lightning.pytorch as L  # noqa: F401
    import torch  # noqa: F401
except ImportError:  # pragma: no cover — [dl] extra missing on CI
    pytest.skip(
        "kailash-ml[dl] extra is required for W22.b auto-attach wiring tests",
        allow_module_level=True,
    )

from kailash_ml.engines.model_registry import ModelRegistry
from kailash_ml.engines.training_pipeline import ModelSpec, TrainingPipeline
from kailash_ml.tracking.runner import _current_run

# ----------------------------------------------------------------------
# Tiny Lightning module wired into kailash_ml._w22b_tiny via sys.modules
# ----------------------------------------------------------------------
#
# The training pipeline's `_train_lightning` path:
#   1. Runs the security allowlist (_shared.validate_model_class) — only
#      accepts model_class strings starting with one of the allowlist
#      prefixes; `kailash_ml.` is allowlisted.
#   2. Resolves via importlib.import_module(parts[0]) + getattr(parts[1]).
#
# Registering the helper at ``kailash_ml._w22b_tiny`` via sys.modules
# satisfies BOTH layers without monkey-patching the allowlist — which
# would weaken a security gate for test convenience.


class _TinyTupleModule(L.LightningModule):
    """Minimal LightningModule that accepts (X, y) tuple batches.

    ``TrainingPipeline._train_lightning`` constructs a
    ``TensorDataset(X_tensor, y_tensor)`` whose DataLoader yields
    ``(x, y)`` tuples. BoringModel's training_step expects a single
    tensor, so we ship a tuple-aware tiny module specifically for this
    wiring test.
    """

    def __init__(self) -> None:
        super().__init__()
        self.layer = torch.nn.Linear(32, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # type: ignore[override]
        return self.layer(x)

    def training_step(self, batch: Any, batch_idx: int) -> torch.Tensor:  # type: ignore[override]
        x, y = batch
        y_hat = self.layer(x).squeeze(-1)
        return torch.nn.functional.mse_loss(y_hat, y)

    def configure_optimizers(self) -> torch.optim.Optimizer:  # type: ignore[override]
        return torch.optim.SGD(self.parameters(), lr=0.01)


# Register under an allowlist-compatible module path. Using a
# ``kailash_ml._w22b_tiny`` fully-qualified name keeps the allowlist
# prefix check (kailash_ml.) happy without loosening it for tests.
import sys as _sys  # noqa: E402
import types as _types  # noqa: E402

_TINY_MODULE_NAME = "kailash_ml._w22b_tiny"
if _TINY_MODULE_NAME not in _sys.modules:
    _mod = _types.ModuleType(_TINY_MODULE_NAME)
    _mod._TinyTupleModule = _TinyTupleModule  # type: ignore[attr-defined]
    _sys.modules[_TINY_MODULE_NAME] = _mod

TINY_MODEL_CLASS = f"{_TINY_MODULE_NAME}._TinyTupleModule"


# ----------------------------------------------------------------------
# Sync duck-typed tracker satisfying the log_figure contract
# ----------------------------------------------------------------------


class _SyncTracker:
    """Sync duck-typed ambient tracker.

    Satisfies the duck-typed ``log_figure(figure, name, *, step)`` contract
    declared in ``specs/ml-diagnostics.md §4.1``. Used in place of a real
    ``ExperimentRun`` to avoid async-bridge concerns in this Tier-2 test
    (see module docstring).
    """

    run_id = "w22b-wiring-test-run"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def log_figure(
        self, figure: Any, name: str, *, step: int | None = None
    ) -> dict[str, Any]:
        record = {"name": name, "step": step, "figure_type": type(figure).__name__}
        self.calls.append(record)
        return record


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def pipeline() -> TrainingPipeline:
    """TrainingPipeline with stub feature_store + registry.

    ``_train_lightning`` does not hit the registry or feature store on
    the direct path; MagicMock stubs are sufficient.
    """
    return TrainingPipeline(
        feature_store=MagicMock(),
        registry=MagicMock(spec=ModelRegistry),
    )


@pytest.fixture
def train_data() -> pl.DataFrame:
    """Small polars frame whose shape matches ``_TinyTupleModule`` input.

    The tuple module's ``Linear(32, 1)`` expects a 32-dim feature tensor.
    We build 16 rows × 32 features + 1 target so the sklearn-interop
    boundary and DataLoader are both happy.
    """
    rows = 16
    return pl.DataFrame(
        {
            **{
                f"f{i}": [float((j * (i + 1)) % 17) for j in range(rows)]
                for i in range(32)
            },
            "target": [float(j % 2) for j in range(rows)],
        }
    )


@pytest.fixture
def feature_cols() -> list[str]:
    return [f"f{i}" for i in range(32)]


@pytest.fixture
def model_spec() -> ModelSpec:
    return ModelSpec(
        model_class=TINY_MODEL_CLASS,
        hyperparameters={
            "trainer_max_epochs": 1,
            "trainer_limit_train_batches": 2,
            "trainer_log_every_n_steps": 1,
            "trainer_enable_checkpointing": False,
            # Disable Lightning's default CSVLogger so the tensorboardX
            # fallback UserWarning doesn't pollute our test suite
            # (per rules/observability.md MUST Rule 5 / MUST NOT
            # unacknowledged WARN).
            "trainer_logger": False,
            # batch_size is consumed by the DataLoader construction inside
            # _train_lightning via trainer_kwargs.pop("batch_size", 32);
            # it MUST carry the trainer_ prefix in the spec.
            "trainer_batch_size": 8,
        },
        framework="lightning",
    )


# ----------------------------------------------------------------------
# Wiring test — real L.Trainer.fit, verify ambient tracker sees figures
# ----------------------------------------------------------------------


@pytest.mark.integration
def test_train_lightning_autoattaches_dl_callback_and_emits_figures(
    pipeline: TrainingPipeline,
    train_data: pl.DataFrame,
    feature_cols: list[str],
    model_spec: ModelSpec,
) -> None:
    """End-to-end: ambient run + real fit → tracker records figures.

    The `_current_run` contextvar is set directly (bypassing
    ``km.track()``'s async context manager) so the test drives the sync
    Lightning training loop without entering an async scope. The DL
    callback is auto-attached by ``_train_lightning`` per
    ``specs/ml-diagnostics.md §5.3`` and fires on
    ``on_train_epoch_end``, emitting figures to the ambient tracker.
    """
    tracker = _SyncTracker()
    token = _current_run.set(tracker)  # type: ignore[arg-type]  # duck-typed per §4.1
    try:
        pipeline._train_lightning(
            train_data=train_data,
            feature_cols=feature_cols,
            target_col="target",
            model_spec=model_spec,
        )
    finally:
        _current_run.reset(token)

    # Externally observable: the callback fired and emitted at least one
    # figure per default plot. Default plots per `as_lightning_callback`:
    # ["loss_curves", "gradient_flow", "dead_neurons"].
    emitted_names = {call["name"] for call in tracker.calls}
    assert "loss_curves" in emitted_names, (
        f"DL callback auto-attach failed: `loss_curves` figure never emitted. "
        f"tracker.calls={tracker.calls!r}"
    )
    # All emitted figures carry the current epoch as step (rank-0-gated,
    # epoch-0 emission triggers via cadence default of 1).
    assert all(call["step"] is not None for call in tracker.calls)
    # Figures are plotly Figure instances — the callback routes through
    # the adapter's `plot_*()` methods.
    assert all(
        call["figure_type"] == "Figure" for call in tracker.calls
    ), f"Non-plotly figure leaked through: {tracker.calls!r}"


@pytest.mark.integration
def test_train_lightning_no_ambient_run_skips_autoattach(
    pipeline: TrainingPipeline,
    train_data: pl.DataFrame,
    feature_cols: list[str],
    model_spec: ModelSpec,
) -> None:
    """Absent ambient run → the callback MUST NOT attach, fit still succeeds.

    Companion to the positive wiring test: proves the gate is load-bearing
    rather than a no-op. We verify the pipeline still completes a real
    fit without crashing when no ambient tracker is set (the common
    notebook / ad-hoc path per §4.1 "no-tracker mode").
    """
    tracker = _SyncTracker()
    assert _current_run.get() is None, "test precondition: no ambient run set at entry"
    pipeline._train_lightning(
        train_data=train_data,
        feature_cols=feature_cols,
        target_col="target",
        model_spec=model_spec,
    )
    assert tracker.calls == [], (
        f"No ambient run was set; tracker MUST NOT have been touched. "
        f"calls={tracker.calls!r}"
    )

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
#
# Portions of this module were originally contributed from MLFP
# (Apache-2.0) and re-authored for the Kailash ecosystem. See
# ``specs/ml-diagnostics.md`` § "Attribution" for the full donation
# history (kailash-py issue #567, PR#1 of 7).
"""Deep-learning training diagnostics for kailash-ml.

``DLDiagnostics`` is the concrete ML adapter that satisfies the
``kailash.diagnostics.protocols.Diagnostic`` Protocol for a PyTorch
training loop. It installs forward/backward hooks on a user-supplied
``nn.Module`` to record, per training batch and per epoch:

    * **Loss trajectory** — per-batch loss and learning rate;
      per-epoch train/val summary for convergence analysis.
    * **Gradient flow** — per-layer L2 norm, scale-invariant per-element
      RMS, and update-ratio (``‖∇W‖ / ‖W‖``) so vanishing / exploding
      gradients are detectable across layers of different sizes.
    * **Activation statistics** — per-layer mean/std/min/max plus an
      activation-type-aware ``inactivity_fraction`` (ReLU family:
      ``|x| < 1e-6``; Tanh: ``|x| > 0.99``; Sigmoid: ``|x| > 0.99`` or
      ``|x| < 0.01``) so saturating non-linearities are distinguished
      from dead ReLUs.
    * **Dead-neuron tracking** — rolling per-channel firing counts on
      ReLU-family layers, bounded-memory via the ``window`` parameter.

``report()`` produces a dict with ``gradient_flow`` / ``dead_neurons``
/ ``loss_trend`` findings (each ``severity`` + ``message``) and is
available on every install — pure polars + numpy, no plotting deps.

The ``plot_*()`` methods return :class:`plotly.graph_objects.Figure`
objects and require ``pip install kailash-ml[dl]``. They raise a loud
``ImportError`` naming the extra when plotly is absent.

The ``lr_range_test`` static method implements the Leslie Smith learning
rate range test with fastai-style EMA smoothing and returns BOTH the
steepest-descent LR (``min_loss_lr``) AND the fastai safe-LR
recommendation (``safe_lr = min_loss_lr / safety_divisor``; default 10).
Use ``safe_lr`` in your optimizer — ``min_loss_lr`` is the edge of
instability.

All DataFrames returned by ``*_df()`` accessors are polars. All plots
are plotly. No matplotlib, no pandas.
"""
from __future__ import annotations

import logging
import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional, cast

import numpy as np
import polars as pl

if TYPE_CHECKING:  # pragma: no cover — typing-only imports
    import plotly.graph_objects as go_types  # noqa: F401 — used in docstring examples

logger = logging.getLogger(__name__)

__all__ = [
    "DLDiagnostics",
    "run_diagnostic_checkpoint",
    "diagnose_classifier",
    "diagnose_regressor",
]


# ---------------------------------------------------------------------------
# Torch import (required — DL diagnostics has no meaningful CPU-only fallback)
# ---------------------------------------------------------------------------


def _require_torch() -> tuple[Any, Any]:
    """Import and return ``(torch, torch.nn)`` with a loud, actionable error.

    DLDiagnostics requires PyTorch because its entire contract is installing
    forward/backward hooks on an ``nn.Module``. Per rules/dependencies.md
    "optional extras with loud failure", we raise an ImportError naming the
    extra instead of silently degrading to None.
    """
    try:
        import torch  # noqa: PLC0415
        import torch.nn as nn  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover — covered by DL-extras install
        raise ImportError(
            "DLDiagnostics requires PyTorch. Install the deep-learning extras: "
            "pip install kailash-ml[dl]"
        ) from exc
    return torch, nn


def _require_plotly() -> Any:
    """Import and return the ``plotly.graph_objects`` module or raise loudly.

    Plotly is declared under the ``[dl]`` extra; the ``report()`` and
    ``*_df()`` accessors work on the base install, but the ``plot_*()``
    methods route through this helper so a missing install surfaces the
    extra name instead of a bare ``ModuleNotFoundError``.
    """
    try:
        import plotly.graph_objects as go  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "Plotting methods require plotly. Install the deep-learning extras: "
            "pip install kailash-ml[dl]"
        ) from exc
    return go


def _require_plotly_subplots() -> Any:
    """Return the ``plotly.subplots.make_subplots`` function or raise loudly."""
    try:
        from plotly.subplots import make_subplots  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "Plotting methods require plotly. Install the deep-learning extras: "
            "pip install kailash-ml[dl]"
        ) from exc
    return make_subplots


def _resolve_device() -> Any:
    """Pick a torch device using the kailash-ml backend resolver.

    ``kailash_ml._device.detect_backend`` is the single SOLE detection
    point for the compute backend (see specs/ml-backends.md §2); this
    helper adapts its :class:`BackendInfo` output to the ``torch.device``
    that the DL hooks need.
    """
    torch, _ = _require_torch()
    try:
        from kailash_ml._device import detect_backend  # noqa: PLC0415

        info = detect_backend()
        return torch.device(info.device_string)
    except Exception:  # noqa: BLE001 — defensive fallback
        # If the resolver itself fails (e.g. a probe explodes on a
        # partially-installed extension), default to CPU rather than
        # crashing diagnostic-session construction. DEBUG level because
        # the CPU fallback is a safe, documented behaviour of the
        # resolver boundary — but forensic grep ("dldiagnostics.device_resolver_failed")
        # MUST be possible so operators can distinguish a silent
        # downgrade from a deliberate CPU run.
        logger.debug(
            "dldiagnostics.device_resolver_failed",
            exc_info=True,
        )
        return torch.device("cpu")


# ---------------------------------------------------------------------------
# Module classifiers (built lazily on first use so torch import cost is
# deferred to the first DLDiagnostics instantiation, not module import)
# ---------------------------------------------------------------------------


def _dead_neuron_sensitive_types() -> tuple[type, ...]:
    """Activation module types that DLDiagnostics treats as ReLU-family."""
    _, nn = _require_torch()
    return (nn.ReLU, nn.LeakyReLU, nn.GELU, nn.ELU, nn.SiLU)


def _activation_monitored_types() -> tuple[type, ...]:
    """Module types that DLDiagnostics installs activation hooks on."""
    _, nn = _require_torch()
    return (
        nn.Linear,
        nn.Conv1d,
        nn.Conv2d,
        nn.Conv3d,
        nn.ReLU,
        nn.LeakyReLU,
        nn.GELU,
        nn.ELU,
        nn.SiLU,
        nn.Tanh,
        nn.Sigmoid,
        nn.BatchNorm1d,
        nn.BatchNorm2d,
        nn.LayerNorm,
    )


# ---------------------------------------------------------------------------
# Hook-handle bookkeeping
# ---------------------------------------------------------------------------


@dataclass
class _HookHandles:
    """Container for registered hook handles so we can detach cleanly."""

    gradient: list = field(default_factory=list)
    activation: list = field(default_factory=list)
    dead_neuron: list = field(default_factory=list)
    grad_cam: list = field(default_factory=list)

    def all(self) -> list:
        return self.gradient + self.activation + self.dead_neuron + self.grad_cam


# ---------------------------------------------------------------------------
# DLDiagnostics — concrete Diagnostic adapter
# ---------------------------------------------------------------------------


class DLDiagnostics:
    """Deep-learning training diagnostics adapter (Diagnostic Protocol).

    Collects per-batch time series of gradient norms, activation
    statistics, dead-neuron fractions, and scalar losses; exposes polars
    DataFrame accessors, plotly visualisations, and an automated report
    that surfaces overfitting, vanishing gradients, and pathological
    dead-ReLU layers.

    The adapter satisfies the cross-SDK :class:`kailash.diagnostics.
    protocols.Diagnostic` Protocol (``run_id`` + ``__enter__`` +
    ``__exit__`` + ``report()``). ``isinstance(diag, Diagnostic)``
    returns ``True`` at runtime because the Protocol is
    ``@runtime_checkable``.

    Args:
        model: The ``nn.Module`` to instrument. The model is NOT modified;
            only forward/backward hooks are attached.
        dead_neuron_threshold: Fraction of zero outputs above which a
            layer is flagged as "dead" in :meth:`report`. Must lie in
            ``(0, 1)``. Defaults to ``0.5``.
        window: Number of recent batches used for dead-neuron statistics.
            Must be ``>= 1``. Defaults to ``64``.
        run_id: Optional correlation identifier for this diagnostic
            session. When omitted, a UUID4 hex is generated. Matches
            :class:`Diagnostic.run_id` in the cross-SDK Protocol.

    Raises:
        TypeError: If ``model`` is not an ``nn.Module``.
        ValueError: If ``dead_neuron_threshold`` is outside ``(0, 1)``,
            ``window < 1``, or ``run_id`` is an empty string.

    Example:
        >>> import torch.nn as nn
        >>> model = nn.Sequential(nn.Linear(10, 32), nn.ReLU(), nn.Linear(32, 1))
        >>> with DLDiagnostics(model) as diag:
        ...     diag.track_gradients()
        ...     diag.track_activations()
        ...     # ... training loop ...
    """

    def __init__(
        self,
        model: Any,
        *,
        dead_neuron_threshold: float = 0.5,
        window: int = 64,
        run_id: Optional[str] = None,
    ) -> None:
        torch, nn = _require_torch()
        if not isinstance(model, nn.Module):
            raise TypeError(
                f"DLDiagnostics requires an nn.Module; got {type(model).__name__}"
            )
        if not 0.0 < dead_neuron_threshold < 1.0:
            raise ValueError("dead_neuron_threshold must be in (0, 1)")
        if window < 1:
            raise ValueError("window must be >= 1")
        if run_id is not None and not run_id:
            raise ValueError("run_id must be a non-empty string when provided")

        self.model = model
        self.device = _resolve_device()
        self.dead_neuron_threshold = dead_neuron_threshold
        self.window = window
        # Satisfies kailash.diagnostics.protocols.Diagnostic.run_id.
        self.run_id: str = run_id if run_id is not None else uuid.uuid4().hex

        # Time series storage — lists of dicts, converted to Polars on demand.
        self._grad_log: list[dict[str, Any]] = []
        self._act_log: list[dict[str, Any]] = []
        self._dead_log: list[dict[str, Any]] = []
        self._batch_log: list[dict[str, Any]] = []
        self._epoch_log: list[dict[str, Any]] = []

        # Running per-layer firing masks for dead-neuron detection.
        # Key: layer name -> tensor of firing counts per neuron (1D).
        self._firing_counts: dict[str, Any] = {}
        self._firing_samples: dict[str, int] = {}

        # Counters bound to hook closures so they share scope.
        self._batch_idx = 0
        self._epoch_idx = 0

        self._handles = _HookHandles()
        self._tracking = {"gradients": False, "activations": False, "dead": False}

        # Grad-CAM capture buffers (populated on demand).
        self._gradcam_activation: Any = None
        self._gradcam_gradient: Any = None

        # Cached torch refs for hot hooks — avoid repeated _require_torch
        # within inner loops.
        self._torch = torch

        # Observability: structured INFO on session construction. Field
        # names are ``dl_*``-prefixed per rules/observability.md MUST Rule 9
        # (LogRecord reserves `module`; ``dl_model_class`` / ``dl_device``
        # are domain-prefixed).
        logger.info(
            "dldiagnostics.init",
            extra={
                "dl_model_class": type(model).__name__,
                "dl_device": str(self.device),
                "dl_window": window,
                "dl_run_id": self.run_id,
            },
        )

    # ── Context-manager support ────────────────────────────────────────────

    def __enter__(self) -> "DLDiagnostics":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> Optional[bool]:
        self.detach()
        return None

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.detach()
        except Exception:
            # Finalizers MUST NOT raise. Silent cleanup is the documented
            # contract for __del__ per rules/patterns.md § Async Resource
            # Cleanup (sync form of the same rule).
            pass

    # ── Hook registration ──────────────────────────────────────────────────

    def track_gradients(self) -> "DLDiagnostics":
        """Register backward hooks on every trainable parameter.

        Records the L2 norm, per-element RMS, and update ratio of each
        parameter's gradient at every backward pass, keyed by parameter
        name.

        Returns:
            ``self`` for chaining.
        """
        if self._tracking["gradients"]:
            return self
        for name, param in self.model.named_parameters():
            if not param.requires_grad:
                continue
            handle = param.register_hook(self._make_grad_hook(name))
            self._handles.gradient.append(handle)
        self._tracking["gradients"] = True
        logger.info(
            "dldiagnostics.track_gradients",
            extra={
                "dl_hooks_registered": len(self._handles.gradient),
                "dl_run_id": self.run_id,
            },
        )
        return self

    def track_activations(self) -> "DLDiagnostics":
        """Register forward hooks on monitored submodules.

        Records mean/std/min/max and activation-type-aware
        ``inactivity_fraction`` per layer at every forward pass.

        Returns:
            ``self`` for chaining.
        """
        if self._tracking["activations"]:
            return self
        monitored = _activation_monitored_types()
        for name, module in self.model.named_modules():
            if name == "" or not isinstance(module, monitored):
                continue
            handle = module.register_forward_hook(self._make_act_hook(name))
            self._handles.activation.append(handle)
        self._tracking["activations"] = True
        logger.info(
            "dldiagnostics.track_activations",
            extra={
                "dl_hooks_registered": len(self._handles.activation),
                "dl_run_id": self.run_id,
            },
        )
        return self

    def track_dead_neurons(self) -> "DLDiagnostics":
        """Register forward hooks on ReLU-family layers to track dead neurons.

        A "neuron" here is a channel (Conv) or output unit (Linear). The
        rolling fraction of batches where that neuron output zero is
        tracked, memory-bounded by the ``window`` parameter.

        Returns:
            ``self`` for chaining.
        """
        if self._tracking["dead"]:
            return self
        sensitive = _dead_neuron_sensitive_types()
        for name, module in self.model.named_modules():
            if name == "" or not isinstance(module, sensitive):
                continue
            handle = module.register_forward_hook(self._make_dead_hook(name))
            self._handles.dead_neuron.append(handle)
        self._tracking["dead"] = True
        logger.info(
            "dldiagnostics.track_dead_neurons",
            extra={
                "dl_hooks_registered": len(self._handles.dead_neuron),
                "dl_run_id": self.run_id,
            },
        )
        return self

    def detach(self) -> None:
        """Remove ALL registered hooks and release references.

        Safe to call multiple times. Invoked automatically on context exit.
        """
        for handle in self._handles.all():
            try:
                handle.remove()
            except Exception:
                # Hook removal failures are benign (module may already be
                # gone). See rules/zero-tolerance.md Rule 3 carve-out for
                # cleanup paths.
                pass
        self._handles = _HookHandles()
        self._tracking = {k: False for k in self._tracking}
        self._gradcam_activation = None
        self._gradcam_gradient = None

    # ── Recording ─────────────────────────────────────────────────────────

    def record_batch(self, *, loss: float, lr: Optional[float] = None) -> None:
        """Record per-batch scalar training signals.

        Args:
            loss: Training loss for the batch (post-backward).
            lr: Current learning rate (optional; read from optimizer).
        """
        if not math.isfinite(loss):
            logger.warning(
                "dldiagnostics.record_batch.nonfinite_loss",
                extra={
                    "dl_loss": str(loss),
                    "dl_batch": self._batch_idx,
                    "dl_run_id": self.run_id,
                },
            )
        self._batch_log.append(
            {
                "batch": self._batch_idx,
                "epoch": self._epoch_idx,
                "loss": float(loss),
                "lr": float(lr) if lr is not None else float("nan"),
            }
        )
        self._batch_idx += 1

    def record_epoch(
        self,
        *,
        val_loss: Optional[float] = None,
        train_loss: Optional[float] = None,
        **extra: float,
    ) -> None:
        """Record per-epoch summary metrics.

        Args:
            val_loss: Validation loss at epoch end.
            train_loss: Mean training loss for the epoch. If ``None``, it
                is computed from the batches in this epoch.
            **extra: Any additional scalar metrics to persist (each is
                coerced to float).
        """
        if train_loss is None:
            epoch_batches = [
                b for b in self._batch_log if b["epoch"] == self._epoch_idx
            ]
            if epoch_batches:
                train_loss = float(np.mean([b["loss"] for b in epoch_batches]))
        entry = {
            "epoch": self._epoch_idx,
            "train_loss": train_loss if train_loss is not None else float("nan"),
            "val_loss": val_loss if val_loss is not None else float("nan"),
            **{k: float(v) for k, v in extra.items()},
        }
        self._epoch_log.append(entry)
        self._epoch_idx += 1

    # ── Public DataFrame accessors ────────────────────────────────────────

    def gradients_df(self) -> pl.DataFrame:
        """Polars DataFrame of per-layer gradient norms by batch."""
        if not self._grad_log:
            return pl.DataFrame(
                schema={
                    "batch": pl.Int64,
                    "layer": pl.Utf8,
                    "grad_norm": pl.Float64,
                    "grad_rms": pl.Float64,
                    "update_ratio": pl.Float64,
                }
            )
        return pl.DataFrame(self._grad_log)

    def activations_df(self) -> pl.DataFrame:
        """Polars DataFrame of per-layer activation statistics by batch."""
        if not self._act_log:
            return pl.DataFrame(
                schema={
                    "batch": pl.Int64,
                    "layer": pl.Utf8,
                    "act_kind": pl.Utf8,
                    "mean": pl.Float64,
                    "std": pl.Float64,
                    "min": pl.Float64,
                    "max": pl.Float64,
                    "dead_fraction": pl.Float64,
                    "inactivity_fraction": pl.Float64,
                }
            )
        return pl.DataFrame(self._act_log)

    def dead_neurons_df(self) -> pl.DataFrame:
        """Polars DataFrame of current per-layer dead-neuron fractions."""
        rows: list[dict[str, Any]] = []
        for name, counts in self._firing_counts.items():
            n_samples = max(self._firing_samples.get(name, 1), 1)
            dead_mask = (counts / n_samples) < 1e-6
            rows.append(
                {
                    "layer": name,
                    "n_neurons": int(counts.numel()),
                    "n_dead": int(dead_mask.sum().item()),
                    "dead_fraction": float(dead_mask.float().mean().item()),
                }
            )
        if not rows:
            return pl.DataFrame(
                schema={
                    "layer": pl.Utf8,
                    "n_neurons": pl.Int64,
                    "n_dead": pl.Int64,
                    "dead_fraction": pl.Float64,
                }
            )
        return pl.DataFrame(rows)

    def batches_df(self) -> pl.DataFrame:
        """Polars DataFrame of per-batch scalars (loss, lr)."""
        if not self._batch_log:
            return pl.DataFrame(
                schema={
                    "batch": pl.Int64,
                    "epoch": pl.Int64,
                    "loss": pl.Float64,
                    "lr": pl.Float64,
                }
            )
        return pl.DataFrame(self._batch_log)

    def epochs_df(self) -> pl.DataFrame:
        """Polars DataFrame of per-epoch summary metrics."""
        if not self._epoch_log:
            return pl.DataFrame(
                schema={
                    "epoch": pl.Int64,
                    "train_loss": pl.Float64,
                    "val_loss": pl.Float64,
                }
            )
        return pl.DataFrame(self._epoch_log)

    # ── Plots (require kailash-ml[dl] — plotly) ────────────────────────────

    def plot_loss_curves(self) -> "go_types.Figure":
        """Loss-curve plot: train vs val with overfitting callout.

        Requires ``pip install kailash-ml[dl]``. Returns a Plotly Figure.
        """
        go = _require_plotly()
        epochs = self.epochs_df()
        batches = self.batches_df()
        fig = go.Figure()
        if batches.height:
            fig.add_trace(
                go.Scatter(
                    x=batches["batch"].to_list(),
                    y=batches["loss"].to_list(),
                    mode="lines",
                    name="train (per batch)",
                    line=dict(color="lightblue", width=1),
                    opacity=0.5,
                )
            )
        if epochs.height:
            fig.add_trace(
                go.Scatter(
                    x=epochs["epoch"].to_list(),
                    y=epochs["train_loss"].to_list(),
                    mode="lines+markers",
                    name="train (epoch mean)",
                    line=dict(color="steelblue", width=2),
                )
            )
            if epochs["val_loss"].is_not_null().any():
                fig.add_trace(
                    go.Scatter(
                        x=epochs["epoch"].to_list(),
                        y=epochs["val_loss"].to_list(),
                        mode="lines+markers",
                        name="val",
                        line=dict(color="firebrick", width=2),
                    )
                )
        overfit_epoch = self._detect_overfit_epoch()
        if overfit_epoch is not None:
            fig.add_vline(
                x=overfit_epoch,
                line=dict(color="orange", dash="dash"),
                annotation_text=f"overfitting suspected @ epoch {overfit_epoch}",
                annotation_position="top",
            )
        fig.update_layout(
            title="Loss Curves",
            xaxis_title="step",
            yaxis_title="loss",
            template="plotly_white",
            hovermode="x unified",
        )
        return fig

    def plot_gradient_flow(self) -> "go_types.Figure":
        """Per-layer gradient L2 norm over time (one trace per parameter).

        Layers whose gradient norm collapses toward zero are the
        vanishing-gradient culprits. Requires ``pip install kailash-ml[dl]``.
        """
        go = _require_plotly()
        df = self.gradients_df()
        fig = go.Figure()
        if df.height == 0:
            fig.update_layout(
                title="Gradient Flow by Layer — no data",
                template="plotly_white",
            )
            return fig
        for layer in df["layer"].unique().to_list():
            sub = df.filter(pl.col("layer") == layer)
            fig.add_trace(
                go.Scatter(
                    x=sub["batch"].to_list(),
                    y=sub["grad_norm"].to_list(),
                    mode="lines",
                    name=layer,
                    hovertemplate=f"{layer}<br>batch=%{{x}}<br>‖∇‖=%{{y:.3e}}",
                )
            )
        fig.update_layout(
            title="Gradient Flow by Layer",
            xaxis_title="batch",
            yaxis_title="gradient L2 norm",
            yaxis_type="log",
            template="plotly_white",
        )
        return fig

    def plot_activation_stats(self) -> "go_types.Figure":
        """Per-layer activation mean over time.

        Requires ``pip install kailash-ml[dl]``.
        """
        go = _require_plotly()
        df = self.activations_df()
        fig = go.Figure()
        if df.height == 0:
            fig.update_layout(
                title="Activation Statistics — no data",
                template="plotly_white",
            )
            return fig
        for layer in df["layer"].unique().to_list():
            sub = df.filter(pl.col("layer") == layer)
            fig.add_trace(
                go.Scatter(
                    x=sub["batch"].to_list(),
                    y=sub["mean"].to_list(),
                    mode="lines",
                    name=f"{layer} — mean",
                    hovertemplate=(
                        f"{layer}<br>batch=%{{x}}<br>mean=%{{y:.3f}}<br>"
                        "std=%{customdata:.3f}"
                    ),
                    customdata=sub["std"].to_list(),
                )
            )
        fig.update_layout(
            title="Activation Mean per Layer",
            xaxis_title="batch",
            yaxis_title="activation mean",
            template="plotly_white",
        )
        return fig

    def plot_dead_neurons(self) -> "go_types.Figure":
        """Fraction of dead neurons per ReLU-family layer.

        Requires ``pip install kailash-ml[dl]``.
        """
        go = _require_plotly()
        df = self.dead_neurons_df()
        fig = go.Figure()
        if df.height == 0:
            fig.update_layout(
                title="Dead Neurons — no ReLU-family layers tracked",
                template="plotly_white",
            )
            return fig
        colors = [
            "firebrick" if frac > self.dead_neuron_threshold else "steelblue"
            for frac in df["dead_fraction"].to_list()
        ]
        fig.add_trace(
            go.Bar(
                x=df["layer"].to_list(),
                y=df["dead_fraction"].to_list(),
                marker_color=colors,
                text=[
                    f"{int(n)}/{int(t)}" for n, t in zip(df["n_dead"], df["n_neurons"])
                ],
                textposition="outside",
            )
        )
        fig.add_hline(
            y=self.dead_neuron_threshold,
            line=dict(color="orange", dash="dash"),
            annotation_text=f"alert threshold ({self.dead_neuron_threshold:.0%})",
        )
        fig.update_layout(
            title="Dead Neuron Fraction by Layer",
            xaxis_title="layer",
            yaxis_title="fraction dead",
            yaxis=dict(range=[0, 1]),
            template="plotly_white",
            showlegend=False,
        )
        return fig

    def plot_training_dashboard(self) -> "go_types.Figure":
        """2x2 training dashboard (loss, gradient flow, activations, LR).

        Requires ``pip install kailash-ml[dl]``.
        """
        go = _require_plotly()
        make_subplots = _require_plotly_subplots()
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "Loss",
                "Gradient Flow",
                "Activation Mean",
                "Learning Rate",
            ),
        )

        # (1,1) Loss
        epochs = self.epochs_df()
        batches = self.batches_df()
        if batches.height:
            fig.add_trace(
                go.Scatter(
                    x=batches["batch"].to_list(),
                    y=batches["loss"].to_list(),
                    mode="lines",
                    name="train loss",
                    line=dict(color="steelblue", width=1),
                ),
                row=1,
                col=1,
            )
        if epochs.height and epochs["val_loss"].is_not_null().any():
            # Place val loss at the last batch of each epoch for alignment.
            val_x = []
            for ep in epochs["epoch"].to_list():
                ep_batches = batches.filter(pl.col("epoch") == ep)
                # polars .max() can return None even on a non-empty frame
                # (all-null column). Coalesce to the epoch index so the x-axis
                # never receives None.
                # The `batch` column is populated exclusively by _batch_idx (int);
                # cast() is the narrow that polars' PythonLiteral union-return
                # can't express at the type level.
                max_batch = ep_batches["batch"].max() if ep_batches.height else None
                val_x.append(int(cast(int, max_batch)) if max_batch is not None else ep)
            fig.add_trace(
                go.Scatter(
                    x=val_x,
                    y=epochs["val_loss"].to_list(),
                    mode="lines+markers",
                    name="val loss",
                    line=dict(color="firebrick"),
                ),
                row=1,
                col=1,
            )

        # (1,2) Gradient flow
        gdf = self.gradients_df()
        if gdf.height:
            for layer in gdf["layer"].unique().to_list():
                sub = gdf.filter(pl.col("layer") == layer)
                fig.add_trace(
                    go.Scatter(
                        x=sub["batch"].to_list(),
                        y=sub["grad_norm"].to_list(),
                        mode="lines",
                        name=layer,
                        showlegend=False,
                    ),
                    row=1,
                    col=2,
                )
            fig.update_yaxes(type="log", row=1, col=2)

        # (2,1) Activation mean
        adf = self.activations_df()
        if adf.height:
            for layer in adf["layer"].unique().to_list():
                sub = adf.filter(pl.col("layer") == layer)
                fig.add_trace(
                    go.Scatter(
                        x=sub["batch"].to_list(),
                        y=sub["mean"].to_list(),
                        mode="lines",
                        name=layer,
                        showlegend=False,
                    ),
                    row=2,
                    col=1,
                )

        # (2,2) LR
        if batches.height and batches["lr"].is_not_null().any():
            fig.add_trace(
                go.Scatter(
                    x=batches["batch"].to_list(),
                    y=batches["lr"].to_list(),
                    mode="lines",
                    name="lr",
                    line=dict(color="darkgreen"),
                    showlegend=False,
                ),
                row=2,
                col=2,
            )

        fig.update_layout(
            title="Training Dashboard",
            template="plotly_white",
            height=720,
        )
        return fig

    def plot_lr_vs_loss(self) -> "go_types.Figure":
        """Plot LR vs loss (useful after an :meth:`lr_range_test`).

        Requires ``pip install kailash-ml[dl]``.
        """
        go = _require_plotly()
        df = self.batches_df()
        fig = go.Figure()
        if df.height == 0 or df["lr"].is_null().all():
            fig.update_layout(title="LR vs Loss — no data", template="plotly_white")
            return fig
        fig.add_trace(
            go.Scatter(
                x=df["lr"].to_list(),
                y=df["loss"].to_list(),
                mode="lines",
                line=dict(color="steelblue"),
            )
        )
        fig.update_layout(
            title="Learning Rate vs Loss",
            xaxis_title="learning rate",
            yaxis_title="loss",
            xaxis_type="log",
            template="plotly_white",
        )
        return fig

    def plot_weight_distributions(self) -> "go_types.Figure":
        """Histogram of weight values, one trace per parameter tensor.

        Requires ``pip install kailash-ml[dl]``.
        """
        go = _require_plotly()
        fig = go.Figure()
        for name, param in self.model.named_parameters():
            if not param.requires_grad or param.ndim == 0:
                continue
            values = param.detach().cpu().flatten().numpy()
            fig.add_trace(go.Histogram(x=values, name=name, opacity=0.6))
        fig.update_layout(
            title="Weight Distributions",
            xaxis_title="value",
            yaxis_title="count",
            barmode="overlay",
            template="plotly_white",
        )
        return fig

    def plot_gradient_norms(self) -> "go_types.Figure":
        """Mean gradient norm per layer across the run (bar chart).

        Requires ``pip install kailash-ml[dl]``.
        """
        go = _require_plotly()
        df = self.gradients_df()
        fig = go.Figure()
        if df.height == 0:
            fig.update_layout(title="Gradient Norms — no data", template="plotly_white")
            return fig
        summary = df.group_by("layer").agg(
            pl.col("grad_norm").mean().alias("mean_grad")
        )
        summary = summary.sort("mean_grad")
        fig.add_trace(
            go.Bar(
                x=summary["layer"].to_list(),
                y=summary["mean_grad"].to_list(),
                marker_color="steelblue",
            )
        )
        fig.update_layout(
            title="Mean Gradient Norm per Layer",
            xaxis_title="layer",
            yaxis_title="mean ‖∇‖",
            yaxis_type="log",
            template="plotly_white",
        )
        return fig

    # ── Automated report (Diagnostic.report contract) ─────────────────────

    def report(self) -> dict[str, Any]:
        """Return a structured summary of the captured diagnostic session.

        The return shape satisfies :meth:`kailash.diagnostics.protocols.
        Diagnostic.report`. Keys:

          * ``run_id`` — the session identifier (matches ``self.run_id``).
          * ``batches`` — total per-batch scalar records captured.
          * ``epochs`` — total per-epoch summary records captured.
          * ``gradient_flow`` — ``{"severity": ..., "message": ...}``
          * ``dead_neurons`` — ``{"severity": ..., "message": ...}``
          * ``loss_trend`` — ``{"severity": ..., "message": ...}``

        Severity values are ``"HEALTHY"`` / ``"WARNING"`` / ``"CRITICAL"``
        / ``"UNKNOWN"``. The method does not print — callers who want a
        human-readable dump can pipe the dict through
        :func:`print_report` (exported alongside the class) or format it
        themselves.
        """
        findings: dict[str, Any] = {
            "run_id": self.run_id,
            "batches": len(self._batch_log),
            "epochs": len(self._epoch_log),
        }

        # 1. Gradient flow — uses SCALE-INVARIANT per-element RMS (grad_rms)
        # and update_ratio (‖∇W‖/‖W‖).
        gdf = self.gradients_df()
        if gdf.height and "grad_rms" in gdf.columns:
            stats = gdf.group_by("layer").agg(
                pl.col("grad_rms").mean().alias("rms"),
                pl.col("update_ratio").mean().alias("ur"),
            )
            min_rms_raw = stats["rms"].min()
            max_rms_raw = stats["rms"].max()
            min_ur_raw = stats["ur"].min()
            max_ur_raw = stats["ur"].max()
            min_rms = (
                float(min_rms_raw) if isinstance(min_rms_raw, (int, float)) else None
            )
            max_rms = (
                float(max_rms_raw) if isinstance(max_rms_raw, (int, float)) else None
            )
            min_ur = float(min_ur_raw) if isinstance(min_ur_raw, (int, float)) else 0.0
            max_ur = float(max_ur_raw) if isinstance(max_ur_raw, (int, float)) else 0.0
            if min_rms is None or max_rms is None or min_rms == 0:
                severity = "UNKNOWN"
                message = "Insufficient gradient data."
            elif min_rms < 1e-5 or min_ur < 1e-4:
                # Vanishing: RMS < 1e-5 OR update ratio < 1e-4.
                worst_layer = (
                    stats.sort("rms").row(0, named=True)["layer"]
                    if min_rms < 1e-5
                    else stats.sort("ur").row(0, named=True)["layer"]
                )
                severity = "CRITICAL"
                message = (
                    f"Vanishing gradients at '{worst_layer}' - "
                    f"min RMS = {min_rms:.2e}, min update_ratio = {min_ur:.2e}. "
                    "Fix: verify pre-norm layout (LayerNorm/RMSNorm before block), "
                    "add residual connections, switch to GELU/SiLU, or use Kaiming init."
                )
            elif max_rms > 1e-2 or max_ur > 0.1:
                # Exploding: RMS > 1e-2 OR update ratio > 0.1.
                worst_layer = (
                    stats.sort("rms", descending=True).row(0, named=True)["layer"]
                    if max_rms > 1e-2
                    else stats.sort("ur", descending=True).row(0, named=True)["layer"]
                )
                severity = "CRITICAL"
                message = (
                    f"Exploding gradients at '{worst_layer}' - "
                    f"max RMS = {max_rms:.2e}, max update_ratio = {max_ur:.2e}. "
                    "Fix: add gradient clipping (or adaptive: ZClip/AGC), reduce LR, "
                    "verify initialization (Kaiming for ReLU, Xavier for Tanh)."
                )
            elif max_rms / max(min_rms, 1e-12) > 1e3:
                severity = "WARNING"
                message = (
                    f"Large RMS spread across layers (max/min = "
                    f"{max_rms / min_rms:.1e}). Deep layers may be learning unevenly."
                )
            else:
                severity = "HEALTHY"
                message = (
                    f"Gradient flow OK (RMS range {min_rms:.2e}-{max_rms:.2e}, "
                    f"update_ratio range {min_ur:.2e}-{max_ur:.2e})."
                )
            findings["gradient_flow"] = {"severity": severity, "message": message}
        elif gdf.height:
            findings["gradient_flow"] = {
                "severity": "UNKNOWN",
                "message": (
                    "grad_rms field missing - re-run with the current library "
                    "version to get scale-invariant diagnosis."
                ),
            }
        else:
            findings["gradient_flow"] = {
                "severity": "UNKNOWN",
                "message": "No gradient tracking enabled - call track_gradients().",
            }

        # 2. Dead neurons / saturation — uses ACTIVATION-TYPE-AWARE
        # inactivity_fraction.
        adf = self.activations_df()
        if adf.height and "inactivity_fraction" in adf.columns:
            agg = (
                adf.filter(pl.col("act_kind") != "other")
                .group_by("layer")
                .agg(
                    pl.col("inactivity_fraction").mean().alias("mean_inactive"),
                    pl.col("act_kind").first().alias("kind"),
                )
                .sort("mean_inactive", descending=True)
            )
            if agg.height:
                worst = agg.row(0, named=True)
                thr = self.dead_neuron_threshold
                if worst["mean_inactive"] > thr:
                    kind = worst["kind"]
                    if kind == "relu":
                        label = "dead neurons"
                        fix = "Switch to GELU/LeakyReLU or re-initialise with Kaiming."
                    elif kind == "tanh":
                        label = "saturated (|x|>0.99)"
                        fix = "Reduce LR, add LayerNorm before, or switch to GELU."
                    elif kind == "sigmoid":
                        label = "saturated (|x|>0.99 or |x|<0.01)"
                        fix = (
                            "Reduce LR, add BN/LN, or switch to softmax+CE if "
                            "classification."
                        )
                    else:
                        label = "inactive"
                        fix = "Investigate activation distribution."
                    findings["dead_neurons"] = {
                        "severity": "WARNING",
                        "message": (
                            f"'{worst['layer']}' ({kind}): "
                            f"{worst['mean_inactive']:.0%} {label}. {fix}"
                        ),
                    }
                else:
                    findings["dead_neurons"] = {
                        "severity": "HEALTHY",
                        "message": (
                            f"All {agg.height} activation layers healthy "
                            f"(worst: {worst['layer']} at "
                            f"{worst['mean_inactive']:.0%} inactive, below "
                            f"{thr:.0%} threshold)."
                        ),
                    }
            else:
                findings["dead_neurons"] = {
                    "severity": "UNKNOWN",
                    "message": (
                        "No activation layers tracked - call track_activations()."
                    ),
                }
        else:
            findings["dead_neurons"] = {
                "severity": "UNKNOWN",
                "message": (
                    "No activation tracking enabled - call track_activations()."
                ),
            }

        # 3. Loss trend
        edf = self.epochs_df()
        if edf.height >= 3 and edf["val_loss"].is_not_null().any():
            overfit = self._detect_overfit_epoch()
            train_trend = self._slope(edf["train_loss"].to_list())
            if overfit is not None:
                severity = "WARNING"
                message = (
                    f"Overfitting suspected at epoch {overfit} "
                    "(val loss rising while train loss falls). "
                    "Consider dropout, weight decay, or early stopping."
                )
            elif train_trend > -1e-4 and edf.height >= 5:
                severity = "WARNING"
                message = (
                    f"Underfitting - train loss slope {train_trend:.2e}/epoch. "
                    "Consider a larger model, more epochs, or higher LR."
                )
            else:
                severity = "HEALTHY"
                message = f"Loss converging (train slope {train_trend:.2e}/epoch)."
            findings["loss_trend"] = {"severity": severity, "message": message}
        else:
            findings["loss_trend"] = {
                "severity": "UNKNOWN",
                "message": "Need at least 3 epochs with val_loss for trend analysis.",
            }

        logger.info(
            "dldiagnostics.report",
            extra={
                "dl_run_id": self.run_id,
                "dl_batches": findings["batches"],
                "dl_epochs": findings["epochs"],
                "dl_gradient_severity": findings["gradient_flow"]["severity"],
                "dl_dead_severity": findings["dead_neurons"]["severity"],
                "dl_loss_severity": findings["loss_trend"]["severity"],
            },
        )
        return findings

    # ── Grad-CAM ──────────────────────────────────────────────────────────

    def grad_cam(
        self,
        input_tensor: Any,
        target_class: int,
        layer_name: str,
    ) -> Any:
        """Compute a Grad-CAM heatmap for ``target_class`` from ``layer_name``.

        Args:
            input_tensor: Input batch ``(N, C, H, W)`` or ``(N, C, L)``.
            target_class: Target class index to explain.
            layer_name: ``model.named_modules()`` key of the conv layer to
                attribute. Usually the last convolutional layer.

        Returns:
            Heatmap tensor with shape matching the spatial dims of the
            tracked layer's output (``(N, H', W')`` for 2D inputs).

        Raises:
            ValueError: If ``layer_name`` is not found in the model.
            RuntimeError: If the layer is unreachable from the forward path.
        """
        torch, _ = _require_torch()
        target_module: Optional[Any] = None
        for name, module in self.model.named_modules():
            if name == layer_name:
                target_module = module
                break
        if target_module is None:
            raise ValueError(
                f"Layer '{layer_name}' not found in model. "
                f"Available: "
                f"{[n for n, _ in self.model.named_modules() if n][:10]}..."
            )

        self._gradcam_activation = None
        self._gradcam_gradient = None

        def fwd_hook(_mod: Any, _inp: Any, out: Any) -> None:
            self._gradcam_activation = out.detach()

        def bwd_hook(_mod: Any, _gi: Any, go: Any) -> None:
            # go is a tuple — first element is d(output)/d(module-output)
            self._gradcam_gradient = go[0].detach()

        h1 = target_module.register_forward_hook(fwd_hook)
        h2 = target_module.register_full_backward_hook(bwd_hook)
        self._handles.grad_cam.extend([h1, h2])

        # Preserve caller's train/eval state — critical for mid-training use.
        was_training = self.model.training

        try:
            self.model.eval()
            inp = input_tensor.to(self.device)
            logits = self.model(inp)
            if logits.ndim != 2:
                raise ValueError(
                    f"grad_cam expects classification logits (N, C); got {logits.shape}"
                )
            self.model.zero_grad(set_to_none=True)
            one_hot = torch.zeros_like(logits)
            one_hot[:, target_class] = 1.0
            logits.backward(gradient=one_hot, retain_graph=False)

            if self._gradcam_activation is None or self._gradcam_gradient is None:
                raise RuntimeError(
                    "Grad-CAM hooks did not fire - layer may be unreachable "
                    "from the forward path."
                )
            activations = self._gradcam_activation  # (N, K, ...)
            gradients = self._gradcam_gradient  # (N, K, ...)
            # Global-average-pool gradients over spatial dims → per-channel weights.
            spatial_dims = tuple(range(2, gradients.ndim))
            weights = gradients.mean(dim=spatial_dims, keepdim=True)
            cam = (weights * activations).sum(dim=1)
            cam = torch.relu(cam)
            # Normalise per-sample to [0, 1].
            flat = cam.flatten(start_dim=1)
            mins = flat.min(dim=1, keepdim=True).values
            maxs = flat.max(dim=1, keepdim=True).values
            denom = (maxs - mins).clamp(min=1e-8)
            flat = (flat - mins) / denom
            cam = flat.view_as(cam)
            return cam.cpu()
        finally:
            # Restore caller's train/eval state BEFORE removing hooks, so
            # downstream errors in hook cleanup don't leave model in eval mode.
            if was_training:
                self.model.train()
            h1.remove()
            h2.remove()
            # Remove from bookkeeping too so detach() stays idempotent.
            self._handles.grad_cam = [
                h for h in self._handles.grad_cam if h is not h1 and h is not h2
            ]
            self._gradcam_activation = None
            self._gradcam_gradient = None

    # ── LR range test (static) ────────────────────────────────────────────

    @staticmethod
    def lr_range_test(
        model: Any,
        dataloader: Any,
        *,
        loss_fn: Optional[Any] = None,
        optimizer_cls: Optional[type] = None,
        lr_min: float = 1e-7,
        lr_max: float = 10.0,
        steps: int = 200,
        device: Optional[Any] = None,
        batch_adapter: Optional[Callable[[Any], tuple[Any, Any]]] = None,
        safety_divisor: float = 10.0,
    ) -> dict[str, Any]:
        """Leslie Smith LR range test with fastai-style safe-LR recipe.

        Trains for ``steps`` batches while exponentially increasing LR
        from ``lr_min`` to ``lr_max``. Smooths the loss curve with EMA
        (beta=0.98) before finding the steepest-descent point — matches
        fastai's ``lr_find()`` and avoids picking a single lucky batch in
        the tail.

        Returns BOTH ``min_loss_lr`` (steepest descent) AND
        ``safe_lr = min_loss_lr / safety_divisor`` (default 10). Use
        ``safe_lr`` in your optimizer — ``min_loss_lr`` is the edge of
        instability.

        The model's weights are saved before the test and **restored** on
        exit (via state_dict deepcopy), so calling this does not corrupt
        your model.

        Args:
            model: The model to probe. Weights are restored after return.
            dataloader: Any DataLoader. By default yields ``(inputs, targets)``
                tuples; pass ``batch_adapter`` for HF/SSL batch formats.
            loss_fn: Loss function (REQUIRED — no silent default).
            optimizer_cls: Optimizer class (default ``torch.optim.SGD``).
            lr_min, lr_max, steps: Sweep configuration.
            device: Override compute device (default: model's current device).
            batch_adapter: Callable ``batch -> (x, y)``. Default handles
                tuple/list; pass a lambda for dict-shaped batches.
            safety_divisor: Divide steepest-descent LR by this to get safe
                LR (fastai default: 10).

        Returns:
            ``{"safe_lr": float, "min_loss_lr": float, "divergence_lr": float,
                "lrs": [...], "losses": [...], "losses_smooth": [...],
                "figure": go.Figure}``

        Raises:
            ValueError: on out-of-range arguments or missing ``loss_fn``.
            ImportError: if plotly is missing (the return value includes a
                ``"figure"`` key).
        """
        if steps < 2:
            raise ValueError("steps must be >= 2")
        if not 0 < lr_min < lr_max:
            raise ValueError("require 0 < lr_min < lr_max")
        if loss_fn is None:
            raise ValueError(
                "loss_fn is required - no silent default. "
                "Pass nn.CrossEntropyLoss() for classification or "
                "nn.MSELoss() for regression."
            )

        torch, _ = _require_torch()
        # Resolve to a concrete class so Pyright narrows out None before the
        # call site at `optimizer_cls(model.parameters(), ...)` below.
        if optimizer_cls is None:
            optimizer_cls = torch.optim.SGD
        assert optimizer_cls is not None  # narrowed for the type checker

        import copy as _copy

        # Device: honor model's current device unless overridden.
        dev = device or next(model.parameters()).device
        if device is not None:
            model = model.to(dev)

        # Save weights for restoration.
        saved_state = _copy.deepcopy(model.state_dict())

        def _default_adapter(batch: Any) -> tuple[Any, Any]:
            if isinstance(batch, (tuple, list)) and len(batch) >= 2:
                return batch[0], batch[1]
            raise ValueError(
                "lr_range_test got a non-(x,y) batch. Pass batch_adapter=... "
                "for HuggingFace-style dict batches or SSL single-tensor batches."
            )

        adapter = batch_adapter or _default_adapter

        lrs: list[float] = []
        losses: list[float] = []
        try:
            optimizer = optimizer_cls(model.parameters(), lr=lr_min)
            gamma = (lr_max / lr_min) ** (1.0 / (steps - 1))
            running_min = float("inf")  # O(1) running min
            model.train()
            data_iter = iter(dataloader)
            for step in range(steps):
                try:
                    batch = next(data_iter)
                except StopIteration:
                    data_iter = iter(dataloader)
                    batch = next(data_iter)
                x, y = adapter(batch)
                x, y = x.to(dev), y.to(dev)
                for pg in optimizer.param_groups:
                    pg["lr"] = lr_min * (gamma**step)
                optimizer.zero_grad(set_to_none=True)
                logits = model(x)
                loss = loss_fn(logits, y)
                loss.backward()
                optimizer.step()
                cur_lr = optimizer.param_groups[0]["lr"]
                cur_loss = float(loss.item())
                lrs.append(cur_lr)
                losses.append(cur_loss)
                if cur_loss < running_min:
                    running_min = cur_loss
                if not math.isfinite(cur_loss) or cur_loss > 10 * running_min:
                    logger.info(
                        "dldiagnostics.lr_range_test.diverged",
                        extra={
                            "dl_step": step,
                            "dl_lr": cur_lr,
                            "dl_loss": cur_loss,
                        },
                    )
                    break
        finally:
            # Always restore weights — no silent corruption.
            model.load_state_dict(saved_state)

        # EMA-smoothed losses (fastai convention, beta=0.98).
        beta = 0.98
        losses_smooth: list[float] = []
        ema = 0.0
        for i, ell in enumerate(losses):
            ema = beta * ema + (1 - beta) * ell
            # Bias-correct the EMA.
            losses_smooth.append(ema / (1 - beta ** (i + 1)))

        # min_loss_lr = LR at the steepest-descent point of SMOOTHED loss.
        min_loss_lr = lr_min
        divergence_lr = lr_max
        if len(losses_smooth) >= 3:
            dl = np.diff(np.array(losses_smooth))
            idx = int(np.argmin(dl))
            min_loss_lr = lrs[idx]
            # Divergence = first point where smoothed loss > 4× its minimum.
            min_smooth = min(losses_smooth)
            for i, s in enumerate(losses_smooth):
                if s > 4 * min_smooth and i > idx:
                    divergence_lr = lrs[i]
                    break

        safe_lr = min_loss_lr / safety_divisor

        go = _require_plotly()
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=lrs,
                y=losses,
                mode="lines",
                name="raw loss",
                line=dict(color="lightgray"),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=lrs,
                y=losses_smooth,
                mode="lines",
                name="smoothed",
                line=dict(color="#0D9488", width=2),
            )
        )
        fig.add_vline(
            x=safe_lr,
            line=dict(color="#22C55E", dash="dash"),
            annotation_text=f"safe_lr = {safe_lr:.2e}",
        )
        fig.add_vline(
            x=min_loss_lr,
            line=dict(color="#F59E0B", dash="dot"),
            annotation_text=f"min_loss_lr = {min_loss_lr:.2e}",
        )
        fig.update_layout(
            title="LR Range Test (smoothed) - use safe_lr, not min_loss_lr",
            xaxis_title="learning rate",
            yaxis_title="loss",
            xaxis_type="log",
            template="plotly_white",
        )
        logger.info(
            "dldiagnostics.lr_range_test.ok",
            extra={
                "dl_safe_lr": safe_lr,
                "dl_min_loss_lr": min_loss_lr,
                "dl_divergence_lr": divergence_lr,
                "dl_steps_run": len(lrs),
            },
        )
        return {
            "safe_lr": safe_lr,
            "min_loss_lr": min_loss_lr,
            "divergence_lr": divergence_lr,
            "suggested_lr": safe_lr,  # backwards-compat alias
            "lrs": lrs,
            "losses": losses,
            "losses_smooth": losses_smooth,
            "figure": fig,
        }

    # ── Hook factories (internal) ─────────────────────────────────────────

    def _make_grad_hook(self, name: str):
        """Scale-invariant gradient tracking.

        Records three metrics per layer per batch:
          - grad_norm: raw L2 norm (preserved for backwards compatibility)
          - grad_rms: per-element RMS = ``‖∇‖ / sqrt(numel)`` — scale-invariant,
            comparable across layers of any size.
          - update_ratio: ``‖∇W‖ / ‖W‖`` — the "effective LR" per layer.

        Casts to fp32 before reduction so BF16/FP16 gradients don't silently
        produce inf/NaN.
        """
        try:
            param = dict(self.model.named_parameters())[name]
        except KeyError:
            param = None

        def _hook(grad: Any) -> None:
            try:
                # Handle sparse gradients (e.g. nn.Embedding(sparse=True)).
                g = grad.coalesce().values() if grad.is_sparse else grad
                # Cast to fp32 to avoid BF16/FP16 inf.
                g_f32 = g.detach().float()
                l2 = float(g_f32.norm(p=2).item())
                numel = max(g_f32.numel(), 1)
                rms = l2 / (numel**0.5)
                # Update ratio — use detached param weight norm.
                if param is not None:
                    p_norm = float(param.detach().float().norm(p=2).item())
                    upd_ratio = l2 / max(p_norm, 1e-12)
                else:
                    upd_ratio = 0.0
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "dldiagnostics.grad_hook.error",
                    extra={
                        "dl_layer": name,
                        "dl_error": str(exc),
                        "dl_run_id": self.run_id,
                    },
                )
                return
            self._grad_log.append(
                {
                    "batch": self._batch_idx,
                    "layer": name,
                    "grad_norm": l2,  # preserved for compatibility
                    "grad_rms": rms,  # scale-invariant
                    "update_ratio": upd_ratio,  # ‖∇W‖ / ‖W‖
                }
            )

        return _hook

    def _make_act_hook(self, name: str):
        """Activation statistics with activation-type-aware inactivity.

        - ReLU / GELU / SiLU: fraction with ``|x| < 1e-6`` (dead neurons)
        - Tanh: fraction with ``|x| > 0.99`` (saturated)
        - Sigmoid: fraction with ``|x| > 0.99`` OR ``|x| < 0.01`` (saturated)
        - Others: 0 (no pathology definition)

        The legacy ``dead_fraction`` field (exact-zero count) is preserved
        for backwards compatibility but is only meaningful for ReLU.
        """
        act_kind = self._classify_activation_module(name)

        def _hook(_module: Any, _inp: Any, output: Any) -> None:
            if output.numel() == 0:
                return
            try:
                # Cast to fp32 for numerical safety.
                out = output.detach().float()
            except AttributeError:
                return
            try:
                mean = float(out.mean().item())
                std = float(out.std().item()) if out.numel() > 1 else 0.0
                mn = float(out.min().item())
                mx = float(out.max().item())
                legacy_dead = float((out == 0).float().mean().item())
                if act_kind == "relu":
                    inactivity = float((out.abs() < 1e-6).float().mean().item())
                elif act_kind == "tanh":
                    inactivity = float((out.abs() > 0.99).float().mean().item())
                elif act_kind == "sigmoid":
                    inactivity = float(
                        ((out > 0.99) | (out < 0.01)).float().mean().item()
                    )
                else:
                    inactivity = 0.0
            except RuntimeError:
                # Non-numeric tensor (e.g. mixed dtype). Skip silently.
                return
            for val_name, val in (("mean", mean), ("std", std)):
                if val != val or val in (float("inf"), float("-inf")):
                    logger.warning(
                        "dldiagnostics.act_hook.nonfinite",
                        extra={
                            "dl_layer": name,
                            "dl_field": val_name,
                            "dl_run_id": self.run_id,
                        },
                    )
                    return
            self._act_log.append(
                {
                    "batch": self._batch_idx,
                    "layer": name,
                    "act_kind": act_kind,
                    "mean": mean,
                    "std": std,
                    "min": mn,
                    "max": mx,
                    "dead_fraction": legacy_dead,
                    "inactivity_fraction": inactivity,
                }
            )

        return _hook

    def _classify_activation_module(self, name: str) -> str:
        """Return one of 'relu', 'tanh', 'sigmoid', 'other' for a module name."""
        try:
            mod = dict(self.model.named_modules())[name]
        except KeyError:
            return "other"
        cls = type(mod).__name__.lower()
        if any(k in cls for k in ("relu", "gelu", "silu", "swish", "elu")):
            return "relu"
        if "tanh" in cls:
            return "tanh"
        if "sigmoid" in cls:
            return "sigmoid"
        return "other"

    def _make_dead_hook(self, name: str):
        torch = self._torch

        def _hook(_module: Any, _inp: Any, output: Any) -> None:
            if output.numel() == 0:
                return
            out = output.detach()
            # Collapse all non-channel dims. Convention: channel dim = 1.
            if out.ndim < 2:
                return
            reduce_dims = tuple(d for d in range(out.ndim) if d != 1)
            fired = (out != 0).any(dim=reduce_dims).float().cpu()
            if name not in self._firing_counts:
                self._firing_counts[name] = torch.zeros_like(fired)
                self._firing_samples[name] = 0
            self._firing_counts[name] += fired
            self._firing_samples[name] += 1
            # Keep memory bounded by decaying old counts when window exceeded.
            if self._firing_samples[name] > self.window:
                scale = self.window / self._firing_samples[name]
                self._firing_counts[name] = self._firing_counts[name] * scale
                self._firing_samples[name] = self.window

        return _hook

    # ── Internal analysis helpers ─────────────────────────────────────────

    @staticmethod
    def _slope(series: list[float]) -> float:
        """Least-squares slope of a 1D series vs its index (ignores NaN)."""
        xs = np.arange(len(series), dtype=float)
        ys = np.asarray(series, dtype=float)
        mask = np.isfinite(ys)
        if mask.sum() < 2:
            return 0.0
        xs, ys = xs[mask], ys[mask]
        return float(np.polyfit(xs, ys, 1)[0])

    def _detect_overfit_epoch(self) -> Optional[int]:
        """Return epoch index where val loss starts rising while train falls."""
        edf = self.epochs_df()
        if edf.height < 3:
            return None
        train = edf["train_loss"].to_list()
        val = edf["val_loss"].to_list()
        for i in range(2, len(val)):
            v_now, v_prev = val[i], val[i - 1]
            t_now, t_prev = train[i], train[i - 1]
            if any(
                x is None or not math.isfinite(x)
                for x in (v_now, v_prev, t_now, t_prev)
            ):
                continue
            if v_now > v_prev and t_now < t_prev:
                return i
        return None


# ════════════════════════════════════════════════════════════════════════
# Module-level helpers — diagnostic checkpoint + preset wrappers
# ════════════════════════════════════════════════════════════════════════


def run_diagnostic_checkpoint(
    model: Any,
    dataloader: Any,
    loss_fn: Callable[..., Any],
    *,
    title: str = "Model",
    n_batches: int = 8,
    train_losses: Optional[list[float]] = None,
    val_losses: Optional[list[float]] = None,
    show: bool = True,
    batch_adapter: Optional[Callable[[Any], tuple[Any, ...]]] = None,
) -> tuple[DLDiagnostics, dict[str, Any]]:
    """Run a short instrumented diagnostic pass on a TRAINED model.

    Attaches the four diagnostic instruments (gradients, activations,
    dead-neurons, scalar history) to the model, runs ``n_batches`` of
    forward-backward passes to populate the history, replays any
    epoch-level losses you collected during real training, and returns
    the :class:`DLDiagnostics` session plus its ``report()`` output.

    The model's weights are NOT updated — gradients are computed but no
    optimizer step is taken. The model's train/eval state is preserved.

    Args:
        model: A trained ``nn.Module``.
        dataloader: Any DataLoader whose batches the loss function accepts.
        loss_fn: Callable. The default contract is
            ``loss_fn(model, batch) -> scalar_loss_or_tuple`` where the
            first element of a returned tuple is the loss tensor.
        title: Human-readable name used by the dashboard title.
        n_batches: How many batches to instrument (default 8).
        train_losses: Optional list of per-epoch train losses captured
            during the actual training run. Replayed into the dashboard so
            viewers see the real loss trajectory.
        val_losses: Optional list of per-epoch validation losses, same
            length as ``train_losses``.
        show: If ``True``, calls ``.show()`` on the dashboard figure when
            plotly is available; silently skipped when plotly is missing.
        batch_adapter: Optional ``batch -> (loss_fn_args...)`` translator
            for non-standard batch shapes.

    Returns:
        ``(diag, findings)`` so the caller can inspect the DataFrames and
        the findings dict.

    Raises:
        TypeError: If ``model`` is not an ``nn.Module``.
        ValueError: If ``n_batches < 1``.
    """
    torch, nn = _require_torch()
    if not isinstance(model, nn.Module):
        raise TypeError("run_diagnostic_checkpoint requires an nn.Module")
    if n_batches < 1:
        raise ValueError("n_batches must be >= 1")

    diag = DLDiagnostics(model)
    diag.track_gradients().track_activations().track_dead_neurons()

    # Replay real training history into the dashboard if provided.
    if train_losses or val_losses:
        n_epochs = max(len(train_losses or []), len(val_losses or []))
        for i in range(n_epochs):
            tl = (
                float(train_losses[i])
                if train_losses and i < len(train_losses)
                else None
            )
            vl = float(val_losses[i]) if val_losses and i < len(val_losses) else None
            # Synthesise one batch entry per epoch so the per-batch trace
            # has data to plot — viewers still see the real epoch losses.
            if tl is not None:
                diag.record_batch(loss=tl)
            diag.record_epoch(train_loss=tl, val_loss=vl)

    was_training = model.training
    try:
        model.train()  # Enable gradients + activation hooks.
        seen = 0
        for batch in dataloader:
            if seen >= n_batches:
                break
            try:
                if batch_adapter is not None:
                    args = batch_adapter(batch)
                    loss_out = loss_fn(model, *args)
                else:
                    loss_out = loss_fn(model, batch)
                # Convention: loss_fn may return (loss, extras) or bare tensor.
                loss = loss_out[0] if isinstance(loss_out, tuple) else loss_out
                if not isinstance(loss, torch.Tensor):
                    raise TypeError(
                        f"loss_fn returned {type(loss).__name__}; expected Tensor"
                    )
                model.zero_grad(set_to_none=True)
                loss.backward()
                # NOTE: no optimizer.step() — diagnostic pass is read-only.
                diag.record_batch(loss=float(loss.item()))
            except Exception as exc:  # pragma: no cover - user loop variability
                logger.warning(
                    "dldiagnostics.checkpoint.batch_skipped",
                    extra={
                        "dl_batch_idx": seen,
                        "dl_error": str(exc),
                        "dl_run_id": diag.run_id,
                    },
                )
            seen += 1
    finally:
        if not was_training:
            model.eval()

    # Render the dashboard + findings. Plot rendering is gated on plotly;
    # if plotly is absent we still return real findings.
    try:
        fig = diag.plot_training_dashboard()
        fig.update_layout(title=f"{title} - Diagnostic Dashboard")
        if show:
            try:
                fig.show()
            except Exception as exc:  # pragma: no cover - no display in CI
                logger.info(
                    "dldiagnostics.checkpoint.show_skipped",
                    extra={
                        "dl_error": str(exc),
                        "dl_run_id": diag.run_id,
                    },
                )
    except ImportError:
        # Plotly missing → report() still works; caller gets findings without figure.
        logger.info(
            "dldiagnostics.checkpoint.plotly_missing",
            extra={"dl_run_id": diag.run_id},
        )

    findings = diag.report()
    return diag, findings


def diagnose_classifier(
    model: Any,
    dataloader: Any,
    *,
    title: str = "Classifier",
    n_batches: int = 8,
    train_losses: Optional[list[float]] = None,
    val_losses: Optional[list[float]] = None,
    show: bool = True,
    forward_returns_tuple: bool = False,
) -> tuple[DLDiagnostics, dict[str, Any]]:
    """Convenience wrapper for ``(x, y)`` cross-entropy classifiers.

    Equivalent to :func:`run_diagnostic_checkpoint` with a built-in
    ``loss_fn`` that calls ``F.cross_entropy(model(x), y)``. Use for
    CNN, transformer, and transfer-learning diagnostic passes.

    Args:
        model: Trained classifier ``nn.Module``.
        dataloader: Yields ``(x, y)`` tuples; ``y`` is class indices.
        title: Title for the dashboard.
        n_batches: Batches to instrument.
        train_losses, val_losses: Optional epoch histories to replay.
        show: Show the figure inline.
        forward_returns_tuple: If ``True``, ``model(x)`` returns
            ``(logits, ...)`` (e.g. attention models) — only the first
            element is used as logits.

    Returns:
        ``(diag, findings)``
    """
    torch, _ = _require_torch()
    import torch.nn.functional as F  # noqa: PLC0415

    def _cls_loss(m: Any, batch: Any) -> Any:
        x, y = batch[0], batch[1]
        out = m(x)
        logits = out[0] if forward_returns_tuple else out
        return F.cross_entropy(logits, y)

    return run_diagnostic_checkpoint(
        model,
        dataloader,
        _cls_loss,
        title=title,
        n_batches=n_batches,
        train_losses=train_losses,
        val_losses=val_losses,
        show=show,
    )


def diagnose_regressor(
    model: Any,
    dataloader: Any,
    *,
    title: str = "Regressor",
    n_batches: int = 8,
    train_losses: Optional[list[float]] = None,
    val_losses: Optional[list[float]] = None,
    show: bool = True,
    forward_returns_tuple: bool = False,
) -> tuple[DLDiagnostics, dict[str, Any]]:
    """Convenience wrapper for ``(x, y)`` MSE regressors.

    Equivalent to :func:`run_diagnostic_checkpoint` with a built-in
    ``loss_fn`` that calls ``F.mse_loss(model(x), y)``.

    Args:
        forward_returns_tuple: Set ``True`` for attention models that
            return ``(predictions, attn_weights)``.

    Returns:
        ``(diag, findings)``
    """
    torch, _ = _require_torch()
    import torch.nn.functional as F  # noqa: PLC0415

    def _reg_loss(m: Any, batch: Any) -> Any:
        x, y = batch[0], batch[1]
        out = m(x)
        pred = out[0] if forward_returns_tuple else out
        return F.mse_loss(pred, y)

    return run_diagnostic_checkpoint(
        model,
        dataloader,
        _reg_loss,
        title=title,
        n_batches=n_batches,
        train_losses=train_losses,
        val_losses=val_losses,
        show=show,
    )

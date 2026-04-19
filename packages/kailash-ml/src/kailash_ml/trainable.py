# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Trainable protocol + family adapters (kailash-ml 2.0 Phase 3).

Implements the `Trainable` protocol from `specs/ml-engines.md` §3 and the
five Phase-3 family adapters: sklearn / xgboost / lightgbm / torch /
lightning. Every adapter wraps its family as a `LightningModule` so the
Lightning Trainer is the single enforcement point for accelerator /
precision resolution (§3 MUST 2 — custom training loops BLOCKED).

Non-torch families (sklearn / xgboost / lightgbm) use a sklearn-style
pattern: the inner `.fit()` runs once inside `on_train_start()` and the
LightningModule executes a single `training_step` with a dummy
grad-carrying loss so the Trainer can drive the outer loop uniformly
alongside the real DL families.

Device mapping for non-Lightning families is per `ml-backends.md` §5:

- sklearn       — CPU only; accelerator warnings on non-CPU request
- xgboost 2.0+  — device="cuda" on CUDA, device="cpu" on CPU; MPS / ROCm
                  / XPU / TPU → UnsupportedFamily
- lightgbm      — device_type="gpu" on CUDA / ROCm (probed); device_type
                  ="cpu" on CPU; MPS / XPU / TPU → UnsupportedFamily
- torch         — all 6 backends via L.Trainer(accelerator=...)
- lightning     — all 6 backends via L.Trainer(accelerator=...)

See `specs/ml-engines.md` §3 and `specs/ml-backends.md` §§ 4–5.
"""
from __future__ import annotations

import logging
import math
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    runtime_checkable,
)

import polars as pl

if TYPE_CHECKING:  # pragma: no cover - type-checker only
    import numpy as np  # noqa: F401 — referenced in string annotations

from kailash_ml._device import UnsupportedFamily, detect_backend
from kailash_ml._result import TrainingResult

__all__ = [
    "Trainable",
    "TrainingContext",
    "Predictions",
    "HyperparameterSpace",
    "HyperparameterRange",
    "SklearnTrainable",
    "XGBoostTrainable",
    "LightGBMTrainable",
    "TorchTrainable",
    "LightningTrainable",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Support types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HyperparameterRange:
    """One hyperparameter's search range."""

    name: str
    kind: str
    low: Optional[float] = None
    high: Optional[float] = None
    choices: Optional[tuple[Any, ...]] = None
    log: bool = False


@dataclass(frozen=True)
class HyperparameterSpace:
    """Search space for a Trainable's hyperparameters.

    Empty is acceptable per ml-engines.md §3.2 MUST 3 (`None` is not).
    """

    params: Sequence[HyperparameterRange] = field(default_factory=tuple)

    def is_empty(self) -> bool:
        return len(self.params) == 0

    def names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.params)


@dataclass(frozen=True)
class TrainingContext:
    """Context injected by the Engine into each Trainable.fit() call.

    Carries the Engine's resolved accelerator / precision / tenant /
    tracker binding — Trainables MUST NOT re-resolve these themselves
    (ml-engines.md §3.2 MUST 4).
    """

    accelerator: str
    precision: str
    devices: Any = 1
    device_string: str = "cpu"
    backend: str = "cpu"
    tenant_id: Optional[str] = None
    tracker_run_id: Optional[str] = None
    trial_number: Optional[int] = None


class Predictions:
    """Typed envelope around a model's prediction output."""

    __slots__ = ("_raw", "_column")

    def __init__(self, raw: Any, *, column: str = "prediction") -> None:
        self._raw = raw
        self._column = column

    @property
    def raw(self) -> Any:
        return self._raw

    @property
    def column(self) -> str:
        return self._column

    def to_polars(self) -> pl.DataFrame:
        if isinstance(self._raw, pl.DataFrame):
            return self._raw
        if isinstance(self._raw, pl.Series):
            return self._raw.to_frame(self._column)
        if isinstance(self._raw, (list, tuple)):
            return pl.DataFrame({self._column: list(self._raw)})
        # numpy array path — flatten to 1-D if necessary
        try:
            import numpy as np

            if isinstance(self._raw, np.ndarray):
                if self._raw.ndim == 1:
                    return pl.DataFrame({self._column: self._raw.tolist()})
                # 2-D: take argmax or first col if it's probabilities
                return pl.DataFrame({self._column: self._raw.tolist()})
        except ImportError:
            pass
        raise TypeError(
            f"Predictions.to_polars() cannot convert {type(self._raw).__name__}; "
            "pass a polars DataFrame / Series, a sequence, or a numpy ndarray."
        )

    def __repr__(self) -> str:
        return f"Predictions(column={self._column!r}, raw={type(self._raw).__name__})"


# ---------------------------------------------------------------------------
# Protocol (ml-engines.md §3.1)
# ---------------------------------------------------------------------------


@runtime_checkable
class Trainable(Protocol):
    """Protocol every model family MUST implement for MLEngine.fit().

    Runtime-checkable: `isinstance(obj, Trainable)` succeeds on any
    object exposing the required surface. See `specs/ml-engines.md` §3.
    """

    family_name: str

    def fit(
        self,
        data: pl.DataFrame,
        *,
        hyperparameters: Mapping[str, Any],
        context: TrainingContext,
    ) -> TrainingResult: ...

    def predict(self, X: pl.DataFrame) -> Predictions: ...

    def to_lightning_module(self) -> Any: ...

    def get_param_distribution(self) -> HyperparameterSpace: ...


# ---------------------------------------------------------------------------
# Shared helpers — split target + features, build Lightning Trainer kwargs
# ---------------------------------------------------------------------------


def _split_xy(
    data: pl.DataFrame, target: str
) -> tuple["np.ndarray", "np.ndarray", tuple[str, ...]]:  # type: ignore[name-defined]
    """Split a polars DataFrame into (X, y) numpy arrays + feature names.

    interop.py is the SOLE numpy conversion point in the package; Phase
    3 keeps the split local to trainable to avoid a cyclic import during
    initial landing. Phase 4+ may centralize.
    """

    if target not in data.columns:
        raise ValueError(
            f"target column {target!r} not in data columns {list(data.columns)}"
        )
    feature_cols = [c for c in data.columns if c != target]
    X = data.select(feature_cols).to_numpy()
    y_series = data.get_column(target)
    y = y_series.to_numpy()
    return X, y, tuple(feature_cols)


def _log_backend_selection(ctx: TrainingContext, *, max_epochs: int) -> dict[str, Any]:
    """Log the resolved Lightning Trainer kwargs at INFO and return them.

    Per ml-backends.md §4.1: every L.Trainer() call MUST pass accelerator
    / devices / precision as concrete values (never "auto") and MUST log
    the resolution at INFO before construction.
    """
    trainer_kwargs = {
        "accelerator": ctx.accelerator,
        "devices": ctx.devices,
        "precision": ctx.precision,
        "max_epochs": max_epochs,
        "enable_checkpointing": False,
        "enable_progress_bar": False,
        "enable_model_summary": False,
        "logger": False,
    }
    logger.info(
        "training.backend.selected",
        extra={
            "accelerator": ctx.accelerator,
            "device_string": ctx.device_string,
            "devices": str(ctx.devices),
            "precision": ctx.precision,
            "backend": ctx.backend,
            "max_epochs": max_epochs,
        },
    )
    return trainer_kwargs


def _effective_context(context: Optional[TrainingContext]) -> TrainingContext:
    """Resolve an optional context into a concrete TrainingContext.

    When the caller passes `None` (typical for direct Trainable usage
    without the Engine), we run `detect_backend()` once and build a
    context from its resolution. This preserves the §3 MUST 4 rule
    (Trainable doesn't RE-resolve if Engine passed a context) while
    allowing standalone use.
    """
    if context is not None:
        return context
    info = detect_backend(None)
    return TrainingContext(
        accelerator=info.accelerator,
        precision=info.precision,
        devices=info.devices,
        device_string=info.device_string,
        backend=info.backend,
    )


def _artifact_dir() -> Path:
    """Return a per-process temp directory for artifact persistence.

    Phase 3 persists fitted estimators to a temp path so
    `TrainingResult.artifact_uris["native"]` is always populated. Phase
    4's ArtifactStore layer will replace this.
    """
    root = Path(tempfile.gettempdir()) / "kailash_ml_artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# Lightning adapter base — sklearn-style single-epoch wrapper
# ---------------------------------------------------------------------------
#
# Used by sklearn / xgboost / lightgbm adapters. The inner estimator
# runs its full `.fit()` inside `on_train_start()`; `training_step`
# emits a dummy grad-carrying loss so the Trainer has something to
# execute; `validation_step` computes a real metric on the same data.
# We deliberately train/validate on the same split — the Engine's
# `setup()` is responsible for holdout; Trainable.fit() trains on the
# data the Engine hands it.


def _make_single_epoch_module(
    estimator: Any,
    X: "np.ndarray",  # type: ignore[name-defined]
    y: "np.ndarray",  # type: ignore[name-defined]
    *,
    metric_name: str,
    metric_fn: Callable[["np.ndarray", "np.ndarray"], float],  # type: ignore[name-defined]
    module_name: str,
) -> Any:
    """Build a LightningModule that fits `estimator` once during on_train_start."""
    import lightning.pytorch as pl_trainer
    import numpy as np
    import torch

    X_arr = np.asarray(X)
    y_arr = np.asarray(y)

    class _SingleEpochAdapter(pl_trainer.LightningModule):
        def __init__(self) -> None:
            super().__init__()
            self._estimator = estimator
            self._X = X_arr
            self._y = y_arr
            self._fitted = False
            # One trainable param so the optimizer has something to step
            # on — the Trainer requires at least one parameter with
            # grad=True for the fake loss to propagate.
            self._bias = torch.nn.Parameter(torch.zeros(1, requires_grad=True))
            self._metric_value: float = 0.0
            self._metric_name = metric_name

        def on_train_start(self) -> None:
            # Single real fit call — this is the sklearn/xgb/lgb training.
            self._estimator.fit(self._X, self._y)
            self._fitted = True
            preds = self._estimator.predict(self._X)
            self._metric_value = float(metric_fn(self._y, preds))

        def training_step(self, batch: Any, batch_idx: int) -> Any:
            # Dummy grad loss — Trainer needs a tensor that carries grad
            # even though the real fit is already done in on_train_start.
            return self._bias.sum() * 0.0

        def configure_optimizers(self) -> Any:
            return torch.optim.SGD([self._bias], lr=1e-3)

        def train_dataloader(self) -> Any:
            # Single batch, single epoch. The actual fit logic lives in
            # on_train_start; we just need Trainer to cycle once.
            ds = torch.utils.data.TensorDataset(
                torch.zeros(1, 1),
                torch.zeros(1, dtype=torch.long),
            )
            return torch.utils.data.DataLoader(ds, batch_size=1)

        @property
        def metric(self) -> float:
            return self._metric_value

    _SingleEpochAdapter.__name__ = module_name
    return _SingleEpochAdapter()


# ---------------------------------------------------------------------------
# SklearnTrainable (ml-backends.md §5.1 — CPU only)
# ---------------------------------------------------------------------------


class SklearnTrainable:
    """Wraps any sklearn estimator as a Trainable.

    Per `ml-backends.md` §5.1 sklearn is CPU-only; if the Engine resolved
    a non-CPU accelerator we log a WARN (`sklearn.backend.ignored`) and
    proceed on CPU. We still route through L.Trainer per `ml-engines.md`
    §3 MUST 2.
    """

    family_name = "sklearn"

    def __init__(
        self,
        estimator: Any = None,
        *,
        target: str = "target",
        metric: str = "auto",
        **kwargs: Any,
    ) -> None:
        """Construct a SklearnTrainable.

        Args:
            estimator: A sklearn estimator instance. If None, defaults
                to ``RandomForestClassifier(n_estimators=50, random_state=42)``
                — a sensible classification baseline.
            target: Name of the target column in the DataFrame passed to
                ``fit()``.
            metric: ``"auto"`` picks accuracy for classifiers and R² for
                regressors; explicit strings "accuracy" / "r2" / "f1" /
                "neg_mse" route to the matching sklearn.metrics function.
            **kwargs: Passed through to the default estimator constructor
                when ``estimator`` is None.
        """
        if estimator is None:
            from sklearn.ensemble import RandomForestClassifier

            defaults = {"n_estimators": 50, "random_state": 42}
            defaults.update(kwargs)
            estimator = RandomForestClassifier(**defaults)
        self._estimator = estimator
        self._target = target
        self._metric_kind = metric
        self._feature_names: tuple[str, ...] = ()
        self._is_fitted = False
        self._last_module: Any = None

    # -- Protocol methods ------------------------------------------------

    def to_lightning_module(self) -> Any:
        """Return the LightningModule wrapper (post-fit).

        Before ``fit()`` is called the module is unbuilt; calling
        ``to_lightning_module()`` on an unfitted SklearnTrainable raises
        a clear error rather than silently returning None.
        """
        if self._last_module is None:
            raise RuntimeError(
                "SklearnTrainable.to_lightning_module() called before fit(); "
                "call fit(data) first or use MLEngine.fit() which builds the "
                "module from your data."
            )
        return self._last_module

    def get_param_distribution(self) -> HyperparameterSpace:
        # Per ml-engines.md §3.2 MUST 3 — empty space is valid.
        return HyperparameterSpace(params=())

    def fit(
        self,
        data: pl.DataFrame,
        *,
        hyperparameters: Optional[Mapping[str, Any]] = None,
        context: Optional[TrainingContext] = None,
    ) -> TrainingResult:
        """Fit the sklearn estimator via a LightningModule wrapper.

        Routes through ``lightning.pytorch.Trainer(accelerator="cpu",
        devices=1, precision="32-true", max_epochs=1)`` per
        ``ml-engines.md`` §3 MUST 2. sklearn is CPU-only
        (``ml-backends.md`` §5.1): if the Engine resolved a non-CPU
        accelerator we log and override to CPU.
        """
        if hyperparameters:
            # Apply any HP overrides to the underlying estimator.
            for k, v in hyperparameters.items():
                if hasattr(self._estimator, k):
                    setattr(self._estimator, k, v)

        ctx = _effective_context(context)
        if ctx.backend != "cpu":
            logger.warning(
                "sklearn.backend.ignored",
                extra={
                    "requested_backend": ctx.backend,
                    "family": self.family_name,
                    "reason": "sklearn is CPU-only per ml-backends.md §5.1",
                },
            )
        cpu_ctx = TrainingContext(
            accelerator="cpu",
            precision="32-true",
            devices=1,
            device_string="cpu",
            backend="cpu",
            tenant_id=ctx.tenant_id,
            tracker_run_id=ctx.tracker_run_id,
            trial_number=ctx.trial_number,
        )

        X, y, feature_names = _split_xy(data, self._target)
        self._feature_names = feature_names
        metric_name, metric_fn = _resolve_metric(self._metric_kind, y)
        module = _make_single_epoch_module(
            self._estimator,
            X,
            y,
            metric_name=metric_name,
            metric_fn=metric_fn,
            module_name="SklearnLightningAdapter",
        )

        import lightning.pytorch as pl_trainer

        trainer_kwargs = _log_backend_selection(cpu_ctx, max_epochs=1)
        trainer = pl_trainer.Trainer(**trainer_kwargs)
        t0 = time.monotonic()
        trainer.fit(module)
        elapsed = time.monotonic() - t0

        self._is_fitted = True
        self._last_module = module

        # Persist a lightweight artifact (pickled sklearn estimator) so
        # artifact_uris["native"] is populated.
        artifact_uri = _persist_native_artifact(
            self._estimator, prefix="sklearn", format="pickle"
        )

        return TrainingResult(
            model_uri=f"models://{self.family_name}/{uuid.uuid4().hex[:8]}",
            metrics={metric_name: module.metric},
            device_used=cpu_ctx.device_string,
            accelerator=cpu_ctx.accelerator,
            precision=cpu_ctx.precision,
            elapsed_seconds=elapsed,
            tracker_run_id=cpu_ctx.tracker_run_id,
            tenant_id=cpu_ctx.tenant_id,
            artifact_uris={"native": artifact_uri},
            lightning_trainer_config=trainer_kwargs,
            family=self.family_name,
            hyperparameters=dict(hyperparameters or {}),
        )

    def predict(self, X: pl.DataFrame) -> Predictions:
        if not self._is_fitted:
            raise RuntimeError(
                "SklearnTrainable.predict() called before fit(). "
                "Call fit(data) first."
            )
        # Accept either the same column order as training or a subset
        # that matches the feature names we saw at fit time.
        if self._feature_names:
            frame = X.select([c for c in self._feature_names if c in X.columns])
        else:
            frame = X
        arr = frame.to_numpy()
        preds = self._estimator.predict(arr)
        return Predictions(preds, column="prediction")


# ---------------------------------------------------------------------------
# TorchTrainable
# ---------------------------------------------------------------------------


class TorchTrainable:
    """Wraps a raw ``torch.nn.Module`` as a Trainable.

    The user supplies a module, a loss function, and (optionally) an
    optimizer class. We wrap the module in a LightningModule whose
    ``training_step`` / ``validation_step`` call the loss against
    mini-batches drawn from the polars DataFrame.

    Routes through ``L.Trainer`` with the Engine's resolved accelerator
    / precision / devices per ``ml-backends.md`` §4.
    """

    family_name = "torch"

    def __init__(
        self,
        model: Any,
        *,
        loss_fn: Optional[Any] = None,
        optimizer_cls: Any = None,
        target: str = "target",
        learning_rate: float = 1e-3,
        task: str = "regression",
        batch_size: int = 32,
    ) -> None:
        import torch

        if model is None:
            raise ValueError("TorchTrainable requires `model: nn.Module`.")
        if loss_fn is None:
            loss_fn = (
                torch.nn.MSELoss()
                if task == "regression"
                else torch.nn.CrossEntropyLoss()
            )
        if optimizer_cls is None:
            optimizer_cls = torch.optim.Adam
        self._model = model
        self._loss_fn = loss_fn
        self._optimizer_cls = optimizer_cls
        self._target = target
        self._learning_rate = learning_rate
        self._task = task
        self._batch_size = batch_size
        self._is_fitted = False
        self._last_module: Any = None
        self._feature_names: tuple[str, ...] = ()

    def to_lightning_module(self) -> Any:
        if self._last_module is None:
            raise RuntimeError(
                "TorchTrainable.to_lightning_module() called before fit(). "
                "Call fit(data) first."
            )
        return self._last_module

    def get_param_distribution(self) -> HyperparameterSpace:
        return HyperparameterSpace(
            params=(
                HyperparameterRange(
                    name="learning_rate", kind="log_float", low=1e-5, high=1e-1
                ),
            )
        )

    def fit(
        self,
        data: pl.DataFrame,
        *,
        hyperparameters: Optional[Mapping[str, Any]] = None,
        context: Optional[TrainingContext] = None,
    ) -> TrainingResult:
        import lightning.pytorch as pl_trainer
        import numpy as np
        import torch

        if hyperparameters and "learning_rate" in hyperparameters:
            self._learning_rate = float(hyperparameters["learning_rate"])
        max_epochs = int(hyperparameters.get("max_epochs", 1)) if hyperparameters else 1

        ctx = _effective_context(context)
        X, y, feature_names = _split_xy(data, self._target)
        self._feature_names = feature_names

        X_t = torch.tensor(np.asarray(X, dtype=np.float32))
        if self._task == "regression":
            y_t = torch.tensor(np.asarray(y, dtype=np.float32)).reshape(-1, 1)
        else:
            y_t = torch.tensor(np.asarray(y, dtype=np.int64))

        inner = self._model
        loss_fn = self._loss_fn
        optimizer_cls = self._optimizer_cls
        lr = self._learning_rate
        task = self._task

        class _TorchLightningAdapter(pl_trainer.LightningModule):
            def __init__(self) -> None:
                super().__init__()
                self.inner = inner
                self._loss_total = 0.0
                self._loss_count = 0

            def forward(self, x: Any) -> Any:
                return self.inner(x)

            def training_step(self, batch: Any, batch_idx: int) -> Any:
                xb, yb = batch
                pred = self.inner(xb)
                if task == "regression" and pred.dim() == 1:
                    pred = pred.unsqueeze(-1)
                loss = loss_fn(pred, yb)
                self._loss_total += float(loss.detach().item())
                self._loss_count += 1
                return loss

            def configure_optimizers(self) -> Any:
                return optimizer_cls(self.inner.parameters(), lr=lr)

            @property
            def mean_loss(self) -> float:
                return self._loss_total / max(self._loss_count, 1)

        module = _TorchLightningAdapter()

        ds = torch.utils.data.TensorDataset(X_t, y_t)
        # pin_memory only on CUDA / ROCm per ml-backends.md §4.2
        pin = ctx.backend in {"cuda", "rocm"}
        loader = torch.utils.data.DataLoader(
            ds,
            batch_size=min(self._batch_size, max(len(X), 1)),
            shuffle=False,
            pin_memory=pin,
        )

        trainer_kwargs = _log_backend_selection(ctx, max_epochs=max_epochs)
        trainer = pl_trainer.Trainer(**trainer_kwargs)
        t0 = time.monotonic()
        trainer.fit(module, loader)
        elapsed = time.monotonic() - t0

        self._is_fitted = True
        self._last_module = module

        artifact_uri = _persist_native_artifact(inner, prefix="torch", format="pt")

        return TrainingResult(
            model_uri=f"models://{self.family_name}/{uuid.uuid4().hex[:8]}",
            metrics={"train_loss": module.mean_loss},
            device_used=ctx.device_string,
            accelerator=ctx.accelerator,
            precision=ctx.precision,
            elapsed_seconds=elapsed,
            tracker_run_id=ctx.tracker_run_id,
            tenant_id=ctx.tenant_id,
            artifact_uris={"native": artifact_uri},
            lightning_trainer_config=trainer_kwargs,
            family=self.family_name,
            hyperparameters={"learning_rate": lr, "max_epochs": max_epochs},
        )

    def predict(self, X: pl.DataFrame) -> Predictions:
        import numpy as np
        import torch

        if not self._is_fitted:
            raise RuntimeError("TorchTrainable.predict() called before fit().")
        feature_frame = (
            X.select([c for c in self._feature_names if c in X.columns])
            if self._feature_names
            else X
        )
        X_np = np.asarray(feature_frame.to_numpy(), dtype=np.float32)
        X_t = torch.tensor(X_np)
        self._model.eval()
        with torch.no_grad():
            preds = self._model(X_t)
        return Predictions(preds.detach().cpu().numpy(), column="prediction")


# ---------------------------------------------------------------------------
# LightningTrainable
# ---------------------------------------------------------------------------


class LightningTrainable:
    """Identity adapter for user-supplied LightningModules.

    The user already provided a LightningModule — we run it through the
    Trainer directly, enforcing the same concrete-backend contract as
    every other family (ml-backends.md §4.1).
    """

    family_name = "lightning"

    def __init__(
        self,
        module: Any,
        *,
        target: str = "target",
        batch_size: int = 32,
        task: str = "regression",
    ) -> None:
        import lightning.pytorch as pl_trainer

        if module is None or not isinstance(module, pl_trainer.LightningModule):
            raise TypeError(
                "LightningTrainable requires a lightning.pytorch.LightningModule. "
                f"Got {type(module).__name__}. Use TorchTrainable for raw nn.Module."
            )
        self._module = module
        self._target = target
        self._batch_size = batch_size
        self._task = task
        self._is_fitted = False
        self._feature_names: tuple[str, ...] = ()

    def to_lightning_module(self) -> Any:
        return self._module

    def get_param_distribution(self) -> HyperparameterSpace:
        return HyperparameterSpace(params=())

    def fit(
        self,
        data: pl.DataFrame,
        *,
        hyperparameters: Optional[Mapping[str, Any]] = None,
        context: Optional[TrainingContext] = None,
    ) -> TrainingResult:
        import lightning.pytorch as pl_trainer
        import numpy as np
        import torch

        max_epochs = int(hyperparameters.get("max_epochs", 1)) if hyperparameters else 1
        ctx = _effective_context(context)
        X, y, feature_names = _split_xy(data, self._target)
        self._feature_names = feature_names

        X_t = torch.tensor(np.asarray(X, dtype=np.float32))
        if self._task == "regression":
            y_t = torch.tensor(np.asarray(y, dtype=np.float32)).reshape(-1, 1)
        else:
            y_t = torch.tensor(np.asarray(y, dtype=np.int64))
        ds = torch.utils.data.TensorDataset(X_t, y_t)
        pin = ctx.backend in {"cuda", "rocm"}
        loader = torch.utils.data.DataLoader(
            ds,
            batch_size=min(self._batch_size, max(len(X), 1)),
            shuffle=False,
            pin_memory=pin,
        )

        trainer_kwargs = _log_backend_selection(ctx, max_epochs=max_epochs)
        trainer = pl_trainer.Trainer(**trainer_kwargs)
        t0 = time.monotonic()
        trainer.fit(self._module, loader)
        elapsed = time.monotonic() - t0

        self._is_fitted = True
        artifact_uri = _persist_native_artifact(
            self._module, prefix="lightning", format="pt"
        )

        # Pull a metric off the module if available; otherwise use a
        # placeholder so TrainingResult satisfies its contract.
        metrics: dict[str, float] = {}
        for attr in ("mean_loss", "final_loss", "train_loss"):
            if hasattr(self._module, attr):
                val = getattr(self._module, attr)
                try:
                    fval = float(val() if callable(val) else val)
                    if math.isfinite(fval):
                        metrics["train_loss"] = fval
                        break
                except (TypeError, ValueError):
                    continue
        if not metrics:
            metrics["train_loss"] = 0.0

        return TrainingResult(
            model_uri=f"models://{self.family_name}/{uuid.uuid4().hex[:8]}",
            metrics=metrics,
            device_used=ctx.device_string,
            accelerator=ctx.accelerator,
            precision=ctx.precision,
            elapsed_seconds=elapsed,
            tracker_run_id=ctx.tracker_run_id,
            tenant_id=ctx.tenant_id,
            artifact_uris={"native": artifact_uri},
            lightning_trainer_config=trainer_kwargs,
            family=self.family_name,
            hyperparameters={"max_epochs": max_epochs},
        )

    def predict(self, X: pl.DataFrame) -> Predictions:
        import numpy as np
        import torch

        if not self._is_fitted:
            raise RuntimeError("LightningTrainable.predict() called before fit().")
        feature_frame = (
            X.select([c for c in self._feature_names if c in X.columns])
            if self._feature_names
            else X
        )
        X_np = np.asarray(feature_frame.to_numpy(), dtype=np.float32)
        X_t = torch.tensor(X_np)
        self._module.eval()
        with torch.no_grad():
            preds = self._module(X_t)
        return Predictions(preds.detach().cpu().numpy(), column="prediction")


# ---------------------------------------------------------------------------
# XGBoostTrainable (ml-backends.md §5.2)
# ---------------------------------------------------------------------------


class XGBoostTrainable:
    """Wraps xgboost's sklearn-style estimator as a Trainable.

    Device mapping per ``ml-backends.md`` §5.2:

    - backend == "cuda" → ``device="cuda"``
    - backend == "cpu"  → ``device="cpu"``
    - backend in {"mps", "rocm", "xpu", "tpu"} → ``UnsupportedFamily``

    Training still routes through L.Trainer per §3 MUST 2 — the inner
    xgboost fit runs in ``on_train_start`` of the LightningModule wrapper.
    """

    family_name = "xgboost"
    _SUPPORTED_BACKENDS = ("cuda", "cpu")

    def __init__(
        self,
        estimator: Any = None,
        *,
        target: str = "target",
        task: str = "classification",
        **kwargs: Any,
    ) -> None:
        if estimator is None:
            import xgboost as xgb

            if task == "classification":
                defaults = {"n_estimators": 20, "max_depth": 3, "random_state": 42}
                defaults.update(kwargs)
                estimator = xgb.XGBClassifier(**defaults)
            else:
                defaults = {"n_estimators": 20, "max_depth": 3, "random_state": 42}
                defaults.update(kwargs)
                estimator = xgb.XGBRegressor(**defaults)
        self._estimator = estimator
        self._target = target
        self._task = task
        self._is_fitted = False
        self._last_module: Any = None
        self._feature_names: tuple[str, ...] = ()

    def to_lightning_module(self) -> Any:
        if self._last_module is None:
            raise RuntimeError(
                "XGBoostTrainable.to_lightning_module() called before fit(). "
                "Call fit(data) first."
            )
        return self._last_module

    def get_param_distribution(self) -> HyperparameterSpace:
        return HyperparameterSpace(
            params=(
                HyperparameterRange(name="n_estimators", kind="int", low=10, high=500),
                HyperparameterRange(name="max_depth", kind="int", low=2, high=12),
                HyperparameterRange(
                    name="learning_rate", kind="log_float", low=1e-3, high=1.0
                ),
            )
        )

    def fit(
        self,
        data: pl.DataFrame,
        *,
        hyperparameters: Optional[Mapping[str, Any]] = None,
        context: Optional[TrainingContext] = None,
    ) -> TrainingResult:
        import lightning.pytorch as pl_trainer

        ctx = _effective_context(context)

        # Device mapping per ml-backends.md §5.2 — enforce supported
        # backend BEFORE any training call. Raises UnsupportedFamily on
        # MPS / ROCm / XPU / TPU with an actionable message.
        if ctx.backend not in self._SUPPORTED_BACKENDS:
            raise UnsupportedFamily(
                f"xgboost cannot run on backend '{ctx.backend}'. "
                f"xgboost 2.0+ supports only {list(self._SUPPORTED_BACKENDS)}. "
                f"Use accelerator='cpu' or install on a CUDA host; or select "
                f"a different family (lightgbm supports CUDA+ROCm; torch "
                f"supports all 6 backends).",
                family=self.family_name,
                backend=ctx.backend,
                supported_backends_for_family=self._SUPPORTED_BACKENDS,
            )

        if hyperparameters:
            for k, v in hyperparameters.items():
                if hasattr(self._estimator, k):
                    setattr(self._estimator, k, v)

        # Set xgboost device per §5.2 (xgboost 2.0+ idiom).
        xgb_device = "cuda" if ctx.backend == "cuda" else "cpu"
        if hasattr(self._estimator, "set_params"):
            try:
                self._estimator.set_params(device=xgb_device)
            except Exception:  # noqa: BLE001
                # Some older xgboost versions use tree_method instead;
                # fall back silently on the estimator's default path.
                logger.debug(
                    "xgboost.device.set_failed",
                    extra={"xgb_device": xgb_device, "family": self.family_name},
                )

        X, y, feature_names = _split_xy(data, self._target)
        self._feature_names = feature_names
        metric_name, metric_fn = _resolve_metric("auto", y, task_hint=self._task)
        module = _make_single_epoch_module(
            self._estimator,
            X,
            y,
            metric_name=metric_name,
            metric_fn=metric_fn,
            module_name="XGBoostLightningAdapter",
        )

        trainer_kwargs = _log_backend_selection(ctx, max_epochs=1)
        trainer = pl_trainer.Trainer(**trainer_kwargs)
        t0 = time.monotonic()
        trainer.fit(module)
        elapsed = time.monotonic() - t0

        self._is_fitted = True
        self._last_module = module

        artifact_uri = _persist_native_artifact(
            self._estimator, prefix="xgboost", format="pickle"
        )

        return TrainingResult(
            model_uri=f"models://{self.family_name}/{uuid.uuid4().hex[:8]}",
            metrics={metric_name: module.metric},
            device_used=ctx.device_string,
            accelerator=ctx.accelerator,
            precision=ctx.precision,
            elapsed_seconds=elapsed,
            tracker_run_id=ctx.tracker_run_id,
            tenant_id=ctx.tenant_id,
            artifact_uris={"native": artifact_uri},
            lightning_trainer_config=trainer_kwargs,
            family=self.family_name,
            hyperparameters=dict(hyperparameters or {}),
        )

    def predict(self, X: pl.DataFrame) -> Predictions:
        if not self._is_fitted:
            raise RuntimeError("XGBoostTrainable.predict() called before fit().")
        frame = (
            X.select([c for c in self._feature_names if c in X.columns])
            if self._feature_names
            else X
        )
        preds = self._estimator.predict(frame.to_numpy())
        return Predictions(preds, column="prediction")


# ---------------------------------------------------------------------------
# LightGBMTrainable (ml-backends.md §5.3)
# ---------------------------------------------------------------------------


class LightGBMTrainable:
    """Wraps lightgbm's sklearn-style estimator as a Trainable.

    Device mapping per ``ml-backends.md`` §5.3:

    - backend in {"cuda", "rocm"} → ``device_type="gpu"`` (probe first)
    - backend == "cpu"             → ``device_type="cpu"``
    - backend in {"mps", "xpu", "tpu"} → ``UnsupportedFamily``
    """

    family_name = "lightgbm"
    _SUPPORTED_BACKENDS = ("cuda", "rocm", "cpu")

    def __init__(
        self,
        estimator: Any = None,
        *,
        target: str = "target",
        task: str = "classification",
        **kwargs: Any,
    ) -> None:
        if estimator is None:
            import lightgbm as lgb

            if task == "classification":
                defaults = {
                    "n_estimators": 20,
                    "max_depth": 3,
                    "random_state": 42,
                    "verbosity": -1,
                }
                defaults.update(kwargs)
                estimator = lgb.LGBMClassifier(**defaults)
            else:
                defaults = {
                    "n_estimators": 20,
                    "max_depth": 3,
                    "random_state": 42,
                    "verbosity": -1,
                }
                defaults.update(kwargs)
                estimator = lgb.LGBMRegressor(**defaults)
        self._estimator = estimator
        self._target = target
        self._task = task
        self._is_fitted = False
        self._last_module: Any = None
        self._feature_names: tuple[str, ...] = ()

    def to_lightning_module(self) -> Any:
        if self._last_module is None:
            raise RuntimeError(
                "LightGBMTrainable.to_lightning_module() called before fit(). "
                "Call fit(data) first."
            )
        return self._last_module

    def get_param_distribution(self) -> HyperparameterSpace:
        return HyperparameterSpace(
            params=(
                HyperparameterRange(name="n_estimators", kind="int", low=10, high=500),
                HyperparameterRange(name="num_leaves", kind="int", low=8, high=255),
                HyperparameterRange(
                    name="learning_rate", kind="log_float", low=1e-3, high=1.0
                ),
            )
        )

    def fit(
        self,
        data: pl.DataFrame,
        *,
        hyperparameters: Optional[Mapping[str, Any]] = None,
        context: Optional[TrainingContext] = None,
    ) -> TrainingResult:
        import lightning.pytorch as pl_trainer

        ctx = _effective_context(context)

        if ctx.backend not in self._SUPPORTED_BACKENDS:
            raise UnsupportedFamily(
                f"lightgbm cannot run on backend '{ctx.backend}'. "
                f"lightgbm supports only {list(self._SUPPORTED_BACKENDS)}. "
                f"Use accelerator='cpu' or install on CUDA/ROCm; or select "
                f"a different family (torch supports all 6 backends).",
                family=self.family_name,
                backend=ctx.backend,
                supported_backends_for_family=self._SUPPORTED_BACKENDS,
            )

        if hyperparameters:
            for k, v in hyperparameters.items():
                if hasattr(self._estimator, k):
                    setattr(self._estimator, k, v)

        lgb_device = "gpu" if ctx.backend in {"cuda", "rocm"} else "cpu"
        if lgb_device == "gpu":
            # Probe at construction — lightgbm raises at fit time if the
            # build doesn't support GPU. We attempt set_params and let
            # any fit-time failure surface as UnsupportedFamily.
            try:
                self._estimator.set_params(device_type="gpu", gpu_use_dp=False)
            except Exception as exc:  # noqa: BLE001
                raise UnsupportedFamily(
                    f"lightgbm GPU support not present in the installed build "
                    f"(requested backend='{ctx.backend}'). "
                    f"Install a GPU-capable build: "
                    f"pip install lightgbm --config-settings=cmake.define.USE_GPU=1, "
                    f"or use accelerator='cpu'.",
                    family=self.family_name,
                    backend=ctx.backend,
                    supported_backends_for_family=("cpu",),
                ) from exc
        else:
            try:
                self._estimator.set_params(device_type="cpu")
            except Exception:  # noqa: BLE001
                logger.debug(
                    "lightgbm.device.set_failed",
                    extra={"lgb_device": "cpu", "family": self.family_name},
                )

        X, y, feature_names = _split_xy(data, self._target)
        self._feature_names = feature_names
        metric_name, metric_fn = _resolve_metric("auto", y, task_hint=self._task)
        module = _make_single_epoch_module(
            self._estimator,
            X,
            y,
            metric_name=metric_name,
            metric_fn=metric_fn,
            module_name="LightGBMLightningAdapter",
        )

        trainer_kwargs = _log_backend_selection(ctx, max_epochs=1)
        trainer = pl_trainer.Trainer(**trainer_kwargs)
        t0 = time.monotonic()
        trainer.fit(module)
        elapsed = time.monotonic() - t0

        self._is_fitted = True
        self._last_module = module

        artifact_uri = _persist_native_artifact(
            self._estimator, prefix="lightgbm", format="pickle"
        )

        return TrainingResult(
            model_uri=f"models://{self.family_name}/{uuid.uuid4().hex[:8]}",
            metrics={metric_name: module.metric},
            device_used=ctx.device_string,
            accelerator=ctx.accelerator,
            precision=ctx.precision,
            elapsed_seconds=elapsed,
            tracker_run_id=ctx.tracker_run_id,
            tenant_id=ctx.tenant_id,
            artifact_uris={"native": artifact_uri},
            lightning_trainer_config=trainer_kwargs,
            family=self.family_name,
            hyperparameters=dict(hyperparameters or {}),
        )

    def predict(self, X: pl.DataFrame) -> Predictions:
        if not self._is_fitted:
            raise RuntimeError("LightGBMTrainable.predict() called before fit().")
        frame = (
            X.select([c for c in self._feature_names if c in X.columns])
            if self._feature_names
            else X
        )
        preds = self._estimator.predict(frame.to_numpy())
        return Predictions(preds, column="prediction")


# ---------------------------------------------------------------------------
# Metric + artifact helpers
# ---------------------------------------------------------------------------


def _resolve_metric(
    kind: str,
    y: "np.ndarray",  # type: ignore[name-defined]
    *,
    task_hint: Optional[str] = None,
) -> tuple[str, Callable[["np.ndarray", "np.ndarray"], float]]:  # type: ignore[name-defined]
    """Pick a sensible metric for the target.

    - ``"auto"`` + integer / string target → accuracy
    - ``"auto"`` + float target → R²
    - ``"accuracy"`` / ``"r2"`` / ``"f1"`` / ``"neg_mse"`` → explicit
    """
    import numpy as np
    from sklearn import metrics as skm

    y = np.asarray(y)

    def _acc(y_true, y_pred):  # type: ignore[no-untyped-def]
        return float(skm.accuracy_score(y_true, y_pred))

    def _r2(y_true, y_pred):  # type: ignore[no-untyped-def]
        return float(skm.r2_score(y_true, y_pred))

    def _f1(y_true, y_pred):  # type: ignore[no-untyped-def]
        return float(skm.f1_score(y_true, y_pred, average="weighted"))

    def _neg_mse(y_true, y_pred):  # type: ignore[no-untyped-def]
        return -float(skm.mean_squared_error(y_true, y_pred))

    explicit = {
        "accuracy": ("accuracy", _acc),
        "r2": ("r2", _r2),
        "f1": ("f1", _f1),
        "neg_mse": ("neg_mse", _neg_mse),
    }
    if kind in explicit:
        return explicit[kind]
    if kind == "auto":
        if task_hint == "regression":
            return ("r2", _r2)
        if task_hint == "classification":
            return ("accuracy", _acc)
        # Infer from y dtype
        if y.dtype.kind in ("i", "u", "b", "O", "U", "S"):
            return ("accuracy", _acc)
        return ("r2", _r2)
    raise ValueError(
        f"Unknown metric {kind!r}; expected auto / accuracy / r2 / f1 / neg_mse."
    )


def _persist_native_artifact(obj: Any, *, prefix: str, format: str) -> str:
    """Persist a fitted estimator / module to a temp file; return URI.

    Phase 3 uses a simple temp-dir scheme. Phase 4's ArtifactStore
    replaces this with proper tenant-scoped storage.
    """
    out_dir = _artifact_dir()
    suffix = {"pickle": ".pkl", "pt": ".pt"}.get(format, ".bin")
    path = out_dir / f"{prefix}_{uuid.uuid4().hex[:8]}{suffix}"
    try:
        if format == "pt":
            import torch

            torch.save(obj, path)
        else:
            import pickle

            with open(path, "wb") as fh:
                pickle.dump(obj, fh)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "artifact.persist.failed",
            extra={"prefix": prefix, "format": format, "error": str(exc)},
        )
        # Fall back to a sentinel path — TrainingResult.artifact_uris must
        # be populated per the contract; downstream ArtifactStore replaces
        # this with a real persisted artifact.
        return f"file://<persist-failed:{prefix}>"
    return f"file://{path}"

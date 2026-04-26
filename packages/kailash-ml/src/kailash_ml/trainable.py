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
from kailash_ml._device_report import DeviceReport
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
    "CatBoostTrainable",
    "TorchTrainable",
    "LightningTrainable",
    "UMAPTrainable",
    "HDBSCANTrainable",
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

    The Lightning passthrough block (``strategy``, ``num_nodes``,
    ``enable_checkpointing``, ``auto_find_lr``, ``callbacks``) carries
    the W20 ``MLEngine.fit()`` kwargs into the TrainingPipeline /
    Trainable adapter per ``ml-engines-v2.md`` §3.2 MUST 6-8.
    """

    accelerator: str
    precision: str
    devices: Any = 1
    device_string: str = "cpu"
    backend: str = "cpu"
    tenant_id: Optional[str] = None
    tracker_run_id: Optional[str] = None
    trial_number: Optional[int] = None
    # Lightning passthrough (ml-engines-v2.md §3.2 MUST 6-8 / §2.2).
    # `strategy` is typed Any because concrete values are `str | None |
    # lightning.pytorch.strategies.Strategy` and importing lightning at
    # module-load time would force the `[dl]` extra.
    strategy: Any = None
    num_nodes: int = 1
    enable_checkpointing: bool = True
    auto_find_lr: bool = False
    callbacks: Optional[tuple] = None


class Predictions:
    """Typed envelope around a model's prediction output.

    Carries a ``device: Optional[DeviceReport]`` — populated by every
    Phase-1 family adapter — so callers can programmatically distinguish
    a CUDA-resolved predict from a CPU-fallback predict. The adapter
    caches the DeviceReport from its most-recent ``fit()`` call and
    stamps it onto every ``Predictions`` it returns until the next
    ``fit()`` overwrites it. See
    ``workspaces/kailash-ml-gpu-stack/journal/0005-GAP-predictions-device-field-missing.md``.
    """

    __slots__ = ("_raw", "_column", "_device")

    def __init__(
        self,
        raw: Any,
        *,
        column: str = "prediction",
        device: Optional[DeviceReport] = None,
    ) -> None:
        self._raw = raw
        self._column = column
        self._device = device

    @property
    def raw(self) -> Any:
        return self._raw

    @property
    def column(self) -> str:
        return self._column

    @property
    def device(self) -> Optional[DeviceReport]:
        """Per-call device evidence for this predict, if the adapter fitted.

        ``None`` is returned only by callers that construct ``Predictions``
        directly without going through a fitted Trainable (rare;
        typically only in unit tests). Every Phase-1 adapter's
        ``predict()`` populates this from the device report cached at
        fit-time.
        """
        return self._device

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


def _is_gpu_oom_error(exc: BaseException) -> bool:
    """Return True if ``exc`` looks like a GPU out-of-memory error.

    Recognises the common messages across xgboost (``XGBoostError`` with
    "out of memory"), torch (``torch.cuda.OutOfMemoryError``,
    ``RuntimeError: CUDA out of memory``), and lightgbm
    (``LightGBMError`` with OOM text). Per revised-stack.md § "No-config
    contract" (xgboost / lightgbm rows) this is the signal that triggers
    the single-retry CPU fallback; any non-OOM exception re-raises
    unchanged (zero-tolerance.md Rule 3 — no silent swallow).
    """
    msg = str(exc).lower()
    if (
        "out of memory" in msg
        or "cuda out of memory" in msg
        or "cuda error: out of memory" in msg
        or "oom" in msg
    ):
        return True
    # Typed OOM classes without English messages (torch's
    # CudaOutOfMemoryError subclasses on some builds expose an empty
    # args tuple; catch by class name so the detection survives).
    return type(exc).__name__ in ("OutOfMemoryError", "CudaOutOfMemoryError")


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
# SklearnTrainable (ml-backends.md §5.1 + GPU-first Phase 1 Array-API dispatch)
# ---------------------------------------------------------------------------
#
# Per the revised-stack spec (workspaces/kailash-ml-gpu-stack/04-validate/
# 02-revised-stack.md lines 84-89), sklearn is CPU-only via the stock numpy
# path BUT can run on the detected device via scikit-learn's Array API
# dispatch for a supported subset of estimators. We engage the Array API
# context when the estimator is on the allowlist AND the caller requested
# a non-CPU backend. Off-allowlist estimators fall back to CPU numpy and
# emit `sklearn.array_api.offlist` at WARN with
# ``fallback_reason="array_api_offlist"`` on the returned ``DeviceReport``.
#
# Allowlist membership is matched on ``type(estimator).__name__`` to keep
# the import surface cheap — pulling in every allowlisted class at module
# import time would defeat the "light sklearn baseline" Phase 3 decision.
# The initial set is conservative (scikit-learn 1.5+ Array API dispatch
# coverage; see the scikit-learn "Array API support" docs). Expansion is a
# spec-level edit, not a code edit.
_SKLEARN_ARRAY_API_ALLOWLIST: frozenset[str] = frozenset(
    {
        "Ridge",
        "LogisticRegression",
        "LinearRegression",
        "LinearDiscriminantAnalysis",
        "KMeans",
        "PCA",
        "StandardScaler",
        "MinMaxScaler",
    }
)


class SklearnTrainable:
    """Wraps any sklearn estimator as a Trainable.

    Two device paths per revised-stack spec lines 84-89:

    * **On allowlist + non-CPU requested** — engage
      ``sklearn.config_context(array_api_dispatch=True)`` around the inner
      estimator fit and move inputs to a torch tensor on
      ``ctx.device_string``. Emits INFO ``sklearn.array_api.engaged``.
      ``TrainingResult.device.array_api == True``.
    * **Off allowlist OR CPU requested** — fall back to CPU numpy as in
      pre-Phase-1 behavior. When the caller asked for a non-CPU backend
      that we had to ignore, emit WARN ``sklearn.array_api.offlist``
      with ``fallback_reason="array_api_offlist"``.

    We still route through L.Trainer per ``ml-engines.md`` §3 MUST 2 for
    both paths — Lightning is the enforcement point for accelerator /
    precision resolution, even when the actual fit runs inside the
    Array API context.
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

    @property
    def model(self) -> Any:
        """Fitted model handle per W33c / `ml-registry.md` §5.6.1.

        Exposed so `MLEngine.register(result)` can locate the trained
        model via ``result.trainable.model`` without each adapter
        duplicating the lookup convention. For sklearn the model IS
        the estimator.
        """
        return self._estimator

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

        Two device paths per revised-stack spec lines 84-89:

        * **Array API engaged** (on-allowlist + non-CPU requested): wraps
          the inner estimator fit in
          ``sklearn.config_context(array_api_dispatch=True)`` and moves
          X/y to a torch tensor on ``ctx.device_string``. The returned
          ``TrainingResult.device.array_api`` is True.
        * **CPU fallback** (off-allowlist, or CPU requested): inner
          estimator fit runs on numpy as in pre-Phase-1 behavior. When a
          non-CPU backend was requested but the estimator was
          off-allowlist we emit WARN ``sklearn.array_api.offlist`` and
          stamp the ``DeviceReport`` with
          ``fallback_reason="array_api_offlist"``.

        Routes through ``lightning.pytorch.Trainer(accelerator="cpu",
        devices=1, precision="32-true", max_epochs=1)`` per
        ``ml-engines.md`` §3 MUST 2 in both paths — Lightning is the
        enforcement point for accelerator / precision resolution even
        when the actual fit runs inside an Array API dispatch context.
        """
        if hyperparameters:
            # Apply any HP overrides to the underlying estimator.
            for k, v in hyperparameters.items():
                if hasattr(self._estimator, k):
                    setattr(self._estimator, k, v)

        ctx = _effective_context(context)
        estimator_class = type(self._estimator).__name__
        on_allowlist = estimator_class in _SKLEARN_ARRAY_API_ALLOWLIST
        non_cpu_requested = ctx.backend != "cpu"
        engage_array_api = on_allowlist and non_cpu_requested

        if engage_array_api:
            # INFO — normal transition: Array API dispatch is the expected
            # code path for an allowlisted estimator on a detected GPU
            # backend. No fallback, no degradation.
            logger.info(
                "sklearn.array_api.engaged",
                extra={
                    "family": self.family_name,
                    "estimator_class": estimator_class,
                    "backend": ctx.backend,
                    "device_string": ctx.device_string,
                },
            )
        elif non_cpu_requested:
            # WARN — degraded path: caller asked for a GPU but the
            # estimator is off-allowlist, so we fall back to CPU numpy.
            logger.warning(
                "sklearn.array_api.offlist",
                extra={
                    "family": self.family_name,
                    "estimator_class": estimator_class,
                    "requested_backend": ctx.backend,
                    "fallback_reason": "array_api_offlist",
                },
            )

        # The Lightning Trainer always runs on CPU — Array API is a
        # data-path dispatch, not a Trainer-accelerator knob. This keeps
        # the outer loop uniform across all non-DL families.
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

        if engage_array_api:
            # Move inputs to torch tensors on the resolved device so the
            # Array API dispatcher routes through torch's backend.
            import torch  # noqa: PLC0415 — local to GPU path

            X_fit = torch.as_tensor(X, device=ctx.device_string)
            y_fit = torch.as_tensor(y, device=ctx.device_string)
        else:
            X_fit, y_fit = X, y

        module = _make_single_epoch_module(
            self._estimator,
            X_fit,
            y_fit,
            metric_name=metric_name,
            metric_fn=metric_fn,
            module_name="SklearnLightningAdapter",
        )

        import lightning.pytorch as pl_trainer

        trainer_kwargs = _log_backend_selection(cpu_ctx, max_epochs=1)
        trainer = pl_trainer.Trainer(**trainer_kwargs)
        t0 = time.monotonic()
        # If engage_array_api was True but scipy's Array API support is
        # not enabled at the env-var level (SCIPY_ARRAY_API=1 before any
        # scipy/sklearn import), sklearn's config_context raises at
        # enter-time. We catch that and fall back to the CPU numpy path
        # with a WARN log so the deployment gap is visible in log
        # aggregators. This is the documented failure mode of sklearn's
        # array_api_dispatch — it requires a pre-import env-var switch
        # that many production images do not yet set by default.
        array_api_runtime_failed = False
        if engage_array_api:
            import sklearn  # noqa: PLC0415 — local to GPU path

            try:
                with sklearn.config_context(array_api_dispatch=True):
                    trainer.fit(module)
            except RuntimeError as exc:
                # scipy array_api gate — "Scikit-learn array API support
                # was enabled but scipy's own support is not enabled"
                if "array API" not in str(exc) and "array_api" not in str(exc):
                    raise
                logger.warning(
                    "sklearn.array_api.runtime_unavailable",
                    extra={
                        "family": self.family_name,
                        "estimator_class": estimator_class,
                        "requested_backend": ctx.backend,
                        "fallback_reason": "array_api_runtime_unavailable",
                        "hint": "set SCIPY_ARRAY_API=1 before any sklearn/scipy import",
                    },
                )
                array_api_runtime_failed = True
                # Retry CPU numpy path — rebuild module with un-tensor'd
                # inputs so the estimator sees plain arrays.
                module = _make_single_epoch_module(
                    self._estimator,
                    X,
                    y,
                    metric_name=metric_name,
                    metric_fn=metric_fn,
                    module_name="SklearnLightningAdapter",
                )
                trainer = pl_trainer.Trainer(**trainer_kwargs)
                trainer.fit(module)
        else:
            trainer.fit(module)
        elapsed = time.monotonic() - t0

        self._is_fitted = True
        self._last_module = module

        # Persist a lightweight artifact (pickled sklearn estimator) so
        # artifact_uris["native"] is populated.
        artifact_uri = _persist_native_artifact(
            self._estimator, prefix="sklearn", format="pickle"
        )

        # DeviceReport carries POST-resolution evidence — what actually
        # ran, not what was requested. Array API path points at the
        # resolved GPU device; fallback path points at "cpu" with
        # ``fallback_reason`` set when a non-CPU request was ignored.
        if engage_array_api and not array_api_runtime_failed:
            device_report = DeviceReport(
                family=self.family_name,
                backend=ctx.backend,
                device_string=ctx.device_string,
                precision=ctx.precision,
                fallback_reason=None,
                array_api=True,
            )
        elif engage_array_api and array_api_runtime_failed:
            # Array API was ATTEMPTED but scipy's env-var gate blocked
            # it; we fell back to CPU numpy. Report the failure shape
            # so operators can grep for the deployment gap.
            device_report = DeviceReport(
                family=self.family_name,
                backend="cpu",
                device_string="cpu",
                precision="32-true",
                fallback_reason="array_api_runtime_unavailable",
                array_api=False,
            )
        else:
            device_report = DeviceReport(
                family=self.family_name,
                backend="cpu",
                device_string="cpu",
                precision="32-true",
                fallback_reason=("array_api_offlist" if non_cpu_requested else None),
                array_api=False,
            )

        self._last_device_report = device_report

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
            device=device_report,
            trainable=self,
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
        return Predictions(preds, column="prediction", device=self._last_device_report)


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

    @property
    def model(self) -> Any:
        """Fitted model handle per W33c / `ml-registry.md` §5.6.1.

        For Torch the model IS the raw ``torch.nn.Module`` supplied at
        construction and mutated in-place by the Lightning trainer.
        """
        return self._model

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

        # Per revised-stack.md § "Transparency contract": every fit
        # returns a DeviceReport. Torch is the DL spine — backend
        # reflects the actually-resolved Lightning accelerator (no
        # eviction / OOM fallback path here; native multi-backend
        # support via L.Trainer per ml-backends.md §5.4).
        device_report = DeviceReport(
            family=self.family_name,
            backend=ctx.backend,
            device_string=ctx.device_string,
            precision=ctx.precision,
            fallback_reason=None,
            array_api=False,
        )
        self._last_device_report = device_report

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
            device=device_report,
            trainable=self,
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
        return Predictions(
            preds.detach().cpu().numpy(),
            column="prediction",
            device=self._last_device_report,
        )


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
        # Empty tuple default so downstream predict() code paths that
        # read self._feature_names before fit() has been called get a
        # consistent shape rather than AttributeError. Populated during
        # fit() from _split_xy(data, target).
        self._feature_names: tuple[str, ...] = ()

    @property
    def model(self) -> Any:
        """Fitted model handle per W33c / `ml-registry.md` §5.6.1.

        For Lightning the model IS the wrapped LightningModule supplied
        at construction.
        """
        return self._module

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

        # Per revised-stack.md § "Transparency contract": every fit
        # returns a DeviceReport. Lightning is the DL spine — backend
        # reflects the actually-resolved Lightning accelerator (no
        # eviction / OOM fallback path here; native multi-backend
        # support via L.Trainer per ml-backends.md §5.5).
        device_report = DeviceReport(
            family=self.family_name,
            backend=ctx.backend,
            device_string=ctx.device_string,
            precision=ctx.precision,
            fallback_reason=None,
            array_api=False,
        )
        self._last_device_report = device_report

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
            device=device_report,
            trainable=self,
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
        return Predictions(
            preds.detach().cpu().numpy(),
            column="prediction",
            device=self._last_device_report,
        )


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

    @property
    def model(self) -> Any:
        """Fitted model handle per W33c / `ml-registry.md` §5.6.1.

        For XGBoost the model IS the sklearn-compatible estimator.
        """
        return self._estimator

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

        # OOM fallback: GPU OOM on the xgboost path MUST degrade to CPU
        # with a WARN log (revised-stack.md § "No-config contract" — xgboost
        # row). Non-OOM exceptions re-raise unchanged per zero-tolerance.md
        # Rule 3 (no silent swallow).
        fallback_reason: Optional[str] = None
        effective_ctx = ctx
        effective_trainer_kwargs = trainer_kwargs
        t0 = time.monotonic()
        try:
            trainer.fit(module)
        except Exception as exc:
            if ctx.backend == "cpu" or not _is_gpu_oom_error(exc):
                raise
            logger.warning(
                "xgboost.gpu.oom_fallback",
                extra={
                    "family": self.family_name,
                    "requested_backend": ctx.backend,
                    "fallback_backend": "cpu",
                    "fallback_reason": "oom",
                    "error_class": type(exc).__name__,
                },
            )
            fallback_reason = "oom"
            # Re-point the xgboost estimator at CPU before the retry so
            # the inner fit inside `on_train_start` actually runs on CPU.
            if hasattr(self._estimator, "set_params"):
                try:
                    self._estimator.set_params(device="cpu")
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "xgboost.device.set_failed",
                        extra={
                            "xgb_device": "cpu",
                            "family": self.family_name,
                        },
                    )
            # Rebuild module + Trainer for the retry — L.Trainer is
            # single-shot, and the first module already exhausted state
            # when trainer.fit raised.
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
            cpu_module = _make_single_epoch_module(
                self._estimator,
                X,
                y,
                metric_name=metric_name,
                metric_fn=metric_fn,
                module_name="XGBoostLightningAdapter",
            )
            cpu_trainer_kwargs = _log_backend_selection(cpu_ctx, max_epochs=1)
            cpu_trainer = pl_trainer.Trainer(**cpu_trainer_kwargs)
            cpu_trainer.fit(cpu_module)
            module = cpu_module
            effective_ctx = cpu_ctx
            effective_trainer_kwargs = cpu_trainer_kwargs
        elapsed = time.monotonic() - t0

        self._is_fitted = True
        self._last_module = module

        artifact_uri = _persist_native_artifact(
            self._estimator, prefix="xgboost", format="pickle"
        )

        device_report = DeviceReport(
            family=self.family_name,
            backend=effective_ctx.backend,
            device_string=effective_ctx.device_string,
            precision=effective_ctx.precision,
            fallback_reason=fallback_reason,
            array_api=False,
        )
        self._last_device_report = device_report

        return TrainingResult(
            model_uri=f"models://{self.family_name}/{uuid.uuid4().hex[:8]}",
            metrics={metric_name: module.metric},
            device_used=effective_ctx.device_string,
            accelerator=effective_ctx.accelerator,
            precision=effective_ctx.precision,
            elapsed_seconds=elapsed,
            tracker_run_id=effective_ctx.tracker_run_id,
            tenant_id=effective_ctx.tenant_id,
            artifact_uris={"native": artifact_uri},
            lightning_trainer_config=effective_trainer_kwargs,
            family=self.family_name,
            hyperparameters=dict(hyperparameters or {}),
            device=device_report,
            trainable=self,
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
        return Predictions(preds, column="prediction", device=self._last_device_report)


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

    @property
    def model(self) -> Any:
        """Fitted model handle per W33c / `ml-registry.md` §5.6.1.

        For LightGBM the model IS the sklearn-compatible estimator.
        """
        return self._estimator

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

        # OOM fallback: lightgbm GPU OOM MUST degrade to CPU with a
        # WARN log (revised-stack.md § "No-config contract" — lightgbm
        # row). ctx.backend in {"cuda", "rocm"} is the GPU path; "cpu"
        # is already at the fallback target and re-raises unchanged
        # per zero-tolerance.md Rule 3.
        fallback_reason: Optional[str] = None
        effective_ctx = ctx
        effective_trainer_kwargs = trainer_kwargs
        t0 = time.monotonic()
        try:
            trainer.fit(module)
        except Exception as exc:
            if ctx.backend == "cpu" or not _is_gpu_oom_error(exc):
                raise
            logger.warning(
                "lightgbm.gpu.oom_fallback",
                extra={
                    "family": self.family_name,
                    "requested_backend": ctx.backend,
                    "fallback_backend": "cpu",
                    "fallback_reason": "oom",
                    "error_class": type(exc).__name__,
                },
            )
            fallback_reason = "oom"
            # lightgbm uses `device_type="cpu"` (not `device=`). Re-point
            # the estimator before the retry; debug-log any set_params
            # failure (old lightgbm builds).
            if hasattr(self._estimator, "set_params"):
                try:
                    self._estimator.set_params(device_type="cpu")
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "lightgbm.device.set_failed",
                        extra={
                            "lgb_device": "cpu",
                            "family": self.family_name,
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
            cpu_module = _make_single_epoch_module(
                self._estimator,
                X,
                y,
                metric_name=metric_name,
                metric_fn=metric_fn,
                module_name="LightGBMLightningAdapter",
            )
            cpu_trainer_kwargs = _log_backend_selection(cpu_ctx, max_epochs=1)
            cpu_trainer = pl_trainer.Trainer(**cpu_trainer_kwargs)
            cpu_trainer.fit(cpu_module)
            module = cpu_module
            effective_ctx = cpu_ctx
            effective_trainer_kwargs = cpu_trainer_kwargs
        elapsed = time.monotonic() - t0

        self._is_fitted = True
        self._last_module = module

        artifact_uri = _persist_native_artifact(
            self._estimator, prefix="lightgbm", format="pickle"
        )

        device_report = DeviceReport(
            family=self.family_name,
            backend=effective_ctx.backend,
            device_string=effective_ctx.device_string,
            precision=effective_ctx.precision,
            fallback_reason=fallback_reason,
            array_api=False,
        )
        self._last_device_report = device_report

        return TrainingResult(
            model_uri=f"models://{self.family_name}/{uuid.uuid4().hex[:8]}",
            metrics={metric_name: module.metric},
            device_used=effective_ctx.device_string,
            accelerator=effective_ctx.accelerator,
            precision=effective_ctx.precision,
            elapsed_seconds=elapsed,
            tracker_run_id=effective_ctx.tracker_run_id,
            tenant_id=effective_ctx.tenant_id,
            artifact_uris={"native": artifact_uri},
            lightning_trainer_config=effective_trainer_kwargs,
            family=self.family_name,
            hyperparameters=dict(hyperparameters or {}),
            device=device_report,
            trainable=self,
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
        return Predictions(preds, column="prediction", device=self._last_device_report)


# ---------------------------------------------------------------------------
# CatBoostTrainable (W6-013 / F-E1-01 — Phase 1 family adapter)
# ---------------------------------------------------------------------------


class CatBoostTrainable:
    """Wraps catboost's sklearn-style estimator as a Trainable.

    Per ``specs/ml-engines-v2.md §3`` + ``ml-engines-v2-addendum.md``
    Classical-ML surface, CatBoost is one of the four non-Torch
    Phase-1 families (sklearn / xgboost / lightgbm / catboost). The
    ``[catboost]`` extra ships in ``pyproject.toml``; importing this
    adapter without the extra raises :class:`ImportError` with an
    actionable message naming the extra (per
    ``rules/dependencies.md`` § "Optional Extras with Loud Failure").

    Device mapping per ``ml-backends.md`` §5 + CatBoost docs:

    - backend == "cuda" → ``task_type="GPU"`` + ``devices="0"``
    - backend == "cpu"  → ``task_type="CPU"``
    - backend in {"mps", "rocm", "xpu", "tpu"} → ``UnsupportedFamily``

    CatBoost's iterative boosting fit runs in
    ``on_train_start`` of the LightningModule wrapper, mirroring the
    XGBoost/LightGBM pattern (Lightning Hard Lock-In, Decision 8).
    """

    family_name = "catboost"
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
            try:
                import catboost as _cb
            except ImportError as exc:  # pragma: no cover — exercised w/o extra
                raise ImportError(
                    "CatBoostTrainable requires the [catboost] extra: "
                    "pip install kailash-ml[catboost]"
                ) from exc

            if task == "classification":
                defaults = {
                    "iterations": 20,
                    "depth": 3,
                    "random_seed": 42,
                    "verbose": False,
                }
                defaults.update(kwargs)
                estimator = _cb.CatBoostClassifier(**defaults)
            else:
                defaults = {
                    "iterations": 20,
                    "depth": 3,
                    "random_seed": 42,
                    "verbose": False,
                }
                defaults.update(kwargs)
                estimator = _cb.CatBoostRegressor(**defaults)
        self._estimator = estimator
        self._target = target
        self._task = task
        self._is_fitted = False
        self._last_module: Any = None
        self._last_device_report: Optional[DeviceReport] = None
        self._feature_names: tuple[str, ...] = ()

    @property
    def model(self) -> Any:
        """Fitted model handle per W33c / `ml-registry.md` §5.6.1.

        For CatBoost the model IS the sklearn-compatible estimator.
        """
        return self._estimator

    def to_lightning_module(self) -> Any:
        if self._last_module is None:
            raise RuntimeError(
                "CatBoostTrainable.to_lightning_module() called before fit(). "
                "Call fit(data) first."
            )
        return self._last_module

    def get_param_distribution(self) -> HyperparameterSpace:
        return HyperparameterSpace(
            params=(
                HyperparameterRange(name="iterations", kind="int", low=10, high=500),
                HyperparameterRange(name="depth", kind="int", low=2, high=10),
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

        # Device mapping per ml-backends.md §5 — enforce supported
        # backend BEFORE any training call. Raises UnsupportedFamily on
        # MPS / ROCm / XPU / TPU with an actionable message.
        if ctx.backend not in self._SUPPORTED_BACKENDS:
            raise UnsupportedFamily(
                f"catboost cannot run on backend '{ctx.backend}'. "
                f"catboost supports only {list(self._SUPPORTED_BACKENDS)}. "
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
                    try:
                        self._estimator.set_params(**{k: v})
                    except Exception:  # noqa: BLE001 — fall back to attribute set
                        setattr(self._estimator, k, v)

        # Set CatBoost task_type per §5 (CatBoost idiom). The set_params
        # call may fail on builds without GPU support — surface as
        # UnsupportedFamily on the GPU path; tolerate on the CPU path
        # (the default task_type is already CPU).
        cb_task_type = "GPU" if ctx.backend == "cuda" else "CPU"
        if cb_task_type == "GPU":
            try:
                self._estimator.set_params(task_type="GPU", devices="0")
            except Exception as exc:  # noqa: BLE001
                raise UnsupportedFamily(
                    f"catboost GPU support not present in the installed build "
                    f"(requested backend='{ctx.backend}'). "
                    f"Install a GPU-capable build of catboost, or use "
                    f"accelerator='cpu'.",
                    family=self.family_name,
                    backend=ctx.backend,
                    supported_backends_for_family=("cpu",),
                ) from exc
        else:
            try:
                self._estimator.set_params(task_type="CPU")
            except Exception:  # noqa: BLE001
                logger.debug(
                    "catboost.device.set_failed",
                    extra={"cb_task_type": "CPU", "family": self.family_name},
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
            module_name="CatBoostLightningAdapter",
        )

        trainer_kwargs = _log_backend_selection(ctx, max_epochs=1)
        trainer = pl_trainer.Trainer(**trainer_kwargs)

        # OOM fallback: GPU OOM on the catboost path MUST degrade to CPU
        # with a WARN log mirroring xgboost / lightgbm (revised-stack.md
        # § "No-config contract"). Non-OOM exceptions re-raise unchanged
        # per zero-tolerance.md Rule 3 (no silent swallow).
        fallback_reason: Optional[str] = None
        effective_ctx = ctx
        effective_trainer_kwargs = trainer_kwargs
        t0 = time.monotonic()
        try:
            trainer.fit(module)
        except Exception as exc:
            if ctx.backend == "cpu" or not _is_gpu_oom_error(exc):
                raise
            logger.warning(
                "catboost.gpu.oom_fallback",
                extra={
                    "family": self.family_name,
                    "requested_backend": ctx.backend,
                    "fallback_backend": "cpu",
                    "fallback_reason": "oom",
                    "error_class": type(exc).__name__,
                },
            )
            fallback_reason = "oom"
            # Re-point catboost at CPU before the retry so the inner fit
            # inside on_train_start actually runs on CPU.
            try:
                self._estimator.set_params(task_type="CPU")
            except Exception:  # noqa: BLE001
                logger.debug(
                    "catboost.device.set_failed",
                    extra={
                        "cb_task_type": "CPU",
                        "family": self.family_name,
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
            cpu_module = _make_single_epoch_module(
                self._estimator,
                X,
                y,
                metric_name=metric_name,
                metric_fn=metric_fn,
                module_name="CatBoostLightningAdapter",
            )
            cpu_trainer_kwargs = _log_backend_selection(cpu_ctx, max_epochs=1)
            cpu_trainer = pl_trainer.Trainer(**cpu_trainer_kwargs)
            cpu_trainer.fit(cpu_module)
            module = cpu_module
            effective_ctx = cpu_ctx
            effective_trainer_kwargs = cpu_trainer_kwargs
        elapsed = time.monotonic() - t0

        self._is_fitted = True
        self._last_module = module

        artifact_uri = _persist_native_artifact(
            self._estimator, prefix="catboost", format="pickle"
        )

        device_report = DeviceReport(
            family=self.family_name,
            backend=effective_ctx.backend,
            device_string=effective_ctx.device_string,
            precision=effective_ctx.precision,
            fallback_reason=fallback_reason,
            array_api=False,
        )
        self._last_device_report = device_report

        return TrainingResult(
            model_uri=f"models://{self.family_name}/{uuid.uuid4().hex[:8]}",
            metrics={metric_name: module.metric},
            device_used=effective_ctx.device_string,
            accelerator=effective_ctx.accelerator,
            precision=effective_ctx.precision,
            elapsed_seconds=elapsed,
            tracker_run_id=effective_ctx.tracker_run_id,
            tenant_id=effective_ctx.tenant_id,
            artifact_uris={"native": artifact_uri},
            lightning_trainer_config=effective_trainer_kwargs,
            family=self.family_name,
            hyperparameters=dict(hyperparameters or {}),
            device=device_report,
            trainable=self,
        )

    def predict(self, X: pl.DataFrame) -> Predictions:
        if not self._is_fitted:
            raise RuntimeError("CatBoostTrainable.predict() called before fit().")
        frame = (
            X.select([c for c in self._feature_names if c in X.columns])
            if self._feature_names
            else X
        )
        preds = self._estimator.predict(frame.to_numpy())
        return Predictions(preds, column="prediction", device=self._last_device_report)


# ---------------------------------------------------------------------------
# UMAPTrainable (Phase 1 — CPU only via umap-learn; cuML evicted per
# workspaces/kailash-ml-gpu-stack/04-validate/02-revised-stack.md CRITICAL-1)
# ---------------------------------------------------------------------------


class UMAPTrainable:
    """Wraps ``umap-learn``'s UMAP as a Trainable.

    Phase 1 ships CPU-only via the ``umap-learn`` pip package. cuML is
    evicted per the Phase 1 revised-stack decision (NVIDIA-only, fragile
    wheels, blocks every other GPU backend). Users on NVIDIA accept the
    slower path; users on every other backend gain a working path. Phase
    2 adds torch-native UMAP across MPS/ROCm/XPU.

    When ``TrainingContext.backend != "cpu"``, the adapter logs
    ``umap.cuml_eviction`` at INFO (documented design, not degraded —
    per ``rules/observability.md`` §3 INFO is the correct level) and
    runs on CPU. The emitted ``DeviceReport.fallback_reason`` is
    ``"cuml_eviction"`` so callers can distinguish this from an OOM or
    driver-missing fallback.

    UMAP is unsupervised: ``target`` is optional; when given, it is
    split off so downstream pipelines can chain a supervised stage.
    """

    family_name = "umap"
    _SUPPORTED_BACKENDS = ("cpu",)  # Phase 1 — CPU only

    def __init__(
        self,
        *,
        target: Optional[str] = None,
        n_components: int = 2,
        n_neighbors: int = 15,
        random_state: int = 42,
        **kwargs: Any,
    ) -> None:
        self._init_kwargs: dict[str, Any] = {
            "n_components": n_components,
            "n_neighbors": n_neighbors,
            "random_state": random_state,
            # umap-learn warns that `random_state` forces `n_jobs=1`; pre-set
            # the value so umap's "overridden to 1" UserWarning does not
            # fire. See umap_.py:1952 (umap-learn 0.5+).
            "n_jobs": kwargs.pop("n_jobs", 1),
            **kwargs,
        }
        self._target = target
        self._reducer: Any = None
        self._is_fitted = False
        self._last_module: Any = None
        self._feature_names: tuple[str, ...] = ()

    @property
    def model(self) -> Any:
        """Fitted model handle per W33c / `ml-registry.md` §5.6.1.

        For UMAP the model IS the fitted reducer (a ``umap.UMAP``
        instance after fit).
        """
        return self._reducer

    def to_lightning_module(self) -> Any:
        if self._last_module is None:
            raise RuntimeError(
                "UMAPTrainable.to_lightning_module() called before fit(). "
                "Call fit(data) first."
            )
        return self._last_module

    def get_param_distribution(self) -> HyperparameterSpace:
        return HyperparameterSpace(
            params=(
                HyperparameterRange(name="n_components", kind="int", low=2, high=50),
                HyperparameterRange(name="n_neighbors", kind="int", low=2, high=200),
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

        try:
            import umap  # umap-learn package
        except ImportError as exc:  # pragma: no cover - declared base dep
            raise ImportError(
                "UMAPTrainable requires the 'umap-learn' package. "
                "It is a base dependency of kailash-ml; reinstall via "
                "'uv sync' or 'pip install kailash-ml'."
            ) from exc

        ctx = _effective_context(context)

        # Phase 1: always CPU (cuML evicted). INFO per observability.md §3.
        fallback_reason: Optional[str] = None
        if ctx.backend != "cpu":
            logger.info(
                "umap.cuml_eviction",
                extra={
                    "family": self.family_name,
                    "requested_backend": ctx.backend,
                    "actual_backend": "cpu",
                    "fallback_reason": "cuml_eviction",
                },
            )
            fallback_reason = "cuml_eviction"

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

        params = dict(self._init_kwargs)
        if hyperparameters:
            params.update(hyperparameters)
        self._reducer = umap.UMAP(**params)

        # UMAP is unsupervised — split off target if given, but do not require it.
        if self._target is not None and self._target in data.columns:
            X, _y, feature_names = _split_xy(data, self._target)
            self._feature_names = feature_names
        else:
            X = data.to_numpy()
            self._feature_names = tuple(data.columns)

        X_arr = np.asarray(X)

        # Build a single-epoch LightningModule that fits UMAP in
        # on_train_start. Same pattern as XGBoost/LightGBM adapters;
        # _make_single_epoch_module assumes supervised (y+metric), so we
        # inline a minimal unsupervised adapter here.
        import torch

        reducer = self._reducer

        class _UMAPLightningAdapter(pl_trainer.LightningModule):
            def __init__(self) -> None:
                super().__init__()
                self._reducer = reducer
                self._X = X_arr
                self._fitted = False
                self._bias = torch.nn.Parameter(torch.zeros(1, requires_grad=True))

            def on_train_start(self) -> None:
                self._reducer.fit(self._X)
                self._fitted = True

            def training_step(self, batch: Any, batch_idx: int) -> Any:
                return self._bias.sum() * 0.0

            def configure_optimizers(self) -> Any:
                return torch.optim.SGD([self._bias], lr=1e-3)

            def train_dataloader(self) -> Any:
                ds = torch.utils.data.TensorDataset(
                    torch.zeros(1, 1),
                    torch.zeros(1, dtype=torch.long),
                )
                return torch.utils.data.DataLoader(ds, batch_size=1)

        module = _UMAPLightningAdapter()

        trainer_kwargs = _log_backend_selection(cpu_ctx, max_epochs=1)
        trainer = pl_trainer.Trainer(**trainer_kwargs)
        t0 = time.monotonic()
        trainer.fit(module)
        elapsed = time.monotonic() - t0

        self._is_fitted = True
        self._last_module = module

        artifact_uri = _persist_native_artifact(
            self._reducer, prefix="umap", format="pickle"
        )

        device_report = DeviceReport(
            family=self.family_name,
            backend="cpu",
            device_string="cpu",
            precision="32-true",
            fallback_reason=fallback_reason,
            array_api=False,
        )
        self._last_device_report = device_report

        return TrainingResult(
            model_uri=f"models://{self.family_name}/{uuid.uuid4().hex[:8]}",
            # UMAP is unsupervised; no supervised metric to report. We
            # emit a placeholder 0.0 so the TrainingResult contract is
            # satisfied. Downstream metrics (trustworthiness, silhouette
            # against a target) belong to the engine, not the adapter.
            metrics={"umap_embedding_components": float(params["n_components"])},
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
            device=device_report,
            trainable=self,
        )

    def predict(self, X: pl.DataFrame) -> Predictions:
        if not self._is_fitted:
            raise RuntimeError("UMAPTrainable.predict() called before fit().")
        # If target was used at fit time, drop it from X if present.
        if self._target is not None and self._target in X.columns:
            frame = X.drop(self._target)
        else:
            frame = X
        embedding = self._reducer.transform(frame.to_numpy())
        return Predictions(
            embedding, column="embedding", device=self._last_device_report
        )


# ---------------------------------------------------------------------------
# HDBSCANTrainable (Phase 1 — CPU only via sklearn.cluster.HDBSCAN;
# cuML evicted per revised-stack.md CRITICAL-1)
# ---------------------------------------------------------------------------


class HDBSCANTrainable:
    """Wraps ``sklearn.cluster.HDBSCAN`` as a Trainable.

    Phase 1 ships CPU-only via sklearn 1.3+'s HDBSCAN (already in our
    ``scikit-learn>=1.5`` base dep). cuML is evicted per the revised
    stack decision. Phase 2 adds torch-native HDBSCAN across non-NVIDIA
    backends.

    Clustering note: HDBSCAN is transductive — ``.fit(X)`` exposes
    ``labels_`` for the training data, but it has no canonical
    ``.predict()`` for new points. ``HDBSCANTrainable.predict(X)``
    re-runs ``.fit_predict(X)`` on ``X``, which clusters the new frame
    independently. For approximate prediction on new points, fit with
    ``prediction_data=True`` and use ``hdbscan.approximate_predict``
    (not wrapped here — belongs in a downstream clustering engine).
    """

    family_name = "hdbscan"
    _SUPPORTED_BACKENDS = ("cpu",)  # Phase 1 — CPU only

    def __init__(
        self,
        *,
        target: Optional[str] = None,
        min_cluster_size: int = 5,
        min_samples: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        self._init_kwargs: dict[str, Any] = {
            "min_cluster_size": min_cluster_size,
            # sklearn 1.5+ emits a FutureWarning that `copy` defaults are
            # changing (False → True in sklearn 1.10). Pre-set the 1.10
            # default so the upgrade is a no-op.
            "copy": kwargs.pop("copy", True),
            **kwargs,
        }
        if min_samples is not None:
            self._init_kwargs["min_samples"] = min_samples
        self._target = target
        self._clusterer: Any = None
        self._is_fitted = False
        self._last_module: Any = None
        self._feature_names: tuple[str, ...] = ()

    @property
    def model(self) -> Any:
        """Fitted model handle per W33c / `ml-registry.md` §5.6.1.

        For HDBSCAN the model IS the fitted clusterer.
        """
        return self._clusterer

    def to_lightning_module(self) -> Any:
        if self._last_module is None:
            raise RuntimeError(
                "HDBSCANTrainable.to_lightning_module() called before fit(). "
                "Call fit(data) first."
            )
        return self._last_module

    def get_param_distribution(self) -> HyperparameterSpace:
        return HyperparameterSpace(
            params=(
                HyperparameterRange(
                    name="min_cluster_size", kind="int", low=2, high=100
                ),
                HyperparameterRange(name="min_samples", kind="int", low=1, high=50),
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
        from sklearn.cluster import HDBSCAN

        ctx = _effective_context(context)

        fallback_reason: Optional[str] = None
        if ctx.backend != "cpu":
            logger.info(
                "hdbscan.cuml_eviction",
                extra={
                    "family": self.family_name,
                    "requested_backend": ctx.backend,
                    "actual_backend": "cpu",
                    "fallback_reason": "cuml_eviction",
                },
            )
            fallback_reason = "cuml_eviction"

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

        params = dict(self._init_kwargs)
        if hyperparameters:
            params.update(hyperparameters)
        self._clusterer = HDBSCAN(**params)

        # HDBSCAN is unsupervised — split off target if given.
        if self._target is not None and self._target in data.columns:
            X, _y, feature_names = _split_xy(data, self._target)
            self._feature_names = feature_names
        else:
            X = data.to_numpy()
            self._feature_names = tuple(data.columns)

        X_arr = np.asarray(X)

        import torch

        clusterer = self._clusterer

        class _HDBSCANLightningAdapter(pl_trainer.LightningModule):
            def __init__(self) -> None:
                super().__init__()
                self._clusterer = clusterer
                self._X = X_arr
                self._fitted = False
                self._n_clusters = 0
                self._n_noise = 0
                self._bias = torch.nn.Parameter(torch.zeros(1, requires_grad=True))

            def on_train_start(self) -> None:
                self._clusterer.fit(self._X)
                self._fitted = True
                labels = self._clusterer.labels_
                # -1 is the HDBSCAN noise label; positive labels are clusters.
                unique = set(int(x) for x in labels)
                self._n_noise = int((labels == -1).sum())
                self._n_clusters = len(unique - {-1})

            def training_step(self, batch: Any, batch_idx: int) -> Any:
                return self._bias.sum() * 0.0

            def configure_optimizers(self) -> Any:
                return torch.optim.SGD([self._bias], lr=1e-3)

            def train_dataloader(self) -> Any:
                ds = torch.utils.data.TensorDataset(
                    torch.zeros(1, 1),
                    torch.zeros(1, dtype=torch.long),
                )
                return torch.utils.data.DataLoader(ds, batch_size=1)

            @property
            def cluster_count(self) -> int:
                return self._n_clusters

            @property
            def noise_count(self) -> int:
                return self._n_noise

        module = _HDBSCANLightningAdapter()

        trainer_kwargs = _log_backend_selection(cpu_ctx, max_epochs=1)
        trainer = pl_trainer.Trainer(**trainer_kwargs)
        t0 = time.monotonic()
        trainer.fit(module)
        elapsed = time.monotonic() - t0

        self._is_fitted = True
        self._last_module = module

        artifact_uri = _persist_native_artifact(
            self._clusterer, prefix="hdbscan", format="pickle"
        )

        device_report = DeviceReport(
            family=self.family_name,
            backend="cpu",
            device_string="cpu",
            precision="32-true",
            fallback_reason=fallback_reason,
            array_api=False,
        )
        self._last_device_report = device_report

        return TrainingResult(
            model_uri=f"models://{self.family_name}/{uuid.uuid4().hex[:8]}",
            metrics={
                "hdbscan_n_clusters": float(module.cluster_count),
                "hdbscan_n_noise": float(module.noise_count),
            },
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
            device=device_report,
            trainable=self,
        )

    def predict(self, X: pl.DataFrame) -> Predictions:
        if not self._is_fitted:
            raise RuntimeError("HDBSCANTrainable.predict() called before fit().")
        # HDBSCAN is transductive. For new data, re-cluster via fit_predict.
        # See class docstring: for approximate_predict-style behavior on
        # new points, instantiate sklearn.cluster.HDBSCAN upstream with
        # appropriate settings — that path belongs in a clustering engine.
        from sklearn.cluster import HDBSCAN

        if self._target is not None and self._target in X.columns:
            frame = X.drop(self._target)
        else:
            frame = X
        new_clusterer = HDBSCAN(**self._init_kwargs)
        labels = new_clusterer.fit_predict(frame.to_numpy())
        return Predictions(
            labels, column="cluster_label", device=self._last_device_report
        )


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

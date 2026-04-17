# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Trainable protocol and family adapter scaffolding (kailash-ml 2.0 Phase 2).

Every model family that `MLEngine.fit()` supports MUST implement the
`Trainable` protocol. This module defines the protocol, the companion
`Predictions` / `HyperparameterSpace` / `TrainingContext` types, and
skeleton adapter classes for sklearn / xgboost / lightgbm / torch /
lightning.

The adapters are scaffolds: they construct correctly and expose the
protocol shape, but their `fit`, `predict`, and `to_lightning_module`
methods raise `NotImplementedError` naming Phase 3. This is NOT a stub
per `rules/zero-tolerance.md` Rule 2 — the pattern is:

    (a) visibly unfinished (the error message names Phase 3),
    (b) tested (unit tests assert the NotImplementedError fires with
        the phase pointer), and
    (c) scheduled for replacement in a named later phase.

When Phase 3 lands, the scaffolds turn into real implementations; the
tests that assert `NotImplementedError` will fail and force the cleanup.

See `specs/ml-engines.md` §3 for the protocol contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, Sequence, Union, runtime_checkable

try:
    import polars as pl
except ImportError:  # pragma: no cover — polars is a base dep
    pl = None  # type: ignore[assignment]

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


_PHASE_3_MESSAGE = (
    "Phase 3 will implement this adapter. The Trainable scaffold exists so "
    "that Engine construction, protocol conformance, and test coverage can "
    "land in Phase 2; the concrete fit/predict/to_lightning_module bodies "
    "land in Phase 3 once the Lightning adapter layer is in place."
)


# ---------------------------------------------------------------------------
# Support types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HyperparameterRange:
    """One hyperparameter's search range.

    `kind` is one of "int", "float", "log_float", "categorical", "bool".
    For categorical/bool, `choices` carries the options and `low`/`high`
    are unused. For numeric kinds, `low`/`high` bound the search space.
    """

    name: str
    kind: str
    low: Optional[float] = None
    high: Optional[float] = None
    choices: Optional[tuple[Any, ...]] = None
    log: bool = False


@dataclass(frozen=True)
class HyperparameterSpace:
    """Search space for a Trainable's hyperparameters.

    Every Trainable MUST return a valid `HyperparameterSpace` from
    `get_param_distribution()` — empty is acceptable, `None` is not
    (ml-engines.md §3.2 MUST 3).
    """

    params: Sequence[HyperparameterRange] = field(default_factory=tuple)

    def is_empty(self) -> bool:
        return len(self.params) == 0

    def names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.params)


@dataclass(frozen=True)
class TrainingContext:
    """Context injected by the Engine into each `Trainable.fit()` call.

    Carries the Engine's resolved accelerator / precision / tenant /
    tracker binding — Trainables MUST NOT re-resolve these themselves
    (ml-engines.md §3.2 MUST 4).
    """

    accelerator: str  # "cuda", "mps", "rocm", "xpu", "tpu", "cpu"
    precision: str  # Concrete Lightning precision string (never "auto")
    devices: Any = 1  # Lightning devices= value
    device_string: str = "cpu"
    tenant_id: Optional[str] = None
    tracker_run_id: Optional[str] = None
    trial_number: Optional[int] = None


# `Predictions` is a thin typed envelope around the adapter's native
# prediction output. Phase 3 will widen this once the concrete
# conversion paths land; for now it wraps an arbitrary ndarray-or-frame
# value and exposes `to_list()` / `to_polars()` helpers.


class Predictions:
    """Typed envelope around a model's prediction output.

    Phase 2 stores the raw value and delegates conversion to the caller.
    Phase 3 will introduce concrete conversion paths (numpy → polars,
    polars → numpy) through the sole interop point.
    """

    __slots__ = ("_raw", "_column")

    def __init__(self, raw: Any, *, column: str = "prediction") -> None:
        self._raw = raw
        self._column = column

    @property
    def raw(self) -> Any:
        """Return the underlying prediction object unchanged."""
        return self._raw

    @property
    def column(self) -> str:
        return self._column

    def to_polars(self) -> "pl.DataFrame":  # type: ignore[name-defined]
        """Return the predictions as a polars DataFrame.

        The Phase 2 implementation accepts either a polars DataFrame
        (returned directly) or a 1-D sequence (wrapped into a single
        column). Numpy arrays and other shapes are deferred to Phase 3
        where the interop.py boundary handles them; calling to_polars()
        on an unsupported shape raises NotImplementedError with a phase
        pointer.
        """
        if pl is None:  # pragma: no cover — polars is a base dep
            raise ImportError(
                "polars is required for Predictions.to_polars(); install "
                "via `pip install kailash-ml`."
            )
        if isinstance(self._raw, pl.DataFrame):
            return self._raw
        if isinstance(self._raw, pl.Series):
            return self._raw.to_frame(self._column)
        if isinstance(self._raw, (list, tuple)):
            return pl.DataFrame({self._column: list(self._raw)})
        raise NotImplementedError(
            "Predictions.to_polars() for non-polars, non-sequence inputs. "
            + _PHASE_3_MESSAGE
        )

    def __repr__(self) -> str:
        return f"Predictions(column={self._column!r}, raw={type(self._raw).__name__})"


# ---------------------------------------------------------------------------
# Protocol (ml-engines.md §3.1)
# ---------------------------------------------------------------------------


@runtime_checkable
class Trainable(Protocol):
    """Protocol every model family MUST implement for MLEngine.fit().

    The runtime-checkable protocol means `isinstance(obj, Trainable)`
    succeeds on any object exposing the required surface — whether or
    not it inherits from a declared base class. This matches the Python
    `typing.Protocol` contract.

    See `specs/ml-engines.md` §3 for the full contract.
    """

    family_name: str

    def fit(
        self,
        data: "pl.DataFrame",  # type: ignore[name-defined]
        *,
        hyperparameters: Mapping[str, Any],
        context: TrainingContext,
    ) -> "TrainingResult":  # type: ignore[name-defined]  # forward ref
        ...

    def predict(self, X: "pl.DataFrame") -> Predictions:  # type: ignore[name-defined]
        ...

    def to_lightning_module(self) -> Any:
        """Return a `lightning.pytorch.LightningModule`.

        Typed as `Any` so callers don't have to import Lightning to
        satisfy the protocol statically; implementations MUST return a
        real `LightningModule` at runtime.
        """
        ...

    def get_param_distribution(self) -> HyperparameterSpace: ...


# ---------------------------------------------------------------------------
# Skeleton adapters
#
# Each adapter's __init__ MUST succeed; methods that depend on the Phase
# 3 Lightning adapter layer raise NotImplementedError with the phase
# pointer. Tests in test_trainable_protocol.py assert this behaviour.
# ---------------------------------------------------------------------------


class _TrainableAdapterBase:
    """Shared scaffold for Phase 2 adapter skeletons.

    Subclasses set `family_name` and may override `__init__` to capture
    their model class/config. `fit`, `predict`, and `to_lightning_module`
    default to raising `NotImplementedError` with a phase pointer.
    """

    family_name: str = "base"

    def __init__(self, model_class: Any = None, **kwargs: Any) -> None:
        self.model_class = model_class
        self.kwargs = dict(kwargs)

    def fit(
        self,
        data: "pl.DataFrame",  # type: ignore[name-defined]
        *,
        hyperparameters: Mapping[str, Any],
        context: TrainingContext,
    ) -> "TrainingResult":  # type: ignore[name-defined]
        raise NotImplementedError(f"{type(self).__name__}.fit — {_PHASE_3_MESSAGE}")

    def predict(self, X: "pl.DataFrame") -> Predictions:  # type: ignore[name-defined]
        raise NotImplementedError(f"{type(self).__name__}.predict — {_PHASE_3_MESSAGE}")

    def to_lightning_module(self) -> Any:
        raise NotImplementedError(
            f"{type(self).__name__}.to_lightning_module — {_PHASE_3_MESSAGE}"
        )

    def get_param_distribution(self) -> HyperparameterSpace:
        # Per ml-engines.md §3.2 MUST 3: empty HyperparameterSpace is
        # acceptable; None is not. Phase 3 may widen this per-family.
        return HyperparameterSpace(params=())


class SklearnTrainable(_TrainableAdapterBase):
    """Wraps an sklearn estimator as a Trainable.

    Phase 3 will supply the `SklearnLightningAdapter` LightningModule
    that routes sklearn's CPU-only fit through `L.Trainer` for metric
    and callback unification (ml-engines.md §3.2 MUST 1).
    """

    family_name = "sklearn"


class XGBoostTrainable(_TrainableAdapterBase):
    """Wraps an xgboost estimator as a Trainable.

    Phase 3 will supply the LightningModule adapter and the
    `device="cuda" | "cpu"` mapping per ml-backends.md §5.2.
    """

    family_name = "xgboost"


class LightGBMTrainable(_TrainableAdapterBase):
    """Wraps a lightgbm estimator as a Trainable.

    Phase 3 will supply the LightningModule adapter and the
    `device_type="gpu" | "cpu"` mapping per ml-backends.md §5.3.
    """

    family_name = "lightgbm"


class TorchTrainable(_TrainableAdapterBase):
    """Wraps a raw torch.nn.Module as a Trainable.

    Phase 3 will wrap the inner module in a LightningModule whose
    `training_step` is derived from the user-supplied loss/optimizer
    config.
    """

    family_name = "torch"


class LightningTrainable(_TrainableAdapterBase):
    """Identity adapter for user-supplied LightningModules.

    Phase 3 will route this through `L.Trainer` directly — no adapter
    layer needed because the user already provided the LightningModule.
    """

    family_name = "lightning"


# Forward-ref shim: TrainingResult lives in `_result.py`; this module
# imports it lazily so that `from kailash_ml.trainable import ...`
# doesn't pull the whole result stack at protocol-inspection time.
Union  # silence unused-import when Union type annotations move in Phase 3

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared types + protocol for AutoML search strategies."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "ParamSpec",
    "Trial",
    "TrialOutcome",
    "SearchStrategy",
]


@dataclass(frozen=True)
class ParamSpec:
    """A single hyperparameter dimension.

    Five kinds of parameter are supported, matching
    ``specs/ml-automl.md`` §2.2:

    - ``kind="int"`` with ``low`` / ``high`` (inclusive)
    - ``kind="float"`` with ``low`` / ``high`` (continuous uniform)
    - ``kind="log_float"`` with ``low`` / ``high`` (log-uniform)
    - ``kind="categorical"`` with ``choices=[...]``
    - ``kind="bool"`` (equivalent to categorical[False, True])
    """

    name: str
    kind: str
    low: float | int | None = None
    high: float | int | None = None
    choices: tuple[Any, ...] | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ParamSpec.name must be non-empty")
        if self.kind not in ("int", "float", "log_float", "categorical", "bool"):
            raise ValueError(
                f"ParamSpec.kind must be one of int|float|log_float|categorical|bool, "
                f"got {self.kind!r}"
            )
        if self.kind in ("int", "float", "log_float"):
            if self.low is None or self.high is None:
                raise ValueError(f"{self.kind} spec requires low and high")
            if not math.isfinite(float(self.low)) or not math.isfinite(
                float(self.high)
            ):
                raise ValueError(f"{self.name}: low/high must be finite")
            if float(self.low) > float(self.high):
                raise ValueError(f"{self.name}: low={self.low!r} > high={self.high!r}")
            if self.kind == "log_float" and float(self.low) <= 0:
                raise ValueError(f"{self.name}: log_float requires low > 0")
        if self.kind == "categorical":
            if not self.choices or len(self.choices) == 0:
                raise ValueError(f"{self.name}: categorical requires non-empty choices")
        if self.kind == "bool":
            object.__setattr__(self, "choices", (False, True))


@dataclass(frozen=True)
class Trial:
    """One proposed set of hyperparameters awaiting evaluation."""

    trial_number: int
    params: dict[str, Any]
    fidelity: float = 1.0
    rung: int = 0


@dataclass
class TrialOutcome:
    """Evaluated trial — what came back from the trainer."""

    trial_number: int
    params: dict[str, Any]
    metric: float
    metric_name: str
    direction: str  # "maximize" | "minimize"
    duration_seconds: float = 0.0
    cost_microdollars: int = 0
    fidelity: float = 1.0
    rung: int = 0
    error: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def is_finite(self) -> bool:
        return isinstance(self.metric, (int, float)) and math.isfinite(
            float(self.metric)
        )


@runtime_checkable
class SearchStrategy(Protocol):
    """Protocol every search strategy implements.

    Per ``specs/ml-automl.md`` §4.2 MUST 1 the protocol is three
    methods: :meth:`suggest` produces the next trial,
    :meth:`observe` folds an evaluated trial back into the strategy's
    internal state, and :meth:`should_stop` signals exhaustion of the
    search (e.g., grid finished, halving last rung complete).
    """

    name: str

    def suggest(self, history: list[TrialOutcome]) -> Trial | None:
        """Return the next trial, or ``None`` if the strategy is done."""
        ...

    def observe(self, outcome: TrialOutcome) -> None:
        """Fold an evaluated trial back into the strategy's state."""
        ...

    def should_stop(self, history: list[TrialOutcome]) -> bool:
        """Return True when no further trials will be produced."""
        ...

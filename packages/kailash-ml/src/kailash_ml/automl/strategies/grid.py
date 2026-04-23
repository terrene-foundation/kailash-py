# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Grid search — exhaustive enumeration over a discrete cartesian product.

Grid requires every dimension to be finite. Continuous dimensions
(``float`` / ``log_float``) are discretised into
``grid_resolution`` evenly-spaced points per dimension. An unbounded
continuous dimension raises ``HPOSpaceUnboundedError`` per
``specs/ml-automl.md`` §10.
"""
from __future__ import annotations

import itertools
import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any

from kailash_ml.automl.strategies._base import (
    ParamSpec,
    SearchStrategy,
    Trial,
    TrialOutcome,
)

logger = logging.getLogger(__name__)

__all__ = ["GridSearchStrategy", "HPOSpaceUnboundedError"]


class HPOSpaceUnboundedError(Exception):
    """Grid search cannot enumerate an unbounded continuous space."""


def _discretize(spec: ParamSpec, resolution: int) -> tuple[Any, ...]:
    """Enumerate the finite set of values a dimension yields under grid."""
    if spec.kind == "categorical":
        return tuple(spec.choices or ())
    if spec.kind == "bool":
        return (False, True)
    low, high = float(spec.low), float(spec.high)  # type: ignore[arg-type]
    if spec.kind == "int":
        # All integers in [low, high] inclusive, subsampled to `resolution` if large
        rng = range(int(low), int(high) + 1)
        if len(rng) <= resolution:
            return tuple(rng)
        # Evenly-spaced sample of `resolution` integers
        step = max(1, (len(rng) - 1) // (resolution - 1))
        return tuple(rng[i] for i in range(0, len(rng), step))[:resolution]
    if spec.kind == "float":
        if resolution < 2:
            return (low,)
        span = high - low
        return tuple(low + (span * i / (resolution - 1)) for i in range(resolution))
    if spec.kind == "log_float":
        if resolution < 2:
            return (low,)
        log_low, log_high = math.log(low), math.log(high)
        span = log_high - log_low
        return tuple(
            math.exp(log_low + (span * i / (resolution - 1))) for i in range(resolution)
        )
    raise HPOSpaceUnboundedError(f"Cannot discretize ParamSpec {spec!r}")


@dataclass
class GridSearchStrategy:
    """Deterministic grid search over a ParamSpec list."""

    space: list[ParamSpec]
    grid_resolution: int = 5
    max_trials: int | None = None
    seed: int = 42
    name: str = "grid"
    # Internals
    _points: list[dict[str, Any]] = field(default_factory=list)
    _cursor: int = 0

    def __post_init__(self) -> None:
        if not self.space:
            raise ValueError("GridSearchStrategy requires a non-empty ParamSpec list")
        if self.grid_resolution < 1:
            raise ValueError("grid_resolution must be >= 1")
        if self.max_trials is not None and self.max_trials <= 0:
            raise ValueError("max_trials must be positive if supplied")
        axes: list[tuple[str, tuple[Any, ...]]] = []
        for spec in self.space:
            values = _discretize(spec, self.grid_resolution)
            if len(values) == 0:
                raise HPOSpaceUnboundedError(
                    f"ParamSpec {spec.name!r} produced zero grid points"
                )
            axes.append((spec.name, values))
        # Deterministic cartesian product order; seed only controls optional shuffle
        product = list(itertools.product(*[vals for _, vals in axes]))
        points = [dict(zip([name for name, _ in axes], combo)) for combo in product]
        if self.max_trials is not None and len(points) > self.max_trials:
            # Shuffle deterministically then truncate, so over-large grids yield
            # a representative (not corner-biased) subsample.
            rng = random.Random(self.seed)
            rng.shuffle(points)
            points = points[: self.max_trials]
        self._points = points
        logger.info(
            "automl.strategy.grid.initialized",
            extra={
                "dimensions": len(self.space),
                "grid_resolution": self.grid_resolution,
                "enumerated_points": len(self._points),
                "max_trials": self.max_trials,
                "seed": self.seed,
            },
        )

    def suggest(self, history: list[TrialOutcome]) -> Trial | None:
        if self._cursor >= len(self._points):
            return None
        params = dict(self._points[self._cursor])
        trial = Trial(trial_number=self._cursor, params=params)
        self._cursor += 1
        return trial

    def observe(self, outcome: TrialOutcome) -> None:
        # Grid does not adapt to outcomes, but we log for audit parity
        logger.debug(
            "automl.strategy.grid.observe",
            extra={
                "trial_number": outcome.trial_number,
                "metric": outcome.metric if outcome.is_finite else None,
            },
        )

    def should_stop(self, history: list[TrialOutcome]) -> bool:
        return self._cursor >= len(self._points)

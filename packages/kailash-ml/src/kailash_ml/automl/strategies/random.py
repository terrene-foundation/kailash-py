# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Random search — deterministic seeded sampling per ParamSpec.

Random sampling is the simplest strategy that still demonstrates the
value of SearchStrategy's protocol: given the same seed and the same
ParamSpec list, two runs MUST produce identical suggestions. This is
the determinism invariant exercised by
``test_automl_random_is_deterministic``.
"""
from __future__ import annotations

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

__all__ = ["RandomSearchStrategy"]


def _sample_one(rng: random.Random, spec: ParamSpec) -> Any:
    if spec.kind == "categorical":
        return rng.choice(list(spec.choices or ()))
    if spec.kind == "bool":
        return rng.choice([False, True])
    low, high = float(spec.low), float(spec.high)  # type: ignore[arg-type]
    if spec.kind == "int":
        return rng.randint(int(low), int(high))
    if spec.kind == "float":
        return rng.uniform(low, high)
    if spec.kind == "log_float":
        log_low, log_high = math.log(low), math.log(high)
        return math.exp(rng.uniform(log_low, log_high))
    raise ValueError(f"Unknown ParamSpec kind: {spec.kind!r}")


@dataclass
class RandomSearchStrategy:
    """Deterministic random search.

    ``max_trials`` bounds the sweep. With the same ``seed`` the stream
    of ``suggest()`` return values is byte-identical across runs — this
    is the contract of :meth:`__eq__`-independent determinism.
    """

    space: list[ParamSpec]
    max_trials: int = 30
    seed: int = 42
    name: str = "random"
    # Internals
    _rng: random.Random = field(default=None)  # type: ignore[assignment]
    _cursor: int = 0

    def __post_init__(self) -> None:
        if not self.space:
            raise ValueError("RandomSearchStrategy requires a non-empty ParamSpec list")
        if self.max_trials <= 0:
            raise ValueError("max_trials must be positive")
        # random.Random with an int seed is the reproducible-source for
        # every downstream sample; never import global `random` at the
        # callsite (would leak global state into the sweep).
        self._rng = random.Random(self.seed)
        logger.info(
            "automl.strategy.random.initialized",
            extra={
                "dimensions": len(self.space),
                "max_trials": self.max_trials,
                "seed": self.seed,
            },
        )

    def suggest(self, history: list[TrialOutcome]) -> Trial | None:
        if self._cursor >= self.max_trials:
            return None
        params = {spec.name: _sample_one(self._rng, spec) for spec in self.space}
        trial = Trial(trial_number=self._cursor, params=params)
        self._cursor += 1
        return trial

    def observe(self, outcome: TrialOutcome) -> None:
        logger.debug(
            "automl.strategy.random.observe",
            extra={
                "trial_number": outcome.trial_number,
                "metric": outcome.metric if outcome.is_finite else None,
            },
        )

    def should_stop(self, history: list[TrialOutcome]) -> bool:
        return self._cursor >= self.max_trials

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AutoML search strategies — grid, random, Bayesian, successive halving.

Every strategy implements :class:`SearchStrategy`. Adding a new
strategy is a one-class addition here; the :class:`AutoMLEngine`
dispatches by strategy name.

See ``specs/ml-automl.md`` §4.1 for the full algorithm catalog. W27a
delivers the four strategies named in the M1 brief; BOHB / CMA-ES /
PBT / ASHA are deferred to post-M1 milestones.
"""
from __future__ import annotations

from kailash_ml.automl.strategies._base import (
    ParamSpec,
    SearchStrategy,
    Trial,
    TrialOutcome,
)
from kailash_ml.automl.strategies.bayesian import BayesianSearchStrategy
from kailash_ml.automl.strategies.grid import GridSearchStrategy
from kailash_ml.automl.strategies.halving import SuccessiveHalvingStrategy
from kailash_ml.automl.strategies.random import RandomSearchStrategy

__all__ = [
    "ParamSpec",
    "SearchStrategy",
    "Trial",
    "TrialOutcome",
    "GridSearchStrategy",
    "RandomSearchStrategy",
    "BayesianSearchStrategy",
    "SuccessiveHalvingStrategy",
    "resolve_strategy",
]


def resolve_strategy(
    name: str,
    *,
    seed: int = 42,
    **kwargs: object,
) -> SearchStrategy:
    """Factory for a :class:`SearchStrategy` by name.

    ``name`` is one of ``"grid"``, ``"random"``, ``"bayesian"``,
    ``"halving"``. Unknown names raise ``ValueError``. See
    ``specs/ml-automl.md`` §4.1 for the semantics of each.
    """
    key = name.lower()
    if key == "grid":
        return GridSearchStrategy(seed=seed, **kwargs)  # type: ignore[arg-type]
    if key == "random":
        return RandomSearchStrategy(seed=seed, **kwargs)  # type: ignore[arg-type]
    if key == "bayesian":
        return BayesianSearchStrategy(seed=seed, **kwargs)  # type: ignore[arg-type]
    if key in ("halving", "successive_halving"):
        return SuccessiveHalvingStrategy(seed=seed, **kwargs)  # type: ignore[arg-type]
    raise ValueError(
        f"Unknown search strategy '{name}'. Valid: grid, random, bayesian, halving"
    )

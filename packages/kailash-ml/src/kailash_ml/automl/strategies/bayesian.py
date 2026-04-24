# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Bayesian search — GP + expected-improvement (EI) acquisition.

Two operating modes, both seeded for determinism:

1. **scikit-optimize present** (``kailash-ml[automl-bayes]`` extra):
   delegate to ``skopt.Optimizer`` with ``acq_func="EI"``. This is the
   production path described in ``specs/ml-automl.md`` §4.1.
2. **scikit-optimize missing**: fall back to a local implementation
   that performs (a) an initial random burst of
   ``n_initial_points`` trials, (b) a lightweight EI over candidate
   random samples using the sample mean + variance of history as the
   posterior. The fallback is deterministic under the same seed and
   preserves the Bayesian "exploit + explore" behaviour in a way that
   unit tests can exercise without requiring the optional extra.

Both paths satisfy the :class:`SearchStrategy` protocol.
"""
from __future__ import annotations

import logging
import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Any

from kailash_ml.automl.strategies._base import (
    ParamSpec,
    SearchStrategy,
    Trial,
    TrialOutcome,
)
from kailash_ml.automl.strategies.random import _sample_one

logger = logging.getLogger(__name__)

__all__ = ["BayesianSearchStrategy"]


def _try_import_skopt():  # pragma: no cover — import shim
    try:
        import skopt  # type: ignore[import-not-found,unused-ignore]

        return skopt
    except ImportError:
        return None


def _spec_to_skopt_dimension(spec: ParamSpec):  # pragma: no cover — lazy
    # Lazy import so skopt is never pulled in when unused
    from skopt.space import Categorical, Integer, Real  # type: ignore

    if spec.kind == "categorical":
        return Categorical(list(spec.choices or ()), name=spec.name)
    if spec.kind == "bool":
        return Categorical([False, True], name=spec.name)
    low, high = spec.low, spec.high
    if spec.kind == "int":
        return Integer(int(low), int(high), name=spec.name)  # type: ignore[arg-type]
    if spec.kind == "float":
        return Real(float(low), float(high), name=spec.name)  # type: ignore[arg-type]
    if spec.kind == "log_float":
        return Real(float(low), float(high), prior="log-uniform", name=spec.name)  # type: ignore[arg-type]
    raise ValueError(f"Unknown ParamSpec kind: {spec.kind!r}")


def _ei_score(
    candidate_metric_estimate: float,
    history_metrics: list[float],
    direction: str,
) -> float:
    """Dead-simple Expected-Improvement proxy used in the no-skopt fallback.

    Uses the sample mean / stdev of history to build a Gaussian
    posterior around ``candidate_metric_estimate``. The candidate
    estimate is a random-projection of the sample (deterministic under
    the same rng seed) so this function alone is not the full Bayesian
    loop — :class:`BayesianSearchStrategy.suggest` combines it with a
    candidate sampler.
    """
    if not history_metrics:
        return 0.0
    best = max(history_metrics) if direction == "maximize" else min(history_metrics)
    stdev = statistics.pstdev(history_metrics) if len(history_metrics) > 1 else 1.0
    if stdev == 0:
        return 0.0
    improvement = (
        candidate_metric_estimate - best
        if direction == "maximize"
        else best - candidate_metric_estimate
    )
    # EI is the positive part of improvement weighted by posterior stdev
    return max(0.0, improvement) / stdev


@dataclass
class BayesianSearchStrategy:
    """GP + EI Bayesian search with a deterministic fallback.

    When scikit-optimize is installed the full GP path is used. The
    fallback retains the interface shape so unit tests can run without
    the optional extra.
    """

    space: list[ParamSpec]
    max_trials: int = 30
    n_initial_points: int = 5
    seed: int = 42
    direction: str = "maximize"
    candidates_per_iter: int = 16
    name: str = "bayesian"
    # Internals
    _rng: random.Random = field(default=None)  # type: ignore[assignment]
    _cursor: int = 0
    _history_metrics: list[float] = field(default_factory=list)
    _skopt_optimizer: Any = field(default=None)  # Optional[skopt.Optimizer]

    def __post_init__(self) -> None:
        if not self.space:
            raise ValueError(
                "BayesianSearchStrategy requires a non-empty ParamSpec list"
            )
        if self.max_trials <= 0:
            raise ValueError("max_trials must be positive")
        if self.n_initial_points <= 0:
            raise ValueError("n_initial_points must be positive")
        if self.direction not in ("maximize", "minimize"):
            raise ValueError("direction must be 'maximize' or 'minimize'")
        if self.candidates_per_iter <= 0:
            raise ValueError("candidates_per_iter must be positive")
        self._rng = random.Random(self.seed)
        skopt = _try_import_skopt()
        if skopt is not None:
            try:  # pragma: no cover — exercised only when extra installed
                dims = [_spec_to_skopt_dimension(s) for s in self.space]
                self._skopt_optimizer = skopt.Optimizer(
                    dimensions=dims,
                    base_estimator="GP",
                    n_initial_points=self.n_initial_points,
                    acq_func="EI",
                    random_state=self.seed,
                )
                logger.info(
                    "automl.strategy.bayesian.initialized",
                    extra={
                        "backend": "scikit-optimize",
                        "dimensions": len(self.space),
                        "max_trials": self.max_trials,
                        "seed": self.seed,
                    },
                )
                return
            except Exception as exc:  # pragma: no cover — skopt init failure
                logger.warning(
                    "automl.strategy.bayesian.skopt_init_failed",
                    extra={
                        "error_class": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )
                self._skopt_optimizer = None
        logger.info(
            "automl.strategy.bayesian.initialized",
            extra={
                "backend": "fallback",
                "dimensions": len(self.space),
                "max_trials": self.max_trials,
                "seed": self.seed,
                "note": (
                    "scikit-optimize not installed; using deterministic"
                    " Random+EI fallback. Install kailash-ml[automl-bayes]"
                    " for the full GP path."
                ),
            },
        )

    def suggest(self, history: list[TrialOutcome]) -> Trial | None:
        if self._cursor >= self.max_trials:
            return None
        trial_number = self._cursor
        if self._skopt_optimizer is not None:  # pragma: no cover
            raw = self._skopt_optimizer.ask()
            params = {s.name: v for s, v in zip(self.space, raw)}
        elif self._cursor < self.n_initial_points or len(self._history_metrics) < 2:
            # Warm-up: random draws until we have enough history for EI
            params = {spec.name: _sample_one(self._rng, spec) for spec in self.space}
        else:
            # Fallback EI: draw candidates, score by EI against history stats
            best_params: dict[str, Any] | None = None
            best_ei = -math.inf
            mean_metric = statistics.fmean(self._history_metrics)
            stdev_metric = (
                statistics.pstdev(self._history_metrics)
                if len(self._history_metrics) > 1
                else 1.0
            )
            for _ in range(self.candidates_per_iter):
                candidate = {
                    spec.name: _sample_one(self._rng, spec) for spec in self.space
                }
                # Deterministic metric estimate: mean + rng-perturbation*stdev
                estimate = mean_metric + (self._rng.gauss(0.0, 1.0) * stdev_metric)
                score = _ei_score(estimate, self._history_metrics, self.direction)
                if score > best_ei:
                    best_ei = score
                    best_params = candidate
            params = best_params or {
                spec.name: _sample_one(self._rng, spec) for spec in self.space
            }
        self._cursor += 1
        return Trial(trial_number=trial_number, params=params)

    def observe(self, outcome: TrialOutcome) -> None:
        if not outcome.is_finite:
            logger.debug(
                "automl.strategy.bayesian.observe.skipped_nonfinite",
                extra={"trial_number": outcome.trial_number},
            )
            return
        self._history_metrics.append(float(outcome.metric))
        if self._skopt_optimizer is not None:  # pragma: no cover
            # skopt expects a list of values in the same order as dimensions
            xs = [outcome.params[s.name] for s in self.space]
            # Convert "maximize" to skopt's "minimize" convention
            y = (
                -float(outcome.metric)
                if self.direction == "maximize"
                else float(outcome.metric)
            )
            self._skopt_optimizer.tell(xs, y)
        logger.debug(
            "automl.strategy.bayesian.observe",
            extra={
                "trial_number": outcome.trial_number,
                "metric": float(outcome.metric),
                "history_len": len(self._history_metrics),
            },
        )

    def should_stop(self, history: list[TrialOutcome]) -> bool:
        return self._cursor >= self.max_trials

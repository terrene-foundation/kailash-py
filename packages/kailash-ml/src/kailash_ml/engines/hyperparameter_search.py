# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""HyperparameterSearch engine -- grid, random, Bayesian, successive halving.

Supports four strategies for hyperparameter optimization. Integrates with
TrainingPipeline for execution and ModelRegistry for result tracking.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl
from kailash_ml.types import FeatureSchema

logger = logging.getLogger(__name__)

__all__ = [
    "HyperparameterSearch",
    "ParamDistribution",
    "SearchSpace",
    "SearchConfig",
    "TrialResult",
    "SearchResult",
]


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------


@dataclass
class ParamDistribution:
    """Single hyperparameter distribution.

    Attributes:
        name: The hyperparameter name (e.g., ``"n_estimators"``).
        type: The distribution type. Valid values:

            - ``"uniform"`` — continuous uniform between ``low`` and ``high``
            - ``"log_uniform"`` — log-uniform between ``low`` and ``high``
            - ``"int_uniform"`` — integer uniform between ``low`` and ``high``
            - ``"categorical"`` — categorical choice from ``choices``

            .. note::
                The ``type`` field intentionally shadows Python's ``type()``
                builtin for API clarity. Use the ``distribution`` property
                as an alias if preferred.

        low: Lower bound for uniform/log_uniform/int_uniform distributions.
        high: Upper bound for uniform/log_uniform/int_uniform distributions.
        choices: List of values for categorical distributions.
    """

    name: str
    type: str  # "uniform", "log_uniform", "int_uniform", "categorical"
    low: float | None = None
    high: float | None = None
    choices: list[Any] | None = None  # for categorical

    @property
    def distribution(self) -> str:
        """Alias for ``type`` that avoids shadowing the Python builtin."""
        return self.type

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "low": self.low,
            "high": self.high,
            "choices": self.choices,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParamDistribution:
        return cls(
            name=data["name"],
            type=data["type"],
            low=data.get("low"),
            high=data.get("high"),
            choices=data.get("choices"),
        )


@dataclass
class SearchSpace:
    """Collection of hyperparameter distributions."""

    params: list[ParamDistribution]

    def sample_grid(self) -> list[dict[str, Any]]:
        """Generate exhaustive grid (small spaces only)."""
        param_values: list[list[tuple[str, Any]]] = []
        for p in self.params:
            if p.type == "categorical" and p.choices is not None:
                param_values.append([(p.name, v) for v in p.choices])
            elif p.type == "int_uniform" and p.low is not None and p.high is not None:
                values = list(range(int(p.low), int(p.high) + 1))
                param_values.append([(p.name, v) for v in values])
            elif p.low is not None and p.high is not None:
                # For continuous params in grid: sample 5 points
                values = np.linspace(p.low, p.high, 5).tolist()
                param_values.append([(p.name, v) for v in values])
            else:
                param_values.append([(p.name, None)])

        combos = list(itertools.product(*param_values))
        return [dict(combo) for combo in combos]

    def sample_random(
        self, n: int, rng: np.random.RandomState | None = None
    ) -> list[dict[str, Any]]:
        """Generate n random samples."""
        if rng is None:
            rng = np.random.RandomState(42)
        samples: list[dict[str, Any]] = []
        for _ in range(n):
            params: dict[str, Any] = {}
            for p in self.params:
                if p.type == "uniform" and p.low is not None and p.high is not None:
                    params[p.name] = float(rng.uniform(p.low, p.high))
                elif (
                    p.type == "log_uniform" and p.low is not None and p.high is not None
                ):
                    params[p.name] = float(
                        np.exp(rng.uniform(np.log(p.low), np.log(p.high)))
                    )
                elif (
                    p.type == "int_uniform" and p.low is not None and p.high is not None
                ):
                    params[p.name] = int(rng.randint(int(p.low), int(p.high) + 1))
                elif p.type == "categorical" and p.choices is not None:
                    params[p.name] = p.choices[rng.randint(len(p.choices))]
                else:
                    params[p.name] = None
            samples.append(params)
        return samples

    def to_dict(self) -> dict[str, Any]:
        return {
            "params": [p.to_dict() for p in self.params],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SearchSpace:
        return cls(
            params=[ParamDistribution.from_dict(p) for p in data["params"]],
        )


@dataclass
class SearchConfig:
    """Search configuration."""

    strategy: str = "bayesian"  # "grid", "random", "bayesian", "successive_halving"
    n_trials: int = 50
    timeout_seconds: float | None = None
    metric_to_optimize: str = "accuracy"
    direction: str = "maximize"  # "maximize" | "minimize"
    early_stopping_patience: int | None = None
    n_jobs: int = 1
    register_best: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "n_trials": self.n_trials,
            "timeout_seconds": self.timeout_seconds,
            "metric_to_optimize": self.metric_to_optimize,
            "direction": self.direction,
            "early_stopping_patience": self.early_stopping_patience,
            "n_jobs": self.n_jobs,
            "register_best": self.register_best,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SearchConfig:
        return cls(
            strategy=data.get("strategy", "bayesian"),
            n_trials=data.get("n_trials", 50),
            timeout_seconds=data.get("timeout_seconds"),
            metric_to_optimize=data.get("metric_to_optimize", "accuracy"),
            direction=data.get("direction", "maximize"),
            early_stopping_patience=data.get("early_stopping_patience"),
            n_jobs=data.get("n_jobs", 1),
            register_best=data.get("register_best", True),
        )


@dataclass
class TrialResult:
    """Result of a single hyperparameter trial."""

    trial_number: int
    params: dict[str, Any]
    metrics: dict[str, float]
    training_time_seconds: float
    pruned: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_number": self.trial_number,
            "params": dict(self.params),
            "metrics": dict(self.metrics),
            "training_time_seconds": self.training_time_seconds,
            "pruned": self.pruned,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrialResult:
        return cls(
            trial_number=data["trial_number"],
            params=data["params"],
            metrics=data["metrics"],
            training_time_seconds=data["training_time_seconds"],
            pruned=data.get("pruned", False),
        )


@dataclass
class SearchResult:
    """Complete search result."""

    best_params: dict[str, Any]
    best_metrics: dict[str, float]
    best_trial_number: int
    all_trials: list[TrialResult]
    total_time_seconds: float
    strategy: str
    model_version: Any | None = None  # ModelVersion | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_params": dict(self.best_params),
            "best_metrics": dict(self.best_metrics),
            "best_trial_number": self.best_trial_number,
            "all_trials": [t.to_dict() for t in self.all_trials],
            "total_time_seconds": self.total_time_seconds,
            "strategy": self.strategy,
            "model_version": None,  # ModelVersion is not JSON-serializable
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SearchResult:
        return cls(
            best_params=data["best_params"],
            best_metrics=data["best_metrics"],
            best_trial_number=data["best_trial_number"],
            all_trials=[TrialResult.from_dict(t) for t in data["all_trials"]],
            total_time_seconds=data["total_time_seconds"],
            strategy=data["strategy"],
            model_version=data.get("model_version"),
        )


# ---------------------------------------------------------------------------
# HyperparameterSearch
# ---------------------------------------------------------------------------


class HyperparameterSearch:
    """[P1: Production with Caveats] Hyperparameter optimization engine.

    Supports grid, random, Bayesian, and successive halving strategies.
    Known limitations: Bayesian search with very high-dimensional spaces
    (>50 parameters) may not converge within default trial budget.

    Parameters
    ----------
    pipeline:
        A :class:`TrainingPipeline` instance for executing training runs.
    """

    def __init__(self, pipeline: Any) -> None:
        self._pipeline = pipeline

    async def search(
        self,
        data: pl.DataFrame,
        schema: FeatureSchema,
        base_model_spec: Any,
        search_space: SearchSpace,
        config: SearchConfig,
        eval_spec: Any,
        experiment_name: str,
        *,
        tracker: Any | None = None,
        parent_run_id: str | None = None,
    ) -> SearchResult:
        """Run hyperparameter search.

        Iterates over hyperparameter configurations using the selected
        strategy, trains a model for each, and returns the best result.

        Parameters
        ----------
        tracker:
            Optional ExperimentTracker instance. When provided, creates a
            parent run for the search and logs each trial as a child run.
            Typed as ``Any`` to avoid circular imports.
        parent_run_id:
            Optional parent run ID. When provided, the search parent run
            is created as a child of this run.
        """
        start_time = time.perf_counter()

        # Start a parent run for the search if tracker is provided
        search_run_id: str | None = None
        if tracker is not None:
            parent_run_obj = await tracker.start_run(
                experiment_name,
                run_name=f"search_{config.strategy}",
                parent_run_id=parent_run_id,
            )
            search_run_id = parent_run_obj.id  # type: ignore[union-attr]
            # Log search config as params on the search run
            await tracker.log_params(
                search_run_id,
                {
                    "search_strategy": config.strategy,
                    "n_trials": str(config.n_trials),
                    "metric_to_optimize": config.metric_to_optimize,
                    "direction": config.direction,
                    "model_class": str(getattr(base_model_spec, "model_class", "")),
                },
            )

        try:
            if config.strategy == "bayesian":
                result = await self._bayesian_search(
                    data,
                    schema,
                    base_model_spec,
                    search_space,
                    config,
                    eval_spec,
                    experiment_name,
                    tracker=tracker,
                    parent_run_id=search_run_id,
                )
            elif config.strategy == "successive_halving":
                result = await self._successive_halving_search(
                    data,
                    schema,
                    base_model_spec,
                    search_space,
                    config,
                    eval_spec,
                    experiment_name,
                    tracker=tracker,
                    parent_run_id=search_run_id,
                )
            elif config.strategy == "random":
                result = await self._random_search(
                    data,
                    schema,
                    base_model_spec,
                    search_space,
                    config,
                    eval_spec,
                    experiment_name,
                    tracker=tracker,
                    parent_run_id=search_run_id,
                )
            elif config.strategy == "grid":
                result = await self._grid_search(
                    data,
                    schema,
                    base_model_spec,
                    search_space,
                    config,
                    eval_spec,
                    experiment_name,
                    tracker=tracker,
                    parent_run_id=search_run_id,
                )
            else:
                raise ValueError(f"Unknown search strategy: {config.strategy}")

            result.total_time_seconds = time.perf_counter() - start_time

            # Log best trial metrics on search run
            if (
                tracker is not None
                and search_run_id is not None
                and result.best_metrics
            ):
                await tracker.log_metrics(search_run_id, result.best_metrics)

        except Exception:
            if tracker is not None and search_run_id is not None:
                await tracker.end_run(search_run_id, status="FAILED")
            raise
        else:
            if tracker is not None and search_run_id is not None:
                await tracker.end_run(search_run_id, status="COMPLETED")

        return result

    # ------------------------------------------------------------------
    # Random search
    # ------------------------------------------------------------------

    async def _random_search(
        self,
        data,
        schema,
        base_model_spec,
        search_space,
        config,
        eval_spec,
        experiment_name,
        *,
        tracker: Any | None = None,
        parent_run_id: str | None = None,
    ) -> SearchResult:
        from kailash_ml.engines.training_pipeline import ModelSpec

        rng = np.random.RandomState(42)
        param_sets = search_space.sample_random(config.n_trials, rng)
        all_trials: list[TrialResult] = []

        for i, params in enumerate(param_sets):
            merged_spec = ModelSpec(
                model_class=base_model_spec.model_class,
                hyperparameters={**base_model_spec.hyperparameters, **params},
                framework=base_model_spec.framework,
            )
            trial_start = time.perf_counter()
            train_result = await self._pipeline.train(
                data,
                schema,
                merged_spec,
                eval_spec,
                f"{experiment_name}_trial_{i}",
                tracker=tracker,
                parent_run_id=parent_run_id,
            )
            trial_time = time.perf_counter() - trial_start
            all_trials.append(
                TrialResult(
                    trial_number=i,
                    params=params,
                    metrics=train_result.metrics,
                    training_time_seconds=trial_time,
                )
            )

        return self._build_result(
            all_trials,
            config,
            "random",
            base_model_spec,
            data,
            schema,
            eval_spec,
            experiment_name,
        )

    # ------------------------------------------------------------------
    # Grid search
    # ------------------------------------------------------------------

    async def _grid_search(
        self,
        data,
        schema,
        base_model_spec,
        search_space,
        config,
        eval_spec,
        experiment_name,
        *,
        tracker: Any | None = None,
        parent_run_id: str | None = None,
    ) -> SearchResult:
        from kailash_ml.engines.training_pipeline import ModelSpec

        param_sets = search_space.sample_grid()
        all_trials: list[TrialResult] = []

        for i, params in enumerate(param_sets):
            merged_spec = ModelSpec(
                model_class=base_model_spec.model_class,
                hyperparameters={**base_model_spec.hyperparameters, **params},
                framework=base_model_spec.framework,
            )
            trial_start = time.perf_counter()
            train_result = await self._pipeline.train(
                data,
                schema,
                merged_spec,
                eval_spec,
                f"{experiment_name}_trial_{i}",
                tracker=tracker,
                parent_run_id=parent_run_id,
            )
            trial_time = time.perf_counter() - trial_start
            all_trials.append(
                TrialResult(
                    trial_number=i,
                    params=params,
                    metrics=train_result.metrics,
                    training_time_seconds=trial_time,
                )
            )

        return self._build_result(
            all_trials,
            config,
            "grid",
            base_model_spec,
            data,
            schema,
            eval_spec,
            experiment_name,
        )

    # ------------------------------------------------------------------
    # Bayesian search (optuna)
    # ------------------------------------------------------------------

    async def _bayesian_search(
        self,
        data,
        schema,
        base_model_spec,
        search_space,
        config,
        eval_spec,
        experiment_name,
        *,
        tracker: Any | None = None,
        parent_run_id: str | None = None,
    ) -> SearchResult:
        import optuna
        from kailash_ml.engines.training_pipeline import ModelSpec

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        all_trials: list[TrialResult] = []
        loop = asyncio.get_running_loop()

        def objective(trial: optuna.Trial) -> float:
            params: dict[str, Any] = {}
            for p in search_space.params:
                if p.type == "uniform" and p.low is not None and p.high is not None:
                    params[p.name] = trial.suggest_float(p.name, p.low, p.high)
                elif (
                    p.type == "log_uniform" and p.low is not None and p.high is not None
                ):
                    params[p.name] = trial.suggest_float(
                        p.name, p.low, p.high, log=True
                    )
                elif (
                    p.type == "int_uniform" and p.low is not None and p.high is not None
                ):
                    params[p.name] = trial.suggest_int(p.name, int(p.low), int(p.high))
                elif p.type == "categorical" and p.choices is not None:
                    params[p.name] = trial.suggest_categorical(p.name, p.choices)

            merged_spec = ModelSpec(
                model_class=base_model_spec.model_class,
                hyperparameters={**base_model_spec.hyperparameters, **params},
                framework=base_model_spec.framework,
            )

            trial_start = time.perf_counter()
            # Run async train synchronously within optuna objective
            future = asyncio.run_coroutine_threadsafe(
                self._pipeline.train(
                    data,
                    schema,
                    merged_spec,
                    eval_spec,
                    f"{experiment_name}_trial_{trial.number}",
                    tracker=tracker,
                    parent_run_id=parent_run_id,
                ),
                loop,
            )
            train_result = future.result(timeout=config.timeout_seconds)
            trial_time = time.perf_counter() - trial_start

            trial_result = TrialResult(
                trial_number=trial.number,
                params=params,
                metrics=train_result.metrics,
                training_time_seconds=trial_time,
            )
            all_trials.append(trial_result)

            return train_result.metrics.get(config.metric_to_optimize, 0.0)

        study = optuna.create_study(direction=config.direction)
        await loop.run_in_executor(
            None,
            lambda: study.optimize(
                objective, n_trials=config.n_trials, timeout=config.timeout_seconds
            ),
        )

        return self._build_result(
            all_trials,
            config,
            "bayesian",
            base_model_spec,
            data,
            schema,
            eval_spec,
            experiment_name,
        )

    # ------------------------------------------------------------------
    # Successive halving (optuna pruner)
    # ------------------------------------------------------------------

    async def _successive_halving_search(
        self,
        data,
        schema,
        base_model_spec,
        search_space,
        config,
        eval_spec,
        experiment_name,
        *,
        tracker: Any | None = None,
        parent_run_id: str | None = None,
    ) -> SearchResult:
        """Successive halving via Optuna's SuccessiveHalvingPruner.

        Trains each configuration at increasing resource budgets (data
        fractions). Poor performers are pruned early, concentrating
        compute on the most promising hyperparameter regions.
        """
        import optuna
        from kailash_ml.engines.training_pipeline import ModelSpec

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        # Resource rungs: train on 12.5%, 25%, 50%, 100% of data
        n_rungs = 4
        rung_fractions = [1.0 / (2 ** (n_rungs - 1 - i)) for i in range(n_rungs)]

        all_trials: list[TrialResult] = []
        loop = asyncio.get_running_loop()

        def objective(trial: optuna.Trial) -> float:
            params: dict[str, Any] = {}
            for p in search_space.params:
                if p.type == "uniform" and p.low is not None and p.high is not None:
                    params[p.name] = trial.suggest_float(p.name, p.low, p.high)
                elif (
                    p.type == "log_uniform" and p.low is not None and p.high is not None
                ):
                    params[p.name] = trial.suggest_float(
                        p.name, p.low, p.high, log=True
                    )
                elif (
                    p.type == "int_uniform" and p.low is not None and p.high is not None
                ):
                    params[p.name] = trial.suggest_int(p.name, int(p.low), int(p.high))
                elif p.type == "categorical" and p.choices is not None:
                    params[p.name] = trial.suggest_categorical(p.name, p.choices)

            merged_spec = ModelSpec(
                model_class=base_model_spec.model_class,
                hyperparameters={**base_model_spec.hyperparameters, **params},
                framework=base_model_spec.framework,
            )

            trial_start = time.perf_counter()
            last_value = 0.0
            last_metrics: dict[str, float] = {}

            for step, frac in enumerate(rung_fractions):
                # Sub-sample data for this rung
                n_rows = data.height
                sample_n = max(1, int(n_rows * frac))
                if sample_n >= n_rows:
                    rung_data = data
                else:
                    rung_data = data.sample(n=sample_n, seed=42 + trial.number)

                future = asyncio.run_coroutine_threadsafe(
                    self._pipeline.train(
                        rung_data,
                        schema,
                        merged_spec,
                        eval_spec,
                        f"{experiment_name}_trial_{trial.number}_rung_{step}",
                        tracker=tracker,
                        parent_run_id=parent_run_id,
                    ),
                    loop,
                )
                train_result = future.result(timeout=config.timeout_seconds)
                last_value = train_result.metrics.get(config.metric_to_optimize, 0.0)
                last_metrics = train_result.metrics

                # Report intermediate value and check for pruning
                trial.report(last_value, step)
                if trial.should_prune():
                    trial_time = time.perf_counter() - trial_start
                    all_trials.append(
                        TrialResult(
                            trial_number=trial.number,
                            params=params,
                            metrics=last_metrics,
                            training_time_seconds=trial_time,
                            pruned=True,
                        )
                    )
                    raise optuna.TrialPruned()

            trial_time = time.perf_counter() - trial_start
            all_trials.append(
                TrialResult(
                    trial_number=trial.number,
                    params=params,
                    metrics=last_metrics,
                    training_time_seconds=trial_time,
                    pruned=False,
                )
            )
            return last_value

        pruner = optuna.pruners.SuccessiveHalvingPruner(
            min_resource=1,
            reduction_factor=2,
            min_early_stopping_rate=0,
        )
        study = optuna.create_study(direction=config.direction, pruner=pruner)
        await loop.run_in_executor(
            None,
            lambda: study.optimize(
                objective, n_trials=config.n_trials, timeout=config.timeout_seconds
            ),
        )

        return self._build_result(
            all_trials,
            config,
            "successive_halving",
            base_model_spec,
            data,
            schema,
            eval_spec,
            experiment_name,
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _build_result(
        self,
        all_trials: list[TrialResult],
        config: SearchConfig,
        strategy: str,
        base_model_spec: Any,
        data: Any,
        schema: Any,
        eval_spec: Any,
        experiment_name: str,
    ) -> SearchResult:
        """Find best trial and build SearchResult."""
        if not all_trials:
            return SearchResult(
                best_params={},
                best_metrics={},
                best_trial_number=-1,
                all_trials=[],
                total_time_seconds=0.0,
                strategy=strategy,
            )

        # Only consider completed (non-pruned) trials for best selection
        completed = [t for t in all_trials if not t.pruned]
        candidates = completed if completed else all_trials

        if config.direction == "maximize":
            best = max(
                candidates,
                key=lambda t: t.metrics.get(config.metric_to_optimize, 0.0),
            )
        else:
            best = min(
                candidates,
                key=lambda t: t.metrics.get(config.metric_to_optimize, float("inf")),
            )

        return SearchResult(
            best_params=best.params,
            best_metrics=best.metrics,
            best_trial_number=best.trial_number,
            all_trials=all_trials,
            total_time_seconds=sum(t.training_time_seconds for t in all_trials),
            strategy=strategy,
        )

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for HyperparameterSearch engine."""
from __future__ import annotations

import numpy as np
import pytest
from kailash_ml.engines.hyperparameter_search import (
    HyperparameterSearch,
    ParamDistribution,
    SearchConfig,
    SearchResult,
    SearchSpace,
    TrialResult,
)


# ---------------------------------------------------------------------------
# SearchConfig validation
# ---------------------------------------------------------------------------


class TestSearchConfig:
    """Tests for SearchConfig defaults and fields."""

    def test_defaults(self) -> None:
        cfg = SearchConfig()
        assert cfg.strategy == "bayesian"
        assert cfg.n_trials == 50
        assert cfg.metric_to_optimize == "accuracy"
        assert cfg.direction == "maximize"
        assert cfg.timeout_seconds is None
        assert cfg.early_stopping_patience is None
        assert cfg.n_jobs == 1
        assert cfg.register_best is True

    def test_custom_config(self) -> None:
        cfg = SearchConfig(
            strategy="grid",
            n_trials=10,
            direction="minimize",
            metric_to_optimize="rmse",
        )
        assert cfg.strategy == "grid"
        assert cfg.n_trials == 10
        assert cfg.direction == "minimize"
        assert cfg.metric_to_optimize == "rmse"


# ---------------------------------------------------------------------------
# ParamDistribution
# ---------------------------------------------------------------------------


class TestParamDistribution:
    """Tests for ParamDistribution."""

    def test_uniform_distribution(self) -> None:
        p = ParamDistribution("lr", "uniform", low=0.001, high=0.1)
        assert p.name == "lr"
        assert p.type == "uniform"
        assert p.low == 0.001
        assert p.high == 0.1

    def test_categorical_distribution(self) -> None:
        p = ParamDistribution("kernel", "categorical", choices=["rbf", "linear"])
        assert p.choices == ["rbf", "linear"]
        assert p.low is None

    def test_param_distribution_alias(self) -> None:
        """Test that distribution property aliases type field."""
        p = ParamDistribution("lr", "uniform", low=0.001, high=0.1)
        assert p.distribution == "uniform"
        assert p.distribution == p.type


# ---------------------------------------------------------------------------
# SearchSpace.sample_grid
# ---------------------------------------------------------------------------


class TestSearchSpaceGrid:
    """Tests for SearchSpace.sample_grid."""

    def test_grid_categorical_only(self) -> None:
        space = SearchSpace(
            [
                ParamDistribution("a", "categorical", choices=[1, 2]),
                ParamDistribution("b", "categorical", choices=["x", "y"]),
            ]
        )
        grid = space.sample_grid()
        assert len(grid) == 4  # 2 x 2
        # Each combo should appear
        combos = {(d["a"], d["b"]) for d in grid}
        assert combos == {(1, "x"), (1, "y"), (2, "x"), (2, "y")}

    def test_grid_int_uniform(self) -> None:
        space = SearchSpace([ParamDistribution("depth", "int_uniform", low=3, high=5)])
        grid = space.sample_grid()
        # Should produce [3, 4, 5]
        values = sorted(d["depth"] for d in grid)
        assert values == [3, 4, 5]

    def test_grid_continuous_samples_5_points(self) -> None:
        space = SearchSpace([ParamDistribution("lr", "uniform", low=0.0, high=1.0)])
        grid = space.sample_grid()
        assert len(grid) == 5
        # Should be linspace(0, 1, 5)
        vals = [d["lr"] for d in grid]
        expected = np.linspace(0.0, 1.0, 5).tolist()
        for v, e in zip(vals, expected):
            assert abs(v - e) < 1e-10

    def test_grid_missing_bounds_produces_none(self) -> None:
        space = SearchSpace([ParamDistribution("x", "uniform")])  # no low/high
        grid = space.sample_grid()
        assert len(grid) == 1
        assert grid[0]["x"] is None


# ---------------------------------------------------------------------------
# SearchSpace.sample_random
# ---------------------------------------------------------------------------


class TestSearchSpaceRandom:
    """Tests for SearchSpace.sample_random."""

    def test_random_produces_n_samples(self) -> None:
        space = SearchSpace([ParamDistribution("lr", "uniform", low=0.001, high=0.1)])
        samples = space.sample_random(7)
        assert len(samples) == 7

    def test_random_log_uniform_positive(self) -> None:
        space = SearchSpace(
            [ParamDistribution("lr", "log_uniform", low=0.001, high=1.0)]
        )
        samples = space.sample_random(20)
        for s in samples:
            assert s["lr"] > 0

    def test_random_int_uniform_range(self) -> None:
        space = SearchSpace([ParamDistribution("n", "int_uniform", low=1, high=5)])
        samples = space.sample_random(50)
        for s in samples:
            assert 1 <= s["n"] <= 5
            assert isinstance(s["n"], int)

    def test_random_categorical_from_choices(self) -> None:
        space = SearchSpace(
            [ParamDistribution("k", "categorical", choices=["a", "b", "c"])]
        )
        samples = space.sample_random(30)
        for s in samples:
            assert s["k"] in ("a", "b", "c")

    def test_random_reproducible_with_seed(self) -> None:
        space = SearchSpace([ParamDistribution("lr", "uniform", low=0.0, high=1.0)])
        s1 = space.sample_random(5, rng=np.random.RandomState(99))
        s2 = space.sample_random(5, rng=np.random.RandomState(99))
        assert s1 == s2


# ---------------------------------------------------------------------------
# _build_result helper
# ---------------------------------------------------------------------------


class TestBuildResult:
    """Tests for the internal _build_result helper (via SearchResult ordering)."""

    def test_best_trial_maximize(self) -> None:
        """_build_result picks the trial with the highest metric when maximize."""
        from unittest.mock import MagicMock

        pipeline = MagicMock()
        hs = HyperparameterSearch(pipeline)

        trials = [
            TrialResult(0, {"lr": 0.1}, {"accuracy": 0.8}, 1.0),
            TrialResult(1, {"lr": 0.01}, {"accuracy": 0.95}, 2.0),
            TrialResult(2, {"lr": 0.5}, {"accuracy": 0.7}, 0.5),
        ]
        config = SearchConfig(direction="maximize", metric_to_optimize="accuracy")

        result = hs._build_result(
            trials, config, "random", None, None, None, None, "exp"
        )
        assert result.best_trial_number == 1
        assert result.best_params == {"lr": 0.01}
        assert result.best_metrics["accuracy"] == 0.95

    def test_best_trial_minimize(self) -> None:
        """_build_result picks the trial with the lowest metric when minimize."""
        from unittest.mock import MagicMock

        pipeline = MagicMock()
        hs = HyperparameterSearch(pipeline)

        trials = [
            TrialResult(0, {"lr": 0.1}, {"rmse": 5.0}, 1.0),
            TrialResult(1, {"lr": 0.01}, {"rmse": 2.0}, 2.0),
            TrialResult(2, {"lr": 0.5}, {"rmse": 8.0}, 0.5),
        ]
        config = SearchConfig(direction="minimize", metric_to_optimize="rmse")

        result = hs._build_result(
            trials, config, "random", None, None, None, None, "exp"
        )
        assert result.best_trial_number == 1
        assert result.best_metrics["rmse"] == 2.0

    def test_empty_trials_returns_empty_result(self) -> None:
        from unittest.mock import MagicMock

        pipeline = MagicMock()
        hs = HyperparameterSearch(pipeline)
        config = SearchConfig()

        result = hs._build_result([], config, "random", None, None, None, None, "exp")
        assert result.best_params == {}
        assert result.best_trial_number == -1
        assert result.all_trials == []

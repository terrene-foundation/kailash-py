"""Unit tests for kaizen_agents.research_patterns.intelligent_optimizer.

Tier 1 — pure logic, no infrastructure.
Re-establishes coverage for the modules moved by PR #75 (closes #821).
"""

from __future__ import annotations

import random
import re

from kaizen_agents.research_patterns.intelligent_optimizer import (
    IntelligentOptimizer,
    OptimizationResult,
)

# ---------------------------------------------------------------------------
# OptimizationResult
# ---------------------------------------------------------------------------


class TestOptimizationResult:
    def test_construction(self) -> None:
        result = OptimizationResult(
            best_params={"lr": 0.01, "depth": 4}, improvement=0.85, iterations=10
        )
        assert result.best_params == {"lr": 0.01, "depth": 4}
        assert result.improvement == 0.85
        assert result.iterations == 10


# ---------------------------------------------------------------------------
# IntelligentOptimizer __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_defaults(self) -> None:
        optimizer = IntelligentOptimizer(strategy="bayesian")
        assert optimizer.strategy == "bayesian"
        assert optimizer.acquisition_function == "ei"
        assert optimizer.population_size == 20
        assert optimizer.crossover_rate == 0.8
        assert optimizer.mutation_rate == 0.1
        assert optimizer.epsilon == 0.1
        assert optimizer.objectives == []
        assert optimizer.weights == []
        assert optimizer.policy == {}
        assert optimizer.q_values == {}

    def test_overrides(self) -> None:
        optimizer = IntelligentOptimizer(
            strategy="genetic",
            acquisition="ucb",
            population_size=50,
            crossover_rate=0.6,
            mutation_rate=0.2,
            epsilon=0.3,
            objectives=["accuracy", "latency"],
            weights=[0.7, 0.3],
        )
        assert optimizer.strategy == "genetic"
        assert optimizer.acquisition_function == "ucb"
        assert optimizer.population_size == 50
        assert optimizer.crossover_rate == 0.6
        assert optimizer.mutation_rate == 0.2
        assert optimizer.epsilon == 0.3
        assert optimizer.objectives == ["accuracy", "latency"]
        assert optimizer.weights == [0.7, 0.3]


# ---------------------------------------------------------------------------
# optimize() dispatch
# ---------------------------------------------------------------------------


class TestOptimizeBayesian:
    def test_returns_expected_shape(self) -> None:
        random.seed(0)
        optimizer = IntelligentOptimizer(strategy="bayesian", acquisition="ei")
        result = optimizer.optimize(
            feature_id="x",
            parameter_space={"lr": (0.001, 0.1), "depth": (2, 8)},
            n_iterations=5,
        )
        assert set(result.keys()) == {"best_params", "improvement", "acquisition"}
        assert result["acquisition"] == "ei"
        assert "lr" in result["best_params"]
        assert "depth" in result["best_params"]

    def test_int_bounds_yield_int_samples(self) -> None:
        random.seed(0)
        optimizer = IntelligentOptimizer(strategy="bayesian")
        result = optimizer.optimize(
            feature_id="x", parameter_space={"depth": (1, 5)}, n_iterations=3
        )
        assert isinstance(result["best_params"]["depth"], int)
        assert 1 <= result["best_params"]["depth"] <= 5

    def test_float_bounds_yield_float_samples(self) -> None:
        random.seed(0)
        optimizer = IntelligentOptimizer(strategy="bayesian")
        result = optimizer.optimize(
            feature_id="x", parameter_space={"lr": (0.0, 1.0)}, n_iterations=3
        )
        assert isinstance(result["best_params"]["lr"], float)
        assert 0.0 <= result["best_params"]["lr"] <= 1.0


class TestOptimizeGenetic:
    def test_returns_expected_shape(self) -> None:
        random.seed(1)
        optimizer = IntelligentOptimizer(strategy="genetic", population_size=5)
        result = optimizer.optimize(
            feature_id="x",
            parameter_space={"lr": (0.001, 0.1), "depth": (2, 8)},
            n_generations=3,
        )
        assert set(result.keys()) == {"best_genome", "fitness"}
        assert "lr" in result["best_genome"]
        assert "depth" in result["best_genome"]
        assert 0.0 <= result["fitness"] <= 1.0


class TestOptimizeMultiObjective:
    def test_returns_expected_shape(self) -> None:
        random.seed(2)
        optimizer = IntelligentOptimizer(
            strategy="multi_objective", objectives=["accuracy", "latency"]
        )
        result = optimizer.optimize(
            feature_id="x", parameter_space={"lr": (0.0, 1.0)}, n_iterations=4
        )
        assert set(result.keys()) == {"pareto_frontier", "n_solutions"}
        assert result["n_solutions"] == 4
        assert isinstance(result["pareto_frontier"], list)
        for solution in result["pareto_frontier"]:
            assert "params" in solution
            assert "objectives" in solution
            assert set(solution["objectives"].keys()) == {"accuracy", "latency"}


class TestOptimizeUnknownStrategy:
    def test_returns_empty_dict(self) -> None:
        optimizer = IntelligentOptimizer(strategy="not_a_real_strategy")
        result = optimizer.optimize(
            feature_id="x", parameter_space={"lr": (0.0, 1.0)}, n_iterations=2
        )
        assert result == {}


# ---------------------------------------------------------------------------
# RL methods
# ---------------------------------------------------------------------------


_ACTION_RE = re.compile(r"^action_[0-5]$")


class TestSelectAction:
    def test_explore_branch_returns_random_action(self) -> None:
        random.seed(0)
        optimizer = IntelligentOptimizer(strategy="rl", epsilon=1.0)  # always explore
        action = optimizer.select_action({"step": 1})
        assert _ACTION_RE.match(action)

    def test_exploit_branch_returns_max_q_action(self) -> None:
        optimizer = IntelligentOptimizer(strategy="rl", epsilon=0.0)  # never explore
        state = {"step": 1}
        state_key = str(sorted(state.items()))
        # Pre-seed a Q-table so exploit has a deterministic max
        optimizer.q_values[state_key] = {
            "action_0": 0.1,
            "action_3": 0.9,
            "action_5": 0.2,
        }
        assert optimizer.select_action(state) == "action_3"

    def test_exploit_with_no_qvalue_falls_back_to_random(self) -> None:
        random.seed(0)
        optimizer = IntelligentOptimizer(strategy="rl", epsilon=0.0)
        action = optimizer.select_action({"step": 99})
        assert _ACTION_RE.match(action)


class TestUpdatePolicy:
    def test_creates_entry_for_new_action(self) -> None:
        optimizer = IntelligentOptimizer(strategy="rl")
        optimizer.update_policy("action_2", 0.7)
        assert optimizer.policy == {"action_2": [0.7]}

    def test_appends_to_existing_action(self) -> None:
        optimizer = IntelligentOptimizer(strategy="rl")
        optimizer.update_policy("action_2", 0.7)
        optimizer.update_policy("action_2", 0.4)
        assert optimizer.policy == {"action_2": [0.7, 0.4]}

    def test_get_policy_returns_live_dict(self) -> None:
        optimizer = IntelligentOptimizer(strategy="rl")
        optimizer.update_policy("action_1", 0.5)
        assert optimizer.get_policy() is optimizer.policy


# ---------------------------------------------------------------------------
# _dominates predicate
# ---------------------------------------------------------------------------


class TestDominates:
    def test_strict_domination(self) -> None:
        optimizer = IntelligentOptimizer(strategy="multi_objective")
        # obj1 is better-or-equal in both AND strictly better in one
        assert optimizer._dominates({"a": 0.9, "b": 0.7}, {"a": 0.5, "b": 0.7}) is True

    def test_no_domination_when_tied(self) -> None:
        optimizer = IntelligentOptimizer(strategy="multi_objective")
        # Equal across all keys — no strict-better axis
        assert optimizer._dominates({"a": 0.5, "b": 0.5}, {"a": 0.5, "b": 0.5}) is False

    def test_no_domination_when_mixed(self) -> None:
        optimizer = IntelligentOptimizer(strategy="multi_objective")
        # obj1 better on a, worse on b — neither dominates
        assert optimizer._dominates({"a": 0.9, "b": 0.3}, {"a": 0.5, "b": 0.7}) is False

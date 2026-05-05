"""Unit tests for kaizen_agents.research_patterns.advanced_patterns.

Tier 1 — pure logic, no infrastructure.
Re-establishes coverage for the modules moved by PR #75 (closes #821).
"""

from __future__ import annotations

import random

import pytest

from kaizen_agents.research_patterns.advanced_patterns import (
    AdaptationStrategy,
    AdaptivePattern,
    AdvancedPatternBuilder,
    CompositionalPattern,
    HierarchicalPattern,
    LearningStrategy,
    MetaLearningPattern,
    PatternStrategy,
)

# ---------------------------------------------------------------------------
# Enum smoke
# ---------------------------------------------------------------------------


class TestEnums:
    def test_pattern_strategy_members(self) -> None:
        assert PatternStrategy.SEQUENTIAL.value == "sequential"
        assert PatternStrategy.PARALLEL.value == "parallel"
        assert PatternStrategy.ENSEMBLE.value == "ensemble"

    def test_adaptation_strategy_members(self) -> None:
        assert AdaptationStrategy.PERFORMANCE_BASED.value == "performance_based"
        assert AdaptationStrategy.ACCURACY_BASED.value == "accuracy_based"
        assert AdaptationStrategy.FAULT_TOLERANT.value == "fault_tolerant"

    def test_learning_strategy_members(self) -> None:
        assert LearningStrategy.BANDIT.value == "bandit"
        assert LearningStrategy.GRADIENT.value == "gradient"


# ---------------------------------------------------------------------------
# CompositionalPattern
# ---------------------------------------------------------------------------


class TestCompositionalPattern:
    def test_post_init_sets_num_components(self) -> None:
        pattern = CompositionalPattern(features=["a", "b", "c"], strategy="sequential")
        assert pattern.num_components == 3

    def test_post_init_empty_features(self) -> None:
        pattern = CompositionalPattern(features=[], strategy="sequential")
        assert pattern.num_components == 0

    def test_execute_sequential(self) -> None:
        pattern = CompositionalPattern(
            features=["alpha", "beta", "gamma"], strategy="sequential"
        )
        result = pattern.execute({"start": "input"})
        assert result["execution_order"] == ["alpha", "beta", "gamma"]
        assert result["output"]["processed_by"] == "gamma"  # last feature wins
        assert result["output"]["start"] == "input"  # original key preserved

    def test_execute_parallel(self) -> None:
        pattern = CompositionalPattern(features=["x", "y"], strategy="parallel")
        result = pattern.execute({"data": 1})
        assert result["num_parallel"] == 2
        assert {entry["feature"] for entry in result["outputs"]} == {"x", "y"}
        for entry in result["outputs"]:
            assert entry["result"] == f"output_from_{entry['feature']}"

    def test_execute_ensemble(self) -> None:
        pattern = CompositionalPattern(
            features=["one", "two", "three"], strategy="ensemble"
        )
        result = pattern.execute({})
        assert result["confidence"] == 0.85
        assert len(result["votes"]) == 3
        assert result["consensus_output"] == result["votes"][0]


# ---------------------------------------------------------------------------
# HierarchicalPattern
# ---------------------------------------------------------------------------


class TestHierarchicalPattern:
    def test_post_init_sets_num_levels(self) -> None:
        pattern = HierarchicalPattern(levels=[["a"], ["b", "c"], ["d"]])
        assert pattern.num_levels == 3

    def test_get_level_features_in_range(self) -> None:
        pattern = HierarchicalPattern(levels=[["root"], ["mid1", "mid2"]])
        assert pattern.get_level_features(0) == ["root"]
        assert pattern.get_level_features(1) == ["mid1", "mid2"]

    def test_get_level_features_out_of_range(self) -> None:
        pattern = HierarchicalPattern(levels=[["only"]])
        assert pattern.get_level_features(-1) == []
        assert pattern.get_level_features(5) == []

    def test_execute_records_levels(self) -> None:
        pattern = HierarchicalPattern(levels=[["lvl0"], ["lvl1a", "lvl1b"]])
        result = pattern.execute({"seed": 1})
        assert result["execution_levels"] == [0, 1]
        # final_output is the last feature of the last level reached
        assert result["final_output"] == "lvl1b"
        assert result["level_0_output"] is not None
        assert result["level_0_output"]["level"] == 0
        assert result["level_1_input"] == result["level_0_output"]


# ---------------------------------------------------------------------------
# AdaptivePattern
# ---------------------------------------------------------------------------


class TestAdaptivePattern:
    def test_post_init_initializes_performance_stats(self) -> None:
        pattern = AdaptivePattern(
            base_features=["a", "b", "c"], adaptation_strategy="performance_based"
        )
        assert pattern.performance_stats == {"a": 0.5, "b": 0.5, "c": 0.5}
        assert pattern.can_adapt is True
        assert pattern.adaptation_history == []

    def test_execute_performance_based_prefers_fast_feature(self) -> None:
        pattern = AdaptivePattern(
            base_features=["slow-feature", "fast-feature", "other"],
            adaptation_strategy="performance_based",
        )
        result = pattern.execute({"x": 1})
        assert result["selected_feature"] == "fast-feature"
        assert result["adaptation_applied"] is True
        assert result["feature_used"] == "fast-feature"

    def test_execute_performance_based_falls_back_to_first(self) -> None:
        pattern = AdaptivePattern(
            base_features=["alpha", "beta"], adaptation_strategy="performance_based"
        )
        result = pattern.execute({})
        assert result["selected_feature"] == "alpha"

    def test_execute_accuracy_based_prefers_accurate_feature(self) -> None:
        pattern = AdaptivePattern(
            base_features=["other", "accurate-feature"],
            adaptation_strategy="accuracy_based",
        )
        result = pattern.execute({})
        assert result["selected_feature"] == "accurate-feature"

    def test_execute_fault_tolerant_returns_primary(self) -> None:
        pattern = AdaptivePattern(
            base_features=["primary", "backup"], adaptation_strategy="fault_tolerant"
        )
        result = pattern.execute({})
        assert result["selected_feature"] == "primary"

    def test_execute_unknown_strategy_returns_first(self) -> None:
        pattern = AdaptivePattern(
            base_features=["a", "b"], adaptation_strategy="unknown_mode"
        )
        result = pattern.execute({})
        assert result["selected_feature"] == "a"

    def test_get_adaptation_history_grows_with_executions(self) -> None:
        pattern = AdaptivePattern(
            base_features=["only"], adaptation_strategy="fault_tolerant"
        )
        pattern.execute({})
        pattern.execute({})
        history = pattern.get_adaptation_history()
        assert len(history) == 2
        assert all(entry["feature"] == "only" for entry in history)
        assert all("timestamp" in entry for entry in history)


# ---------------------------------------------------------------------------
# MetaLearningPattern
# ---------------------------------------------------------------------------


class TestMetaLearningPattern:
    def test_post_init_initializes_uniform_weights(self) -> None:
        pattern = MetaLearningPattern(
            candidate_features=["a", "b", "c", "d"], learning_strategy="bandit"
        )
        assert set(pattern.feature_weights.keys()) == {"a", "b", "c", "d"}
        # Uniform distribution sums to 1.0
        assert pytest.approx(sum(pattern.feature_weights.values())) == 1.0
        for weight in pattern.feature_weights.values():
            assert pytest.approx(weight) == 0.25

    def test_execute_bandit_returns_valid_feature(self) -> None:
        random.seed(0)
        pattern = MetaLearningPattern(
            candidate_features=["x", "y", "z"],
            learning_strategy="bandit",
            exploration_rate=0.5,
        )
        result = pattern.execute({"data": 1})
        assert result["selected_feature"] in {"x", "y", "z"}
        assert result["execution_id"] == "exec_0"
        assert len(pattern.execution_history) == 1

    def test_execute_gradient_picks_highest_weight(self) -> None:
        pattern = MetaLearningPattern(
            candidate_features=["lo", "hi"], learning_strategy="gradient"
        )
        # Bias the weights so "hi" dominates
        pattern.feature_weights["hi"] = 0.9
        pattern.feature_weights["lo"] = 0.1
        result = pattern.execute({})
        assert result["selected_feature"] == "hi"

    def test_execute_unknown_strategy_returns_first(self) -> None:
        pattern = MetaLearningPattern(
            candidate_features=["first", "second"], learning_strategy="unknown"
        )
        result = pattern.execute({})
        assert result["selected_feature"] == "first"

    def test_provide_feedback_bandit_updates_weight_to_average_reward(self) -> None:
        pattern = MetaLearningPattern(
            candidate_features=["a", "b"], learning_strategy="bandit"
        )
        # Force selection of "a" by making it highest-weight + zero exploration
        pattern.feature_weights["a"] = 0.99
        pattern.feature_weights["b"] = 0.01
        pattern.exploration_rate = 0.0
        result1 = pattern.execute({})
        pattern.provide_feedback(result1["execution_id"], 0.8)
        assert pytest.approx(pattern.feature_weights["a"]) == 0.8
        # Second feedback averages
        pattern.feature_weights["a"] = 0.99  # re-bias for second selection
        result2 = pattern.execute({})
        pattern.provide_feedback(result2["execution_id"], 0.4)
        assert pytest.approx(pattern.feature_weights["a"]) == 0.6  # avg(0.8, 0.4)

    def test_provide_feedback_gradient_adds_learning_rate_times_reward(self) -> None:
        pattern = MetaLearningPattern(
            candidate_features=["a"], learning_strategy="gradient"
        )
        baseline = pattern.feature_weights["a"]
        result = pattern.execute({})
        pattern.provide_feedback(result["execution_id"], 1.0)
        # Gradient: weight += 0.1 * reward
        assert pytest.approx(pattern.feature_weights["a"]) == baseline + 0.1

    def test_provide_feedback_unknown_id_is_noop(self) -> None:
        pattern = MetaLearningPattern(
            candidate_features=["a"], learning_strategy="bandit"
        )
        baseline_weight = pattern.feature_weights["a"]
        baseline_rewards = dict(pattern.feature_rewards)
        pattern.provide_feedback("does_not_exist", 5.0)
        assert pattern.feature_weights["a"] == baseline_weight
        assert dict(pattern.feature_rewards) == baseline_rewards

    def test_get_learning_stats_shape(self) -> None:
        pattern = MetaLearningPattern(
            candidate_features=["a", "b"], learning_strategy="bandit"
        )
        random.seed(1)
        result = pattern.execute({})
        pattern.provide_feedback(result["execution_id"], 0.5)
        stats = pattern.get_learning_stats()
        assert stats["total_executions"] == 1
        assert set(stats["feature_preferences"].keys()) == {"a", "b"}
        assert "average_rewards" in stats

    def test_get_feature_weights_returns_live_dict(self) -> None:
        pattern = MetaLearningPattern(
            candidate_features=["a"], learning_strategy="gradient"
        )
        weights = pattern.get_feature_weights()
        assert weights is pattern.feature_weights


# ---------------------------------------------------------------------------
# AdvancedPatternBuilder
# ---------------------------------------------------------------------------


class TestAdvancedPatternBuilder:
    def test_init_defaults_to_none(self) -> None:
        builder = AdvancedPatternBuilder()
        assert builder.registry is None
        assert builder.feature_manager is None

    def test_init_accepts_registry_and_manager(self) -> None:
        sentinel_registry = object()
        sentinel_manager = object()
        builder = AdvancedPatternBuilder(
            registry=sentinel_registry, feature_manager=sentinel_manager
        )
        assert builder.registry is sentinel_registry
        assert builder.feature_manager is sentinel_manager

    def test_compose_returns_compositional_pattern(self) -> None:
        builder = AdvancedPatternBuilder()
        pattern = builder.compose(features=["a", "b"], strategy="ensemble")
        assert isinstance(pattern, CompositionalPattern)
        assert pattern.features == ["a", "b"]
        assert pattern.strategy == "ensemble"

    def test_hierarchical_returns_hierarchical_pattern(self) -> None:
        builder = AdvancedPatternBuilder()
        pattern = builder.hierarchical(levels=[["root"], ["leaf1", "leaf2"]])
        assert isinstance(pattern, HierarchicalPattern)
        assert pattern.levels == [["root"], ["leaf1", "leaf2"]]
        assert pattern.num_levels == 2

    def test_adaptive_returns_adaptive_pattern(self) -> None:
        builder = AdvancedPatternBuilder()
        pattern = builder.adaptive(
            base_features=["a", "b"], adaptation_strategy="performance_based"
        )
        assert isinstance(pattern, AdaptivePattern)
        assert pattern.base_features == ["a", "b"]
        assert pattern.adaptation_strategy == "performance_based"

    def test_meta_learning_default_exploration_rate(self) -> None:
        builder = AdvancedPatternBuilder()
        pattern = builder.meta_learning(
            candidate_features=["a", "b"], learning_strategy="bandit"
        )
        assert isinstance(pattern, MetaLearningPattern)
        assert pattern.exploration_rate == 0.1

    def test_meta_learning_explicit_exploration_rate(self) -> None:
        builder = AdvancedPatternBuilder()
        pattern = builder.meta_learning(
            candidate_features=["a"],
            learning_strategy="gradient",
            exploration_rate=0.42,
        )
        assert pattern.exploration_rate == 0.42

    def test_get_available_features_with_no_registry(self) -> None:
        builder = AdvancedPatternBuilder()
        assert builder.get_available_features() == []

    def test_get_available_features_with_registry(self) -> None:
        builder = AdvancedPatternBuilder(registry=object())
        # Current implementation returns [] regardless — pin the contract so a
        # future enhancement that wires the registry update this test in lockstep.
        assert builder.get_available_features() == []

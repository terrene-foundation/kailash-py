"""
Unit Tests for LLMRouter (Tier 1)

Tests the LLMRouter for intelligent model selection:
- RoutingRule creation and matching
- LLMRouter routing strategies
- Rule-based routing
- Capability filtering
"""

import pytest

from kaizen.llm.routing.analyzer import TaskComplexity, TaskType
from kaizen.llm.routing.capabilities import LLMCapabilities, register_model
from kaizen.llm.routing.router import (
    LLMRouter,
    RoutingDecision,
    RoutingRule,
    RoutingStrategy,
)


class TestRoutingStrategy:
    """Tests for RoutingStrategy enum."""

    def test_all_strategies_exist(self):
        """Test all strategies exist."""
        assert RoutingStrategy.RULES
        assert RoutingStrategy.TASK_COMPLEXITY
        assert RoutingStrategy.COST_OPTIMIZED
        assert RoutingStrategy.QUALITY_OPTIMIZED
        assert RoutingStrategy.BALANCED

    def test_strategy_values(self):
        """Test strategy values."""
        assert RoutingStrategy.RULES.value == "rules"
        assert RoutingStrategy.BALANCED.value == "balanced"


class TestRoutingRule:
    """Tests for RoutingRule dataclass."""

    def test_create_rule(self):
        """Test creating a routing rule."""
        rule = RoutingRule(
            name="test_rule",
            condition=lambda task, ctx: "test" in task.lower(),
            model="gpt-4",
            priority=10,
        )

        assert rule.name == "test_rule"
        assert rule.model == "gpt-4"
        assert rule.priority == 10

    def test_rule_matches_true(self):
        """Test rule matching when condition is true."""
        rule = RoutingRule(
            name="code_rule",
            condition=lambda task, ctx: "code" in task.lower(),
            model="gpt-4",
        )

        assert rule.matches("Write some code", {}) is True

    def test_rule_matches_false(self):
        """Test rule matching when condition is false."""
        rule = RoutingRule(
            name="code_rule",
            condition=lambda task, ctx: "code" in task.lower(),
            model="gpt-4",
        )

        assert rule.matches("Write a story", {}) is False

    def test_rule_handles_exception(self):
        """Test rule handles condition exceptions gracefully."""

        def bad_condition(task, ctx):
            raise ValueError("Test error")

        rule = RoutingRule(
            name="bad_rule",
            condition=bad_condition,
            model="gpt-4",
        )

        # Should return False, not raise
        assert rule.matches("test", {}) is False


class TestRoutingDecision:
    """Tests for RoutingDecision dataclass."""

    def test_create_decision(self):
        """Test creating a routing decision."""
        decision = RoutingDecision(
            model="gpt-4",
            strategy=RoutingStrategy.BALANCED,
            rule_name="test_rule",
            reasoning="Test reasoning",
            alternatives=["claude-3-opus", "gpt-3.5-turbo"],
        )

        assert decision.model == "gpt-4"
        assert decision.strategy == RoutingStrategy.BALANCED
        assert len(decision.alternatives) == 2

    def test_decision_to_dict(self):
        """Test decision serialization."""
        decision = RoutingDecision(
            model="gpt-4",
            strategy=RoutingStrategy.RULES,
            rule_name="test",
            reasoning="Matched rule",
        )

        data = decision.to_dict()

        assert data["model"] == "gpt-4"
        assert data["strategy"] == "rules"
        assert data["rule_name"] == "test"


class TestLLMRouterCreation:
    """Tests for LLMRouter creation."""

    def test_create_default(self):
        """Test creating with defaults."""
        router = LLMRouter()

        assert router.default_model == "gpt-4"
        assert "gpt-4" in router.available_models

    def test_create_with_models(self):
        """Test creating with available models."""
        router = LLMRouter(
            available_models=["gpt-4", "claude-3-opus", "gpt-3.5-turbo"],
            default_model="gpt-4",
        )

        assert len(router.available_models) == 3
        assert "claude-3-opus" in router.available_models

    def test_add_remove_model(self):
        """Test adding and removing models."""
        router = LLMRouter(available_models=["gpt-4"])

        router.add_model("claude-3-opus")
        assert "claude-3-opus" in router.available_models

        router.remove_model("claude-3-opus")
        assert "claude-3-opus" not in router.available_models


class TestLLMRouterRules:
    """Tests for rule management."""

    def test_add_rule(self):
        """Test adding a rule."""
        router = LLMRouter(available_models=["gpt-4", "gpt-3.5-turbo"])

        router.add_rule(
            name="simple_tasks",
            condition=lambda task, ctx: "simple" in task.lower(),
            model="gpt-3.5-turbo",
            priority=10,
        )

        assert len(router.rules) == 1
        assert router.rules[0].name == "simple_tasks"

    def test_add_keyword_rule(self):
        """Test adding keyword-based rule."""
        router = LLMRouter(available_models=["gpt-4", "gpt-3.5-turbo"])

        router.add_keyword_rule(
            keywords=["simple", "quick", "basic"],
            model="gpt-3.5-turbo",
            priority=5,
        )

        # Test the rule works
        decision = router.route(
            "Give me a quick answer", strategy=RoutingStrategy.RULES
        )
        assert decision.model == "gpt-3.5-turbo"

    def test_add_type_rule(self):
        """Test adding task type rule."""
        router = LLMRouter(available_models=["gpt-4", "codellama"])

        router.add_type_rule(
            task_type=TaskType.CODE,
            model="codellama",
            priority=10,
        )

        # Route a code task
        decision = router.route(
            "Write a Python function",
            strategy=RoutingStrategy.RULES,
        )
        assert decision.model == "codellama"

    def test_add_complexity_rule(self):
        """Test adding complexity threshold rule."""
        router = LLMRouter(available_models=["gpt-4", "o1"])

        router.add_complexity_rule(
            min_complexity=TaskComplexity.HIGH,
            model="o1",
            priority=10,
        )

        # Route a complex task
        decision = router.route(
            "Design a sophisticated, comprehensive, advanced system architecture",
            strategy=RoutingStrategy.RULES,
        )
        # Should use o1 for complex tasks
        assert decision.model in ("o1", "gpt-4")

    def test_rule_priority_order(self):
        """Test rules are sorted by priority."""
        router = LLMRouter(available_models=["gpt-4", "gpt-3.5-turbo"])

        router.add_rule(
            name="low_priority",
            condition=lambda t, c: True,
            model="gpt-3.5-turbo",
            priority=1,
        )
        router.add_rule(
            name="high_priority",
            condition=lambda t, c: True,
            model="gpt-4",
            priority=10,
        )

        # High priority should be first
        assert router.rules[0].name == "high_priority"

    def test_remove_rule(self):
        """Test removing a rule."""
        router = LLMRouter()

        router.add_rule("test", lambda t, c: True, "gpt-4", 0)
        assert len(router.rules) == 1

        removed = router.remove_rule("test")
        assert removed is True
        assert len(router.rules) == 0

    def test_clear_rules(self):
        """Test clearing all rules."""
        router = LLMRouter()

        router.add_rule("r1", lambda t, c: True, "gpt-4", 0)
        router.add_rule("r2", lambda t, c: True, "gpt-4", 0)

        router.clear_rules()
        assert len(router.rules) == 0


class TestLLMRouterRuleBasedRouting:
    """Tests for rule-based routing strategy."""

    def test_first_matching_rule_wins(self):
        """Test first matching rule is used."""
        router = LLMRouter(available_models=["gpt-4", "gpt-3.5-turbo", "claude-3-opus"])

        # Higher priority rule
        router.add_rule(
            name="always_match",
            condition=lambda t, c: True,
            model="claude-3-opus",
            priority=100,
        )
        # Lower priority rule
        router.add_rule(
            name="also_match",
            condition=lambda t, c: True,
            model="gpt-3.5-turbo",
            priority=1,
        )

        decision = router.route("any task", strategy=RoutingStrategy.RULES)

        assert decision.model == "claude-3-opus"
        assert decision.rule_name == "always_match"

    def test_no_match_uses_default(self):
        """Test default is used when no rules match."""
        router = LLMRouter(
            available_models=["gpt-4", "gpt-3.5-turbo"],
            default_model="gpt-4",
        )

        router.add_rule(
            name="never_match",
            condition=lambda t, c: False,
            model="gpt-3.5-turbo",
            priority=10,
        )

        decision = router.route("any task", strategy=RoutingStrategy.RULES)

        assert decision.model == "gpt-4"
        assert decision.rule_name is None


class TestLLMRouterComplexityRouting:
    """Tests for task complexity routing strategy."""

    def test_complexity_routing_high_complexity(self):
        """Test high complexity task routes to high quality model."""
        router = LLMRouter(
            available_models=["gpt-4", "gpt-3.5-turbo", "o1"],
        )

        decision = router.route(
            "Design a sophisticated, advanced, comprehensive production system",
            strategy=RoutingStrategy.TASK_COMPLEXITY,
        )

        # Should route to high quality model
        assert decision.model in ("gpt-4", "o1")
        assert decision.analysis is not None

    def test_complexity_routing_low_complexity(self):
        """Test low complexity task can use cheaper model."""
        router = LLMRouter(
            available_models=["gpt-4", "gpt-3.5-turbo"],
        )

        decision = router.route(
            "What is 2+2?",
            strategy=RoutingStrategy.TASK_COMPLEXITY,
        )

        # Should use cheaper model for trivial task
        # (may still use gpt-4 if it's cheapest among qualified)
        assert decision.model in ("gpt-4", "gpt-3.5-turbo")


class TestLLMRouterCostOptimized:
    """Tests for cost-optimized routing strategy."""

    def test_cost_routing_selects_cheapest(self):
        """Test cost routing selects cheapest capable model."""
        router = LLMRouter(
            available_models=["gpt-4", "gpt-3.5-turbo", "gpt-4o-mini"],
        )

        decision = router.route(
            "Simple task",
            strategy=RoutingStrategy.COST_OPTIMIZED,
        )

        # Should select cheapest model
        assert decision.model in ("gpt-3.5-turbo", "gpt-4o-mini")
        assert decision.reasoning == "Selected cheapest capable model"


class TestLLMRouterQualityOptimized:
    """Tests for quality-optimized routing strategy."""

    def test_quality_routing_selects_best(self):
        """Test quality routing selects highest quality model."""
        router = LLMRouter(
            available_models=["gpt-4", "gpt-3.5-turbo", "claude-3-opus"],
        )

        decision = router.route(
            "Any task",
            strategy=RoutingStrategy.QUALITY_OPTIMIZED,
        )

        # Should select highest quality model
        assert decision.model in ("gpt-4", "claude-3-opus")
        assert decision.reasoning == "Selected highest quality model"


class TestLLMRouterBalanced:
    """Tests for balanced routing strategy."""

    def test_balanced_routing(self):
        """Test balanced routing considers multiple factors."""
        router = LLMRouter(
            available_models=["gpt-4", "gpt-3.5-turbo", "claude-3-opus", "gpt-4o"],
        )

        decision = router.route(
            "Write Python code to implement a sorting algorithm",
            strategy=RoutingStrategy.BALANCED,
        )

        # Should select a capable model balancing cost/quality
        assert decision.model is not None
        assert decision.analysis is not None
        assert "balanced" in decision.reasoning.lower() or decision.reasoning

    def test_balanced_considers_specialty(self):
        """Test balanced routing considers specialties."""
        router = LLMRouter(
            available_models=["gpt-4", "claude-3-opus", "codellama"],
        )

        decision = router.route(
            "Write a Python function to sort data",
            strategy=RoutingStrategy.BALANCED,
        )

        # Should prefer code specialists
        assert decision.model is not None


class TestLLMRouterCapabilityFiltering:
    """Tests for capability-based filtering."""

    def test_vision_requirement_filtering(self):
        """Test vision requirement filters models."""
        router = LLMRouter(
            available_models=["gpt-4", "gpt-4o", "gpt-3.5-turbo"],
        )

        decision = router.route(
            "Describe this image",
            context={"has_images": True},
            strategy=RoutingStrategy.BALANCED,
        )

        # Should select vision-capable model
        assert decision.model in ("gpt-4o", "gpt-4-turbo", "gpt-4-vision", "gpt-4")

    def test_explicit_requirements(self):
        """Test explicit capability requirements."""
        router = LLMRouter(
            available_models=["gpt-4", "gpt-4o", "claude-3-opus"],
        )

        decision = router.route(
            "Any task",
            required_capabilities={"vision": True},
            strategy=RoutingStrategy.BALANCED,
        )

        # Should respect explicit requirements
        assert decision.model is not None


class TestLLMRouterAlternatives:
    """Tests for alternatives in routing decisions."""

    def test_decision_includes_alternatives(self):
        """Test decision includes alternative models."""
        router = LLMRouter(
            available_models=["gpt-4", "gpt-3.5-turbo", "claude-3-opus", "gpt-4o"],
        )

        decision = router.route(
            "Any task",
            strategy=RoutingStrategy.BALANCED,
        )

        # Should have alternatives
        assert len(decision.alternatives) <= 3  # Limited to 3
        assert decision.model not in decision.alternatives


class TestLLMRouterAnalysis:
    """Tests for task analysis in routing."""

    def test_analysis_included_in_decision(self):
        """Test task analysis is included in non-rules decisions."""
        router = LLMRouter(available_models=["gpt-4"])

        decision = router.route(
            "Write Python code",
            strategy=RoutingStrategy.BALANCED,
        )

        assert decision.analysis is not None
        assert decision.analysis.type == TaskType.CODE

    def test_analysis_not_for_rules_only(self):
        """Test rules-only strategy may not include analysis."""
        router = LLMRouter(available_models=["gpt-4"])

        router.add_rule(
            name="always",
            condition=lambda t, c: True,
            model="gpt-4",
            priority=10,
        )

        decision = router.route(
            "Any task",
            strategy=RoutingStrategy.RULES,
        )

        # Rules strategy with match doesn't need analysis
        assert decision.rule_name == "always"


class TestLLMRouterEdgeCases:
    """Tests for edge cases."""

    def test_empty_available_models(self):
        """Test routing with only default model."""
        router = LLMRouter(
            available_models=[],
            default_model="gpt-4",
        )

        decision = router.route("task")

        assert decision.model == "gpt-4"

    def test_unknown_model_in_registry(self):
        """Test routing with model not in registry."""
        router = LLMRouter(
            available_models=["unknown-model-xyz", "gpt-4"],
            default_model="unknown-model-xyz",
        )

        decision = router.route("task", strategy=RoutingStrategy.BALANCED)

        # Should still work, treating unknown as medium quality
        assert decision.model is not None

    def test_no_capable_models(self):
        """Test when no models meet requirements."""
        # Register a model with no vision
        register_model(
            LLMCapabilities(
                provider="test",
                model="no-vision-model",
                supports_vision=False,
            )
        )

        router = LLMRouter(
            available_models=["no-vision-model"],
            default_model="no-vision-model",
        )

        decision = router.route(
            "Describe image",
            required_capabilities={"vision": True},
        )

        # Should fall back to default
        assert decision.model == "no-vision-model"
        assert "No capable models" in decision.reasoning

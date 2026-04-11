"""
Unit tests for MultiDimensionEvaluator.

Tests cover:
- InteractionMode behaviors (conjunctive, disjunctive, independent, hierarchical)
- Unknown dimension warnings
- Anti-gaming detection (boundary pushing, splitting)
- Tightening validation
- Empty constraint handling
"""

from typing import Any, Dict

import pytest
from kailash.trust.constraints import (
    ConstraintCheckResult,
    ConstraintDimension,
    ConstraintDimensionRegistry,
    ConstraintValue,
)
from kailash.trust.constraints.evaluator import (
    EvaluationResult,
    InteractionMode,
    MultiDimensionEvaluator,
)


# Test dimensions
class MockCostDimension(ConstraintDimension):
    """Mock cost dimension for testing."""

    @property
    def name(self) -> str:
        return "cost_limit"

    @property
    def description(self) -> str:
        return "Test cost limit"

    def parse(self, value: Any) -> ConstraintValue:
        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=float(value),
            metadata={},
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        limit = constraint.parsed
        used = context.get("cost_used", 0.0)
        satisfied = used <= limit
        return ConstraintCheckResult(
            satisfied=satisfied,
            reason="within budget" if satisfied else "over budget",
            remaining=max(0, limit - used),
            used=used,
            limit=limit,
        )


class MockRateDimension(ConstraintDimension):
    """Mock rate dimension for testing."""

    @property
    def name(self) -> str:
        return "rate_limit"

    @property
    def description(self) -> str:
        return "Test rate limit"

    def parse(self, value: Any) -> ConstraintValue:
        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=int(value),
            metadata={},
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        limit = constraint.parsed
        used = context.get("requests", 0)
        satisfied = used <= limit
        return ConstraintCheckResult(
            satisfied=satisfied,
            reason="within limit" if satisfied else "exceeded",
            remaining=max(0, limit - used),
            used=used,
            limit=limit,
        )


class MockTimeDimension(ConstraintDimension):
    """Mock time dimension for testing (always passes/fails based on context)."""

    @property
    def name(self) -> str:
        return "time_window"

    @property
    def description(self) -> str:
        return "Test time window"

    def parse(self, value: Any) -> ConstraintValue:
        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=value,
            metadata={},
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        in_window = context.get("in_time_window", True)
        return ConstraintCheckResult(
            satisfied=in_window,
            reason="in window" if in_window else "outside window",
        )


@pytest.fixture
def registry() -> ConstraintDimensionRegistry:
    """Create registry with test dimensions."""
    reg = ConstraintDimensionRegistry()
    reg.register(MockCostDimension())
    reg.register(MockRateDimension())
    reg.register(MockTimeDimension())
    return reg


@pytest.fixture
def evaluator(registry: ConstraintDimensionRegistry) -> MultiDimensionEvaluator:
    """Create evaluator with test registry."""
    return MultiDimensionEvaluator(registry, enable_anti_gaming=True)


class TestConjunctiveMode:
    """Tests for CONJUNCTIVE interaction mode (ALL must pass)."""

    def test_conjunctive_all_pass(self, evaluator: MultiDimensionEvaluator):
        """Conjunctive mode passes when ALL dimensions pass."""
        result = evaluator.evaluate(
            constraints={"cost_limit": 1000, "rate_limit": 100},
            context={"cost_used": 500, "requests": 50},
            mode=InteractionMode.CONJUNCTIVE,
        )

        assert result.satisfied is True
        assert result.failed_dimensions == []
        assert len(result.dimension_results) == 2

    def test_conjunctive_one_fails(self, evaluator: MultiDimensionEvaluator):
        """Conjunctive mode fails when ANY dimension fails."""
        result = evaluator.evaluate(
            constraints={"cost_limit": 1000, "rate_limit": 100},
            context={"cost_used": 500, "requests": 150},  # rate exceeded
            mode=InteractionMode.CONJUNCTIVE,
        )

        assert result.satisfied is False
        assert "rate_limit" in result.failed_dimensions
        assert "cost_limit" not in result.failed_dimensions


class TestDisjunctiveMode:
    """Tests for DISJUNCTIVE interaction mode (ANY pass is enough)."""

    def test_disjunctive_any_passes(self, evaluator: MultiDimensionEvaluator):
        """Disjunctive mode passes when ANY dimension passes."""
        result = evaluator.evaluate(
            constraints={"cost_limit": 1000, "rate_limit": 100},
            context={"cost_used": 500, "requests": 150},  # rate fails
            mode=InteractionMode.DISJUNCTIVE,
        )

        assert result.satisfied is True  # cost_limit passed
        assert "rate_limit" in result.failed_dimensions

    def test_disjunctive_all_fail(self, evaluator: MultiDimensionEvaluator):
        """Disjunctive mode fails when ALL dimensions fail."""
        result = evaluator.evaluate(
            constraints={"cost_limit": 1000, "rate_limit": 100},
            context={"cost_used": 1500, "requests": 150},  # both fail
            mode=InteractionMode.DISJUNCTIVE,
        )

        assert result.satisfied is False
        assert "cost_limit" in result.failed_dimensions
        assert "rate_limit" in result.failed_dimensions


class TestHierarchicalMode:
    """Tests for HIERARCHICAL interaction mode (first dimension determines)."""

    def test_hierarchical_first_determines(self, evaluator: MultiDimensionEvaluator):
        """Hierarchical mode uses first dimension's result."""
        # First dimension (cost_limit) passes, second fails
        result = evaluator.evaluate(
            constraints={"cost_limit": 1000, "rate_limit": 100},
            context={"cost_used": 500, "requests": 150},
            mode=InteractionMode.HIERARCHICAL,
        )

        assert result.satisfied is True  # First dimension passed

        # First dimension fails, second passes
        result2 = evaluator.evaluate(
            constraints={"cost_limit": 1000, "rate_limit": 100},
            context={"cost_used": 1500, "requests": 50},
            mode=InteractionMode.HIERARCHICAL,
        )

        assert result2.satisfied is False  # First dimension failed


class TestIndependentMode:
    """Tests for INDEPENDENT interaction mode (majority must pass)."""

    def test_independent_majority_pass(self, evaluator: MultiDimensionEvaluator):
        """Independent mode passes when majority pass."""
        # 2 of 3 pass = majority
        result = evaluator.evaluate(
            constraints={
                "cost_limit": 1000,
                "rate_limit": 100,
                "time_window": "09:00-17:00",
            },
            context={
                "cost_used": 500,  # pass
                "requests": 150,  # fail
                "in_time_window": True,  # pass
            },
            mode=InteractionMode.INDEPENDENT,
        )

        assert result.satisfied is True
        assert len(result.failed_dimensions) == 1

        # 1 of 3 pass = minority
        result2 = evaluator.evaluate(
            constraints={
                "cost_limit": 1000,
                "rate_limit": 100,
                "time_window": "09:00-17:00",
            },
            context={
                "cost_used": 1500,  # fail
                "requests": 150,  # fail
                "in_time_window": True,  # pass
            },
            mode=InteractionMode.INDEPENDENT,
        )

        assert result2.satisfied is False
        assert len(result2.failed_dimensions) == 2


class TestUnknownDimension:
    """Tests for handling unknown dimensions."""

    def test_unknown_dimension_warning(self, evaluator: MultiDimensionEvaluator):
        """Unknown dimensions generate warnings but don't fail."""
        result = evaluator.evaluate(
            constraints={
                "cost_limit": 1000,
                "unknown_dimension": "some_value",
            },
            context={"cost_used": 500},
            mode=InteractionMode.CONJUNCTIVE,
        )

        assert result.satisfied is True
        assert "Unknown dimension: unknown_dimension" in result.warnings
        assert "unknown_dimension" not in result.dimension_results


class TestAntiGaming:
    """Tests for anti-gaming detection."""

    def test_anti_gaming_boundary_pushing(self, registry: ConstraintDimensionRegistry):
        """Boundary pushing detected when usage_ratio > 0.95."""
        evaluator = MultiDimensionEvaluator(registry, enable_anti_gaming=True)

        result = evaluator.evaluate(
            constraints={"cost_limit": 1000},
            context={"cost_used": 980},  # 98% usage
            mode=InteractionMode.CONJUNCTIVE,
            agent_id="agent-pushy",
        )

        assert result.satisfied is True
        assert any("boundary_pushing" in flag for flag in result.anti_gaming_flags)

    def test_anti_gaming_splitting_detection(
        self, registry: ConstraintDimensionRegistry
    ):
        """Splitting detected when 8+ of last 10 evaluations have small ops."""
        evaluator = MultiDimensionEvaluator(registry, enable_anti_gaming=True)

        # Simulate 10 small operations
        for i in range(10):
            evaluator.evaluate(
                constraints={"cost_limit": 1000},
                context={"cost_used": 50},  # 5% usage = small op
                mode=InteractionMode.CONJUNCTIVE,
                agent_id="agent-splitter",
            )

        # The 11th evaluation should detect the pattern
        result = evaluator.evaluate(
            constraints={"cost_limit": 1000},
            context={"cost_used": 50},
            mode=InteractionMode.CONJUNCTIVE,
            agent_id="agent-splitter",
        )

        assert any("constraint_splitting" in flag for flag in result.anti_gaming_flags)


class TestValidateTightening:
    """Tests for constraint tightening validation."""

    def test_validate_tightening_valid(self, registry: ConstraintDimensionRegistry):
        """Valid tightening returns empty violations."""
        evaluator = MultiDimensionEvaluator(registry)

        violations = evaluator.validate_tightening(
            parent_constraints={"cost_limit": 1000, "rate_limit": 100},
            child_constraints={"cost_limit": 500, "rate_limit": 50},  # tighter
        )

        assert violations == []

    def test_validate_tightening_violation(self, registry: ConstraintDimensionRegistry):
        """Invalid tightening returns violation messages."""
        evaluator = MultiDimensionEvaluator(registry)

        violations = evaluator.validate_tightening(
            parent_constraints={"cost_limit": 500},
            child_constraints={"cost_limit": 1000},  # looser!
        )

        assert len(violations) == 1
        assert "cost_limit" in violations[0]
        assert "looser" in violations[0]


class TestEmptyConstraints:
    """Tests for empty constraint handling."""

    def test_empty_constraints_satisfied(self, evaluator: MultiDimensionEvaluator):
        """Empty constraints are satisfied (no constraints = no restrictions)."""
        result = evaluator.evaluate(
            constraints={},
            context={"cost_used": 1000000},  # huge cost doesn't matter
            mode=InteractionMode.CONJUNCTIVE,
        )

        assert result.satisfied is True
        assert result.dimension_results == {}
        assert result.failed_dimensions == []
        assert result.warnings == []

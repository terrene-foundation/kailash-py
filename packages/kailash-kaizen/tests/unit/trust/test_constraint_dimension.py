"""
Unit tests for EATP Constraint Dimension Protocol and Registry.

Tests cover:
- ConstraintValue creation and fields
- ConstraintCheckResult creation and fields
- Custom ConstraintDimension subclass implementation
- ConstraintDimensionRegistry management and approval workflow
"""

from typing import Any, Dict, List

import pytest
from kaizen.trust.constraints.dimension import (
    ConstraintCheckResult,
    ConstraintDimension,
    ConstraintDimensionRegistry,
    ConstraintValue,
)


class TestConstraintValue:
    """Tests for ConstraintValue dataclass."""

    def test_constraint_value_creation(self):
        """ConstraintValue can be created with all fields."""
        value = ConstraintValue(
            dimension="cost_limit",
            raw_value="1000",
            parsed=1000.0,
            metadata={"currency": "USD"},
        )

        assert value.dimension == "cost_limit"
        assert value.raw_value == "1000"
        assert value.parsed == 1000.0
        assert value.metadata == {"currency": "USD"}

    def test_constraint_value_default_metadata(self):
        """ConstraintValue has empty dict as default metadata."""
        value = ConstraintValue(
            dimension="rate_limit",
            raw_value=100,
            parsed=100,
        )

        assert value.metadata == {}

    def test_constraint_value_with_complex_parsed(self):
        """ConstraintValue can hold complex parsed values."""
        parsed_window = {"start": "09:00", "end": "17:00"}
        value = ConstraintValue(
            dimension="time_window",
            raw_value="09:00-17:00",
            parsed=parsed_window,
            metadata={"timezone": "UTC"},
        )

        assert value.parsed == {"start": "09:00", "end": "17:00"}


class TestConstraintCheckResult:
    """Tests for ConstraintCheckResult dataclass."""

    def test_constraint_check_result_satisfied(self):
        """ConstraintCheckResult with satisfied constraint."""
        result = ConstraintCheckResult(
            satisfied=True,
            reason="within budget",
            remaining=500.0,
            used=500.0,
            limit=1000.0,
        )

        assert result.satisfied is True
        assert result.reason == "within budget"
        assert result.remaining == 500.0
        assert result.used == 500.0
        assert result.limit == 1000.0

    def test_constraint_check_result_not_satisfied(self):
        """ConstraintCheckResult with violated constraint."""
        result = ConstraintCheckResult(
            satisfied=False,
            reason="exceeded budget by 200",
            remaining=0.0,
            used=1200.0,
            limit=1000.0,
        )

        assert result.satisfied is False
        assert result.reason == "exceeded budget by 200"

    def test_constraint_check_result_minimal(self):
        """ConstraintCheckResult with only required fields."""
        result = ConstraintCheckResult(
            satisfied=True,
            reason="OK",
        )

        assert result.satisfied is True
        assert result.reason == "OK"
        assert result.remaining is None
        assert result.used is None
        assert result.limit is None


# Custom dimension for testing
class TokenLimitDimension(ConstraintDimension):
    """Test dimension for token limits."""

    @property
    def name(self) -> str:
        return "token_limit"

    @property
    def description(self) -> str:
        return "Maximum tokens per request"

    @property
    def version(self) -> str:
        return "2.0.0"

    @property
    def requires_audit(self) -> bool:
        return True

    def parse(self, value: Any) -> ConstraintValue:
        parsed = int(value)
        if parsed < 0:
            raise ValueError("Token limit must be non-negative")
        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=parsed,
            metadata={"type": "tokens"},
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        limit = constraint.parsed
        used = context.get("tokens_used", 0)
        remaining = max(0, limit - used)
        satisfied = used <= limit

        return ConstraintCheckResult(
            satisfied=satisfied,
            reason="within limit" if satisfied else f"exceeded by {used - limit}",
            remaining=float(remaining),
            used=float(used),
            limit=float(limit),
        )


class TestConstraintDimension:
    """Tests for custom ConstraintDimension subclass."""

    @pytest.fixture
    def dimension(self) -> TokenLimitDimension:
        """Create a test TokenLimitDimension."""
        return TokenLimitDimension()

    def test_dimension_properties(self, dimension: TokenLimitDimension):
        """Dimension has correct property values."""
        assert dimension.name == "token_limit"
        assert dimension.description == "Maximum tokens per request"
        assert dimension.version == "2.0.0"
        assert dimension.requires_audit is True

    def test_parse_returns_correct_constraint_value(
        self, dimension: TokenLimitDimension
    ):
        """parse() returns correct ConstraintValue."""
        value = dimension.parse(1000)

        assert value.dimension == "token_limit"
        assert value.raw_value == 1000
        assert value.parsed == 1000
        assert value.metadata == {"type": "tokens"}

    def test_parse_string_value(self, dimension: TokenLimitDimension):
        """parse() handles string input."""
        value = dimension.parse("500")

        assert value.parsed == 500

    def test_parse_invalid_value(self, dimension: TokenLimitDimension):
        """parse() raises ValueError for invalid input."""
        with pytest.raises(ValueError, match="must be non-negative"):
            dimension.parse(-100)

    def test_check_satisfied_constraint(self, dimension: TokenLimitDimension):
        """check() returns satisfied for within-limit usage."""
        constraint = dimension.parse(1000)
        context = {"tokens_used": 500}

        result = dimension.check(constraint, context)

        assert result.satisfied is True
        assert result.reason == "within limit"
        assert result.remaining == 500.0
        assert result.used == 500.0
        assert result.limit == 1000.0

    def test_check_exact_limit(self, dimension: TokenLimitDimension):
        """check() returns satisfied when exactly at limit."""
        constraint = dimension.parse(1000)
        context = {"tokens_used": 1000}

        result = dimension.check(constraint, context)

        assert result.satisfied is True
        assert result.remaining == 0.0

    def test_check_exceeded_constraint(self, dimension: TokenLimitDimension):
        """check() returns not satisfied for exceeded usage."""
        constraint = dimension.parse(1000)
        context = {"tokens_used": 1200}

        result = dimension.check(constraint, context)

        assert result.satisfied is False
        assert "exceeded by 200" in result.reason
        assert result.remaining == 0.0
        assert result.used == 1200.0

    def test_check_missing_context_key(self, dimension: TokenLimitDimension):
        """check() handles missing context key (defaults to 0)."""
        constraint = dimension.parse(1000)
        context = {}

        result = dimension.check(constraint, context)

        assert result.satisfied is True
        assert result.used == 0.0

    def test_validate_tightening_valid(self, dimension: TokenLimitDimension):
        """validate_tightening() returns True for valid tightening."""
        parent = dimension.parse(1000)
        child = dimension.parse(500)

        assert dimension.validate_tightening(parent, child) is True

    def test_validate_tightening_equal(self, dimension: TokenLimitDimension):
        """validate_tightening() returns True for equal constraints."""
        parent = dimension.parse(1000)
        child = dimension.parse(1000)

        assert dimension.validate_tightening(parent, child) is True

    def test_validate_tightening_invalid(self, dimension: TokenLimitDimension):
        """validate_tightening() returns False for loosening."""
        parent = dimension.parse(500)
        child = dimension.parse(1000)

        assert dimension.validate_tightening(parent, child) is False

    def test_compose_picks_tightest(self, dimension: TokenLimitDimension):
        """compose() picks the tightest constraint."""
        constraints = [
            dimension.parse(1000),
            dimension.parse(500),
            dimension.parse(750),
        ]

        composed = dimension.compose(constraints)

        assert composed.parsed == 500
        assert composed.metadata.get("composed") is True
        assert composed.metadata.get("source_count") == 3

    def test_compose_single_constraint(self, dimension: TokenLimitDimension):
        """compose() returns single constraint unchanged."""
        constraint = dimension.parse(1000)

        composed = dimension.compose([constraint])

        assert composed is constraint

    def test_compose_empty_raises(self, dimension: TokenLimitDimension):
        """compose() raises ValueError for empty list."""
        with pytest.raises(ValueError, match="Cannot compose empty"):
            dimension.compose([])


class TestConstraintDimensionRegistry:
    """Tests for ConstraintDimensionRegistry."""

    @pytest.fixture
    def registry(self) -> ConstraintDimensionRegistry:
        """Create a fresh registry."""
        return ConstraintDimensionRegistry()

    @pytest.fixture
    def unreviewed_registry(self) -> ConstraintDimensionRegistry:
        """Create a registry that allows unreviewed dimensions."""
        return ConstraintDimensionRegistry(allow_unreviewed=True)

    def test_register_and_get(self, registry: ConstraintDimensionRegistry):
        """Register dimension and retrieve it."""
        dimension = TokenLimitDimension()
        registry.register(dimension)

        retrieved = registry.get("token_limit")

        assert retrieved is dimension

    def test_has_returns_true_for_registered(
        self, registry: ConstraintDimensionRegistry
    ):
        """has() returns True for registered dimension."""
        registry.register(TokenLimitDimension())

        assert registry.has("token_limit") is True

    def test_has_returns_false_for_unknown(self, registry: ConstraintDimensionRegistry):
        """has() returns False for unknown dimension."""
        assert registry.has("unknown_dimension") is False

    def test_get_returns_none_for_unknown(self, registry: ConstraintDimensionRegistry):
        """get() returns None for unknown dimension."""
        assert registry.get("unknown_dimension") is None

    def test_all_returns_all_registered(self, registry: ConstraintDimensionRegistry):
        """all() returns all registered dimensions."""
        dim1 = TokenLimitDimension()

        # Create second dimension with different name
        class CostDimension(ConstraintDimension):
            @property
            def name(self) -> str:
                return "cost_limit"

            @property
            def description(self) -> str:
                return "Cost limit"

            def parse(self, value: Any) -> ConstraintValue:
                return ConstraintValue(
                    dimension=self.name, raw_value=value, parsed=float(value)
                )

            def check(
                self, constraint: ConstraintValue, context: Dict[str, Any]
            ) -> ConstraintCheckResult:
                return ConstraintCheckResult(satisfied=True, reason="OK")

        dim2 = CostDimension()

        registry.register(dim1)
        registry.register(dim2)

        all_dims = registry.all()

        assert len(all_dims) == 2
        names = {name for name, _ in all_dims}
        assert names == {"token_limit", "cost_limit"}

    def test_register_duplicate_raises(self, registry: ConstraintDimensionRegistry):
        """register() raises ValueError for duplicate dimension."""
        registry.register(TokenLimitDimension())

        with pytest.raises(ValueError, match="already registered"):
            registry.register(TokenLimitDimension())

    def test_pending_review_dimension_not_returned(
        self, registry: ConstraintDimensionRegistry
    ):
        """Dimension pending review is NOT returned by get()."""
        registry.register(TokenLimitDimension(), requires_review=True)

        assert registry.get("token_limit") is None

    def test_pending_review_dimension_returned_when_allowed(
        self, unreviewed_registry: ConstraintDimensionRegistry
    ):
        """Dimension pending review IS returned when allow_unreviewed=True."""
        dimension = TokenLimitDimension()
        unreviewed_registry.register(dimension, requires_review=True)

        retrieved = unreviewed_registry.get("token_limit")

        assert retrieved is dimension

    def test_pending_review_list(self, registry: ConstraintDimensionRegistry):
        """pending_review() returns dimensions awaiting approval."""
        registry.register(TokenLimitDimension(), requires_review=True)

        pending = registry.pending_review()

        assert "token_limit" in pending

    def test_approve_dimension(self, registry: ConstraintDimensionRegistry):
        """approve_dimension() moves from pending to approved."""
        dimension = TokenLimitDimension()
        registry.register(dimension, requires_review=True)

        # Before approval
        assert registry.get("token_limit") is None
        assert "token_limit" in registry.pending_review()

        # Approve
        registry.approve_dimension("token_limit", reviewer="security-team")

        # After approval
        assert registry.get("token_limit") is dimension
        assert "token_limit" not in registry.pending_review()

    def test_approve_unknown_dimension_raises(
        self, registry: ConstraintDimensionRegistry
    ):
        """approve_dimension() raises for unknown dimension."""
        with pytest.raises(ValueError, match="not found"):
            registry.approve_dimension("unknown", reviewer="reviewer")

    def test_builtin_dimensions_auto_approved(
        self, registry: ConstraintDimensionRegistry
    ):
        """Built-in dimensions are auto-approved."""

        # Create a dimension with a built-in name
        class CostLimitDimension(ConstraintDimension):
            @property
            def name(self) -> str:
                return "cost_limit"

            @property
            def description(self) -> str:
                return "Cost limit"

            def parse(self, value: Any) -> ConstraintValue:
                return ConstraintValue(
                    dimension=self.name, raw_value=value, parsed=float(value)
                )

            def check(
                self, constraint: ConstraintValue, context: Dict[str, Any]
            ) -> ConstraintCheckResult:
                return ConstraintCheckResult(satisfied=True, reason="OK")

        dimension = CostLimitDimension()
        registry.register(dimension, requires_review=True)  # Even with requires_review

        # Built-in should be auto-approved
        assert "cost_limit" not in registry.pending_review()
        assert registry.get("cost_limit") is dimension

    def test_parse_constraint_delegates_to_dimension(
        self, registry: ConstraintDimensionRegistry
    ):
        """parse_constraint() delegates to dimension's parse()."""
        registry.register(TokenLimitDimension())

        result = registry.parse_constraint("token_limit", 1000)

        assert result is not None
        assert result.dimension == "token_limit"
        assert result.parsed == 1000

    def test_parse_constraint_returns_none_for_unknown(
        self, registry: ConstraintDimensionRegistry
    ):
        """parse_constraint() returns None for unknown dimension."""
        result = registry.parse_constraint("unknown_dimension", 100)

        assert result is None

    def test_parse_constraint_returns_none_for_pending(
        self, registry: ConstraintDimensionRegistry
    ):
        """parse_constraint() returns None for pending review dimension."""
        registry.register(TokenLimitDimension(), requires_review=True)

        result = registry.parse_constraint("token_limit", 1000)

        assert result is None

    def test_builtin_dimensions_set(self):
        """BUILTIN_DIMENSIONS contains expected dimensions."""
        expected = {
            "cost_limit",
            "time_window",
            "resources",
            "rate_limit",
            "geo_restrictions",
            "budget_limit",
            "max_delegation_depth",
            "allowed_actions",
        }

        assert ConstraintDimensionRegistry.BUILTIN_DIMENSIONS == expected

    def test_has_still_true_for_pending(self, registry: ConstraintDimensionRegistry):
        """has() returns True even for pending review dimensions."""
        registry.register(TokenLimitDimension(), requires_review=True)

        assert registry.has("token_limit") is True

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Constraint Dimension Protocol and Registry for EATP.

This module provides the extensible constraint dimension system that enables
pluggable constraint types for the Enterprise Agent Trust Protocol (EATP).

Key Components:
- ConstraintValue: Parsed representation of a constraint value
- ConstraintCheckResult: Result of checking a constraint against context
- ConstraintDimension: Abstract base class for constraint dimension plugins
- ConstraintDimensionRegistry: Central registry for dimension management

The constraint dimension system follows a plugin architecture where custom
constraint types can be registered and evaluated uniformly. Built-in
dimensions are auto-approved, while custom dimensions require review.

Example:
    from eatp.constraints import (
        ConstraintDimension,
        ConstraintDimensionRegistry,
        ConstraintValue,
        ConstraintCheckResult,
    )

    class TokenLimitDimension(ConstraintDimension):
        @property
        def name(self) -> str:
            return "token_limit"

        @property
        def description(self) -> str:
            return "Maximum tokens per request"

        def parse(self, value: Any) -> ConstraintValue:
            parsed = int(value)
            return ConstraintValue(
                dimension=self.name,
                raw_value=value,
                parsed=parsed,
                metadata={}
            )

        def check(
            self,
            constraint: ConstraintValue,
            context: Dict[str, Any]
        ) -> ConstraintCheckResult:
            limit = constraint.parsed
            used = context.get("tokens_used", 0)
            return ConstraintCheckResult(
                satisfied=used <= limit,
                reason="within limit" if used <= limit else "exceeded",
                remaining=max(0, limit - used),
                used=used,
                limit=limit,
            )

    # Register and use
    registry = ConstraintDimensionRegistry()
    registry.register(TokenLimitDimension())
    dim = registry.get("token_limit")
    value = dim.parse(1000)
    result = dim.check(value, {"tokens_used": 500})

Author: Kaizen Framework Team
Created: 2026-02-08
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ConstraintValue:
    """
    Parsed representation of a constraint value.

    A ConstraintValue encapsulates both the raw input and parsed representation
    of a constraint, along with any metadata needed for evaluation.

    Attributes:
        dimension: Name of the constraint dimension (e.g., "cost_limit")
        raw_value: Original unparsed value as provided
        parsed: Parsed/normalized value for evaluation
        metadata: Additional metadata for constraint evaluation
    """

    dimension: str
    raw_value: Any
    parsed: Any
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConstraintCheckResult:
    """
    Result of checking a constraint against execution context.

    Contains both the boolean result and detailed information about
    the check for audit and debugging purposes.

    Attributes:
        satisfied: True if the constraint is satisfied
        reason: Human-readable explanation of the result
        remaining: Optional remaining budget/capacity (e.g., remaining tokens)
        used: Optional amount already used
        limit: Optional limit value from the constraint
    """

    satisfied: bool
    reason: str
    remaining: Optional[float] = None
    used: Optional[float] = None
    limit: Optional[float] = None


class ConstraintDimension(ABC):
    """
    Abstract base class for constraint dimension plugins.

    A constraint dimension defines how a particular type of constraint
    is parsed, validated, checked, and composed. Each dimension handles
    one aspect of constraint evaluation (e.g., cost limits, time windows).

    Subclasses must implement:
    - name: Unique identifier for this dimension
    - description: Human-readable description
    - parse(): Convert raw value to ConstraintValue
    - check(): Evaluate constraint against context

    Subclasses may override:
    - version: Dimension version (default: "1.0.0")
    - requires_audit: Whether operations need audit logging (default: False)
    - validate_tightening(): Verify child constraint is tighter than parent
    - compose(): Combine multiple constraints into most restrictive

    Example:
        class CostLimitDimension(ConstraintDimension):
            @property
            def name(self) -> str:
                return "cost_limit"

            @property
            def description(self) -> str:
                return "Maximum cost in cents"

            def parse(self, value: Any) -> ConstraintValue:
                return ConstraintValue(
                    dimension=self.name,
                    raw_value=value,
                    parsed=float(value),
                    metadata={}
                )

            def check(
                self,
                constraint: ConstraintValue,
                context: Dict[str, Any]
            ) -> ConstraintCheckResult:
                limit = constraint.parsed
                cost = context.get("cost", 0)
                return ConstraintCheckResult(
                    satisfied=cost <= limit,
                    reason="within budget" if cost <= limit else "over budget",
                    remaining=max(0, limit - cost),
                    used=cost,
                    limit=limit,
                )
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique identifier for this constraint dimension.

        Returns:
            Dimension name (e.g., "cost_limit", "time_window")
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Human-readable description of this constraint dimension.

        Returns:
            Description explaining what this dimension constrains
        """
        pass

    @property
    def version(self) -> str:
        """
        Version of this dimension implementation.

        Returns:
            Semantic version string (default: "1.0.0")
        """
        return "1.0.0"

    @property
    def requires_audit(self) -> bool:
        """
        Whether operations with this constraint require audit logging.

        Returns:
            True if audit required (default: False)
        """
        return False

    @abstractmethod
    def parse(self, value: Any) -> ConstraintValue:
        """
        Parse a raw constraint value into a ConstraintValue.

        This method should validate and normalize the input value,
        converting it to a form suitable for evaluation.

        Args:
            value: Raw constraint value from configuration or delegation

        Returns:
            Parsed ConstraintValue ready for evaluation

        Raises:
            ValueError: If value cannot be parsed or is invalid
        """
        pass

    @abstractmethod
    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        """
        Check if a constraint is satisfied given the execution context.

        Args:
            constraint: Parsed constraint value to check
            context: Execution context containing relevant values

        Returns:
            ConstraintCheckResult indicating if constraint is satisfied
        """
        pass

    def validate_tightening(
        self,
        parent: ConstraintValue,
        child: ConstraintValue,
    ) -> bool:
        """
        Validate that child constraint is tighter than or equal to parent.

        This is a fundamental EATP security property - delegations can only
        TIGHTEN constraints, never loosen them.

        Default implementation assumes numeric values where lower = tighter.
        Override for different semantics (e.g., set containment).

        Args:
            parent: Parent (delegator) constraint
            child: Child (delegatee) constraint

        Returns:
            True if child is valid tightening of parent
        """
        try:
            # Default: assume numeric where lower = tighter
            parent_val = float(parent.parsed)
            child_val = float(child.parsed)
            return child_val <= parent_val
        except (TypeError, ValueError):
            # Non-numeric: subclass should override
            logger.warning(
                f"validate_tightening not implemented for non-numeric "
                f"dimension {self.name}, returning False"
            )
            return False

    def compose(self, constraints: List[ConstraintValue]) -> ConstraintValue:
        """
        Compose multiple constraints into the most restrictive one.

        Used when combining constraints from multiple sources (e.g., multiple
        delegations in a chain). Default implementation picks the tightest
        numeric constraint.

        Args:
            constraints: List of constraints to compose

        Returns:
            Single ConstraintValue representing the composition

        Raises:
            ValueError: If constraints list is empty or cannot be composed
        """
        if not constraints:
            raise ValueError("Cannot compose empty constraints list")

        if len(constraints) == 1:
            return constraints[0]

        try:
            # Default: pick minimum (tightest) numeric value
            tightest = min(constraints, key=lambda c: float(c.parsed))
            return ConstraintValue(
                dimension=self.name,
                raw_value=tightest.raw_value,
                parsed=tightest.parsed,
                metadata={
                    "composed": True,
                    "source_count": len(constraints),
                },
            )
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"Cannot compose non-numeric constraints for dimension {self.name}: {e}"
            )


class ConstraintDimensionRegistry:
    """
    Central registry for constraint dimension plugins.

    Manages registration, approval, and retrieval of constraint dimensions.
    Built-in dimensions are auto-approved; custom dimensions require review
    before they can be used.

    Attributes:
        BUILTIN_DIMENSIONS: Set of built-in dimension names that are auto-approved

    Example:
        registry = ConstraintDimensionRegistry()

        # Register a custom dimension
        registry.register(MyCustomDimension(), requires_review=True)

        # Check if it's pending review
        assert "my_custom" in registry.pending_review()

        # Approve after security review
        registry.approve_dimension("my_custom", reviewer="security-team")

        # Now it can be retrieved
        dim = registry.get("my_custom")
    """

    BUILTIN_DIMENSIONS: Set[str] = {
        "cost_limit",
        "time_window",
        "resources",
        "rate_limit",
        "geo_restrictions",
        "budget_limit",
        "max_delegation_depth",
        "allowed_actions",
    }

    def __init__(self, allow_unreviewed: bool = False):
        """
        Initialize the constraint dimension registry.

        Args:
            allow_unreviewed: If True, allow retrieval of dimensions pending
                review (useful for testing). Default: False for security.
        """
        self._allow_unreviewed = allow_unreviewed
        self._dimensions: Dict[str, ConstraintDimension] = {}
        self._pending_review: Set[str] = set()
        self._reviewers: Dict[str, str] = {}

    def register(
        self,
        dimension: ConstraintDimension,
        requires_review: bool = False,
    ) -> None:
        """
        Register a constraint dimension.

        Built-in dimensions (in BUILTIN_DIMENSIONS) are auto-approved.
        Custom dimensions can optionally require security review before use.

        Args:
            dimension: The dimension instance to register
            requires_review: If True, dimension requires approval before use

        Raises:
            ValueError: If a dimension with this name is already registered
        """
        name = dimension.name

        if name in self._dimensions:
            raise ValueError(f"Dimension '{name}' is already registered")

        self._dimensions[name] = dimension

        # Built-in dimensions are auto-approved
        if name in self.BUILTIN_DIMENSIONS:
            logger.debug(f"Auto-approved built-in dimension: {name}")
        elif requires_review:
            self._pending_review.add(name)
            logger.info(f"Dimension '{name}' registered pending review")
        else:
            logger.debug(f"Dimension '{name}' registered (no review required)")

    def approve_dimension(self, name: str, reviewer: str) -> None:
        """
        Approve a dimension pending review.

        Args:
            name: Name of the dimension to approve
            reviewer: Identifier of the reviewer approving (for audit)

        Raises:
            ValueError: If dimension not found or not pending review
        """
        if name not in self._dimensions:
            raise ValueError(f"Dimension '{name}' not found")

        if name not in self._pending_review:
            logger.debug(f"Dimension '{name}' is already approved")
            return

        self._pending_review.remove(name)
        self._reviewers[name] = reviewer
        logger.info(f"Dimension '{name}' approved by {reviewer}")

    def get(self, name: str) -> Optional[ConstraintDimension]:
        """
        Retrieve a constraint dimension by name.

        Dimensions pending review are not returned unless allow_unreviewed
        was set to True during initialization.

        Args:
            name: Name of the dimension to retrieve

        Returns:
            The dimension if found and approved, None otherwise
        """
        if name not in self._dimensions:
            return None

        # Check if pending review
        if name in self._pending_review and not self._allow_unreviewed:
            logger.warning(f"Dimension '{name}' is pending review and cannot be used")
            return None

        return self._dimensions[name]

    def has(self, name: str) -> bool:
        """
        Check if a dimension is registered (regardless of review status).

        Args:
            name: Name of the dimension to check

        Returns:
            True if dimension is registered
        """
        return name in self._dimensions

    def all(self) -> List[Tuple[str, ConstraintDimension]]:
        """
        Get all registered dimensions.

        Returns:
            List of (name, dimension) tuples for all registered dimensions
        """
        return list(self._dimensions.items())

    def pending_review(self) -> List[str]:
        """
        Get list of dimensions pending security review.

        Returns:
            List of dimension names awaiting approval
        """
        return list(self._pending_review)

    def parse_constraint(
        self,
        dimension_name: str,
        value: Any,
    ) -> Optional[ConstraintValue]:
        """
        Parse a constraint value using the appropriate dimension.

        Convenience method that combines dimension lookup with parsing.

        Args:
            dimension_name: Name of the dimension to use for parsing
            value: Raw value to parse

        Returns:
            Parsed ConstraintValue, or None if dimension not found/approved
        """
        dimension = self.get(dimension_name)
        if dimension is None:
            return None

        return dimension.parse(value)

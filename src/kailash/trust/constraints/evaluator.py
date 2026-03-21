# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Multi-Dimension Constraint Evaluator for EATP.

This module provides the MultiDimensionEvaluator that orchestrates evaluation
of constraints across multiple dimensions with configurable interaction modes.

Key Components:
- InteractionMode: Enum defining how dimensions interact
- EvaluationResult: Result of multi-dimension evaluation
- MultiDimensionEvaluator: Main evaluator with anti-gaming detection

The evaluator supports four interaction modes:
- INDEPENDENT: Each dimension evaluated separately, majority must pass
- CONJUNCTIVE: ALL dimensions must pass (AND logic)
- DISJUNCTIVE: ANY dimension passing is sufficient (OR logic)
- HIERARCHICAL: First dimension determines result

Anti-gaming detection flags:
- Boundary pushing: usage_ratio > 0.95 for any dimension
- Constraint splitting: 8+ of last 10 evaluations have small ops (used/limit < 0.1)

Example:
    from kailash.trust.constraints import (
        ConstraintDimensionRegistry,
        MultiDimensionEvaluator,
        InteractionMode,
    )
    from kailash.trust.constraints.builtin import CostLimitDimension

    registry = ConstraintDimensionRegistry()
    registry.register(CostLimitDimension())

    evaluator = MultiDimensionEvaluator(registry)
    result = evaluator.evaluate(
        constraints={"cost_limit": 1000},
        context={"cost_used": 500},
        mode=InteractionMode.CONJUNCTIVE,
    )

    if result.satisfied:
        print("All constraints satisfied")
    else:
        print(f"Failed dimensions: {result.failed_dimensions}")

Author: Kaizen Framework Team
Created: 2026-02-08
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from kailash.trust.constraints.dimension import (
    ConstraintCheckResult,
    ConstraintDimensionRegistry,
    ConstraintValue,
)

logger = logging.getLogger(__name__)


class InteractionMode(str, Enum):
    """
    Defines how multiple constraint dimensions interact during evaluation.

    Attributes:
        INDEPENDENT: Each dimension evaluated separately, majority must pass
        CONJUNCTIVE: ALL dimensions must pass (AND logic)
        DISJUNCTIVE: ANY dimension passing is sufficient (OR logic)
        HIERARCHICAL: First dimension determines result (priority-based)
    """

    INDEPENDENT = "independent"
    CONJUNCTIVE = "conjunctive"
    DISJUNCTIVE = "disjunctive"
    HIERARCHICAL = "hierarchical"


@dataclass
class EvaluationResult:
    """
    Result of multi-dimension constraint evaluation.

    Contains comprehensive information about the evaluation including
    individual dimension results, interaction mode used, and any
    anti-gaming flags detected.

    Attributes:
        satisfied: True if overall evaluation passed
        dimension_results: Map of dimension name to individual result
        interaction_mode: Mode used for evaluation
        failed_dimensions: List of dimension names that failed
        warnings: Human-readable warnings (e.g., unknown dimensions)
        anti_gaming_flags: Detected anti-gaming patterns
    """

    satisfied: bool
    dimension_results: Dict[str, ConstraintCheckResult]
    interaction_mode: InteractionMode
    failed_dimensions: List[str]
    warnings: List[str] = field(default_factory=list)
    anti_gaming_flags: List[str] = field(default_factory=list)


class MultiDimensionEvaluator:
    """
    Evaluates constraints across multiple dimensions.

    The evaluator orchestrates constraint checking across registered
    dimensions, applying the specified interaction mode to determine
    overall satisfaction. It also includes anti-gaming detection to
    identify potential constraint manipulation patterns.

    Attributes:
        _registry: ConstraintDimensionRegistry for dimension lookup
        _enable_anti_gaming: Whether to run anti-gaming detection
        _evaluation_history: History of evaluations per agent for pattern detection

    Example:
        evaluator = MultiDimensionEvaluator(registry, enable_anti_gaming=True)

        result = evaluator.evaluate(
            constraints={"cost_limit": 1000, "rate_limit": 100},
            context={"cost_used": 800, "requests_in_period": 50},
            mode=InteractionMode.CONJUNCTIVE,
            agent_id="agent-123"
        )

        if result.anti_gaming_flags:
            logger.warning(f"Potential gaming detected: {result.anti_gaming_flags}")
    """

    def __init__(
        self,
        registry: ConstraintDimensionRegistry,
        enable_anti_gaming: bool = True,
    ):
        """
        Initialize the multi-dimension evaluator.

        Args:
            registry: Registry containing constraint dimension plugins
            enable_anti_gaming: If True, run anti-gaming detection on evaluations
        """
        self._registry = registry
        self._enable_anti_gaming = enable_anti_gaming
        self._evaluation_history: Dict[str, List[EvaluationResult]] = defaultdict(list)

    def evaluate(
        self,
        constraints: Dict[str, Any],
        context: Dict[str, Any],
        mode: InteractionMode = InteractionMode.CONJUNCTIVE,
        agent_id: Optional[str] = None,
    ) -> EvaluationResult:
        """
        Evaluate constraints across all specified dimensions.

        Args:
            constraints: Map of dimension name to constraint value
            context: Execution context containing values to check
            mode: Interaction mode for combining dimension results
            agent_id: Optional agent ID for anti-gaming tracking

        Returns:
            EvaluationResult with overall satisfaction and details
        """
        dimension_results: Dict[str, ConstraintCheckResult] = {}
        failed_dimensions: List[str] = []
        warnings: List[str] = []

        # Handle empty constraints - considered satisfied
        if not constraints:
            return EvaluationResult(
                satisfied=True,
                dimension_results={},
                interaction_mode=mode,
                failed_dimensions=[],
                warnings=[],
                anti_gaming_flags=[],
            )

        # Evaluate each dimension
        for dimension_name, constraint_value in constraints.items():
            dimension = self._registry.get(dimension_name)

            if dimension is None:
                warnings.append(f"Unknown dimension: {dimension_name}")
                logger.warning(f"Unknown constraint dimension: {dimension_name}")
                continue

            try:
                # Parse the constraint value
                parsed = dimension.parse(constraint_value)

                # Check against context
                result = dimension.check(parsed, context)
                dimension_results[dimension_name] = result

                if not result.satisfied:
                    failed_dimensions.append(dimension_name)

            except Exception as e:
                logger.error(f"Error evaluating dimension {dimension_name}: {e}")
                # Treat errors as failures
                dimension_results[dimension_name] = ConstraintCheckResult(
                    satisfied=False,
                    reason=f"Evaluation error: {e}",
                )
                failed_dimensions.append(dimension_name)

        # Compute overall satisfaction based on mode
        satisfied = self._compute_satisfaction(dimension_results, failed_dimensions, mode)

        # Run anti-gaming detection if enabled
        anti_gaming_flags: List[str] = []
        if self._enable_anti_gaming and agent_id:
            anti_gaming_flags = self._check_anti_gaming(agent_id, constraints, context, dimension_results)

        result = EvaluationResult(
            satisfied=satisfied,
            dimension_results=dimension_results,
            interaction_mode=mode,
            failed_dimensions=failed_dimensions,
            warnings=warnings,
            anti_gaming_flags=anti_gaming_flags,
        )

        # Store in history for pattern detection
        if agent_id:
            history = self._evaluation_history[agent_id]
            history.append(result)
            # Keep only last 10 evaluations
            if len(history) > 10:
                self._evaluation_history[agent_id] = history[-10:]

        return result

    def _compute_satisfaction(
        self,
        results: Dict[str, ConstraintCheckResult],
        failed: List[str],
        mode: InteractionMode,
    ) -> bool:
        """
        Compute overall satisfaction based on interaction mode.

        Args:
            results: Map of dimension name to check result
            failed: List of failed dimension names
            mode: Interaction mode to apply

        Returns:
            True if overall constraint evaluation is satisfied
        """
        if not results:
            # No valid dimensions evaluated
            return True

        total = len(results)
        passed = total - len(failed)

        if mode == InteractionMode.CONJUNCTIVE:
            # ALL must pass
            return len(failed) == 0

        elif mode == InteractionMode.DISJUNCTIVE:
            # ANY pass is enough
            return passed > 0

        elif mode == InteractionMode.INDEPENDENT:
            # Majority must pass
            return passed > (total / 2)

        elif mode == InteractionMode.HIERARCHICAL:
            # First dimension determines result
            if results:
                first_key = next(iter(results))
                return results[first_key].satisfied

        return False

    def _check_anti_gaming(
        self,
        agent_id: str,
        constraints: Dict[str, Any],
        context: Dict[str, Any],
        results: Dict[str, ConstraintCheckResult],
    ) -> List[str]:
        """
        Check for anti-gaming patterns in the evaluation.

        Detects:
        1. Boundary pushing: usage_ratio > 0.95 for any dimension
        2. Constraint splitting: 8+ of last 10 evaluations have small ops

        Args:
            agent_id: Agent being evaluated
            constraints: Constraint values used
            context: Execution context
            results: Individual dimension results

        Returns:
            List of detected anti-gaming flags
        """
        flags: List[str] = []

        # Check for boundary pushing (usage_ratio > 0.95)
        for dim_name, result in results.items():
            if result.limit is not None and result.limit > 0:
                if result.used is not None:
                    usage_ratio = result.used / result.limit
                    if usage_ratio > 0.95:
                        flags.append(f"boundary_pushing:{dim_name} (usage_ratio={usage_ratio:.2f})")

        # Check for constraint splitting
        # 8+ of last 10 evaluations have small ops (used/limit < 0.1)
        history = self._evaluation_history.get(agent_id, [])
        if len(history) >= 10:
            small_ops_count = 0
            for past_result in history[-10:]:
                for dim_result in past_result.dimension_results.values():
                    if dim_result.limit is not None and dim_result.limit > 0:
                        if dim_result.used is not None:
                            if dim_result.used / dim_result.limit < 0.1:
                                small_ops_count += 1
                                break  # Count once per evaluation

            if small_ops_count >= 8:
                flags.append(f"constraint_splitting:detected ({small_ops_count}/10 evaluations with small ops)")

        return flags

    def validate_tightening(
        self,
        parent_constraints: Dict[str, Any],
        child_constraints: Dict[str, Any],
    ) -> List[str]:
        """
        Validate that child constraints properly tighten parent constraints.

        A fundamental EATP security property: delegations can only TIGHTEN
        constraints, never loosen them.

        Args:
            parent_constraints: Parent (delegator) constraints
            child_constraints: Child (delegatee) constraints

        Returns:
            List of violation messages (empty if valid tightening)
        """
        violations: List[str] = []

        for dim_name, child_value in child_constraints.items():
            # Check if parent has this dimension
            if dim_name not in parent_constraints:
                # Child can add NEW constraints (tightening)
                continue

            parent_value = parent_constraints[dim_name]

            # Get the dimension to validate
            dimension = self._registry.get(dim_name)
            if dimension is None:
                # Can't validate unknown dimension
                violations.append(f"Unknown dimension: {dim_name}")
                continue

            try:
                # Parse both constraints
                parent_parsed = dimension.parse(parent_value)
                child_parsed = dimension.parse(child_value)

                # Validate tightening
                if not dimension.validate_tightening(parent_parsed, child_parsed):
                    violations.append(
                        f"Dimension '{dim_name}': child constraint "
                        f"({child_value}) is looser than parent ({parent_value})"
                    )

            except Exception as e:
                violations.append(f"Error validating {dim_name}: {e}")

        return violations

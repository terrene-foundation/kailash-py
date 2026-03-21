# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Extensible constraint system for EATP.
Provides plugin architecture for custom constraint dimensions.
"""

from kailash.trust.constraints.budget_tracker import (
    BudgetCheckResult,
    BudgetEvent,
    BudgetSnapshot,
    BudgetTracker,
    BudgetTrackerError,
    microdollars_to_usd,
    usd_to_microdollars,
)
from kailash.trust.constraints.builtin import (
    CommunicationDimension,
    CostLimitDimension,
    DataAccessDimension,
    RateLimitDimension,
    ResourceDimension,
    TimeDimension,
    register_builtin_dimensions,
)
from kailash.trust.constraints.dimension import (
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

__all__ = [
    # Core dimension types
    "ConstraintDimension",
    "ConstraintDimensionRegistry",
    "ConstraintValue",
    "ConstraintCheckResult",
    # Multi-dimension evaluator
    "MultiDimensionEvaluator",
    "InteractionMode",
    "EvaluationResult",
    # Built-in dimensions
    "CostLimitDimension",
    "TimeDimension",
    "ResourceDimension",
    "RateLimitDimension",
    "DataAccessDimension",
    "CommunicationDimension",
    "register_builtin_dimensions",
    # Budget tracker primitive
    "BudgetTracker",
    "BudgetSnapshot",
    "BudgetCheckResult",
    "BudgetEvent",
    "BudgetTrackerError",
    "usd_to_microdollars",
    "microdollars_to_usd",
]

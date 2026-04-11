"""
Extensible constraint system for EATP.
Provides plugin architecture for custom constraint dimensions.
"""

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
]

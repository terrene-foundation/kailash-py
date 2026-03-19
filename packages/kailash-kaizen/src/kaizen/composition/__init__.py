from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Composite Agent Validation for Kailash Kaizen.

Provides DAG validation, schema compatibility checking, and cost estimation
for composite agent pipelines.
"""

from kaizen.composition.cost_estimator import estimate_cost
from kaizen.composition.dag_validator import validate_dag
from kaizen.composition.errors import (
    CompositionError,
    CycleDetectedError,
    SchemaIncompatibleError,
)
from kaizen.composition.models import (
    CompatibilityResult,
    CostEstimate,
    ValidationResult,
)
from kaizen.composition.schema_compat import check_schema_compatibility

__all__ = [
    "validate_dag",
    "check_schema_compatibility",
    "estimate_cost",
    "ValidationResult",
    "CompatibilityResult",
    "CostEstimate",
    "CompositionError",
    "CycleDetectedError",
    "SchemaIncompatibleError",
]

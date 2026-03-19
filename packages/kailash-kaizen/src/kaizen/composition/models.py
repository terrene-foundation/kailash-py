from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Data models for composite agent validation.

All models use dataclasses with full to_dict()/from_dict() serialization.
Error classes are defined in ``errors.py`` and re-exported here for
backward compatibility.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from kaizen.composition.errors import (
    CompositionError,
    CycleDetectedError,
    SchemaIncompatibleError,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ValidationResult",
    "CompatibilityResult",
    "CostEstimate",
    "CompositionError",
    "CycleDetectedError",
    "SchemaIncompatibleError",
]


@dataclass
class ValidationResult:
    """Result of DAG validation.

    Attributes:
        is_valid: True if the DAG has no cycles.
        topological_order: Valid execution order (empty if cycles exist).
        cycles: List of detected cycles, each cycle is a list of agent names.
        warnings: Non-fatal issues (e.g., missing dependencies).
    """

    is_valid: bool
    topological_order: List[str] = field(default_factory=list)
    cycles: List[List[str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "topological_order": list(self.topological_order),
            "cycles": [list(c) for c in self.cycles],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ValidationResult:
        if "is_valid" not in data:
            raise ValueError("ValidationResult.from_dict requires 'is_valid' key")
        return cls(
            is_valid=data["is_valid"],
            topological_order=list(data.get("topological_order", [])),
            cycles=[list(c) for c in data.get("cycles", [])],
            warnings=list(data.get("warnings", [])),
        )


@dataclass
class CompatibilityResult:
    """Result of schema compatibility check.

    Attributes:
        compatible: True if output schema satisfies all required input fields.
        mismatches: List of field-level incompatibilities with details.
        warnings: Non-fatal issues (e.g., optional fields missing from output).
    """

    compatible: bool
    mismatches: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "compatible": self.compatible,
            "mismatches": [dict(m) for m in self.mismatches],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CompatibilityResult:
        if "compatible" not in data:
            raise ValueError("CompatibilityResult.from_dict requires 'compatible' key")
        return cls(
            compatible=data["compatible"],
            mismatches=[dict(m) for m in data.get("mismatches", [])],
            warnings=list(data.get("warnings", [])),
        )


@dataclass
class CostEstimate:
    """Estimated cost for a composite agent pipeline.

    Attributes:
        estimated_total_microdollars: Total estimated cost in microdollars (1 USD = 1_000_000).
        per_agent: Per-agent cost breakdown in microdollars.
        confidence: Confidence level: "high" (100+ invocations), "medium" (10+), "low" (<10).
        warnings: Issues that affect estimate accuracy.
    """

    estimated_total_microdollars: int = 0
    per_agent: Dict[str, int] = field(default_factory=dict)
    confidence: str = "low"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "estimated_total_microdollars": self.estimated_total_microdollars,
            "per_agent": dict(self.per_agent),
            "confidence": self.confidence,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CostEstimate:
        return cls(
            estimated_total_microdollars=data.get("estimated_total_microdollars", 0),
            per_agent=dict(data.get("per_agent", {})),
            confidence=data.get("confidence", "low"),
            warnings=list(data.get("warnings", [])),
        )

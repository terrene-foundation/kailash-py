# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Field-level validation result types.

Provides structured result types for aggregating validation errors
across all fields of a DataFlowModel instance. Designed for error
aggregation (collect ALL errors, not fail-fast).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

__all__ = [
    "FieldValidationError",
    "ValidationResult",
]


@dataclass(frozen=True)
class FieldValidationError:
    """A single field-level validation failure.

    Attributes:
        field: Name of the model field that failed validation.
        message: Human-readable description of the failure.
        validator: Name of the validator function that produced this error.
        value: The value that failed validation (optional, omitted for sensitive data).
    """

    field: str
    message: str
    validator: str
    value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        result: Dict[str, Any] = {
            "field": self.field,
            "message": self.message,
            "validator": self.validator,
        }
        if self.value is not None:
            result["value"] = self.value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FieldValidationError:
        """Deserialize from dictionary."""
        return cls(
            field=data["field"],
            message=data["message"],
            validator=data["validator"],
            value=data.get("value"),
        )


@dataclass
class ValidationResult:
    """Aggregated result of validating a model instance.

    Collects all validation errors across all fields. The ``valid``
    property is ``True`` only when ``errors`` is empty.

    Attributes:
        errors: List of individual field validation failures.
    """

    errors: List[FieldValidationError] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """Return ``True`` when there are no validation errors."""
        return len(self.errors) == 0

    def add_error(
        self,
        field_name: str,
        message: str,
        validator: str,
        value: Any = None,
    ) -> None:
        """Append a validation error to the result.

        Args:
            field_name: Name of the field that failed.
            message: Human-readable description.
            validator: Name of the validator that produced this error.
            value: The offending value (optional).
        """
        self.errors.append(
            FieldValidationError(
                field=field_name,
                message=message,
                validator=validator,
                value=value,
            )
        )

    def merge(self, other: ValidationResult) -> None:
        """Merge errors from another ``ValidationResult`` into this one."""
        self.errors.extend(other.errors)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ValidationResult:
        """Deserialize from dictionary."""
        return cls(
            errors=[FieldValidationError.from_dict(e) for e in data.get("errors", [])],
        )

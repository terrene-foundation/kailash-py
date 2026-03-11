"""
Base Validator Infrastructure

This module provides the base validator class and registration system
for all DataFlow strict mode validators.

Validators are organized by layer:
- Layer 1: ModelValidator (model structure validation)
- Layer 2: ParameterValidator (node parameter validation)
- Layer 3: ConnectionValidator (connection validation)
- Layer 4: WorkflowValidator (workflow structure validation)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ValidationError:
    """
    Structured validation error.

    Attributes:
        error_code: Error code (e.g., STRICT_MODEL_001)
        category: Error category (e.g., MODEL_VALIDATION)
        severity: ERROR or WARNING
        message: Human-readable error message
        context: Additional context data
        solution: Suggested fix with code example
    """

    error_code: str
    category: str
    severity: str
    message: str
    context: Dict[str, Any]
    solution: Dict[str, Any]


class BaseValidator(ABC):
    """
    Base class for all strict mode validators.

    Each validator implements a specific validation layer and provides
    structured error messages following the ADR-003 error format.
    """

    @abstractmethod
    def validate(self, target: Any) -> List[ValidationError]:
        """
        Validate the target and return any validation errors.

        Args:
            target: Object to validate (model, parameters, connection, workflow)

        Returns:
            List of ValidationError instances (empty if valid)
        """
        pass


# Validator registry (populated by validator implementations)
_validator_registry: Dict[str, BaseValidator] = {}


def register_validator(name: str, validator: BaseValidator) -> None:
    """Register a validator in the global registry."""
    _validator_registry[name] = validator


def get_validator(name: str) -> Optional[BaseValidator]:
    """Get a validator from the global registry."""
    return _validator_registry.get(name)

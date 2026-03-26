"""
DataFlow Validation Package

This package provides:

1. **Strict mode validation** — opt-in structural validation for DataFlow models,
   parameters, connections, and workflows (existing).
2. **Field-level validation** — ``@field_validator`` decorator and common
   validators (email, URL, UUID, length, range, pattern, phone) for
   validating model *instance* data at runtime (new — issue #82).

Usage::

    from dataflow.validation import (
        field_validator, validate_model, ValidationResult, FieldValidationError,
        email_validator, url_validator, uuid_validator,
        length_validator, range_validator, pattern_validator, phone_validator,
    )
"""

from dataflow.validation.decorators import field_validator, validate_model
from dataflow.validation.field_validators import (
    email_validator,
    length_validator,
    pattern_validator,
    phone_validator,
    range_validator,
    url_validator,
    uuid_validator,
)
from dataflow.validation.result import FieldValidationError, ValidationResult
from dataflow.validation.strict_mode import (
    StrictModeConfig,
    get_strict_mode_config,
    is_strict_mode_enabled,
)

__all__ = [
    # Strict mode (existing)
    "StrictModeConfig",
    "get_strict_mode_config",
    "is_strict_mode_enabled",
    # Field-level validation (issue #82)
    "field_validator",
    "validate_model",
    "ValidationResult",
    "FieldValidationError",
    # Common validators (issue #82)
    "email_validator",
    "url_validator",
    "uuid_validator",
    "length_validator",
    "range_validator",
    "pattern_validator",
    "phone_validator",
]

__version__ = "0.6.0"

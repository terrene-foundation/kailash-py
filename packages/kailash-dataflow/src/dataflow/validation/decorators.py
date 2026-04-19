# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Field-level validation decorators for DataFlowModel classes.

Apply ``@field_validator`` to a DataFlowModel subclass to attach
validation rules to individual fields. Then call ``validate_model``
on an instance to collect all validation errors.

Usage::

    from dataflow.validation.decorators import field_validator, validate_model
    from dataflow.validation.field_validators import email_validator, length_validator

    @field_validator("email", email_validator)
    @field_validator("name", length_validator(min_len=1, max_len=100))
    @dataclass
    class User(DataFlowModel):
        name: str = ""
        email: str = ""

    user = User(name="", email="bad")
    result = validate_model(user)
    assert not result.valid
    assert len(result.errors) == 2

Thread-safe: the registry uses a class-level list stored via
``__field_validators__``. Decoration happens at import time (single-
threaded); validation reads the list without mutation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple, Type, TypeVar

from dataflow.validation.result import ValidationResult

if TYPE_CHECKING:
    from dataflow.classification.policy import ClassificationPolicy

logger = logging.getLogger(__name__)

__all__ = [
    "field_validator",
    "validate_model",
]

T = TypeVar("T")

# Type alias for a validator entry: (field_name, validator_fn, validator_label)
_ValidatorEntry = Tuple[str, Callable[[Any], bool], str]


def field_validator(
    field_name: str,
    validator_fn: Callable[[Any], bool],
) -> Callable[[Type[T]], Type[T]]:
    """Class decorator that attaches a field-level validator.

    Multiple ``@field_validator`` decorators can be stacked on a single
    class. Validators are stored in order on a ``__field_validators__``
    class attribute (a list of tuples).

    Args:
        field_name: The model field to validate.
        validator_fn: A callable ``(value) -> bool``. Returns ``True``
            if the value is valid.

    Returns:
        A class decorator that records the validator.
    """
    # Derive a human-readable label for error messages.
    label = getattr(
        validator_fn,
        "__qualname__",
        getattr(validator_fn, "__name__", repr(validator_fn)),
    )

    def _decorator(cls: Type[T]) -> Type[T]:
        # Lazily initialize the validator list. Copy from parent to
        # avoid mutating a shared superclass list.
        existing: List[_ValidatorEntry] = list(getattr(cls, "__field_validators__", []))
        existing.append((field_name, validator_fn, label))
        cls.__field_validators__ = existing  # type: ignore[attr-defined]
        return cls

    return _decorator


def validate_model(
    instance: Any,
    policy: Optional["ClassificationPolicy"] = None,
    model_name: Optional[str] = None,
) -> ValidationResult:
    """Run all registered field validators against a model instance.

    Collects ALL validation errors (does not fail-fast). Returns a
    ``ValidationResult`` whose ``.valid`` property is ``True`` only
    when every validator passes.

    When ``policy`` and ``model_name`` are provided, validation errors
    on classified fields are routed through
    ``dataflow.classification.validation_error.sanitize_validation_error``
    so the caller-facing error surface never echoes a classified field
    NAME or raw VALUE back to the caller. ``ValidationResult.classified_field_count``
    tracks the aggregate for operator alerting. See issue #520 and
    ``rules/event-payload-classification.md`` Rules 5–7.

    Args:
        instance: A DataFlowModel instance (or any object whose class
            has a ``__field_validators__`` attribute).
        policy: Optional classification policy. When ``None`` the
            helper is a pass-through and errors contain raw field
            names / values (backwards-compatible behaviour for
            unclassified models).
        model_name: Optional model name used by the sanitiser to look
            up per-field classification. Required when ``policy`` is
            supplied; ignored otherwise.

    Returns:
        A ``ValidationResult`` aggregating all errors.
    """
    # Lazy import avoids a cycle with classification.policy.
    from dataflow.classification.validation_error import sanitize_validation_error

    result = ValidationResult()
    validators: List[_ValidatorEntry] = getattr(
        type(instance), "__field_validators__", []
    )

    for field_name, validator_fn, label in validators:
        value = getattr(instance, field_name, None)
        try:
            is_valid = validator_fn(value)
        except Exception as exc:
            # Validator raised — treat as validation failure, not crash.
            # Classified field names stay at DEBUG per
            # rules/observability.md Rule 8; the WARN-level signal is
            # carried by the ValidationResult aggregate.
            logger.debug(
                "validator.raised",
                extra={
                    "validator": label,
                    "exc_type": type(exc).__name__,
                    "field": field_name,
                    "error": str(exc),
                },
            )
            is_valid = False

        if not is_valid:
            raw_message = (
                f"Validation failed for field '{field_name}' " f"(validator: {label})"
            )
            safe_field, safe_message, safe_value, is_classified = (
                sanitize_validation_error(
                    policy=policy,
                    model_name=model_name or "",
                    field_name=field_name,
                    message=raw_message,
                    value=value,
                )
            )
            result.add_error(
                field_name=safe_field,
                message=safe_message,
                validator=label,
                value=safe_value,
                is_classified=is_classified,
            )

    return result

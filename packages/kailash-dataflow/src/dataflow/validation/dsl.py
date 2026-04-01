# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Declarative ``__validation__`` dict parser for ``@db.model`` classes.

Parses a ``__validation__`` class attribute into the existing
``__field_validators__`` internal format used by
``dataflow.validation.decorators.validate_model``.

Usage on a model class::

    @db.model
    class User:
        id: str
        name: str
        email: str
        status: str

        __validation__ = {
            "name":   {"min_length": 1, "max_length": 100},
            "email":  {"validators": ["email"]},
            "status": {"one_of": ["active", "inactive", "pending"]},
        }

This produces the same internal ``__field_validators__`` list that
stacking ``@field_validator`` decorators would create.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from dataflow.validation.field_validators import (
    email_validator,
    length_validator,
    pattern_validator,
    phone_validator,
    range_validator,
    url_validator,
    uuid_validator,
)

logger = logging.getLogger(__name__)

__all__ = [
    "apply_validation_dict",
    "one_of_validator",
    "NAMED_VALIDATORS",
]


# ---------------------------------------------------------------------------
# Named validator mapping
# ---------------------------------------------------------------------------

NAMED_VALIDATORS: Dict[str, Callable[[Any], bool]] = {
    "email": email_validator,
    "url": url_validator,
    "uuid": uuid_validator,
    "phone": phone_validator,
}


# ---------------------------------------------------------------------------
# one_of validator (new)
# ---------------------------------------------------------------------------


def one_of_validator(allowed: List[Any]) -> Callable[[Any], bool]:
    """Return a validator that checks value membership in *allowed*.

    Args:
        allowed: List of acceptable values.

    Returns:
        A callable ``(value) -> bool``.
    """
    allowed_set = set(allowed)

    def _check(value: Any) -> bool:
        return value in allowed_set

    _check.__qualname__ = f"one_of_validator({allowed!r})"
    return _check


# ---------------------------------------------------------------------------
# Dict parser
# ---------------------------------------------------------------------------


def apply_validation_dict(cls: type, validation_dict: Dict[str, Any]) -> None:
    """Parse ``__validation__`` dict into ``__field_validators__`` format.

    Mutates *cls* in-place, appending validator entries to
    ``cls.__field_validators__`` in the same ``(field_name, fn, label)``
    tuple format used by ``@field_validator``.

    Keys starting with ``_`` are reserved for config (e.g. ``_config``)
    and are silently skipped.

    Args:
        cls: The model class to augment.
        validation_dict: The ``__validation__`` dict from the class.

    Raises:
        ValueError: If the dict contains an unknown named validator or
            an invalid rule structure.
    """
    # Ensure the list exists (copy from parent to avoid mutation)
    existing: list = list(getattr(cls, "__field_validators__", []))

    for field_name, rules in validation_dict.items():
        if field_name.startswith("_"):
            # Config keys (e.g. _config) -- handle reserved ones
            if field_name == "_config":
                _handle_config(rules)
            continue

        if not isinstance(rules, dict):
            raise ValueError(
                f"Validation rules for '{field_name}' must be a dict, "
                f"got {type(rules).__name__}"
            )

        validators: List[Callable[[Any], bool]] = []

        # min_length / max_length
        if "min_length" in rules or "max_length" in rules:
            fn = length_validator(
                min_len=rules.get("min_length"),
                max_len=rules.get("max_length"),
            )
            validators.append(fn)

        # Named validators
        if "validators" in rules:
            for v_name in rules["validators"]:
                if v_name not in NAMED_VALIDATORS:
                    raise ValueError(
                        f"Unknown validator '{v_name}'. "
                        f"Available: {', '.join(sorted(NAMED_VALIDATORS.keys()))}"
                    )
                validators.append(NAMED_VALIDATORS[v_name])

        # Range
        if "range" in rules:
            range_spec = rules["range"]
            validators.append(
                range_validator(
                    min_val=range_spec.get("min"),
                    max_val=range_spec.get("max"),
                )
            )

        # One-of
        if "one_of" in rules:
            validators.append(one_of_validator(rules["one_of"]))

        # Pattern
        if "pattern" in rules:
            validators.append(pattern_validator(rules["pattern"]))

        # Custom callable
        if "custom" in rules:
            validators.append(rules["custom"])

        # Append all validators as (field_name, fn, label) tuples
        for fn in validators:
            label = getattr(
                fn,
                "__qualname__",
                getattr(fn, "__name__", repr(fn)),
            )
            existing.append((field_name, fn, label))

    cls.__field_validators__ = existing


def _handle_config(config: Any) -> None:
    """Process ``_config`` key from validation dict (reserved for future use)."""
    if not isinstance(config, dict):
        return
    if config.get("validate_on_read"):
        logger.info(
            "validate_on_read is reserved for future use and has no effect in v1."
        )

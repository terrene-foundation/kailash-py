# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Validation-error sanitization helpers.

Validation errors carry a surface that is strictly wider than an internal
log line: they are surfaced back to the caller (HTTP 400 body, CLI
stderr, agent response), recorded in audit trails, and often displayed
in developer tooling. A raw classified field VALUE or a classified
field NAME in a validation error is a permanent leak with a wider blast
radius than any log entry.

This module provides ``sanitize_validation_error`` — the single filter
point that every ``FieldValidationError`` constructed in the DataFlow
validation pipeline routes through. The helper:

1. Replaces a classified field NAME with ``"<classified>"`` so the
   error surface cannot be used to enumerate the schema.
2. Replaces a classified field VALUE with a type-descriptor
   (``"<classified string>"``, ``"<classified int>"``, etc.) so the
   error surface cannot be used to exfiltrate the value.
3. Rewrites the human-readable ``message`` to strip any interpolated
   field name before it is surfaced.

Cross-SDK: contract matches ``kailash-rs`` BP-049 (v3.19.0). Same
placeholder strings, same type-descriptor vocabulary, same behaviour
when no policy is configured (pass-through).

See issue #520 and ``rules/event-payload-classification.md`` Rules 5–7.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Tuple

if TYPE_CHECKING:
    from dataflow.classification.policy import ClassificationPolicy

__all__ = [
    "sanitize_validation_error",
    "CLASSIFIED_FIELD_NAME_PLACEHOLDER",
    "classified_value_descriptor",
]


# Single placeholder string for classified field names. Intentionally
# short and grep-able so an audit of caller-facing strings can surface
# every validation error that touched a classified field.
CLASSIFIED_FIELD_NAME_PLACEHOLDER = "<classified>"


def classified_value_descriptor(value: Any) -> str:
    """Return a type-descriptor string for a classified field value.

    The descriptor reveals only the Python type of the value, never the
    value itself. Covers the common field types: ``str``, ``int``,
    ``float``, ``bool``, ``bytes``, ``list``, ``dict``; falls back to
    ``"<classified value>"`` for anything else.

    Cross-SDK: matches ``kailash-rs`` descriptor vocabulary.
    """
    if value is None:
        return "<classified none>"
    if isinstance(value, bool):
        return "<classified bool>"
    if isinstance(value, int):
        return "<classified int>"
    if isinstance(value, float):
        return "<classified float>"
    if isinstance(value, (bytes, bytearray)):
        return "<classified bytes>"
    if isinstance(value, str):
        return "<classified string>"
    if isinstance(value, list):
        return "<classified list>"
    if isinstance(value, dict):
        return "<classified dict>"
    return "<classified value>"


def sanitize_validation_error(
    policy: Optional["ClassificationPolicy"],
    model_name: str,
    field_name: str,
    message: str,
    value: Any = None,
) -> Tuple[str, str, Any, bool]:
    """Return a sanitised ``(field, message, value, is_classified)`` tuple.

    Args:
        policy: The active classification policy, or ``None`` if no
            classifications are registered on this DataFlow instance.
            When ``None`` the helper is a pass-through and
            ``is_classified`` is always ``False``.
        model_name: The model the validation error is about (e.g.
            ``"User"``).
        field_name: The field name that failed validation. When the
            ``(model_name, field_name)`` pair is classified, the name
            returned by this helper is
            ``CLASSIFIED_FIELD_NAME_PLACEHOLDER``; otherwise the name
            is returned unchanged.
        message: The human-readable validation message. When the field
            is classified and the message contains the raw field name,
            the raw name is replaced with the placeholder so the name
            cannot be recovered from the surface text.
        value: The offending value (optional). When the field is
            classified this is replaced with a type-descriptor via
            :func:`classified_value_descriptor`; otherwise it is
            returned unchanged.

    Returns:
        A 4-tuple ``(safe_field, safe_message, safe_value,
        is_classified)``. Callers use ``is_classified`` to increment a
        ``classified_field_count`` aggregate on the surrounding
        ``ValidationResult`` for operator alerting without revealing
        which fields were affected.
    """
    if policy is None:
        return field_name, message, value, False

    field_classification = policy.get_field(model_name, field_name)
    if field_classification is None:
        return field_name, message, value, False

    # Classified: replace name, scrub message, and replace value with
    # a type-descriptor.
    safe_field = CLASSIFIED_FIELD_NAME_PLACEHOLDER
    safe_message = message.replace(field_name, CLASSIFIED_FIELD_NAME_PLACEHOLDER)
    safe_value = classified_value_descriptor(value) if value is not None else None
    return safe_field, safe_message, safe_value, True

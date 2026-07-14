from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared type-guarded coercion helpers for manifest ``from_dict`` methods.

``list(value)`` silently char-splits a ``str`` (``list("pii")`` ->
``['p', 'i', 'i']``) instead of raising — a type-confusion bug per
``security.md``'s "Type-Confusion MUST Raise, Not Silently Coerce"
discipline.  :func:`coerce_list_field` is the single shared guard used by
every ``from_dict`` classmethod in this package so a should-be-list field
(``capabilities``, ``tools``, ``supported_models``, ``agents_requested``,
``data_access_needed``) raises a clear, field-named
:class:`~kaizen.manifest.errors.ManifestValidationError` instead of
silently producing a per-character list.
"""

from typing import Any, List

from kaizen.manifest.errors import ManifestValidationError

__all__ = ["coerce_list_field", "safe_repr"]

_DEFAULT_REPR_CAP = 200
_TRUNCATION_SUFFIX = "…(truncated)"


def safe_repr(value: Any, max_len: int = _DEFAULT_REPR_CAP) -> str:
    """Return a length-bounded ``repr`` of *value* for error messages.

    Manifest validation errors are forwarded verbatim to the MCP client
    (the catalog server relays ``ManifestValidationError`` messages —
    ``ManifestError`` is a ``ValueError`` subclass). Echoing an
    attacker-controlled field value with an unbounded ``{value!r}`` lets a
    caller amplify a tiny request into a huge error payload
    (DoS / input-validation, per ``security.md`` length-limits). Every
    attacker-influenced ``{X!r}`` in a manifest error message MUST route
    through this helper, which truncates the ``repr`` to *max_len*
    characters (truncation suffix included within the budget) so the
    emitted message stays bounded regardless of input size.
    """
    rendered = repr(value)
    if len(rendered) <= max_len:
        return rendered
    keep = max(0, max_len - len(_TRUNCATION_SUFFIX))
    return rendered[:keep] + _TRUNCATION_SUFFIX


def coerce_list_field(value: Any, field_name: str) -> List[Any]:
    """Coerce *value* to a ``list``, raising on type-confused input.

    Args:
        value: The raw value pulled from a ``dict`` (typically via
            ``data.get(field_name, [])``).
        field_name: The manifest field name, used in the error message.

    Returns:
        A new ``list`` containing *value*'s items.

    Raises:
        ManifestValidationError: If *value* is a ``str``/``bytes`` (which
            would silently char-split) or any other non-list/tuple type.
    """
    if isinstance(value, (str, bytes)):
        raise ManifestValidationError(
            f"Field {field_name!r} must be a list, got a "
            f"{type(value).__name__} ({safe_repr(value)}); a string would "
            f"silently split into individual characters",
            details={"field": field_name, "received_type": type(value).__name__},
        )
    if not isinstance(value, (list, tuple)):
        raise ManifestValidationError(
            f"Field {field_name!r} must be a list, got {type(value).__name__} "
            f"({safe_repr(value)})",
            details={"field": field_name, "received_type": type(value).__name__},
        )
    return list(value)

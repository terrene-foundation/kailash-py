# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Allowlist helpers for LLM-emitted plan values.

An LLM emitting a plan may invent a node-type, field-type, or
config-value the framework does not actually expose ("hallucination").
Realizing such a plan against the framework primitive raises a deep
``KeyError`` / ``AttributeError`` whose stack does not point back at
the brief — the user sees a Python traceback and cannot fix it.

The three helpers below close that failure mode at the validation gate.
Every realizer MUST validate LLM-emitted identifiers against a
caller-provided allowlist (the set of node-types / field-types /
config-values the framework genuinely exposes for this primitive). A
miss raises :class:`BriefInterpretationError` with ``unknown_value``
set to the offending name, so the caller can present an actionable
error or retry the LLM with a refined prompt.

Origin: issue #1125 — every ``from_brief()`` primitive needs the same
mechanical check; consolidating into one module makes the contract
uniform.
"""

from __future__ import annotations

from typing import Dict, Set

from kailash._from_brief.exceptions import BriefInterpretationError

__all__ = [
    "validate_node_type",
    "validate_field_type",
    "validate_config_value",
]


def validate_node_type(name: str, allowed: Set[str]) -> None:
    """Raise if ``name`` is not in the framework's node-type allowlist.

    Args:
        name: The node-type identifier the LLM emitted (e.g.
            ``"CSVReaderNode"``).
        allowed: The set of node-type identifiers the framework
            exposes for this primitive. Callers MUST pass an explicit
            set — there is no implicit "anything goes" path.

    Raises:
        BriefInterpretationError: With ``unknown_value=name`` when
            ``name`` is not in ``allowed``.
    """
    if name not in allowed:
        raise BriefInterpretationError(
            f"node_type={name!r} is not in the framework's allowlist "
            f"(allowed: {sorted(allowed)!r}); the LLM emitted an "
            f"unknown node type",
            unknown_value=name,
        )


def validate_field_type(name: str, allowed: Set[str]) -> None:
    """Raise if ``name`` is not in the framework's field-type allowlist.

    Args:
        name: The field-type identifier the LLM emitted (e.g.
            ``"str"``, ``"int"``, ``"List[str]"``).
        allowed: The set of field-type identifiers the framework
            exposes for this primitive.

    Raises:
        BriefInterpretationError: With ``unknown_value=name`` when
            ``name`` is not in ``allowed``.
    """
    if name not in allowed:
        raise BriefInterpretationError(
            f"field_type={name!r} is not in the framework's allowlist "
            f"(allowed: {sorted(allowed)!r}); the LLM emitted an "
            f"unknown field type",
            unknown_value=name,
        )


def validate_config_value(
    field: str,
    value: str,
    allowed: Dict[str, Set[str]],
) -> None:
    """Raise if ``value`` is not in the allowlist for ``field``.

    Used for enum-shaped configuration fields where the LLM must pick
    from a finite set (e.g. ``mode in {"json", "yaml", "csv"}``).

    Args:
        field: The configuration field name (used for error message).
        value: The value the LLM emitted for this field.
        allowed: Mapping from field name to the set of values that
            field accepts. If ``field`` is not a key in ``allowed``,
            this function treats the entire field as unknown.

    Raises:
        BriefInterpretationError: With ``unknown_value=value`` when
            ``value`` is not in ``allowed[field]``, OR with
            ``unknown_value=field`` when ``field`` is not a key in
            ``allowed``.
    """
    if field not in allowed:
        raise BriefInterpretationError(
            f"config field={field!r} has no allowlist entry; the LLM "
            f"emitted a configuration field the framework does not "
            f"expose",
            unknown_value=field,
        )
    allowed_values = allowed[field]
    if value not in allowed_values:
        raise BriefInterpretationError(
            f"config value {field}={value!r} is not in the allowlist "
            f"for this field (allowed: {sorted(allowed_values)!r}); the "
            f"LLM emitted an unknown configuration value",
            unknown_value=value,
        )

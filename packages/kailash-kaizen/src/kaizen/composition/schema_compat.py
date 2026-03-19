from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Schema compatibility checker for composite agent pipelines.

Uses structural subtyping: an output schema is compatible with an input
schema if it provides at least all required fields with compatible types.
"""

import logging
from typing import Any, Dict, List

from kaizen.composition.models import CompatibilityResult

logger = logging.getLogger(__name__)

__all__ = ["check_schema_compatibility"]

# Type widening rules: output_type -> set of compatible input types
# "integer" can satisfy a "number" input (widening)
_TYPE_WIDENING: Dict[str, set] = {
    "integer": {"integer", "number"},
    "number": {"number"},
    "string": {"string"},
    "boolean": {"boolean"},
    "array": {"array"},
    "object": {"object"},
    "null": {"null"},
}


def check_schema_compatibility(
    output_schema: Dict[str, Any],
    input_schema: Dict[str, Any],
) -> CompatibilityResult:
    """Check if output_schema is compatible with input_schema.

    Uses structural subtyping: output must provide at least all required
    fields of the input, with compatible types.

    Args:
        output_schema: JSON Schema describing the output of the upstream agent.
        input_schema: JSON Schema describing the expected input of the downstream agent.

    Returns:
        CompatibilityResult with compatible, mismatches, and warnings.
    """
    mismatches: List[Dict[str, Any]] = []
    warnings: List[str] = []

    _check_object_compat(
        output_schema=output_schema,
        input_schema=input_schema,
        path="",
        mismatches=mismatches,
        warnings=warnings,
    )

    compatible = len(mismatches) == 0

    if not compatible:
        logger.info(
            "Schema incompatibility found: %d mismatch(es)",
            len(mismatches),
        )

    return CompatibilityResult(
        compatible=compatible,
        mismatches=mismatches,
        warnings=warnings,
    )


def _check_object_compat(
    output_schema: Dict[str, Any],
    input_schema: Dict[str, Any],
    path: str,
    mismatches: List[Dict[str, Any]],
    warnings: List[str],
) -> None:
    """Recursively check compatibility between two object schemas.

    Args:
        output_schema: Output schema (or sub-schema).
        input_schema: Input schema (or sub-schema).
        path: Dot-separated path for error context (e.g., "address.city").
        mismatches: Accumulator for incompatibilities.
        warnings: Accumulator for non-fatal issues.
    """
    input_props = input_schema.get("properties", {})
    output_props = output_schema.get("properties", {})
    required_fields = set(input_schema.get("required", []))

    # All properties defined in input_schema
    all_input_fields = set(input_props.keys())
    optional_fields = all_input_fields - required_fields

    # Check each required field
    for field_name in sorted(required_fields):
        field_path = f"{path}.{field_name}" if path else field_name
        input_field_schema = input_props.get(field_name, {})

        if field_name not in output_props:
            mismatches.append(
                {
                    "field": field_path,
                    "reason": "missing_required_field",
                    "detail": (
                        f"Required field '{field_path}' is not present "
                        f"in output schema"
                    ),
                }
            )
            logger.debug("Missing required field: %s", field_path)
            continue

        output_field_schema = output_props[field_name]
        _check_type_compat(
            output_field_schema=output_field_schema,
            input_field_schema=input_field_schema,
            field_path=field_path,
            mismatches=mismatches,
            warnings=warnings,
        )

    # Check optional fields (not required but defined in input)
    for field_name in sorted(optional_fields):
        field_path = f"{path}.{field_name}" if path else field_name

        if field_name not in output_props:
            warnings.append(
                f"Optional field '{field_path}' is not present in output schema"
            )
            logger.debug("Optional field missing from output: %s", field_path)


def _check_type_compat(
    output_field_schema: Dict[str, Any],
    input_field_schema: Dict[str, Any],
    field_path: str,
    mismatches: List[Dict[str, Any]],
    warnings: List[str],
) -> None:
    """Check type compatibility between two field schemas.

    Handles type widening (integer -> number), nested objects, and arrays.
    """
    output_type = output_field_schema.get("type")
    input_type = input_field_schema.get("type")

    # If either type is unspecified, skip type checking
    if output_type is None or input_type is None:
        return

    # Check type compatibility with widening
    allowed_types = _TYPE_WIDENING.get(output_type, {output_type})
    if input_type not in allowed_types:
        mismatches.append(
            {
                "field": field_path,
                "reason": "type_mismatch",
                "output_type": output_type,
                "input_type": input_type,
                "detail": (
                    f"Field '{field_path}': output type '{output_type}' is "
                    f"not compatible with input type '{input_type}'"
                ),
            }
        )
        logger.debug(
            "Type mismatch at %s: output=%s, input=%s",
            field_path,
            output_type,
            input_type,
        )
        return

    # Recurse into nested objects
    if output_type == "object" and input_type == "object":
        _check_object_compat(
            output_schema=output_field_schema,
            input_schema=input_field_schema,
            path=field_path,
            mismatches=mismatches,
            warnings=warnings,
        )

    # Recurse into array items
    if output_type == "array" and input_type == "array":
        output_items = output_field_schema.get("items", {})
        input_items = input_field_schema.get("items", {})
        if output_items and input_items:
            _check_type_compat(
                output_field_schema=output_items,
                input_field_schema=input_items,
                field_path=f"{field_path}[]",
                mismatches=mismatches,
                warnings=warnings,
            )

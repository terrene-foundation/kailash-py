# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Tier 1 (Unit) tests for schema compatibility checker.

Tests check_schema_compatibility() for structural subtyping, type widening,
nested objects, arrays, and missing/optional fields.

Self-contained: imports ONLY from kaizen.composition, never from kaizen.core.
"""

from __future__ import annotations

from kaizen.composition.models import CompatibilityResult
from kaizen.composition.schema_compat import check_schema_compatibility


class TestExactMatchCompatible:
    """Identical schemas are compatible."""

    def test_exact_match_compatible(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name", "age"],
        }
        result = check_schema_compatibility(output_schema=schema, input_schema=schema)

        assert result.compatible is True
        assert len(result.mismatches) == 0


class TestOutputHasExtraFieldsCompatible:
    """Output provides more fields than input requires -- still compatible."""

    def test_output_has_extra_fields_compatible(self) -> None:
        output_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "email": {"type": "string"},
            },
            "required": ["name", "age", "email"],
        }
        input_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name", "age"],
        }
        result = check_schema_compatibility(
            output_schema=output_schema, input_schema=input_schema
        )

        assert result.compatible is True
        assert len(result.mismatches) == 0


class TestMissingRequiredFieldIncompatible:
    """Output missing a required input field is incompatible."""

    def test_missing_required_field_incompatible(self) -> None:
        output_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        }
        input_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name", "age"],
        }
        result = check_schema_compatibility(
            output_schema=output_schema, input_schema=input_schema
        )

        assert result.compatible is False
        assert len(result.mismatches) > 0
        assert any("age" in str(m) for m in result.mismatches)


class TestTypeMismatchIncompatible:
    """Output field type doesn't match input field type."""

    def test_type_mismatch_incompatible(self) -> None:
        output_schema = {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
            },
            "required": ["value"],
        }
        input_schema = {
            "type": "object",
            "properties": {
                "value": {"type": "number"},
            },
            "required": ["value"],
        }
        result = check_schema_compatibility(
            output_schema=output_schema, input_schema=input_schema
        )

        assert result.compatible is False
        assert len(result.mismatches) > 0


class TestIntegerToNumberCompatible:
    """integer output -> number input is compatible (widening)."""

    def test_integer_to_number_compatible(self) -> None:
        output_schema = {
            "type": "object",
            "properties": {
                "value": {"type": "integer"},
            },
            "required": ["value"],
        }
        input_schema = {
            "type": "object",
            "properties": {
                "value": {"type": "number"},
            },
            "required": ["value"],
        }
        result = check_schema_compatibility(
            output_schema=output_schema, input_schema=input_schema
        )

        assert result.compatible is True
        assert len(result.mismatches) == 0


class TestNestedObjectCompatible:
    """Nested objects with matching fields are compatible."""

    def test_nested_object_compatible(self) -> None:
        output_schema = {
            "type": "object",
            "properties": {
                "address": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "zip": {"type": "string"},
                    },
                    "required": ["city", "zip"],
                },
            },
            "required": ["address"],
        }
        input_schema = {
            "type": "object",
            "properties": {
                "address": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                    },
                    "required": ["city"],
                },
            },
            "required": ["address"],
        }
        result = check_schema_compatibility(
            output_schema=output_schema, input_schema=input_schema
        )

        assert result.compatible is True
        assert len(result.mismatches) == 0


class TestNestedObjectIncompatible:
    """Nested object missing a required nested field is incompatible."""

    def test_nested_object_incompatible(self) -> None:
        output_schema = {
            "type": "object",
            "properties": {
                "address": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                    },
                    "required": ["city"],
                },
            },
            "required": ["address"],
        }
        input_schema = {
            "type": "object",
            "properties": {
                "address": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "zip": {"type": "string"},
                    },
                    "required": ["city", "zip"],
                },
            },
            "required": ["address"],
        }
        result = check_schema_compatibility(
            output_schema=output_schema, input_schema=input_schema
        )

        assert result.compatible is False
        assert len(result.mismatches) > 0


class TestOptionalFieldMissingOk:
    """Optional input fields (not in 'required') missing from output produce warning, not error."""

    def test_optional_field_missing_ok(self) -> None:
        output_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        }
        input_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "nickname": {"type": "string"},
            },
            "required": ["name"],
        }
        result = check_schema_compatibility(
            output_schema=output_schema, input_schema=input_schema
        )

        assert result.compatible is True
        assert len(result.mismatches) == 0
        # Optional field missing should produce a warning
        assert len(result.warnings) > 0
        assert any("nickname" in w for w in result.warnings)


class TestEmptySchemasCompatible:
    """Two empty schemas are trivially compatible."""

    def test_empty_schemas_compatible(self) -> None:
        result = check_schema_compatibility(output_schema={}, input_schema={})

        assert result.compatible is True
        assert len(result.mismatches) == 0


class TestArrayItemTypeCompatible:
    """Array items with compatible types are compatible."""

    def test_array_item_type_compatible(self) -> None:
        output_schema = {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["tags"],
        }
        input_schema = {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["tags"],
        }
        result = check_schema_compatibility(
            output_schema=output_schema, input_schema=input_schema
        )

        assert result.compatible is True
        assert len(result.mismatches) == 0


class TestArrayItemTypeMismatch:
    """Array items with incompatible types are incompatible."""

    def test_array_item_type_mismatch(self) -> None:
        output_schema = {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
            },
            "required": ["tags"],
        }
        input_schema = {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["tags"],
        }
        result = check_schema_compatibility(
            output_schema=output_schema, input_schema=input_schema
        )

        assert result.compatible is False
        assert len(result.mismatches) > 0


class TestCompatibilityResultSerialization:
    """CompatibilityResult to_dict/from_dict round-trip."""

    def test_round_trip(self) -> None:
        original = CompatibilityResult(
            compatible=False,
            mismatches=[{"field": "age", "reason": "missing"}],
            warnings=["nickname is optional and missing"],
        )
        data = original.to_dict()
        restored = CompatibilityResult.from_dict(data)

        assert restored.compatible == original.compatible
        assert restored.mismatches == original.mismatches
        assert restored.warnings == original.warnings

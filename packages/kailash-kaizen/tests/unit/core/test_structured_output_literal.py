"""
Test Literal type handling in structured output generation.

Tests BUG #1 fix: Literal types should be converted to JSON schema enum constraints.
"""

from typing import Literal

import pytest
from kaizen.core.structured_output import (
    StructuredOutputGenerator,
    create_structured_output_config,
)
from kaizen.signatures import InputField, OutputField, Signature


class TestLiteralTypeHandling:
    """Test that Literal types are correctly converted to enum constraints."""

    def test_literal_string_to_enum(self):
        """Test basic Literal[str] conversion to enum."""

        class LiteralSignature(Signature):
            input_text: str = InputField(desc="Input text")
            category: Literal["A", "B", "C"] = OutputField(desc="Category")

        schema = StructuredOutputGenerator.signature_to_json_schema(LiteralSignature())

        assert "category" in schema["properties"]
        assert schema["properties"]["category"]["type"] == "string"
        assert schema["properties"]["category"]["enum"] == ["A", "B", "C"]
        assert "category" in schema["required"]

    def test_literal_with_sentinel_value(self):
        """Test Literal with sentinel value (e.g., 'Not Mentioned')."""

        class SentinelLiteralSignature(Signature):
            text: str = InputField(desc="Text to analyze")
            specialty: Literal[
                "Not Mentioned", "Cardiology", "Neurology", "Orthopedics"
            ] = OutputField(desc="Medical specialty")

        schema = StructuredOutputGenerator.signature_to_json_schema(
            SentinelLiteralSignature()
        )

        assert "specialty" in schema["properties"]
        assert schema["properties"]["specialty"]["type"] == "string"
        assert schema["properties"]["specialty"]["enum"] == [
            "Not Mentioned",
            "Cardiology",
            "Neurology",
            "Orthopedics",
        ]

    def test_multiple_literal_fields(self):
        """Test multiple Literal fields in same signature."""

        class MultiLiteralSignature(Signature):
            text: str = InputField(desc="Input")
            priority: Literal["low", "medium", "high"] = OutputField(desc="Priority")
            status: Literal["pending", "approved", "rejected"] = OutputField(
                desc="Status"
            )

        schema = StructuredOutputGenerator.signature_to_json_schema(
            MultiLiteralSignature()
        )

        assert schema["properties"]["priority"]["enum"] == ["low", "medium", "high"]
        assert schema["properties"]["status"]["enum"] == [
            "pending",
            "approved",
            "rejected",
        ]

    def test_literal_mixed_with_other_types(self):
        """Test Literal fields mixed with regular types."""

        class MixedSignature(Signature):
            input: str = InputField(desc="Input")
            category: Literal["A", "B", "C"] = OutputField(desc="Category")
            confidence: float = OutputField(desc="Confidence score")
            count: int = OutputField(desc="Count")

        schema = StructuredOutputGenerator.signature_to_json_schema(MixedSignature())

        # Literal field should have enum
        assert schema["properties"]["category"]["type"] == "string"
        assert schema["properties"]["category"]["enum"] == ["A", "B", "C"]

        # Other fields should not have enum
        assert schema["properties"]["confidence"]["type"] == "number"
        assert "enum" not in schema["properties"]["confidence"]
        assert schema["properties"]["count"]["type"] == "integer"
        assert "enum" not in schema["properties"]["count"]

    def test_literal_with_description(self):
        """Test that Literal fields preserve descriptions."""

        class DescriptiveLiteralSignature(Signature):
            input: str = InputField(desc="Input text")
            level: Literal["beginner", "intermediate", "advanced"] = OutputField(
                desc="Skill level category"
            )

        schema = StructuredOutputGenerator.signature_to_json_schema(
            DescriptiveLiteralSignature()
        )

        assert schema["properties"]["level"]["description"] == "Skill level category"
        assert schema["properties"]["level"]["enum"] == [
            "beginner",
            "intermediate",
            "advanced",
        ]

    def test_create_structured_output_config_with_literal(self):
        """Test that create_structured_output_config works with Literal types."""

        class LiteralConfigSignature(Signature):
            query: str = InputField(desc="User query")
            intent: Literal["question", "command", "statement"] = OutputField(
                desc="Intent"
            )

        config = create_structured_output_config(
            LiteralConfigSignature(), strict=True, name="intent_classification"
        )

        assert config["type"] == "json_schema"
        assert config["json_schema"]["name"] == "intent_classification"
        assert config["json_schema"]["strict"] is True

        schema = config["json_schema"]["schema"]
        assert schema["properties"]["intent"]["enum"] == [
            "question",
            "command",
            "statement",
        ]

    def test_literal_with_many_values(self):
        """Test Literal with many possible values."""

        class ManyValuesSignature(Signature):
            text: str = InputField(desc="Input")
            color: Literal[
                "red",
                "orange",
                "yellow",
                "green",
                "blue",
                "indigo",
                "violet",
                "black",
                "white",
            ] = OutputField(desc="Color")

        schema = StructuredOutputGenerator.signature_to_json_schema(
            ManyValuesSignature()
        )

        assert len(schema["properties"]["color"]["enum"]) == 9
        assert "red" in schema["properties"]["color"]["enum"]
        assert "violet" in schema["properties"]["color"]["enum"]

    def test_literal_single_value(self):
        """Test Literal with single value (edge case)."""

        class SingleValueLiteralSignature(Signature):
            input: str = InputField(desc="Input")
            constant: Literal["FIXED"] = OutputField(desc="Fixed value")

        schema = StructuredOutputGenerator.signature_to_json_schema(
            SingleValueLiteralSignature()
        )

        assert schema["properties"]["constant"]["enum"] == ["FIXED"]

    def test_literal_values_with_spaces(self):
        """Test Literal values containing spaces."""

        class SpacedLiteralSignature(Signature):
            text: str = InputField(desc="Input")
            category: Literal["Option One", "Option Two", "Option Three"] = OutputField(
                desc="Category with spaces"
            )

        schema = StructuredOutputGenerator.signature_to_json_schema(
            SpacedLiteralSignature()
        )

        assert schema["properties"]["category"]["enum"] == [
            "Option One",
            "Option Two",
            "Option Three",
        ]

    def test_literal_values_with_special_characters(self):
        """Test Literal values with special characters."""

        class SpecialCharsLiteralSignature(Signature):
            input: str = InputField(desc="Input")
            status: Literal["pending...", "in-progress", "done!"] = OutputField(
                desc="Status"
            )

        schema = StructuredOutputGenerator.signature_to_json_schema(
            SpecialCharsLiteralSignature()
        )

        assert schema["properties"]["status"]["enum"] == [
            "pending...",
            "in-progress",
            "done!",
        ]


class TestLiteralTypeValidation:
    """Test that validation works correctly with Literal types."""

    def test_validate_literal_field_valid_value(self):
        """Test validation passes for valid Literal value."""

        class LiteralSig(Signature):
            output: Literal["A", "B", "C"] = OutputField(desc="Output")

        output = {"output": "A"}
        is_valid, errors = StructuredOutputGenerator.validate_output(
            output, LiteralSig()
        )

        assert is_valid
        assert len(errors) == 0

    def test_validate_literal_field_missing(self):
        """Test validation fails when Literal field is missing."""

        class LiteralSig(Signature):
            output: Literal["A", "B", "C"] = OutputField(desc="Output")

        output = {}  # Missing 'output' field
        is_valid, errors = StructuredOutputGenerator.validate_output(
            output, LiteralSig()
        )

        assert not is_valid
        assert len(errors) == 1
        assert "Missing required field: output" in errors[0]


class TestLiteralIntegration:
    """Integration tests for Literal types with structured outputs."""

    def test_literal_in_strict_mode_config(self):
        """Test Literal type in strict mode configuration."""

        class StrictLiteralSignature(Signature):
            query: str = InputField(desc="Query")
            category: Literal["tech", "business", "personal"] = OutputField(
                desc="Category"
            )

        config = create_structured_output_config(
            StrictLiteralSignature(), strict=True, name="categorization"
        )

        # Verify strict mode structure
        assert config["type"] == "json_schema"
        assert config["json_schema"]["strict"] is True
        assert config["json_schema"]["schema"]["additionalProperties"] is False

        # Verify enum constraint
        assert config["json_schema"]["schema"]["properties"]["category"]["enum"] == [
            "tech",
            "business",
            "personal",
        ]

    def test_literal_in_legacy_mode_config(self):
        """Test Literal type in legacy mode configuration."""

        class LegacyLiteralSignature(Signature):
            input: str = InputField(desc="Input")
            type: Literal["type1", "type2"] = OutputField(desc="Type")

        config = create_structured_output_config(LegacyLiteralSignature(), strict=False)

        # Legacy mode uses different structure (Bug #5 fix: no schema key)
        # OpenAI expects only {"type": "json_object"} for legacy mode
        assert config == {"type": "json_object"}
        assert "schema" not in config, "Legacy mode should not include schema key"

    def test_real_world_medical_specialty_example(self):
        """Test real-world example from bug report: medical specialty extraction."""

        class MedicalSpecialtySignature(Signature):
            conversation_text: str = InputField(desc="Patient conversation")
            referral_specialty: Literal[
                "Not Mentioned", "Cardiology", "Neurology", "Orthopedics"
            ] = OutputField(desc="Medical specialty")
            confidence: float = OutputField(desc="Confidence 0-1")

        config = create_structured_output_config(
            MedicalSpecialtySignature(),
            strict=True,
            name="medical_specialty_extraction",
        )

        schema = config["json_schema"]["schema"]

        # Verify schema structure
        assert "referral_specialty" in schema["properties"]
        assert "confidence" in schema["properties"]

        # Verify enum constraint for specialty
        assert schema["properties"]["referral_specialty"]["type"] == "string"
        assert schema["properties"]["referral_specialty"]["enum"] == [
            "Not Mentioned",
            "Cardiology",
            "Neurology",
            "Orthopedics",
        ]

        # Verify confidence is number (not enum)
        assert schema["properties"]["confidence"]["type"] == "number"
        assert "enum" not in schema["properties"]["confidence"]

        # Verify both are required
        assert "referral_specialty" in schema["required"]
        assert "confidence" in schema["required"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Unit tests for structured output support.

Tests the StructuredOutputGenerator class and its integration with
OpenAI's structured output format.
"""

import pytest
from kaizen.core.structured_output import (
    StructuredOutputGenerator,
    create_structured_output_config,
)
from kaizen.signatures import InputField, OutputField, Signature


class SimpleQASignature(Signature):
    """Simple Q&A signature for testing."""

    question: str = InputField(description="The question to answer")
    answer: str = OutputField(description="The answer")
    confidence: float = OutputField(description="Confidence score 0-1")


class ComplexSignature(Signature):
    """Complex signature with multiple types."""

    text: str = InputField(description="Input text")
    count: int = OutputField(description="Item count")
    score: float = OutputField(description="Quality score")
    is_valid: bool = OutputField(description="Validation result")
    tags: list = OutputField(description="Tags list")
    metadata: dict = OutputField(description="Metadata object")


class TestStructuredOutputGenerator:
    """Test suite for StructuredOutputGenerator."""

    def test_signature_to_json_schema_basic(self):
        """Test basic JSON schema generation from signature."""
        signature = SimpleQASignature()
        schema = StructuredOutputGenerator.signature_to_json_schema(signature)

        # Verify schema structure
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
        assert schema["additionalProperties"] is False

        # Verify output fields are present
        assert "answer" in schema["properties"]
        assert "confidence" in schema["properties"]

        # Verify types
        assert schema["properties"]["answer"]["type"] == "string"
        assert schema["properties"]["confidence"]["type"] == "number"

        # Verify descriptions
        assert schema["properties"]["answer"]["description"] == "The answer"
        assert (
            schema["properties"]["confidence"]["description"] == "Confidence score 0-1"
        )

        # Verify required fields
        assert "answer" in schema["required"]
        assert "confidence" in schema["required"]

    def test_signature_to_json_schema_all_types(self):
        """Test schema generation with all supported types."""
        signature = ComplexSignature()
        schema = StructuredOutputGenerator.signature_to_json_schema(signature)

        # Verify all types are correctly mapped
        assert schema["properties"]["count"]["type"] == "integer"
        assert schema["properties"]["score"]["type"] == "number"
        assert schema["properties"]["is_valid"]["type"] == "boolean"
        assert schema["properties"]["tags"]["type"] == "array"
        assert schema["properties"]["metadata"]["type"] == "object"

    def test_python_type_to_json_type_mapping(self):
        """Test Python type to JSON type mapping."""
        generator = StructuredOutputGenerator()

        # Test all supported mappings
        assert generator._python_type_to_json_type(str) == "string"
        assert generator._python_type_to_json_type(int) == "integer"
        assert generator._python_type_to_json_type(float) == "number"
        assert generator._python_type_to_json_type(bool) == "boolean"
        assert generator._python_type_to_json_type(list) == "array"
        assert generator._python_type_to_json_type(dict) == "object"

        # Test unknown type defaults to string
        class CustomType:
            pass

        assert generator._python_type_to_json_type(CustomType) == "string"

    def test_generate_system_prompt_with_schema(self):
        """Test system prompt generation with embedded schema."""
        signature = SimpleQASignature()
        prompt = StructuredOutputGenerator.generate_system_prompt_with_schema(signature)

        # Verify prompt contains key elements
        assert "question" in prompt  # Input field mentioned
        assert "answer" in prompt  # Output field mentioned
        assert "confidence" in prompt  # Output field mentioned
        assert "JSON" in prompt or "json" in prompt  # JSON instructions present
        assert "schema" in prompt.lower()  # Schema mentioned

        # Verify it contains instructions
        assert "MUST" in prompt or "must" in prompt  # Strong instruction
        assert "required" in prompt.lower()  # Mentions required fields

    def test_validate_output_success(self):
        """Test output validation with valid output."""
        signature = SimpleQASignature()

        # Valid output
        output = {"answer": "Machine learning is AI", "confidence": 0.95}

        is_valid, errors = StructuredOutputGenerator.validate_output(output, signature)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_output_missing_field(self):
        """Test validation catches missing required fields."""
        signature = SimpleQASignature()

        # Missing 'confidence' field
        output = {"answer": "Machine learning is AI"}

        is_valid, errors = StructuredOutputGenerator.validate_output(output, signature)

        assert is_valid is False
        assert len(errors) == 1
        assert "Missing required field: confidence" in errors[0]

    def test_validate_output_type_mismatch(self):
        """Test validation catches type mismatches."""
        signature = SimpleQASignature()

        # Wrong type for confidence (should be float, got string)
        output = {"answer": "Machine learning is AI", "confidence": "high"}

        is_valid, errors = StructuredOutputGenerator.validate_output(output, signature)

        assert is_valid is False
        assert len(errors) == 1
        # Error message format: "field: Expected type, got actual_type"
        assert "confidence" in errors[0]
        assert "Expected float" in errors[0]

    def test_validate_output_numeric_flexibility(self):
        """Test that int/float are interchangeable for numeric types."""
        signature = ComplexSignature()

        # int for float field should be OK
        output = {
            "count": 10,
            "score": 1,  # int instead of float - should be OK
            "is_valid": True,
            "tags": ["test"],
            "metadata": {"key": "value"},
        }

        is_valid, errors = StructuredOutputGenerator.validate_output(output, signature)

        assert is_valid is True
        assert len(errors) == 0

        # float for int field should also be OK
        output2 = {
            "count": 10.0,  # float instead of int - should be OK
            "score": 0.95,
            "is_valid": True,
            "tags": ["test"],
            "metadata": {"key": "value"},
        }

        is_valid2, errors2 = StructuredOutputGenerator.validate_output(
            output2, signature
        )

        assert is_valid2 is True
        assert len(errors2) == 0

    def test_create_structured_output_config_strict_mode(self):
        """Test strict mode (new OpenAI Structured Outputs format)."""
        signature = SimpleQASignature()
        config = create_structured_output_config(signature, strict=True)

        # Verify new format structure
        assert config["type"] == "json_schema"
        assert "json_schema" in config

        # Verify json_schema nested structure
        json_schema = config["json_schema"]
        assert json_schema["name"] == "response"  # Default name
        assert json_schema["strict"] is True
        assert "schema" in json_schema

        # Verify actual schema
        schema = json_schema["schema"]
        assert schema["type"] == "object"
        assert "answer" in schema["properties"]
        assert "confidence" in schema["properties"]

    def test_create_structured_output_config_legacy_mode(self):
        """Test legacy mode (old json_object format)."""
        signature = SimpleQASignature()
        config = create_structured_output_config(signature, strict=False)

        # Verify legacy format structure (Bug #5 fix: no schema key)
        # OpenAI expects only {"type": "json_object"} for legacy mode
        assert config == {"type": "json_object"}
        assert "schema" not in config, "Legacy mode should not include schema key"

    def test_create_structured_output_config_custom_name(self):
        """Test strict mode with custom schema name."""
        signature = SimpleQASignature()
        config = create_structured_output_config(
            signature, strict=True, name="qa_response"
        )

        # Verify custom name is used
        assert config["json_schema"]["name"] == "qa_response"
        assert config["json_schema"]["strict"] is True

    def test_empty_signature_validation(self):
        """Test validation with signature that has no output fields."""

        class EmptySignature(Signature):
            """Signature with no output fields."""

            input_text: str = InputField(description="Input")

        signature = EmptySignature()
        output = {}

        is_valid, errors = StructuredOutputGenerator.validate_output(output, signature)

        # Should be valid since there are no required output fields
        assert is_valid is True
        assert len(errors) == 0

    def test_schema_no_additional_properties(self):
        """Test that generated schemas disallow additional properties."""
        signature = SimpleQASignature()
        schema = StructuredOutputGenerator.signature_to_json_schema(signature)

        # Verify strict schema (no additional properties allowed)
        assert schema["additionalProperties"] is False


class TestStructuredOutputIntegration:
    """Integration tests for structured output with signatures."""

    def test_signature_to_openai_format(self):
        """Test that generated schema is compatible with OpenAI format."""
        signature = SimpleQASignature()
        # Default is now strict mode (new format)
        config = create_structured_output_config(signature)

        # Verify it matches OpenAI's Structured Outputs format
        assert isinstance(config, dict)
        assert config["type"] == "json_schema"
        assert "json_schema" in config

        json_schema = config["json_schema"]
        assert json_schema["strict"] is True
        assert isinstance(json_schema["schema"], dict)
        assert json_schema["schema"]["type"] == "object"

        # Verify it has all required OpenAI schema elements
        schema = json_schema["schema"]
        assert "properties" in schema
        assert "required" in schema
        assert isinstance(schema["properties"], dict)
        assert isinstance(schema["required"], list)

    def test_round_trip_validation(self):
        """Test creating schema and validating output that matches it."""
        signature = SimpleQASignature()

        # Generate schema
        schema = StructuredOutputGenerator.signature_to_json_schema(signature)

        # Create output that matches schema
        output = {
            "answer": "Test answer",
            "confidence": 0.85,
        }

        # Validate it
        is_valid, errors = StructuredOutputGenerator.validate_output(output, signature)

        assert is_valid is True
        assert len(errors) == 0

    def test_multiple_validation_errors(self):
        """Test that all validation errors are caught and reported."""
        signature = ComplexSignature()

        # Output with multiple issues
        output = {
            "count": "not_an_int",  # Type error
            # Missing: score, is_valid, tags, metadata (4 missing fields)
        }

        is_valid, errors = StructuredOutputGenerator.validate_output(output, signature)

        assert is_valid is False
        # Should have 5 errors: 1 type mismatch + 4 missing fields
        assert len(errors) == 5


class TestStructuredOutputWorkflowIntegration:
    """Test structured output integration with Kaizen workflow system."""

    def test_structured_output_config_format(self):
        """Test that structured output config is properly formatted for workflow use."""
        signature = SimpleQASignature()

        # Test strict mode format
        strict_config = create_structured_output_config(signature, strict=True)
        assert strict_config["type"] == "json_schema"
        assert "json_schema" in strict_config
        assert strict_config["json_schema"]["strict"] is True

        # This format should be passable via provider_config
        provider_config = {"response_format": strict_config}
        assert isinstance(provider_config, dict)
        assert "response_format" in provider_config

    def test_provider_config_merge_logic(self):
        """Test the merge logic for provider_config into generation_config."""
        signature = SimpleQASignature()
        response_format = create_structured_output_config(signature, strict=True)

        # Simulate what LLMAgentNode.run() does
        generation_config = {"temperature": 0.7, "max_tokens": 500}
        provider_config = {"response_format": response_format}

        # Merge provider_config into generation_config (same logic as in llm_agent.py:736-737)
        if provider_config:
            merged_config = {**generation_config, **provider_config}

        # Verify merge worked
        assert "temperature" in merged_config
        assert "max_tokens" in merged_config
        assert "response_format" in merged_config
        assert merged_config["response_format"] == response_format


class TestArrayItemsAndValidation:
    """Test Fix 3 (array items) and Fix 4 (validation constraints)."""

    def test_array_has_items_property(self):
        """Test Fix 3: Array schemas must include 'items' property."""

        class ArraySignature(Signature):
            text: str = InputField(desc="Input text")
            tags: list = OutputField(desc="List of tags")

        sig = ArraySignature()
        schema = StructuredOutputGenerator.signature_to_json_schema(sig)

        # Verify array has items property
        assert "tags" in schema["properties"]
        assert schema["properties"]["tags"]["type"] == "array"
        assert "items" in schema["properties"]["tags"]
        assert schema["properties"]["tags"]["items"] == {"type": "string"}

    def test_enum_validation_constraint(self):
        """Test Fix 4: Enum validation constraints are added to schema."""

        class EnumSignature(Signature):
            text: str = InputField(desc="Input text")
            category: str = OutputField(
                desc="Category",
                metadata={"validation": {"enum": ["positive", "neutral", "negative"]}},
            )

        sig = EnumSignature()
        schema = StructuredOutputGenerator.signature_to_json_schema(sig)

        # Verify enum constraint is in schema
        assert "category" in schema["properties"]
        assert "enum" in schema["properties"]["category"]
        assert schema["properties"]["category"]["enum"] == [
            "positive",
            "neutral",
            "negative",
        ]

    def test_numeric_validation_constraints(self):
        """Test Fix 4: Min/max validation constraints are added to schema."""

        class NumericSignature(Signature):
            text: str = InputField(desc="Input text")
            confidence: float = OutputField(
                desc="Confidence score",
                metadata={"validation": {"min": 0.0, "max": 1.0}},
            )

        sig = NumericSignature()
        schema = StructuredOutputGenerator.signature_to_json_schema(sig)

        # Verify min/max constraints are in schema
        assert "confidence" in schema["properties"]
        assert "minimum" in schema["properties"]["confidence"]
        assert "maximum" in schema["properties"]["confidence"]
        assert schema["properties"]["confidence"]["minimum"] == 0.0
        assert schema["properties"]["confidence"]["maximum"] == 1.0

    def test_pattern_validation_constraint(self):
        """Test Fix 4: Pattern validation constraints are added to schema."""

        class PatternSignature(Signature):
            text: str = InputField(desc="Input text")
            email: str = OutputField(
                desc="Email address",
                metadata={"validation": {"pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"}},
            )

        sig = PatternSignature()
        schema = StructuredOutputGenerator.signature_to_json_schema(sig)

        # Verify pattern constraint is in schema
        assert "email" in schema["properties"]
        assert "pattern" in schema["properties"]["email"]
        assert schema["properties"]["email"]["pattern"] == r"^[\w\.-]+@[\w\.-]+\.\w+$"

    def test_multiple_validation_constraints(self):
        """Test Fix 4: Multiple validation constraints can be applied together."""

        class MultiValidationSignature(Signature):
            text: str = InputField(desc="Input text")
            priority: str = OutputField(
                desc="Priority level",
                metadata={
                    "validation": {
                        "enum": ["low", "medium", "high", "urgent"],
                        "pattern": r"^[a-z]+$",
                    }
                },
            )
            score: int = OutputField(
                desc="Score",
                metadata={"validation": {"min": 0, "max": 100}},
            )

        sig = MultiValidationSignature()
        schema = StructuredOutputGenerator.signature_to_json_schema(sig)

        # Verify priority has both enum and pattern
        assert "priority" in schema["properties"]
        assert "enum" in schema["properties"]["priority"]
        assert "pattern" in schema["properties"]["priority"]

        # Verify score has min and max
        assert "score" in schema["properties"]
        assert "minimum" in schema["properties"]["score"]
        assert "maximum" in schema["properties"]["score"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

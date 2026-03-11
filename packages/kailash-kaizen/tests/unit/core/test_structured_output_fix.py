"""
Unit tests for Bug #5 fix: create_structured_output_config(strict=False) format.

Bug: strict=False returns {"type": "json_object", "schema": {...}} instead of {"type": "json_object"}
Fix: Remove schema key from legacy format per ADR-001

Test Strategy:
1. Test strict=False returns correct format (NO schema key)
2. Test strict=True remains unchanged (json_schema format)
3. Test auto-fallback returns correct format (NO schema key)
4. Test backward compatibility with existing code
"""

from typing import Any, Dict

import pytest
from kaizen.core.structured_output import create_structured_output_config
from kaizen.signatures import InputField, OutputField, Signature


class SimpleQASignature(Signature):
    """Simple Q&A signature for testing."""

    question: str = InputField(description="The question to answer")
    answer: str = OutputField(description="The answer")
    confidence: float = OutputField(description="Confidence score 0-1")


class FlexibleSignature(Signature):
    """Signature with Dict[str, Any] that triggers auto-fallback."""

    input_text: str = InputField(description="Input text")
    result: Dict[str, Any] = OutputField(description="Flexible result")


class TestBug5Fix:
    """Test suite for Bug #5 fix: strict=False format correction."""

    def test_strict_false_returns_json_object_only(self):
        """
        Test that strict=False returns {"type": "json_object"} with NO schema key.

        This is the core bug fix test.
        Expected: {"type": "json_object"}
        Bug behavior: {"type": "json_object", "schema": {...}}
        """
        signature = SimpleQASignature()
        config = create_structured_output_config(signature, strict=False)

        # Core assertion: Only type key, NO schema key
        assert config == {"type": "json_object"}, (
            f"Expected {{'type': 'json_object'}}, got {config}. "
            "strict=False should NOT include schema key."
        )

        # Verify no schema key exists
        assert "schema" not in config, (
            "strict=False should not include 'schema' key in response. "
            "OpenAI legacy format only accepts {'type': 'json_object'}."
        )

        # Verify correct type
        assert (
            config["type"] == "json_object"
        ), "strict=False must use 'json_object' type."

    def test_strict_true_unchanged(self):
        """
        Test that strict=True still works correctly (no regression).

        Expected: {"type": "json_schema", "json_schema": {"name": "...", "strict": True, "schema": {...}}}
        """
        signature = SimpleQASignature()
        config = create_structured_output_config(signature, strict=True)

        # Verify new format structure
        assert (
            config["type"] == "json_schema"
        ), "strict=True must use 'json_schema' type"
        assert "json_schema" in config, "strict=True must have 'json_schema' key"

        # Verify json_schema nested structure
        json_schema = config["json_schema"]
        assert json_schema["name"] == "response", "Default name should be 'response'"
        assert json_schema["strict"] is True, "strict flag should be True"
        assert "schema" in json_schema, "Schema must be nested in json_schema key"

        # Verify actual schema structure
        schema = json_schema["schema"]
        assert schema["type"] == "object"
        assert "answer" in schema["properties"]
        assert "confidence" in schema["properties"]

    def test_auto_fallback_returns_json_object(self):
        """
        Test that auto-fallback from strict=True to strict=False returns correct format.

        When signature has Dict[str, Any] (incompatible with strict mode),
        auto-fallback should return {"type": "json_object"} with NO schema key.
        """
        signature = FlexibleSignature()

        # This should trigger auto-fallback to strict=False
        config = create_structured_output_config(
            signature, strict=True, auto_fallback=True
        )

        # Should fallback to correct legacy format
        assert config == {
            "type": "json_object"
        }, f"Auto-fallback should return {{'type': 'json_object'}}, got {config}"

        # Verify no schema key after fallback
        assert (
            "schema" not in config
        ), "Auto-fallback to strict=False should not include schema key"

    def test_strict_false_explicit_parameter(self):
        """Test explicit strict=False parameter (not just default)."""
        signature = SimpleQASignature()
        config = create_structured_output_config(signature, strict=False)

        # Must be exact format
        assert config == {"type": "json_object"}
        assert len(config) == 1, "Config should only have 'type' key"

    def test_backward_compatibility_openai_api(self):
        """
        Test that the fixed format is compatible with OpenAI API.

        OpenAI expects: {"type": "json_object"} for legacy mode
        NOT: {"type": "json_object", "schema": {...}}
        """
        signature = SimpleQASignature()
        config = create_structured_output_config(signature, strict=False)

        # Simulate OpenAI API call structure
        expected_openai_format = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "test"}],
            "response_format": {"type": "json_object"},  # This is what OpenAI expects
        }

        # Our config should match OpenAI's expected format
        assert (
            config == expected_openai_format["response_format"]
        ), "Config format must match OpenAI API expectations"

    def test_strict_false_with_complex_signature(self):
        """Test strict=False with complex signature types."""

        class ComplexSignature(Signature):
            text: str = InputField(description="Input")
            count: int = OutputField(description="Count")
            score: float = OutputField(description="Score")
            valid: bool = OutputField(description="Valid")
            tags: list = OutputField(description="Tags")
            metadata: dict = OutputField(description="Metadata")

        signature = ComplexSignature()
        config = create_structured_output_config(signature, strict=False)

        # Even with complex types, strict=False should only return type
        assert config == {"type": "json_object"}
        assert "schema" not in config

    def test_strict_false_no_side_effects(self):
        """Test that calling strict=False doesn't affect subsequent strict=True calls."""
        signature = SimpleQASignature()

        # Call strict=False first
        config_false = create_structured_output_config(signature, strict=False)
        assert config_false == {"type": "json_object"}

        # Call strict=True after
        config_true = create_structured_output_config(signature, strict=True)
        assert config_true["type"] == "json_schema"
        assert "json_schema" in config_true

        # Call strict=False again
        config_false_2 = create_structured_output_config(signature, strict=False)
        assert config_false_2 == {"type": "json_object"}


class TestRegressionPrevention:
    """Regression tests to ensure fix doesn't break existing functionality."""

    def test_strict_true_custom_name(self):
        """Test strict=True with custom name still works."""
        signature = SimpleQASignature()
        config = create_structured_output_config(
            signature, strict=True, name="custom_response"
        )

        assert config["type"] == "json_schema"
        assert config["json_schema"]["name"] == "custom_response"
        assert config["json_schema"]["strict"] is True

    def test_auto_fallback_disabled_raises_error(self):
        """Test that auto_fallback=False raises ValueError for incompatible types."""
        signature = FlexibleSignature()

        with pytest.raises(ValueError, match="OpenAI strict mode incompatibility"):
            create_structured_output_config(signature, strict=True, auto_fallback=False)

    def test_default_parameters(self):
        """Test default parameters behavior."""
        signature = SimpleQASignature()

        # Default should be strict=True
        config = create_structured_output_config(signature)
        assert config["type"] == "json_schema"
        assert config["json_schema"]["strict"] is True

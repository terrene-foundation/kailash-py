"""Tests for StructuredOutput helper class.

Covers the fluent API for explicit structured output configuration.
"""

import pytest

from kaizen.core.structured_output import StructuredOutput
from kaizen.signatures import InputField, OutputField, Signature


class SimpleSig(Signature):
    """Simple test signature."""

    question: str = InputField(desc="A question")
    answer: str = OutputField(desc="The answer")


class ComplexSig(Signature):
    """Complex signature with multiple types."""

    text: str = InputField(desc="Input text")
    summary: str = OutputField(desc="Summary")
    confidence: float = OutputField(desc="Confidence 0-1")
    tags: list = OutputField(desc="Tags")


class TestStructuredOutputFromSignature:
    """Test StructuredOutput.from_signature()."""

    def test_creates_from_simple_signature(self):
        so = StructuredOutput.from_signature(SimpleSig())
        assert so.to_dict() is not None
        schema = so.to_dict()
        assert "properties" in schema
        assert "answer" in schema["properties"]

    def test_uses_signature_class_name(self):
        so = StructuredOutput.from_signature(SimpleSig())
        result = so.for_provider("openai")
        assert result["json_schema"]["name"] == "SimpleSig"

    def test_uses_custom_name(self):
        so = StructuredOutput.from_signature(SimpleSig(), name="custom_name")
        result = so.for_provider("openai")
        assert result["json_schema"]["name"] == "custom_name"


class TestStructuredOutputForProvider:
    """Test StructuredOutput.for_provider()."""

    def test_openai_returns_json_schema_strict(self):
        so = StructuredOutput.from_signature(SimpleSig())
        result = so.for_provider("openai")
        assert result["type"] == "json_schema"
        assert result["json_schema"]["strict"] is True
        assert "schema" in result["json_schema"]

    def test_azure_returns_json_object(self):
        so = StructuredOutput.from_signature(SimpleSig())
        result = so.for_provider("azure")
        assert result == {"type": "json_object"}

    def test_google_returns_json_object(self):
        so = StructuredOutput.from_signature(SimpleSig())
        result = so.for_provider("google")
        assert result == {"type": "json_object"}

    def test_gemini_returns_json_object(self):
        so = StructuredOutput.from_signature(SimpleSig())
        result = so.for_provider("gemini")
        assert result == {"type": "json_object"}

    def test_case_insensitive(self):
        so = StructuredOutput.from_signature(SimpleSig())
        assert so.for_provider("OpenAI")["type"] == "json_schema"
        assert so.for_provider("AZURE")["type"] == "json_object"


class TestStructuredOutputPromptHint:
    """Test StructuredOutput.prompt_hint()."""

    def test_contains_json(self):
        so = StructuredOutput.from_signature(SimpleSig())
        hint = so.prompt_hint()
        assert "json" in hint.lower()
        assert "JSON object" in hint

    def test_is_string(self):
        so = StructuredOutput.from_signature(SimpleSig())
        assert isinstance(so.prompt_hint(), str)


class TestStructuredOutputToDict:
    """Test StructuredOutput.to_dict()."""

    def test_returns_schema_dict(self):
        so = StructuredOutput.from_signature(ComplexSig())
        schema = so.to_dict()
        assert isinstance(schema, dict)
        assert "properties" in schema

    def test_returns_copy(self):
        so = StructuredOutput.from_signature(SimpleSig())
        d1 = so.to_dict()
        d2 = so.to_dict()
        assert d1 == d2
        d1["extra"] = "modified"
        assert "extra" not in so.to_dict()

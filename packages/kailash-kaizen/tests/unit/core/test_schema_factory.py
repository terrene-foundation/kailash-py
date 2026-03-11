"""
Unit tests for SchemaFactory.

Tests the automatic schema adaptation for provider constraints,
particularly OpenAI Structured Outputs API strict mode compatibility.

Author: Kailash Kaizen Team
Version: 0.6.4
"""

from typing import TypedDict

import pytest
from kaizen.core.config import BaseAgentConfig
from kaizen.core.schema_factory import SchemaFactory
from typing_extensions import NotRequired


# Test schemas
class SimpleSchema(TypedDict):
    """Schema with all required fields."""

    name: str
    age: int
    active: bool


class SchemaWithOptional(TypedDict):
    """Schema with NotRequired fields."""

    name: str
    age: int
    tools: NotRequired[list]
    dependencies: NotRequired[dict]


class FullyOptionalSchema(TypedDict):
    """Schema with all NotRequired fields."""

    tools: NotRequired[list]
    metadata: NotRequired[dict]
    notes: NotRequired[str]


# Tests
class TestSchemaFactory:
    """Test suite for SchemaFactory."""

    def test_is_openai_strict_mode_true(self):
        """Test detection of OpenAI strict mode enabled."""
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            provider_config={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"strict": True, "name": "test"},
                }
            },
        )

        result = SchemaFactory._is_openai_strict_mode(config)

        assert result is True

    def test_is_openai_strict_mode_false_non_openai(self):
        """Test detection when provider is not OpenAI."""
        config = BaseAgentConfig(
            llm_provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            provider_config={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"strict": True},
                }
            },
        )

        result = SchemaFactory._is_openai_strict_mode(config)

        assert result is False

    def test_is_openai_strict_mode_false_strict_false(self):
        """Test detection when strict=False."""
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            provider_config={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"strict": False},
                }
            },
        )

        result = SchemaFactory._is_openai_strict_mode(config)

        assert result is False

    def test_is_openai_strict_mode_false_no_provider_config(self):
        """Test detection when no provider_config."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4o-mini")

        result = SchemaFactory._is_openai_strict_mode(config)

        assert result is False

    def test_is_openai_strict_mode_false_legacy_json_mode(self):
        """Test detection for legacy JSON mode."""
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            provider_config={"response_format": {"type": "json_object"}},
        )

        result = SchemaFactory._is_openai_strict_mode(config)

        assert result is False

    def test_make_all_required_simple_schema(self):
        """Test that simple schema (all required) stays unchanged."""
        adapted = SchemaFactory._make_all_required(SimpleSchema)

        # Check annotations
        annotations = adapted.__annotations__
        assert "name" in annotations
        assert "age" in annotations
        assert "active" in annotations
        assert annotations["name"] == str
        assert annotations["age"] == int
        assert annotations["active"] == bool

    def test_make_all_required_with_optional(self):
        """Test unwrapping NotRequired fields."""
        adapted = SchemaFactory._make_all_required(SchemaWithOptional)

        # Check annotations
        annotations = adapted.__annotations__
        assert "name" in annotations
        assert "age" in annotations
        assert "tools" in annotations
        assert "dependencies" in annotations

        # Check types (NotRequired should be unwrapped)
        assert annotations["name"] == str
        assert annotations["age"] == int
        assert annotations["tools"] == list  # Unwrapped from NotRequired[list]
        assert annotations["dependencies"] == dict  # Unwrapped from NotRequired[dict]

    def test_make_all_required_fully_optional(self):
        """Test unwrapping all NotRequired fields."""
        adapted = SchemaFactory._make_all_required(FullyOptionalSchema)

        # Check annotations
        annotations = adapted.__annotations__
        assert "tools" in annotations
        assert "metadata" in annotations
        assert "notes" in annotations

        # Check types (all NotRequired unwrapped)
        assert annotations["tools"] == list
        assert annotations["metadata"] == dict
        assert annotations["notes"] == str

    def test_adapt_for_provider_openai_strict(self):
        """Test adaptation for OpenAI strict mode."""
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            provider_config={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"strict": True, "name": "test"},
                }
            },
        )

        adapted = SchemaFactory.adapt_for_provider(SchemaWithOptional, config)

        # Should unwrap NotRequired fields
        annotations = adapted.__annotations__
        assert annotations["tools"] == list
        assert annotations["dependencies"] == dict

    def test_adapt_for_provider_non_strict(self):
        """Test adaptation for non-strict mode (should preserve original)."""
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            provider_config={"response_format": {"type": "json_object"}},
        )

        adapted = SchemaFactory.adapt_for_provider(SchemaWithOptional, config)

        # Should preserve original schema
        assert adapted == SchemaWithOptional

    def test_adapt_for_provider_non_openai(self):
        """Test adaptation for non-OpenAI provider (should preserve original)."""
        config = BaseAgentConfig(
            llm_provider="anthropic", model="claude-3-5-sonnet-20241022"
        )

        adapted = SchemaFactory.adapt_for_provider(SchemaWithOptional, config)

        # Should preserve original schema
        assert adapted == SchemaWithOptional

    def test_get_empty_default_list(self):
        """Test empty default for list type."""
        result = SchemaFactory.get_empty_default(list)
        assert result == []

    def test_get_empty_default_dict(self):
        """Test empty default for dict type."""
        result = SchemaFactory.get_empty_default(dict)
        assert result == {}

    def test_get_empty_default_str(self):
        """Test empty default for str type."""
        result = SchemaFactory.get_empty_default(str)
        assert result == ""

    def test_get_empty_default_int(self):
        """Test empty default for int type."""
        result = SchemaFactory.get_empty_default(int)
        assert result == 0

    def test_get_empty_default_float(self):
        """Test empty default for float type."""
        result = SchemaFactory.get_empty_default(float)
        assert result == 0.0

    def test_get_empty_default_bool(self):
        """Test empty default for bool type."""
        result = SchemaFactory.get_empty_default(bool)
        assert result is False

    def test_schema_name_generation(self):
        """Test that adapted schema has appropriate name."""
        adapted = SchemaFactory._make_all_required(SchemaWithOptional)

        # Should append "Strict" to original name
        assert adapted.__name__ == "SchemaWithOptionalStrict"

    def test_multiple_adaptations_idempotent(self):
        """Test that adapting multiple times is safe."""
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            provider_config={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"strict": True, "name": "test"},
                }
            },
        )

        # Adapt twice
        adapted1 = SchemaFactory.adapt_for_provider(SchemaWithOptional, config)
        adapted2 = SchemaFactory.adapt_for_provider(adapted1, config)

        # Should produce equivalent schemas
        assert adapted1.__annotations__ == adapted2.__annotations__

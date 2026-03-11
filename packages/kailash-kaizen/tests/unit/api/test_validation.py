"""
Unit Tests for Configuration Validation (Tier 1)

Tests the configuration validation for helpful error messages:
- ConfigurationError exception
- Model-runtime compatibility
- Capability consistency
- Full configuration validation
"""

import pytest

from kaizen.api.types import AgentCapabilities, ExecutionMode, MemoryDepth, ToolAccess
from kaizen.api.validation import (
    ConfigurationError,
    get_recommended_configuration,
    validate_capability_consistency,
    validate_configuration,
    validate_model_name,
    validate_model_runtime_compatibility,
)


class TestConfigurationError:
    """Tests for ConfigurationError exception."""

    def test_create_basic(self):
        """Test creating basic error."""
        error = ConfigurationError("Invalid configuration")

        assert str(error) == "Invalid configuration"
        assert error.message == "Invalid configuration"
        assert error.field is None
        assert error.value is None
        assert error.suggestions == []

    def test_create_with_field(self):
        """Test creating error with field info."""
        error = ConfigurationError(
            message="Invalid model",
            field="model",
            value="invalid-model",
        )

        assert error.field == "model"
        assert error.value == "invalid-model"

    def test_create_with_suggestions(self):
        """Test creating error with suggestions."""
        error = ConfigurationError(
            message="Invalid model",
            suggestions=[
                'Use model="gpt-4"',
                'Use model="claude-3-opus"',
            ],
        )

        error_str = str(error)
        assert "Suggestions:" in error_str
        assert 'Use model="gpt-4"' in error_str

    def test_to_dict(self):
        """Test to_dict method."""
        error = ConfigurationError(
            message="Test error",
            field="test_field",
            value="test_value",
            suggestions=["Fix it"],
        )

        data = error.to_dict()

        assert data["message"] == "Test error"
        assert data["field"] == "test_field"
        assert data["value"] == "test_value"
        assert data["suggestions"] == ["Fix it"]


class TestModelRuntimeCompatibility:
    """Tests for model-runtime compatibility validation."""

    def test_local_supports_all_models(self):
        """Test local runtime supports all models."""
        models = [
            "gpt-4",
            "claude-3-opus",
            "gemini-1.5-pro",
            "llama3.2",
            "custom-model",
        ]

        for model in models:
            is_valid, error = validate_model_runtime_compatibility(model, "local")
            assert is_valid is True
            assert error is None

    def test_local_aliases(self):
        """Test local runtime aliases."""
        is_valid1, _ = validate_model_runtime_compatibility("gpt-4", "kaizen")
        is_valid2, _ = validate_model_runtime_compatibility("gpt-4", "native")

        assert is_valid1 is True
        assert is_valid2 is True

    def test_claude_code_with_claude_model(self):
        """Test claude_code runtime with Claude models."""
        is_valid, error = validate_model_runtime_compatibility(
            "claude-3-opus", "claude_code"
        )
        assert is_valid is True
        assert error is None

    def test_claude_code_with_gpt_model(self):
        """Test claude_code runtime with GPT model fails."""
        is_valid, error = validate_model_runtime_compatibility("gpt-4", "claude_code")
        assert is_valid is False
        assert error is not None
        assert "not compatible" in error.message

    def test_error_includes_suggestions(self):
        """Test error includes helpful suggestions."""
        is_valid, error = validate_model_runtime_compatibility("gpt-4", "claude_code")

        assert error is not None
        assert len(error.suggestions) > 0
        assert any("local" in s.lower() for s in error.suggestions)


class TestCapabilityConsistency:
    """Tests for capability consistency validation."""

    def test_valid_capabilities(self):
        """Test valid capabilities pass validation."""
        caps = AgentCapabilities(
            execution_modes=[ExecutionMode.AUTONOMOUS],
            max_memory_depth=MemoryDepth.SESSION,
            tool_access=ToolAccess.CONSTRAINED,
            max_cycles=50,
            max_turns=30,
            timeout_seconds=300.0,
        )

        is_valid, errors = validate_capability_consistency(caps)
        assert is_valid is True
        assert errors == []

    def test_invalid_max_cycles(self):
        """Test invalid max_cycles fails."""
        caps = AgentCapabilities(max_cycles=0)

        is_valid, errors = validate_capability_consistency(caps)
        assert is_valid is False
        assert len(errors) == 1
        assert errors[0].field == "max_cycles"

    def test_invalid_max_turns(self):
        """Test invalid max_turns fails."""
        caps = AgentCapabilities(max_turns=0)

        is_valid, errors = validate_capability_consistency(caps)
        assert is_valid is False
        assert any(e.field == "max_turns" for e in errors)

    def test_invalid_timeout(self):
        """Test invalid timeout fails."""
        caps = AgentCapabilities(timeout_seconds=0)

        is_valid, errors = validate_capability_consistency(caps)
        assert is_valid is False
        assert any(e.field == "timeout_seconds" for e in errors)

    def test_negative_max_tool_calls(self):
        """Test negative max_tool_calls fails."""
        caps = AgentCapabilities(max_tool_calls=-1)

        is_valid, errors = validate_capability_consistency(caps)
        assert is_valid is False
        assert any(e.field == "max_tool_calls" for e in errors)

    def test_conflicting_tool_lists(self):
        """Test conflicting allowed/denied tools fails."""
        caps = AgentCapabilities(
            allowed_tools=["read", "write", "bash"],
            denied_tools=["bash", "rm"],  # bash is in both
        )

        is_valid, errors = validate_capability_consistency(caps)
        assert is_valid is False
        assert any("allowed_tools" in str(e.field) for e in errors)


class TestFullConfigValidation:
    """Tests for full configuration validation."""

    def test_valid_configuration(self):
        """Test valid configuration passes."""
        is_valid, errors = validate_configuration(
            model="gpt-4",
            runtime="local",
            execution_mode="autonomous",
            memory="session",
            tool_access="constrained",
            max_cycles=50,
        )

        assert is_valid is True
        assert errors == []

    def test_missing_model(self):
        """Test missing model fails."""
        is_valid, errors = validate_configuration(
            model="",
            runtime="local",
        )

        assert is_valid is False
        assert any(e.field == "model" for e in errors)

    def test_invalid_execution_mode(self):
        """Test invalid execution mode fails."""
        is_valid, errors = validate_configuration(
            model="gpt-4",
            execution_mode="invalid_mode",
        )

        assert is_valid is False
        assert any(e.field == "execution_mode" for e in errors)

    def test_invalid_memory_shortcut(self):
        """Test invalid memory shortcut fails."""
        is_valid, errors = validate_configuration(
            model="gpt-4",
            memory="invalid_memory",
        )

        assert is_valid is False
        assert any(e.field == "memory" for e in errors)

    def test_invalid_tool_access(self):
        """Test invalid tool access fails."""
        is_valid, errors = validate_configuration(
            model="gpt-4",
            tool_access="invalid_access",
        )

        assert is_valid is False
        assert any(e.field == "tool_access" for e in errors)

    def test_invalid_max_cycles_type(self):
        """Test invalid max_cycles type fails."""
        is_valid, errors = validate_configuration(
            model="gpt-4",
            max_cycles="not_a_number",
        )

        assert is_valid is False
        assert any(e.field == "max_cycles" for e in errors)

    def test_invalid_timeout_type(self):
        """Test invalid timeout type fails."""
        is_valid, errors = validate_configuration(
            model="gpt-4",
            timeout_seconds="not_a_number",
        )

        assert is_valid is False
        assert any(e.field == "timeout_seconds" for e in errors)

    def test_model_runtime_incompatibility(self):
        """Test model-runtime incompatibility detected."""
        is_valid, errors = validate_configuration(
            model="gpt-4",
            runtime="claude_code",  # GPT on Claude runtime
        )

        assert is_valid is False
        assert any(e.field == "runtime" for e in errors)


class TestValidateModelName:
    """Tests for model name validation."""

    def test_known_models_valid(self):
        """Test known models are valid."""
        models = ["gpt-4", "claude-3-opus", "gemini-1.5-pro", "llama3.2", "o1"]

        for model in models:
            is_valid, suggestion = validate_model_name(model)
            assert is_valid is True

    def test_unknown_model_with_suggestion(self):
        """Test unknown model returns suggestion."""
        is_valid, suggestion = validate_model_name("unknown-model-xyz")

        # Still valid (could be custom model)
        assert is_valid is True
        # But includes a suggestion
        assert suggestion is not None
        assert "not a recognized model" in suggestion


class TestGetRecommendedConfiguration:
    """Tests for recommended configuration."""

    def test_code_task_recommendation(self):
        """Test code task gets autonomous + constrained."""
        config = get_recommended_configuration("Implement a REST API endpoint")

        assert config["execution_mode"] == "autonomous"
        assert config["tool_access"] == "constrained"

    def test_research_task_recommendation(self):
        """Test research task gets autonomous + read_only."""
        config = get_recommended_configuration(
            "Research best practices for authentication"
        )

        assert config["execution_mode"] == "autonomous"
        assert config["tool_access"] == "read_only"

    def test_simple_qa_recommendation(self):
        """Test simple Q&A gets single + none."""
        config = get_recommended_configuration("What is IRP?")

        assert config["execution_mode"] == "single"
        assert config["tool_access"] == "none"

    def test_conversation_task_recommendation(self):
        """Test conversation task gets multi mode."""
        config = get_recommended_configuration("Help me step by step with this task")

        assert config["execution_mode"] == "multi"
        assert config["memory"] == "session"

    def test_custom_model_preserved(self):
        """Test custom model is preserved."""
        config = get_recommended_configuration("Simple question", model="claude-3-opus")

        assert config["model"] == "claude-3-opus"

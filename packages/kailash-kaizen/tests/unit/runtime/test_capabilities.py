"""
Unit Tests for Runtime Capabilities (Tier 1)

Tests RuntimeCapabilities dataclass and capability checking logic.

Coverage:
- Capability creation and defaults
- supports() method with various inputs
- meets_requirements() method
- get_missing_requirements() method
- estimated_cost() calculation
- Serialization (to_dict, from_dict)
- Pre-defined capabilities
"""

import pytest

from kaizen.runtime.capabilities import (
    CLAUDE_CODE_CAPABILITIES,
    GEMINI_CLI_CAPABILITIES,
    KAIZEN_LOCAL_CAPABILITIES,
    OPENAI_CODEX_CAPABILITIES,
    RuntimeCapabilities,
)


class TestRuntimeCapabilities:
    """Test RuntimeCapabilities dataclass."""

    def test_create_minimal_capabilities(self):
        """Test creating capabilities with minimal fields."""
        caps = RuntimeCapabilities(
            runtime_name="test_runtime",
            provider="test_provider",
        )

        assert caps.runtime_name == "test_runtime"
        assert caps.provider == "test_provider"
        assert caps.version == "1.0.0"
        assert caps.supports_streaming is True  # Default
        assert caps.supports_tool_calling is True  # Default

    def test_create_full_capabilities(self):
        """Test creating capabilities with all fields."""
        caps = RuntimeCapabilities(
            runtime_name="full_runtime",
            provider="my_company",
            version="2.0.0",
            supports_streaming=True,
            supports_tool_calling=True,
            supports_parallel_tools=True,
            supports_vision=True,
            supports_audio=True,
            supports_code_execution=True,
            supports_file_access=True,
            supports_web_access=True,
            supports_interrupt=True,
            max_context_tokens=100000,
            max_output_tokens=4096,
            cost_per_1k_input_tokens=0.01,
            cost_per_1k_output_tokens=0.03,
            typical_latency_ms=200.0,
            cold_start_ms=500.0,
            native_tools=["tool1", "tool2"],
            supported_models=["model-a", "model-b"],
            metadata={"custom": "value"},
        )

        assert caps.supports_vision is True
        assert caps.max_context_tokens == 100000
        assert len(caps.native_tools) == 2


class TestSupportsMethod:
    """Test the supports() method."""

    @pytest.fixture
    def full_caps(self):
        """Create capabilities with all features enabled."""
        return RuntimeCapabilities(
            runtime_name="full",
            provider="test",
            supports_streaming=True,
            supports_tool_calling=True,
            supports_parallel_tools=True,
            supports_vision=True,
            supports_audio=True,
            supports_code_execution=True,
            supports_file_access=True,
            supports_web_access=True,
            supports_interrupt=True,
            native_tools=["read_file", "bash_command"],
        )

    @pytest.fixture
    def minimal_caps(self):
        """Create capabilities with minimal features."""
        return RuntimeCapabilities(
            runtime_name="minimal",
            provider="test",
            supports_streaming=True,
            supports_tool_calling=True,
            supports_parallel_tools=False,
            supports_vision=False,
            supports_audio=False,
            supports_code_execution=False,
            supports_file_access=False,
            supports_web_access=False,
            supports_interrupt=False,
        )

    def test_supports_basic_capability(self, full_caps, minimal_caps):
        """Test checking basic capabilities."""
        # Full caps supports everything
        assert full_caps.supports("vision") is True
        assert full_caps.supports("file_access") is True
        assert full_caps.supports("code_execution") is True

        # Minimal caps only supports basics
        assert minimal_caps.supports("streaming") is True
        assert minimal_caps.supports("vision") is False
        assert minimal_caps.supports("file_access") is False

    def test_supports_tool_requirement(self, full_caps):
        """Test checking tool requirements."""
        assert full_caps.supports("tool:read_file") is True
        assert full_caps.supports("tool:bash_command") is True
        assert full_caps.supports("tool:nonexistent") is False

    def test_supports_aliases(self, full_caps, minimal_caps):
        """Test capability aliases."""
        # Image -> vision
        assert full_caps.supports("image") is True
        assert full_caps.supports("images") is True
        assert minimal_caps.supports("image") is False

        # File -> file_access
        assert full_caps.supports("file") is True
        assert full_caps.supports("files") is True

        # Web -> web_access
        assert full_caps.supports("web") is True
        assert full_caps.supports("http") is True

        # Bash -> code_execution
        assert full_caps.supports("bash") is True
        assert full_caps.supports("shell") is True

    def test_supports_case_insensitive(self, full_caps):
        """Test case insensitivity."""
        assert full_caps.supports("VISION") is True
        assert full_caps.supports("Vision") is True
        assert full_caps.supports("FILE_ACCESS") is True


class TestMeetsRequirements:
    """Test meets_requirements() method."""

    @pytest.fixture
    def caps(self):
        return RuntimeCapabilities(
            runtime_name="test",
            provider="test",
            supports_vision=True,
            supports_file_access=True,
            supports_web_access=True,
            supports_code_execution=False,
            supports_audio=False,
        )

    def test_meets_all_requirements(self, caps):
        """Test when all requirements are met."""
        reqs = ["vision", "file_access"]
        assert caps.meets_requirements(reqs) is True

    def test_fails_one_requirement(self, caps):
        """Test when one requirement is not met."""
        reqs = ["vision", "audio"]  # audio is False
        assert caps.meets_requirements(reqs) is False

    def test_empty_requirements(self, caps):
        """Test empty requirements list always passes."""
        assert caps.meets_requirements([]) is True

    def test_single_requirement(self, caps):
        """Test single requirement."""
        assert caps.meets_requirements(["vision"]) is True
        assert caps.meets_requirements(["audio"]) is False


class TestGetMissingRequirements:
    """Test get_missing_requirements() method."""

    @pytest.fixture
    def caps(self):
        return RuntimeCapabilities(
            runtime_name="test",
            provider="test",
            supports_vision=True,
            supports_file_access=True,
            supports_audio=False,
            supports_code_execution=False,
        )

    def test_all_met(self, caps):
        """Test when all requirements are met."""
        missing = caps.get_missing_requirements(["vision", "file_access"])
        assert missing == []

    def test_some_missing(self, caps):
        """Test when some requirements are missing."""
        missing = caps.get_missing_requirements(["vision", "audio", "code_execution"])
        assert "audio" in missing
        assert "code_execution" in missing
        assert "vision" not in missing

    def test_all_missing(self, caps):
        """Test when all requirements are missing."""
        missing = caps.get_missing_requirements(["audio", "code_execution"])
        assert len(missing) == 2


class TestEstimatedCost:
    """Test estimated_cost() method."""

    def test_calculate_cost(self):
        """Test cost calculation."""
        caps = RuntimeCapabilities(
            runtime_name="test",
            provider="test",
            cost_per_1k_input_tokens=0.01,  # $0.01 per 1k input
            cost_per_1k_output_tokens=0.03,  # $0.03 per 1k output
        )

        # 2000 input + 1000 output
        cost = caps.estimated_cost(input_tokens=2000, output_tokens=1000)

        # Expected: (2000/1000)*0.01 + (1000/1000)*0.03 = 0.02 + 0.03 = 0.05
        assert cost == pytest.approx(0.05)

    def test_cost_with_no_pricing(self):
        """Test when pricing is not configured."""
        caps = RuntimeCapabilities(
            runtime_name="test",
            provider="test",
        )

        cost = caps.estimated_cost(1000, 1000)
        assert cost is None


class TestSerialization:
    """Test to_dict and from_dict methods."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        caps = RuntimeCapabilities(
            runtime_name="ser_test",
            provider="test_co",
            version="1.2.3",
            supports_vision=True,
            max_context_tokens=50000,
            native_tools=["tool1"],
        )

        data = caps.to_dict()

        assert data["runtime_name"] == "ser_test"
        assert data["provider"] == "test_co"
        assert data["version"] == "1.2.3"
        assert data["supports_vision"] is True
        assert data["max_context_tokens"] == 50000
        assert data["native_tools"] == ["tool1"]

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "runtime_name": "deser_test",
            "provider": "my_provider",
            "version": "3.0.0",
            "supports_vision": True,
            "supports_audio": True,
            "max_context_tokens": 100000,
            "native_tools": ["read", "write"],
        }

        caps = RuntimeCapabilities.from_dict(data)

        assert caps.runtime_name == "deser_test"
        assert caps.provider == "my_provider"
        assert caps.version == "3.0.0"
        assert caps.supports_vision is True
        assert caps.supports_audio is True
        assert caps.max_context_tokens == 100000
        assert "read" in caps.native_tools

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = RuntimeCapabilities(
            runtime_name="roundtrip",
            provider="test",
            supports_vision=True,
            supports_file_access=True,
            native_tools=["tool1", "tool2"],
            metadata={"key": "value"},
        )

        data = original.to_dict()
        restored = RuntimeCapabilities.from_dict(data)

        assert restored.runtime_name == original.runtime_name
        assert restored.supports_vision == original.supports_vision
        assert restored.native_tools == original.native_tools


class TestPredefinedCapabilities:
    """Test pre-defined capability constants."""

    def test_kaizen_local_capabilities(self):
        """Test KAIZEN_LOCAL_CAPABILITIES."""
        caps = KAIZEN_LOCAL_CAPABILITIES

        assert caps.runtime_name == "kaizen_local"
        assert caps.provider == "kaizen"
        assert caps.supports_tool_calling is True
        assert caps.supports_file_access is True
        assert caps.supports_code_execution is True
        assert "read_file" in caps.native_tools
        assert "bash_command" in caps.native_tools

    def test_claude_code_capabilities(self):
        """Test CLAUDE_CODE_CAPABILITIES."""
        caps = CLAUDE_CODE_CAPABILITIES

        assert caps.runtime_name == "claude_code"
        assert caps.provider == "anthropic"
        assert caps.supports_vision is True
        assert caps.supports_interrupt is True
        assert "Read" in caps.native_tools
        assert "Bash" in caps.native_tools

    def test_openai_codex_capabilities(self):
        """Test OPENAI_CODEX_CAPABILITIES."""
        caps = OPENAI_CODEX_CAPABILITIES

        assert caps.runtime_name == "openai_codex"
        assert caps.provider == "openai"
        assert caps.supports_parallel_tools is True
        assert "gpt-4-turbo" in caps.supported_models

    def test_gemini_cli_capabilities(self):
        """Test GEMINI_CLI_CAPABILITIES."""
        caps = GEMINI_CLI_CAPABILITIES

        assert caps.runtime_name == "gemini_cli"
        assert caps.provider == "google"
        assert caps.supports_audio is True  # Gemini supports audio
        assert caps.max_context_tokens == 1000000  # Large context

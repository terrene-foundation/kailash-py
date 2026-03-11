"""
Unit Tests for Capability Presets (Tier 1)

Tests the pre-configured capability presets:
- Each preset returns valid configuration
- Presets have expected defaults
- Overrides work correctly
"""

import pytest

from kaizen.api.presets import CapabilityPresets, preset


class TestQAAssistantPreset:
    """Tests for qa_assistant preset."""

    def test_returns_config(self):
        """Test returns configuration dict."""
        config = CapabilityPresets.qa_assistant()

        assert isinstance(config, dict)
        assert "model" in config
        assert "execution_mode" in config

    def test_default_values(self):
        """Test default values."""
        config = CapabilityPresets.qa_assistant()

        assert config["execution_mode"] == "single"
        assert config["memory"] == "stateless"
        assert config["tool_access"] == "none"

    def test_custom_model(self):
        """Test custom model."""
        config = CapabilityPresets.qa_assistant(model="claude-3-opus")

        assert config["model"] == "claude-3-opus"

    def test_override_values(self):
        """Test override values."""
        config = CapabilityPresets.qa_assistant(timeout_seconds=120.0)

        assert config["timeout_seconds"] == 120.0


class TestTutorPreset:
    """Tests for tutor preset."""

    def test_default_values(self):
        """Test default values."""
        config = CapabilityPresets.tutor()

        assert config["execution_mode"] == "multi"
        assert config["memory"] == "session"
        assert config["tool_access"] == "none"
        assert config["max_turns"] == 50

    def test_custom_max_turns(self):
        """Test custom max_turns."""
        config = CapabilityPresets.tutor(max_turns=100)

        assert config["max_turns"] == 100


class TestResearcherPreset:
    """Tests for researcher preset."""

    def test_default_values(self):
        """Test default values."""
        config = CapabilityPresets.researcher()

        assert config["execution_mode"] == "autonomous"
        assert config["memory"] == "session"
        assert config["tool_access"] == "read_only"
        assert config["max_cycles"] == 50

    def test_custom_max_cycles(self):
        """Test custom max_cycles."""
        config = CapabilityPresets.researcher(max_cycles=100)

        assert config["max_cycles"] == 100


class TestDeveloperPreset:
    """Tests for developer preset."""

    def test_default_values(self):
        """Test default values."""
        config = CapabilityPresets.developer()

        assert config["execution_mode"] == "autonomous"
        assert config["memory"] == "session"
        assert config["tool_access"] == "constrained"
        assert config["max_cycles"] == 100

    def test_longer_timeout(self):
        """Test developer has longer timeout."""
        config = CapabilityPresets.developer()

        assert config["timeout_seconds"] >= 900


class TestAdminPreset:
    """Tests for admin preset."""

    def test_default_values(self):
        """Test default values."""
        config = CapabilityPresets.admin()

        assert config["execution_mode"] == "autonomous"
        assert config["memory"] == "persistent"
        assert config["tool_access"] == "full"

    def test_very_long_timeout(self):
        """Test admin has very long timeout."""
        config = CapabilityPresets.admin()

        assert config["timeout_seconds"] >= 1800


class TestChatAssistantPreset:
    """Tests for chat_assistant preset."""

    def test_default_values(self):
        """Test default values."""
        config = CapabilityPresets.chat_assistant()

        assert config["execution_mode"] == "multi"
        assert config["memory"] == "persistent"
        assert config["tool_access"] == "none"
        assert config["max_turns"] == 100

    def test_custom_memory_path(self):
        """Test custom memory path."""
        config = CapabilityPresets.chat_assistant(memory_path="/custom/path")

        assert config["memory_path"] == "/custom/path"


class TestDataAnalystPreset:
    """Tests for data_analyst preset."""

    def test_default_values(self):
        """Test default values."""
        config = CapabilityPresets.data_analyst()

        assert config["execution_mode"] == "autonomous"
        assert config["tool_access"] == "constrained"
        assert "allowed_tools" in config

    def test_has_analysis_tools(self):
        """Test has required analysis tools."""
        config = CapabilityPresets.data_analyst()
        tools = config["allowed_tools"]

        assert "read" in tools
        assert "python" in tools


class TestCodeReviewerPreset:
    """Tests for code_reviewer preset."""

    def test_default_values(self):
        """Test default values."""
        config = CapabilityPresets.code_reviewer()

        assert config["execution_mode"] == "autonomous"
        assert config["tool_access"] == "read_only"

    def test_default_model(self):
        """Test default model is Claude."""
        config = CapabilityPresets.code_reviewer()

        assert "claude" in config["model"]


class TestCustomPreset:
    """Tests for custom preset."""

    def test_custom_values(self):
        """Test custom values."""
        config = CapabilityPresets.custom(
            execution_mode="autonomous",
            memory="persistent",
            tool_access="constrained",
        )

        assert config["execution_mode"] == "autonomous"
        assert config["memory"] == "persistent"
        assert config["tool_access"] == "constrained"

    def test_additional_overrides(self):
        """Test additional overrides."""
        config = CapabilityPresets.custom(
            execution_mode="multi",
            max_turns=75,
            custom_key="custom_value",
        )

        assert config["max_turns"] == 75
        assert config["custom_key"] == "custom_value"


class TestListPresets:
    """Tests for list_presets class method."""

    def test_returns_all_presets(self):
        """Test returns all presets."""
        presets = CapabilityPresets.list_presets()

        assert "qa_assistant" in presets
        assert "tutor" in presets
        assert "researcher" in presets
        assert "developer" in presets
        assert "admin" in presets
        assert "chat_assistant" in presets
        assert "data_analyst" in presets
        assert "code_reviewer" in presets
        assert "custom" in presets

    def test_descriptions_provided(self):
        """Test each preset has a description."""
        presets = CapabilityPresets.list_presets()

        for name, description in presets.items():
            assert isinstance(description, str)
            assert len(description) > 0


class TestGetPreset:
    """Tests for get_preset class method."""

    def test_get_by_name(self):
        """Test getting preset by name."""
        config = CapabilityPresets.get_preset("developer")

        assert config["execution_mode"] == "autonomous"
        assert config["tool_access"] == "constrained"

    def test_get_with_overrides(self):
        """Test getting preset with overrides."""
        config = CapabilityPresets.get_preset("developer", max_cycles=200)

        assert config["max_cycles"] == 200

    def test_invalid_name_raises(self):
        """Test invalid name raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            CapabilityPresets.get_preset("invalid_preset")

        assert "Unknown preset" in str(exc_info.value)


class TestPresetFunction:
    """Tests for preset() convenience function."""

    def test_preset_function(self):
        """Test preset() function."""
        config = preset("developer")

        assert config["execution_mode"] == "autonomous"

    def test_preset_with_overrides(self):
        """Test preset() with overrides."""
        config = preset("researcher", model="claude-3-opus", max_cycles=75)

        assert config["model"] == "claude-3-opus"
        assert config["max_cycles"] == 75

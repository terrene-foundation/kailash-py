"""Unit tests for kaizen.core.kaizen_options module.

Tests KaizenOptions configuration dataclass.
"""

from pathlib import Path

import pytest

from kaizen.core.kaizen_options import KaizenOptions
from kaizen.core.specialist_types import SpecialistDefinition


class TestKaizenOptions:
    """Tests for KaizenOptions dataclass."""

    def test_create_minimal(self):
        """Test creating options with defaults (isolated mode)."""
        options = KaizenOptions()
        assert options.specialists is None
        assert options.setting_sources is None
        assert options.is_isolated is True
        assert str(options.user_settings_dir) == "~/.kaizen/"
        assert str(options.project_settings_dir) == ".kaizen/"
        assert str(options.local_settings_dir) == ".kaizen-local/"
        assert options.context_file_name == "KAIZEN.md"
        assert options.specialists_dir_name == "specialists"
        assert options.skills_dir_name == "skills"
        assert options.commands_dir_name == "commands"
        assert options.cwd is None
        assert options.budget_limit_usd is None
        assert options.audit_enabled is True

    def test_create_with_programmatic_specialists(self):
        """Test creating options with programmatic specialists."""
        specialists = {
            "code-reviewer": SpecialistDefinition(
                description="Code review specialist",
                system_prompt="You are a senior code reviewer...",
            ),
            "data-analyst": SpecialistDefinition(
                description="Data analysis specialist",
                system_prompt="You are a data analyst...",
            ),
        }
        options = KaizenOptions(specialists=specialists)
        assert options.specialists == specialists
        assert len(options.specialists) == 2
        assert "code-reviewer" in options.specialists
        assert "data-analyst" in options.specialists
        assert options.is_isolated is True  # Still isolated - no filesystem

    def test_create_with_setting_sources(self):
        """Test creating options with filesystem sources enabled."""
        options = KaizenOptions(setting_sources=["project"])
        assert options.setting_sources == ["project"]
        assert options.is_isolated is False
        assert options.has_project_source is True
        assert options.has_user_source is False
        assert options.has_local_source is False

    def test_create_with_all_sources(self):
        """Test creating options with all sources enabled."""
        options = KaizenOptions(setting_sources=["user", "project", "local"])
        assert options.is_isolated is False
        assert options.has_user_source is True
        assert options.has_project_source is True
        assert options.has_local_source is True

    def test_create_with_custom_paths(self):
        """Test creating options with custom directory paths."""
        options = KaizenOptions(
            user_settings_dir="~/.my-kaizen/",
            project_settings_dir=".my-kaizen/",
            local_settings_dir=".my-kaizen-local/",
            context_file_name="PROJECT.md",
            specialists_dir_name="agents",
            skills_dir_name="knowledge",
        )
        assert str(options.user_settings_dir) == "~/.my-kaizen/"
        assert str(options.project_settings_dir) == ".my-kaizen/"
        assert str(options.local_settings_dir) == ".my-kaizen-local/"
        assert options.context_file_name == "PROJECT.md"
        assert options.specialists_dir_name == "agents"
        assert options.skills_dir_name == "knowledge"

    def test_create_with_runtime_settings(self):
        """Test creating options with runtime settings."""
        options = KaizenOptions(
            cwd="/path/to/project",
            budget_limit_usd=10.0,
            audit_enabled=False,
        )
        assert str(options.cwd) == "/path/to/project"
        assert options.budget_limit_usd == 10.0
        assert options.audit_enabled is False

    def test_validation_negative_budget(self):
        """Test that negative budget raises ValueError."""
        with pytest.raises(ValueError, match="budget_limit_usd must be non-negative"):
            KaizenOptions(budget_limit_usd=-5.0)

    def test_validation_zero_budget(self):
        """Test that zero budget is valid."""
        options = KaizenOptions(budget_limit_usd=0.0)
        assert options.budget_limit_usd == 0.0

    def test_validation_invalid_setting_source(self):
        """Test that invalid setting source raises ValueError."""
        with pytest.raises(ValueError, match="Invalid setting source"):
            KaizenOptions(setting_sources=["invalid"])  # type: ignore

    def test_validation_mixed_valid_invalid_sources(self):
        """Test that mix of valid and invalid sources raises ValueError."""
        with pytest.raises(ValueError, match="Invalid setting source"):
            KaizenOptions(setting_sources=["project", "invalid"])  # type: ignore

    def test_is_isolated_none(self):
        """Test is_isolated when setting_sources is None."""
        options = KaizenOptions(setting_sources=None)
        assert options.is_isolated is True

    def test_is_isolated_empty_list(self):
        """Test is_isolated when setting_sources is empty list."""
        options = KaizenOptions(setting_sources=[])
        assert options.is_isolated is False  # Enabled but empty

    def test_get_source_dir_user(self):
        """Test get_source_dir for user source."""
        options = KaizenOptions()
        user_dir = options.get_source_dir("user")
        assert user_dir == Path.home() / ".kaizen"

    def test_get_source_dir_project(self):
        """Test get_source_dir for project source."""
        options = KaizenOptions(cwd="/test/project")
        project_dir = options.get_source_dir("project")
        assert str(project_dir) == "/test/project/.kaizen"

    def test_get_source_dir_local(self):
        """Test get_source_dir for local source."""
        options = KaizenOptions(cwd="/test/project")
        local_dir = options.get_source_dir("local")
        assert str(local_dir) == "/test/project/.kaizen-local"

    def test_get_source_dir_invalid(self):
        """Test get_source_dir with invalid source."""
        options = KaizenOptions()
        with pytest.raises(ValueError, match="Invalid setting source"):
            options.get_source_dir("invalid")  # type: ignore

    def test_get_specialists_dir(self):
        """Test get_specialists_dir."""
        options = KaizenOptions(cwd="/test/project")
        specialists_dir = options.get_specialists_dir("project")
        assert str(specialists_dir) == "/test/project/.kaizen/specialists"

    def test_get_skills_dir(self):
        """Test get_skills_dir."""
        options = KaizenOptions(cwd="/test/project")
        skills_dir = options.get_skills_dir("project")
        assert str(skills_dir) == "/test/project/.kaizen/skills"

    def test_get_commands_dir(self):
        """Test get_commands_dir."""
        options = KaizenOptions(cwd="/test/project")
        commands_dir = options.get_commands_dir("project")
        assert str(commands_dir) == "/test/project/.kaizen/commands"

    def test_get_context_file(self):
        """Test get_context_file."""
        options = KaizenOptions(cwd="/test/project")
        context_file = options.get_context_file("project")
        assert str(context_file) == "/test/project/.kaizen/KAIZEN.md"

    def test_get_context_file_custom_name(self):
        """Test get_context_file with custom context file name."""
        options = KaizenOptions(
            cwd="/test/project",
            context_file_name="PROJECT.md",
        )
        context_file = options.get_context_file("project")
        assert str(context_file) == "/test/project/.kaizen/PROJECT.md"

    def test_custom_specialists_dir_name(self):
        """Test custom specialists directory name."""
        options = KaizenOptions(
            cwd="/test/project",
            specialists_dir_name="agents",
        )
        specialists_dir = options.get_specialists_dir("project")
        assert str(specialists_dir) == "/test/project/.kaizen/agents"

    def test_path_object_input(self):
        """Test that Path objects are accepted."""
        options = KaizenOptions(
            user_settings_dir=Path("~/.custom-kaizen/"),
            project_settings_dir=Path(".custom-kaizen/"),
            cwd=Path("/test/project"),
        )
        assert options.user_settings_dir == Path("~/.custom-kaizen/")
        assert options.project_settings_dir == Path(".custom-kaizen/")
        assert options.cwd == Path("/test/project")

    def test_to_dict(self):
        """Test serialization to dictionary."""
        specialists = {
            "test": SpecialistDefinition(
                description="Test",
                system_prompt="Test prompt",
            )
        }
        options = KaizenOptions(
            specialists=specialists,
            setting_sources=["project"],
            budget_limit_usd=5.0,
        )
        data = options.to_dict()
        assert "test" in data["specialists"]
        assert data["setting_sources"] == ["project"]
        assert data["budget_limit_usd"] == 5.0

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "specialists": {
                "test": {
                    "description": "Test specialist",
                    "system_prompt": "Test prompt",
                }
            },
            "setting_sources": ["project", "local"],
            "user_settings_dir": "~/.custom/",
            "budget_limit_usd": 10.0,
        }
        options = KaizenOptions.from_dict(data)
        assert options.specialists is not None
        assert "test" in options.specialists
        assert options.setting_sources == ["project", "local"]
        assert str(options.user_settings_dir) == "~/.custom/"
        assert options.budget_limit_usd == 10.0

    def test_roundtrip_serialization(self):
        """Test that to_dict/from_dict roundtrips correctly."""
        original = KaizenOptions(
            specialists={
                "test": SpecialistDefinition(
                    description="Roundtrip test",
                    system_prompt="Testing roundtrip.",
                )
            },
            setting_sources=["user", "project"],
            context_file_name="CUSTOM.md",
            budget_limit_usd=15.0,
            audit_enabled=False,
        )
        data = original.to_dict()
        restored = KaizenOptions.from_dict(data)

        assert len(restored.specialists) == len(original.specialists)
        assert restored.setting_sources == original.setting_sources
        assert restored.context_file_name == original.context_file_name
        assert restored.budget_limit_usd == original.budget_limit_usd
        assert restored.audit_enabled == original.audit_enabled

"""Unit tests for kaizen.core.specialist_types module.

Tests SpecialistDefinition, SkillDefinition, and ContextFile dataclasses.
"""

import pytest

from kaizen.core.specialist_types import (
    ContextFile,
    SettingSource,
    SkillDefinition,
    SpecialistDefinition,
)


class TestSpecialistDefinition:
    """Tests for SpecialistDefinition dataclass."""

    def test_create_minimal(self):
        """Test creating specialist with only required fields."""
        spec = SpecialistDefinition(
            description="Test specialist",
            system_prompt="You are a test specialist.",
        )
        assert spec.description == "Test specialist"
        assert spec.system_prompt == "You are a test specialist."
        assert spec.available_tools is None
        assert spec.model is None
        assert spec.signature is None
        assert spec.temperature is None
        assert spec.max_tokens is None
        assert spec.memory_enabled is False
        assert spec.source == "programmatic"
        assert spec.file_path is None

    def test_create_full(self):
        """Test creating specialist with all fields."""
        spec = SpecialistDefinition(
            description="Code review specialist",
            system_prompt="You are a senior code reviewer...",
            available_tools=["Read", "Glob", "Grep"],
            model="gpt-4",
            signature="CodeReviewSignature",
            temperature=0.7,
            max_tokens=4096,
            memory_enabled=True,
            source="project",
            file_path="/path/to/specialist.md",
        )
        assert spec.description == "Code review specialist"
        assert spec.available_tools == ["Read", "Glob", "Grep"]
        assert spec.model == "gpt-4"
        assert spec.signature == "CodeReviewSignature"
        assert spec.temperature == 0.7
        assert spec.max_tokens == 4096
        assert spec.memory_enabled is True
        assert spec.source == "project"
        assert spec.file_path == "/path/to/specialist.md"

    def test_validation_empty_description(self):
        """Test that empty description raises ValueError."""
        with pytest.raises(ValueError, match="must have a description"):
            SpecialistDefinition(description="", system_prompt="Test prompt")

    def test_validation_empty_system_prompt(self):
        """Test that empty system_prompt raises ValueError."""
        with pytest.raises(ValueError, match="must have a system_prompt"):
            SpecialistDefinition(description="Test", system_prompt="")

    def test_validation_temperature_low(self):
        """Test that temperature < 0 raises ValueError."""
        with pytest.raises(ValueError, match="Temperature must be between"):
            SpecialistDefinition(
                description="Test",
                system_prompt="Test",
                temperature=-0.1,
            )

    def test_validation_temperature_high(self):
        """Test that temperature > 2.0 raises ValueError."""
        with pytest.raises(ValueError, match="Temperature must be between"):
            SpecialistDefinition(
                description="Test",
                system_prompt="Test",
                temperature=2.5,
            )

    def test_validation_temperature_valid_bounds(self):
        """Test that valid temperature bounds are accepted."""
        # Min bound
        spec = SpecialistDefinition(
            description="Test", system_prompt="Test", temperature=0.0
        )
        assert spec.temperature == 0.0

        # Max bound
        spec = SpecialistDefinition(
            description="Test", system_prompt="Test", temperature=2.0
        )
        assert spec.temperature == 2.0

    def test_validation_max_tokens_zero(self):
        """Test that max_tokens <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            SpecialistDefinition(
                description="Test",
                system_prompt="Test",
                max_tokens=0,
            )

    def test_validation_max_tokens_negative(self):
        """Test that negative max_tokens raises ValueError."""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            SpecialistDefinition(
                description="Test",
                system_prompt="Test",
                max_tokens=-100,
            )

    def test_to_dict(self):
        """Test serialization to dictionary."""
        spec = SpecialistDefinition(
            description="Test specialist",
            system_prompt="You are a test.",
            available_tools=["Read"],
            model="gpt-4",
            temperature=0.5,
        )
        data = spec.to_dict()
        assert data["description"] == "Test specialist"
        assert data["system_prompt"] == "You are a test."
        assert data["available_tools"] == ["Read"]
        assert data["model"] == "gpt-4"
        assert data["temperature"] == 0.5
        assert data["source"] == "programmatic"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "description": "From dict specialist",
            "system_prompt": "Created from dict.",
            "available_tools": ["Write", "Edit"],
            "model": "claude-3-opus",
            "temperature": 0.3,
            "source": "user",
        }
        spec = SpecialistDefinition.from_dict(data)
        assert spec.description == "From dict specialist"
        assert spec.system_prompt == "Created from dict."
        assert spec.available_tools == ["Write", "Edit"]
        assert spec.model == "claude-3-opus"
        assert spec.temperature == 0.3
        assert spec.source == "user"

    def test_roundtrip_serialization(self):
        """Test that to_dict/from_dict roundtrips correctly."""
        original = SpecialistDefinition(
            description="Roundtrip test",
            system_prompt="Testing roundtrip.",
            available_tools=["Bash", "Glob"],
            model="gpt-4-turbo",
            temperature=1.0,
            max_tokens=2048,
            memory_enabled=True,
            source="local",
            file_path="/path/to/file.md",
        )
        data = original.to_dict()
        restored = SpecialistDefinition.from_dict(data)

        assert restored.description == original.description
        assert restored.system_prompt == original.system_prompt
        assert restored.available_tools == original.available_tools
        assert restored.model == original.model
        assert restored.temperature == original.temperature
        assert restored.max_tokens == original.max_tokens
        assert restored.memory_enabled == original.memory_enabled
        assert restored.source == original.source
        assert restored.file_path == original.file_path


class TestSkillDefinition:
    """Tests for SkillDefinition dataclass."""

    def test_create_minimal(self):
        """Test creating skill with only required fields."""
        skill = SkillDefinition(
            name="python-expert",
            description="Python programming expertise",
            location="/path/to/skill",
        )
        assert skill.name == "python-expert"
        assert skill.description == "Python programming expertise"
        assert skill.location == "/path/to/skill"
        assert skill.skill_content is None
        assert skill.additional_files is None
        assert skill.source == "project"

    def test_create_with_content(self):
        """Test creating skill with content loaded."""
        skill = SkillDefinition(
            name="code-reviewer",
            description="Code review expertise",
            location="/path/to/skill",
            skill_content="# Code Review\nReview code...",
            additional_files={"patterns.md": "# Patterns\n..."},
            source="user",
        )
        assert skill.skill_content == "# Code Review\nReview code..."
        assert skill.additional_files == {"patterns.md": "# Patterns\n..."}
        assert skill.source == "user"

    def test_validation_empty_name(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="must have a name"):
            SkillDefinition(name="", description="Test", location="/path")

    def test_validation_empty_description(self):
        """Test that empty description raises ValueError."""
        with pytest.raises(ValueError, match="must have a description"):
            SkillDefinition(name="test", description="", location="/path")

    def test_validation_empty_location(self):
        """Test that empty location raises ValueError."""
        with pytest.raises(ValueError, match="must have a location"):
            SkillDefinition(name="test", description="Test", location="")

    def test_is_loaded_false(self):
        """Test is_loaded property when content not loaded."""
        skill = SkillDefinition(name="test", description="Test", location="/path")
        assert skill.is_loaded is False

    def test_is_loaded_true(self):
        """Test is_loaded property when content is loaded."""
        skill = SkillDefinition(
            name="test",
            description="Test",
            location="/path",
            skill_content="Content here",
        )
        assert skill.is_loaded is True

    def test_get_file_none(self):
        """Test get_file when no additional files."""
        skill = SkillDefinition(name="test", description="Test", location="/path")
        assert skill.get_file("patterns.md") is None

    def test_get_file_not_found(self):
        """Test get_file when file not in additional_files."""
        skill = SkillDefinition(
            name="test",
            description="Test",
            location="/path",
            additional_files={"other.md": "content"},
        )
        assert skill.get_file("patterns.md") is None

    def test_get_file_found(self):
        """Test get_file when file exists."""
        skill = SkillDefinition(
            name="test",
            description="Test",
            location="/path",
            additional_files={"patterns.md": "Pattern content"},
        )
        assert skill.get_file("patterns.md") == "Pattern content"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        skill = SkillDefinition(
            name="test-skill",
            description="Test description",
            location="/path/to/skill",
            skill_content="Skill content",
            source="local",
        )
        data = skill.to_dict()
        assert data["name"] == "test-skill"
        assert data["description"] == "Test description"
        assert data["location"] == "/path/to/skill"
        assert data["skill_content"] == "Skill content"
        assert data["source"] == "local"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "name": "from-dict",
            "description": "Created from dict",
            "location": "/dict/path",
            "skill_content": "Dict content",
            "source": "user",
        }
        skill = SkillDefinition.from_dict(data)
        assert skill.name == "from-dict"
        assert skill.description == "Created from dict"
        assert skill.location == "/dict/path"
        assert skill.skill_content == "Dict content"
        assert skill.source == "user"


class TestContextFile:
    """Tests for ContextFile dataclass."""

    def test_create(self):
        """Test creating context file."""
        ctx = ContextFile(
            path="/path/to/KAIZEN.md",
            content="# Project Context\nThis is the project...",
            source="project",
        )
        assert ctx.path == "/path/to/KAIZEN.md"
        assert ctx.content == "# Project Context\nThis is the project..."
        assert ctx.source == "project"

    def test_create_default_source(self):
        """Test that default source is 'project'."""
        ctx = ContextFile(path="/path", content="content")
        assert ctx.source == "project"

    def test_validation_empty_path(self):
        """Test that empty path raises ValueError."""
        with pytest.raises(ValueError, match="must have a path"):
            ContextFile(path="", content="content")

    def test_validation_none_content(self):
        """Test that None content raises ValueError."""
        with pytest.raises(ValueError, match="must have content"):
            ContextFile(path="/path", content=None)  # type: ignore


class TestSettingSource:
    """Tests for SettingSource type."""

    def test_valid_sources(self):
        """Test that valid sources are accepted in SpecialistDefinition."""
        for source in ["user", "project", "local"]:
            skill = SkillDefinition(
                name="test",
                description="Test",
                location="/path",
                source=source,  # type: ignore
            )
            assert skill.source == source

    def test_programmatic_source(self):
        """Test that programmatic source works for specialists."""
        spec = SpecialistDefinition(
            description="Test",
            system_prompt="Test",
            source="programmatic",
        )
        assert spec.source == "programmatic"

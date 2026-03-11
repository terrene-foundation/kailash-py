"""Unit tests for LocalKaizenAdapter with KaizenOptions integration.

Tests the integration of the Specialist System (ADR-013) with LocalKaizenAdapter.
"""

from pathlib import Path
from typing import Optional

import pytest

from kaizen.core.kaizen_options import KaizenOptions
from kaizen.core.specialist_types import SkillDefinition, SpecialistDefinition
from kaizen.runtime.adapters.kaizen_local import LocalKaizenAdapter
from kaizen.runtime.adapters.types import AutonomousConfig, PlanningStrategy
from kaizen.runtime.specialist_loader import SpecialistLoader
from kaizen.runtime.specialist_registry import SkillRegistry, SpecialistRegistry


class TestLocalKaizenAdapterWithKaizenOptions:
    """Tests for LocalKaizenAdapter with KaizenOptions."""

    def test_adapter_without_kaizen_options(self):
        """Test that adapter works without KaizenOptions (backward compatible)."""
        adapter = LocalKaizenAdapter()
        assert adapter.kaizen_options is None
        assert adapter.specialist_registry is None
        assert adapter.skill_registry is None

    def test_adapter_with_kaizen_options_isolated(self):
        """Test adapter with isolated KaizenOptions (no filesystem)."""
        options = KaizenOptions()  # Isolated mode (no setting_sources)
        adapter = LocalKaizenAdapter(kaizen_options=options)

        assert adapter.kaizen_options == options
        assert adapter.specialist_registry is not None
        assert len(adapter.specialist_registry) == 0  # No specialists in isolated mode

    def test_adapter_with_programmatic_specialists(self):
        """Test adapter with programmatic specialists from KaizenOptions."""
        specialists = {
            "code-reviewer": SpecialistDefinition(
                description="Code review specialist",
                system_prompt="You are an expert code reviewer.",
            ),
            "data-analyst": SpecialistDefinition(
                description="Data analysis specialist",
                system_prompt="You analyze data and create insights.",
                temperature=0.3,
            ),
        }
        options = KaizenOptions(specialists=specialists)
        adapter = LocalKaizenAdapter(kaizen_options=options)

        assert len(adapter.specialist_registry) == 2
        assert "code-reviewer" in adapter.specialist_registry.list()
        assert "data-analyst" in adapter.specialist_registry.list()

    def test_adapter_with_filesystem_sources(self, tmp_path: Path):
        """Test adapter loads specialists from filesystem."""
        # Create specialist file
        specialists_dir = tmp_path / ".kaizen" / "specialists"
        specialists_dir.mkdir(parents=True)
        (specialists_dir / "test-specialist.md").write_text(
            """# Test Specialist
**Description**: Test specialist from filesystem
**System Prompt**: You are a test specialist.
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        adapter = LocalKaizenAdapter(kaizen_options=options)

        assert len(adapter.specialist_registry) == 1
        assert "test-specialist" in adapter.specialist_registry.list()

    def test_get_specialist(self, tmp_path: Path):
        """Test getting a specialist by name."""
        specialists = {
            "my-specialist": SpecialistDefinition(
                description="My specialist",
                system_prompt="Custom system prompt.",
            ),
        }
        options = KaizenOptions(specialists=specialists)
        adapter = LocalKaizenAdapter(kaizen_options=options)

        specialist = adapter.get_specialist("my-specialist")
        assert specialist is not None
        assert specialist.description == "My specialist"
        assert specialist.system_prompt == "Custom system prompt."

    def test_get_specialist_not_found(self):
        """Test getting a non-existent specialist returns None."""
        options = KaizenOptions()
        adapter = LocalKaizenAdapter(kaizen_options=options)

        specialist = adapter.get_specialist("nonexistent")
        assert specialist is None

    def test_list_specialists(self):
        """Test listing all available specialists."""
        specialists = {
            "alpha": SpecialistDefinition(
                description="Alpha",
                system_prompt="Alpha prompt.",
            ),
            "beta": SpecialistDefinition(
                description="Beta",
                system_prompt="Beta prompt.",
            ),
        }
        options = KaizenOptions(specialists=specialists)
        adapter = LocalKaizenAdapter(kaizen_options=options)

        names = adapter.list_specialists()
        assert set(names) == {"alpha", "beta"}


class TestLocalKaizenAdapterContextInjection:
    """Tests for context file injection into system prompts."""

    def test_context_file_not_loaded_in_isolated_mode(self):
        """Test that context file is not loaded in isolated mode."""
        options = KaizenOptions()  # Isolated mode
        adapter = LocalKaizenAdapter(kaizen_options=options)

        assert adapter.context_file is None

    def test_context_file_loaded_from_filesystem(self, tmp_path: Path):
        """Test loading context file from filesystem."""
        kaizen_dir = tmp_path / ".kaizen"
        kaizen_dir.mkdir()
        (kaizen_dir / "KAIZEN.md").write_text(
            """# Project Context
This is a Python project for workflow automation.

## Coding Standards
- Use type hints
- Follow PEP 8
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        adapter = LocalKaizenAdapter(kaizen_options=options)

        assert adapter.context_file is not None
        assert "workflow automation" in adapter.context_file.content

    def test_context_injected_into_system_prompt(self, tmp_path: Path):
        """Test that context is injected into system prompt."""
        kaizen_dir = tmp_path / ".kaizen"
        kaizen_dir.mkdir()
        (kaizen_dir / "KAIZEN.md").write_text(
            """# Important Context
Always use async/await patterns.
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        adapter = LocalKaizenAdapter(kaizen_options=options)

        # Get context section for system prompt
        context_section = adapter.get_context_prompt_section()
        assert context_section is not None
        assert "Always use async/await patterns" in context_section


class TestLocalKaizenAdapterSkills:
    """Tests for skill loading with adapter."""

    def test_skills_loaded_from_filesystem(self, tmp_path: Path):
        """Test loading skills from filesystem."""
        skill_dir = tmp_path / ".kaizen" / "skills" / "python-patterns"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: python-patterns
description: Python design patterns
---
# Python Patterns
Content here.
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        adapter = LocalKaizenAdapter(kaizen_options=options)

        assert len(adapter.skill_registry) == 1
        assert "python-patterns" in adapter.skill_registry.list()

    def test_get_skill(self, tmp_path: Path):
        """Test getting a skill by name."""
        skill_dir = tmp_path / ".kaizen" / "skills" / "testing"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: testing
description: Testing best practices
---
# Testing
Test content.
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        adapter = LocalKaizenAdapter(kaizen_options=options)

        skill = adapter.get_skill("testing")
        assert skill is not None
        assert skill.description == "Testing best practices"

    def test_load_skill_content(self, tmp_path: Path):
        """Test loading full skill content on demand."""
        skill_dir = tmp_path / ".kaizen" / "skills" / "coding"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: coding
description: Coding standards
---
# Coding Standards
Follow these standards:
1. Use type hints
2. Write tests
"""
        )
        (skill_dir / "examples.md").write_text("# Examples\nExample code here.")

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        adapter = LocalKaizenAdapter(kaizen_options=options)

        skill = adapter.get_skill("coding")
        assert skill.skill_content is None  # Not loaded yet

        # Load content
        loaded_skill = adapter.load_skill_content(skill)
        assert loaded_skill.skill_content is not None
        assert "Follow these standards" in loaded_skill.skill_content
        assert loaded_skill.additional_files is not None
        assert "examples.md" in loaded_skill.additional_files


class TestLocalKaizenAdapterConfigMerging:
    """Tests for merging KaizenOptions with AutonomousConfig."""

    def test_budget_from_kaizen_options(self):
        """Test that budget_limit_usd from KaizenOptions is used."""
        options = KaizenOptions(budget_limit_usd=5.0)
        adapter = LocalKaizenAdapter(kaizen_options=options)

        # Budget should be accessible
        assert adapter.effective_budget_limit == 5.0

    def test_budget_from_config_overrides(self):
        """Test that AutonomousConfig budget overrides KaizenOptions."""
        options = KaizenOptions(budget_limit_usd=5.0)
        config = AutonomousConfig(budget_limit_usd=10.0)
        adapter = LocalKaizenAdapter(config=config, kaizen_options=options)

        # Config should take precedence
        assert adapter.effective_budget_limit == 10.0

    def test_cwd_from_kaizen_options(self):
        """Test that cwd from KaizenOptions is used."""
        options = KaizenOptions(cwd="/test/project")
        adapter = LocalKaizenAdapter(kaizen_options=options)

        assert adapter.working_directory == Path("/test/project")

    def test_cwd_defaults_to_current(self):
        """Test that cwd defaults to current directory when not set."""
        options = KaizenOptions()
        adapter = LocalKaizenAdapter(kaizen_options=options)

        # Should default to current directory
        assert adapter.working_directory == Path.cwd()


class TestFromSpecialist:
    """Tests for creating adapter configured for a specific specialist."""

    def test_from_specialist_basic(self):
        """Test creating adapter from specialist definition."""
        specialists = {
            "code-reviewer": SpecialistDefinition(
                description="Code reviewer",
                system_prompt="You review code carefully.",
                model="gpt-4o",
                temperature=0.2,
            ),
        }
        options = KaizenOptions(specialists=specialists)
        adapter = LocalKaizenAdapter(kaizen_options=options)

        # Create configured adapter for specialist
        specialist_adapter = adapter.for_specialist("code-reviewer")

        assert specialist_adapter is not None
        assert specialist_adapter.config.model == "gpt-4o"
        assert specialist_adapter.config.temperature == 0.2

    def test_from_specialist_with_tools(self):
        """Test that specialist tools are respected."""
        specialists = {
            "reader": SpecialistDefinition(
                description="Read-only specialist",
                system_prompt="You only read files.",
                available_tools=["Read", "Glob", "Grep"],
            ),
        }
        options = KaizenOptions(specialists=specialists)
        adapter = LocalKaizenAdapter(kaizen_options=options)

        specialist_adapter = adapter.for_specialist("reader")

        # Tools should be limited
        assert specialist_adapter.available_tools == ["Read", "Glob", "Grep"]

    def test_from_specialist_not_found(self):
        """Test that missing specialist returns None."""
        options = KaizenOptions()
        adapter = LocalKaizenAdapter(kaizen_options=options)

        specialist_adapter = adapter.for_specialist("nonexistent")
        assert specialist_adapter is None

    def test_from_specialist_preserves_registries(self):
        """Test that specialist adapter shares registries."""
        specialists = {
            "helper": SpecialistDefinition(
                description="Helper",
                system_prompt="You help.",
            ),
            "other": SpecialistDefinition(
                description="Other",
                system_prompt="Other agent.",
            ),
        }
        options = KaizenOptions(specialists=specialists)
        adapter = LocalKaizenAdapter(kaizen_options=options)

        specialist_adapter = adapter.for_specialist("helper")

        # Should have access to all specialists
        assert len(specialist_adapter.specialist_registry) == 2

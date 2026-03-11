"""Integration tests for SpecialistLoader.

Tests filesystem-based loading of specialists, skills, and context files.
Uses real filesystem operations (NO MOCKING per project directives).
"""

from pathlib import Path

import pytest

from kaizen.core.kaizen_options import KaizenOptions
from kaizen.core.specialist_types import SkillDefinition, SpecialistDefinition
from kaizen.runtime.specialist_loader import SpecialistLoader


class TestSpecialistLoaderFilesystem:
    """Integration tests for SpecialistLoader with real filesystem."""

    def test_load_specialist_from_project_dir(self, tmp_path: Path):
        """Test loading a specialist from .kaizen/specialists/ directory."""
        # Create project structure
        specialists_dir = tmp_path / ".kaizen" / "specialists"
        specialists_dir.mkdir(parents=True)

        # Create specialist markdown file
        specialist_file = specialists_dir / "code-reviewer.md"
        specialist_file.write_text(
            """# Code Reviewer Specialist

**Description**: Expert code reviewer for Python projects
**System Prompt**: You are a senior code reviewer. Review code for:
- Code quality and best practices
- Security vulnerabilities
- Performance issues
**Available Tools**: Read, Glob, Grep
**Model**: gpt-4
**Temperature**: 0.3
**Memory Enabled**: true
"""
        )

        # Configure loader
        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)

        # Load specialists
        registry = loader.load_specialists()

        # Verify
        assert len(registry) == 1
        assert "code-reviewer" in registry.list()

        specialist = registry.get("code-reviewer")
        assert specialist is not None
        assert specialist.description == "Expert code reviewer for Python projects"
        assert "senior code reviewer" in specialist.system_prompt
        assert specialist.available_tools == ["Read", "Glob", "Grep"]
        assert specialist.model == "gpt-4"
        assert specialist.temperature == 0.3
        assert specialist.memory_enabled is True
        assert specialist.source == "project"
        assert specialist.file_path == str(specialist_file)

    def test_load_multiple_specialists(self, tmp_path: Path):
        """Test loading multiple specialists from same directory."""
        specialists_dir = tmp_path / ".kaizen" / "specialists"
        specialists_dir.mkdir(parents=True)

        # Create multiple specialist files
        (specialists_dir / "python-expert.md").write_text(
            """# Python Expert
**Description**: Python programming specialist
**System Prompt**: You are a Python expert.
"""
        )

        (specialists_dir / "data-analyst.md").write_text(
            """# Data Analyst
**Description**: Data analysis and visualization
**System Prompt**: You analyze data and create visualizations.
**Temperature**: 0.5
"""
        )

        (specialists_dir / "security-auditor.md").write_text(
            """# Security Auditor
**Description**: Security vulnerability scanner
**System Prompt**: You audit code for security issues.
**Max Tokens**: 8192
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_specialists()

        assert len(registry) == 3
        assert set(registry.list()) == {
            "python-expert",
            "data-analyst",
            "security-auditor",
        }

        # Verify individual specialists
        assert (
            registry.get("python-expert").description == "Python programming specialist"
        )
        assert registry.get("data-analyst").temperature == 0.5
        assert registry.get("security-auditor").max_tokens == 8192

    def test_load_specialists_priority_order(self, tmp_path: Path):
        """Test that local specialists override project specialists."""
        # Create project specialist
        project_dir = tmp_path / ".kaizen" / "specialists"
        project_dir.mkdir(parents=True)
        (project_dir / "reviewer.md").write_text(
            """# Reviewer
**Description**: Project-level reviewer
**System Prompt**: You are a project reviewer.
"""
        )

        # Create local specialist with same name
        local_dir = tmp_path / ".kaizen-local" / "specialists"
        local_dir.mkdir(parents=True)
        (local_dir / "reviewer.md").write_text(
            """# Reviewer
**Description**: Local custom reviewer
**System Prompt**: You are a customized local reviewer.
**Temperature**: 0.1
"""
        )

        options = KaizenOptions(
            setting_sources=["project", "local"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_specialists()

        # Local should override project
        assert len(registry) == 1
        specialist = registry.get("reviewer")
        assert specialist.description == "Local custom reviewer"
        assert specialist.source == "local"
        assert specialist.temperature == 0.1

    def test_load_specialists_with_programmatic_base(self, tmp_path: Path):
        """Test that filesystem specialists override programmatic ones."""
        # Create programmatic specialist
        programmatic_specialists = {
            "helper": SpecialistDefinition(
                description="Programmatic helper",
                system_prompt="You are a programmatic helper.",
            )
        }

        # Create filesystem specialist with same name
        specialists_dir = tmp_path / ".kaizen" / "specialists"
        specialists_dir.mkdir(parents=True)
        (specialists_dir / "helper.md").write_text(
            """# Helper
**Description**: Filesystem helper (overrides programmatic)
**System Prompt**: You are a filesystem helper.
"""
        )

        options = KaizenOptions(
            specialists=programmatic_specialists,
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_specialists()

        # Filesystem should override programmatic
        specialist = registry.get("helper")
        assert specialist.description == "Filesystem helper (overrides programmatic)"
        assert specialist.source == "project"

    def test_load_specialists_missing_required_fields(self, tmp_path: Path):
        """Test that specialists missing required fields are skipped."""
        specialists_dir = tmp_path / ".kaizen" / "specialists"
        specialists_dir.mkdir(parents=True)

        # Missing Description
        (specialists_dir / "no-description.md").write_text(
            """# No Description
**System Prompt**: Missing description field.
"""
        )

        # Missing System Prompt
        (specialists_dir / "no-prompt.md").write_text(
            """# No Prompt
**Description**: Has description but no system prompt.
"""
        )

        # Valid specialist
        (specialists_dir / "valid.md").write_text(
            """# Valid
**Description**: Valid specialist
**System Prompt**: Has both required fields.
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_specialists()

        # Only valid specialist should be loaded
        assert len(registry) == 1
        assert "valid" in registry.list()

    def test_load_specialists_empty_directory(self, tmp_path: Path):
        """Test loading from empty specialists directory."""
        specialists_dir = tmp_path / ".kaizen" / "specialists"
        specialists_dir.mkdir(parents=True)

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_specialists()

        assert len(registry) == 0

    def test_load_specialists_nonexistent_directory(self, tmp_path: Path):
        """Test loading when specialists directory doesn't exist."""
        # Create .kaizen but not specialists subdirectory
        (tmp_path / ".kaizen").mkdir()

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_specialists()

        assert len(registry) == 0

    def test_isolated_mode_skips_filesystem(self, tmp_path: Path):
        """Test that isolated mode doesn't load from filesystem."""
        specialists_dir = tmp_path / ".kaizen" / "specialists"
        specialists_dir.mkdir(parents=True)
        (specialists_dir / "should-not-load.md").write_text(
            """# Should Not Load
**Description**: This should not be loaded
**System Prompt**: In isolated mode.
"""
        )

        # No setting_sources = isolated mode
        options = KaizenOptions(cwd=str(tmp_path))
        loader = SpecialistLoader(options)
        registry = loader.load_specialists()

        assert len(registry) == 0


class TestSkillLoaderFilesystem:
    """Integration tests for skill loading with real filesystem."""

    def test_load_skill_from_project_dir(self, tmp_path: Path):
        """Test loading a skill from .kaizen/skills/ directory."""
        # Create skill directory structure
        skill_dir = tmp_path / ".kaizen" / "skills" / "python-patterns"
        skill_dir.mkdir(parents=True)

        # Create SKILL.md with frontmatter
        (skill_dir / "SKILL.md").write_text(
            """---
name: python-patterns
description: Common Python design patterns and best practices
---
# Python Patterns Skill

This skill provides guidance on Python design patterns.

## Singleton Pattern
...

## Factory Pattern
...
"""
        )

        # Create additional files
        (skill_dir / "examples.md").write_text(
            """# Examples
Code examples for each pattern.
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_skills()

        assert len(registry) == 1
        skill = registry.get("python-patterns")
        assert skill is not None
        assert skill.name == "python-patterns"
        assert skill.description == "Common Python design patterns and best practices"
        assert skill.location == str(skill_dir)
        assert skill.source == "project"
        # Content is lazy-loaded
        assert skill.skill_content is None

    def test_load_skill_content_on_demand(self, tmp_path: Path):
        """Test progressive disclosure - content loaded on demand."""
        skill_dir = tmp_path / ".kaizen" / "skills" / "testing"
        skill_dir.mkdir(parents=True)

        (skill_dir / "SKILL.md").write_text(
            """---
name: testing
description: Testing best practices
---
# Testing Skill

Comprehensive testing guide.
"""
        )

        (skill_dir / "pytest-tips.md").write_text(
            """# Pytest Tips
Use fixtures effectively.
"""
        )

        (skill_dir / "coverage.md").write_text(
            """# Coverage
Aim for high coverage.
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_skills()

        skill = registry.get("testing")
        assert skill.skill_content is None  # Not loaded yet

        # Load content on demand
        loaded_skill = loader.load_skill_content(skill)
        assert loaded_skill.skill_content is not None
        assert "Comprehensive testing guide" in loaded_skill.skill_content
        assert loaded_skill.additional_files is not None
        assert "pytest-tips.md" in loaded_skill.additional_files
        assert "coverage.md" in loaded_skill.additional_files

    def test_load_multiple_skills(self, tmp_path: Path):
        """Test loading multiple skills from same directory."""
        skills_base = tmp_path / ".kaizen" / "skills"

        # Create multiple skill directories
        for skill_name in ["git-workflow", "code-review", "debugging"]:
            skill_dir = skills_base / skill_name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                f"""---
name: {skill_name}
description: {skill_name.replace('-', ' ').title()} expertise
---
# {skill_name.title()} Skill
Content for {skill_name}.
"""
            )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_skills()

        assert len(registry) == 3
        assert set(registry.list()) == {"git-workflow", "code-review", "debugging"}

    def test_load_skill_priority_order(self, tmp_path: Path):
        """Test that local skills override project skills."""
        # Create project skill
        project_skill = tmp_path / ".kaizen" / "skills" / "formatting"
        project_skill.mkdir(parents=True)
        (project_skill / "SKILL.md").write_text(
            """---
name: formatting
description: Project formatting rules
---
# Formatting
Standard project formatting.
"""
        )

        # Create local skill with same name
        local_skill = tmp_path / ".kaizen-local" / "skills" / "formatting"
        local_skill.mkdir(parents=True)
        (local_skill / "SKILL.md").write_text(
            """---
name: formatting
description: Custom local formatting rules
---
# Formatting
Custom local formatting overrides.
"""
        )

        options = KaizenOptions(
            setting_sources=["project", "local"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_skills()

        skill = registry.get("formatting")
        assert skill.description == "Custom local formatting rules"
        assert skill.source == "local"

    def test_load_skill_without_frontmatter(self, tmp_path: Path):
        """Test loading skill that uses first paragraph as description."""
        skill_dir = tmp_path / ".kaizen" / "skills" / "quick-tips"
        skill_dir.mkdir(parents=True)

        # No frontmatter, use first paragraph
        (skill_dir / "SKILL.md").write_text(
            """# Quick Tips

This skill provides quick tips for everyday coding tasks.

## Tip 1
...
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_skills()

        skill = registry.get("quick-tips")
        assert skill is not None
        assert skill.name == "quick-tips"  # Defaults to directory name
        assert "quick tips for everyday coding" in skill.description.lower()

    def test_load_skill_missing_skill_md(self, tmp_path: Path):
        """Test that directories without SKILL.md are skipped."""
        skills_base = tmp_path / ".kaizen" / "skills"

        # Directory without SKILL.md
        (skills_base / "no-skill-file").mkdir(parents=True)
        (skills_base / "no-skill-file" / "random.md").write_text("Random content")

        # Directory with SKILL.md
        valid_skill = skills_base / "valid-skill"
        valid_skill.mkdir(parents=True)
        (valid_skill / "SKILL.md").write_text(
            """---
name: valid-skill
description: Valid skill with SKILL.md
---
# Valid
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_skills()

        assert len(registry) == 1
        assert "valid-skill" in registry.list()

    def test_isolated_mode_skips_skill_loading(self, tmp_path: Path):
        """Test that isolated mode doesn't load skills from filesystem."""
        skill_dir = tmp_path / ".kaizen" / "skills" / "should-not-load"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: should-not-load
description: This should not be loaded
---
# Should Not Load
"""
        )

        options = KaizenOptions(cwd=str(tmp_path))  # No setting_sources
        loader = SpecialistLoader(options)
        registry = loader.load_skills()

        assert len(registry) == 0


class TestContextFileLoader:
    """Integration tests for context file loading."""

    def test_load_context_file_from_project(self, tmp_path: Path):
        """Test loading KAIZEN.md from project directory."""
        kaizen_dir = tmp_path / ".kaizen"
        kaizen_dir.mkdir()

        context_content = """# Project Context

This is a Kailash SDK project for building workflow automation.

## Architecture
- Core workflow engine
- Plugin system
- CLI interface

## Coding Standards
- Use type hints
- Follow PEP 8
- Write tests first
"""
        (kaizen_dir / "KAIZEN.md").write_text(context_content)

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        context = loader.load_context_file()

        assert context is not None
        assert context.path == str(kaizen_dir / "KAIZEN.md")
        assert "workflow automation" in context.content
        assert context.source == "project"

    def test_load_context_file_priority(self, tmp_path: Path):
        """Test that local context file overrides project context file."""
        # Create project context
        project_kaizen = tmp_path / ".kaizen"
        project_kaizen.mkdir()
        (project_kaizen / "KAIZEN.md").write_text(
            "# Project Context\nDefault project info."
        )

        # Create local context
        local_kaizen = tmp_path / ".kaizen-local"
        local_kaizen.mkdir()
        (local_kaizen / "KAIZEN.md").write_text(
            "# Local Context\nCustom local overrides."
        )

        options = KaizenOptions(
            setting_sources=["project", "local"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        context = loader.load_context_file()

        # Local should override (checked in reverse order)
        assert context is not None
        assert "Local Context" in context.content
        assert context.source == "local"

    def test_load_context_file_custom_name(self, tmp_path: Path):
        """Test loading context file with custom name."""
        kaizen_dir = tmp_path / ".kaizen"
        kaizen_dir.mkdir()
        (kaizen_dir / "PROJECT.md").write_text("# Custom Project File\nCustom context.")

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
            context_file_name="PROJECT.md",
        )
        loader = SpecialistLoader(options)
        context = loader.load_context_file()

        assert context is not None
        assert "Custom Project File" in context.content

    def test_load_context_file_not_found(self, tmp_path: Path):
        """Test when no context file exists."""
        (tmp_path / ".kaizen").mkdir()  # Empty directory

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        context = loader.load_context_file()

        assert context is None

    def test_load_context_file_isolated_mode(self, tmp_path: Path):
        """Test that isolated mode returns None for context file."""
        kaizen_dir = tmp_path / ".kaizen"
        kaizen_dir.mkdir()
        (kaizen_dir / "KAIZEN.md").write_text("# Should Not Load")

        options = KaizenOptions(cwd=str(tmp_path))  # No setting_sources
        loader = SpecialistLoader(options)
        context = loader.load_context_file()

        assert context is None


class TestLoadAll:
    """Integration tests for load_all() method."""

    def test_load_all_full_structure(self, tmp_path: Path):
        """Test loading specialists, skills, and context together."""
        # Create full project structure
        kaizen_dir = tmp_path / ".kaizen"

        # Specialists
        specialists_dir = kaizen_dir / "specialists"
        specialists_dir.mkdir(parents=True)
        (specialists_dir / "analyst.md").write_text(
            """# Analyst
**Description**: Data analyst
**System Prompt**: You analyze data.
"""
        )

        # Skills
        skill_dir = kaizen_dir / "skills" / "sql"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: sql
description: SQL query expertise
---
# SQL Skill
"""
        )

        # Context
        (kaizen_dir / "KAIZEN.md").write_text("# Project Context\nAnalytics project.")

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        specialists, skills, context = loader.load_all()

        assert len(specialists) == 1
        assert "analyst" in specialists.list()

        assert len(skills) == 1
        assert "sql" in skills.list()

        assert context is not None
        assert "Analytics project" in context.content

    def test_load_all_empty_structure(self, tmp_path: Path):
        """Test load_all when directories are empty."""
        (tmp_path / ".kaizen").mkdir()

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        specialists, skills, context = loader.load_all()

        assert len(specialists) == 0
        assert len(skills) == 0
        assert context is None

    def test_load_all_with_all_sources(self, tmp_path: Path):
        """Test load_all with user, project, and local sources."""
        # User source (simulated with custom path)
        user_dir = tmp_path / "user-kaizen"
        user_specialists = user_dir / "specialists"
        user_specialists.mkdir(parents=True)
        (user_specialists / "global-helper.md").write_text(
            """# Global Helper
**Description**: User-level helper
**System Prompt**: Global helper.
"""
        )

        # Project source
        project_dir = tmp_path / "project" / ".kaizen"
        project_specialists = project_dir / "specialists"
        project_specialists.mkdir(parents=True)
        (project_specialists / "project-helper.md").write_text(
            """# Project Helper
**Description**: Project-level helper
**System Prompt**: Project helper.
"""
        )

        # Local source
        local_dir = tmp_path / "project" / ".kaizen-local"
        local_specialists = local_dir / "specialists"
        local_specialists.mkdir(parents=True)
        (local_specialists / "local-helper.md").write_text(
            """# Local Helper
**Description**: Local-level helper
**System Prompt**: Local helper.
"""
        )

        options = KaizenOptions(
            setting_sources=["user", "project", "local"],
            user_settings_dir=str(user_dir) + "/",
            cwd=str(tmp_path / "project"),
        )
        loader = SpecialistLoader(options)
        specialists, skills, context = loader.load_all()

        # All three specialists should be loaded
        assert len(specialists) == 3
        assert "global-helper" in specialists.list()
        assert "project-helper" in specialists.list()
        assert "local-helper" in specialists.list()

        # Verify sources
        assert specialists.get("global-helper").source == "user"
        assert specialists.get("project-helper").source == "project"
        assert specialists.get("local-helper").source == "local"


class TestEdgeCases:
    """Edge case and error handling tests."""

    def test_malformed_temperature_value(self, tmp_path: Path):
        """Test handling of non-numeric temperature value."""
        specialists_dir = tmp_path / ".kaizen" / "specialists"
        specialists_dir.mkdir(parents=True)
        (specialists_dir / "bad-temp.md").write_text(
            """# Bad Temp
**Description**: Has invalid temperature
**System Prompt**: Test specialist.
**Temperature**: not-a-number
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_specialists()

        # Should still load, just without temperature
        specialist = registry.get("bad-temp")
        assert specialist is not None
        assert specialist.temperature is None

    def test_malformed_max_tokens_value(self, tmp_path: Path):
        """Test handling of non-integer max_tokens value."""
        specialists_dir = tmp_path / ".kaizen" / "specialists"
        specialists_dir.mkdir(parents=True)
        (specialists_dir / "bad-tokens.md").write_text(
            """# Bad Tokens
**Description**: Has invalid max_tokens
**System Prompt**: Test specialist.
**Max Tokens**: 1024.5
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_specialists()

        specialist = registry.get("bad-tokens")
        assert specialist is not None
        assert specialist.max_tokens is None

    def test_special_characters_in_names(self, tmp_path: Path):
        """Test handling of special characters in specialist names."""
        specialists_dir = tmp_path / ".kaizen" / "specialists"
        specialists_dir.mkdir(parents=True)

        # File with special characters (valid for filesystem)
        (specialists_dir / "code-review_v2.md").write_text(
            """# Code Review V2
**Description**: Code review version 2
**System Prompt**: Review code.
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_specialists()

        assert "code-review_v2" in registry.list()

    def test_unicode_content(self, tmp_path: Path):
        """Test handling of Unicode content in specialists."""
        specialists_dir = tmp_path / ".kaizen" / "specialists"
        specialists_dir.mkdir(parents=True)
        (specialists_dir / "multilingual.md").write_text(
            """# Multilingual Specialist
**Description**: Supports multiple languages: 日本語, 中文, العربية
**System Prompt**: You can process text in multiple languages including:
- Japanese (日本語)
- Chinese (中文)
- Arabic (العربية)
- Russian (Русский)
""",
            encoding="utf-8",
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_specialists()

        specialist = registry.get("multilingual")
        assert specialist is not None
        assert "日本語" in specialist.description
        assert "中文" in specialist.system_prompt

    def test_file_not_markdown(self, tmp_path: Path):
        """Test that non-markdown files in specialists directory are ignored."""
        specialists_dir = tmp_path / ".kaizen" / "specialists"
        specialists_dir.mkdir(parents=True)

        # Non-markdown files
        (specialists_dir / "config.json").write_text('{"key": "value"}')
        (specialists_dir / "notes.txt").write_text("Some notes")
        (specialists_dir / "script.py").write_text("print('hello')")

        # Valid markdown
        (specialists_dir / "valid.md").write_text(
            """# Valid
**Description**: Valid specialist
**System Prompt**: Test.
"""
        )

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_specialists()

        assert len(registry) == 1
        assert "valid" in registry.list()

    def test_empty_skill_content_file(self, tmp_path: Path):
        """Test handling of empty SKILL.md file."""
        skill_dir = tmp_path / ".kaizen" / "skills" / "empty-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("")

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_skills()

        # Empty skill should be skipped (no description)
        assert len(registry) == 0

    def test_symlink_handling(self, tmp_path: Path):
        """Test that symlinks are followed for specialists."""
        # Create actual specialist
        actual_dir = tmp_path / "actual-specialists"
        actual_dir.mkdir()
        (actual_dir / "linked.md").write_text(
            """# Linked Specialist
**Description**: Specialist via symlink
**System Prompt**: Test symlink.
"""
        )

        # Create symlink
        kaizen_dir = tmp_path / ".kaizen"
        kaizen_dir.mkdir()
        specialists_link = kaizen_dir / "specialists"
        specialists_link.symlink_to(actual_dir)

        options = KaizenOptions(
            setting_sources=["project"],
            cwd=str(tmp_path),
        )
        loader = SpecialistLoader(options)
        registry = loader.load_specialists()

        assert "linked" in registry.list()

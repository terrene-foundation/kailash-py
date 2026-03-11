"""Filesystem discovery for specialists and skills.

This module implements filesystem-based loading of specialist and skill
definitions from .kaizen/, ~/.kaizen/, and .kaizen-local/ directories.

See: docs/architecture/adr/013-specialist-system-user-defined-capabilities.md
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from kaizen.core.kaizen_options import KaizenOptions
from kaizen.core.specialist_types import (
    ContextFile,
    SettingSource,
    SkillDefinition,
    SpecialistDefinition,
)
from kaizen.runtime.specialist_registry import SkillRegistry, SpecialistRegistry

logger = logging.getLogger(__name__)


class SpecialistLoader:
    """Filesystem discovery for specialists and skills.

    Loads specialist and skill definitions from configured directories:
    - User: ~/.kaizen/ (or custom user_settings_dir)
    - Project: .kaizen/ (or custom project_settings_dir)
    - Local: .kaizen-local/ (or custom local_settings_dir)

    Priority order (later sources override earlier):
    1. Programmatic specialists (from KaizenOptions.specialists)
    2. User specialists (~/.kaizen/specialists/)
    3. Project specialists (.kaizen/specialists/)
    4. Local specialists (.kaizen-local/specialists/)

    Example:
        >>> options = KaizenOptions(
        ...     setting_sources=["project"],  # Load from .kaizen/
        ... )
        >>> loader = SpecialistLoader(options)
        >>> specialists = loader.load_specialists()
        >>> skills = loader.load_skills()
        >>> context = loader.load_context_file()

    Specialist Markdown Format:
        # Specialist Name
        **Description**: Short description for CLI display
        **System Prompt**: Full system prompt text
        **Available Tools**: tool1, tool2, tool3  (optional)
        **Model**: gpt-4  (optional)
        **Temperature**: 0.7  (optional)
        **Memory Enabled**: true  (optional)

    Skill Directory Structure:
        .kaizen/skills/python-expert/
        ├── SKILL.md          # Entry point with metadata
        ├── patterns.md       # Additional file
        └── best-practices.md # Additional file

    SKILL.md Format:
        ---
        name: python-expert
        description: Python programming expertise with best practices
        ---
        # Python Expert Skill
        [Skill content here]
    """

    def __init__(self, options: KaizenOptions) -> None:
        """Initialize loader with options.

        Args:
            options: KaizenOptions with paths and setting sources
        """
        self.options = options

    def load_specialists(self) -> SpecialistRegistry:
        """Load specialists from all enabled sources.

        Returns:
            SpecialistRegistry with all loaded specialists
        """
        registry = SpecialistRegistry()

        # 1. Load programmatic specialists first (lowest priority)
        if self.options.specialists:
            for name, specialist in self.options.specialists.items():
                registry.register(name, specialist)
                logger.debug(f"Registered programmatic specialist: {name}")

        # 2. Load from filesystem sources (if enabled)
        if not self.options.is_isolated and self.options.setting_sources:
            for source in self.options.setting_sources:
                source_specialists = self._load_specialists_from_source(source)
                registry.merge(source_specialists, overwrite=True)

        return registry

    def _load_specialists_from_source(
        self,
        source: SettingSource,
    ) -> SpecialistRegistry:
        """Load specialists from a single source directory.

        Args:
            source: The setting source ("user", "project", or "local")

        Returns:
            SpecialistRegistry with specialists from this source
        """
        registry = SpecialistRegistry()
        specialists_dir = self.options.get_specialists_dir(source)

        if not specialists_dir.exists():
            logger.debug(f"Specialists directory does not exist: {specialists_dir}")
            return registry

        if not specialists_dir.is_dir():
            logger.warning(f"Specialists path is not a directory: {specialists_dir}")
            return registry

        # Load all .md files in the directory
        for md_file in specialists_dir.glob("*.md"):
            try:
                specialist = self._parse_specialist_file(md_file, source)
                if specialist:
                    name = md_file.stem  # filename without .md
                    registry.register(name, specialist)
                    logger.debug(f"Loaded specialist from {source}: {name}")
            except Exception as e:
                logger.error(f"Failed to parse specialist file {md_file}: {e}")

        return registry

    def _parse_specialist_file(
        self,
        path: Path,
        source: SettingSource,
    ) -> Optional[SpecialistDefinition]:
        """Parse a specialist markdown file.

        Args:
            path: Path to the markdown file
            source: Source type for metadata

        Returns:
            SpecialistDefinition if valid, None otherwise

        Markdown Format:
            # Specialist Name
            **Description**: Short description
            **System Prompt**: Full system prompt text
            **Available Tools**: tool1, tool2
            **Model**: gpt-4
            **Temperature**: 0.7
            **Memory Enabled**: true
        """
        content = path.read_text(encoding="utf-8")

        # Parse fields using regex
        description_match = re.search(r"\*\*Description\*\*:\s*(.+?)(?:\n|$)", content)
        system_prompt_match = re.search(
            r"\*\*System Prompt\*\*:\s*(.+?)(?=\n\*\*|\Z)", content, re.DOTALL
        )
        tools_match = re.search(r"\*\*Available Tools\*\*:\s*(.+?)(?:\n|$)", content)
        model_match = re.search(r"\*\*Model\*\*:\s*(.+?)(?:\n|$)", content)
        temperature_match = re.search(r"\*\*Temperature\*\*:\s*(.+?)(?:\n|$)", content)
        max_tokens_match = re.search(r"\*\*Max Tokens\*\*:\s*(.+?)(?:\n|$)", content)
        memory_match = re.search(
            r"\*\*Memory Enabled\*\*:\s*(.+?)(?:\n|$)", content, re.IGNORECASE
        )

        # Extract required fields
        if not description_match:
            logger.warning(f"Missing **Description** in {path}")
            return None

        if not system_prompt_match:
            logger.warning(f"Missing **System Prompt** in {path}")
            return None

        description = description_match.group(1).strip()
        system_prompt = system_prompt_match.group(1).strip()

        # Extract optional fields
        available_tools = None
        if tools_match:
            tools_str = tools_match.group(1).strip()
            available_tools = [t.strip() for t in tools_str.split(",")]

        model = model_match.group(1).strip() if model_match else None

        temperature = None
        if temperature_match:
            try:
                temperature = float(temperature_match.group(1).strip())
            except ValueError:
                logger.warning(f"Invalid temperature in {path}")

        max_tokens = None
        if max_tokens_match:
            try:
                max_tokens = int(max_tokens_match.group(1).strip())
            except ValueError:
                logger.warning(f"Invalid max_tokens in {path}")

        memory_enabled = False
        if memory_match:
            memory_str = memory_match.group(1).strip().lower()
            memory_enabled = memory_str in ("true", "yes", "1")

        return SpecialistDefinition(
            description=description,
            system_prompt=system_prompt,
            available_tools=available_tools,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            memory_enabled=memory_enabled,
            source=source,
            file_path=str(path),
        )

    def load_skills(self) -> SkillRegistry:
        """Load skills from all enabled sources.

        Skills are loaded with metadata only (progressive disclosure).
        Full content is loaded on demand via SkillDefinition.skill_content.

        Returns:
            SkillRegistry with all loaded skills
        """
        registry = SkillRegistry()

        if self.options.is_isolated:
            return registry

        if self.options.setting_sources:
            for source in self.options.setting_sources:
                source_skills = self._load_skills_from_source(source)
                registry.merge(source_skills, overwrite=True)

        return registry

    def _load_skills_from_source(
        self,
        source: SettingSource,
    ) -> SkillRegistry:
        """Load skills from a single source directory.

        Args:
            source: The setting source ("user", "project", or "local")

        Returns:
            SkillRegistry with skills from this source
        """
        registry = SkillRegistry()
        skills_dir = self.options.get_skills_dir(source)

        if not skills_dir.exists():
            logger.debug(f"Skills directory does not exist: {skills_dir}")
            return registry

        if not skills_dir.is_dir():
            logger.warning(f"Skills path is not a directory: {skills_dir}")
            return registry

        # Each subdirectory is a skill
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                logger.debug(f"Skill directory missing SKILL.md: {skill_dir}")
                continue

            try:
                skill = self._parse_skill_directory(skill_dir, source)
                if skill:
                    registry.register(skill)
                    logger.debug(f"Loaded skill from {source}: {skill.name}")
            except Exception as e:
                logger.error(f"Failed to parse skill directory {skill_dir}: {e}")

        return registry

    def _parse_skill_directory(
        self,
        skill_dir: Path,
        source: SettingSource,
    ) -> Optional[SkillDefinition]:
        """Parse a skill directory.

        Args:
            skill_dir: Path to the skill directory
            source: Source type for metadata

        Returns:
            SkillDefinition with metadata (content lazy-loaded)

        SKILL.md Format:
            ---
            name: skill-name
            description: Skill description with keywords
            ---
            # Skill Title
            [Skill content]
        """
        skill_file = skill_dir / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8")

        # Parse YAML frontmatter if present
        name = skill_dir.name  # Default to directory name
        description = ""

        frontmatter_match = re.match(r"^---\n(.+?)\n---\n", content, re.DOTALL)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)

            name_match = re.search(r"name:\s*(.+?)(?:\n|$)", frontmatter)
            if name_match:
                name = name_match.group(1).strip().strip("\"'")

            desc_match = re.search(
                r"description:\s*[\"']?(.+?)[\"']?(?:\n|$)", frontmatter
            )
            if desc_match:
                description = desc_match.group(1).strip()

        # If no frontmatter description, try to extract from first paragraph
        if not description:
            # Remove frontmatter and get first non-empty paragraph
            body = content
            if frontmatter_match:
                body = content[frontmatter_match.end() :]
            lines = [
                l.strip()
                for l in body.split("\n")
                if l.strip() and not l.startswith("#")
            ]
            if lines:
                description = lines[0][:200]  # First 200 chars

        if not description:
            logger.warning(f"Skill {name} has no description")
            return None

        return SkillDefinition(
            name=name,
            description=description,
            location=str(skill_dir),
            source=source,
            # skill_content is None - loaded lazily
        )

    def load_skill_content(self, skill: SkillDefinition) -> SkillDefinition:
        """Load full content for a skill (progressive disclosure).

        Args:
            skill: SkillDefinition with location set

        Returns:
            Updated SkillDefinition with content loaded
        """
        skill_dir = Path(skill.location)
        skill_file = skill_dir / "SKILL.md"

        if not skill_file.exists():
            logger.warning(f"Skill file not found: {skill_file}")
            return skill

        # Load SKILL.md content
        skill.skill_content = skill_file.read_text(encoding="utf-8")

        # Load additional files
        additional_files: dict[str, str] = {}
        for md_file in skill_dir.glob("*.md"):
            if md_file.name != "SKILL.md":
                additional_files[md_file.name] = md_file.read_text(encoding="utf-8")

        skill.additional_files = additional_files if additional_files else None

        return skill

    def load_context_file(self) -> Optional[ContextFile]:
        """Load project context file (e.g., KAIZEN.md).

        Loads from the highest-priority source that has the file:
        1. Local (.kaizen-local/KAIZEN.md)
        2. Project (.kaizen/KAIZEN.md)
        3. User (~/.kaizen/KAIZEN.md)

        Returns:
            ContextFile if found, None otherwise
        """
        if self.options.is_isolated:
            return None

        if not self.options.setting_sources:
            return None

        # Check sources in reverse priority order (local > project > user)
        for source in reversed(self.options.setting_sources):
            context_path = self.options.get_context_file(source)
            if context_path.exists() and context_path.is_file():
                try:
                    content = context_path.read_text(encoding="utf-8")
                    return ContextFile(
                        path=str(context_path),
                        content=content,
                        source=source,
                    )
                except Exception as e:
                    logger.error(f"Failed to read context file {context_path}: {e}")

        return None

    def load_all(
        self,
    ) -> tuple[SpecialistRegistry, SkillRegistry, Optional[ContextFile]]:
        """Load specialists, skills, and context file.

        Convenience method to load all resources at once.

        Returns:
            Tuple of (specialists, skills, context_file)
        """
        specialists = self.load_specialists()
        skills = self.load_skills()
        context = self.load_context_file()
        return specialists, skills, context


__all__ = [
    "SpecialistLoader",
]

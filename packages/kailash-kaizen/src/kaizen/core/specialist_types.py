"""Specialist and Skill type definitions for user-defined capabilities.

This module implements ADR-013: Specialist System & User-Defined Capabilities.
It provides type-safe definitions for:
- SpecialistDefinition: Programmatic or filesystem-based specialist definitions
- SkillDefinition: Progressive disclosure skill definitions
- SettingSource: Literal type for setting source locations

See: docs/architecture/adr/013-specialist-system-user-defined-capabilities.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

# Type alias for setting sources
SettingSource = Literal["user", "project", "local"]


@dataclass
class SpecialistDefinition:
    """Type-safe specialist definition (programmatic or filesystem).

    A specialist is a configured agent with:
    - A system prompt that defines its behavior
    - Optional tool restrictions
    - Optional model/temperature overrides
    - Source tracking for filesystem-loaded specialists

    Example (Programmatic):
        >>> specialist = SpecialistDefinition(
        ...     description="Code review specialist",
        ...     system_prompt="You are a senior code reviewer...",
        ...     available_tools=["Read", "Glob", "Grep"],
        ...     model="gpt-4",
        ... )

    Example (Filesystem - loaded by SpecialistLoader):
        Markdown format in .kaizen/specialists/code-reviewer.md:
        ```
        # Code Reviewer
        **Description**: Expert code review specialist
        **System Prompt**: You are a senior code reviewer...
        **Available Tools**: Read, Glob, Grep
        **Model**: gpt-4
        ```

    Attributes:
        description: Short description for CLI/UI display (required)
        system_prompt: Full system prompt for the specialist (required)
        available_tools: Optional list of allowed tool names (None = all tools)
        model: Optional model override (e.g., "gpt-4", "claude-3-opus")
        signature: Optional signature class name for typed I/O
        temperature: Optional temperature override (0.0-2.0)
        max_tokens: Optional max tokens override
        memory_enabled: Enable conversation memory (default: False)
        source: Where this specialist was loaded from
        file_path: Path to source file if loaded from filesystem
    """

    # Required fields
    description: str
    system_prompt: str

    # Optional fields
    available_tools: Optional[list[str]] = None
    model: Optional[str] = None
    signature: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    memory_enabled: bool = False

    # Metadata (for filesystem specialists)
    source: Literal["programmatic", "user", "project", "local"] = "programmatic"
    file_path: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate specialist definition."""
        if not self.description:
            raise ValueError("Specialist must have a description")
        if not self.system_prompt:
            raise ValueError("Specialist must have a system_prompt")

        # Validate temperature if provided
        if self.temperature is not None:
            if not 0.0 <= self.temperature <= 2.0:
                raise ValueError(
                    f"Temperature must be between 0.0 and 2.0, got {self.temperature}"
                )

        # Validate max_tokens if provided
        if self.max_tokens is not None:
            if self.max_tokens <= 0:
                raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "description": self.description,
            "system_prompt": self.system_prompt,
            "available_tools": self.available_tools,
            "model": self.model,
            "signature": self.signature,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "memory_enabled": self.memory_enabled,
            "source": self.source,
            "file_path": self.file_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SpecialistDefinition":
        """Create from dictionary."""
        return cls(
            description=data["description"],
            system_prompt=data["system_prompt"],
            available_tools=data.get("available_tools"),
            model=data.get("model"),
            signature=data.get("signature"),
            temperature=data.get("temperature"),
            max_tokens=data.get("max_tokens"),
            memory_enabled=data.get("memory_enabled", False),
            source=data.get("source", "programmatic"),
            file_path=data.get("file_path"),
        )


@dataclass
class SkillDefinition:
    """Progressive disclosure skill definition.

    Skills are knowledge bundles that can be loaded on-demand:
    - Metadata (name, description) is loaded first for matching
    - Full content (SKILL.md) is loaded lazily when invoked
    - Additional linked files are loaded on-demand

    This follows the progressive disclosure pattern:
    1. Metadata layer: Always in context for skill matching
    2. SKILL.md layer: Loaded when skill is invoked
    3. Sub-file layer: Loaded only when specifically needed

    Example directory structure:
        .kaizen/skills/python-expert/
        ├── SKILL.md          # Entry point (loaded on invoke)
        ├── patterns.md       # Sub-topic (loaded on demand)
        └── best-practices.md # Sub-topic (loaded on demand)

    Attributes:
        name: Unique skill identifier
        description: Description with trigger keywords for matching
        location: Path to skill directory
        skill_content: SKILL.md content (lazy loaded, None until invoked)
        additional_files: Dict of filename -> content (lazy loaded)
        source: Where this skill was loaded from
    """

    # Metadata (loaded first)
    name: str
    description: str
    location: str

    # Progressive loading (lazy)
    skill_content: Optional[str] = None
    additional_files: Optional[dict[str, str]] = field(default=None)

    # Source tracking
    source: SettingSource = "project"

    def __post_init__(self) -> None:
        """Validate skill definition."""
        if not self.name:
            raise ValueError("Skill must have a name")
        if not self.description:
            raise ValueError("Skill must have a description")
        if not self.location:
            raise ValueError("Skill must have a location")

    @property
    def is_loaded(self) -> bool:
        """Check if skill content has been loaded."""
        return self.skill_content is not None

    def get_file(self, filename: str) -> Optional[str]:
        """Get content of an additional file.

        Args:
            filename: Name of the file to get

        Returns:
            File content if loaded, None otherwise
        """
        if self.additional_files is None:
            return None
        return self.additional_files.get(filename)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "location": self.location,
            "skill_content": self.skill_content,
            "additional_files": self.additional_files,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillDefinition":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            description=data["description"],
            location=data["location"],
            skill_content=data.get("skill_content"),
            additional_files=data.get("additional_files"),
            source=data.get("source", "project"),
        )


@dataclass
class ContextFile:
    """Project context file (e.g., KAIZEN.md).

    Context files are automatically injected into agent system prompts
    to provide project-specific information.

    Attributes:
        path: Path to the context file
        content: File content
        source: Where this context file was loaded from
    """

    path: str
    content: str
    source: SettingSource = "project"

    def __post_init__(self) -> None:
        """Validate context file."""
        if not self.path:
            raise ValueError("Context file must have a path")
        if self.content is None:
            raise ValueError("Context file must have content")


__all__ = [
    "SettingSource",
    "SpecialistDefinition",
    "SkillDefinition",
    "ContextFile",
]

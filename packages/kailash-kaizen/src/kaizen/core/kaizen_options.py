"""Kaizen runtime configuration with user-defined capabilities.

This module implements ADR-013: Specialist System & User-Defined Capabilities.
KaizenOptions provides configuration for:
- Programmatic specialists (in-memory, type-safe)
- Filesystem settings (explicit opt-in)
- Configurable paths for all directories and files
- Runtime settings (budget, audit, etc.)

See: docs/architecture/adr/013-specialist-system-user-defined-capabilities.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from kaizen.core.specialist_types import SettingSource, SpecialistDefinition


@dataclass
class KaizenOptions:
    """Kaizen runtime configuration with user-defined capabilities.

    This class configures how Kaizen loads specialists, skills, and context:

    1. **Programmatic Specialists** (in-memory, type-safe):
       Passed via `specialists` parameter. No filesystem access needed.

    2. **Filesystem Settings** (explicit opt-in):
       Enabled via `setting_sources` parameter. Loads from:
       - "user": ~/.kaizen/ (user-level settings)
       - "project": .kaizen/ (project-level settings)
       - "local": .kaizen-local/ (local overrides, gitignored)

    3. **Configurable Paths**:
       All directory and file names are configurable.

    Example (Programmatic only - isolated mode):
        >>> options = KaizenOptions(
        ...     specialists={
        ...         "code-reviewer": SpecialistDefinition(
        ...             description="Code review specialist",
        ...             system_prompt="You are a senior code reviewer..."
        ...         )
        ...     }
        ... )
        >>> # setting_sources=None means no filesystem loading

    Example (Filesystem loading - opt-in):
        >>> options = KaizenOptions(
        ...     setting_sources=["project"],  # Load from .kaizen/
        ... )
        >>> # Loads specialists from .kaizen/specialists/
        >>> # Loads skills from .kaizen/skills/
        >>> # Injects .kaizen/KAIZEN.md into system prompt

    Example (Full loading with all sources):
        >>> options = KaizenOptions(
        ...     setting_sources=["user", "project", "local"],
        ...     user_settings_dir="~/.my-kaizen/",  # Custom user dir
        ...     context_file_name="PROJECT.md",  # Custom context file
        ... )

    Attributes:
        specialists: Dict of name -> SpecialistDefinition (programmatic)
        setting_sources: List of sources to load from (None = disabled)
        user_settings_dir: User settings directory (default: ~/.kaizen/)
        project_settings_dir: Project settings directory (default: .kaizen/)
        local_settings_dir: Local settings directory (default: .kaizen-local/)
        context_file_name: Context file name (default: KAIZEN.md)
        specialists_dir_name: Specialists subdirectory (default: specialists)
        skills_dir_name: Skills subdirectory (default: skills)
        commands_dir_name: Commands subdirectory (default: commands)
        cwd: Working directory for relative paths
        budget_limit_usd: Maximum budget in USD (None = unlimited)
        audit_enabled: Enable audit logging (default: True)
    """

    # ──────────────────────────────────────────────────────────────
    # PROGRAMMATIC SPECIALISTS (in-memory, type-safe)
    # ──────────────────────────────────────────────────────────────
    specialists: Optional[dict[str, SpecialistDefinition]] = None

    # ──────────────────────────────────────────────────────────────
    # FILESYSTEM SETTINGS (explicit opt-in)
    # ──────────────────────────────────────────────────────────────
    setting_sources: Optional[list[SettingSource]] = None
    # None = disabled (isolated mode, programmatic only)
    # [] = enabled but empty (no sources to load)
    # ["project"] = load from project only
    # ["user", "project", "local"] = load all sources

    # ──────────────────────────────────────────────────────────────
    # CONFIGURABLE PATHS (user can override)
    # ──────────────────────────────────────────────────────────────
    # User settings directory
    user_settings_dir: Union[str, Path] = field(default="~/.kaizen/")

    # Project settings directory
    project_settings_dir: Union[str, Path] = field(default=".kaizen/")

    # Local settings directory (gitignored)
    local_settings_dir: Union[str, Path] = field(default=".kaizen-local/")

    # Context file name (auto-injected into system prompt)
    context_file_name: str = field(default="KAIZEN.md")

    # Subdirectory names
    specialists_dir_name: str = field(default="specialists")
    skills_dir_name: str = field(default="skills")
    commands_dir_name: str = field(default="commands")

    # ──────────────────────────────────────────────────────────────
    # RUNTIME SETTINGS
    # ──────────────────────────────────────────────────────────────
    cwd: Optional[Union[str, Path]] = None

    # Budget and audit
    budget_limit_usd: Optional[float] = None
    audit_enabled: bool = True

    def __post_init__(self) -> None:
        """Validate options and normalize paths."""
        # Validate budget if provided
        if self.budget_limit_usd is not None and self.budget_limit_usd < 0:
            raise ValueError(
                f"budget_limit_usd must be non-negative, got {self.budget_limit_usd}"
            )

        # Validate setting_sources if provided
        if self.setting_sources is not None:
            valid_sources = {"user", "project", "local"}
            for source in self.setting_sources:
                if source not in valid_sources:
                    raise ValueError(
                        f"Invalid setting source: {source}. "
                        f"Must be one of: {valid_sources}"
                    )

    @property
    def is_isolated(self) -> bool:
        """Check if running in isolated mode (no filesystem loading)."""
        return self.setting_sources is None

    @property
    def has_user_source(self) -> bool:
        """Check if user settings are enabled."""
        return self.setting_sources is not None and "user" in self.setting_sources

    @property
    def has_project_source(self) -> bool:
        """Check if project settings are enabled."""
        return self.setting_sources is not None and "project" in self.setting_sources

    @property
    def has_local_source(self) -> bool:
        """Check if local settings are enabled."""
        return self.setting_sources is not None and "local" in self.setting_sources

    def get_source_dir(self, source: SettingSource) -> Path:
        """Get the directory path for a setting source.

        Args:
            source: The setting source ("user", "project", or "local")

        Returns:
            Resolved Path to the source directory

        Raises:
            ValueError: If source is invalid
        """
        base_path = self.cwd or Path.cwd()
        if isinstance(base_path, str):
            base_path = Path(base_path)

        if source == "user":
            user_dir = self.user_settings_dir
            if isinstance(user_dir, str):
                user_dir = Path(user_dir)
            return user_dir.expanduser().resolve()

        elif source == "project":
            project_dir = self.project_settings_dir
            if isinstance(project_dir, str):
                project_dir = Path(project_dir)
            if not project_dir.is_absolute():
                project_dir = base_path / project_dir
            return project_dir.resolve()

        elif source == "local":
            local_dir = self.local_settings_dir
            if isinstance(local_dir, str):
                local_dir = Path(local_dir)
            if not local_dir.is_absolute():
                local_dir = base_path / local_dir
            return local_dir.resolve()

        else:
            raise ValueError(f"Invalid setting source: {source}")

    def get_specialists_dir(self, source: SettingSource) -> Path:
        """Get the specialists directory for a source."""
        return self.get_source_dir(source) / self.specialists_dir_name

    def get_skills_dir(self, source: SettingSource) -> Path:
        """Get the skills directory for a source."""
        return self.get_source_dir(source) / self.skills_dir_name

    def get_commands_dir(self, source: SettingSource) -> Path:
        """Get the commands directory for a source."""
        return self.get_source_dir(source) / self.commands_dir_name

    def get_context_file(self, source: SettingSource) -> Path:
        """Get the context file path for a source."""
        return self.get_source_dir(source) / self.context_file_name

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "specialists": (
                {k: v.to_dict() for k, v in self.specialists.items()}
                if self.specialists
                else None
            ),
            "setting_sources": self.setting_sources,
            "user_settings_dir": str(self.user_settings_dir),
            "project_settings_dir": str(self.project_settings_dir),
            "local_settings_dir": str(self.local_settings_dir),
            "context_file_name": self.context_file_name,
            "specialists_dir_name": self.specialists_dir_name,
            "skills_dir_name": self.skills_dir_name,
            "commands_dir_name": self.commands_dir_name,
            "cwd": str(self.cwd) if self.cwd else None,
            "budget_limit_usd": self.budget_limit_usd,
            "audit_enabled": self.audit_enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KaizenOptions":
        """Create from dictionary."""
        specialists = None
        if data.get("specialists"):
            specialists = {
                k: SpecialistDefinition.from_dict(v)
                for k, v in data["specialists"].items()
            }

        return cls(
            specialists=specialists,
            setting_sources=data.get("setting_sources"),
            user_settings_dir=data.get("user_settings_dir", "~/.kaizen/"),
            project_settings_dir=data.get("project_settings_dir", ".kaizen/"),
            local_settings_dir=data.get("local_settings_dir", ".kaizen-local/"),
            context_file_name=data.get("context_file_name", "KAIZEN.md"),
            specialists_dir_name=data.get("specialists_dir_name", "specialists"),
            skills_dir_name=data.get("skills_dir_name", "skills"),
            commands_dir_name=data.get("commands_dir_name", "commands"),
            cwd=data.get("cwd"),
            budget_limit_usd=data.get("budget_limit_usd"),
            audit_enabled=data.get("audit_enabled", True),
        )


__all__ = [
    "KaizenOptions",
]

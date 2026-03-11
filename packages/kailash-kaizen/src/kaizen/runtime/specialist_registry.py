"""In-memory registry for specialists and skills.

This module provides thread-safe storage and retrieval of specialist
and skill definitions loaded from programmatic sources or filesystem.

See: docs/architecture/adr/013-specialist-system-user-defined-capabilities.md
"""

from __future__ import annotations

import threading
from typing import Iterator, Optional

from kaizen.core.specialist_types import SkillDefinition, SpecialistDefinition


class SpecialistRegistry:
    """Thread-safe in-memory registry for specialists.

    This registry stores specialist definitions and provides:
    - Thread-safe registration and retrieval
    - Priority-based merging (local > project > user > programmatic)
    - Listing and iteration support
    - Clear and remove operations

    Example:
        >>> registry = SpecialistRegistry()
        >>> registry.register("code-reviewer", SpecialistDefinition(
        ...     description="Code review specialist",
        ...     system_prompt="You are a senior code reviewer..."
        ... ))
        >>> specialist = registry.get("code-reviewer")
        >>> print(specialist.description)
        'Code review specialist'

    Thread Safety:
        All operations are protected by a reentrant lock, making
        this registry safe to use from multiple threads.
    """

    def __init__(self) -> None:
        """Initialize empty registry with thread lock."""
        self._specialists: dict[str, SpecialistDefinition] = {}
        self._lock = threading.RLock()

    def register(
        self,
        name: str,
        specialist: SpecialistDefinition,
        *,
        overwrite: bool = True,
    ) -> bool:
        """Register a specialist in the registry.

        Args:
            name: Unique name for the specialist
            specialist: SpecialistDefinition to register
            overwrite: If True, overwrite existing specialist with same name

        Returns:
            True if registered, False if already exists and overwrite=False

        Raises:
            ValueError: If name is empty
        """
        if not name:
            raise ValueError("Specialist name cannot be empty")

        with self._lock:
            if name in self._specialists and not overwrite:
                return False
            self._specialists[name] = specialist
            return True

    def get(self, name: str) -> Optional[SpecialistDefinition]:
        """Get a specialist by name.

        Args:
            name: Name of the specialist to retrieve

        Returns:
            SpecialistDefinition if found, None otherwise
        """
        with self._lock:
            return self._specialists.get(name)

    def remove(self, name: str) -> bool:
        """Remove a specialist from the registry.

        Args:
            name: Name of the specialist to remove

        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if name in self._specialists:
                del self._specialists[name]
                return True
            return False

    def clear(self) -> int:
        """Remove all specialists from the registry.

        Returns:
            Number of specialists removed
        """
        with self._lock:
            count = len(self._specialists)
            self._specialists.clear()
            return count

    def list(self) -> list[str]:
        """Get list of all registered specialist names.

        Returns:
            List of specialist names (sorted alphabetically)
        """
        with self._lock:
            return sorted(self._specialists.keys())

    def __len__(self) -> int:
        """Get number of registered specialists."""
        with self._lock:
            return len(self._specialists)

    def __contains__(self, name: str) -> bool:
        """Check if specialist exists in registry."""
        with self._lock:
            return name in self._specialists

    def __iter__(self) -> Iterator[tuple[str, SpecialistDefinition]]:
        """Iterate over (name, specialist) pairs."""
        with self._lock:
            # Create a copy to allow safe iteration
            items = list(self._specialists.items())
        return iter(items)

    def merge(
        self,
        other: "SpecialistRegistry",
        *,
        overwrite: bool = True,
    ) -> int:
        """Merge another registry into this one.

        Args:
            other: Registry to merge from
            overwrite: If True, other's specialists overwrite existing

        Returns:
            Number of specialists added or updated
        """
        count = 0
        for name, specialist in other:
            if self.register(name, specialist, overwrite=overwrite):
                count += 1
        return count

    def filter_by_source(
        self,
        source: str,
    ) -> list[tuple[str, SpecialistDefinition]]:
        """Get specialists from a specific source.

        Args:
            source: Source to filter by ("programmatic", "user", "project", "local")

        Returns:
            List of (name, specialist) tuples from the specified source
        """
        with self._lock:
            return [
                (name, spec)
                for name, spec in self._specialists.items()
                if spec.source == source
            ]

    def to_dict(self) -> dict[str, dict]:
        """Convert registry to dictionary for serialization."""
        with self._lock:
            return {
                name: specialist.to_dict()
                for name, specialist in self._specialists.items()
            }

    @classmethod
    def from_dict(cls, data: dict[str, dict]) -> "SpecialistRegistry":
        """Create registry from dictionary."""
        registry = cls()
        for name, spec_data in data.items():
            specialist = SpecialistDefinition.from_dict(spec_data)
            registry.register(name, specialist)
        return registry


class SkillRegistry:
    """Thread-safe in-memory registry for skills.

    Similar to SpecialistRegistry but for SkillDefinitions.
    Supports progressive loading - skills are registered with
    metadata first, then content is loaded on demand.

    Example:
        >>> registry = SkillRegistry()
        >>> registry.register(SkillDefinition(
        ...     name="python-expert",
        ...     description="Python programming expertise",
        ...     location="/path/to/skill",
        ... ))
        >>> skill = registry.get("python-expert")
        >>> print(skill.is_loaded)  # False - content not yet loaded
    """

    def __init__(self) -> None:
        """Initialize empty registry with thread lock."""
        self._skills: dict[str, SkillDefinition] = {}
        self._lock = threading.RLock()

    def register(
        self,
        skill: SkillDefinition,
        *,
        overwrite: bool = True,
    ) -> bool:
        """Register a skill in the registry.

        Args:
            skill: SkillDefinition to register (uses skill.name as key)
            overwrite: If True, overwrite existing skill with same name

        Returns:
            True if registered, False if already exists and overwrite=False
        """
        with self._lock:
            if skill.name in self._skills and not overwrite:
                return False
            self._skills[skill.name] = skill
            return True

    def get(self, name: str) -> Optional[SkillDefinition]:
        """Get a skill by name.

        Args:
            name: Name of the skill to retrieve

        Returns:
            SkillDefinition if found, None otherwise
        """
        with self._lock:
            return self._skills.get(name)

    def remove(self, name: str) -> bool:
        """Remove a skill from the registry.

        Args:
            name: Name of the skill to remove

        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if name in self._skills:
                del self._skills[name]
                return True
            return False

    def clear(self) -> int:
        """Remove all skills from the registry.

        Returns:
            Number of skills removed
        """
        with self._lock:
            count = len(self._skills)
            self._skills.clear()
            return count

    def list(self) -> list[str]:
        """Get list of all registered skill names.

        Returns:
            List of skill names (sorted alphabetically)
        """
        with self._lock:
            return sorted(self._skills.keys())

    def search(self, query: str) -> list[SkillDefinition]:
        """Search skills by keyword in name or description.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching skills
        """
        query_lower = query.lower()
        with self._lock:
            return [
                skill
                for skill in self._skills.values()
                if query_lower in skill.name.lower()
                or query_lower in skill.description.lower()
            ]

    def __len__(self) -> int:
        """Get number of registered skills."""
        with self._lock:
            return len(self._skills)

    def __contains__(self, name: str) -> bool:
        """Check if skill exists in registry."""
        with self._lock:
            return name in self._skills

    def __iter__(self) -> Iterator[tuple[str, SkillDefinition]]:
        """Iterate over (name, skill) pairs."""
        with self._lock:
            items = list(self._skills.items())
        return iter(items)

    def merge(
        self,
        other: "SkillRegistry",
        *,
        overwrite: bool = True,
    ) -> int:
        """Merge another registry into this one.

        Args:
            other: Registry to merge from
            overwrite: If True, other's skills overwrite existing

        Returns:
            Number of skills added or updated
        """
        count = 0
        for _, skill in other:
            if self.register(skill, overwrite=overwrite):
                count += 1
        return count

    def to_dict(self) -> dict[str, dict]:
        """Convert registry to dictionary for serialization."""
        with self._lock:
            return {name: skill.to_dict() for name, skill in self._skills.items()}

    @classmethod
    def from_dict(cls, data: dict[str, dict]) -> "SkillRegistry":
        """Create registry from dictionary."""
        registry = cls()
        for _, skill_data in data.items():
            skill = SkillDefinition.from_dict(skill_data)
            registry.register(skill)
        return registry


__all__ = [
    "SpecialistRegistry",
    "SkillRegistry",
]

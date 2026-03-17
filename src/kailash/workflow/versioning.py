"""Workflow versioning system for the Kailash SDK.

This module provides a versioning registry for workflows, enabling
teams to manage multiple versions of the same workflow with semver-based
ordering, deprecation support, and optional migration functions.

Usage:
    >>> from kailash.workflow.versioning import WorkflowVersionRegistry, VersionedWorkflow
    >>> from kailash.workflow.builder import WorkflowBuilder
    >>>
    >>> registry = WorkflowVersionRegistry()
    >>>
    >>> v1 = WorkflowBuilder()
    >>> v1.add_node("CSVReaderNode", "reader", {"file_path": "data_v1.csv"})
    >>> registry.register("etl_pipeline", "1.0.0", v1)
    >>>
    >>> v2 = WorkflowBuilder()
    >>> v2.add_node("CSVReaderNode", "reader", {"file_path": "data_v2.csv"})
    >>> registry.register("etl_pipeline", "2.0.0", v2)
    >>>
    >>> latest = registry.get("etl_pipeline")  # Returns v2
    >>> specific = registry.get("etl_pipeline", version="1.0.0")
    >>>
    >>> registry.deprecate("etl_pipeline", "1.0.0")
    >>> latest = registry.get("etl_pipeline")  # Still returns v2

See Also:
    - WorkflowBuilder: Creates workflow definitions
    - LocalRuntime: Executes workflows

Version:
    Added in: v0.13.0
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "VersionedWorkflow",
    "WorkflowVersionRegistry",
    "parse_semver",
]


def parse_semver(version: str) -> Tuple[int, int, int]:
    """Parse a semantic version string into a comparable tuple.

    Supports standard semver format: MAJOR.MINOR.PATCH. Pre-release
    suffixes (e.g., "-beta.1") are stripped for ordering purposes.

    Args:
        version: A semver string like "1.2.3" or "2.0.0-beta.1".

    Returns:
        A tuple of (major, minor, patch) integers.

    Raises:
        ValueError: If the version string is not valid semver.

    Example:
        >>> parse_semver("1.2.3")
        (1, 2, 3)
        >>> parse_semver("0.10.0")
        (0, 10, 0)
    """
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(
            f"Invalid semver format: '{version}'. "
            f"Expected format: MAJOR.MINOR.PATCH (e.g., '1.0.0')"
        )
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


@dataclass
class VersionedWorkflow:
    """A workflow paired with version metadata.

    Attributes:
        version: Semantic version string (e.g., "1.0.0").
        workflow_builder: The WorkflowBuilder instance for this version.
        deprecated: Whether this version is deprecated. Deprecated versions
            are excluded from "latest" resolution but can still be fetched
            by explicit version.
        migration_fn: Optional callable that migrates inputs from the
            previous version format to this version's format. Signature:
            (old_inputs: Dict) -> Dict.
    """

    version: str
    workflow_builder: Any
    deprecated: bool = False
    migration_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None

    def __post_init__(self) -> None:
        """Validate the version string on creation."""
        parse_semver(self.version)


class WorkflowVersionRegistry:
    """Registry for managing versioned workflows.

    Provides registration, lookup, deprecation, and listing of workflow
    versions. Version resolution uses semantic versioning for ordering,
    so "latest" always returns the highest non-deprecated version.

    Thread Safety:
        This class is not thread-safe. If used from multiple threads,
        external synchronization is required.

    Example:
        >>> registry = WorkflowVersionRegistry()
        >>> registry.register("my_workflow", "1.0.0", builder_v1)
        >>> registry.register("my_workflow", "1.1.0", builder_v1_1)
        >>> registry.register("my_workflow", "2.0.0", builder_v2)
        >>>
        >>> registry.deprecate("my_workflow", "1.0.0")
        >>> latest = registry.get("my_workflow")  # Returns 2.0.0 version
        >>> versions = registry.list_versions("my_workflow")  # All 3 versions
    """

    def __init__(self) -> None:
        """Initialize an empty version registry."""
        self._registry: Dict[str, Dict[str, VersionedWorkflow]] = {}

    def register(
        self,
        name: str,
        version: str,
        workflow_builder: Any,
        migration_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> VersionedWorkflow:
        """Register a new workflow version.

        Args:
            name: The workflow name (e.g., "etl_pipeline").
            version: Semantic version string (e.g., "1.0.0").
            workflow_builder: The WorkflowBuilder instance for this version.
            migration_fn: Optional function to migrate inputs from the
                previous version.

        Returns:
            The created VersionedWorkflow instance.

        Raises:
            ValueError: If the version string is invalid or the version
                is already registered for this workflow name.

        Example:
            >>> vw = registry.register("my_wf", "1.0.0", builder)
            >>> vw.version
            '1.0.0'
        """
        # Validate semver (raises ValueError if invalid)
        parse_semver(version)

        if name not in self._registry:
            self._registry[name] = {}

        if version in self._registry[name]:
            raise ValueError(
                f"Version '{version}' is already registered for workflow '{name}'. "
                f"Use a new version number or remove the existing one first."
            )

        versioned = VersionedWorkflow(
            version=version,
            workflow_builder=workflow_builder,
            deprecated=False,
            migration_fn=migration_fn,
        )
        self._registry[name][version] = versioned

        logger.info("Registered workflow '%s' version '%s'", name, version)
        return versioned

    def get(
        self,
        name: str,
        version: Optional[str] = None,
    ) -> VersionedWorkflow:
        """Get a workflow version.

        If version is None, returns the latest non-deprecated version
        based on semver ordering. If version is specified, returns that
        exact version (even if deprecated).

        Args:
            name: The workflow name.
            version: Optional specific version to retrieve. If None,
                returns the latest non-deprecated version.

        Returns:
            The VersionedWorkflow for the requested version.

        Raises:
            KeyError: If the workflow name is not found, or no matching
                version exists.

        Example:
            >>> latest = registry.get("my_wf")
            >>> specific = registry.get("my_wf", version="1.0.0")
        """
        if name not in self._registry:
            raise KeyError(f"Workflow '{name}' is not registered")

        versions = self._registry[name]

        if version is not None:
            if version not in versions:
                raise KeyError(
                    f"Version '{version}' not found for workflow '{name}'. "
                    f"Available versions: {sorted(versions.keys())}"
                )
            return versions[version]

        # Find latest non-deprecated version
        candidates = [vw for vw in versions.values() if not vw.deprecated]

        if not candidates:
            raise KeyError(
                f"No non-deprecated versions available for workflow '{name}'. "
                f"All versions are deprecated: {sorted(versions.keys())}"
            )

        # Sort by semver and return the highest
        candidates.sort(key=lambda vw: parse_semver(vw.version))
        return candidates[-1]

    def list_versions(self, name: str) -> List[VersionedWorkflow]:
        """List all versions of a workflow, sorted by semver ascending.

        Args:
            name: The workflow name.

        Returns:
            A list of VersionedWorkflow instances, sorted by version.

        Raises:
            KeyError: If the workflow name is not found.

        Example:
            >>> versions = registry.list_versions("my_wf")
            >>> [v.version for v in versions]
            ['1.0.0', '1.1.0', '2.0.0']
        """
        if name not in self._registry:
            raise KeyError(f"Workflow '{name}' is not registered")

        versions = list(self._registry[name].values())
        versions.sort(key=lambda vw: parse_semver(vw.version))
        return versions

    def deprecate(self, name: str, version: str) -> None:
        """Mark a workflow version as deprecated.

        Deprecated versions are excluded from "latest" resolution via
        get(name) but can still be fetched with get(name, version=version).

        Args:
            name: The workflow name.
            version: The version to deprecate.

        Raises:
            KeyError: If the workflow name or version is not found.

        Example:
            >>> registry.deprecate("my_wf", "1.0.0")
            >>> registry.get("my_wf", version="1.0.0").deprecated
            True
        """
        if name not in self._registry:
            raise KeyError(f"Workflow '{name}' is not registered")

        if version not in self._registry[name]:
            raise KeyError(f"Version '{version}' not found for workflow '{name}'")

        self._registry[name][version].deprecated = True
        logger.info("Deprecated workflow '%s' version '%s'", name, version)

    def list_workflow_names(self) -> List[str]:
        """List all registered workflow names.

        Returns:
            A sorted list of workflow names.

        Example:
            >>> registry.list_workflow_names()
            ['etl_pipeline', 'report_generator']
        """
        return sorted(self._registry.keys())

    def remove(self, name: str, version: str) -> None:
        """Remove a workflow version from the registry.

        Args:
            name: The workflow name.
            version: The version to remove.

        Raises:
            KeyError: If the workflow name or version is not found.
        """
        if name not in self._registry:
            raise KeyError(f"Workflow '{name}' is not registered")

        if version not in self._registry[name]:
            raise KeyError(f"Version '{version}' not found for workflow '{name}'")

        del self._registry[name][version]

        # Clean up empty workflow entries
        if not self._registry[name]:
            del self._registry[name]

        logger.info("Removed workflow '%s' version '%s'", name, version)

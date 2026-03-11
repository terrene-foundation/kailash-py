"""
Compatibility Checker for Experimental Features.

This module provides the CompatibilityChecker class for validating
feature compatibility with framework versions and dependencies.

Components:
- CompatibilityChecker: Validate feature compatibility and suggest upgrades
"""

from typing import List, Optional

from kaizen.research.experimental import ExperimentalFeature
from packaging import version as pkg_version


class CompatibilityChecker:
    """
    Check feature compatibility with framework versions.

    Validates feature compatibility requirements, suggests upgrades,
    and validates dependencies.

    Example:
        >>> checker = CompatibilityChecker()
        >>> is_compatible = checker.check_compatibility(feature, "0.2.0")
        >>> if not is_compatible:
        ...     suggestion = checker.suggest_upgrade(feature, "0.2.0")
        ...     print(suggestion)
    """

    def __init__(self):
        """Initialize CompatibilityChecker."""
        pass

    def check_compatibility(
        self, feature: ExperimentalFeature, framework_version: str
    ) -> bool:
        """
        Check if feature is compatible with framework version.

        Args:
            feature: ExperimentalFeature to check
            framework_version: Framework version string (e.g., "0.2.0")

        Returns:
            True if compatible, False otherwise

        Example:
            >>> is_compatible = checker.check_compatibility(feature, "0.2.0")
            >>> if is_compatible:
            ...     feature.enable()
        """
        if not feature.compatibility:
            return True  # No requirements = compatible

        # Check kaizen framework version requirement
        requirement = feature.compatibility.get("kaizen", ">=0.0.0")

        return self._check_version_requirement(framework_version, requirement)

    def get_compatible_features(
        self, features: List[ExperimentalFeature], framework_version: str
    ) -> List[ExperimentalFeature]:
        """
        Get all features compatible with framework version.

        Args:
            features: List of ExperimentalFeature instances
            framework_version: Framework version string

        Returns:
            List of compatible features

        Example:
            >>> compatible = checker.get_compatible_features(features, "0.2.0")
            >>> print(f"Found {len(compatible)} compatible features")
        """
        return [f for f in features if self.check_compatibility(f, framework_version)]

    def suggest_upgrade(
        self, feature: ExperimentalFeature, current_version: str
    ) -> Optional[str]:
        """
        Suggest framework upgrade for incompatible feature.

        Args:
            feature: ExperimentalFeature to check
            current_version: Current framework version

        Returns:
            Upgrade suggestion string, or None if already compatible

        Example:
            >>> suggestion = checker.suggest_upgrade(feature, "0.1.0")
            >>> if suggestion:
            ...     print(f"Upgrade needed: {suggestion}")
        """
        if self.check_compatibility(feature, current_version):
            return None  # Already compatible

        # Extract required version from compatibility
        requirement = feature.compatibility.get("kaizen", "")

        if ">=" in requirement:
            required_version = requirement.split(">=")[1].strip()
            return f"Upgrade to Kaizen {required_version} or higher"
        elif ">" in requirement:
            required_version = requirement.split(">")[1].strip()
            return f"Upgrade to Kaizen version higher than {required_version}"
        elif "==" in requirement:
            required_version = requirement.split("==")[1].strip()
            return f"Upgrade to Kaizen {required_version}"

        return "Upgrade to latest Kaizen version"

    def validate_dependencies(self, feature: ExperimentalFeature) -> List[str]:
        """
        Validate and list feature dependencies.

        Args:
            feature: ExperimentalFeature to validate

        Returns:
            List of dependency names

        Example:
            >>> dependencies = checker.validate_dependencies(feature)
            >>> print(f"Dependencies: {', '.join(dependencies)}")
        """
        if not feature.compatibility:
            return []

        return list(feature.compatibility.keys())

    def _check_version_requirement(self, version_str: str, requirement: str) -> bool:
        """
        Check if version satisfies requirement.

        Args:
            version_str: Version string to check (e.g., "0.2.0")
            requirement: Requirement string (e.g., ">=0.1.0")

        Returns:
            True if requirement satisfied
        """
        # Parse requirement (e.g., ">=0.2.0" → operator=">=", version="0.2.0")
        if ">=" in requirement:
            req_version = requirement.split(">=")[1].strip()
            return pkg_version.parse(version_str) >= pkg_version.parse(req_version)
        elif "==" in requirement:
            req_version = requirement.split("==")[1].strip()
            return pkg_version.parse(version_str) == pkg_version.parse(req_version)
        elif ">" in requirement:
            req_version = requirement.split(">")[1].strip()
            return pkg_version.parse(version_str) > pkg_version.parse(req_version)
        elif "<=" in requirement:
            req_version = requirement.split("<=")[1].strip()
            return pkg_version.parse(version_str) <= pkg_version.parse(req_version)
        elif "<" in requirement:
            req_version = requirement.split("<")[1].strip()
            return pkg_version.parse(version_str) < pkg_version.parse(req_version)

        return True  # No recognized operator = compatible


__all__ = ["CompatibilityChecker"]

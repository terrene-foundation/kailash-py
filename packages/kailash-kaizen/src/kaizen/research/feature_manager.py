"""
Feature Manager for Experimental Features.

This module provides the FeatureManager class for auto-discovery,
registration, and lifecycle management of experimental features.

Components:
- FeatureManager: Central manager for experimental feature lifecycle
"""

from typing import Dict, List, Optional

from kaizen.research.experimental import ExperimentalFeature
from kaizen.research.registry import ResearchRegistry
from packaging import version as pkg_version


class FeatureManager:
    """
    Manager for experimental feature lifecycle and discovery.

    Provides auto-discovery of features from ResearchRegistry,
    registration, retrieval, filtering, and status management.

    Attributes:
        registry: ResearchRegistry instance for feature discovery

    Example:
        >>> registry = ResearchRegistry()
        >>> manager = FeatureManager(registry=registry)
        >>> features = manager.discover_features()
        >>> manager.register_feature(feature)
        >>> experimental_features = manager.list_features(status="experimental")
    """

    def __init__(self, registry: ResearchRegistry):
        """
        Initialize FeatureManager with ResearchRegistry.

        Args:
            registry: ResearchRegistry instance for feature discovery
        """
        self.registry = registry
        self._features: Dict[str, ExperimentalFeature] = {}

    def discover_features(self) -> List[ExperimentalFeature]:
        """
        Auto-discover features from ResearchRegistry entries.

        Converts validated registry entries into ExperimentalFeature instances
        with default status "experimental".

        Returns:
            List of discovered ExperimentalFeature instances

        Example:
            >>> manager = FeatureManager(registry)
            >>> features = manager.discover_features()
            >>> print(f"Discovered {len(features)} features")
        """
        discovered_features = []

        # Get all registered papers from registry
        registry_entries = self.registry.list_all()

        for entry in registry_entries:
            # Create ExperimentalFeature from registry entry
            feature_id = f"{entry['paper'].arxiv_id}-v1.0.0"

            # Extract metadata from registry entry
            metadata = entry.get("metadata", {})

            # Build performance metrics from validation results
            performance = {}
            if hasattr(entry["validation"], "reproduced_metrics"):
                performance.update(entry["validation"].reproduced_metrics or {})

            # Create feature
            feature = ExperimentalFeature(
                feature_id=feature_id,
                paper=entry["paper"],
                validation=entry["validation"],
                signature_class=entry["signature_class"],
                version="1.0.0",
                status="experimental",  # Default status for discovered features
                compatibility={},
                performance=performance,
                metadata=metadata,
            )

            discovered_features.append(feature)

        return discovered_features

    def register_feature(self, feature: ExperimentalFeature) -> str:
        """
        Register a new experimental feature.

        Args:
            feature: ExperimentalFeature instance to register

        Returns:
            Feature ID of registered feature

        Raises:
            ValueError: If feature with same ID already registered

        Example:
            >>> feature_id = manager.register_feature(feature)
            >>> print(f"Registered feature: {feature_id}")
        """
        if feature.feature_id in self._features:
            raise ValueError(f"Feature {feature.feature_id} already registered")

        self._features[feature.feature_id] = feature
        return feature.feature_id

    def get_feature(self, feature_id: str) -> Optional[ExperimentalFeature]:
        """
        Retrieve a feature by ID.

        Args:
            feature_id: Unique feature identifier

        Returns:
            ExperimentalFeature if found, None otherwise

        Example:
            >>> feature = manager.get_feature("flash-attention-v1")
            >>> if feature:
            ...     print(f"Found: {feature.feature_id}")
        """
        return self._features.get(feature_id)

    def list_features(
        self, status: Optional[str] = None, compatibility: Optional[str] = None
    ) -> List[ExperimentalFeature]:
        """
        List features with optional filters.

        Args:
            status: Filter by status ("experimental", "beta", "stable", "deprecated")
            compatibility: Filter by compatible framework version

        Returns:
            List of ExperimentalFeature instances matching filters

        Example:
            >>> # List all experimental features
            >>> experimental = manager.list_features(status="experimental")
            >>> # List features compatible with v0.2.0
            >>> compatible = manager.list_features(compatibility="0.2.0")
        """
        features = list(self._features.values())

        # Filter by status
        if status is not None:
            features = [f for f in features if f.status == status]

        # Filter by compatibility
        if compatibility is not None:
            features = [f for f in features if self._is_compatible(f, compatibility)]

        return features

    def update_feature_status(self, feature_id: str, new_status: str) -> None:
        """
        Update feature lifecycle status.

        Args:
            feature_id: ID of feature to update
            new_status: New status to transition to

        Raises:
            ValueError: If feature not found or invalid transition

        Example:
            >>> manager.update_feature_status("flash-attention-v1", "beta")
            >>> manager.update_feature_status("flash-attention-v1", "stable")
        """
        feature = self.get_feature(feature_id)

        if feature is None:
            raise ValueError(f"Feature {feature_id} not found")

        # Use ExperimentalFeature's validation logic
        feature.update_status(new_status)

    def _is_compatible(self, feature: ExperimentalFeature, version_str: str) -> bool:
        """
        Check if feature is compatible with given framework version.

        Args:
            feature: ExperimentalFeature to check
            version_str: Framework version string (e.g., "0.2.0")

        Returns:
            True if compatible, False otherwise
        """
        if not feature.compatibility:
            return True  # No requirements = compatible

        # Check kaizen framework version requirement
        requirement = feature.compatibility.get("kaizen", ">=0.0.0")

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

        return True


__all__ = ["FeatureManager"]

"""
Documentation Generator for Experimental Features.

This module provides the DocumentationGenerator class for automatically
generating documentation, usage examples, API references, and changelogs.

Components:
- DocumentationGenerator: Auto-generate feature documentation
"""

from typing import List

from kaizen.research.experimental import ExperimentalFeature


class DocumentationGenerator:
    """
    Generate documentation for experimental features.

    Automatically creates markdown documentation, usage examples,
    API references, and changelogs from feature metadata.

    Example:
        >>> generator = DocumentationGenerator()
        >>> docs = generator.generate_feature_docs(feature)
        >>> print(docs)
    """

    def __init__(self):
        """Initialize DocumentationGenerator."""
        pass

    def generate_feature_docs(self, feature: ExperimentalFeature) -> str:
        """
        Generate markdown documentation for feature.

        Args:
            feature: ExperimentalFeature to document

        Returns:
            Markdown-formatted documentation string

        Example:
            >>> docs = generator.generate_feature_docs(feature)
            >>> with open("feature.md", "w") as f:
            ...     f.write(docs)
        """
        # Use ExperimentalFeature's built-in get_documentation method
        # and enhance with additional sections
        base_docs = feature.get_documentation()

        # Add usage section
        doc_parts = [base_docs]

        # Add installation/setup if compatibility specified
        if feature.compatibility:
            doc_parts.append("\n## Installation\n")
            doc_parts.append("```bash\n")
            doc_parts.append("pip install kaizen\n")
            doc_parts.append("```\n")

        # Add status badge
        status_badge = self._get_status_badge(feature.status)
        doc_parts.insert(0, f"{status_badge}\n\n")

        return "".join(doc_parts)

    def generate_usage_example(self, feature: ExperimentalFeature) -> str:
        """
        Generate code usage example.

        Args:
            feature: ExperimentalFeature to demonstrate

        Returns:
            Python code example string

        Example:
            >>> example = generator.generate_usage_example(feature)
            >>> print(example)
        """
        code_parts = []

        # Imports
        code_parts.append(
            "from kaizen.research import FeatureManager, ResearchRegistry\n"
        )
        code_parts.append("\n")

        # Setup
        code_parts.append("# Get feature from manager\n")
        code_parts.append("registry = ResearchRegistry()\n")
        code_parts.append("manager = FeatureManager(registry)\n")
        code_parts.append(f'feature = manager.get_feature("{feature.feature_id}")\n')
        code_parts.append("\n")

        # Enable feature
        code_parts.append("# Enable experimental feature\n")
        code_parts.append("feature.enable()\n")
        code_parts.append("\n")

        # Usage
        code_parts.append("# Use feature\n")
        code_parts.append("result = feature.execute(\n")
        code_parts.append("    # Add your parameters here\n")
        code_parts.append(")\n")

        return "".join(code_parts)

    def generate_api_reference(self, feature: ExperimentalFeature) -> str:
        """
        Generate API reference documentation.

        Args:
            feature: ExperimentalFeature to document

        Returns:
            API reference string

        Example:
            >>> api_ref = generator.generate_api_reference(feature)
            >>> print(api_ref)
        """
        ref_parts = []

        # API Header
        ref_parts.append(f"# {feature.feature_id} API Reference\n\n")

        # Methods
        ref_parts.append("## Methods\n\n")

        # enable()
        ref_parts.append("### `enable()`\n")
        ref_parts.append("Enable the experimental feature for use.\n\n")

        # disable()
        ref_parts.append("### `disable()`\n")
        ref_parts.append("Disable the experimental feature.\n\n")

        # execute()
        ref_parts.append("### `execute(**kwargs)`\n")
        ref_parts.append("Execute the feature with provided parameters.\n\n")
        ref_parts.append("**Returns**: Execution result\n\n")

        # is_enabled()
        ref_parts.append("### `is_enabled()`\n")
        ref_parts.append("Check if feature is currently enabled.\n\n")
        ref_parts.append("**Returns**: `bool`\n\n")

        # Properties
        ref_parts.append("## Properties\n\n")
        ref_parts.append(f"- **feature_id**: `{feature.feature_id}`\n")
        ref_parts.append(f"- **version**: `{feature.version}`\n")
        ref_parts.append(f"- **status**: `{feature.status}`\n")

        return "".join(ref_parts)

    def generate_changelog(self, features: List[ExperimentalFeature]) -> str:
        """
        Generate changelog from features.

        Args:
            features: List of ExperimentalFeature instances

        Returns:
            Changelog string

        Example:
            >>> changelog = generator.generate_changelog(features)
            >>> print(changelog)
        """
        changelog_parts = []

        # Header
        changelog_parts.append("# Experimental Features Changelog\n\n")

        # Group by version
        versions = {}
        for feature in features:
            version = feature.version
            if version not in versions:
                versions[version] = []
            versions[version].append(feature)

        # Generate entries by version
        for version in sorted(versions.keys(), reverse=True):
            changelog_parts.append(f"## Version {version}\n\n")

            for feature in versions[version]:
                changelog_parts.append(f"### {feature.feature_id}\n")
                changelog_parts.append(f"- **Status**: {feature.status}\n")
                changelog_parts.append(f"- **Paper**: {feature.paper.title}\n")

                if feature.performance:
                    changelog_parts.append(
                        f"- **Performance**: {feature.performance}\n"
                    )

                changelog_parts.append("\n")

        return "".join(changelog_parts)

    def _get_status_badge(self, status: str) -> str:
        """
        Get status badge for documentation.

        Args:
            status: Feature status string

        Returns:
            Markdown badge string
        """
        badges = {
            "experimental": "![Status: Experimental](https://img.shields.io/badge/status-experimental-yellow)",
            "beta": "![Status: Beta](https://img.shields.io/badge/status-beta-blue)",
            "stable": "![Status: Stable](https://img.shields.io/badge/status-stable-green)",
            "deprecated": "![Status: Deprecated](https://img.shields.io/badge/status-deprecated-red)",
        }

        return badges.get(status, "")


__all__ = ["DocumentationGenerator"]

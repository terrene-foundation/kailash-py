"""
Research Integration Pipeline - Complete Example

Demonstrates the full research-to-production pipeline:
1. Integrate research paper from arXiv
2. Validate reproducibility
3. Create experimental feature
4. Manage feature lifecycle
5. Generate documentation
6. Deploy to production

Usage:
    python workflow.py --arxiv-id 2205.14135
    python workflow.py --list-features
    python workflow.py --promote-feature <feature-id>
"""

from dataclasses import dataclass
from typing import Optional

from kaizen.research import (
    CompatibilityChecker,
    DocumentationGenerator,
    FeatureManager,
    IntegrationWorkflow,
    ResearchAdapter,
    ResearchParser,
    ResearchRegistry,
    ResearchValidator,
)


@dataclass
class ResearchIntegrationConfig:
    """Configuration for research integration workflow."""

    # Pipeline components
    enable_validation: bool = True
    enable_documentation: bool = True
    auto_enable_features: bool = False

    # Quality thresholds
    min_reproducibility_score: float = 0.90
    min_test_pass_rate: float = 0.95

    # Performance targets
    max_parse_time_seconds: int = 30
    max_validation_time_minutes: int = 5

    # Framework compatibility
    framework_version: str = "0.2.0"


class ResearchIntegrationPipeline:
    """Complete research integration pipeline."""

    def __init__(self, config: ResearchIntegrationConfig):
        self.config = config

        # Initialize Phase 1 components
        self.parser = ResearchParser()
        self.validator = ResearchValidator()
        self.adapter = ResearchAdapter()
        self.registry = ResearchRegistry()

        # Initialize Phase 2 components
        self.feature_manager = FeatureManager(self.registry)
        self.workflow = IntegrationWorkflow(
            self.parser,
            self.validator,
            self.adapter,
            self.registry,
            self.feature_manager,
        )
        self.compatibility_checker = CompatibilityChecker()
        self.doc_generator = DocumentationGenerator()

    def integrate_from_arxiv(self, arxiv_id: str, auto_enable: bool = False) -> dict:
        """
        Integrate a research paper from arXiv.

        Args:
            arxiv_id: arXiv paper ID (e.g., "2205.14135")
            auto_enable: Automatically enable the feature after integration

        Returns:
            dict: Integration result with feature information
        """
        print(f"\n🔬 Integrating research paper: {arxiv_id}")
        print("=" * 60)

        # Step 1: Integrate from arXiv
        print("\n📥 Step 1: Parsing paper from arXiv...")
        feature = self.workflow.integrate_from_arxiv(
            arxiv_id, auto_enable=auto_enable or self.config.auto_enable_features
        )

        print(f"✅ Paper integrated: {feature.paper.title}")
        print(f"   Authors: {', '.join(feature.paper.authors[:3])}...")
        print(
            f"   Reproducibility Score: {feature.validation.reproducibility_score:.2%}"
        )

        # Step 2: Check compatibility
        print("\n🔍 Step 2: Checking compatibility...")
        is_compatible = self.compatibility_checker.check_compatibility(
            feature, self.config.framework_version
        )

        if is_compatible:
            print(f"✅ Compatible with Kaizen {self.config.framework_version}")
        else:
            print("⚠️  Incompatible with current version")
            suggestion = self.compatibility_checker.suggest_upgrade(
                feature, self.config.framework_version
            )
            print(f"   Suggestion: {suggestion}")

        # Step 3: Generate documentation
        if self.config.enable_documentation:
            print("\n📝 Step 3: Generating documentation...")
            docs = self.doc_generator.generate_feature_docs(feature)
            usage_example = self.doc_generator.generate_usage_example(feature)

            print(f"✅ Documentation generated ({len(docs)} chars)")
            print(f"✅ Usage example generated ({len(usage_example)} chars)")

        # Step 4: Return result
        result = {
            "feature_id": feature.feature_id,
            "paper_title": feature.paper.title,
            "status": feature.status,
            "is_enabled": feature.is_enabled(),
            "is_compatible": is_compatible,
            "reproducibility_score": feature.validation.reproducibility_score,
            "performance_metrics": feature.performance,
        }

        print("\n✨ Integration complete!")
        print(f"   Feature ID: {result['feature_id']}")
        print(f"   Status: {result['status']}")
        print(f"   Enabled: {result['is_enabled']}")

        return result

    def list_features(self, status_filter: Optional[str] = None) -> list:
        """
        List all integrated features.

        Args:
            status_filter: Optional status filter ("experimental", "beta", "stable")

        Returns:
            list: List of feature information dictionaries
        """
        print("\n📋 Available Research Features")
        print("=" * 60)

        if status_filter:
            features = self.feature_manager.list_features(status=status_filter)
            print(f"\nFiltering by status: {status_filter}")
        else:
            features = self.feature_manager.list_features()

        if not features:
            print("\n⚠️  No features found")
            return []

        results = []
        for i, feature in enumerate(features, 1):
            print(f"\n{i}. {feature.paper.title[:60]}...")
            print(f"   ID: {feature.feature_id}")
            print(f"   Status: {feature.status}")
            print(f"   Enabled: {'✅' if feature.is_enabled() else '❌'}")
            print(f"   Reproducibility: {feature.validation.reproducibility_score:.2%}")

            results.append(
                {
                    "feature_id": feature.feature_id,
                    "title": feature.paper.title,
                    "status": feature.status,
                    "is_enabled": feature.is_enabled(),
                }
            )

        return results

    def promote_feature(self, feature_id: str, new_status: str) -> dict:
        """
        Promote feature through lifecycle (experimental → beta → stable).

        Args:
            feature_id: Feature identifier
            new_status: Target status ("beta", "stable", "deprecated")

        Returns:
            dict: Updated feature information
        """
        print(f"\n⬆️  Promoting feature: {feature_id}")
        print("=" * 60)

        # Get current feature
        feature = self.feature_manager.get_feature(feature_id)
        if not feature:
            raise ValueError(f"Feature not found: {feature_id}")

        print(f"\nCurrent status: {feature.status}")
        print(f"Target status: {new_status}")

        # Validate transition
        valid_transitions = {
            "experimental": ["beta", "deprecated"],
            "beta": ["stable", "deprecated"],
            "stable": ["deprecated"],
        }

        if new_status not in valid_transitions.get(feature.status, []):
            raise ValueError(
                f"Invalid transition: {feature.status} → {new_status}\n"
                f"Valid transitions from {feature.status}: "
                f"{', '.join(valid_transitions.get(feature.status, []))}"
            )

        # Update status
        self.feature_manager.update_feature_status(feature_id, new_status)
        updated_feature = self.feature_manager.get_feature(feature_id)

        print(f"\n✅ Feature promoted to: {updated_feature.status}")

        # Regenerate documentation
        if self.config.enable_documentation:
            print("\n📝 Regenerating documentation...")
            docs = self.doc_generator.generate_feature_docs(updated_feature)
            print(f"✅ Documentation updated ({len(docs)} chars)")

        return {
            "feature_id": feature_id,
            "old_status": feature.status,
            "new_status": updated_feature.status,
        }

    def generate_changelog(self) -> str:
        """Generate changelog for all features."""
        print("\n📋 Generating Changelog")
        print("=" * 60)

        all_features = self.feature_manager.list_features()
        changelog = self.doc_generator.generate_changelog(all_features)

        print(f"\n✅ Changelog generated ({len(changelog)} chars)")
        print("\n" + changelog[:500] + "..." if len(changelog) > 500 else changelog)

        return changelog

    def get_compatible_features(self) -> list:
        """Get features compatible with current framework version."""
        print("\n🔍 Compatible Features")
        print("=" * 60)

        all_features = self.feature_manager.list_features()
        compatible = self.compatibility_checker.get_compatible_features(
            all_features, self.config.framework_version
        )

        print(f"\nFramework version: {self.config.framework_version}")
        print(f"Compatible features: {len(compatible)}/{len(all_features)}")

        results = []
        for feature in compatible:
            print(f"\n✅ {feature.paper.title[:60]}...")
            print(f"   ID: {feature.feature_id}")
            print(f"   Requirements: {feature.compatibility.get('kaizen', 'N/A')}")

            results.append(
                {
                    "feature_id": feature.feature_id,
                    "title": feature.paper.title,
                    "requirements": feature.compatibility,
                }
            )

        return results


def main():
    """Example usage of research integration pipeline."""
    import argparse

    parser = argparse.ArgumentParser(description="Research Integration Pipeline")
    parser.add_argument(
        "--arxiv-id", help="arXiv paper ID to integrate (e.g., 2205.14135)"
    )
    parser.add_argument(
        "--list-features", action="store_true", help="List all integrated features"
    )
    parser.add_argument(
        "--promote-feature",
        help="Promote feature to new status (format: feature-id:status)",
    )
    parser.add_argument(
        "--compatible", action="store_true", help="List compatible features only"
    )
    parser.add_argument("--changelog", action="store_true", help="Generate changelog")
    parser.add_argument(
        "--auto-enable",
        action="store_true",
        help="Auto-enable features after integration",
    )

    args = parser.parse_args()

    # Initialize pipeline
    config = ResearchIntegrationConfig(auto_enable_features=args.auto_enable)
    pipeline = ResearchIntegrationPipeline(config)

    # Execute requested action
    if args.arxiv_id:
        pipeline.integrate_from_arxiv(args.arxiv_id, args.auto_enable)

    elif args.list_features:
        pipeline.list_features()

    elif args.promote_feature:
        feature_id, status = args.promote_feature.split(":")
        pipeline.promote_feature(feature_id, status)

    elif args.compatible:
        pipeline.get_compatible_features()

    elif args.changelog:
        pipeline.generate_changelog()

    else:
        parser.print_help()


if __name__ == "__main__":
    # Example: Direct usage
    config = ResearchIntegrationConfig()
    pipeline = ResearchIntegrationPipeline(config)

    print("🚀 Research Integration Pipeline Demo")
    print("=" * 60)

    # Note: This is a demonstration structure
    # In real usage, you would integrate actual papers from arXiv
    print("\nTo integrate a research paper:")
    print("  python workflow.py --arxiv-id 2205.14135")
    print("\nTo list all features:")
    print("  python workflow.py --list-features")
    print("\nTo promote a feature:")
    print("  python workflow.py --promote-feature feature-id:beta")

    # For testing, show the structure
    print("\n✅ Pipeline initialized successfully!")
    print(f"   Min reproducibility score: {config.min_reproducibility_score:.0%}")
    print(f"   Framework version: {config.framework_version}")

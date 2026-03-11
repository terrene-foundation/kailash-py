"""
Unit tests for FeatureManager - WRITE TESTS FIRST (TDD RED Phase)

Test Coverage:
1. Feature manager initialization
2. Auto-discovery from ResearchRegistry
3. Feature registration and retrieval
4. Feature filtering and search
5. Feature lifecycle management
6. Status updates and transitions

CRITICAL: These tests MUST be written BEFORE implementation!
"""

from unittest.mock import Mock

import pytest


class TestFeatureManager:
    """Test suite for FeatureManager component."""

    def test_feature_manager_initialization(self):
        """Test FeatureManager initializes with ResearchRegistry."""
        from kaizen.research import FeatureManager, ResearchRegistry

        registry = ResearchRegistry()
        manager = FeatureManager(registry=registry)

        assert manager is not None
        assert manager.registry is registry

    def test_auto_discover_features_from_registry(self, flash_attention_paper):
        """Test auto-discovery of features from registry entries."""
        from kaizen.research import FeatureManager, ResearchRegistry, ValidationResult

        # Setup: Registry with validated papers
        registry = ResearchRegistry()
        validation = ValidationResult(
            validation_passed=True,
            reproducibility_score=0.96,
            reproduced_metrics={"speedup": 2.7},
            quality_score={"overall": 0.95},
            issues=[],
        )

        registry.register_paper(
            paper=flash_attention_paper, validation=validation, signature_class=Mock()
        )

        # Auto-discover should create ExperimentalFeature from registry entries
        manager = FeatureManager(registry=registry)
        features = manager.discover_features()

        assert len(features) > 0
        assert features[0].paper.arxiv_id == flash_attention_paper.arxiv_id
        assert features[0].status == "experimental"  # Default status

    def test_register_feature(self, flash_attention_paper):
        """Test registering a new experimental feature."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureManager,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry=registry)

        validation = ValidationResult(
            validation_passed=True, reproducibility_score=0.96
        )

        feature = ExperimentalFeature(
            feature_id="flash-attention-v1",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        # Register feature
        feature_id = manager.register_feature(feature)

        assert feature_id == "flash-attention-v1"
        # Should be retrievable
        retrieved = manager.get_feature("flash-attention-v1")
        assert retrieved is not None
        assert retrieved.feature_id == "flash-attention-v1"

    def test_get_feature(self, flash_attention_paper):
        """Test retrieving a feature by ID."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureManager,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry=registry)

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        manager.register_feature(feature)

        # Get existing feature
        retrieved = manager.get_feature("test-feature")
        assert retrieved is not None
        assert retrieved.feature_id == "test-feature"

        # Get non-existent feature
        missing = manager.get_feature("nonexistent")
        assert missing is None

    def test_list_features_all(self, flash_attention_paper, maml_paper):
        """Test listing all features without filters."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureManager,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry=registry)

        # Register multiple features
        for i, paper in enumerate([flash_attention_paper, maml_paper]):
            feature = ExperimentalFeature(
                feature_id=f"feature-{i}",
                paper=paper,
                validation=ValidationResult(
                    validation_passed=True, reproducibility_score=0.95
                ),
                signature_class=Mock(),
                version="1.0.0",
                status="experimental",
                compatibility={},
                performance={},
                metadata={},
            )
            manager.register_feature(feature)

        # List all features
        all_features = manager.list_features()
        assert len(all_features) == 2

    def test_list_features_filter_by_status(self, flash_attention_paper, maml_paper):
        """Test filtering features by status."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureManager,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry=registry)

        # Register features with different statuses
        feature1 = ExperimentalFeature(
            feature_id="experimental-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        feature2 = ExperimentalFeature(
            feature_id="beta-feature",
            paper=maml_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="beta",
            compatibility={},
            performance={},
            metadata={},
        )

        manager.register_feature(feature1)
        manager.register_feature(feature2)

        # Filter by experimental status
        experimental_features = manager.list_features(status="experimental")
        assert len(experimental_features) == 1
        assert experimental_features[0].status == "experimental"

        # Filter by beta status
        beta_features = manager.list_features(status="beta")
        assert len(beta_features) == 1
        assert beta_features[0].status == "beta"

    def test_list_features_filter_by_compatibility(self, flash_attention_paper):
        """Test filtering features by compatibility requirements."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureManager,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry=registry)

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.2.0"},
            performance={},
            metadata={},
        )

        manager.register_feature(feature)

        # Filter by compatible version
        compatible_features = manager.list_features(compatibility="0.2.0")
        assert len(compatible_features) == 1

        # Filter by incompatible version
        incompatible_features = manager.list_features(compatibility="0.1.0")
        assert len(incompatible_features) == 0

    def test_update_feature_status(self, flash_attention_paper):
        """Test updating feature status through manager."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureManager,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry=registry)

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        manager.register_feature(feature)

        # Update status
        manager.update_feature_status("test-feature", "beta")

        # Verify status changed
        retrieved = manager.get_feature("test-feature")
        assert retrieved.status == "beta"

    def test_feature_lifecycle_transitions(self, flash_attention_paper):
        """Test complete lifecycle: experimental → beta → stable."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureManager,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry=registry)

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        manager.register_feature(feature)

        # experimental → beta
        manager.update_feature_status("test-feature", "beta")
        assert manager.get_feature("test-feature").status == "beta"

        # beta → stable
        manager.update_feature_status("test-feature", "stable")
        assert manager.get_feature("test-feature").status == "stable"

    def test_update_nonexistent_feature_raises_error(self):
        """Test updating non-existent feature raises error."""
        from kaizen.research import FeatureManager, ResearchRegistry

        registry = ResearchRegistry()
        manager = FeatureManager(registry=registry)

        with pytest.raises(ValueError, match="Feature .* not found"):
            manager.update_feature_status("nonexistent", "beta")

    def test_discover_features_with_metadata(self, flash_attention_paper):
        """Test discovered features include metadata from registry."""
        from kaizen.research import FeatureManager, ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        # Register with metadata
        validation = ValidationResult(
            validation_passed=True,
            reproducibility_score=0.96,
            reproduced_metrics={"speedup": 2.7},
            quality_score={"overall": 0.95},
            issues=[],
        )

        registry.register_paper(
            paper=flash_attention_paper,
            validation=validation,
            signature_class=Mock(),
            metadata={"tags": ["attention", "optimization"]},
        )

        manager = FeatureManager(registry=registry)
        features = manager.discover_features()

        assert len(features) > 0
        # Metadata should be included
        assert "tags" in features[0].metadata

    def test_register_duplicate_feature_raises_error(self, flash_attention_paper):
        """Test registering duplicate feature ID raises error."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureManager,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry=registry)

        feature = ExperimentalFeature(
            feature_id="duplicate-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        # Register once (should succeed)
        manager.register_feature(feature)

        # Register again (should fail)
        with pytest.raises(ValueError, match="Feature .* already registered"):
            manager.register_feature(feature)

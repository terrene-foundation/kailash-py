"""
Unit tests for CompatibilityChecker - WRITE TESTS FIRST (TDD RED Phase)

Test Coverage:
1. Compatibility checker initialization
2. Check feature compatibility with framework versions
3. Get compatible features for a version
4. Suggest framework upgrades
5. Validate feature dependencies

CRITICAL: These tests MUST be written BEFORE implementation!
"""

from unittest.mock import Mock


class TestCompatibilityChecker:
    """Test suite for CompatibilityChecker component."""

    def test_compatibility_checker_initialization(self):
        """Test CompatibilityChecker initializes correctly."""
        from kaizen.research import CompatibilityChecker

        checker = CompatibilityChecker()

        assert checker is not None

    def test_check_compatibility_compatible(self, flash_attention_paper):
        """Test checking compatible feature."""
        from kaizen.research import (
            CompatibilityChecker,
            ExperimentalFeature,
            ValidationResult,
        )

        checker = CompatibilityChecker()

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.1.0"},
            performance={},
            metadata={},
        )

        # Framework version 0.2.0 >= 0.1.0 (compatible)
        is_compatible = checker.check_compatibility(feature, "0.2.0")
        assert is_compatible is True

    def test_check_compatibility_incompatible(self, flash_attention_paper):
        """Test checking incompatible feature."""
        from kaizen.research import (
            CompatibilityChecker,
            ExperimentalFeature,
            ValidationResult,
        )

        checker = CompatibilityChecker()

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.5.0"},
            performance={},
            metadata={},
        )

        # Framework version 0.2.0 < 0.5.0 (incompatible)
        is_compatible = checker.check_compatibility(feature, "0.2.0")
        assert is_compatible is False

    def test_check_compatibility_no_requirements(self, flash_attention_paper):
        """Test feature with no compatibility requirements is always compatible."""
        from kaizen.research import (
            CompatibilityChecker,
            ExperimentalFeature,
            ValidationResult,
        )

        checker = CompatibilityChecker()

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},  # No requirements
            performance={},
            metadata={},
        )

        # Should be compatible with any version
        is_compatible = checker.check_compatibility(feature, "0.1.0")
        assert is_compatible is True

    def test_get_compatible_features(self, flash_attention_paper, maml_paper):
        """Test getting all compatible features for a framework version."""
        from kaizen.research import (
            CompatibilityChecker,
            ExperimentalFeature,
            ValidationResult,
        )

        checker = CompatibilityChecker()

        # Feature requiring >=0.1.0
        feature1 = ExperimentalFeature(
            feature_id="feature-1",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.1.0"},
            performance={},
            metadata={},
        )

        # Feature requiring >=0.5.0
        feature2 = ExperimentalFeature(
            feature_id="feature-2",
            paper=maml_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.5.0"},
            performance={},
            metadata={},
        )

        features = [feature1, feature2]

        # Framework 0.2.0 should be compatible with feature1 only
        compatible = checker.get_compatible_features(features, "0.2.0")
        assert len(compatible) == 1
        assert compatible[0].feature_id == "feature-1"

        # Framework 0.5.0 should be compatible with both
        compatible = checker.get_compatible_features(features, "0.5.0")
        assert len(compatible) == 2

    def test_suggest_upgrade(self, flash_attention_paper):
        """Test suggesting framework upgrade for incompatible feature."""
        from kaizen.research import (
            CompatibilityChecker,
            ExperimentalFeature,
            ValidationResult,
        )

        checker = CompatibilityChecker()

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.5.0"},
            performance={},
            metadata={},
        )

        # Should suggest upgrade to meet requirement
        suggestion = checker.suggest_upgrade(feature, current_version="0.2.0")
        assert suggestion is not None
        assert "0.5.0" in suggestion

    def test_suggest_upgrade_no_suggestion_when_compatible(self, flash_attention_paper):
        """Test no upgrade suggestion when already compatible."""
        from kaizen.research import (
            CompatibilityChecker,
            ExperimentalFeature,
            ValidationResult,
        )

        checker = CompatibilityChecker()

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.1.0"},
            performance={},
            metadata={},
        )

        # Already compatible, no suggestion needed
        suggestion = checker.suggest_upgrade(feature, current_version="0.5.0")
        assert suggestion is None

    def test_validate_dependencies(self, flash_attention_paper):
        """Test validating feature dependencies."""
        from kaizen.research import (
            CompatibilityChecker,
            ExperimentalFeature,
            ValidationResult,
        )

        checker = CompatibilityChecker()

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.2.0", "python": ">=3.8", "torch": ">=2.0.0"},
            performance={},
            metadata={},
        )

        # Get list of dependencies
        dependencies = checker.validate_dependencies(feature)
        assert len(dependencies) == 3
        assert "kaizen" in dependencies
        assert "python" in dependencies
        assert "torch" in dependencies

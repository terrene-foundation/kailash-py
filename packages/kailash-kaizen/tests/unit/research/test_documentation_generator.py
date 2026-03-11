"""
Unit tests for DocumentationGenerator - WRITE TESTS FIRST (TDD RED Phase)

Test Coverage:
1. Generator initialization
2. Generate feature documentation (markdown)
3. Generate usage examples
4. Generate API reference
5. Generate changelog from features
6. Documentation templates and formatting

CRITICAL: These tests MUST be written BEFORE implementation!
"""

from unittest.mock import Mock


class TestDocumentationGenerator:
    """Test suite for DocumentationGenerator component."""

    def test_documentation_generator_initialization(self):
        """Test DocumentationGenerator initializes correctly."""
        from kaizen.research import DocumentationGenerator

        generator = DocumentationGenerator()

        assert generator is not None

    def test_generate_feature_docs(self, flash_attention_paper):
        """Test generating markdown documentation for feature."""
        from kaizen.research import (
            DocumentationGenerator,
            ExperimentalFeature,
            ValidationResult,
        )

        generator = DocumentationGenerator()

        feature = ExperimentalFeature(
            feature_id="flash-attention-v1",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True,
                reproducibility_score=0.96,
                reproduced_metrics={"speedup": 2.7},
                quality_score={"overall": 0.95},
                issues=[],
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.1.0"},
            performance={"speedup": 2.7, "memory_reduction": 0.3},
            metadata={"tags": ["attention", "optimization"]},
        )

        # Generate docs
        docs = generator.generate_feature_docs(feature)

        # Should be markdown format
        assert docs is not None
        assert isinstance(docs, str)
        assert len(docs) > 0
        # Should include key information
        assert "flash-attention-v1" in docs or "Flash" in docs
        assert "1.0.0" in docs
        assert "experimental" in docs.lower()

    def test_generate_usage_example(self, flash_attention_paper):
        """Test generating code usage example."""
        from kaizen.research import (
            DocumentationGenerator,
            ExperimentalFeature,
            ValidationResult,
        )

        generator = DocumentationGenerator()

        feature = ExperimentalFeature(
            feature_id="flash-attention-v1",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.96
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        # Generate usage example
        example = generator.generate_usage_example(feature)

        # Should be Python code
        assert example is not None
        assert isinstance(example, str)
        assert len(example) > 0
        # Should include code patterns
        assert "import" in example or "from" in example or "feature" in example.lower()

    def test_generate_api_reference(self, flash_attention_paper):
        """Test generating API reference documentation."""
        from kaizen.research import (
            DocumentationGenerator,
            ExperimentalFeature,
            ValidationResult,
        )

        generator = DocumentationGenerator()

        feature = ExperimentalFeature(
            feature_id="flash-attention-v1",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.96
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        # Generate API reference
        api_ref = generator.generate_api_reference(feature)

        # Should include API information
        assert api_ref is not None
        assert isinstance(api_ref, str)
        assert len(api_ref) > 0

    def test_generate_changelog(self, flash_attention_paper, maml_paper):
        """Test generating changelog from features."""
        from kaizen.research import (
            DocumentationGenerator,
            ExperimentalFeature,
            ValidationResult,
        )

        generator = DocumentationGenerator()

        feature1 = ExperimentalFeature(
            feature_id="feature-1",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.96
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        feature2 = ExperimentalFeature(
            feature_id="feature-2",
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

        features = [feature1, feature2]

        # Generate changelog
        changelog = generator.generate_changelog(features)

        # Should include both features
        assert changelog is not None
        assert isinstance(changelog, str)
        assert len(changelog) > 0
        # Should list features by version or status
        assert "feature-1" in changelog or "feature-2" in changelog

    def test_documentation_includes_performance_metrics(self, flash_attention_paper):
        """Test documentation includes performance metrics."""
        from kaizen.research import (
            DocumentationGenerator,
            ExperimentalFeature,
            ValidationResult,
        )

        generator = DocumentationGenerator()

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.96
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={"speedup": 2.7, "accuracy": 0.95},
            metadata={},
        )

        docs = generator.generate_feature_docs(feature)

        # Should include performance metrics
        assert "speedup" in docs.lower() or "2.7" in docs
        assert "accuracy" in docs.lower() or "0.95" in docs

    def test_documentation_includes_compatibility_info(self, flash_attention_paper):
        """Test documentation includes compatibility information."""
        from kaizen.research import (
            DocumentationGenerator,
            ExperimentalFeature,
            ValidationResult,
        )

        generator = DocumentationGenerator()

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.96
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.2.0", "python": ">=3.8"},
            performance={},
            metadata={},
        )

        docs = generator.generate_feature_docs(feature)

        # Should include compatibility requirements
        assert "0.2.0" in docs or "3.8" in docs
        assert "kaizen" in docs.lower() or "python" in docs.lower()

    def test_usage_example_includes_enable_step(self, flash_attention_paper):
        """Test usage example includes feature enable step."""
        from kaizen.research import (
            DocumentationGenerator,
            ExperimentalFeature,
            ValidationResult,
        )

        generator = DocumentationGenerator()

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.96
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        example = generator.generate_usage_example(feature)

        # Should include enable() call
        assert "enable" in example.lower()

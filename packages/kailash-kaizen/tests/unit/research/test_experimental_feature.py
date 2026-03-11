"""
Unit tests for ExperimentalFeature - WRITE TESTS FIRST (TDD RED Phase)

Test Coverage:
1. Feature creation and metadata
2. Feature enable/disable functionality
3. Feature execution with signature
4. Feature status lifecycle (experimental → beta → stable)
5. Feature versioning and compatibility
6. Performance benchmarking integration

CRITICAL: These tests MUST be written BEFORE implementation!
"""

from unittest.mock import Mock, patch

import pytest


class TestExperimentalFeature:
    """Test suite for ExperimentalFeature component."""

    def test_experimental_feature_creation(self, flash_attention_paper):
        """Test creating an experimental feature from research."""
        from kaizen.research import ExperimentalFeature, ValidationResult

        validation = ValidationResult(
            validation_passed=True,
            reproducibility_score=0.96,
            reproduced_metrics={"speedup": 2.7},
            quality_score={"overall": 0.95},
            issues=[],
        )

        signature_class = Mock()

        feature = ExperimentalFeature(
            feature_id="flash-attention-v1",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=signature_class,
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.1.0"},
            performance={"speedup": 2.7, "memory_reduction": 0.3},
            metadata={"tags": ["attention", "optimization"]},
        )

        assert feature.feature_id == "flash-attention-v1"
        assert feature.paper.arxiv_id == flash_attention_paper.arxiv_id
        assert feature.status == "experimental"
        assert feature.version == "1.0.0"

    def test_feature_enable_disable(self, flash_attention_paper):
        """Test feature can be enabled and disabled."""
        from kaizen.research import ExperimentalFeature, ValidationResult

        validation = ValidationResult(
            validation_passed=True, reproducibility_score=0.96
        )
        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        # Should start disabled
        assert not feature.is_enabled()

        # Enable feature
        feature.enable()
        assert feature.is_enabled()

        # Disable feature
        feature.disable()
        assert not feature.is_enabled()

    def test_feature_execution_when_enabled(self, flash_attention_paper):
        """Test feature can execute when enabled."""
        from kaizen.research import ExperimentalFeature, ValidationResult

        validation = ValidationResult(
            validation_passed=True, reproducibility_score=0.96
        )

        # Mock signature execution
        mock_signature_instance = Mock()
        mock_signature_instance.execute.return_value = {"result": "success"}
        mock_signature_class = Mock(return_value=mock_signature_instance)

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=mock_signature_class,
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        feature.enable()
        result = feature.execute(query="test", key="test", value="test")

        assert result == {"result": "success"}
        mock_signature_instance.execute.assert_called_once()

    def test_feature_execution_when_disabled_raises_error(self, flash_attention_paper):
        """Test feature execution fails when disabled."""
        from kaizen.research import ExperimentalFeature, ValidationResult

        validation = ValidationResult(
            validation_passed=True, reproducibility_score=0.96
        )
        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        # Feature starts disabled
        with pytest.raises(RuntimeError, match="Feature .* is not enabled"):
            feature.execute(query="test")

    def test_feature_status_lifecycle(self, flash_attention_paper):
        """Test feature status transitions (experimental → beta → stable)."""
        from kaizen.research import ExperimentalFeature, ValidationResult

        validation = ValidationResult(
            validation_passed=True, reproducibility_score=0.96
        )
        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        assert feature.status == "experimental"

        # Transition to beta
        feature.update_status("beta")
        assert feature.status == "beta"

        # Transition to stable
        feature.update_status("stable")
        assert feature.status == "stable"

    def test_feature_invalid_status_transition(self, flash_attention_paper):
        """Test invalid status transitions are rejected."""
        from kaizen.research import ExperimentalFeature, ValidationResult

        validation = ValidationResult(
            validation_passed=True, reproducibility_score=0.96
        )
        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        # Can't go directly from experimental to stable
        with pytest.raises(ValueError, match="Invalid status transition"):
            feature.update_status("stable")

    def test_feature_metadata(self, flash_attention_paper):
        """Test feature metadata storage and retrieval."""
        from kaizen.research import ExperimentalFeature, ValidationResult

        validation = ValidationResult(
            validation_passed=True, reproducibility_score=0.96
        )
        metadata = {
            "tags": ["attention", "optimization"],
            "author": "Tri Dao",
            "description": "Fast attention algorithm",
        }

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata=metadata,
        )

        assert feature.metadata["tags"] == ["attention", "optimization"]
        assert feature.metadata["author"] == "Tri Dao"

    def test_feature_versioning(self, flash_attention_paper):
        """Test feature version management."""
        from kaizen.research import ExperimentalFeature, ValidationResult

        validation = ValidationResult(
            validation_passed=True, reproducibility_score=0.96
        )

        # Create v1.0.0
        feature_v1 = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        # Create v2.0.0
        feature_v2 = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=Mock(),
            version="2.0.0",
            status="beta",
            compatibility={},
            performance={},
            metadata={},
        )

        assert feature_v1.version == "1.0.0"
        assert feature_v2.version == "2.0.0"
        assert feature_v1.feature_id == feature_v2.feature_id

    def test_feature_compatibility_metadata(self, flash_attention_paper):
        """Test feature compatibility requirements."""
        from kaizen.research import ExperimentalFeature, ValidationResult

        validation = ValidationResult(
            validation_passed=True, reproducibility_score=0.96
        )
        compatibility = {"kaizen": ">=0.2.0", "python": ">=3.8", "torch": ">=2.0.0"}

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility=compatibility,
            performance={},
            metadata={},
        )

        assert feature.compatibility["kaizen"] == ">=0.2.0"
        assert feature.compatibility["python"] == ">=3.8"
        assert "torch" in feature.compatibility

    def test_feature_performance_benchmarks(self, flash_attention_paper):
        """Test feature performance benchmark storage."""
        from kaizen.research import ExperimentalFeature, ValidationResult

        validation = ValidationResult(
            validation_passed=True, reproducibility_score=0.96
        )
        performance = {
            "speedup": 2.7,
            "memory_reduction": 0.3,
            "latency_p50": 0.01,
            "latency_p95": 0.05,
        }

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance=performance,
            metadata={},
        )

        assert feature.performance["speedup"] == 2.7
        assert feature.performance["latency_p95"] == 0.05

    def test_feature_get_documentation(self, flash_attention_paper):
        """Test auto-generated feature documentation."""
        from kaizen.research import ExperimentalFeature, ValidationResult

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
            compatibility={"kaizen": ">=0.1.0"},
            performance={"speedup": 2.7},
            metadata={"description": "Fast attention algorithm"},
        )

        docs = feature.get_documentation()

        assert docs is not None
        assert "Flash" in docs or "flash-attention" in docs
        assert "1.0.0" in docs
        assert "experimental" in docs


class TestFeatureIntegrationWithPhase1:
    """Test ExperimentalFeature integration with Phase 1 components."""

    def test_feature_from_validated_research(self, flash_attention_paper):
        """Test creating feature from Phase 1 validation pipeline."""
        from kaizen.research import (
            ExperimentalFeature,
            ResearchAdapter,
            ValidationResult,
        )

        # Simul Phase 1 outputs
        validation = ValidationResult(
            validation_passed=True,
            reproducibility_score=0.96,
            reproduced_metrics={"speedup": 2.7},
            quality_score={"overall": 0.95},
            issues=[],
        )

        adapter = ResearchAdapter()

        # Mock signature creation
        with patch("kaizen.research.adapter.importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_func = Mock()
            mock_func.__name__ = "flash_attn_func"
            mock_module.flash_attn_func = mock_func
            mock_import.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=flash_attention_paper,
                implementation_module="flash_attn",
                main_function="flash_attn_func",
            )

        # Create experimental feature
        feature = ExperimentalFeature(
            feature_id="flash-attention-v1",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=signature_class,
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance=validation.reproduced_metrics,
            metadata={},
        )

        assert feature.feature_id == "flash-attention-v1"
        assert feature.validation.reproducibility_score == 0.96

    def test_feature_stores_quality_metrics(self, flash_attention_paper):
        """Test feature stores quality metrics from Phase 1 validation."""
        from kaizen.research import ExperimentalFeature, ValidationResult

        validation = ValidationResult(
            validation_passed=True,
            reproducibility_score=0.96,
            reproduced_metrics={"speedup": 2.7},
            quality_score={"accuracy": 0.95, "code_quality": 0.9, "documentation": 0.8},
            issues=[],
        )

        feature = ExperimentalFeature(
            feature_id="test-feature",
            paper=flash_attention_paper,
            validation=validation,
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={},
            metadata={},
        )

        assert feature.validation.quality_score["accuracy"] == 0.95
        assert feature.validation.quality_score["code_quality"] == 0.9

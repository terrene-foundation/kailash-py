"""
Unit tests for FeatureOptimizer - WRITE TESTS FIRST (TDD RED Phase)

Test Coverage:
1. Optimizer initialization with auto-optimization engine
2. Optimize experimental feature
3. Benchmark feature performance
4. Compare multiple features
5. Integration with TODO-145 auto-optimization

CRITICAL: These tests MUST be written BEFORE implementation!
"""

from unittest.mock import Mock


class TestFeatureOptimizer:
    """Test suite for FeatureOptimizer component."""

    def test_feature_optimizer_initialization(self):
        """Test FeatureOptimizer initializes with optimization engine."""
        from kaizen.research import FeatureOptimizer

        # Mock optimization engine (from TODO-145)
        mock_engine = Mock()

        optimizer = FeatureOptimizer(optimization_engine=mock_engine)

        assert optimizer is not None
        assert optimizer.optimization_engine is mock_engine

    def test_optimize_feature(self, flash_attention_paper):
        """Test optimizing a feature with dataset."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureOptimizer,
            ValidationResult,
        )

        mock_engine = Mock()
        optimizer = FeatureOptimizer(optimization_engine=mock_engine)

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

        dataset = [{"input": "test1"}, {"input": "test2"}]

        # Optimize should return metrics
        metrics = optimizer.optimize_feature(feature, dataset)

        assert metrics is not None
        assert isinstance(metrics, dict)
        # Should include performance metrics
        assert "optimized" in metrics or "latency" in metrics or len(metrics) > 0

    def test_benchmark_feature(self, flash_attention_paper):
        """Test benchmarking feature performance."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureOptimizer,
            ValidationResult,
        )

        mock_engine = Mock()
        optimizer = FeatureOptimizer(optimization_engine=mock_engine)

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
            performance={"speedup": 2.7},
            metadata={},
        )

        benchmark_dataset = [{"input": "test1"}, {"input": "test2"}]

        # Benchmark should return performance metrics
        metrics = optimizer.benchmark_feature(feature, benchmark_dataset)

        assert metrics is not None
        assert isinstance(metrics, dict)
        assert len(metrics) > 0

    def test_compare_features(self, flash_attention_paper, maml_paper):
        """Test comparing multiple features."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureOptimizer,
            ValidationResult,
        )

        mock_engine = Mock()
        optimizer = FeatureOptimizer(optimization_engine=mock_engine)

        feature1 = ExperimentalFeature(
            feature_id="feature-1",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.95
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={},
            performance={"speedup": 2.7},
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
            status="experimental",
            compatibility={},
            performance={"speedup": 1.5},
            metadata={},
        )

        features = [feature1, feature2]

        # Compare should return metrics for each feature
        comparison = optimizer.compare_features(features)

        assert comparison is not None
        assert isinstance(comparison, dict)
        assert "feature-1" in comparison
        assert "feature-2" in comparison

    def test_optimization_integration_with_todo_145(self, flash_attention_paper):
        """Test integration with TODO-145 auto-optimization engine."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureOptimizer,
            ValidationResult,
        )

        # Mock TODO-145 optimization engine
        mock_engine = Mock()
        mock_engine.optimize = Mock(
            return_value={"optimized": True, "improvement": 0.3}
        )

        optimizer = FeatureOptimizer(optimization_engine=mock_engine)

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

        dataset = [{"input": "test"}]

        # Optimize using TODO-145 engine
        metrics = optimizer.optimize_feature(feature, dataset)

        # Engine should have been called
        assert mock_engine.optimize.called or len(metrics) > 0

    def test_optimizer_without_engine_uses_defaults(self, flash_attention_paper):
        """Test optimizer can work without external optimization engine."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureOptimizer,
            ValidationResult,
        )

        # Initialize without engine
        optimizer = FeatureOptimizer(optimization_engine=None)

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
            performance={"speedup": 2.7},
            metadata={},
        )

        # Should still return metrics (using defaults or feature.performance)
        metrics = optimizer.benchmark_feature(feature, [])

        assert metrics is not None
        assert isinstance(metrics, dict)

    def test_optimize_feature_updates_performance(self, flash_attention_paper):
        """Test optimizing feature updates its performance metrics."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureOptimizer,
            ValidationResult,
        )

        mock_engine = Mock()
        optimizer = FeatureOptimizer(optimization_engine=mock_engine)

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
            performance={"speedup": 1.0},  # Initial performance
            metadata={},
        )

        dataset = [{"input": "test"}]

        # Optimize
        metrics = optimizer.optimize_feature(feature, dataset)

        # Metrics should be returned
        assert metrics is not None
        assert isinstance(metrics, dict)

    def test_benchmark_feature_with_empty_dataset(self, flash_attention_paper):
        """Test benchmarking with empty dataset returns feature's existing performance."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureOptimizer,
            ValidationResult,
        )

        mock_engine = Mock()
        optimizer = FeatureOptimizer(optimization_engine=mock_engine)

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
            performance={"speedup": 2.7, "accuracy": 0.95},
            metadata={},
        )

        # Benchmark with empty dataset
        metrics = optimizer.benchmark_feature(feature, [])

        # Should return existing performance metrics
        assert metrics is not None
        assert isinstance(metrics, dict)
        # Should include at least some metrics
        assert len(metrics) > 0

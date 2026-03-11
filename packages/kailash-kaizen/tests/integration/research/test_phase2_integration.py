"""
Integration tests for Phase 2 Experimental Feature System - WRITE TESTS FIRST

Test Coverage:
1. Complete experimental feature workflow (discovery → registration → docs)
2. Feature manager auto-discovery integration
3. Integration workflow automation
4. Compatibility checking across features
5. Feature optimization workflows
6. Documentation generation for multiple features
7. End-to-end user scenarios

CRITICAL: These tests validate Phase 2 components working together!
"""

from pathlib import Path
from unittest.mock import Mock, patch


class TestPhase2ExperimentalFeatureWorkflow:
    """Test complete Phase 2 experimental feature workflow."""

    def test_complete_experimental_feature_workflow(self, flash_attention_paper):
        """Test complete workflow: integrate → register → optimize → document."""
        from kaizen.research import (
            DocumentationGenerator,
            FeatureManager,
            FeatureOptimizer,
            IntegrationWorkflow,
            ResearchAdapter,
            ResearchParser,
            ResearchRegistry,
            ResearchValidator,
        )

        # Phase 1 components
        parser = ResearchParser()
        validator = ResearchValidator()
        adapter = ResearchAdapter()
        registry = ResearchRegistry()

        # Phase 2 components
        feature_manager = FeatureManager(registry)
        workflow = IntegrationWorkflow(
            parser, validator, adapter, registry, feature_manager
        )
        optimizer = FeatureOptimizer()
        doc_generator = DocumentationGenerator()

        # Mock the pipeline
        with (
            patch("kaizen.research.parser.arxiv") as mock_arxiv,
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch("pathlib.Path.glob") as mock_glob,
            patch("kaizen.research.adapter.importlib"),
        ):

            # Setup mocks
            mock_result = Mock()
            mock_result.entry_id = "http://arxiv.org/abs/2205.14135"
            mock_result.title = flash_attention_paper.title
            # Create mock authors with name attribute
            mock_authors = []
            for author in flash_attention_paper.authors:
                mock_author = Mock()
                mock_author.name = author
                mock_authors.append(mock_author)
            mock_result.authors = mock_authors
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = "http://arxiv.org/pdf/2205.14135.pdf"
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            mock_glob.return_value = [Mock(spec=Path)]
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7", stderr=""
            )

            # Step 1: Integrate from arXiv
            feature = workflow.integrate_from_arxiv("2205.14135")
            assert feature is not None

            # Step 2: Verify feature is in manager
            retrieved = feature_manager.get_feature(feature.feature_id)
            assert retrieved is not None

            # Step 3: Optimize feature
            metrics = optimizer.benchmark_feature(feature, [])
            assert metrics is not None

            # Step 4: Generate documentation
            docs = doc_generator.generate_feature_docs(feature)
            assert docs is not None
            assert len(docs) > 0

    def test_feature_manager_auto_discovery(self, flash_attention_paper):
        """Test feature manager auto-discovers features from registry."""
        from kaizen.research import FeatureManager, ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        # Register papers in registry
        validation = ValidationResult(
            validation_passed=True,
            reproducibility_score=0.96,
            reproduced_metrics={"speedup": 2.7},
        )

        registry.register_paper(
            paper=flash_attention_paper, validation=validation, signature_class=Mock()
        )

        # Auto-discover features
        manager = FeatureManager(registry)
        features = manager.discover_features()

        assert len(features) > 0
        assert features[0].paper.arxiv_id == flash_attention_paper.arxiv_id

    def test_compatibility_checker_with_feature_manager(
        self, flash_attention_paper, maml_paper
    ):
        """Test compatibility checker integration with feature manager."""
        from kaizen.research import (
            CompatibilityChecker,
            ExperimentalFeature,
            FeatureManager,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry)
        checker = CompatibilityChecker()

        # Register features with different compatibility requirements
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

        manager.register_feature(feature1)
        manager.register_feature(feature2)

        # Get compatible features for version 0.2.0
        all_features = manager.list_features()
        compatible = checker.get_compatible_features(all_features, "0.2.0")

        # Only feature1 should be compatible
        assert len(compatible) == 1
        assert compatible[0].feature_id == "feature-1"

    def test_optimizer_with_manager_integration(self, flash_attention_paper):
        """Test optimizer integration with feature manager."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureManager,
            FeatureOptimizer,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry)
        optimizer = FeatureOptimizer()

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
            performance={"speedup": 2.0},
            metadata={},
        )

        manager.register_feature(feature)

        # Optimize features in manager
        all_features = manager.list_features()
        comparison = optimizer.compare_features(all_features)

        assert len(comparison) > 0
        assert "test-feature" in comparison

    def test_documentation_generator_for_all_features(
        self, flash_attention_paper, maml_paper
    ):
        """Test documentation generator creates docs for all features."""
        from kaizen.research import (
            DocumentationGenerator,
            ExperimentalFeature,
            FeatureManager,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry)
        doc_generator = DocumentationGenerator()

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
                status="experimental" if i == 0 else "beta",
                compatibility={},
                performance={},
                metadata={},
            )
            manager.register_feature(feature)

        # Generate changelog for all features
        all_features = manager.list_features()
        changelog = doc_generator.generate_changelog(all_features)

        assert changelog is not None
        assert "feature-0" in changelog or "feature-1" in changelog

    def test_integration_workflow_with_compatibility_check(self, flash_attention_paper):
        """Test integration workflow validates compatibility."""
        from kaizen.research import (
            CompatibilityChecker,
            FeatureManager,
            IntegrationWorkflow,
            ResearchAdapter,
            ResearchParser,
            ResearchRegistry,
            ResearchValidator,
        )

        # Setup
        parser = ResearchParser()
        validator = ResearchValidator()
        adapter = ResearchAdapter()
        registry = ResearchRegistry()
        manager = FeatureManager(registry)
        workflow = IntegrationWorkflow(parser, validator, adapter, registry, manager)
        checker = CompatibilityChecker()

        with (
            patch("kaizen.research.parser.arxiv") as mock_arxiv,
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch("pathlib.Path.glob") as mock_glob,
            patch("kaizen.research.adapter.importlib"),
        ):

            # Setup mocks
            mock_result = Mock()
            mock_result.entry_id = "http://arxiv.org/abs/2205.14135"
            mock_result.title = flash_attention_paper.title
            # Create mock authors with name attribute
            mock_authors = []
            for author in flash_attention_paper.authors:
                mock_author = Mock()
                mock_author.name = author
                mock_authors.append(mock_author)
            mock_result.authors = mock_authors
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = "http://arxiv.org/pdf/2205.14135.pdf"
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            mock_glob.return_value = [Mock(spec=Path)]
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7", stderr=""
            )

            # Integrate and check compatibility
            feature = workflow.integrate_from_arxiv("2205.14135")
            is_compatible = checker.check_compatibility(feature, "0.2.0")

            assert is_compatible is True  # Should be compatible with 0.2.0

    def test_end_to_end_feature_lifecycle(self, flash_attention_paper):
        """Test complete feature lifecycle: experimental → beta → stable."""
        from kaizen.research import (
            DocumentationGenerator,
            ExperimentalFeature,
            FeatureManager,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry)
        doc_generator = DocumentationGenerator()

        # Create experimental feature
        feature = ExperimentalFeature(
            feature_id="lifecycle-test",
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

        # Register
        manager.register_feature(feature)

        # Document as experimental
        docs_v1 = doc_generator.generate_feature_docs(feature)
        assert "experimental" in docs_v1.lower()

        # Transition to beta
        manager.update_feature_status("lifecycle-test", "beta")
        updated_feature = manager.get_feature("lifecycle-test")
        assert updated_feature.status == "beta"

        # Document as beta
        docs_v2 = doc_generator.generate_feature_docs(updated_feature)
        assert "beta" in docs_v2.lower()

        # Transition to stable
        manager.update_feature_status("lifecycle-test", "stable")
        final_feature = manager.get_feature("lifecycle-test")
        assert final_feature.status == "stable"

    def test_batch_integration_with_documentation(self, sample_papers):
        """Test batch integration generates documentation for all features."""
        from kaizen.research import (
            DocumentationGenerator,
            FeatureManager,
            IntegrationWorkflow,
            ResearchAdapter,
            ResearchParser,
            ResearchRegistry,
            ResearchValidator,
        )

        parser = ResearchParser()
        validator = ResearchValidator()
        adapter = ResearchAdapter()
        registry = ResearchRegistry()
        manager = FeatureManager(registry)
        workflow = IntegrationWorkflow(parser, validator, adapter, registry, manager)
        doc_generator = DocumentationGenerator()

        arxiv_ids = [
            paper.arxiv_id for paper in sample_papers[:1]
        ]  # Just test with one

        with (
            patch("kaizen.research.parser.arxiv") as mock_arxiv,
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch("pathlib.Path.glob") as mock_glob,
            patch("kaizen.research.adapter.importlib"),
        ):

            # Mock for paper
            mock_result = Mock()
            mock_result.entry_id = f"http://arxiv.org/abs/{arxiv_ids[0]}"
            mock_result.title = sample_papers[0].title
            mock_result.authors = [
                Mock(name=author) for author in sample_papers[0].authors
            ]
            mock_result.summary = sample_papers[0].abstract
            mock_result.pdf_url = f"http://arxiv.org/pdf/{arxiv_ids[0]}.pdf"
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            mock_glob.return_value = [Mock(spec=Path)]
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7", stderr=""
            )

            # Batch integrate
            features = workflow.batch_integrate(arxiv_ids)

            # Generate docs for all
            changelog = doc_generator.generate_changelog(features)

            assert len(features) >= 1
            assert changelog is not None

    def test_feature_enable_disable_workflow(self, flash_attention_paper):
        """Test feature enable/disable through manager."""
        from kaizen.research import (
            ExperimentalFeature,
            FeatureManager,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry)

        feature = ExperimentalFeature(
            feature_id="enable-test",
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

        # Feature should start disabled
        retrieved = manager.get_feature("enable-test")
        assert not retrieved.is_enabled()

        # Enable
        retrieved.enable()
        assert retrieved.is_enabled()

        # Disable
        retrieved.disable()
        assert not retrieved.is_enabled()

    def test_complete_documentation_suite_generation(self, flash_attention_paper):
        """Test generating complete documentation suite for a feature."""
        from kaizen.research import (
            DocumentationGenerator,
            ExperimentalFeature,
            FeatureManager,
            ResearchRegistry,
            ValidationResult,
        )

        registry = ResearchRegistry()
        manager = FeatureManager(registry)
        doc_generator = DocumentationGenerator()

        feature = ExperimentalFeature(
            feature_id="docs-test",
            paper=flash_attention_paper,
            validation=ValidationResult(
                validation_passed=True, reproducibility_score=0.96
            ),
            signature_class=Mock(),
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.1.0"},
            performance={"speedup": 2.7},
            metadata={"tags": ["attention"]},
        )

        manager.register_feature(feature)

        # Generate complete documentation suite
        feature_docs = doc_generator.generate_feature_docs(feature)
        usage_example = doc_generator.generate_usage_example(feature)
        api_reference = doc_generator.generate_api_reference(feature)

        # All should be generated
        assert feature_docs is not None and len(feature_docs) > 0
        assert usage_example is not None and len(usage_example) > 0
        assert api_reference is not None and len(api_reference) > 0

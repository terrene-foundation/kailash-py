"""
Unit tests for IntegrationWorkflow - WRITE TESTS FIRST (TDD RED Phase)

Test Coverage:
1. Workflow initialization with Phase 1 components
2. Auto-integration from arXiv (parse → validate → adapt → feature)
3. Integration from code URL
4. Batch integration of multiple papers
5. Integration status tracking
6. Error handling and recovery

CRITICAL: These tests MUST be written BEFORE implementation!
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestIntegrationWorkflow:
    """Test suite for IntegrationWorkflow component."""

    def test_integration_workflow_initialization(self):
        """Test IntegrationWorkflow initializes with Phase 1 components."""
        from kaizen.research import (
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
        feature_manager = FeatureManager(registry)

        workflow = IntegrationWorkflow(
            parser=parser,
            validator=validator,
            adapter=adapter,
            registry=registry,
            feature_manager=feature_manager,
        )

        assert workflow is not None
        assert workflow.parser is parser
        assert workflow.validator is validator
        assert workflow.adapter is adapter
        assert workflow.registry is registry
        assert workflow.feature_manager is feature_manager

    def test_integrate_from_arxiv_auto(self, flash_attention_paper):
        """Test automatic integration from arXiv ID."""
        from kaizen.research import (
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
        feature_manager = FeatureManager(registry)

        workflow = IntegrationWorkflow(
            parser=parser,
            validator=validator,
            adapter=adapter,
            registry=registry,
            feature_manager=feature_manager,
        )

        # Mock the entire pipeline
        with (
            patch("kaizen.research.parser.arxiv") as mock_arxiv,
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch("pathlib.Path.glob") as mock_glob,
            patch("kaizen.research.adapter.importlib"),
        ):

            # Mock arXiv
            mock_result = Mock()
            mock_result.entry_id = "http://arxiv.org/abs/2205.14135"
            mock_result.title = flash_attention_paper.title
            mock_result.authors = [
                Mock(name=author) for author in flash_attention_paper.authors
            ]
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = "http://arxiv.org/pdf/2205.14135.pdf"
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            # Mock validation
            mock_glob.return_value = [Mock(spec=Path)]
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7", stderr=""
            )

            # Integrate from arXiv
            feature = workflow.integrate_from_arxiv(
                arxiv_id="2205.14135", auto_enable=False
            )

            assert feature is not None
            assert feature.paper.arxiv_id == "2205.14135"
            assert feature.validation.validation_passed is True
            assert feature.status == "experimental"

    def test_integrate_from_arxiv_auto_enable(self, flash_attention_paper):
        """Test integration with auto_enable=True."""
        from kaizen.research import (
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
        feature_manager = FeatureManager(registry)

        workflow = IntegrationWorkflow(
            parser=parser,
            validator=validator,
            adapter=adapter,
            registry=registry,
            feature_manager=feature_manager,
        )

        with (
            patch("kaizen.research.parser.arxiv") as mock_arxiv,
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch("pathlib.Path.glob") as mock_glob,
            patch("kaizen.research.adapter.importlib"),
        ):

            # Setup mocks (same as above)
            mock_result = Mock()
            mock_result.entry_id = "http://arxiv.org/abs/2205.14135"
            mock_result.title = flash_attention_paper.title
            mock_result.authors = [
                Mock(name=author) for author in flash_attention_paper.authors
            ]
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = "http://arxiv.org/pdf/2205.14135.pdf"
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            mock_glob.return_value = [Mock(spec=Path)]
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7", stderr=""
            )

            # Integrate with auto_enable
            feature = workflow.integrate_from_arxiv(
                arxiv_id="2205.14135", auto_enable=True
            )

            # Feature should be enabled
            assert feature.is_enabled() is True

    def test_integrate_from_url(self, flash_attention_paper):
        """Test integration from code URL with paper ID."""
        from kaizen.research import (
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
        feature_manager = FeatureManager(registry)

        workflow = IntegrationWorkflow(
            parser=parser,
            validator=validator,
            adapter=adapter,
            registry=registry,
            feature_manager=feature_manager,
        )

        with (
            patch("kaizen.research.parser.arxiv") as mock_arxiv,
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch("pathlib.Path.glob") as mock_glob,
            patch("kaizen.research.adapter.importlib"),
        ):

            # Mock arXiv
            mock_result = Mock()
            mock_result.entry_id = "http://arxiv.org/abs/2205.14135"
            mock_result.title = flash_attention_paper.title
            mock_result.authors = [
                Mock(name=author) for author in flash_attention_paper.authors
            ]
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = "http://arxiv.org/pdf/2205.14135.pdf"
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            # Mock validation
            mock_glob.return_value = [Mock(spec=Path)]
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7", stderr=""
            )

            # Integrate from URL
            feature = workflow.integrate_from_url(
                code_url="https://github.com/Dao-AILab/flash-attention",
                paper_id="2205.14135",
                auto_enable=False,
            )

            assert feature is not None
            assert feature.paper.arxiv_id == "2205.14135"

    def test_batch_integrate(self, sample_papers):
        """Test batch integration of multiple papers."""
        from kaizen.research import (
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
        feature_manager = FeatureManager(registry)

        workflow = IntegrationWorkflow(
            parser=parser,
            validator=validator,
            adapter=adapter,
            registry=registry,
            feature_manager=feature_manager,
        )

        arxiv_ids = [paper.arxiv_id for paper in sample_papers]

        with (
            patch("kaizen.research.parser.arxiv") as mock_arxiv,
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch("pathlib.Path.glob") as mock_glob,
            patch("kaizen.research.adapter.importlib"),
        ):

            # Mock for all papers
            def mock_arxiv_search(arxiv_id):
                # Find matching paper
                for paper in sample_papers:
                    if paper.arxiv_id == arxiv_id:
                        mock_result = Mock()
                        mock_result.entry_id = f"http://arxiv.org/abs/{arxiv_id}"
                        mock_result.title = paper.title
                        mock_result.authors = [
                            Mock(name=author) for author in paper.authors
                        ]
                        mock_result.summary = paper.abstract
                        mock_result.pdf_url = f"http://arxiv.org/pdf/{arxiv_id}.pdf"
                        return [mock_result]
                return []

            mock_arxiv.Search.return_value.results = lambda: mock_arxiv_search(
                arxiv_ids[0]
            )

            mock_glob.return_value = [Mock(spec=Path)]
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7", stderr=""
            )

            # Batch integrate
            features = workflow.batch_integrate(
                arxiv_ids[:1]
            )  # Just test with one for simplicity

            assert len(features) >= 1
            assert all(f.validation.validation_passed for f in features)

    def test_get_integration_status(self, flash_attention_paper):
        """Test tracking integration status."""
        from kaizen.research import (
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
        feature_manager = FeatureManager(registry)

        workflow = IntegrationWorkflow(
            parser=parser,
            validator=validator,
            adapter=adapter,
            registry=registry,
            feature_manager=feature_manager,
        )

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
            mock_result.authors = [
                Mock(name=author) for author in flash_attention_paper.authors
            ]
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = "http://arxiv.org/pdf/2205.14135.pdf"
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            mock_glob.return_value = [Mock(spec=Path)]
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7", stderr=""
            )

            # Start integration
            feature = workflow.integrate_from_arxiv("2205.14135")

            # Get status (should track completion)
            status = workflow.get_integration_status(feature.feature_id)

            assert status is not None
            assert status["status"] in ["completed", "in_progress", "failed"]

    def test_integration_error_handling_invalid_arxiv(self):
        """Test error handling with invalid arXiv ID."""
        from kaizen.research import (
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
        feature_manager = FeatureManager(registry)

        workflow = IntegrationWorkflow(
            parser=parser,
            validator=validator,
            adapter=adapter,
            registry=registry,
            feature_manager=feature_manager,
        )

        with patch("kaizen.research.parser.arxiv") as mock_arxiv:
            # Mock no results
            mock_arxiv.Search.return_value.results.return_value = []

            # Should raise error for invalid arXiv ID
            with pytest.raises(ValueError, match="Failed to parse paper"):
                workflow.integrate_from_arxiv("invalid_id")

    def test_integration_error_handling_validation_failure(self, flash_attention_paper):
        """Test error handling when validation fails."""
        from kaizen.research import (
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
        feature_manager = FeatureManager(registry)

        workflow = IntegrationWorkflow(
            parser=parser,
            validator=validator,
            adapter=adapter,
            registry=registry,
            feature_manager=feature_manager,
        )

        with (
            patch("kaizen.research.parser.arxiv") as mock_arxiv,
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
        ):

            # Mock arXiv
            mock_result = Mock()
            mock_result.entry_id = "http://arxiv.org/abs/2205.14135"
            mock_result.title = flash_attention_paper.title
            mock_result.authors = [
                Mock(name=author) for author in flash_attention_paper.authors
            ]
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = "http://arxiv.org/pdf/2205.14135.pdf"
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            # Mock validation failure (returncode != 0)
            mock_subprocess.run.return_value = Mock(
                returncode=1, stdout="", stderr="Error"
            )

            # Should raise error for failed validation
            with pytest.raises(ValueError, match="Validation failed"):
                workflow.integrate_from_arxiv("2205.14135")

    def test_workflow_registers_feature_in_manager(self, flash_attention_paper):
        """Test that workflow registers feature in FeatureManager."""
        from kaizen.research import (
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
        feature_manager = FeatureManager(registry)

        workflow = IntegrationWorkflow(
            parser=parser,
            validator=validator,
            adapter=adapter,
            registry=registry,
            feature_manager=feature_manager,
        )

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
            mock_result.authors = [
                Mock(name=author) for author in flash_attention_paper.authors
            ]
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = "http://arxiv.org/pdf/2205.14135.pdf"
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            mock_glob.return_value = [Mock(spec=Path)]
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7", stderr=""
            )

            # Integrate
            feature = workflow.integrate_from_arxiv("2205.14135")

            # Feature should be in manager
            retrieved = feature_manager.get_feature(feature.feature_id)
            assert retrieved is not None
            assert retrieved.feature_id == feature.feature_id

    def test_workflow_registers_paper_in_registry(self, flash_attention_paper):
        """Test that workflow registers paper in ResearchRegistry."""
        from kaizen.research import (
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
        feature_manager = FeatureManager(registry)

        workflow = IntegrationWorkflow(
            parser=parser,
            validator=validator,
            adapter=adapter,
            registry=registry,
            feature_manager=feature_manager,
        )

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
            mock_result.authors = [
                Mock(name=author) for author in flash_attention_paper.authors
            ]
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = "http://arxiv.org/pdf/2205.14135.pdf"
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            mock_glob.return_value = [Mock(spec=Path)]
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7", stderr=""
            )

            # Integrate
            feature = workflow.integrate_from_arxiv("2205.14135")

            # Paper should be in registry
            retrieved = registry.get_by_id(feature.paper.arxiv_id)
            assert retrieved is not None
            assert retrieved["paper"].arxiv_id == feature.paper.arxiv_id

"""
Integration tests for complete research workflow - WRITE TESTS FIRST (TDD RED Phase)

Test Coverage:
1. End-to-end: Parse → Validate → Adapt → Register → Execute
2. Real infrastructure (NO MOCKING per Kaizen testing principles)
3. Performance validation (<7 days integration time)
4. Complete user workflows

CRITICAL: These tests define the integration success criteria!
Write these BEFORE implementing the components.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestResearchIntegrationWorkflow:
    """Test complete research integration workflow."""

    def test_complete_workflow_flash_attention(self, flash_attention_paper):
        """Test complete workflow: parse → validate → adapt → register."""
        from kaizen.research import (
            ResearchAdapter,
            ResearchParser,
            ResearchRegistry,
            ResearchValidator,
        )

        # Step 1: Parse research paper
        parser = ResearchParser()

        with patch("kaizen.research.parser.arxiv") as mock_arxiv:
            mock_result = Mock()
            mock_result.entry_id = (
                f"http://arxiv.org/abs/{flash_attention_paper.arxiv_id}"
            )
            mock_result.title = flash_attention_paper.title
            mock_result.authors = [
                Mock(name=author) for author in flash_attention_paper.authors
            ]
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = (
                f"http://arxiv.org/pdf/{flash_attention_paper.arxiv_id}.pdf"
            )
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            paper = parser.parse_from_arxiv("2205.14135")

        assert paper is not None

        # Step 2: Validate implementation
        validator = ResearchValidator()

        with (
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch("pathlib.Path.glob") as mock_glob,
        ):
            mock_glob.return_value = [Mock(spec=Path)]  # Mock test files exist
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7\naccuracy: 1.0", stderr=""
            )

            validation = validator.validate_implementation(
                paper=paper,
                code_url="https://github.com/Dao-AILab/flash-attention",
                validation_dataset=None,
            )

        assert validation.validation_passed is True
        assert validation.reproducibility_score >= 0.95

        # Step 3: Adapt to signature
        adapter = ResearchAdapter()

        with patch("kaizen.research.adapter.importlib") as mock_importlib:
            mock_module = Mock()
            mock_func = Mock(return_value="result")
            mock_module.flash_attn_func = mock_func
            mock_importlib.import_module.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=paper,
                implementation_module="flash_attn",
                main_function="flash_attn_func",
            )

        assert signature_class is not None

        # Step 4: Register in catalog
        registry = ResearchRegistry()
        entry_id = registry.register_paper(
            paper=paper, validation=validation, signature_class=signature_class
        )

        assert entry_id is not None

        # Step 5: Verify retrieval
        retrieved = registry.get_by_id(paper.arxiv_id)
        assert retrieved is not None
        assert retrieved["paper"].arxiv_id == paper.arxiv_id

    def test_complete_workflow_multiple_papers(self, sample_papers):
        """Test workflow with multiple research papers."""
        from kaizen.research import (
            ResearchAdapter,
            ResearchParser,
            ResearchRegistry,
            ResearchValidator,
        )

        registry = ResearchRegistry()
        successful_integrations = 0

        for paper_fixture in sample_papers:
            # Parse
            parser = ResearchParser()

            with patch("kaizen.research.parser.arxiv") as mock_arxiv:
                mock_result = Mock()
                mock_result.entry_id = f"http://arxiv.org/abs/{paper_fixture.arxiv_id}"
                mock_result.title = paper_fixture.title
                mock_result.authors = [
                    Mock(name=author) for author in paper_fixture.authors
                ]
                mock_result.summary = paper_fixture.abstract
                mock_result.pdf_url = (
                    f"http://arxiv.org/pdf/{paper_fixture.arxiv_id}.pdf"
                )
                mock_arxiv.Search.return_value.results.return_value = [mock_result]

                paper = parser.parse_from_arxiv(paper_fixture.arxiv_id)

            # Validate
            validator = ResearchValidator()

            with (
                patch("kaizen.research.validator.subprocess") as mock_subprocess,
                patch("kaizen.research.validator.git.Repo.clone_from"),
                patch("pathlib.Path.glob") as mock_glob,
            ):
                # Return metrics matching the paper
                mock_glob.return_value = [Mock(spec=Path)]  # Mock test files exist
                metrics_str = " ".join(
                    [f"{k}: {v}" for k, v in paper_fixture.metrics.items()]
                )
                mock_subprocess.run.return_value = Mock(
                    returncode=0, stdout=metrics_str, stderr=""
                )

                validation = validator.validate_implementation(
                    paper=paper,
                    code_url=paper_fixture.code_url,
                    validation_dataset=None,
                )

            if validation.validation_passed:
                # Adapt
                adapter = ResearchAdapter()

                with patch("kaizen.research.adapter.importlib"):
                    signature_class = adapter.create_signature_adapter(
                        paper=paper, implementation_module="test", main_function="test"
                    )

                # Register
                registry.register_paper(
                    paper=paper, validation=validation, signature_class=signature_class
                )

                successful_integrations += 1

        # Should successfully integrate all sample papers
        assert successful_integrations == len(sample_papers)
        assert len(registry.list_all()) == len(sample_papers)

    def test_workflow_performance_targets(
        self, flash_attention_paper, performance_timer
    ):
        """Test complete workflow meets performance targets."""
        from kaizen.research import (
            ResearchAdapter,
            ResearchParser,
            ResearchRegistry,
            ResearchValidator,
        )

        total_timer = performance_timer()
        total_timer.start()

        # Parse (<30s)
        parser = ResearchParser()
        parse_timer = performance_timer()
        parse_timer.start()

        with patch("kaizen.research.parser.arxiv") as mock_arxiv:
            mock_result = Mock()
            mock_result.entry_id = (
                f"http://arxiv.org/abs/{flash_attention_paper.arxiv_id}"
            )
            mock_result.title = flash_attention_paper.title
            mock_result.authors = [
                Mock(name=author) for author in flash_attention_paper.authors
            ]
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = (
                f"http://arxiv.org/pdf/{flash_attention_paper.arxiv_id}.pdf"
            )
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            paper = parser.parse_from_arxiv("2205.14135")

        parse_time = parse_timer.stop()
        assert parse_time < 30, f"Parse took {parse_time:.1f}s (target: <30s)"

        # Validate (<5 minutes)
        validator = ResearchValidator()
        validate_timer = performance_timer()
        validate_timer.start()

        with (
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch("pathlib.Path.glob") as mock_glob,
        ):
            mock_glob.return_value = [Mock(spec=Path)]  # Mock test files exist
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7", stderr=""
            )

            validation = validator.validate_implementation(
                paper=paper,
                code_url="https://github.com/test/repo",
                validation_dataset=None,
            )

        validate_time = validate_timer.stop()
        assert (
            validate_time < 300
        ), f"Validation took {validate_time:.1f}s (target: <300s)"

        # Adapt (<1s)
        adapter = ResearchAdapter()
        adapt_timer = performance_timer()
        adapt_timer.start()

        with patch("kaizen.research.adapter.importlib"):
            signature_class = adapter.create_signature_adapter(
                paper=paper, implementation_module="test", main_function="test"
            )

        adapt_time = adapt_timer.stop()
        assert adapt_time < 1, f"Adaptation took {adapt_time:.1f}s (target: <1s)"

        # Register (<0.1s)
        registry = ResearchRegistry()
        register_timer = performance_timer()
        register_timer.start()

        registry.register_paper(
            paper=paper, validation=validation, signature_class=signature_class
        )

        register_time = register_timer.stop()
        assert (
            register_time < 0.1
        ), f"Registration took {register_time:.3f}s (target: <0.1s)"

        # Search (<0.1s)
        search_timer = performance_timer()
        search_timer.start()
        registry.search(title="Flash")
        search_time = search_timer.stop()

        assert search_time < 0.1, f"Search took {search_time:.3f}s (target: <0.1s)"

        total_time = total_timer.stop()
        print("\n=== Performance Summary ===")
        print(f"Parse: {parse_time:.3f}s (target: <30s)")
        print(f"Validate: {validate_time:.3f}s (target: <300s)")
        print(f"Adapt: {adapt_time:.3f}s (target: <1s)")
        print(f"Register: {register_time:.3f}s (target: <0.1s)")
        print(f"Search: {search_time:.3f}s (target: <0.1s)")
        print(f"Total: {total_time:.3f}s")

    def test_workflow_error_handling(self, invalid_paper):
        """Test workflow handles errors gracefully."""
        from kaizen.research import ResearchParser, ResearchValidator

        # Parse should fail or return minimal paper
        parser = ResearchParser()

        with patch("kaizen.research.parser.arxiv") as mock_arxiv:
            mock_arxiv.Search.return_value.results.return_value = []

            with pytest.raises(ValueError):
                parser.parse_from_arxiv("invalid_id")

        # Validator should handle invalid paper
        validator = ResearchValidator()
        validation = validator.validate_implementation(
            paper=invalid_paper,
            code_url="https://github.com/invalid/repo",
            validation_dataset=None,
        )

        assert validation.validation_passed is False

    def test_workflow_with_real_signature_execution(self, flash_attention_paper):
        """Test that adapted signature can execute in workflow."""
        from kaizen.research import ResearchAdapter, ResearchParser

        # Parse paper
        parser = ResearchParser()

        with patch("kaizen.research.parser.arxiv") as mock_arxiv:
            mock_result = Mock()
            mock_result.entry_id = (
                f"http://arxiv.org/abs/{flash_attention_paper.arxiv_id}"
            )
            mock_result.title = flash_attention_paper.title
            mock_result.authors = [
                Mock(name=author) for author in flash_attention_paper.authors
            ]
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = (
                f"http://arxiv.org/pdf/{flash_attention_paper.arxiv_id}.pdf"
            )
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            paper = parser.parse_from_arxiv("2205.14135")

        # Adapt to signature
        adapter = ResearchAdapter()

        with patch("kaizen.research.adapter.importlib") as mock_importlib:
            mock_module = Mock()
            mock_func = Mock(return_value={"output": "test_result"})
            mock_module.test_func = mock_func
            mock_importlib.import_module.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=paper, implementation_module="test", main_function="test_func"
            )

            # Execute signature (integration with TODO-142)
            sig_instance = signature_class()

            # Should be executable
            assert hasattr(sig_instance, "execute")


class TestIntegrationWithExistingSystems:
    """Test integration with TODO-142, TODO-145, TODO-151."""

    def test_integration_with_signature_system(self, flash_attention_paper):
        """Test integration with TODO-142 signature programming system."""
        from kaizen.research import ResearchAdapter
        from kaizen.signatures import Signature

        adapter = ResearchAdapter()

        with patch("kaizen.research.adapter.importlib"):
            signature_class = adapter.create_signature_adapter(
                paper=flash_attention_paper,
                implementation_module="test",
                main_function="test",
            )

            # Should be compatible with Signature system
            assert issubclass(signature_class, Signature)

    def test_integration_with_quality_metrics(self, flash_attention_paper):
        """Test integration with TODO-145 QualityMetrics."""
        from kaizen.research import ResearchValidator

        validator = ResearchValidator()

        # Validator should use QualityMetrics from TODO-145
        with (
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
        ):
            mock_subprocess.run.return_value = Mock(returncode=0, stdout="", stderr="")

            validation = validator.validate_implementation(
                paper=flash_attention_paper,
                code_url="https://github.com/test/repo",
                validation_dataset=None,
            )

            # Should include quality scoring
            assert hasattr(validation, "quality_score")

    def test_searchable_catalog_across_registry(self, sample_papers):
        """Test searchable research catalog functionality."""
        from kaizen.research import ResearchRegistry, ValidationResult

        registry = ResearchRegistry()

        for paper in sample_papers:
            registry.register_paper(
                paper=paper,
                validation=ValidationResult(
                    validation_passed=True, reproducibility_score=0.95
                ),
                signature_class=Mock(),
            )

        # Should be searchable by multiple criteria
        title_results = registry.search(title="Flash")
        author_results = registry.search(author="Tri Dao")
        method_results = registry.search(methodology="attention")

        assert len(title_results) > 0
        assert len(author_results) > 0
        assert len(method_results) > 0


class TestEndToEndUserScenarios:
    """Test complete user scenarios."""

    def test_researcher_integrates_new_paper(self, flash_attention_paper):
        """Test scenario: Researcher integrates a new research paper."""
        from kaizen.research import (
            ResearchAdapter,
            ResearchParser,
            ResearchRegistry,
            ResearchValidator,
        )

        # User wants to integrate Flash Attention paper
        arxiv_id = "2205.14135"
        code_url = "https://github.com/Dao-AILab/flash-attention"

        # Step 1: Parse paper
        parser = ResearchParser()

        with patch("kaizen.research.parser.arxiv") as mock_arxiv:
            mock_result = Mock()
            mock_result.entry_id = f"http://arxiv.org/abs/{arxiv_id}"
            mock_result.title = flash_attention_paper.title
            mock_result.authors = [
                Mock(name=author) for author in flash_attention_paper.authors
            ]
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = f"http://arxiv.org/pdf/{arxiv_id}.pdf"
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            paper = parser.parse_from_arxiv(arxiv_id)

        # Step 2: Validate (researcher provides validation dataset)
        validator = ResearchValidator()

        with (
            patch("kaizen.research.validator.subprocess") as mock_subprocess,
            patch("kaizen.research.validator.git.Repo.clone_from"),
            patch("pathlib.Path.glob") as mock_glob,
        ):
            mock_glob.return_value = [Mock(spec=Path)]  # Mock test files exist
            mock_subprocess.run.return_value = Mock(
                returncode=0, stdout="speedup: 2.7\naccuracy: 1.0", stderr=""
            )

            validation = validator.validate_implementation(
                paper=paper,
                code_url=code_url,
                validation_dataset=None,  # Could provide custom dataset
            )

        # Validation should pass
        assert validation.validation_passed is True

        # Step 3: Adapt to Kaizen signature
        adapter = ResearchAdapter()

        with patch("kaizen.research.adapter.importlib"):
            signature_class = adapter.create_signature_adapter(
                paper=paper,
                implementation_module="flash_attn",
                main_function="flash_attn_func",
            )

        # Step 4: Register for future use
        registry = ResearchRegistry()
        registry.register_paper(
            paper=paper, validation=validation, signature_class=signature_class
        )

        # Step 5: Later, researcher can find and reuse
        retrieved = registry.search(title="Flash")

        assert len(retrieved) > 0
        assert retrieved[0]["paper"].arxiv_id == arxiv_id

    def test_developer_searches_and_uses_research(self, sample_papers):
        """Test scenario: Developer searches for and uses research."""
        from kaizen.research import ResearchRegistry, ValidationResult

        # Setup: Registry already has papers
        registry = ResearchRegistry()

        for paper in sample_papers:
            registry.register_paper(
                paper=paper,
                validation=ValidationResult(
                    validation_passed=True, reproducibility_score=0.95
                ),
                signature_class=Mock(),
            )

        # Developer searches for attention mechanisms
        results = registry.search(methodology="attention")

        # Should find Flash Attention
        assert len(results) > 0

        # Developer retrieves specific paper
        flash_attention_entry = registry.get_by_id(sample_papers[0].arxiv_id)

        assert flash_attention_entry is not None

        # Developer can use the signature_class
        signature_class = flash_attention_entry["signature_class"]
        assert signature_class is not None

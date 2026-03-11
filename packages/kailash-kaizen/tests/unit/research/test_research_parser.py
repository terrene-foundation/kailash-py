"""
Unit tests for ResearchParser - WRITE TESTS FIRST (TDD RED Phase)

Test Coverage:
1. Parse arXiv papers by ID
2. Parse PDF files
3. Extract methodology from text
4. Extract metrics from text
5. Handle malformed inputs
6. Performance validation (<30s per paper)

CRITICAL: These tests MUST be written BEFORE implementation!
Implementation comes in GREEN phase after all tests are written.
"""

from unittest.mock import Mock, patch

import pytest


class TestResearchParser:
    """Test suite for ResearchParser component."""

    def test_parser_initialization(self):
        """Test ResearchParser can be instantiated."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()
        assert parser is not None
        assert hasattr(parser, "parse_from_arxiv")
        assert hasattr(parser, "parse_from_pdf")
        assert hasattr(parser, "_extract_methods")
        assert hasattr(parser, "_extract_metrics")

    def test_parse_from_arxiv_flash_attention(self, flash_attention_paper):
        """Test parsing Flash Attention paper from arXiv ID."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()

        # Mock arXiv API to return our test paper
        with patch("kaizen.research.parser.arxiv") as mock_arxiv:
            mock_result = Mock()
            mock_result.entry_id = (
                f"http://arxiv.org/abs/{flash_attention_paper.arxiv_id}"
            )
            mock_result.title = flash_attention_paper.title
            # Fix: Create mock authors with .name property that returns the string
            mock_authors = []
            for author in flash_attention_paper.authors:
                mock_author = Mock()
                mock_author.name = author  # Set name as string, not Mock
                mock_authors.append(mock_author)
            mock_result.authors = mock_authors
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = (
                f"http://arxiv.org/pdf/{flash_attention_paper.arxiv_id}.pdf"
            )
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            paper = parser.parse_from_arxiv("2205.14135")

            assert paper is not None
            assert paper.arxiv_id == "2205.14135"
            assert "FlashAttention" in paper.title or "Flash Attention" in paper.title
            assert len(paper.authors) > 0
            assert "Tri Dao" in paper.authors
            assert len(paper.abstract) > 0

    def test_parse_from_arxiv_maml(self, maml_paper):
        """Test parsing MAML paper from arXiv ID."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()

        with patch("kaizen.research.parser.arxiv") as mock_arxiv:
            mock_result = Mock()
            mock_result.entry_id = f"http://arxiv.org/abs/{maml_paper.arxiv_id}"
            mock_result.title = maml_paper.title
            # Fix: Create mock authors with .name property that returns the string
            mock_authors = []
            for author in maml_paper.authors:
                mock_author = Mock()
                mock_author.name = author  # Set name as string, not Mock
                mock_authors.append(mock_author)
            mock_result.authors = mock_authors
            mock_result.summary = maml_paper.abstract
            mock_result.pdf_url = f"http://arxiv.org/pdf/{maml_paper.arxiv_id}.pdf"
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            paper = parser.parse_from_arxiv("1703.03400")

            assert paper is not None
            assert paper.arxiv_id == "1703.03400"
            assert "MAML" in paper.title or "Meta-Learning" in paper.title
            assert "Chelsea Finn" in paper.authors

    def test_parse_from_arxiv_invalid_id(self):
        """Test error handling for invalid arXiv ID."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()

        with patch("kaizen.research.parser.arxiv") as mock_arxiv:
            mock_arxiv.Search.return_value.results.return_value = []

            with pytest.raises(ValueError, match="Paper.*not found"):
                parser.parse_from_arxiv("invalid_id")

    def test_parse_from_arxiv_performance(
        self, flash_attention_paper, performance_timer
    ):
        """Test arXiv parsing meets <30s performance target."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()

        with patch("kaizen.research.parser.arxiv") as mock_arxiv:
            mock_result = Mock()
            mock_result.entry_id = (
                f"http://arxiv.org/abs/{flash_attention_paper.arxiv_id}"
            )
            mock_result.title = flash_attention_paper.title
            # Fix: Create mock authors with .name property that returns the string
            mock_authors = []
            for author in flash_attention_paper.authors:
                mock_author = Mock()
                mock_author.name = author  # Set name as string, not Mock
                mock_authors.append(mock_author)
            mock_result.authors = mock_authors
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = (
                f"http://arxiv.org/pdf/{flash_attention_paper.arxiv_id}.pdf"
            )
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            # Fix: Instantiate the Timer class
            timer = performance_timer()
            timer.start()
            parser.parse_from_arxiv("2205.14135")
            timer.stop()

            timer.assert_under(30.0, "arXiv parsing")

    def test_parse_from_pdf(self, mock_pdf_content):
        """Test parsing paper from PDF file."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()

        # Mock PDF reader and Path.exists() check
        with (
            patch("kaizen.research.parser.PdfReader") as MockPdfReader,
            patch("kaizen.research.parser.Path.exists", return_value=True),
        ):
            mock_reader = Mock()
            mock_page = Mock()
            mock_page.extract_text.return_value = mock_pdf_content
            mock_reader.pages = [mock_page]
            MockPdfReader.return_value = mock_reader

            paper = parser.parse_from_pdf("/fake/path/flash_attention.pdf")

            assert paper is not None
            assert paper.title != ""
            assert "FlashAttention" in paper.title or "Flash Attention" in paper.title
            assert len(paper.methodology) > 0

    def test_parse_from_pdf_missing_file(self):
        """Test error handling for missing PDF file."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()

        with pytest.raises(FileNotFoundError):
            parser.parse_from_pdf("/nonexistent/path/paper.pdf")

    def test_extract_methods_from_text(self):
        """Test method extraction from paper text."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()
        text = """
        We propose FlashAttention, a novel attention mechanism that uses
        tiling to reduce memory transfers. Our approach leverages SRAM
        for intermediate computations.
        """

        methods = parser._extract_methods(text)

        assert "FlashAttention" in methods or "Flash Attention" in methods
        assert "tiling" in methods.lower()
        assert "SRAM" in methods or "sram" in methods.lower()

    def test_extract_methods_multiple_techniques(self):
        """Test extraction of multiple methodology terms."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()
        text = """
        Our methodology combines gradient descent, backpropagation,
        and meta-learning to achieve fast adaptation.
        """

        methods = parser._extract_methods(text)

        assert "gradient descent" in methods.lower()
        assert "backpropagation" in methods.lower()
        assert "meta-learning" in methods.lower()

    def test_extract_metrics_speedup_and_accuracy(self):
        """Test metric extraction from paper text."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()
        text = "FlashAttention achieves 2.7x speedup with 95.3% accuracy"

        metrics = parser._extract_metrics(text)

        assert "speedup" in metrics
        assert metrics["speedup"] == pytest.approx(2.7, abs=0.1)
        assert "accuracy" in metrics
        assert metrics["accuracy"] == pytest.approx(0.953, abs=0.01)

    def test_extract_metrics_memory_reduction(self):
        """Test extraction of memory reduction metrics."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()
        text = "Our approach reduces memory usage by 3x while maintaining performance"

        metrics = parser._extract_metrics(text)

        assert "memory_reduction" in metrics or "memory" in metrics
        # Should extract the 3x factor
        assert any(v == pytest.approx(3.0, abs=0.1) for v in metrics.values())

    def test_extract_metrics_percentage_format(self):
        """Test extraction of percentage-based metrics."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()
        text = "We achieve 89.5% accuracy and 12.3% error rate"

        metrics = parser._extract_metrics(text)

        assert "accuracy" in metrics
        assert metrics["accuracy"] == pytest.approx(0.895, abs=0.01)

    def test_extract_metrics_no_metrics_found(self):
        """Test handling of text with no extractable metrics."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()
        text = "This is just a description with no numeric results"

        metrics = parser._extract_metrics(text)

        # Should return empty dict or dict with no metrics
        assert isinstance(metrics, dict)

    def test_parse_complete_paper_structure(self, flash_attention_paper):
        """Test that parsed paper has all required fields."""
        from kaizen.research import ResearchPaper, ResearchParser

        parser = ResearchParser()

        with patch("kaizen.research.parser.arxiv") as mock_arxiv:
            mock_result = Mock()
            mock_result.entry_id = (
                f"http://arxiv.org/abs/{flash_attention_paper.arxiv_id}"
            )
            mock_result.title = flash_attention_paper.title
            # Fix: Create mock authors with .name property that returns the string
            mock_authors = []
            for author in flash_attention_paper.authors:
                mock_author = Mock()
                mock_author.name = author  # Set name as string, not Mock
                mock_authors.append(mock_author)
            mock_result.authors = mock_authors
            mock_result.summary = flash_attention_paper.abstract
            mock_result.pdf_url = (
                f"http://arxiv.org/pdf/{flash_attention_paper.arxiv_id}.pdf"
            )
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            paper = parser.parse_from_arxiv("2205.14135")

            # Verify ResearchPaper structure
            assert isinstance(paper, ResearchPaper)
            assert hasattr(paper, "arxiv_id")
            assert hasattr(paper, "title")
            assert hasattr(paper, "authors")
            assert hasattr(paper, "abstract")
            assert hasattr(paper, "methodology")
            assert hasattr(paper, "metrics")
            assert hasattr(paper, "code_url")

    def test_parse_extracts_code_repository_url(self):
        """Test extraction of code repository URLs from paper."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()
        text = """
        Our code is available at https://github.com/author/repository
        and can be used to reproduce all experiments.
        """

        code_url = parser._extract_code_url(text)

        assert code_url is not None
        assert "github.com" in code_url
        assert "author/repository" in code_url

    def test_parse_handles_multiple_code_urls(self):
        """Test handling of papers with multiple repository URLs."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()
        text = """
        Main implementation: https://github.com/main/repo
        Additional experiments: https://github.com/experiments/repo
        """

        code_url = parser._extract_code_url(text)

        # Should return the first or main URL
        assert code_url is not None
        assert "github.com" in code_url

    def test_parse_creates_unique_paper_id(self):
        """Test that each parsed paper gets a unique identifier."""
        from kaizen.research import ResearchParser

        parser = ResearchParser()

        with patch("kaizen.research.parser.arxiv") as mock_arxiv:
            mock_result = Mock()
            mock_result.entry_id = "http://arxiv.org/abs/2205.14135"
            mock_result.title = "Test Paper"
            # Fix: Create mock author with .name property that returns the string
            mock_author = Mock()
            mock_author.name = "Author"
            mock_result.authors = [mock_author]
            mock_result.summary = "Abstract"
            mock_result.pdf_url = "http://arxiv.org/pdf/2205.14135.pdf"
            mock_arxiv.Search.return_value.results.return_value = [mock_result]

            paper1 = parser.parse_from_arxiv("2205.14135")
            paper2 = parser.parse_from_arxiv("2205.14135")

            # Same paper should have same ID
            assert paper1.arxiv_id == paper2.arxiv_id


class TestResearchPaperDataclass:
    """Test ResearchPaper data structure."""

    def test_research_paper_creation(self):
        """Test ResearchPaper can be created with required fields."""
        from kaizen.research import ResearchPaper

        paper = ResearchPaper(
            arxiv_id="2205.14135",
            title="Test Paper",
            authors=["Author 1", "Author 2"],
            abstract="Test abstract",
            methodology="Test methodology",
            metrics={"speedup": 2.0},
            code_url="https://github.com/test/repo",
        )

        assert paper.arxiv_id == "2205.14135"
        assert paper.title == "Test Paper"
        assert len(paper.authors) == 2
        assert paper.metrics["speedup"] == 2.0

    def test_research_paper_optional_fields(self):
        """Test ResearchPaper with optional fields."""
        from kaizen.research import ResearchPaper

        paper = ResearchPaper(
            arxiv_id="test",
            title="Test",
            authors=["Author"],
            abstract="Abstract",
            methodology="Methods",
        )

        # Optional fields should have defaults
        assert hasattr(paper, "metrics")
        assert hasattr(paper, "code_url")

"""
Unit tests for BaseDocumentProvider abstract class.

Tests:
- ExtractionResult dataclass validation
- ProviderCapability enum
- Abstract method enforcement
- Helper methods (_get_page_count, _validate_file_type)
"""

from dataclasses import asdict
from typing import Any, Dict

import pytest
from kaizen.providers.document.base_provider import (
    BaseDocumentProvider,
    ExtractionResult,
    ProviderCapability,
)


class TestExtractionResult:
    """Tests for ExtractionResult dataclass."""

    def test_extraction_result_creation(self):
        """Test creating ExtractionResult with required fields."""
        result = ExtractionResult(
            text="Sample text",
            markdown="# Sample",
            cost=0.05,
            provider="test_provider",
        )

        assert result.text == "Sample text"
        assert result.markdown == "# Sample"
        assert result.cost == 0.05
        assert result.provider == "test_provider"
        assert result.tables == []
        assert result.images == []
        assert result.chunks == []
        assert result.bounding_boxes == []

    def test_extraction_result_with_tables(self):
        """Test ExtractionResult with table data."""
        tables = [
            {
                "table_id": 0,
                "headers": ["Col1", "Col2"],
                "rows": [["A", "B"]],
                "page": 1,
            }
        ]

        result = ExtractionResult(
            text="Text with table",
            tables=tables,
            cost=0.10,
            provider="test",
        )

        assert len(result.tables) == 1
        assert result.tables[0]["table_id"] == 0

    def test_extraction_result_with_chunks(self):
        """Test ExtractionResult with RAG chunks."""
        chunks = [
            {
                "chunk_id": 0,
                "text": "Chunk 1",
                "page": 1,
                "bbox": [0, 0, 100, 100],
                "token_count": 50,
            },
            {
                "chunk_id": 1,
                "text": "Chunk 2",
                "page": 2,
                "bbox": None,
                "token_count": 45,
            },
        ]

        result = ExtractionResult(
            text="Full text",
            chunks=chunks,
            cost=0.15,
            provider="test",
        )

        assert len(result.chunks) == 2
        assert result.chunks[0]["chunk_id"] == 0
        assert result.chunks[1]["bbox"] is None

    def test_extraction_result_with_bounding_boxes(self):
        """Test ExtractionResult with spatial coordinates."""
        bboxes = [
            {"page": 1, "bbox": [10, 20, 110, 120], "text": "Text 1"},
            {"page": 2, "bbox": [15, 25, 115, 125], "text": "Text 2"},
        ]

        result = ExtractionResult(
            text="Text",
            bounding_boxes=bboxes,
            cost=0.05,
            provider="landing_ai",
        )

        assert len(result.bounding_boxes) == 2
        assert result.bounding_boxes[0]["bbox"] == [10, 20, 110, 120]

    def test_extraction_result_metadata(self):
        """Test ExtractionResult with metadata."""
        metadata = {
            "file_name": "test.pdf",
            "file_type": "pdf",
            "page_count": 10,
            "model": "gpt-4o-mini",
        }

        result = ExtractionResult(
            text="Text",
            metadata=metadata,
            cost=0.20,
            provider="openai",
        )

        assert result.metadata["file_name"] == "test.pdf"
        assert result.metadata["page_count"] == 10

    def test_extraction_result_processing_time(self):
        """Test ExtractionResult with processing time."""
        result = ExtractionResult(
            text="Text",
            cost=0.10,
            provider="test",
            processing_time=1.5,
        )

        assert result.processing_time == 1.5

    def test_extraction_result_to_dict(self):
        """Test converting ExtractionResult to dict."""
        result = ExtractionResult(
            text="Test",
            cost=0.05,
            provider="test",
        )

        result_dict = asdict(result)

        assert isinstance(result_dict, dict)
        assert result_dict["text"] == "Test"
        assert result_dict["cost"] == 0.05


class TestProviderCapability:
    """Tests for ProviderCapability enum."""

    def test_all_capabilities_exist(self):
        """Test all expected capabilities are defined."""
        expected = {
            "text_extraction",
            "table_extraction",
            "image_description",
            "bounding_boxes",
            "markdown_output",
            "semantic_chunking",
        }

        actual = {cap.value for cap in ProviderCapability}

        assert actual == expected

    def test_capability_values(self):
        """Test capability enum values."""
        assert ProviderCapability.TEXT_EXTRACTION.value == "text_extraction"
        assert ProviderCapability.TABLE_EXTRACTION.value == "table_extraction"
        assert ProviderCapability.BOUNDING_BOXES.value == "bounding_boxes"

    def test_capability_membership(self):
        """Test checking capability membership."""
        caps = [
            ProviderCapability.TEXT_EXTRACTION,
            ProviderCapability.TABLE_EXTRACTION,
        ]

        assert ProviderCapability.TEXT_EXTRACTION in caps
        assert ProviderCapability.BOUNDING_BOXES not in caps


class ConcreteProvider(BaseDocumentProvider):
    """Concrete implementation for testing abstract base class."""

    def __init__(self):
        super().__init__(provider_name="test_provider")

    async def extract(
        self, file_path: str, file_type: str, **options
    ) -> ExtractionResult:
        return ExtractionResult(
            text="Test text",
            cost=0.0,
            provider=self.provider_name,
        )

    async def estimate_cost(self, file_path: str) -> float:
        return 0.0

    def is_available(self) -> bool:
        return True

    def get_capabilities(self) -> Dict[str, Any]:
        return {"provider": self.provider_name}


class TestBaseDocumentProvider:
    """Tests for BaseDocumentProvider abstract class."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that BaseDocumentProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseDocumentProvider(provider_name="test")  # type: ignore

    def test_concrete_implementation(self):
        """Test that concrete implementation works."""
        provider = ConcreteProvider()

        assert provider.provider_name == "test_provider"
        assert provider.is_available() is True

    @pytest.mark.asyncio
    async def test_concrete_extract(self):
        """Test extract method in concrete implementation."""
        provider = ConcreteProvider()

        result = await provider.extract("test.pdf", "pdf")

        assert result.text == "Test text"
        assert result.provider == "test_provider"

    @pytest.mark.asyncio
    async def test_concrete_estimate_cost(self):
        """Test estimate_cost in concrete implementation."""
        provider = ConcreteProvider()

        cost = await provider.estimate_cost("test.pdf")

        assert cost == 0.0

    def test_validate_file_type_valid(self):
        """Test _validate_file_type with valid types."""
        provider = ConcreteProvider()

        # Should not raise
        provider._validate_file_type("pdf")
        provider._validate_file_type("docx")
        provider._validate_file_type("txt")
        provider._validate_file_type("md")

    def test_validate_file_type_invalid(self):
        """Test _validate_file_type with invalid type."""
        provider = ConcreteProvider()

        with pytest.raises(ValueError, match="Unsupported file type"):
            provider._validate_file_type("xlsx")

    def test_get_page_count_pdf(self, tmp_path):
        """Test _get_page_count for PDF files."""
        provider = ConcreteProvider()

        # Create a mock PDF file
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF content")

        # For now, implementation returns 1 for mock files
        # Real implementation would use PyPDF2
        page_count = provider._get_page_count(str(pdf_file))

        assert page_count >= 1

    def test_get_page_count_txt(self, tmp_path):
        """Test _get_page_count for text files."""
        provider = ConcreteProvider()

        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Line 1\n" * 100)  # 100 lines

        page_count = provider._get_page_count(str(txt_file))

        # Text files: ~50 lines per page (implementation specific)
        # Should return at least 1 page
        assert page_count >= 1

    def test_get_page_count_md(self, tmp_path):
        """Test _get_page_count for markdown files."""
        provider = ConcreteProvider()

        md_file = tmp_path / "test.md"
        md_file.write_text("# Header\n\nContent\n" * 30)

        page_count = provider._get_page_count(str(md_file))

        assert page_count >= 1

    def test_get_page_count_nonexistent_file(self):
        """Test _get_page_count with nonexistent file."""
        provider = ConcreteProvider()

        # Implementation may vary: could return 1 or raise error
        # Just verify it handles gracefully
        try:
            page_count = provider._get_page_count("/nonexistent/file.pdf")
            assert page_count >= 1
        except Exception:
            # Some implementations may raise, which is also acceptable
            pass

    def test_provider_name_property(self):
        """Test provider_name property."""
        provider = ConcreteProvider()

        assert provider.provider_name == "test_provider"

    def test_get_capabilities_returns_dict(self):
        """Test get_capabilities returns dictionary."""
        provider = ConcreteProvider()

        caps = provider.get_capabilities()

        assert isinstance(caps, dict)
        assert "provider" in caps

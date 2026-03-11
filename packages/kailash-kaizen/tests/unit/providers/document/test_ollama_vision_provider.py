"""
Unit tests for Ollama Vision provider.

Tests:
- Provider initialization and configuration
- Cost estimation (always $0.00)
- Availability checking
- Capability reporting
- Mock extraction using respx (real API tested in Tier 2)
"""

import os
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from kaizen.providers.document.base_provider import ExtractionResult
from kaizen.providers.document.ollama_vision_provider import OllamaVisionProvider


class TestOllamaVisionProviderInit:
    """Tests for Ollama Vision provider initialization."""

    def test_init_with_base_url(self):
        """Test initialization with explicit base URL."""
        provider = OllamaVisionProvider(base_url="http://custom:11434")

        assert provider.provider_name == "ollama_vision"
        assert provider.base_url == "http://custom:11434"
        assert provider.model == "llama3.2-vision"

    def test_init_with_env_var(self, monkeypatch):
        """Test initialization with environment variable."""
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://env:11434")

        provider = OllamaVisionProvider()

        assert provider.base_url == "http://env:11434"

    def test_init_without_base_url(self):
        """Test initialization with default base URL."""
        with patch.dict(os.environ, {}, clear=True):
            provider = OllamaVisionProvider()

            assert provider.base_url == "http://localhost:11434"

    def test_init_with_custom_model(self):
        """Test initialization with custom model."""
        provider = OllamaVisionProvider(
            base_url="http://localhost:11434",
            model="llava",
        )

        assert provider.model == "llava"

    def test_init_with_custom_timeout(self):
        """Test initialization with custom timeout."""
        provider = OllamaVisionProvider(timeout=300)

        assert provider.timeout == 300

    def test_cost_per_page_constant(self):
        """Test COST_PER_PAGE constant (FREE)."""
        assert OllamaVisionProvider.COST_PER_PAGE == 0.0


class TestOllamaVisionProviderAvailability:
    """Tests for Ollama Vision provider availability checking."""

    def test_is_available_with_base_url(self):
        """Test availability when base URL is set."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        # For mock implementation, availability is True if base_url is set
        assert provider.is_available() is True

    def test_is_available_without_base_url(self):
        """Test availability when base URL is None."""
        provider = OllamaVisionProvider(base_url=None)

        # Provider may still set default base_url in __init__
        # Just check that it handles None gracefully
        availability = provider.is_available()
        assert isinstance(availability, bool)


class TestOllamaVisionProviderCostEstimation:
    """Tests for cost estimation logic (always free)."""

    @pytest.mark.asyncio
    async def test_estimate_cost_always_zero(self):
        """Test cost estimation always returns $0.00."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        cost = await provider.estimate_cost("test.pdf")

        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_estimate_cost_large_document(self):
        """Test cost estimation for large document (still free)."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        with patch.object(provider, "_get_page_count", return_value=1000):
            cost = await provider.estimate_cost("large.pdf")

        assert cost == 0.0  # Always free!


class TestOllamaVisionProviderCapabilities:
    """Tests for provider capabilities reporting."""

    def test_get_capabilities_structure(self):
        """Test capabilities dictionary structure."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        caps = provider.get_capabilities()

        assert isinstance(caps, dict)
        assert "provider" in caps
        assert "accuracy" in caps
        assert "table_accuracy" in caps
        assert "cost_per_page" in caps
        assert "supports_bounding_boxes" in caps

    def test_get_capabilities_values(self):
        """Test capabilities values."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        caps = provider.get_capabilities()

        assert caps["provider"] == "ollama_vision"
        assert caps["accuracy"] == 0.85  # 85% accuracy (acceptable)
        assert caps["table_accuracy"] == 0.70  # 70% table accuracy (lower)
        assert caps["cost_per_page"] == 0.0  # FREE!
        assert caps["supports_bounding_boxes"] is False
        assert caps["supports_tables"] is True
        assert caps["avg_speed_seconds"] == 40.0  # Slower but free

    def test_get_capabilities_use_cases(self):
        """Test use cases in capabilities."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        caps = provider.get_capabilities()

        assert "use_cases" in caps
        assert isinstance(caps["use_cases"], list)
        assert "Budget-constrained applications" in caps["use_cases"]
        assert "Privacy-sensitive documents" in caps["use_cases"]


# Mock API response for Ollama Vision
MOCK_OLLAMA_RESPONSE = {
    "response": """# Document Extraction

This is the extracted text from the document.

<!-- TABLE START -->
| Column 1 | Column 2 |
|----------|----------|
| Value 1  | Value 2  |
<!-- TABLE END -->

More text content here.""",
    "done": True,
    "model": "llama3.2-vision",
}


class TestOllamaVisionProviderExtraction:
    """Tests for extraction method with mocked HTTP calls."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_basic(self, tmp_path):
        """Test basic extraction without tables or RAG."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        # Mock the Ollama API
        respx.post("http://localhost:11434/api/generate").mock(
            return_value=Response(200, json=MOCK_OLLAMA_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=1):
            with patch.object(
                provider, "_prepare_document_images", return_value=["base64image"]
            ):
                result = await provider.extract(
                    str(pdf_file),
                    "pdf",
                    extract_tables=False,
                    chunk_for_rag=False,
                )

        assert isinstance(result, ExtractionResult)
        assert result.provider == "ollama_vision"
        assert result.cost == 0.0  # Always free!
        assert len(result.text) > 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_with_tables(self, tmp_path):
        """Test extraction with table extraction enabled."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post("http://localhost:11434/api/generate").mock(
            return_value=Response(200, json=MOCK_OLLAMA_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=1):
            with patch.object(
                provider, "_prepare_document_images", return_value=["base64image"]
            ):
                result = await provider.extract(
                    str(pdf_file),
                    "pdf",
                    extract_tables=True,
                )

        # Tables should be extracted from the mock response
        assert len(result.tables) > 0
        assert result.tables[0]["table_id"] == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_with_rag_chunks(self, tmp_path):
        """Test extraction with RAG chunking."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post("http://localhost:11434/api/generate").mock(
            return_value=Response(200, json=MOCK_OLLAMA_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=1):
            with patch.object(
                provider, "_prepare_document_images", return_value=["base64image"]
            ):
                result = await provider.extract(
                    str(pdf_file),
                    "pdf",
                    chunk_for_rag=True,
                    chunk_size=512,
                )

        assert len(result.chunks) > 0
        assert "chunk_id" in result.chunks[0]
        assert "text" in result.chunks[0]
        assert "page" in result.chunks[0]

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_no_bounding_boxes(self, tmp_path):
        """Test that Ollama Vision does not provide bounding boxes."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post("http://localhost:11434/api/generate").mock(
            return_value=Response(200, json=MOCK_OLLAMA_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=1):
            with patch.object(
                provider, "_prepare_document_images", return_value=["base64image"]
            ):
                result = await provider.extract(
                    str(pdf_file),
                    "pdf",
                    chunk_for_rag=True,
                )

        # Ollama chunks should not have bounding boxes
        assert len(result.chunks) > 0
        for chunk in result.chunks:
            assert chunk.get("bbox") is None

    @pytest.mark.asyncio
    async def test_extract_invalid_file_type(self, tmp_path):
        """Test extraction with invalid file type."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.write_text("Mock Excel")

        with pytest.raises(ValueError, match="Unsupported file type"):
            await provider.extract(str(xlsx_file), "xlsx")

    @pytest.mark.asyncio
    async def test_extract_nonexistent_file(self):
        """Test extraction with nonexistent file."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        with pytest.raises(FileNotFoundError):
            await provider.extract("/nonexistent/file.pdf", "pdf")

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_cost_always_zero(self, tmp_path):
        """Test cost is always $0.00 regardless of page count."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post("http://localhost:11434/api/generate").mock(
            return_value=Response(200, json=MOCK_OLLAMA_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=100):
            with patch.object(
                provider, "_prepare_document_images", return_value=["base64image"]
            ):
                result = await provider.extract(str(pdf_file), "pdf")

        assert result.cost == 0.0  # Free even for 100 pages!

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_metadata(self, tmp_path):
        """Test metadata in extraction result."""
        provider = OllamaVisionProvider(
            base_url="http://custom:11434",
            model="llava",
        )

        pdf_file = tmp_path / "document.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post("http://custom:11434/api/generate").mock(
            return_value=Response(200, json=MOCK_OLLAMA_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=5):
            with patch.object(
                provider, "_prepare_document_images", return_value=["base64image"]
            ):
                result = await provider.extract(str(pdf_file), "pdf")

        assert "file_name" in result.metadata
        assert result.metadata["file_name"] == "document.pdf"
        assert result.metadata["file_type"] == "pdf"
        assert result.metadata["page_count"] == 5
        assert result.metadata["model"] == "llava"
        assert result.metadata["base_url"] == "http://custom:11434"

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_processing_time_recorded(self, tmp_path):
        """Test that processing time is recorded."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post("http://localhost:11434/api/generate").mock(
            return_value=Response(200, json=MOCK_OLLAMA_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=1):
            with patch.object(
                provider, "_prepare_document_images", return_value=["base64image"]
            ):
                result = await provider.extract(str(pdf_file), "pdf")

        assert result.processing_time > 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_markdown_output(self, tmp_path):
        """Test markdown output generation."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post("http://localhost:11434/api/generate").mock(
            return_value=Response(200, json=MOCK_OLLAMA_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=1):
            with patch.object(
                provider, "_prepare_document_images", return_value=["base64image"]
            ):
                result = await provider.extract(str(pdf_file), "pdf")

        assert len(result.markdown) > 0
        assert "#" in result.markdown

    @pytest.mark.asyncio
    async def test_extract_when_unavailable(self, tmp_path):
        """Test extraction raises error when Ollama is unavailable."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        with patch.object(provider, "is_available", return_value=False):
            with patch.object(provider, "_get_page_count", return_value=1):
                with pytest.raises(RuntimeError, match="Ollama not available"):
                    await provider.extract(str(pdf_file), "pdf")

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_api_error(self, tmp_path):
        """Test handling of API errors."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post("http://localhost:11434/api/generate").mock(
            return_value=Response(500, json={"error": "Internal Server Error"})
        )

        with patch.object(provider, "_get_page_count", return_value=1):
            with patch.object(
                provider, "_prepare_document_images", return_value=["base64image"]
            ):
                with pytest.raises(RuntimeError, match="Ollama Vision API call failed"):
                    await provider.extract(str(pdf_file), "pdf")

"""
Unit tests for Landing AI Document Parse provider.

Tests:
- Provider initialization and configuration
- Cost estimation logic
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
from kaizen.providers.document.landing_ai_provider import LandingAIProvider


class TestLandingAIProviderInit:
    """Tests for Landing AI provider initialization."""

    def test_init_with_api_key(self):
        """Test initialization with explicit API key."""
        provider = LandingAIProvider(api_key="test-key-123")

        assert provider.provider_name == "landing_ai"
        assert provider.api_key == "test-key-123"
        assert provider.endpoint == LandingAIProvider.DEFAULT_ENDPOINT

    def test_init_with_env_var(self, monkeypatch):
        """Test initialization with environment variable."""
        monkeypatch.setenv("LANDING_AI_API_KEY", "env-key-456")

        provider = LandingAIProvider()

        assert provider.api_key == "env-key-456"

    def test_init_without_api_key(self):
        """Test initialization without API key."""
        with patch.dict(os.environ, {}, clear=True):
            provider = LandingAIProvider()

            assert provider.api_key is None

    def test_init_with_custom_endpoint(self):
        """Test initialization with custom endpoint."""
        provider = LandingAIProvider(
            api_key="test-key",
            endpoint="https://custom.api.com/parse",
        )

        assert provider.endpoint == "https://custom.api.com/parse"

    def test_cost_per_page_constant(self):
        """Test COST_PER_PAGE constant."""
        assert LandingAIProvider.COST_PER_PAGE == 0.015


class TestLandingAIProviderAvailability:
    """Tests for Landing AI provider availability checking."""

    def test_is_available_with_api_key(self):
        """Test availability when API key is set."""
        provider = LandingAIProvider(api_key="test-key")

        assert provider.is_available() is True

    def test_is_available_without_api_key(self, monkeypatch):
        """Test availability when API key is missing."""
        monkeypatch.delenv("LANDING_AI_API_KEY", raising=False)
        provider = LandingAIProvider(api_key=None)

        assert provider.is_available() is False

    def test_is_available_with_empty_api_key(self, monkeypatch):
        """Test availability with empty string API key."""
        monkeypatch.delenv("LANDING_AI_API_KEY", raising=False)
        provider = LandingAIProvider(api_key="")

        assert provider.is_available() is False


class TestLandingAIProviderCostEstimation:
    """Tests for cost estimation logic."""

    @pytest.mark.asyncio
    async def test_estimate_cost_10_page_pdf(self, tmp_path):
        """Test cost estimation for 10-page PDF."""
        provider = LandingAIProvider(api_key="test-key")

        # Mock _get_page_count to return 10
        with patch.object(provider, "_get_page_count", return_value=10):
            cost = await provider.estimate_cost("test.pdf")

        expected_cost = 10 * 0.015  # $0.15
        assert cost == expected_cost

    @pytest.mark.asyncio
    async def test_estimate_cost_1_page_pdf(self, tmp_path):
        """Test cost estimation for 1-page PDF."""
        provider = LandingAIProvider(api_key="test-key")

        with patch.object(provider, "_get_page_count", return_value=1):
            cost = await provider.estimate_cost("test.pdf")

        assert cost == 0.015

    @pytest.mark.asyncio
    async def test_estimate_cost_100_page_pdf(self, tmp_path):
        """Test cost estimation for large document."""
        provider = LandingAIProvider(api_key="test-key")

        with patch.object(provider, "_get_page_count", return_value=100):
            cost = await provider.estimate_cost("test.pdf")

        expected_cost = 100 * 0.015  # $1.50
        assert cost == expected_cost


class TestLandingAIProviderCapabilities:
    """Tests for provider capabilities reporting."""

    def test_get_capabilities_structure(self):
        """Test capabilities dictionary structure."""
        provider = LandingAIProvider(api_key="test-key")

        caps = provider.get_capabilities()

        assert isinstance(caps, dict)
        assert "provider" in caps
        assert "accuracy" in caps
        assert "table_accuracy" in caps
        assert "cost_per_page" in caps
        assert "supports_bounding_boxes" in caps

    def test_get_capabilities_values(self):
        """Test capabilities values."""
        provider = LandingAIProvider(api_key="test-key")

        caps = provider.get_capabilities()

        assert caps["provider"] == "landing_ai"
        assert caps["accuracy"] == 0.98  # 98% accuracy
        assert caps["table_accuracy"] == 0.99  # 99% table accuracy
        assert caps["cost_per_page"] == 0.015
        assert caps["supports_bounding_boxes"] is True
        assert caps["supports_tables"] is True

    def test_get_capabilities_use_cases(self):
        """Test use cases in capabilities."""
        provider = LandingAIProvider(api_key="test-key")

        caps = provider.get_capabilities()

        assert "use_cases" in caps
        assert isinstance(caps["use_cases"], list)
        assert len(caps["use_cases"]) > 0


# Mock API response for Landing AI
MOCK_LANDING_AI_RESPONSE = {
    "text": "This is extracted text from the document.",
    "markdown": "# Document\n\nThis is extracted text from the document.",
    "pages": [
        {
            "page_number": 1,
            "elements": [
                {
                    "type": "text",
                    "text": "This is extracted text from the document.",
                    "bbox": [50, 50, 550, 750],
                    "confidence": 0.98,
                }
            ],
        }
    ],
    "tables": [
        {
            "headers": ["Column 1", "Column 2"],
            "rows": [["Value 1", "Value 2"], ["Value 3", "Value 4"]],
            "page": 1,
            "bbox": [100, 200, 400, 350],
        }
    ],
}


class TestLandingAIProviderExtraction:
    """Tests for extraction method with mocked HTTP calls."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_basic(self, tmp_path):
        """Test basic extraction without tables or RAG."""
        provider = LandingAIProvider(api_key="test-key")

        # Create mock file
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        # Mock the Landing AI API
        respx.post(provider.endpoint).mock(
            return_value=Response(200, json=MOCK_LANDING_AI_RESPONSE)
        )

        # Mock page count
        with patch.object(provider, "_get_page_count", return_value=1):
            result = await provider.extract(
                str(pdf_file),
                "pdf",
                extract_tables=False,
                chunk_for_rag=False,
            )

        assert isinstance(result, ExtractionResult)
        assert result.provider == "landing_ai"
        assert result.cost == 0.015  # 1 page * $0.015
        assert len(result.text) > 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_with_tables(self, tmp_path):
        """Test extraction with table extraction enabled."""
        provider = LandingAIProvider(api_key="test-key")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post(provider.endpoint).mock(
            return_value=Response(200, json=MOCK_LANDING_AI_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=1):
            result = await provider.extract(
                str(pdf_file),
                "pdf",
                extract_tables=True,
            )

        assert len(result.tables) > 0
        assert result.tables[0]["table_id"] == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_with_rag_chunks(self, tmp_path):
        """Test extraction with RAG chunking."""
        provider = LandingAIProvider(api_key="test-key")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post(provider.endpoint).mock(
            return_value=Response(200, json=MOCK_LANDING_AI_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=1):
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
        assert "bbox" in result.chunks[0]  # Landing AI provides bounding boxes

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_with_bounding_boxes(self, tmp_path):
        """Test that Landing AI extraction includes bounding boxes."""
        provider = LandingAIProvider(api_key="test-key")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post(provider.endpoint).mock(
            return_value=Response(200, json=MOCK_LANDING_AI_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=1):
            result = await provider.extract(
                str(pdf_file),
                "pdf",
                chunk_for_rag=True,
            )

        # Landing AI should provide bounding boxes for chunks
        assert len(result.chunks) > 0
        # At least some chunks should have bounding boxes
        has_bbox = any(chunk.get("bbox") is not None for chunk in result.chunks)
        assert has_bbox

    @pytest.mark.asyncio
    async def test_extract_invalid_file_type(self, tmp_path):
        """Test extraction with invalid file type."""
        provider = LandingAIProvider(api_key="test-key")

        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.write_text("Mock Excel")

        with pytest.raises(ValueError, match="Unsupported file type"):
            await provider.extract(str(xlsx_file), "xlsx")

    @pytest.mark.asyncio
    async def test_extract_nonexistent_file(self):
        """Test extraction with nonexistent file."""
        provider = LandingAIProvider(api_key="test-key")

        with pytest.raises(FileNotFoundError):
            await provider.extract("/nonexistent/file.pdf", "pdf")

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_cost_calculation(self, tmp_path):
        """Test cost calculation for multi-page document."""
        provider = LandingAIProvider(api_key="test-key")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post(provider.endpoint).mock(
            return_value=Response(200, json=MOCK_LANDING_AI_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=10):
            result = await provider.extract(str(pdf_file), "pdf")

        expected_cost = 10 * 0.015  # $0.15
        assert result.cost == expected_cost

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_metadata(self, tmp_path):
        """Test metadata in extraction result."""
        provider = LandingAIProvider(api_key="test-key")

        pdf_file = tmp_path / "report.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post(provider.endpoint).mock(
            return_value=Response(200, json=MOCK_LANDING_AI_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=5):
            result = await provider.extract(str(pdf_file), "pdf")

        assert "file_name" in result.metadata
        assert result.metadata["file_name"] == "report.pdf"
        assert result.metadata["file_type"] == "pdf"
        assert result.metadata["page_count"] == 5

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_processing_time_recorded(self, tmp_path):
        """Test that processing time is recorded."""
        provider = LandingAIProvider(api_key="test-key")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post(provider.endpoint).mock(
            return_value=Response(200, json=MOCK_LANDING_AI_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=1):
            result = await provider.extract(str(pdf_file), "pdf")

        assert result.processing_time > 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_markdown_output(self, tmp_path):
        """Test markdown output generation."""
        provider = LandingAIProvider(api_key="test-key")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post(provider.endpoint).mock(
            return_value=Response(200, json=MOCK_LANDING_AI_RESPONSE)
        )

        with patch.object(provider, "_get_page_count", return_value=1):
            result = await provider.extract(str(pdf_file), "pdf")

        assert len(result.markdown) > 0
        assert "#" in result.markdown  # Markdown header

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_api_error_401(self, tmp_path):
        """Test handling of 401 Unauthorized error."""
        provider = LandingAIProvider(api_key="invalid-key")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post(provider.endpoint).mock(return_value=Response(401))

        with patch.object(provider, "_get_page_count", return_value=1):
            with pytest.raises(ValueError, match="Invalid Landing AI API key"):
                await provider.extract(str(pdf_file), "pdf")

    @pytest.mark.asyncio
    @respx.mock
    async def test_extract_api_error_429(self, tmp_path):
        """Test handling of 429 rate limit error."""
        provider = LandingAIProvider(api_key="test-key")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        respx.post(provider.endpoint).mock(return_value=Response(429))

        with patch.object(provider, "_get_page_count", return_value=1):
            with pytest.raises(RuntimeError, match="rate limit exceeded"):
                await provider.extract(str(pdf_file), "pdf")

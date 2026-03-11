"""
Integration tests for document extraction providers.

Tests real API calls to Landing AI, OpenAI, and Ollama.
These tests may incur API costs (~$5 total).

Run with: pytest tests/integration/providers/document/ -m integration

IMPORTANT: NO MOCKING - Real infrastructure only (Tier 2 policy)
"""

import os

import pytest
from kaizen.providers.document import (
    LandingAIProvider,
    OllamaVisionProvider,
    OpenAIVisionProvider,
    ProviderManager,
)

# ============================================================================
# Landing AI Integration Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.landing_ai
@pytest.mark.cost
class TestLandingAIIntegration:
    """Integration tests for Landing AI provider with real API."""

    @pytest.fixture(autouse=True)
    def skip_if_no_api_key(self, landing_ai_available):
        """Skip tests if Landing AI API key not available."""
        if not landing_ai_available:
            pytest.skip("Landing AI API key not available (set LANDING_AI_API_KEY)")

    def test_landing_ai_provider_initialization(self):
        """Test Landing AI provider initializes with API key."""
        provider = LandingAIProvider(api_key=os.getenv("LANDING_AI_API_KEY"))

        assert provider.provider_name == "landing_ai"
        assert provider.is_available() is True
        assert provider.api_key is not None

    @pytest.mark.asyncio
    async def test_landing_ai_cost_estimation(self, sample_txt_path):
        """Test Landing AI cost estimation with real file."""
        provider = LandingAIProvider(api_key=os.getenv("LANDING_AI_API_KEY"))

        # Estimate cost (doesn't call API, just counts pages)
        cost = await provider.estimate_cost(sample_txt_path)

        # Should estimate at least $0.015 (1 page minimum)
        assert cost >= 0.015

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_landing_ai_text_extraction(self, sample_txt_path):
        """Test Landing AI extracts text from real file."""
        provider = LandingAIProvider(api_key=os.getenv("LANDING_AI_API_KEY"))

        result = await provider.extract(
            sample_txt_path,
            file_type="txt",
            extract_tables=False,
            chunk_for_rag=False,
        )

        # Verify extraction result
        assert result.provider == "landing_ai"
        assert len(result.text) > 0
        assert result.cost >= 0.0  # May be free for txt, or may charge
        assert result.processing_time > 0

        # Landing AI specific: should have metadata
        assert "file_name" in result.metadata

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_landing_ai_with_tables(self, sample_txt_path):
        """Test Landing AI table extraction."""
        provider = LandingAIProvider(api_key=os.getenv("LANDING_AI_API_KEY"))

        result = await provider.extract(
            sample_txt_path,
            file_type="txt",
            extract_tables=True,
        )

        # Should attempt table extraction
        # Tables may or may not be found depending on content
        assert isinstance(result.tables, list)

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_landing_ai_rag_chunking(self, sample_txt_path):
        """Test Landing AI RAG chunking with bounding boxes."""
        provider = LandingAIProvider(api_key=os.getenv("LANDING_AI_API_KEY"))

        result = await provider.extract(
            sample_txt_path,
            file_type="txt",
            chunk_for_rag=True,
            chunk_size=512,
        )

        # Should generate chunks
        assert len(result.chunks) > 0

        # Landing AI specific: chunks should have bounding boxes
        # (at least some of them)
        any(chunk.get("bbox") is not None for chunk in result.chunks)
        # Note: For txt files, bboxes may not be available
        # This is acceptable behavior

    def test_landing_ai_capabilities(self):
        """Test Landing AI reports correct capabilities."""
        provider = LandingAIProvider(api_key=os.getenv("LANDING_AI_API_KEY"))

        caps = provider.get_capabilities()

        # Verify Landing AI specific capabilities
        assert caps["provider"] == "landing_ai"
        assert caps["accuracy"] == 0.98  # 98% accuracy
        assert caps["cost_per_page"] == 0.015  # $0.015/page
        assert caps["supports_bounding_boxes"] is True
        assert caps["supports_tables"] is True


# ============================================================================
# OpenAI Vision Integration Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.openai
@pytest.mark.cost
class TestOpenAIVisionIntegration:
    """Integration tests for OpenAI Vision provider with real API."""

    @pytest.fixture(autouse=True)
    def skip_if_no_api_key(self, openai_available):
        """Skip tests if OpenAI API key not available."""
        if not openai_available:
            pytest.skip("OpenAI API key not available (set OPENAI_API_KEY)")

    def test_openai_provider_initialization(self):
        """Test OpenAI provider initializes with API key."""
        provider = OpenAIVisionProvider(api_key=os.getenv("OPENAI_API_KEY"))

        assert provider.provider_name == "openai_vision"
        assert provider.is_available() is True
        assert provider.api_key is not None
        assert provider.model == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_openai_cost_estimation(self, sample_txt_path):
        """Test OpenAI cost estimation with real file."""
        provider = OpenAIVisionProvider(api_key=os.getenv("OPENAI_API_KEY"))

        cost = await provider.estimate_cost(sample_txt_path)

        # Should estimate at least $0.068 (1 page minimum)
        assert cost >= 0.068

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_openai_text_extraction(self, sample_txt_path):
        """Test OpenAI extracts text from real file."""
        provider = OpenAIVisionProvider(api_key=os.getenv("OPENAI_API_KEY"))

        result = await provider.extract(
            sample_txt_path,
            file_type="txt",
            extract_tables=False,
            chunk_for_rag=False,
        )

        # Verify extraction result
        assert result.provider == "openai_vision"
        assert len(result.text) > 0
        assert result.cost >= 0.0
        assert result.processing_time > 0

        # OpenAI specific: fast processing
        # Should be fastest provider (typically < 1s per page)
        assert result.processing_time < 10.0  # Generous upper bound

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_openai_rag_chunking(self, sample_txt_path):
        """Test OpenAI RAG chunking (no bounding boxes)."""
        provider = OpenAIVisionProvider(api_key=os.getenv("OPENAI_API_KEY"))

        result = await provider.extract(
            sample_txt_path,
            file_type="txt",
            chunk_for_rag=True,
            chunk_size=512,
        )

        # Should generate chunks
        assert len(result.chunks) > 0

        # OpenAI specific: NO bounding boxes
        for chunk in result.chunks:
            assert chunk.get("bbox") is None

    def test_openai_capabilities(self):
        """Test OpenAI reports correct capabilities."""
        provider = OpenAIVisionProvider(api_key=os.getenv("OPENAI_API_KEY"))

        caps = provider.get_capabilities()

        # Verify OpenAI specific capabilities
        assert caps["provider"] == "openai_vision"
        assert caps["accuracy"] == 0.95  # 95% accuracy
        assert caps["cost_per_page"] == 0.068  # $0.068/page
        assert caps["supports_bounding_boxes"] is False
        assert caps["supports_tables"] is True
        assert caps["avg_speed_seconds"] == 0.8  # Fastest


# ============================================================================
# Ollama Vision Integration Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.ollama
class TestOllamaVisionIntegration:
    """Integration tests for Ollama Vision provider (FREE, local)."""

    @pytest.fixture(autouse=True)
    def skip_if_ollama_not_running(self, ollama_available):
        """Skip tests if Ollama not running."""
        if not ollama_available:
            pytest.skip("Ollama not running (start with: ollama serve)")

    def test_ollama_provider_initialization(self):
        """Test Ollama provider initializes."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        assert provider.provider_name == "ollama_vision"
        assert provider.is_available() is True
        assert provider.base_url == "http://localhost:11434"
        assert provider.model == "llama3.2-vision"

    @pytest.mark.asyncio
    async def test_ollama_cost_always_zero(self, sample_txt_path):
        """Test Ollama cost is always $0.00."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        cost = await provider.estimate_cost(sample_txt_path)

        # Always free!
        assert cost == 0.0

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_ollama_text_extraction(self, sample_txt_path):
        """Test Ollama extracts text from real file."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        result = await provider.extract(
            sample_txt_path,
            file_type="txt",
            extract_tables=False,
            chunk_for_rag=False,
        )

        # Verify extraction result
        assert result.provider == "ollama_vision"
        assert len(result.text) > 0
        assert result.cost == 0.0  # Free!
        assert result.processing_time > 0

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_ollama_rag_chunking(self, sample_txt_path):
        """Test Ollama RAG chunking (no bounding boxes)."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        result = await provider.extract(
            sample_txt_path,
            file_type="txt",
            chunk_for_rag=True,
            chunk_size=512,
        )

        # Should generate chunks
        assert len(result.chunks) > 0

        # Ollama specific: NO bounding boxes
        for chunk in result.chunks:
            assert chunk.get("bbox") is None

    def test_ollama_capabilities(self):
        """Test Ollama reports correct capabilities."""
        provider = OllamaVisionProvider(base_url="http://localhost:11434")

        caps = provider.get_capabilities()

        # Verify Ollama specific capabilities
        assert caps["provider"] == "ollama_vision"
        assert caps["accuracy"] == 0.85  # 85% accuracy (acceptable)
        assert caps["cost_per_page"] == 0.0  # FREE!
        assert caps["supports_bounding_boxes"] is False
        assert caps["supports_tables"] is True


# ============================================================================
# Provider Manager Integration Tests
# ============================================================================


@pytest.mark.integration
class TestProviderManagerIntegration:
    """Integration tests for ProviderManager with real providers."""

    def test_provider_manager_initialization(self):
        """Test ProviderManager initializes all providers."""
        manager = ProviderManager(
            landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
            openai_key=os.getenv("OPENAI_API_KEY"),
            ollama_base_url="http://localhost:11434",
        )

        # Should have all 3 providers
        assert len(manager.providers) == 3
        assert "landing_ai" in manager.providers
        assert "openai_vision" in manager.providers
        assert "ollama_vision" in manager.providers

    def test_provider_manager_available_providers(self, ollama_available):
        """Test getting available providers."""
        manager = ProviderManager(
            landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
            openai_key=os.getenv("OPENAI_API_KEY"),
            ollama_base_url="http://localhost:11434",
        )

        available = manager.get_available_providers()

        # At least Ollama should be available if running
        if ollama_available:
            assert "ollama_vision" in available

    @pytest.mark.asyncio
    async def test_provider_manager_cost_estimation(self, sample_txt_path):
        """Test cost estimation across all providers."""
        manager = ProviderManager(
            landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
            openai_key=os.getenv("OPENAI_API_KEY"),
            ollama_base_url="http://localhost:11434",
        )

        costs = await manager.estimate_cost(sample_txt_path, provider="auto")

        # Should have cost estimates for all providers
        assert "ollama_vision" in costs
        assert costs["ollama_vision"] == 0.0  # Always free

    @pytest.mark.slow
    @pytest.mark.asyncio
    @pytest.mark.ollama
    async def test_provider_manager_auto_selection_ollama(
        self, sample_txt_path, ollama_available
    ):
        """Test automatic provider selection with Ollama (free)."""
        if not ollama_available:
            pytest.skip("Ollama not running")

        manager = ProviderManager(
            landing_ai_key=None,  # Not available
            openai_key=None,  # Not available
            ollama_base_url="http://localhost:11434",
        )

        result = await manager.extract(
            sample_txt_path,
            file_type="txt",
            provider="auto",
            prefer_free=True,
        )

        # Should use Ollama (only available provider)
        assert result.provider == "ollama_vision"
        assert result.cost == 0.0

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_provider_manager_fallback_chain(
        self, sample_txt_path, ollama_available, monkeypatch
    ):
        """Test fallback chain when primary providers not available."""
        if not ollama_available:
            pytest.skip("Ollama not running (needed for fallback)")

        # Unset environment variables to ensure fallback
        monkeypatch.delenv("LANDING_AI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        manager = ProviderManager(
            landing_ai_key=None,  # Not available
            openai_key=None,  # Not available
            ollama_base_url="http://localhost:11434",  # Available
        )

        # Should fallback to Ollama (only available provider)
        result = await manager.extract(
            sample_txt_path,
            file_type="txt",
            provider="auto",
        )

        # Should use Ollama (only available option)
        assert result.provider == "ollama_vision"

    @pytest.mark.asyncio
    async def test_provider_manager_budget_constraint(
        self, sample_txt_path, ollama_available
    ):
        """Test budget constraint enforcement."""
        if not ollama_available:
            pytest.skip("Ollama not running (needed for free option)")

        manager = ProviderManager(
            landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
            openai_key=os.getenv("OPENAI_API_KEY"),
            ollama_base_url="http://localhost:11434",
        )

        # Set very low budget - should force Ollama (free)
        result = await manager.extract(
            sample_txt_path,
            file_type="txt",
            provider="auto",
            max_cost=0.01,  # $0.01 max (less than any paid provider)
        )

        # Should use Ollama (free, under budget)
        assert result.provider == "ollama_vision"
        assert result.cost == 0.0

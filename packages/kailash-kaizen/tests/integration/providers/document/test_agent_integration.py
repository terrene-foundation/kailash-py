"""
Integration tests for DocumentExtractionAgent with real providers.

Tests the full agent with real API calls.
These tests may incur API costs (~$2-3 total).

Run with: pytest tests/integration/providers/document/test_agent_integration.py -m integration

IMPORTANT: NO MOCKING - Real infrastructure only (Tier 2 policy)
"""

import os

import pytest
from kaizen.agents.multi_modal import DocumentExtractionAgent, DocumentExtractionConfig


@pytest.mark.integration
class TestDocumentExtractionAgentIntegration:
    """Integration tests for DocumentExtractionAgent."""

    def test_agent_initialization_with_api_keys(self):
        """Test agent initializes with provider API keys."""
        config = DocumentExtractionConfig(
            provider="auto",
            landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
            openai_key=os.getenv("OPENAI_API_KEY"),
            ollama_base_url="http://localhost:11434",
        )

        agent = DocumentExtractionAgent(config=config)

        # Should have provider manager configured
        assert agent.provider_manager is not None
        assert len(agent.provider_manager.providers) == 3

    @pytest.mark.slow
    @pytest.mark.ollama
    def test_agent_extract_with_ollama(self, sample_txt_path, ollama_available):
        """Test agent extraction with Ollama (free, local)."""
        if not ollama_available:
            pytest.skip("Ollama not running")

        config = DocumentExtractionConfig(
            provider="ollama_vision",  # Force Ollama
            ollama_base_url="http://localhost:11434",
        )

        agent = DocumentExtractionAgent(config=config)

        # Extract document
        result = agent.extract(sample_txt_path, file_type="txt")

        # Verify result
        assert "text" in result
        assert len(result["text"]) > 0
        assert result["provider"] == "ollama_vision"
        assert result["cost"] == 0.0  # Free!
        assert "processing_time" in result

    @pytest.mark.slow
    @pytest.mark.ollama
    def test_agent_extract_with_rag_chunking(self, sample_txt_path, ollama_available):
        """Test agent RAG chunking with Ollama."""
        if not ollama_available:
            pytest.skip("Ollama not running")

        config = DocumentExtractionConfig(
            provider="ollama_vision",
            ollama_base_url="http://localhost:11434",
            chunk_for_rag=True,
            chunk_size=512,
        )

        agent = DocumentExtractionAgent(config=config)

        # Extract with chunking
        result = agent.extract(sample_txt_path, file_type="txt")

        # Verify chunks
        assert "chunks" in result
        assert len(result["chunks"]) > 0

        # Verify chunk structure
        for chunk in result["chunks"]:
            assert "chunk_id" in chunk
            assert "text" in chunk
            assert "page" in chunk

    @pytest.mark.slow
    @pytest.mark.ollama
    def test_agent_estimate_cost(self, sample_txt_path):
        """Test agent cost estimation."""
        config = DocumentExtractionConfig(
            provider="auto",
            landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
            openai_key=os.getenv("OPENAI_API_KEY"),
            ollama_base_url="http://localhost:11434",
        )

        agent = DocumentExtractionAgent(config=config)

        # Estimate costs
        costs = agent.estimate_cost(sample_txt_path)

        # Should have estimates for available providers
        assert isinstance(costs, dict)
        assert "ollama_vision" in costs
        assert costs["ollama_vision"] == 0.0  # Free

    @pytest.mark.slow
    @pytest.mark.ollama
    def test_agent_prefer_free(self, sample_txt_path, ollama_available):
        """Test agent prefers free provider when requested."""
        if not ollama_available:
            pytest.skip("Ollama not running")

        config = DocumentExtractionConfig(
            provider="auto",
            prefer_free=True,  # Should use Ollama
            landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
            openai_key=os.getenv("OPENAI_API_KEY"),
            ollama_base_url="http://localhost:11434",
        )

        agent = DocumentExtractionAgent(config=config)

        # Extract (should use Ollama)
        result = agent.extract(sample_txt_path, file_type="txt")

        # Should use free provider
        assert result["provider"] == "ollama_vision"
        assert result["cost"] == 0.0

    @pytest.mark.slow
    @pytest.mark.ollama
    def test_agent_budget_constraint(self, sample_txt_path, ollama_available):
        """Test agent respects budget constraints."""
        if not ollama_available:
            pytest.skip("Ollama not running")

        config = DocumentExtractionConfig(
            provider="auto",
            max_cost_per_doc=0.01,  # Very low budget
            landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
            openai_key=os.getenv("OPENAI_API_KEY"),
            ollama_base_url="http://localhost:11434",
        )

        agent = DocumentExtractionAgent(config=config)

        # Extract (should use free provider to stay under budget)
        result = agent.extract(sample_txt_path, file_type="txt")

        # Should stay under budget
        assert result["cost"] <= 0.01

    @pytest.mark.ollama
    def test_agent_get_available_providers(self, ollama_available):
        """Test agent reports available providers."""
        config = DocumentExtractionConfig(
            provider="auto",
            landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
            openai_key=os.getenv("OPENAI_API_KEY"),
            ollama_base_url="http://localhost:11434",
        )

        agent = DocumentExtractionAgent(config=config)

        # Get available providers
        available = agent.get_available_providers()

        # At least Ollama should be available if running
        if ollama_available:
            assert "ollama_vision" in available

    def test_agent_get_provider_capabilities(self):
        """Test agent reports provider capabilities."""
        config = DocumentExtractionConfig(
            provider="auto",
            landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
            openai_key=os.getenv("OPENAI_API_KEY"),
            ollama_base_url="http://localhost:11434",
        )

        agent = DocumentExtractionAgent(config=config)

        # Get capabilities
        caps = agent.get_provider_capabilities()

        # Should have all providers
        assert "landing_ai" in caps
        assert "openai_vision" in caps
        assert "ollama_vision" in caps

        # Verify key capability fields
        assert caps["landing_ai"]["accuracy"] == 0.98
        assert caps["openai_vision"]["cost_per_page"] == 0.068
        assert caps["ollama_vision"]["cost_per_page"] == 0.0


@pytest.mark.integration
@pytest.mark.cost
@pytest.mark.landing_ai
@pytest.mark.slow
class TestDocumentExtractionAgentLandingAI:
    """Integration tests with Landing AI (may incur costs)."""

    @pytest.fixture(autouse=True)
    def skip_if_no_api_key(self, landing_ai_available):
        """Skip tests if Landing AI API key not available."""
        if not landing_ai_available:
            pytest.skip("Landing AI API key not available")

    def test_agent_extract_with_landing_ai(self, sample_txt_path):
        """Test agent extraction with Landing AI."""
        config = DocumentExtractionConfig(
            provider="landing_ai",  # Force Landing AI
            landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
        )

        agent = DocumentExtractionAgent(config=config)

        # Extract document
        result = agent.extract(sample_txt_path, file_type="txt")

        # Verify result
        assert result["provider"] == "landing_ai"
        assert len(result["text"]) > 0
        assert result["cost"] >= 0.0

    def test_agent_landing_ai_with_tables(self, sample_txt_path):
        """Test agent table extraction with Landing AI."""
        config = DocumentExtractionConfig(
            provider="landing_ai",
            landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
            extract_tables=True,
        )

        agent = DocumentExtractionAgent(config=config)

        # Extract with tables
        result = agent.extract(sample_txt_path, file_type="txt", extract_tables=True)

        # Should attempt table extraction
        assert "tables" in result
        assert isinstance(result["tables"], list)


@pytest.mark.integration
@pytest.mark.cost
@pytest.mark.openai
@pytest.mark.slow
class TestDocumentExtractionAgentOpenAI:
    """Integration tests with OpenAI (may incur costs)."""

    @pytest.fixture(autouse=True)
    def skip_if_no_api_key(self, openai_available):
        """Skip tests if OpenAI API key not available."""
        if not openai_available:
            pytest.skip("OpenAI API key not available")

    def test_agent_extract_with_openai(self, sample_txt_path):
        """Test agent extraction with OpenAI."""
        config = DocumentExtractionConfig(
            provider="openai_vision",  # Force OpenAI
            openai_key=os.getenv("OPENAI_API_KEY"),
        )

        agent = DocumentExtractionAgent(config=config)

        # Extract document
        result = agent.extract(sample_txt_path, file_type="txt")

        # Verify result
        assert result["provider"] == "openai_vision"
        assert len(result["text"]) > 0
        assert result["cost"] >= 0.0

        # OpenAI is fastest - should be quick
        assert result["processing_time"] < 10.0

    def test_agent_openai_rag_chunking(self, sample_txt_path):
        """Test agent RAG chunking with OpenAI (no bounding boxes)."""
        config = DocumentExtractionConfig(
            provider="openai_vision",
            openai_key=os.getenv("OPENAI_API_KEY"),
            chunk_for_rag=True,
            chunk_size=512,
        )

        agent = DocumentExtractionAgent(config=config)

        # Extract with chunking
        result = agent.extract(sample_txt_path, file_type="txt")

        # Verify chunks (no bounding boxes for OpenAI)
        assert len(result["chunks"]) > 0
        for chunk in result["chunks"]:
            assert chunk.get("bbox") is None  # OpenAI doesn't provide bboxes

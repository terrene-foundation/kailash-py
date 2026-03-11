"""
Unit tests for ProviderManager.

Tests:
- Provider initialization and registry
- Automatic provider selection
- Fallback chain logic
- Budget constraint enforcement
- Cost estimation across providers
- Manual provider selection
"""

from unittest.mock import patch

import pytest
from kaizen.providers.document.base_provider import ExtractionResult
from kaizen.providers.document.provider_manager import ProviderManager


class TestProviderManagerInit:
    """Tests for ProviderManager initialization."""

    def test_init_with_all_keys(self):
        """Test initialization with all provider keys."""
        manager = ProviderManager(
            landing_ai_key="landing-key",
            openai_key="openai-key",
            ollama_base_url="http://localhost:11434",
        )

        assert "landing_ai" in manager.providers
        assert "openai_vision" in manager.providers
        assert "ollama_vision" in manager.providers
        assert len(manager.providers) == 3

    def test_init_without_keys(self):
        """Test initialization without API keys."""
        manager = ProviderManager()

        # Should still create all providers (they handle missing keys)
        assert len(manager.providers) == 3

    def test_init_with_custom_fallback_chain(self):
        """Test initialization with custom fallback chain."""
        custom_chain = ["ollama_vision", "landing_ai", "openai_vision"]

        manager = ProviderManager(default_fallback_chain=custom_chain)

        assert manager.default_fallback_chain == custom_chain

    def test_default_fallback_chain_quality_first(self):
        """Test default fallback chain prioritizes quality."""
        manager = ProviderManager()

        # Default: Landing AI (98%) → OpenAI (95%) → Ollama (85%)
        assert manager.default_fallback_chain == [
            "landing_ai",
            "openai_vision",
            "ollama_vision",
        ]


class TestProviderManagerAvailability:
    """Tests for checking provider availability."""

    def test_get_available_providers_all_configured(self):
        """Test getting available providers when all are configured."""
        manager = ProviderManager(
            landing_ai_key="key1",
            openai_key="key2",
            ollama_base_url="http://localhost:11434",
        )

        available = manager.get_available_providers()

        # All providers should be available
        assert "landing_ai" in available
        assert "openai_vision" in available
        assert "ollama_vision" in available

    def test_get_available_providers_partial(self):
        """Test getting available providers with some missing."""
        manager = ProviderManager(
            landing_ai_key=None,  # Not available
            openai_key="openai-key",  # Available
            ollama_base_url="http://localhost:11434",  # Available
        )

        available = manager.get_available_providers()

        assert "openai_vision" in available
        assert "ollama_vision" in available


class TestProviderManagerCapabilities:
    """Tests for getting provider capabilities."""

    def test_get_provider_capabilities_structure(self):
        """Test capabilities dictionary structure."""
        manager = ProviderManager()

        caps = manager.get_provider_capabilities()

        assert isinstance(caps, dict)
        assert "landing_ai" in caps
        assert "openai_vision" in caps
        assert "ollama_vision" in caps

    def test_get_provider_capabilities_values(self):
        """Test capabilities for each provider."""
        manager = ProviderManager()

        caps = manager.get_provider_capabilities()

        # Landing AI
        assert caps["landing_ai"]["accuracy"] == 0.98
        assert caps["landing_ai"]["cost_per_page"] == 0.015

        # OpenAI
        assert caps["openai_vision"]["accuracy"] == 0.95
        assert caps["openai_vision"]["cost_per_page"] == 0.068

        # Ollama
        assert caps["ollama_vision"]["accuracy"] == 0.85
        assert caps["ollama_vision"]["cost_per_page"] == 0.0


class TestProviderManagerCostEstimation:
    """Tests for cost estimation across providers."""

    @pytest.mark.asyncio
    async def test_estimate_cost_all_providers(self, tmp_path):
        """Test estimating cost for all providers."""
        manager = ProviderManager()

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        # Mock _estimate_provider_cost for each provider
        with patch.object(manager, "_estimate_provider_cost") as mock_estimate:
            mock_estimate.side_effect = [0.15, 0.68, 0.0]  # 10 pages

            costs = await manager.estimate_cost(str(pdf_file), provider="auto")

        assert "landing_ai" in costs
        assert "openai_vision" in costs
        assert "ollama_vision" in costs
        assert costs["ollama_vision"] == 0.0  # Free

    @pytest.mark.asyncio
    async def test_estimate_cost_single_provider(self, tmp_path):
        """Test estimating cost for single provider."""
        manager = ProviderManager()

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        with patch.object(manager, "_estimate_provider_cost", return_value=0.15):
            costs = await manager.estimate_cost(str(pdf_file), provider="landing_ai")

        assert list(costs.keys()) == ["landing_ai"]
        assert costs["landing_ai"] == 0.15

    @pytest.mark.asyncio
    async def test_estimate_cost_with_recommendation(self, tmp_path):
        """Test cost estimation includes recommendation."""
        manager = ProviderManager()

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        with patch.object(manager, "_estimate_provider_cost") as mock_estimate:
            mock_estimate.side_effect = [0.15, 0.68, 0.0]

            costs = await manager.estimate_cost(
                str(pdf_file), provider="auto", prefer_free=True
            )

        # Should recommend Ollama (free)
        assert costs["recommended"] == "ollama_vision"

    @pytest.mark.asyncio
    async def test_estimate_cost_recommend_cheapest(self, tmp_path):
        """Test recommendation for cheapest available provider."""
        manager = ProviderManager()

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        with patch.object(manager, "_estimate_provider_cost") as mock_estimate:
            mock_estimate.side_effect = [0.15, 0.68, 0.0]

            costs = await manager.estimate_cost(
                str(pdf_file), provider="auto", prefer_free=False
            )

        # Should recommend Ollama (cheapest)
        assert costs["recommended"] == "ollama_vision"


class TestProviderManagerExtraction:
    """Tests for document extraction with provider selection."""

    @pytest.mark.asyncio
    async def test_extract_manual_provider_selection(self, tmp_path):
        """Test extraction with manual provider selection."""
        manager = ProviderManager(landing_ai_key="key")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        mock_result = ExtractionResult(
            text="Extracted",
            cost=0.015,
            provider="landing_ai",
        )

        with patch.object(
            manager, "_extract_with_provider", return_value=mock_result
        ) as mock_extract:
            result = await manager.extract(str(pdf_file), provider="landing_ai")

        assert result.provider == "landing_ai"
        mock_extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_auto_selection_success(self, tmp_path):
        """Test auto-selection with first provider succeeding."""
        manager = ProviderManager()

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        mock_result = ExtractionResult(
            text="Extracted",
            cost=0.015,
            provider="landing_ai",
        )

        with patch.object(manager, "_extract_with_provider", return_value=mock_result):
            result = await manager.extract(str(pdf_file), provider="auto")

        assert result.provider == "landing_ai"

    @pytest.mark.asyncio
    async def test_extract_auto_selection_fallback(self, tmp_path):
        """Test auto-selection with fallback to second provider."""
        manager = ProviderManager()

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        openai_result = ExtractionResult(
            text="Extracted",
            cost=0.068,
            provider="openai_vision",
        )

        async def mock_extract_side_effect(*args, **kwargs):
            if kwargs.get("provider_name") == "landing_ai":
                raise Exception("Landing AI failed")
            return openai_result

        with patch.object(
            manager, "_extract_with_provider", side_effect=mock_extract_side_effect
        ):
            result = await manager.extract(str(pdf_file), provider="auto")

        assert result.provider == "openai_vision"

    @pytest.mark.asyncio
    async def test_extract_all_providers_fail(self, tmp_path):
        """Test extraction when all providers fail."""
        manager = ProviderManager()

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        with patch.object(
            manager,
            "_extract_with_provider",
            side_effect=Exception("Provider failed"),
        ):
            with pytest.raises(RuntimeError, match="All providers failed"):
                await manager.extract(str(pdf_file), provider="auto")

    @pytest.mark.asyncio
    async def test_extract_with_budget_constraint(self, tmp_path):
        """Test extraction with budget constraint."""
        manager = ProviderManager()

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        ollama_result = ExtractionResult(
            text="Extracted",
            cost=0.0,
            provider="ollama_vision",
        )

        async def mock_cost_estimator(provider_name, file_path):
            costs = {"landing_ai": 0.15, "openai_vision": 0.68, "ollama_vision": 0.0}
            return costs.get(provider_name, 0.0)

        with patch.object(
            manager, "_estimate_provider_cost", side_effect=mock_cost_estimator
        ):
            with patch.object(
                manager, "_extract_with_provider", return_value=ollama_result
            ):
                result = await manager.extract(
                    str(pdf_file), provider="auto", max_cost=0.05
                )

        # Should use Ollama (only provider under $0.05)
        assert result.provider == "ollama_vision"

    @pytest.mark.asyncio
    async def test_extract_prefer_free(self, tmp_path):
        """Test extraction with prefer_free=True."""
        manager = ProviderManager()

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        ollama_result = ExtractionResult(
            text="Extracted",
            cost=0.0,
            provider="ollama_vision",
        )

        with patch.object(
            manager, "_extract_with_provider", return_value=ollama_result
        ):
            result = await manager.extract(
                str(pdf_file), provider="auto", prefer_free=True
            )

        assert result.provider == "ollama_vision"

    @pytest.mark.asyncio
    async def test_extract_invalid_provider(self, tmp_path):
        """Test extraction with invalid provider name."""
        manager = ProviderManager()

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        with pytest.raises(ValueError, match="Unknown provider"):
            await manager.extract(str(pdf_file), provider="invalid_provider")

    @pytest.mark.asyncio
    async def test_extract_unavailable_provider(self, tmp_path, monkeypatch):
        """Test extraction with unavailable provider."""
        monkeypatch.delenv("LANDING_AI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        manager = ProviderManager(landing_ai_key=None)  # Not configured

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("Mock PDF")

        with pytest.raises(RuntimeError, match="not available"):
            await manager.extract(str(pdf_file), provider="landing_ai")


class TestProviderManagerSelectionChain:
    """Tests for provider selection chain logic."""

    def test_selection_chain_prefer_free(self):
        """Test selection chain with prefer_free=True."""
        manager = ProviderManager()

        chain = manager._get_selection_chain(prefer_free=True, max_cost=None)

        # Ollama first (free)
        assert chain[0] == "ollama_vision"
        assert "landing_ai" in chain
        assert "openai_vision" in chain

    def test_selection_chain_budget_constrained(self):
        """Test selection chain with budget constraint."""
        manager = ProviderManager()

        chain = manager._get_selection_chain(prefer_free=False, max_cost=0.10)

        # Landing AI first (cheapest paid: $0.015)
        assert chain[0] == "landing_ai"
        assert chain[1] == "ollama_vision"

    def test_selection_chain_quality_first(self):
        """Test default selection chain prioritizes quality."""
        manager = ProviderManager()

        chain = manager._get_selection_chain(prefer_free=False, max_cost=None)

        # Landing AI (98%) → OpenAI (95%) → Ollama (85%)
        assert chain == ["landing_ai", "openai_vision", "ollama_vision"]

    def test_selection_chain_with_custom_fallback(self):
        """Test selection chain uses custom fallback order."""
        custom_chain = ["openai_vision", "landing_ai", "ollama_vision"]
        manager = ProviderManager(default_fallback_chain=custom_chain)

        chain = manager._get_selection_chain(prefer_free=False, max_cost=None)

        assert chain == custom_chain

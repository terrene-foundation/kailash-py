"""
Provider manager for automatic selection and fallback handling.

The ProviderManager orchestrates multiple document extraction providers with:
- Automatic provider selection (quality, cost, availability)
- Fallback chain: Landing AI → OpenAI → Ollama
- Budget constraint enforcement
- Cost-aware provider switching
- Manual provider override

Selection Modes:
- auto: Best available provider (quality-first)
- manual: Specific provider by name
- prefer_free: Use Ollama if available, otherwise cheapest
- budget_constrained: Stay within cost limits

Example:
    >>> manager = ProviderManager()
    >>>
    >>> # Auto-select best provider
    >>> result = await manager.extract("report.pdf")
    >>> print(f"Used: {result.provider}")  # "landing_ai"
    >>>
    >>> # Prefer free provider
    >>> result = await manager.extract("report.pdf", prefer_free=True)
    >>> print(f"Used: {result.provider}")  # "ollama_vision"
    >>>
    >>> # Budget constraint
    >>> result = await manager.extract("report.pdf", max_cost=0.05)
    >>> print(f"Cost: ${result.cost:.3f}")  # Under $0.05
"""

import logging
from typing import Any, Dict, List, Optional

from kaizen.providers.document.base_provider import (
    BaseDocumentProvider,
    ExtractionResult,
)
from kaizen.providers.document.landing_ai_provider import LandingAIProvider
from kaizen.providers.document.ollama_vision_provider import OllamaVisionProvider
from kaizen.providers.document.openai_vision_provider import OpenAIVisionProvider

logger = logging.getLogger(__name__)


class ProviderManager:
    """
    Manager for automatic provider selection and fallback handling.

    The ProviderManager coordinates multiple document extraction providers
    and handles automatic selection based on quality, cost, and availability.

    Features:
    - Automatic provider selection (quality-first by default)
    - Fallback chain: Landing AI → OpenAI → Ollama
    - Budget constraint enforcement
    - Cost-aware provider switching
    - Manual provider override

    Example:
        >>> manager = ProviderManager(
        ...     landing_ai_key="...",
        ...     openai_key="...",
        ...     ollama_base_url="http://localhost:11434"
        ... )
        >>>
        >>> # Auto-select best available
        >>> result = await manager.extract("report.pdf")
        >>>
        >>> # Prefer free provider
        >>> result = await manager.extract("report.pdf", prefer_free=True)
        >>>
        >>> # Budget constraint
        >>> result = await manager.extract("report.pdf", max_cost=0.10)
        >>>
        >>> # Manual selection
        >>> result = await manager.extract("report.pdf", provider="ollama_vision")
    """

    def __init__(
        self,
        landing_ai_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
        default_fallback_chain: Optional[List[str]] = None,
    ):
        """
        Initialize provider manager with provider credentials.

        Args:
            landing_ai_key: Landing AI API key
            openai_key: OpenAI API key
            ollama_base_url: Ollama API base URL
            default_fallback_chain: Default fallback order
                                   (default: ["landing_ai", "openai_vision", "ollama_vision"])
        """
        # Initialize providers
        self.providers: Dict[str, BaseDocumentProvider] = {
            "landing_ai": LandingAIProvider(api_key=landing_ai_key),
            "openai_vision": OpenAIVisionProvider(api_key=openai_key),
            "ollama_vision": OllamaVisionProvider(base_url=ollama_base_url),
        }

        # Default fallback chain: quality-first
        self.default_fallback_chain = default_fallback_chain or [
            "landing_ai",
            "openai_vision",
            "ollama_vision",
        ]

        logger.info("ProviderManager initialized with 3 providers")

    async def extract(
        self,
        file_path: str,
        file_type: str = "pdf",
        provider: str = "auto",
        prefer_free: bool = False,
        max_cost: Optional[float] = None,
        fallback_chain: Optional[List[str]] = None,
        **options,
    ) -> ExtractionResult:
        """
        Extract document content with automatic provider selection.

        Args:
            file_path: Path to document file
            file_type: File type (pdf, docx, txt, md)
            provider: Provider name or "auto" for automatic selection
            prefer_free: Prefer free providers (Ollama) when available
            max_cost: Maximum cost in USD (enforce budget)
            fallback_chain: Custom fallback order (overrides default)
            **options: Extraction options (extract_tables, chunk_for_rag, etc.)

        Returns:
            ExtractionResult from successful provider

        Raises:
            RuntimeError: If all providers fail or cost exceeds budget

        Example:
            >>> # Auto-select (quality-first)
            >>> result = await manager.extract("report.pdf")
            >>>
            >>> # Prefer free (Ollama)
            >>> result = await manager.extract("report.pdf", prefer_free=True)
            >>>
            >>> # Budget constraint
            >>> result = await manager.extract("report.pdf", max_cost=0.05)
            >>>
            >>> # Manual selection
            >>> result = await manager.extract("report.pdf", provider="landing_ai")
        """
        # Manual provider selection
        if provider != "auto":
            return await self._extract_with_provider(
                provider_name=provider,
                file_path=file_path,
                file_type=file_type,
                **options,
            )

        # Automatic provider selection with fallback
        chain = fallback_chain or self._get_selection_chain(prefer_free, max_cost)

        logger.info(f"Attempting extraction with fallback chain: {chain}")

        errors = []
        for provider_name in chain:
            try:
                # Check budget before attempting
                if max_cost is not None:
                    estimated_cost = await self._estimate_provider_cost(
                        provider_name, file_path
                    )
                    if estimated_cost > max_cost:
                        logger.info(
                            f"Skipping {provider_name}: "
                            f"estimated ${estimated_cost:.3f} > budget ${max_cost:.3f}"
                        )
                        continue

                # Attempt extraction
                result = await self._extract_with_provider(
                    provider_name=provider_name,
                    file_path=file_path,
                    file_type=file_type,
                    **options,
                )

                logger.info(
                    f"Successfully extracted with {provider_name} "
                    f"(cost: ${result.cost:.3f})"
                )

                return result

            except Exception as e:
                error_msg = f"{provider_name} failed: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)
                continue

        # All providers failed
        raise RuntimeError(
            f"All providers failed to extract document. Errors: {'; '.join(errors)}"
        )

    async def estimate_cost(
        self,
        file_path: str,
        provider: str = "auto",
        prefer_free: bool = False,
    ) -> Dict[str, float]:
        """
        Estimate extraction cost across all providers.

        Args:
            file_path: Path to document file
            provider: Provider name or "auto" for all
            prefer_free: Include preferred provider recommendation

        Returns:
            Dict mapping provider names to estimated costs

        Example:
            >>> costs = await manager.estimate_cost("report.pdf")
            >>> print(f"Landing AI: ${costs['landing_ai']:.3f}")
            >>> print(f"OpenAI: ${costs['openai_vision']:.3f}")
            >>> print(f"Ollama: ${costs['ollama_vision']:.3f}")  # $0.00
        """
        if provider != "auto":
            cost = await self._estimate_provider_cost(provider, file_path)
            return {provider: cost}

        # Estimate all providers
        costs = {}
        for provider_name in self.providers.keys():
            try:
                cost = await self._estimate_provider_cost(provider_name, file_path)
                costs[provider_name] = cost
            except Exception as e:
                logger.warning(f"Cost estimation failed for {provider_name}: {e}")
                costs[provider_name] = None

        # Add recommendation
        if prefer_free:
            costs["recommended"] = "ollama_vision"
        else:
            # Recommend available and cheapest
            available_costs = {k: v for k, v in costs.items() if v is not None}
            if available_costs:
                cheapest = min(available_costs.items(), key=lambda x: x[1])
                costs["recommended"] = cheapest[0]

        return costs

    def get_available_providers(self) -> List[str]:
        """
        Get list of available providers (properly configured).

        Returns:
            List of available provider names

        Example:
            >>> available = manager.get_available_providers()
            >>> print(f"Available: {', '.join(available)}")
        """
        available = []
        for name, provider in self.providers.items():
            if provider.is_available():
                available.append(name)
        return available

    def get_provider_capabilities(self) -> Dict[str, Dict[str, Any]]:
        """
        Get capabilities for all providers.

        Returns:
            Dict mapping provider names to capability dicts

        Example:
            >>> caps = manager.get_provider_capabilities()
            >>> for provider, info in caps.items():
            ...     print(f"{provider}: {info['accuracy']} accuracy, ${info['cost_per_page']:.3f}/page")
        """
        return {
            name: provider.get_capabilities()
            for name, provider in self.providers.items()
        }

    async def _extract_with_provider(
        self,
        provider_name: str,
        file_path: str,
        file_type: str,
        **options,
    ) -> ExtractionResult:
        """Extract document using specific provider."""
        provider = self.providers.get(provider_name)

        if not provider:
            raise ValueError(
                f"Unknown provider: {provider_name}. "
                f"Available: {list(self.providers.keys())}"
            )

        if not provider.is_available():
            raise RuntimeError(
                f"Provider {provider_name} not available. "
                "Check configuration (API keys, Ollama running, etc.)"
            )

        return await provider.extract(file_path, file_type, **options)

    async def _estimate_provider_cost(
        self, provider_name: str, file_path: str
    ) -> float:
        """Estimate cost for specific provider."""
        provider = self.providers.get(provider_name)

        if not provider:
            raise ValueError(f"Unknown provider: {provider_name}")

        return await provider.estimate_cost(file_path)

    def _get_selection_chain(
        self, prefer_free: bool, max_cost: Optional[float]
    ) -> List[str]:
        """
        Get provider selection chain based on preferences.

        Args:
            prefer_free: Prefer free providers (Ollama first)
            max_cost: Maximum cost constraint

        Returns:
            Ordered list of provider names to try
        """
        if prefer_free:
            # Free-first: Ollama → Landing AI → OpenAI
            return ["ollama_vision", "landing_ai", "openai_vision"]

        if max_cost is not None:
            # Cost-constrained: cheapest first
            # Landing AI ($0.015) → Ollama ($0.00) → OpenAI ($0.068)
            return ["landing_ai", "ollama_vision", "openai_vision"]

        # Default: quality-first
        # Landing AI (98%) → OpenAI (95%) → Ollama (85%)
        return self.default_fallback_chain

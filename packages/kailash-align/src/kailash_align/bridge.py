# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""KaizenModelBridge: connect fine-tuned models to Kaizen Delegate.

Factory for creating Kaizen Delegates that use fine-tuned local models
deployed via Ollama or vLLM. Uses only PUBLIC Delegate APIs -- no
modifications to Delegate or adapter classes needed (R1-11).

NOTE (R2-04): Delegate's budget_usd tracking uses cloud API pricing.
Local models (Ollama/vLLM) have $0/token cost. If budget_usd is set
on a governed Delegate, the budget is never consumed. Use max_turns
or max_tokens for execution bounds on local models instead.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Optional

from kailash_align.exceptions import AlignmentError

logger = logging.getLogger(__name__)

__all__ = ["KaizenModelBridge", "BridgeConfig", "BridgeNotReadyError"]


class BridgeNotReadyError(AlignmentError):
    """Raised when the bridge cannot connect to the deployed model."""

    pass


@dataclass(frozen=True)
class BridgeConfig:
    """Configuration for KaizenModelBridge.

    Args:
        ollama_host: Ollama server URL.
        vllm_endpoint: vLLM OpenAI-compatible API endpoint.
        default_strategy: Force a specific strategy ('ollama' or 'vllm').
            None = auto-detect.
    """

    ollama_host: str = "http://localhost:11434"
    vllm_endpoint: Optional[str] = None
    default_strategy: Optional[str] = None


class KaizenModelBridge:
    """Factory for creating Kaizen Delegates that use fine-tuned local models.

    The bridge looks up deployed adapters in AdapterRegistry and constructs
    Delegate instances with the correct adapter (OllamaStreamAdapter or
    OpenAIStreamAdapter) and model string.

    This is a convenience factory, not a new adapter. It uses existing
    public APIs from kaizen_agents.delegate and kaizen_agents.delegate.adapters.

    NOTE (R2-04): Delegate's budget_usd tracking uses cloud API pricing.
    Local models (Ollama/vLLM) have $0/token cost. If budget_usd is set
    on a governed Delegate, the budget is never consumed. Use max_turns
    or max_tokens for execution bounds on local models instead.

    Args:
        adapter_registry: AdapterRegistry for looking up deployed adapters.
        config: BridgeConfig with endpoint configuration.
    """

    def __init__(
        self, adapter_registry: Any, config: Optional[BridgeConfig] = None
    ) -> None:
        self._registry = adapter_registry
        self._config = config or BridgeConfig()

    async def create_delegate(
        self,
        adapter_name: str,
        version: Optional[str] = None,
        strategy: Optional[str] = None,
        delegate_kwargs: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Create a Kaizen Delegate for a deployed fine-tuned model.

        Args:
            adapter_name: Name of adapter in registry.
            version: Specific version (None = latest).
            strategy: 'ollama' or 'vllm'. None = auto-detect via resolve_strategy().
            delegate_kwargs: Additional kwargs passed to Delegate constructor
                (e.g., tools, system_prompt, max_turns, max_tokens).

        Returns:
            Configured Delegate instance ready for use.

        Raises:
            BridgeNotReadyError: If model is not deployed or endpoint not reachable.
        """
        from kaizen_agents import Delegate

        adapter_version = await self._registry.get_adapter(adapter_name, version)
        strategy = strategy or await self.resolve_strategy(adapter_version)
        delegate_config = self._build_delegate_config(adapter_version, strategy)

        kwargs = {**delegate_config, **(delegate_kwargs or {})}
        delegate = Delegate(**kwargs)

        logger.info(
            "Created Delegate for adapter %s v%s via %s strategy",
            adapter_name,
            adapter_version.version,
            strategy,
        )
        return delegate

    async def get_delegate_config(
        self,
        adapter_name: str,
        version: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get Delegate constructor arguments without creating the Delegate.

        Useful for inspecting the configuration before creating the Delegate,
        or for passing to other systems.

        Returns:
            dict of Delegate constructor kwargs.
        """
        adapter_version = await self._registry.get_adapter(adapter_name, version)
        strategy = strategy or await self.resolve_strategy(adapter_version)
        return self._build_delegate_config(adapter_version, strategy)

    async def resolve_strategy(self, adapter_version: Any) -> str:
        """Auto-detect serving strategy.

        Priority:
        1. If config.default_strategy is set, use it.
        2. If adapter has GGUF path and Ollama is available, use 'ollama'.
        3. If config.vllm_endpoint is set and reachable, use 'vllm'.
        4. Raise BridgeNotReadyError.

        R2-03: Ollama is the recommended target for Apple Silicon.
        vLLM is CUDA-only in practice.
        """
        if self._config.default_strategy:
            return self._config.default_strategy

        # Check Ollama
        if adapter_version.gguf_path:
            if self._is_ollama_available():
                return "ollama"

        # Check vLLM
        if self._config.vllm_endpoint:
            if await self._is_vllm_available():
                return "vllm"

        raise BridgeNotReadyError(
            f"Cannot determine serving strategy for adapter "
            f"'{adapter_version.adapter_name}'. "
            f"Ensure the model is deployed via Ollama or vLLM."
        )

    async def discover_deployed_models(self) -> list[dict[str, Any]]:
        """List models available in the serving infrastructure.

        Queries Ollama's /api/tags endpoint to list locally available models.

        Returns:
            List of dicts with model_name, size, modified_at, source.
        """
        models: list[dict[str, Any]] = []
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._config.ollama_host}/api/tags",
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                for model in data.get("models", []):
                    models.append(
                        {
                            "model_name": model["name"],
                            "size": model.get("size"),
                            "modified_at": model.get("modified_at"),
                            "source": "ollama",
                        }
                    )
        except Exception as exc:
            logger.warning("Failed to query Ollama: %s", exc)

        return models

    def _build_delegate_config(
        self, adapter_version: Any, strategy: str
    ) -> dict[str, Any]:
        """Build Delegate constructor kwargs for the given strategy."""
        if strategy == "ollama":
            return {
                "model": adapter_version.adapter_name,
                "adapter": "ollama",
                "adapter_kwargs": {
                    "host": self._config.ollama_host,
                },
            }
        elif strategy == "vllm":
            return {
                "model": adapter_version.adapter_name,
                "adapter": "openai",
                "adapter_kwargs": {
                    "base_url": self._config.vllm_endpoint,
                    "api_key": "not-needed",
                },
            }
        else:
            raise BridgeNotReadyError(f"Unknown strategy: {strategy}")

    def _is_ollama_available(self) -> bool:
        """Check if Ollama server is running."""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    async def _is_vllm_available(self) -> bool:
        """Check if vLLM endpoint is reachable."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._config.vllm_endpoint}/models",
                    timeout=5.0,
                )
                return resp.status_code == 200
        except Exception:
            return False

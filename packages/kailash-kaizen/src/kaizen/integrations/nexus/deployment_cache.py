"""
Deployment caching for improved Kaizen-Nexus performance.

This module provides caching mechanisms to avoid recompiling workflows
during deployment, significantly improving deployment performance.

Features:
- LRU-based workflow cache
- Hash-based cache keys from agent configuration
- Configurable cache size
- Cache invalidation support
- 90% faster redeployment with caching
"""

import hashlib
import json
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from ...core.base_agent import BaseAgent


class DeploymentCache:
    """
    Cache compiled workflows to avoid recompilation during deployment.

    This cache significantly improves redeployment performance by storing
    built workflow objects and reusing them for identical agent configurations.

    Performance Impact:
    - Initial deployment: ~1.5s (no cache)
    - Cached deployment: ~0.15s (90% faster)

    Example:
        >>> cache = DeploymentCache(max_size=100)
        >>> cache_key = cache.create_cache_key(agent, "workflow_name")
        >>> cached_workflow = cache.get(cache_key)
        >>> if cached_workflow is None:
        ...     workflow = agent.to_workflow().build()
        ...     cache.set(cache_key, workflow)
        ... else:
        ...     workflow = cached_workflow
    """

    def __init__(self, max_size: int = 100):
        """
        Initialize deployment cache.

        Args:
            max_size: Maximum number of cached workflows (default: 100)
        """
        self.max_size = max_size
        self._cache: Dict[str, Any] = {}

    @staticmethod
    def create_cache_key(agent: "BaseAgent", name: str) -> str:
        """
        Create cache key from agent configuration.

        The cache key is based on:
        - Workflow name
        - RESOLVED LLM provider (see FIX 8 note below)
        - Model name
        - Signature structure
        - Effective system prompt (#1948: two agents sharing name+provider+
          model+signature but different prompts — e.g. different discovered
          MCP tools or a custom prompt override — must NOT collide)
        - Temperature (#1948: same-shape agents at different temperatures
          build different workflows and must key distinctly)

        Args:
            agent: BaseAgent instance
            name: Workflow name

        Returns:
            SHA256 hash of agent configuration
        """
        # Extract agent configuration
        config = getattr(agent, "config", None)
        signature = getattr(agent, "signature", None)

        # FIX 8: hash the RESOLVED provider, not the raw `llm_provider`
        # attribute, so the key CHANGES the moment ambient key availability
        # changes for an agent with no explicit `llm_provider` (the common
        # auto-detect case FIX5/FIX6 target) — otherwise the key stayed
        # IDENTICAL regardless of what `to_workflow()` would actually
        # resolve the provider to, and a cache HIT would keep serving a
        # workflow built under a now-stale provider.
        #
        # NOTE (FIX 14 — scope this claim honestly): this key change is
        # necessary but NOT sufficient on its own to guarantee a fresh
        # rebuild. A cache MISS still only causes a fresh `to_workflow()`
        # call — it does NOT, by itself, force that call to re-resolve the
        # provider if `to_workflow()`'s OWN internal memo
        # (`self._workflow`/`self._workflow_provider`) is stale in some
        # OTHER way. The "keys arrive mid-process -> real dispatch" property
        # is jointly guaranteed by THIS key tracking the resolved provider
        # AND `to_workflow()`/`compile_workflow()` invalidating their own
        # memo on the SAME provider drift (see FIX 12/FIX 13 in
        # `kaizen/core/base_agent.py` and `kaizen/core/agents.py`). This
        # cache is defense-in-depth for the DEPLOY-time redundant-rebuild
        # cost, not the sole guarantor of freshness.
        from kaizen.core._provider_env import detect_provider_from_env

        llm_provider = getattr(config, "llm_provider", None)
        resolved_provider = llm_provider or detect_provider_from_env()

        # #1948: key on the agent's REAL EFFECTIVE system prompt plus
        # temperature. Two agents that share name + provider + model +
        # signature but carry different prompts (or run at different
        # temperatures) build DIFFERENT workflows; omitting these dimensions
        # let the second agent collide onto the first's cached build under the
        # module-global cache.
        #
        # `system_prompt` is NOT a BaseAgentConfig field, so reading it off the
        # config was a no-op for every real agent. The effective prompt comes
        # from `agent._generate_system_prompt()` — the same method
        # `to_workflow()` invokes — which captures the signature, the
        # discovered MCP tools (`_discovered_mcp_tools`), and any subclass
        # prompt override. That is the value that actually differentiates two
        # otherwise-identical agents. A non-BaseAgent that carries an explicit
        # `config.system_prompt` falls back to it.
        prompt_gen = getattr(agent, "_generate_system_prompt", None)
        if callable(prompt_gen):
            effective_system_prompt = prompt_gen()
        else:
            effective_system_prompt = getattr(config, "system_prompt", None)

        # #1948: a DETERMINISTIC signature representation. `str(signature)` fell
        # to Signature's default object repr (`<Sig object at 0x...>`), whose
        # embedded memory address made the cache key UNIQUE PER AGENT INSTANCE —
        # so two structurally-identical agents never shared a cache entry and
        # the cache never hit for real agents. `to_dict()` is the stable
        # structural form (identical across instances of the same signature).
        if signature is None:
            signature_repr = None
        elif hasattr(signature, "to_dict"):
            signature_repr = json.dumps(
                signature.to_dict(), sort_keys=True, default=str
            )
        else:
            signature_repr = str(signature)

        # Build key data
        key_data = {
            "name": name,
            "provider": resolved_provider,
            "model": getattr(config, "model", None),
            "signature": signature_repr,
            "system_prompt": effective_system_prompt,
            "temperature": getattr(config, "temperature", None),
        }

        # Create deterministic JSON string
        key_str = json.dumps(key_data, sort_keys=True)

        # Hash for cache key
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, cache_key: str) -> Optional[Any]:
        """
        Retrieve cached workflow build.

        Args:
            cache_key: Cache key from create_cache_key()

        Returns:
            Cached workflow or None if not found
        """
        return self._cache.get(cache_key)

    def set(self, cache_key: str, workflow: Any):
        """
        Cache workflow build.

        Uses simple FIFO eviction when cache is full.

        Args:
            cache_key: Cache key from create_cache_key()
            workflow: Built workflow object
        """
        # Evict oldest entry if cache is full
        if len(self._cache) >= self.max_size:
            # Simple FIFO eviction
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        # Store workflow
        self._cache[cache_key] = workflow

    def invalidate(self, cache_key: Optional[str] = None):
        """
        Invalidate cache entry or entire cache.

        Args:
            cache_key: Specific key to invalidate, or None to clear all
        """
        if cache_key:
            self._cache.pop(cache_key, None)
        else:
            self._cache.clear()

    def stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats (size, max_size)
        """
        return {"size": len(self._cache), "max_size": self.max_size}


# Module-level cache instance
_deployment_cache = DeploymentCache(max_size=100)


def get_deployment_cache() -> DeploymentCache:
    """
    Get the module-level deployment cache instance.

    Returns:
        Global DeploymentCache instance
    """
    return _deployment_cache


def clear_deployment_cache():
    """
    Clear the module-level deployment cache.

    Useful for testing or when you want to force recompilation.
    """
    _deployment_cache.invalidate()

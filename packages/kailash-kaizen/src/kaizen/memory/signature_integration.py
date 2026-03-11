"""
Signature system integration with enterprise memory tiers.

This module provides integration between the signature-based programming
system and the enterprise memory system for intelligent caching.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ..signatures.core import Signature
from .enterprise import EnterpriseMemorySystem

logger = logging.getLogger(__name__)


@dataclass
class SignatureCacheConfig:
    """Configuration for signature caching"""

    enable_semantic_caching: bool = True
    enable_exact_caching: bool = True
    enable_fuzzy_caching: bool = False
    default_ttl: int = 3600  # 1 hour
    max_cache_size: int = 10000
    cache_hit_threshold: int = 2  # Promote to hot after 2 hits


class SignatureMemoryIntegration:
    """Integration between signature system and memory tiers"""

    def __init__(
        self,
        memory_system: EnterpriseMemorySystem,
        config: Optional[SignatureCacheConfig] = None,
    ):
        self.memory = memory_system
        self.config = config or SignatureCacheConfig()
        self._cache_stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "semantic_hits": 0,
            "exact_hits": 0,
            "fuzzy_hits": 0,
            "cache_writes": 0,
        }

    async def get_cached_result(
        self, signature: Signature, inputs: Dict[str, Any], strategy: str = "semantic"
    ) -> Optional[Any]:
        """Retrieve cached signature result using specified caching strategy"""
        start_time = time.perf_counter()

        try:
            cache_keys = self._generate_cache_keys(signature, inputs, strategy)

            # Try cache keys in order of specificity
            for cache_key in cache_keys:
                result = await self.memory.get(cache_key)
                if result is not None:
                    self._cache_stats["cache_hits"] += 1
                    self._cache_stats[f"{strategy}_hits"] += 1

                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    logger.debug(
                        f"Cache hit for signature '{signature.name}' "
                        f"using {strategy} strategy in {elapsed_ms:.2f}ms"
                    )
                    return result

            self._cache_stats["cache_misses"] += 1
            return None

        except Exception as e:
            logger.error(
                f"Error retrieving cached result for signature '{signature.name}': {e}"
            )
            self._cache_stats["cache_misses"] += 1
            return None

    async def cache_signature_result(
        self,
        signature: Signature,
        inputs: Dict[str, Any],
        result: Any,
        strategy: str = "semantic",
        ttl: Optional[int] = None,
    ) -> bool:
        """Cache signature execution result with intelligent tier placement"""
        try:
            cache_keys = self._generate_cache_keys(signature, inputs, strategy)
            effective_ttl = ttl or self.config.default_ttl

            # Determine tier hint based on signature metadata and result characteristics
            tier_hint = self._determine_tier_hint(signature, result)

            # Cache with primary key (most specific)
            primary_key = (
                cache_keys[0]
                if cache_keys
                else self._generate_exact_key(signature, inputs)
            )

            success = await self.memory.put(
                primary_key, result, tier_hint=tier_hint, ttl=effective_ttl
            )

            if success:
                self._cache_stats["cache_writes"] += 1
                logger.debug(
                    f"Cached result for signature '{signature.name}' "
                    f"using {strategy} strategy in {tier_hint} tier"
                )

            return success

        except Exception as e:
            logger.error(f"Error caching result for signature '{signature.name}': {e}")
            return False

    def _generate_cache_keys(
        self, signature: Signature, inputs: Dict[str, Any], strategy: str
    ) -> List[str]:
        """Generate cache keys based on caching strategy"""
        keys = []

        if strategy == "exact" and self.config.enable_exact_caching:
            keys.append(self._generate_exact_key(signature, inputs))

        elif strategy == "semantic" and self.config.enable_semantic_caching:
            keys.extend(
                [
                    self._generate_semantic_key(signature, inputs),
                    self._generate_exact_key(signature, inputs),  # Fallback
                ]
            )

        elif strategy == "fuzzy" and self.config.enable_fuzzy_caching:
            keys.extend(
                [
                    self._generate_fuzzy_key(signature, inputs),
                    self._generate_semantic_key(signature, inputs),  # Fallback
                    self._generate_exact_key(signature, inputs),  # Final fallback
                ]
            )

        else:
            # Default to exact matching
            keys.append(self._generate_exact_key(signature, inputs))

        return keys

    def _generate_exact_key(self, signature: Signature, inputs: Dict[str, Any]) -> str:
        """Generate exact cache key from signature and inputs"""
        try:
            # Create deterministic hash from signature definition and inputs
            sig_data = {
                "name": signature.name,
                "inputs": (
                    sorted(signature.inputs.items())
                    if hasattr(signature, "inputs")
                    else []
                ),
                "outputs": (
                    sorted(signature.outputs.items())
                    if hasattr(signature, "outputs")
                    else []
                ),
            }
            sig_hash = hashlib.md5(
                json.dumps(sig_data, sort_keys=True).encode()
            ).hexdigest()

            # Hash inputs deterministically
            input_hash = hashlib.md5(
                json.dumps(inputs, sort_keys=True, default=str).encode()
            ).hexdigest()

            return f"sig_exact:{sig_hash}:{input_hash}"

        except Exception as e:
            logger.warning(f"Error generating exact cache key: {e}")
            # Fallback to simple string representation
            return (
                f"sig_exact:{hash(str(signature))}:{hash(str(sorted(inputs.items())))}"
            )

    def _generate_semantic_key(
        self, signature: Signature, inputs: Dict[str, Any]
    ) -> str:
        """Generate semantic cache key focusing on input semantics"""
        try:
            # Extract semantic features from inputs
            semantic_features = self._extract_semantic_features(inputs)

            # Create signature identifier
            sig_id = (
                signature.name
                if hasattr(signature, "name")
                else str(hash(str(signature)))
            )

            # Combine for semantic key
            features_hash = hashlib.md5(
                json.dumps(semantic_features, sort_keys=True).encode()
            ).hexdigest()
            return f"sig_semantic:{sig_id}:{features_hash}"

        except Exception as e:
            logger.warning(f"Error generating semantic cache key: {e}")
            return self._generate_exact_key(signature, inputs)

    def _generate_fuzzy_key(self, signature: Signature, inputs: Dict[str, Any]) -> str:
        """Generate fuzzy cache key for approximate matching"""
        try:
            # Simplify inputs for fuzzy matching
            fuzzy_inputs = self._simplify_inputs_for_fuzzy_matching(inputs)

            sig_id = (
                signature.name
                if hasattr(signature, "name")
                else str(hash(str(signature)))
            )
            fuzzy_hash = hashlib.md5(
                json.dumps(fuzzy_inputs, sort_keys=True).encode()
            ).hexdigest()

            return f"sig_fuzzy:{sig_id}:{fuzzy_hash}"

        except Exception as e:
            logger.warning(f"Error generating fuzzy cache key: {e}")
            return self._generate_semantic_key(signature, inputs)

    def _extract_semantic_features(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Extract semantic features from inputs for caching"""
        features = {}

        for key, value in inputs.items():
            if isinstance(value, str):
                # For strings, use length and word count as features
                features[f"{key}_length"] = len(value)
                features[f"{key}_words"] = len(value.split()) if value else 0
                features[f"{key}_type"] = "string"

            elif isinstance(value, (int, float)):
                # For numbers, use the value itself and its type
                features[f"{key}_value"] = value
                features[f"{key}_type"] = type(value).__name__

            elif isinstance(value, (list, tuple)):
                # For sequences, use length and element types
                features[f"{key}_length"] = len(value)
                features[f"{key}_type"] = "sequence"
                if value:
                    features[f"{key}_element_type"] = type(value[0]).__name__

            elif isinstance(value, dict):
                # For dictionaries, use key count and structure
                features[f"{key}_keys"] = sorted(value.keys())
                features[f"{key}_type"] = "dict"

            else:
                # For other types, just use the type
                features[f"{key}_type"] = type(value).__name__

        return features

    def _simplify_inputs_for_fuzzy_matching(
        self, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simplify inputs for fuzzy cache matching"""
        simplified = {}

        for key, value in inputs.items():
            if isinstance(value, str):
                # For strings, normalize case and whitespace
                simplified[key] = " ".join(value.lower().split())

            elif isinstance(value, (int, float)):
                # For numbers, round to reduce precision
                if isinstance(value, float):
                    simplified[key] = round(value, 2)
                else:
                    simplified[key] = value

            elif isinstance(value, (list, tuple)):
                # For sequences, just keep length and type info
                simplified[key] = {"type": "sequence", "length": len(value)}

            elif isinstance(value, dict):
                # For dicts, just keep structure info
                simplified[key] = {"type": "dict", "keys": sorted(value.keys())}

            else:
                # For other types, use string representation
                simplified[key] = str(type(value).__name__)

        return simplified

    def _determine_tier_hint(self, signature: Signature, result: Any) -> str:
        """Determine appropriate tier based on signature characteristics"""
        try:
            # Check signature metadata for hints
            if hasattr(signature, "metadata") and signature.metadata:
                access_freq = signature.metadata.get("access_frequency", "medium")
                computation_cost = signature.metadata.get("computation_cost", "medium")

                # High frequency or high computation cost -> hot tier
                if access_freq == "high" or computation_cost == "high":
                    return "hot"

                # Medium frequency with medium cost -> warm tier
                if access_freq == "medium" and computation_cost == "medium":
                    return "warm"

            # Check result size for tier determination
            try:
                result_size = len(str(result))
                if result_size < 1024:  # Small results in hot tier
                    return "hot"
                elif result_size < 100000:  # Medium results in warm tier
                    return "warm"
                else:  # Large results in cold tier
                    return "cold"
            except Exception as e:
                logger.debug(f"Result size calculation failed: {e}")

            # Default to warm tier
            return "warm"

        except Exception as e:
            logger.warning(f"Error determining tier hint: {e}")
            return "warm"

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get caching statistics"""
        total_requests = (
            self._cache_stats["cache_hits"] + self._cache_stats["cache_misses"]
        )
        hit_rate = (
            self._cache_stats["cache_hits"] / total_requests
            if total_requests > 0
            else 0.0
        )

        return {
            "hit_rate": hit_rate,
            "total_requests": total_requests,
            **self._cache_stats,
        }

    def reset_stats(self):
        """Reset caching statistics"""
        for key in self._cache_stats:
            self._cache_stats[key] = 0


# Global instance for easy access (will be initialized by framework)
_signature_memory_integration: Optional[SignatureMemoryIntegration] = None


def get_signature_memory_integration() -> Optional[SignatureMemoryIntegration]:
    """Get the global signature memory integration instance"""
    return _signature_memory_integration


def set_signature_memory_integration(integration: SignatureMemoryIntegration):
    """Set the global signature memory integration instance"""
    global _signature_memory_integration
    _signature_memory_integration = integration


def create_cache_key_generator(strategy: str = "semantic") -> Callable:
    """Create cache key generator function for signature optimizer"""

    def cache_key_generator(signature: Signature, inputs: Dict[str, Any]) -> str:
        integration = get_signature_memory_integration()
        if integration:
            keys = integration._generate_cache_keys(signature, inputs, strategy)
            return (
                keys[0]
                if keys
                else f"sig_{strategy}_{hash(str(signature))}_{hash(str(inputs))}"
            )
        else:
            # Fallback when integration not available
            return f"sig_{strategy}_{hash(str(signature))}_{hash(str(inputs))}"

    return cache_key_generator

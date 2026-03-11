"""
Intent Detection System for Journey Orchestration.

Provides LLM-powered intent classification with pattern matching fast-path
and result caching for performance optimization.

Components:
    - IntentClassificationSignature: Signature for LLM intent classification
    - IntentMatch: Result of intent detection
    - IntentDetector: Orchestrates pattern matching, caching, and LLM classification

Architecture:
    IntentDetector
    - Pattern Matching (Fast Path): <1ms latency
    - Cache Check: <5ms latency
    - LLM Classification (Slow Path): <200ms latency
    - Cache Storage: Store with TTL

Usage:
    from kaizen.journey.intent import IntentDetector, IntentMatch
    from kaizen.journey.transitions import IntentTrigger

    detector = IntentDetector(
        model="gpt-4o-mini",
        cache_ttl_seconds=300,
        confidence_threshold=0.7
    )

    triggers = [
        IntentTrigger(patterns=["refund", "money back"]),
        IntentTrigger(patterns=["help", "question"]),
    ]

    result = await detector.detect_intent(
        message="I want my money back",
        available_triggers=triggers,
        context={}
    )

    if result:
        print(f"Intent: {result.intent}")
        print(f"Confidence: {result.confidence}")
        print(f"Method: {result.detection_method}")

References:
    - docs/plans/03-journey/04-intent-detection.md
    - TODO-JO-003: Intent Detection System
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from kaizen.signatures import InputField, OutputField, Signature

if TYPE_CHECKING:
    from kaizen.journey.transitions import IntentTrigger

logger = logging.getLogger(__name__)


# ============================================================================
# IntentClassificationSignature (REQ-ID-004)
# ============================================================================


class IntentClassificationSignature(Signature):
    """
    Signature for LLM intent classification.

    Designed to classify user messages into intent categories with high accuracy.
    Uses Kaizen's Layer 2 signature features (__intent__, __guidelines__) for
    optimal prompt engineering.

    Inputs:
        message: The user message to classify
        available_intents: JSON list of possible intent categories
        conversation_context: Optional recent conversation context

    Outputs:
        intent: Detected intent name or "unknown"
        confidence: Confidence score from 0.0 to 1.0
        reasoning: Brief explanation of classification decision
    """

    __doc__ = """Classify the user's intent from their message.

    Analyze the message and determine which intent category best matches.
    Be precise and consider the context of the conversation.
    If no intent clearly matches, return 'unknown'.
    """

    __intent__ = "Classify user intent from message with high accuracy"

    __guidelines__ = [
        "Consider the full message context, not just keywords",
        "Match against the provided intent categories only",
        "Return 'unknown' if confidence is below threshold",
        "Explain your reasoning briefly",
    ]

    # Inputs
    message: str = InputField(description="User message to classify")
    available_intents: str = InputField(
        description="JSON list of possible intent categories"
    )
    conversation_context: str = InputField(
        description="Recent conversation context for disambiguation",
        default="",
    )

    # Outputs
    intent: str = OutputField(description="Detected intent name or 'unknown'")
    confidence: float = OutputField(description="Confidence score from 0.0 to 1.0")
    reasoning: str = OutputField(
        description="Brief explanation of classification decision"
    )


# ============================================================================
# IntentMatch (REQ-ID-005)
# ============================================================================


@dataclass
class IntentMatch:
    """
    Result of intent detection.

    Contains all information about a detected intent, including the matched
    trigger, confidence score, detection method, and caching status.

    Attributes:
        intent: Detected intent name
        confidence: Confidence score (0.0 to 1.0)
        reasoning: Explanation of classification decision
        trigger: The IntentTrigger that matched (if any)
        from_cache: Whether this result was retrieved from cache
        detection_method: How the intent was detected ("pattern", "llm", "cache")
    """

    intent: str
    confidence: float
    reasoning: str
    trigger: Optional["IntentTrigger"] = None
    from_cache: bool = False
    detection_method: str = "pattern"  # "pattern", "llm", "cache"


# ============================================================================
# IntentDetector (REQ-ID-006)
# ============================================================================


class IntentDetector:
    """
    LLM-powered intent detector with pattern matching fast-path and caching.

    Detection Flow:
    1. Pattern Matching (Fast Path): Check patterns in IntentTriggers
    2. Cache Lookup: Check if message+triggers combination is cached
    3. LLM Classification (Slow Path): Use BaseAgent with IntentClassificationSignature
    4. Cache Result: Store successful LLM results with TTL

    Performance Targets:
    - Pattern match latency: <1ms
    - Cache lookup latency: <5ms
    - LLM classification latency: <200ms
    - Cache hit rate: >80% for repeated messages

    Attributes:
        model: LLM model for classification (default: gpt-4o-mini)
        cache_ttl_seconds: Cache entry TTL (default: 300s)
        confidence_threshold: Minimum confidence for valid match (default: 0.7)
        max_cache_size: Maximum cache entries (default: 1000)

    Example:
        >>> detector = IntentDetector(
        ...     model="gpt-4o-mini",
        ...     cache_ttl_seconds=300
        ... )
        >>> triggers = [IntentTrigger(patterns=["help"])]
        >>> result = await detector.detect_intent("I need help", triggers, {})
        >>> result.detection_method
        'pattern'
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        llm_provider: str = "openai",
        cache_ttl_seconds: int = 300,
        confidence_threshold: float = 0.7,
        max_cache_size: int = 1000,
    ):
        """
        Initialize IntentDetector.

        Args:
            model: LLM model for classification
            llm_provider: LLM provider (openai, ollama, etc.)
            cache_ttl_seconds: Cache TTL in seconds
            confidence_threshold: Minimum confidence for valid match
            max_cache_size: Maximum cache entries before eviction
        """
        self.model = model
        self.llm_provider = llm_provider
        self.cache_ttl_seconds = cache_ttl_seconds
        self.confidence_threshold = confidence_threshold
        self.max_cache_size = max_cache_size

        # Cache: message hash -> (IntentMatch, timestamp)
        self._cache: Dict[str, tuple] = {}

        # Lazy-initialized agent
        self._agent: Optional[Any] = None

    async def detect_intent(
        self,
        message: str,
        available_triggers: List["IntentTrigger"],
        context: Dict[str, Any],
    ) -> Optional[IntentMatch]:
        """
        Detect intent from message.

        Order of operations:
        1. Pattern matching (fast, sync)
        2. Cache lookup
        3. LLM classification (slow, async)

        Args:
            message: User message to classify
            available_triggers: List of IntentTriggers to check
            context: Current conversation context

        Returns:
            IntentMatch if intent detected above threshold, None otherwise
        """
        # Step 1: Fast path - pattern matching
        for trigger in available_triggers:
            if trigger.evaluate(message, context):
                return IntentMatch(
                    intent=trigger.get_intent_name(),
                    confidence=1.0,
                    reasoning="Pattern match",
                    trigger=trigger,
                    from_cache=False,
                    detection_method="pattern",
                )

        # Step 2: Check cache
        cache_key = self._cache_key(message, available_triggers)
        cached = self._get_cached(cache_key)
        if cached:
            # Return copy with from_cache=True
            return IntentMatch(
                intent=cached.intent,
                confidence=cached.confidence,
                reasoning=cached.reasoning,
                trigger=cached.trigger,
                from_cache=True,
                detection_method="cache",
            )

        # Step 3: LLM classification (only triggers with use_llm_fallback)
        llm_triggers = [t for t in available_triggers if t.use_llm_fallback]
        if not llm_triggers:
            return None

        try:
            result = await self._llm_classify(message, llm_triggers, context)

            # Step 4: Cache result
            if result:
                self._cache_result(cache_key, result)

            return result
        except Exception as e:
            # LLM errors should not crash the detector
            logger.warning(f"LLM classification error: {e}")
            return None

    async def _llm_classify(
        self,
        message: str,
        triggers: List["IntentTrigger"],
        context: Dict[str, Any],
    ) -> Optional[IntentMatch]:
        """
        Use LLM for intent classification.

        Creates a BaseAgent with IntentClassificationSignature and runs
        the classification.

        Args:
            message: User message to classify
            triggers: List of IntentTriggers (with use_llm_fallback=True)
            context: Current conversation context

        Returns:
            IntentMatch if classification successful, None otherwise
        """
        from dataclasses import dataclass as dc

        from kaizen.core.base_agent import BaseAgent

        # Lazy initialize agent
        if self._agent is None:
            # Only enable async mode for OpenAI provider
            # (BaseAgentConfig validates that use_async_llm is only valid for OpenAI)
            is_openai = self.llm_provider.lower() == "openai"

            @dc
            class IntentConfig:
                llm_provider: str = self.llm_provider
                model: str = self.model
                temperature: float = 0.3  # Low temperature for classification
                use_async_llm: bool = is_openai  # Only enable async for OpenAI

            self._agent = BaseAgent(
                config=IntentConfig(),
                signature=IntentClassificationSignature(),
            )

        # Build intent list from triggers
        intent_list: List[str] = []
        trigger_map: Dict[str, "IntentTrigger"] = {}
        for t in triggers:
            for pattern in t.patterns:
                if pattern not in intent_list:
                    intent_list.append(pattern)
                    trigger_map[pattern] = t

        # Format context for prompt
        context_str = ""
        if context:
            # Only include relevant context fields (primitive types)
            relevant = {
                k: v
                for k, v in context.items()
                if isinstance(v, (str, int, float, bool))
            }
            if relevant:
                context_str = json.dumps(relevant, indent=2)

        # Execute classification
        try:
            # For providers that support async (OpenAI), use run_async
            # For other providers (Ollama), fall back to sync run in executor
            if self.llm_provider.lower() == "openai":
                result = await self._agent.run_async(
                    message=message,
                    available_intents=json.dumps(intent_list),
                    conversation_context=context_str,
                )
            else:
                # Use sync run() method for providers that don't support async
                # Run in executor to avoid blocking the event loop
                import asyncio
                import functools

                loop = asyncio.get_event_loop()
                run_func = functools.partial(
                    self._agent.run,
                    message=message,
                    available_intents=json.dumps(intent_list),
                    conversation_context=context_str,
                )
                result = await loop.run_in_executor(None, run_func)

            # Parse confidence (handle string or float)
            confidence_raw = result.get("confidence", 0.0)
            if isinstance(confidence_raw, str):
                try:
                    confidence = float(confidence_raw)
                except ValueError:
                    confidence = 0.0
            else:
                confidence = float(confidence_raw)

            detected_intent = result.get("intent", "unknown")

            if confidence >= self.confidence_threshold and detected_intent != "unknown":
                # Find matching trigger
                trigger = trigger_map.get(detected_intent)
                if trigger:
                    return IntentMatch(
                        intent=detected_intent,
                        confidence=confidence,
                        reasoning=result.get("reasoning", ""),
                        trigger=trigger,
                        from_cache=False,
                        detection_method="llm",
                    )

        except Exception as e:
            # Log error but don't fail - just return None
            logger.warning(f"Intent classification failed: {e}")

        return None

    def _cache_key(
        self,
        message: str,
        triggers: List["IntentTrigger"],
    ) -> str:
        """
        Generate cache key from message and triggers.

        The key is a hash of the normalized message and sorted patterns.

        Args:
            message: User message
            triggers: List of IntentTriggers

        Returns:
            MD5 hash string as cache key
        """
        # Normalize message
        msg_normalized = message.lower().strip()

        # Sort patterns for consistent key
        patterns_str = "|".join(sorted(p for t in triggers for p in t.patterns))

        content = f"{msg_normalized}:{patterns_str}"
        return hashlib.md5(content.encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[IntentMatch]:
        """
        Get cached result if not expired.

        Args:
            key: Cache key

        Returns:
            IntentMatch if found and not expired, None otherwise
        """
        if key not in self._cache:
            return None

        result, timestamp = self._cache[key]
        if time.time() - timestamp > self.cache_ttl_seconds:
            # Expired - remove from cache
            del self._cache[key]
            return None

        return result

    def _cache_result(self, key: str, result: IntentMatch) -> None:
        """
        Cache result with timestamp.

        Implements LRU-style eviction when cache is full.

        Args:
            key: Cache key
            result: IntentMatch to cache
        """
        # Evict oldest entries if cache full
        if len(self._cache) >= self.max_cache_size:
            oldest_key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k][1],
            )
            del self._cache[oldest_key]

        self._cache[key] = (result, time.time())

    def clear_cache(self) -> None:
        """Clear all cached results."""
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache metrics (total_entries, valid_entries, etc.)
        """
        now = time.time()

        valid_entries = sum(
            1
            for _, (_, ts) in self._cache.items()
            if now - ts <= self.cache_ttl_seconds
        )

        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "max_size": self.max_cache_size,
            "ttl_seconds": self.cache_ttl_seconds,
        }


__all__ = [
    "IntentClassificationSignature",
    "IntentMatch",
    "IntentDetector",
]

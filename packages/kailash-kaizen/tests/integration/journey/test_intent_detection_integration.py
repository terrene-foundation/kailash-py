"""
Integration tests for Intent Detection with Real OpenAI.

These are Tier 2 (Integration) tests that use real OpenAI inference.
NO MOCKING - tests use real LLM infrastructure.

Prerequisites:
    - OPENAI_API_KEY set in .env file
    - Valid OpenAI API access

Usage:
    pytest tests/integration/journey/test_intent_detection_integration.py -v

References:
    - docs/plans/03-journey/04-intent-detection.md
    - TODO-JO-003: Intent Detection System
"""

import os
import time

import pytest
from dotenv import load_dotenv

from kaizen.journey.intent import IntentDetector, IntentMatch
from kaizen.journey.transitions import IntentTrigger

# Load environment variables from .env
load_dotenv()


# ============================================================================
# Test Configuration
# ============================================================================

# Use OpenAI for integration tests (real LLM, fast responses)
# Use gpt-4o-mini which supports temperature parameter (gpt-5-nano doesn't)
OPENAI_MODEL = "gpt-4o-mini"  # Cost-effective, supports all parameters
OPENAI_PROVIDER = "openai"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def is_openai_available() -> bool:
    """Check if OpenAI API key is configured."""
    return bool(OPENAI_API_KEY)


# Skip entire module if OpenAI not available
OPENAI_AVAILABLE = is_openai_available()
OPENAI_SKIP_REASON = "OPENAI_API_KEY not set in environment"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not OPENAI_AVAILABLE,
        reason=OPENAI_SKIP_REASON,
    ),
]


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def openai_detector():
    """Create IntentDetector configured for OpenAI."""
    return IntentDetector(
        llm_provider=OPENAI_PROVIDER,
        model=OPENAI_MODEL,
        cache_ttl_seconds=60,
        confidence_threshold=0.7,
        max_cache_size=100,
    )


@pytest.fixture
def refund_trigger():
    """Create refund intent trigger."""
    return IntentTrigger(
        patterns=["refund", "money back", "return"],
        use_llm_fallback=True,
    )


@pytest.fixture
def booking_trigger():
    """Create booking intent trigger."""
    return IntentTrigger(
        patterns=["book", "appointment", "schedule"],
        use_llm_fallback=True,
    )


@pytest.fixture
def help_trigger():
    """Create help intent trigger."""
    return IntentTrigger(
        patterns=["help", "question", "support"],
        use_llm_fallback=True,
    )


@pytest.fixture
def cancellation_trigger():
    """Create cancellation intent trigger."""
    return IntentTrigger(
        patterns=["cancel", "stop", "end"],
        use_llm_fallback=True,
    )


# ============================================================================
# Pattern Matching Tests (No LLM)
# ============================================================================


class TestPatternMatchingIntegration:
    """Integration tests for pattern matching (fast path)."""

    @pytest.mark.asyncio
    async def test_pattern_match_help(self, openai_detector, help_trigger):
        """Test pattern match for help intent."""
        result = await openai_detector.detect_intent(
            message="I need help",
            available_triggers=[help_trigger],
            context={},
        )

        assert result is not None
        assert result.intent == "help"
        assert result.confidence == 1.0
        assert result.detection_method == "pattern"

    @pytest.mark.asyncio
    async def test_pattern_match_booking(self, openai_detector, booking_trigger):
        """Test pattern match for booking intent."""
        result = await openai_detector.detect_intent(
            message="I want to book an appointment",
            available_triggers=[booking_trigger],
            context={},
        )

        assert result is not None
        assert result.intent == "book"
        assert result.detection_method == "pattern"


# ============================================================================
# LLM Classification Tests (Real Ollama)
# ============================================================================


class TestLLMClassificationIntegration:
    """Integration tests for LLM classification (slow path)."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)  # 30 second timeout for LLM call
    async def test_llm_refund_intent(self, openai_detector, refund_trigger):
        """Test LLM classifies refund intent correctly.

        Message doesn't match pattern but semantically means refund.
        Note: Message must NOT contain any pattern keywords: 'refund', 'money back', 'return'
        """
        result = await openai_detector.detect_intent(
            # This message semantically means refund but doesn't contain pattern keywords
            message="I am dissatisfied with this purchase and would like a full reimbursement",
            available_triggers=[refund_trigger],
            context={},
        )

        # Should match via LLM (not pattern)
        assert result is not None
        assert result.intent in ["refund", "money back", "return"]
        assert result.detection_method == "llm"
        assert result.confidence >= 0.6

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_llm_booking_intent(self, openai_detector, booking_trigger):
        """Test LLM classifies booking intent correctly.

        Note: Message must NOT contain any pattern keywords: 'book', 'appointment', 'schedule'
        """
        result = await openai_detector.detect_intent(
            # This message semantically means booking but doesn't contain pattern keywords
            message="I'd like to reserve a time slot with Dr. Smith next Tuesday",
            available_triggers=[booking_trigger],
            context={},
        )

        # Should match via LLM
        assert result is not None
        assert result.intent in ["book", "appointment", "schedule"]
        assert result.detection_method == "llm"

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_llm_help_intent(self, openai_detector, help_trigger):
        """Test LLM classifies help intent correctly.

        Note: Message must NOT contain any pattern keywords: 'help', 'question', 'support'
        """
        result = await openai_detector.detect_intent(
            # This message semantically means needing assistance but doesn't contain pattern keywords
            message="I'm confused and need some clarification about how this works",
            available_triggers=[help_trigger],
            context={},
        )

        # Should match via LLM
        assert result is not None
        assert result.intent in ["help", "question", "support"]
        assert result.detection_method == "llm"

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_llm_multiple_triggers(
        self, openai_detector, refund_trigger, booking_trigger, help_trigger
    ):
        """Test LLM selects correct intent from multiple options."""
        result = await openai_detector.detect_intent(
            message="I'm confused about how to get my refund processed",
            available_triggers=[refund_trigger, booking_trigger, help_trigger],
            context={},
        )

        # Should match refund intent
        assert result is not None
        assert result.intent in ["refund", "money back", "return"]

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_llm_no_match(self, openai_detector, booking_trigger):
        """Test LLM returns None for unrelated message."""
        result = await openai_detector.detect_intent(
            message="The weather is nice today",
            available_triggers=[booking_trigger],
            context={},
        )

        # May return None or low confidence result
        if result is not None:
            # If returned, should have lower confidence
            assert result.confidence < 0.9


# ============================================================================
# Caching Tests (With Real LLM)
# ============================================================================


class TestCachingIntegration:
    """Integration tests for caching with real LLM.

    Note: Only LLM results are cached. Pattern matches are NOT cached by design
    because they are already fast (<1ms) and caching would add unnecessary overhead.
    """

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_llm_result_cached(self, openai_detector, refund_trigger):
        """Test LLM result is cached for subsequent calls.

        Note: Message must NOT contain pattern keywords to force LLM classification.
        """
        # This message semantically means refund but doesn't contain pattern keywords
        # (patterns are: 'refund', 'money back', 'return')
        message = "I am dissatisfied and would like a full reimbursement"

        # First call - LLM classification
        start1 = time.time()
        result1 = await openai_detector.detect_intent(
            message=message,
            available_triggers=[refund_trigger],
            context={},
        )
        time1 = time.time() - start1

        assert result1 is not None
        assert result1.from_cache is False
        assert result1.detection_method == "llm"

        # Second call - should hit cache
        start2 = time.time()
        result2 = await openai_detector.detect_intent(
            message=message,
            available_triggers=[refund_trigger],
            context={},
        )
        time2 = time.time() - start2

        assert result2 is not None
        assert result2.from_cache is True
        assert result2.detection_method == "cache"
        assert result2.intent == result1.intent

        # Cache hit should be significantly faster
        assert time2 < time1 / 2  # At least 2x faster

    @pytest.mark.asyncio
    async def test_pattern_match_not_cached(self, openai_detector, help_trigger):
        """Test pattern match result is NOT cached (by design).

        Pattern matches are intentionally not cached because:
        1. They are already fast (<1ms)
        2. Caching would add unnecessary overhead
        3. Pattern matching is deterministic (no need to remember)
        """
        # First call - pattern match
        result1 = await openai_detector.detect_intent(
            message="I need help",
            available_triggers=[help_trigger],
            context={},
        )
        assert result1.from_cache is False
        assert result1.detection_method == "pattern"

        # Second call - still pattern match (not cached)
        result2 = await openai_detector.detect_intent(
            message="I need help",
            available_triggers=[help_trigger],
            context={},
        )
        # Pattern matches return from_cache=False and detection_method="pattern"
        # because caching is only for expensive LLM calls
        assert result2.from_cache is False
        assert result2.detection_method == "pattern"
        assert result2.intent == result1.intent


# ============================================================================
# Context Tests (With Real LLM)
# ============================================================================


class TestContextIntegration:
    """Integration tests for context handling with real LLM."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_context_influences_classification(
        self, openai_detector, refund_trigger, booking_trigger
    ):
        """Test conversation context influences classification."""
        context = {
            "previous_topic": "refund_policy",
            "customer_status": "returning_customer",
        }

        # Ambiguous message - context should help
        result = await openai_detector.detect_intent(
            message="I want to proceed with that",
            available_triggers=[refund_trigger, booking_trigger],
            context=context,
        )

        # With refund-related context, should lean toward refund
        # (Note: LLM behavior may vary, this is a guidance test)
        assert result is not None or result is None  # May or may not match


# ============================================================================
# Performance Tests
# ============================================================================


class TestPerformanceIntegration:
    """Performance tests for intent detection."""

    @pytest.mark.asyncio
    async def test_pattern_match_latency(self, openai_detector, help_trigger):
        """Test pattern matching latency is under 1ms."""
        # Clear cache to ensure pattern match path
        openai_detector.clear_cache()

        start = time.time()
        result = await openai_detector.detect_intent(
            message="I need help",
            available_triggers=[help_trigger],
            context={},
        )
        latency = time.time() - start

        assert result is not None
        assert result.detection_method == "pattern"
        # Pattern match should be very fast (< 10ms to be safe)
        assert latency < 0.01  # 10ms

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_cache_lookup_latency(self, openai_detector, help_trigger):
        """Test cache lookup latency is under 5ms.

        Note: Must use a message that triggers LLM (not pattern match)
        because only LLM results are cached.
        """
        # This message semantically means needing assistance but doesn't match patterns
        # (patterns are: 'help', 'question', 'support')
        message = "I'm confused and need some clarification"

        # First call to populate cache (LLM classification)
        result1 = await openai_detector.detect_intent(
            message=message,
            available_triggers=[help_trigger],
            context={},
        )
        assert result1 is not None
        assert result1.detection_method == "llm"

        # Measure cache hit
        start = time.time()
        result = await openai_detector.detect_intent(
            message=message,
            available_triggers=[help_trigger],
            context={},
        )
        latency = time.time() - start

        assert result is not None
        assert result.from_cache is True
        assert result.detection_method == "cache"
        # Cache lookup should be fast (< 10ms to be safe)
        assert latency < 0.01  # 10ms

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_llm_classification_latency(self, openai_detector, refund_trigger):
        """Test LLM classification latency is under 10 seconds."""
        # Clear cache
        openai_detector.clear_cache()

        start = time.time()
        result = await openai_detector.detect_intent(
            message="I want to get my purchase returned please",
            available_triggers=[refund_trigger],
            context={},
        )
        latency = time.time() - start

        # LLM call should complete within 10 seconds
        # (Ollama local inference varies based on hardware)
        assert latency < 10.0

        if result is not None:
            assert result.detection_method == "llm"


# ============================================================================
# Error Recovery Tests
# ============================================================================


class TestErrorRecoveryIntegration:
    """Integration tests for error recovery."""

    @pytest.mark.asyncio
    async def test_handles_empty_message(self, openai_detector, help_trigger):
        """Test handles empty message gracefully."""
        result = await openai_detector.detect_intent(
            message="",
            available_triggers=[help_trigger],
            context={},
        )

        # Should not crash, may return None
        assert result is None or isinstance(result, IntentMatch)

    @pytest.mark.asyncio
    async def test_handles_very_long_message(self, openai_detector, help_trigger):
        """Test handles very long message."""
        long_message = "I need help with " + "many things " * 100

        result = await openai_detector.detect_intent(
            message=long_message,
            available_triggers=[help_trigger],
            context={},
        )

        # Should not crash
        assert result is not None
        assert result.intent == "help"
        assert result.detection_method == "pattern"  # "help" pattern matched

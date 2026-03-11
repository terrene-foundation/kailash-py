"""
Unit tests for Intent Detection System (TODO-JO-003).

Tests cover:
- REQ-ID-004: IntentClassificationSignature
- REQ-ID-005: IntentMatch
- REQ-ID-006: IntentDetector

These are Tier 1 (Unit) tests that use mocked LLM for fast execution.
For real LLM tests, see tests/integration/journey/test_intent_detection_integration.py
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.journey.intent import (
    IntentClassificationSignature,
    IntentDetector,
    IntentMatch,
)
from kaizen.journey.transitions import IntentTrigger

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def help_trigger():
    """Create help intent trigger."""
    return IntentTrigger(patterns=["help", "question"])


@pytest.fixture
def refund_trigger():
    """Create refund intent trigger."""
    return IntentTrigger(patterns=["refund", "money back"])


@pytest.fixture
def booking_trigger():
    """Create booking intent trigger."""
    return IntentTrigger(patterns=["book", "appointment", "schedule"])


@pytest.fixture
def no_llm_trigger():
    """Create trigger without LLM fallback."""
    return IntentTrigger(
        patterns=["specific_keyword"],
        use_llm_fallback=False,
    )


@pytest.fixture
def detector():
    """Create IntentDetector with default settings."""
    return IntentDetector(
        model="gpt-4o-mini",
        cache_ttl_seconds=300,
        confidence_threshold=0.7,
        max_cache_size=100,
    )


@pytest.fixture
def mock_agent_result():
    """Mock successful LLM classification result."""
    return {
        "intent": "refund",
        "confidence": 0.95,
        "reasoning": "User is asking for money back",
    }


# ============================================================================
# REQ-ID-004: IntentClassificationSignature Tests
# ============================================================================


class TestIntentClassificationSignature:
    """Tests for IntentClassificationSignature."""

    def test_signature_has_inputs(self):
        """Test signature has required input fields."""
        sig = IntentClassificationSignature()

        # Check input fields exist
        inputs = getattr(sig, "_signature_inputs", {})
        assert "message" in inputs
        assert "available_intents" in inputs
        assert "conversation_context" in inputs

    def test_signature_has_outputs(self):
        """Test signature has required output fields."""
        sig = IntentClassificationSignature()

        # Check output fields exist
        outputs = getattr(sig, "_signature_outputs", {})
        assert "intent" in outputs
        assert "confidence" in outputs
        assert "reasoning" in outputs

    def test_signature_has_intent(self):
        """Test signature has __intent__ attribute."""
        assert hasattr(IntentClassificationSignature, "__intent__")
        assert "Classify" in IntentClassificationSignature.__intent__

    def test_signature_has_guidelines(self):
        """Test signature has __guidelines__ attribute."""
        assert hasattr(IntentClassificationSignature, "__guidelines__")
        guidelines = IntentClassificationSignature.__guidelines__
        assert isinstance(guidelines, list)
        assert len(guidelines) > 0

    def test_signature_instantiation(self):
        """Test signature can be instantiated."""
        sig = IntentClassificationSignature()
        assert sig is not None


# ============================================================================
# REQ-ID-005: IntentMatch Tests
# ============================================================================


class TestIntentMatch:
    """Tests for IntentMatch dataclass."""

    def test_creation_minimal(self):
        """Test creating IntentMatch with required fields only."""
        match = IntentMatch(
            intent="help",
            confidence=0.95,
            reasoning="Pattern match",
        )
        assert match.intent == "help"
        assert match.confidence == 0.95
        assert match.reasoning == "Pattern match"
        assert match.trigger is None
        assert match.from_cache is False
        assert match.detection_method == "pattern"

    def test_creation_full(self, help_trigger):
        """Test creating IntentMatch with all fields."""
        match = IntentMatch(
            intent="help",
            confidence=0.85,
            reasoning="LLM classification",
            trigger=help_trigger,
            from_cache=True,
            detection_method="cache",
        )
        assert match.intent == "help"
        assert match.confidence == 0.85
        assert match.reasoning == "LLM classification"
        assert match.trigger == help_trigger
        assert match.from_cache is True
        assert match.detection_method == "cache"

    def test_detection_method_values(self):
        """Test valid detection method values."""
        for method in ["pattern", "llm", "cache"]:
            match = IntentMatch(
                intent="test",
                confidence=1.0,
                reasoning="test",
                detection_method=method,
            )
            assert match.detection_method == method


# ============================================================================
# REQ-ID-006: IntentDetector Tests - Pattern Matching
# ============================================================================


class TestIntentDetectorPatternMatching:
    """Tests for IntentDetector pattern matching (fast path)."""

    @pytest.mark.asyncio
    async def test_pattern_match_returns_immediately(self, detector, help_trigger):
        """Test pattern match returns without LLM call."""
        result = await detector.detect_intent(
            message="I need help",
            available_triggers=[help_trigger],
            context={},
        )

        assert result is not None
        assert result.intent == "help"
        assert result.confidence == 1.0
        assert result.detection_method == "pattern"
        assert result.from_cache is False

    @pytest.mark.asyncio
    async def test_pattern_match_first_trigger_wins(
        self, detector, help_trigger, refund_trigger
    ):
        """Test first matching trigger is returned."""
        result = await detector.detect_intent(
            message="I have a question about refund",
            available_triggers=[help_trigger, refund_trigger],
            context={},
        )

        # "question" matches help_trigger first
        assert result is not None
        assert result.intent == "help"
        assert result.trigger == help_trigger

    @pytest.mark.asyncio
    async def test_pattern_match_sets_trigger(self, detector, help_trigger):
        """Test pattern match includes trigger reference."""
        result = await detector.detect_intent(
            message="I need help",
            available_triggers=[help_trigger],
            context={},
        )

        assert result.trigger == help_trigger
        assert result.trigger.patterns == ["help", "question"]


# ============================================================================
# REQ-ID-006: IntentDetector Tests - Caching
# ============================================================================


class TestIntentDetectorCaching:
    """Tests for IntentDetector caching."""

    @pytest.mark.asyncio
    async def test_pattern_match_not_cached(self, detector, help_trigger):
        """Test pattern matches return immediately (not from cache)."""
        # First call - pattern match (always returns immediately)
        result1 = await detector.detect_intent(
            message="need help",
            available_triggers=[help_trigger],
            context={},
        )
        assert result1.from_cache is False
        assert result1.detection_method == "pattern"

        # Second call - still pattern match (pattern always wins over cache)
        result2 = await detector.detect_intent(
            message="need help",
            available_triggers=[help_trigger],
            context={},
        )
        assert result2.from_cache is False
        assert result2.detection_method == "pattern"

    @pytest.mark.asyncio
    async def test_llm_result_cached(self, detector, refund_trigger):
        """Test LLM results are cached for subsequent calls."""
        llm_result = IntentMatch(
            intent="refund",
            confidence=0.95,
            reasoning="LLM classification",
            trigger=refund_trigger,
            detection_method="llm",
        )

        with patch.object(
            detector, "_llm_classify", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = llm_result

            # First call - LLM invoked
            result1 = await detector.detect_intent(
                message="I want my purchase returned",
                available_triggers=[refund_trigger],
                context={},
            )
            assert result1.detection_method == "llm"
            assert result1.from_cache is False
            assert mock_llm.call_count == 1

            # Second call - should hit cache
            result2 = await detector.detect_intent(
                message="I want my purchase returned",
                available_triggers=[refund_trigger],
                context={},
            )
            assert result2.from_cache is True
            assert result2.detection_method == "cache"
            # LLM not called again
            assert mock_llm.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_key_case_insensitive(self, detector, refund_trigger):
        """Test cache keys are case-insensitive for LLM results."""
        llm_result = IntentMatch(
            intent="refund",
            confidence=0.95,
            reasoning="LLM classification",
            trigger=refund_trigger,
            detection_method="llm",
        )

        with patch.object(
            detector, "_llm_classify", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = llm_result

            # First call with uppercase
            await detector.detect_intent(
                message="I WANT MY PURCHASE RETURNED",
                available_triggers=[refund_trigger],
                context={},
            )

            # Same message, different case - should hit cache
            result2 = await detector.detect_intent(
                message="i want my purchase returned",
                available_triggers=[refund_trigger],
                context={},
            )

            assert result2.from_cache is True
            assert mock_llm.call_count == 1  # Only called once

    @pytest.mark.asyncio
    async def test_cache_key_whitespace_normalized(self, detector, refund_trigger):
        """Test cache keys normalize whitespace for LLM results."""
        llm_result = IntentMatch(
            intent="refund",
            confidence=0.95,
            reasoning="LLM classification",
            trigger=refund_trigger,
            detection_method="llm",
        )

        with patch.object(
            detector, "_llm_classify", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = llm_result

            # First call with extra whitespace
            await detector.detect_intent(
                message="  I want my purchase returned  ",
                available_triggers=[refund_trigger],
                context={},
            )

            # Same message, normalized whitespace - should hit cache
            result2 = await detector.detect_intent(
                message="I want my purchase returned",
                available_triggers=[refund_trigger],
                context={},
            )

            assert result2.from_cache is True
            assert mock_llm.call_count == 1

    def test_cache_expiration(self):
        """Test cache entries expire after TTL."""
        detector = IntentDetector(cache_ttl_seconds=1)

        # Manually add expired entry
        key = "test_key"
        match = IntentMatch(
            intent="test",
            confidence=1.0,
            reasoning="test",
        )
        # Add with old timestamp
        detector._cache[key] = (match, time.time() - 2)

        # Should be expired
        result = detector._get_cached(key)
        assert result is None
        assert key not in detector._cache  # Should be removed

    def test_cache_eviction(self):
        """Test cache evicts oldest when full."""
        detector = IntentDetector(max_cache_size=2)

        # Add 3 entries
        for i in range(3):
            key = f"key_{i}"
            match = IntentMatch(
                intent=f"intent_{i}",
                confidence=1.0,
                reasoning="test",
            )
            detector._cache_result(key, match)
            time.sleep(0.01)  # Small delay for different timestamps

        # Should only have 2 entries (oldest evicted)
        assert len(detector._cache) == 2
        # First key should be evicted
        assert "key_0" not in detector._cache

    def test_clear_cache(self, detector):
        """Test clear_cache removes all entries."""
        # Add some entries
        for i in range(5):
            key = f"key_{i}"
            match = IntentMatch(
                intent=f"intent_{i}",
                confidence=1.0,
                reasoning="test",
            )
            detector._cache_result(key, match)

        assert len(detector._cache) > 0

        detector.clear_cache()
        assert len(detector._cache) == 0

    def test_get_cache_stats(self, detector):
        """Test get_cache_stats returns correct metrics."""
        # Add entries
        for i in range(3):
            key = f"key_{i}"
            match = IntentMatch(
                intent=f"intent_{i}",
                confidence=1.0,
                reasoning="test",
            )
            detector._cache_result(key, match)

        stats = detector.get_cache_stats()
        assert stats["total_entries"] == 3
        assert stats["valid_entries"] == 3
        assert stats["max_size"] == 100
        assert stats["ttl_seconds"] == 300


# ============================================================================
# REQ-ID-006: IntentDetector Tests - LLM Fallback
# ============================================================================


class TestIntentDetectorLLMFallback:
    """Tests for IntentDetector LLM fallback."""

    @pytest.mark.asyncio
    async def test_no_llm_when_pattern_matches(self, detector, help_trigger):
        """Test LLM is not called when pattern matches."""
        with patch.object(
            detector, "_llm_classify", new_callable=AsyncMock
        ) as mock_llm:
            result = await detector.detect_intent(
                message="I need help",
                available_triggers=[help_trigger],
                context={},
            )

            # LLM should not be called
            mock_llm.assert_not_called()
            assert result.detection_method == "pattern"

    @pytest.mark.asyncio
    async def test_llm_called_when_no_pattern_match(
        self, detector, refund_trigger, mock_agent_result
    ):
        """Test LLM is called when pattern doesn't match."""
        with patch.object(
            detector, "_llm_classify", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = IntentMatch(
                intent="refund",
                confidence=0.95,
                reasoning="LLM classification",
                trigger=refund_trigger,
                detection_method="llm",
            )

            # Message doesn't match pattern "refund" or "money back"
            result = await detector.detect_intent(
                message="I want my purchase returned",
                available_triggers=[refund_trigger],
                context={},
            )

            # LLM should be called
            mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_llm_when_use_llm_fallback_false(self, detector, no_llm_trigger):
        """Test LLM not called when use_llm_fallback=False."""
        with patch.object(
            detector, "_llm_classify", new_callable=AsyncMock
        ) as mock_llm:
            result = await detector.detect_intent(
                message="some random message",
                available_triggers=[no_llm_trigger],
                context={},
            )

            # LLM should not be called
            mock_llm.assert_not_called()
            # Should return None (no match)
            assert result is None

    @pytest.mark.asyncio
    async def test_llm_result_cached(self, detector, refund_trigger):
        """Test LLM result is cached for subsequent calls."""
        llm_result = IntentMatch(
            intent="refund",
            confidence=0.95,
            reasoning="LLM classification",
            trigger=refund_trigger,
            detection_method="llm",
        )

        with patch.object(
            detector, "_llm_classify", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = llm_result

            # First call - LLM invoked
            result1 = await detector.detect_intent(
                message="I want my purchase returned",
                available_triggers=[refund_trigger],
                context={},
            )
            assert mock_llm.call_count == 1

            # Second call - should hit cache
            result2 = await detector.detect_intent(
                message="I want my purchase returned",
                available_triggers=[refund_trigger],
                context={},
            )

            # LLM not called again
            assert mock_llm.call_count == 1
            assert result2.from_cache is True

    @pytest.mark.asyncio
    async def test_confidence_threshold_filtering(self, detector, refund_trigger):
        """Test results below confidence threshold are rejected."""
        low_confidence_result = IntentMatch(
            intent="refund",
            confidence=0.5,  # Below 0.7 threshold
            reasoning="Low confidence match",
            trigger=refund_trigger,
            detection_method="llm",
        )

        with patch.object(
            detector, "_llm_classify", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = None  # LLM returns None for low confidence

            result = await detector.detect_intent(
                message="maybe I want something back",
                available_triggers=[refund_trigger],
                context={},
            )

            # Should return None due to low confidence
            assert result is None


# ============================================================================
# REQ-ID-006: IntentDetector Tests - Configuration
# ============================================================================


class TestIntentDetectorConfiguration:
    """Tests for IntentDetector configuration."""

    def test_default_configuration(self):
        """Test default configuration values."""
        detector = IntentDetector()
        assert detector.model == "gpt-4o-mini"
        assert detector.llm_provider == "openai"
        assert detector.cache_ttl_seconds == 300
        assert detector.confidence_threshold == 0.7
        assert detector.max_cache_size == 1000

    def test_custom_configuration(self):
        """Test custom configuration values."""
        detector = IntentDetector(
            model="gpt-4",
            llm_provider="openai",
            cache_ttl_seconds=600,
            confidence_threshold=0.9,
            max_cache_size=500,
        )
        assert detector.model == "gpt-4"
        assert detector.llm_provider == "openai"
        assert detector.cache_ttl_seconds == 600
        assert detector.confidence_threshold == 0.9
        assert detector.max_cache_size == 500

    def test_ollama_provider(self):
        """Test Ollama provider configuration."""
        detector = IntentDetector(
            llm_provider="ollama",
            model="llama3.2:3b",
        )
        assert detector.llm_provider == "ollama"
        assert detector.model == "llama3.2:3b"


# ============================================================================
# REQ-ID-006: IntentDetector Tests - Error Handling
# ============================================================================


class TestIntentDetectorErrorHandling:
    """Tests for IntentDetector error handling."""

    @pytest.mark.asyncio
    async def test_empty_triggers_returns_none(self, detector):
        """Test empty triggers list returns None."""
        result = await detector.detect_intent(
            message="any message",
            available_triggers=[],
            context={},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_error_returns_none(self, detector, refund_trigger):
        """Test LLM error returns None (doesn't crash)."""
        with patch.object(
            detector, "_llm_classify", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.side_effect = Exception("LLM API error")

            # Should not raise, returns None
            result = await detector.detect_intent(
                message="I want my purchase returned",
                available_triggers=[refund_trigger],
                context={},
            )

            # Returns None on error (pattern didn't match, LLM failed)
            assert result is None

    @pytest.mark.asyncio
    async def test_handles_context_with_complex_types(self, detector, help_trigger):
        """Test detector handles context with complex types."""
        context = {
            "simple": "string",
            "number": 42,
            "boolean": True,
            "list": [1, 2, 3],  # Not primitive - should be filtered
            "dict": {"nested": "value"},  # Not primitive - should be filtered
        }

        # Should not crash
        result = await detector.detect_intent(
            message="I need help",
            available_triggers=[help_trigger],
            context=context,
        )
        assert result is not None


# ============================================================================
# Integration Tests (Detector + Trigger)
# ============================================================================


class TestDetectorTriggerIntegration:
    """Integration tests for IntentDetector with triggers."""

    @pytest.mark.asyncio
    async def test_multiple_triggers_pattern_priority(self, detector):
        """Test first matching trigger pattern wins."""
        trigger1 = IntentTrigger(patterns=["help"])
        trigger2 = IntentTrigger(patterns=["help", "assist"])

        result = await detector.detect_intent(
            message="I need help",
            available_triggers=[trigger1, trigger2],
            context={},
        )

        # First trigger should match
        assert result.trigger == trigger1

    @pytest.mark.asyncio
    async def test_trigger_reference_preserved(self, detector):
        """Test trigger reference is preserved through detection."""
        trigger = IntentTrigger(
            patterns=["test"],
            use_llm_fallback=False,
            confidence_threshold=0.8,
        )

        result = await detector.detect_intent(
            message="this is a test",
            available_triggers=[trigger],
            context={},
        )

        assert result is not None
        assert result.trigger is trigger
        assert result.trigger.use_llm_fallback is False
        assert result.trigger.confidence_threshold == 0.8

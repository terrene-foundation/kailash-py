"""
Unit tests for Transition System (TODO-JO-003).

Tests cover:
- REQ-ID-001: Transition class
- REQ-ID-002: BaseTrigger and IntentTrigger
- REQ-ID-003: ConditionTrigger
- REQ-ID-004: AlwaysTrigger
- REQ-ID-005: TransitionResult

These are Tier 1 (Unit) tests that don't require LLM calls.
"""

from typing import Any, Dict

import pytest

from kaizen.journey.transitions import (
    AlwaysTrigger,
    BaseTrigger,
    ConditionTrigger,
    IntentTrigger,
    Transition,
    TransitionResult,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def help_trigger():
    """Create help intent trigger."""
    return IntentTrigger(patterns=["help", "question", "what is"])


@pytest.fixture
def refund_trigger():
    """Create refund intent trigger."""
    return IntentTrigger(patterns=["refund", "money back"])


@pytest.fixture
def retry_condition_trigger():
    """Create retry count condition trigger."""
    return ConditionTrigger(
        condition=lambda ctx: ctx.get("retry_count", 0) >= 3,
        description="Trigger after 3 retries",
    )


@pytest.fixture
def help_transition(help_trigger):
    """Create help transition."""
    return Transition(
        trigger=help_trigger,
        from_pathway="*",
        to_pathway="faq",
        priority=10,
    )


# ============================================================================
# REQ-ID-005: TransitionResult Tests
# ============================================================================


class TestTransitionResult:
    """Tests for TransitionResult dataclass."""

    def test_creation_minimal(self):
        """Test creating TransitionResult with minimal fields."""
        result = TransitionResult(matched=False)
        assert result.matched is False
        assert result.transition is None
        assert result.trigger_result is None
        assert result.updated_context is None

    def test_creation_full(self, help_transition):
        """Test creating TransitionResult with all fields."""
        result = TransitionResult(
            matched=True,
            transition=help_transition,
            trigger_result={"confidence": 0.9},
            updated_context={"topic": "faq"},
        )
        assert result.matched is True
        assert result.transition == help_transition
        assert result.trigger_result == {"confidence": 0.9}
        assert result.updated_context == {"topic": "faq"}


# ============================================================================
# REQ-ID-002: IntentTrigger Tests
# ============================================================================


class TestIntentTrigger:
    """Tests for IntentTrigger class."""

    def test_pattern_match_basic(self, help_trigger):
        """Test basic pattern matching."""
        assert help_trigger.evaluate("I need help", {})
        assert help_trigger.evaluate("Can I ask a question?", {})
        assert help_trigger.evaluate("What is AI?", {})

    def test_pattern_match_case_insensitive(self, help_trigger):
        """Test pattern matching is case-insensitive."""
        assert help_trigger.evaluate("I need HELP", {})
        assert help_trigger.evaluate("QUESTION about service", {})
        assert help_trigger.evaluate("What Is this?", {})

    def test_pattern_match_word_boundary(self):
        """Ensure pattern matching uses word boundaries."""
        trigger = IntentTrigger(patterns=["help"])

        # Should match "help" as whole word
        assert trigger.evaluate("I need help", {})
        assert trigger.evaluate("help me please", {})
        assert trigger.evaluate("can you help?", {})

        # Should NOT match "helpful" (help as substring)
        assert not trigger.evaluate("That was helpful", {})
        assert not trigger.evaluate("unhelpful response", {})
        assert not trigger.evaluate("helper application", {})

    def test_pattern_match_no_match(self, help_trigger):
        """Test pattern matching returns False when no match."""
        assert not help_trigger.evaluate("Book an appointment", {})
        assert not help_trigger.evaluate("I want to cancel", {})
        assert not help_trigger.evaluate("", {})

    def test_empty_patterns(self):
        """Test trigger with empty patterns returns False."""
        trigger = IntentTrigger(patterns=[])
        assert not trigger.evaluate("any message", {})

    def test_get_intent_name(self):
        """Test get_intent_name returns first pattern."""
        trigger = IntentTrigger(patterns=["help", "question"])
        assert trigger.get_intent_name() == "help"

    def test_get_intent_name_empty(self):
        """Test get_intent_name with empty patterns returns 'unknown'."""
        trigger = IntentTrigger(patterns=[])
        assert trigger.get_intent_name() == "unknown"

    def test_multi_word_pattern(self):
        """Test multi-word pattern matching."""
        trigger = IntentTrigger(patterns=["money back", "get refund"])

        assert trigger.evaluate("I want my money back", {})
        assert trigger.evaluate("Can I get refund please?", {})
        assert not trigger.evaluate("back money", {})

    def test_special_characters_in_pattern(self):
        """Test patterns with special regex characters."""
        # Test patterns with apostrophes (common in contractions)
        trigger = IntentTrigger(patterns=["what's", "don't"])

        # Apostrophes work because they're still "word-ish"
        assert trigger.evaluate("what's happening", {})
        assert trigger.evaluate("don't worry", {})

        # Test that regex special chars are escaped properly
        # (they won't match at word boundaries if followed by special chars)
        trigger2 = IntentTrigger(patterns=["c++"])
        # c++ won't match due to word boundary issues with +
        # This documents current behavior - patterns should be word-like
        assert not trigger2.evaluate("I know c++", {})

        # Regular words with numbers work fine
        trigger3 = IntentTrigger(patterns=["help123"])
        assert trigger3.evaluate("please help123 me", {})

    def test_default_values(self):
        """Test IntentTrigger default values."""
        trigger = IntentTrigger(patterns=["test"])
        assert trigger.use_llm_fallback is True
        assert trigger.confidence_threshold == 0.7

    def test_custom_values(self):
        """Test IntentTrigger with custom values."""
        trigger = IntentTrigger(
            patterns=["test"],
            use_llm_fallback=False,
            confidence_threshold=0.9,
        )
        assert trigger.use_llm_fallback is False
        assert trigger.confidence_threshold == 0.9

    def test_hashable(self):
        """Test IntentTrigger is hashable for caching."""
        trigger = IntentTrigger(patterns=["help"])
        # Should not raise
        hash(trigger)
        # Should be usable as dict key
        d = {trigger: "value"}
        assert d[trigger] == "value"


# ============================================================================
# REQ-ID-003: ConditionTrigger Tests
# ============================================================================


class TestConditionTrigger:
    """Tests for ConditionTrigger class."""

    def test_condition_true(self, retry_condition_trigger):
        """Test condition returns True when met."""
        context = {"retry_count": 3}
        assert retry_condition_trigger.evaluate("any message", context)

        context = {"retry_count": 5}
        assert retry_condition_trigger.evaluate("any message", context)

    def test_condition_false(self, retry_condition_trigger):
        """Test condition returns False when not met."""
        context = {"retry_count": 2}
        assert not retry_condition_trigger.evaluate("any message", context)

        context = {"retry_count": 0}
        assert not retry_condition_trigger.evaluate("any message", context)

    def test_condition_missing_key(self, retry_condition_trigger):
        """Test condition handles missing context key with default."""
        context = {}  # No retry_count
        assert not retry_condition_trigger.evaluate("any message", context)

    def test_condition_none(self):
        """Test trigger with None condition returns False."""
        trigger = ConditionTrigger(condition=None)
        assert not trigger.evaluate("any message", {})

    def test_condition_exception_safety(self):
        """Test condition exceptions return False (fail-safe)."""
        # Condition that will raise KeyError
        trigger = ConditionTrigger(condition=lambda ctx: ctx["missing_key"] > 0)
        # Should return False, not raise exception
        assert not trigger.evaluate("any message", {})

    def test_condition_type_error_safety(self):
        """Test condition type errors return False."""
        trigger = ConditionTrigger(
            condition=lambda ctx: ctx["count"] + "string"  # TypeError
        )
        context = {"count": 5}
        assert not trigger.evaluate("any message", context)

    def test_message_ignored(self):
        """Test that message parameter is ignored."""
        trigger = ConditionTrigger(condition=lambda ctx: ctx.get("active", False))
        context = {"active": True}

        # Same result regardless of message
        assert trigger.evaluate("message 1", context)
        assert trigger.evaluate("message 2", context)
        assert trigger.evaluate("", context)

    def test_description(self):
        """Test description field is set."""
        trigger = ConditionTrigger(
            condition=lambda ctx: True,
            description="Always true trigger",
        )
        assert trigger.description == "Always true trigger"

    def test_hashable(self):
        """Test ConditionTrigger is hashable."""
        trigger = ConditionTrigger(
            condition=lambda ctx: True,
            description="test",
        )
        # Should not raise
        hash(trigger)


# ============================================================================
# REQ-ID-004: AlwaysTrigger Tests
# ============================================================================


class TestAlwaysTrigger:
    """Tests for AlwaysTrigger class."""

    def test_always_returns_true(self):
        """Test AlwaysTrigger always returns True."""
        trigger = AlwaysTrigger()
        assert trigger.evaluate("any message", {})
        assert trigger.evaluate("", {})
        assert trigger.evaluate("different message", {"some": "context"})

    def test_empty_message_and_context(self):
        """Test AlwaysTrigger returns True even with empty inputs."""
        trigger = AlwaysTrigger()
        assert trigger.evaluate("", {})

    def test_complex_context(self):
        """Test AlwaysTrigger ignores context entirely."""
        trigger = AlwaysTrigger()
        complex_context = {
            "user_id": "12345",
            "nested": {"data": [1, 2, 3]},
            "count": 100,
        }
        assert trigger.evaluate("test", complex_context)

    def test_hashable(self):
        """Test AlwaysTrigger is hashable for caching."""
        trigger = AlwaysTrigger()
        # Should not raise
        hash(trigger)
        # Should be usable as dict key
        d = {trigger: "value"}
        assert d[trigger] == "value"

    def test_multiple_instances_hash_equal(self):
        """Test multiple AlwaysTrigger instances have same hash."""
        trigger1 = AlwaysTrigger()
        trigger2 = AlwaysTrigger()
        # Both should have same hash since they're functionally identical
        assert hash(trigger1) == hash(trigger2)

    def test_in_transition(self):
        """Test AlwaysTrigger works correctly in a Transition."""
        trigger = AlwaysTrigger()
        transition = Transition(
            trigger=trigger,
            from_pathway="*",
            to_pathway="fallback",
            priority=-100,  # Low priority for fallback
        )

        # Should match any message from any pathway
        assert transition.matches("intake", "any message", {})
        assert transition.matches("booking", "", {})
        assert transition.matches("faq", "hello world", {"key": "value"})

    def test_as_default_fallback(self):
        """Test AlwaysTrigger as default fallback transition."""
        # Specific intent trigger
        help_trigger = IntentTrigger(patterns=["help"])
        help_transition = Transition(
            trigger=help_trigger,
            from_pathway="*",
            to_pathway="faq",
            priority=10,
        )

        # Default fallback with AlwaysTrigger
        always_trigger = AlwaysTrigger()
        fallback_transition = Transition(
            trigger=always_trigger,
            from_pathway="*",
            to_pathway="main_menu",
            priority=-100,  # Very low priority
        )

        transitions = [help_transition, fallback_transition]
        # Sort by priority (descending)
        sorted_transitions = sorted(transitions, key=lambda t: t.priority, reverse=True)

        # High priority help transition first
        assert sorted_transitions[0] == help_transition
        assert sorted_transitions[1] == fallback_transition

        # Test: "help" message should match help_transition first
        message = "I need help"
        matched = None
        for t in sorted_transitions:
            if t.matches("any", message, {}):
                matched = t.to_pathway
                break
        assert matched == "faq"

        # Test: unrecognized message should fall through to fallback
        message = "random gibberish"
        matched = None
        for t in sorted_transitions:
            if t.matches("any", message, {}):
                matched = t.to_pathway
                break
        assert matched == "main_menu"  # Fallback matched

    def test_specific_pathway_restriction(self):
        """Test AlwaysTrigger respects from_pathway restriction."""
        trigger = AlwaysTrigger()
        transition = Transition(
            trigger=trigger,
            from_pathway="booking",  # Only from booking
            to_pathway="confirmation",
        )

        # Should only match when current pathway is "booking"
        assert transition.matches("booking", "any message", {})
        assert not transition.matches("intake", "any message", {})
        assert not transition.matches("faq", "any message", {})


# ============================================================================
# REQ-ID-001: Transition Tests
# ============================================================================


class TestTransition:
    """Tests for Transition class."""

    def test_matches_any_pathway(self, help_transition):
        """Test transition with from_pathway='*' matches any pathway."""
        assert help_transition.matches("intake", "I need help", {})
        assert help_transition.matches("booking", "I need help", {})
        assert help_transition.matches("faq", "I need help", {})

    def test_matches_specific_pathway(self, help_trigger):
        """Test transition with specific from_pathway."""
        transition = Transition(
            trigger=help_trigger,
            from_pathway="intake",
            to_pathway="faq",
        )
        assert transition.matches("intake", "I need help", {})
        assert not transition.matches("booking", "I need help", {})

    def test_matches_pathway_list(self, help_trigger):
        """Test transition with from_pathway as list."""
        transition = Transition(
            trigger=help_trigger,
            from_pathway=["intake", "booking"],
            to_pathway="faq",
        )
        assert transition.matches("intake", "I need help", {})
        assert transition.matches("booking", "I need help", {})
        assert not transition.matches("checkout", "I need help", {})

    def test_matches_trigger_required(self, help_transition):
        """Test transition requires trigger match."""
        # Wrong message - trigger doesn't match
        assert not help_transition.matches("intake", "Book a flight", {})

    def test_context_update_append(self, help_trigger):
        """Test context update with append: syntax."""
        transition = Transition(
            trigger=help_trigger,
            to_pathway="faq",
            context_update={"rejected_doctors": "append:selected_doctor"},
        )

        context = {"rejected_doctors": ["Dr. A"]}
        result = {"selected_doctor": "Dr. B"}

        new_context = transition.apply_context_update(context, result)
        assert new_context["rejected_doctors"] == ["Dr. A", "Dr. B"]

    def test_context_update_append_creates_list(self, help_trigger):
        """Test append: creates list if field doesn't exist."""
        transition = Transition(
            trigger=help_trigger,
            to_pathway="faq",
            context_update={"items": "append:item"},
        )

        context = {}
        result = {"item": "first"}

        new_context = transition.apply_context_update(context, result)
        assert new_context["items"] == ["first"]

    def test_context_update_append_from_scalar(self, help_trigger):
        """Test append: converts scalar to list."""
        transition = Transition(
            trigger=help_trigger,
            to_pathway="faq",
            context_update={"items": "append:item"},
        )

        context = {"items": "existing"}
        result = {"item": "new"}

        new_context = transition.apply_context_update(context, result)
        assert new_context["items"] == ["existing", "new"]

    def test_context_update_set(self, help_trigger):
        """Test context update with set: syntax."""
        transition = Transition(
            trigger=help_trigger,
            to_pathway="faq",
            context_update={"status": "set:active"},
        )

        context = {"status": "inactive"}
        new_context = transition.apply_context_update(context, {})
        assert new_context["status"] == "active"

    def test_context_update_copy(self, help_trigger):
        """Test context update with copy: syntax."""
        transition = Transition(
            trigger=help_trigger,
            to_pathway="faq",
            context_update={"customer_name": "copy:name"},
        )

        context = {}
        result = {"name": "Alice"}

        new_context = transition.apply_context_update(context, result)
        assert new_context["customer_name"] == "Alice"

    def test_context_update_copy_missing(self, help_trigger):
        """Test copy: handles missing source field."""
        transition = Transition(
            trigger=help_trigger,
            to_pathway="faq",
            context_update={"customer_name": "copy:name"},
        )

        context = {}
        result = {}  # No 'name' field

        new_context = transition.apply_context_update(context, result)
        assert "customer_name" not in new_context

    def test_context_update_remove(self, help_trigger):
        """Test context update with remove: syntax."""
        transition = Transition(
            trigger=help_trigger,
            to_pathway="faq",
            context_update={"_cleanup": "remove:temp_data"},
        )

        context = {"temp_data": "some value", "keep": "this"}
        new_context = transition.apply_context_update(context, {})

        assert "temp_data" not in new_context
        assert new_context["keep"] == "this"

    def test_context_update_direct_reference(self, help_trigger):
        """Test context update with direct field reference."""
        transition = Transition(
            trigger=help_trigger,
            to_pathway="faq",
            context_update={"customer_name": "name"},
        )

        context = {}
        result = {"name": "Bob"}

        new_context = transition.apply_context_update(context, result)
        assert new_context["customer_name"] == "Bob"

    def test_context_update_none(self, help_transition):
        """Test apply_context_update with no context_update."""
        context = {"existing": "value"}
        new_context = help_transition.apply_context_update(context, {})
        assert new_context == {"existing": "value"}

    def test_context_update_preserves_original(self, help_trigger):
        """Test context update doesn't mutate original context."""
        transition = Transition(
            trigger=help_trigger,
            to_pathway="faq",
            context_update={"new_field": "set:value"},
        )

        original_context = {"existing": "value"}
        new_context = transition.apply_context_update(original_context, {})

        assert "new_field" in new_context
        assert "new_field" not in original_context  # Original unchanged

    def test_priority(self, help_trigger):
        """Test transitions can have different priorities."""
        high_priority = Transition(
            trigger=help_trigger,
            to_pathway="urgent_faq",
            priority=100,
        )
        low_priority = Transition(
            trigger=help_trigger,
            to_pathway="faq",
            priority=1,
        )

        assert high_priority.priority > low_priority.priority

    def test_default_values(self, help_trigger):
        """Test Transition default values."""
        transition = Transition(trigger=help_trigger)
        assert transition.from_pathway == "*"
        assert transition.to_pathway == ""
        assert transition.context_update is None
        assert transition.priority == 0


# ============================================================================
# Integration Tests (Trigger + Transition)
# ============================================================================


class TestTriggerTransitionIntegration:
    """Integration tests for triggers with transitions."""

    def test_intent_trigger_in_transition(self):
        """Test IntentTrigger works correctly in Transition."""
        trigger = IntentTrigger(patterns=["cancel", "stop"])
        transition = Transition(
            trigger=trigger,
            from_pathway="booking",
            to_pathway="cancellation",
            context_update={"previous_pathway": "set:booking"},
        )

        # Test matching
        assert transition.matches("booking", "I want to cancel", {})
        assert not transition.matches("booking", "I want to book", {})
        assert not transition.matches("intake", "I want to cancel", {})

        # Test context update
        new_context = transition.apply_context_update({}, {})
        assert new_context["previous_pathway"] == "booking"

    def test_condition_trigger_in_transition(self):
        """Test ConditionTrigger works correctly in Transition."""
        trigger = ConditionTrigger(condition=lambda ctx: ctx.get("error_count", 0) > 2)
        transition = Transition(
            trigger=trigger,
            from_pathway="*",
            to_pathway="error_handling",
        )

        context_ok = {"error_count": 1}
        context_error = {"error_count": 3}

        assert not transition.matches("any", "any message", context_ok)
        assert transition.matches("any", "any message", context_error)

    def test_multiple_transitions_priority(self):
        """Test multiple transitions are evaluated by priority."""
        specific_trigger = IntentTrigger(patterns=["urgent help"])
        general_trigger = IntentTrigger(patterns=["help"])

        high_priority = Transition(
            trigger=specific_trigger,
            to_pathway="urgent_support",
            priority=100,
        )
        low_priority = Transition(
            trigger=general_trigger,
            to_pathway="faq",
            priority=10,
        )

        transitions = [low_priority, high_priority]
        # Sort by priority (descending)
        sorted_transitions = sorted(transitions, key=lambda t: t.priority, reverse=True)

        # High priority should be first
        assert sorted_transitions[0] == high_priority
        assert sorted_transitions[1] == low_priority

        # Test matching (both should match "urgent help")
        message = "I need urgent help"
        for t in sorted_transitions:
            if t.matches("any", message, {}):
                # First match (high priority) wins
                assert t.to_pathway == "urgent_support"
                break

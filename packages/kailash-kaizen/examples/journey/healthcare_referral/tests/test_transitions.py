"""
Transition Detection Tests for Healthcare Referral Journey

Tests intent detection, transition matching, and pathway navigation.
These are Tier 1 tests (unit tests) with minimal external dependencies.
"""

import pytest

from examples.journey.healthcare_referral.journey import HealthcareReferralJourney
from kaizen.journey import ConditionTrigger, IntentTrigger, Transition


class TestFAQTransitionPatterns:
    """Test FAQ intent pattern matching."""

    def test_question_patterns_match(self):
        """Test that question-like messages match FAQ patterns."""
        # Get FAQ transition
        faq_transition = None
        for t in HealthcareReferralJourney._transitions:
            if t.to_pathway == "faq":
                faq_transition = t
                break

        assert faq_transition is not None, "FAQ transition not found"
        assert isinstance(faq_transition.trigger, IntentTrigger)

        # Test matching messages
        trigger = faq_transition.trigger
        matching_messages = [
            "What is a specialist?",
            "What's the difference between an orthopedist and a chiropractor?",
            "How does my insurance work?",
            "Can you explain the referral process?",
            "Tell me about the different types of doctors",
            "I have a question about the appointment",
            "Help me understand this",
        ]

        for msg in matching_messages:
            result = trigger.evaluate(msg, {})
            assert result is True, f"Expected FAQ match for: {msg}"

    def test_booking_messages_do_not_match_faq(self):
        """Test that normal booking messages don't trigger FAQ."""
        faq_transition = None
        for t in HealthcareReferralJourney._transitions:
            if t.to_pathway == "faq":
                faq_transition = t
                break

        trigger = faq_transition.trigger
        non_matching_messages = [
            "I'll take the 3pm slot",
            "Book me with Dr. Smith",
            "Not Dr. Jones, anyone else",
            "Yes, confirm the appointment",
            "My back hurts",
        ]

        for msg in non_matching_messages:
            # Pattern matching should NOT match these
            result = trigger.evaluate(msg, {})
            # Note: These might still match via LLM fallback in real use,
            # but pattern matching alone should not match
            # We're testing the fast path here
            assert result is False, f"Unexpected FAQ pattern match for: {msg}"


class TestHesitationTransitionPatterns:
    """Test hesitation intent pattern matching."""

    def test_hesitation_patterns_match(self):
        """Test that hesitant messages match patterns."""
        hesitation_transition = None
        for t in HealthcareReferralJourney._transitions:
            if t.to_pathway == "persuasion":
                hesitation_transition = t
                break

        assert hesitation_transition is not None, "Hesitation transition not found"
        assert isinstance(hesitation_transition.trigger, IntentTrigger)

        trigger = hesitation_transition.trigger
        matching_messages = [
            "I'm not sure about this",
            "Maybe I should wait",
            "Let me think about it",
            "I need to think about it",
            "I don't know if I want to book",
            "On second thought...",
            "I'm hesitant to proceed",
        ]

        for msg in matching_messages:
            result = trigger.evaluate(msg, {})
            assert result is True, f"Expected hesitation match for: {msg}"

    def test_hesitation_only_from_booking(self):
        """Test that hesitation transition only triggers from booking."""
        hesitation_transition = None
        for t in HealthcareReferralJourney._transitions:
            if t.to_pathway == "persuasion":
                hesitation_transition = t
                break

        # Check from_pathway
        assert hesitation_transition.from_pathway == ["booking"]

        # Test transition matching from different pathways
        msg = "I'm not sure about this"

        # Should match from booking
        assert hesitation_transition.matches("booking", msg, {}) is True

        # Should NOT match from intake
        assert hesitation_transition.matches("intake", msg, {}) is False

        # Should NOT match from faq
        assert hesitation_transition.matches("faq", msg, {}) is False

    def test_confident_messages_do_not_match_hesitation(self):
        """Test that confident messages don't trigger hesitation."""
        hesitation_transition = None
        for t in HealthcareReferralJourney._transitions:
            if t.to_pathway == "persuasion":
                hesitation_transition = t
                break

        trigger = hesitation_transition.trigger
        non_matching_messages = [
            "Yes, book that appointment",
            "I want Dr. Chen",
            "Let's do the 9am slot",
            "Perfect, confirm it",
        ]

        for msg in non_matching_messages:
            result = trigger.evaluate(msg, {})
            assert result is False, f"Unexpected hesitation match for: {msg}"


class TestCancellationTransitionPatterns:
    """Test cancellation intent pattern matching."""

    def test_cancellation_patterns_match(self):
        """Test that cancellation messages match patterns."""
        cancel_transition = None
        for t in HealthcareReferralJourney._transitions:
            if t.to_pathway is None:  # Cancel ends journey
                cancel_transition = t
                break

        assert cancel_transition is not None, "Cancellation transition not found"

        trigger = cancel_transition.trigger
        matching_messages = [
            "Cancel",
            "Stop",
            "Nevermind",
            "Never mind",
            "Forget it",
            "Quit",
            "Exit",
        ]

        for msg in matching_messages:
            result = trigger.evaluate(msg, {})
            assert result is True, f"Expected cancellation match for: {msg}"

    def test_cancellation_has_high_priority(self):
        """Test that cancellation has high priority."""
        cancel_transition = None
        for t in HealthcareReferralJourney._transitions:
            if t.to_pathway is None:
                cancel_transition = t
                break

        # Cancellation should have high priority to catch explicit requests
        assert cancel_transition.priority >= 20

    def test_cancellation_no_llm_fallback(self):
        """Test that cancellation uses exact match only."""
        cancel_transition = None
        for t in HealthcareReferralJourney._transitions:
            if t.to_pathway is None:
                cancel_transition = t
                break

        # For safety, cancellation should not use LLM fallback
        assert cancel_transition.trigger.use_llm_fallback is False


class TestConditionTriggers:
    """Test condition-based transitions."""

    def test_booking_complete_condition(self):
        """Test booking complete condition trigger."""
        booking_complete_transition = None
        for t in HealthcareReferralJourney._transitions:
            if (
                isinstance(t.trigger, ConditionTrigger)
                and t.from_pathway == "booking"
                and t.to_pathway == "confirmation"
            ):
                booking_complete_transition = t
                break

        assert (
            booking_complete_transition is not None
        ), "Booking complete transition not found"

        trigger = booking_complete_transition.trigger

        # Should trigger when booking_complete is True
        result = trigger.evaluate("any message", {"booking_complete": True})
        assert result is True

        # Should NOT trigger when booking_complete is False
        result = trigger.evaluate("any message", {"booking_complete": False})
        assert result is False

        # Should NOT trigger when booking_complete is missing
        result = trigger.evaluate("any message", {})
        assert result is False

    def test_intake_ready_condition(self):
        """Test intake ready condition trigger."""
        intake_ready_transition = None
        for t in HealthcareReferralJourney._transitions:
            if (
                isinstance(t.trigger, ConditionTrigger)
                and t.from_pathway == "intake"
                and t.to_pathway == "booking"
            ):
                intake_ready_transition = t
                break

        assert intake_ready_transition is not None, "Intake ready transition not found"

        trigger = intake_ready_transition.trigger

        # Should trigger when ready_for_booking is True
        result = trigger.evaluate("any message", {"ready_for_booking": True})
        assert result is True

        # Should NOT trigger when ready_for_booking is False
        result = trigger.evaluate("any message", {"ready_for_booking": False})
        assert result is False


class TestTransitionPriority:
    """Test transition priority ordering."""

    def test_cancellation_highest_priority(self):
        """Test that cancellation has highest priority."""
        transitions = HealthcareReferralJourney._transitions
        priorities = [(t.to_pathway, t.priority) for t in transitions]

        cancel_priority = None
        for pathway, priority in priorities:
            if pathway is None:
                cancel_priority = priority
                break

        # Cancellation should have the highest priority
        assert cancel_priority is not None
        for pathway, priority in priorities:
            if pathway is not None:
                assert (
                    cancel_priority >= priority
                ), f"Cancel priority ({cancel_priority}) should be >= {pathway} priority ({priority})"

    def test_faq_has_moderate_priority(self):
        """Test that FAQ has moderate priority."""
        faq_transition = None
        for t in HealthcareReferralJourney._transitions:
            if t.to_pathway == "faq":
                faq_transition = t
                break

        # FAQ should have moderate priority (higher than conditions)
        assert faq_transition.priority >= 5

    def test_conditions_have_low_priority(self):
        """Test that condition triggers have low priority."""
        for t in HealthcareReferralJourney._transitions:
            if isinstance(t.trigger, ConditionTrigger):
                # Condition triggers should have lowest priority
                # (evaluated after intent triggers)
                assert t.priority <= 5


class TestGlobalTransitions:
    """Test global (from any pathway) transitions."""

    def test_faq_is_global(self):
        """Test that FAQ transition triggers from any pathway."""
        faq_transition = None
        for t in HealthcareReferralJourney._transitions:
            if t.to_pathway == "faq":
                faq_transition = t
                break

        assert faq_transition.from_pathway == "*"

        # Test that it matches from all pathways
        msg = "What is a specialist?"
        for pathway in ["intake", "booking", "persuasion", "confirmation"]:
            assert faq_transition.matches(pathway, msg, {}) is True

    def test_cancellation_is_global(self):
        """Test that cancellation triggers from any pathway."""
        cancel_transition = None
        for t in HealthcareReferralJourney._transitions:
            if t.to_pathway is None:
                cancel_transition = t
                break

        assert cancel_transition.from_pathway == "*"


class TestTransitionCount:
    """Test expected number of transitions."""

    def test_minimum_transitions(self):
        """Test that journey has minimum expected transitions."""
        transitions = HealthcareReferralJourney._transitions

        # Should have at least:
        # - FAQ (global)
        # - Hesitation (from booking)
        # - Cancellation (global)
        # - Booking complete (condition)
        # - Intake ready (condition)
        assert len(transitions) >= 5

    def test_intent_trigger_count(self):
        """Test number of intent-based triggers."""
        intent_triggers = [
            t
            for t in HealthcareReferralJourney._transitions
            if isinstance(t.trigger, IntentTrigger)
        ]

        # Should have at least FAQ, hesitation, cancellation
        assert len(intent_triggers) >= 3

    def test_condition_trigger_count(self):
        """Test number of condition-based triggers."""
        condition_triggers = [
            t
            for t in HealthcareReferralJourney._transitions
            if isinstance(t.trigger, ConditionTrigger)
        ]

        # Should have at least booking_complete and ready_for_booking
        assert len(condition_triggers) >= 2


class TestReturnBehavior:
    """Test return behavior for detour pathways."""

    def test_faq_returns_to_previous(self):
        """Test that FAQ pathway returns to previous."""
        from kaizen.journey.behaviors import ReturnToPrevious

        faq_path = HealthcareReferralJourney.FAQPath

        assert faq_path._return_behavior is not None
        assert isinstance(faq_path._return_behavior, ReturnToPrevious)

    def test_faq_preserves_context_on_return(self):
        """Test that FAQ preserves context when returning."""
        faq_path = HealthcareReferralJourney.FAQPath

        assert faq_path._return_behavior.preserve_context is True

    def test_faq_max_detour_depth(self):
        """Test FAQ has reasonable max detour depth."""
        faq_path = HealthcareReferralJourney.FAQPath

        # Should allow reasonable nesting but prevent infinite loops
        assert faq_path._return_behavior.max_depth >= 2
        assert faq_path._return_behavior.max_depth <= 5

    def test_persuasion_does_not_return_to_previous(self):
        """Test that persuasion has explicit next, not return behavior."""
        persuasion_path = HealthcareReferralJourney.PersuasionPath

        # Persuasion goes back to booking explicitly
        assert persuasion_path._return_behavior is None
        assert persuasion_path._next == "booking"


class TestWordBoundaryMatching:
    """Test that pattern matching uses word boundaries."""

    def test_help_pattern_word_boundary(self):
        """Test that 'help' matches as word, not substring."""
        faq_transition = None
        for t in HealthcareReferralJourney._transitions:
            if t.to_pathway == "faq":
                faq_transition = t
                break

        trigger = faq_transition.trigger

        # Should match "help" as a word
        assert trigger.evaluate("I need help", {}) is True
        assert trigger.evaluate("Help me please", {}) is True

        # Should NOT match "helpful" (word boundary)
        assert trigger.evaluate("That was helpful", {}) is False
        assert trigger.evaluate("This is unhelpful", {}) is False

    def test_cancel_pattern_word_boundary(self):
        """Test that 'cancel' matches as word, not substring."""
        cancel_transition = None
        for t in HealthcareReferralJourney._transitions:
            if t.to_pathway is None:
                cancel_transition = t
                break

        trigger = cancel_transition.trigger

        # Should match "cancel" as a word
        assert trigger.evaluate("Cancel the appointment", {}) is True
        assert trigger.evaluate("I want to cancel", {}) is True

        # Should NOT match "cancellation" or "cancelled"
        # Actually, "cancel" is at the start of "cancellation", so word boundary
        # \bcancel\b should NOT match "cancellation"
        assert trigger.evaluate("What's the cancellation policy?", {}) is False

"""
Unit Tests for Healthcare Referral Journey Definition

Tests the journey class definition, pathway extraction, and configuration.
These are Tier 1 tests (unit tests) with no external dependencies.
"""

import pytest

from examples.journey.healthcare_referral.journey import (
    HealthcareReferralJourney,
    default_config,
    production_config,
)
from examples.journey.healthcare_referral.signatures import (
    BookingSignature,
    ConfirmationSignature,
    FAQSignature,
    IntakeSignature,
    PersuasionSignature,
)
from kaizen.journey.behaviors import ReturnToPrevious


class TestJourneyDefinition:
    """Test journey class definition and pathway extraction."""

    def test_journey_has_correct_pathways(self):
        """Test that all 5 pathways are extracted from journey definition."""
        pathways = HealthcareReferralJourney._pathways

        assert "intake" in pathways, "Missing intake pathway"
        assert "booking" in pathways, "Missing booking pathway"
        assert "faq" in pathways, "Missing faq pathway"
        assert "persuasion" in pathways, "Missing persuasion pathway"
        assert "confirmation" in pathways, "Missing confirmation pathway"
        assert len(pathways) == 5, f"Expected 5 pathways, got {len(pathways)}"

    def test_entry_pathway_is_intake(self):
        """Test that entry pathway is set to intake."""
        assert HealthcareReferralJourney._entry_pathway == "intake"

    def test_has_global_transitions(self):
        """Test that global transitions are defined."""
        transitions = HealthcareReferralJourney._transitions

        # Should have at least FAQ, hesitation, and cancellation transitions
        assert (
            len(transitions) >= 3
        ), f"Expected at least 3 transitions, got {len(transitions)}"

    def test_pathway_id_conversion(self):
        """Test that pathway class names are converted to snake_case IDs."""
        pathways = HealthcareReferralJourney._pathways

        # IntakePath -> intake
        assert "intake" in pathways
        # BookingPath -> booking
        assert "booking" in pathways
        # FAQPath -> faq
        assert "faq" in pathways
        # PersuasionPath -> persuasion
        assert "persuasion" in pathways
        # ConfirmationPath -> confirmation
        assert "confirmation" in pathways


class TestPathwayConfiguration:
    """Test individual pathway configurations."""

    def test_intake_signature(self):
        """Test IntakePath has correct signature."""
        intake_path = HealthcareReferralJourney.IntakePath
        assert intake_path._signature == IntakeSignature

    def test_intake_accumulates_symptoms(self):
        """Test IntakePath accumulates correct fields."""
        intake_path = HealthcareReferralJourney.IntakePath
        accumulate = intake_path._accumulate

        assert "symptoms" in accumulate
        assert "severity" in accumulate
        assert "preferences" in accumulate
        assert "insurance_info" in accumulate

    def test_intake_next_pathway(self):
        """Test IntakePath transitions to booking."""
        intake_path = HealthcareReferralJourney.IntakePath
        assert intake_path._next == "booking"

    def test_intake_agents(self):
        """Test IntakePath has correct agent."""
        intake_path = HealthcareReferralJourney.IntakePath
        assert "intake_agent" in intake_path._agents

    def test_booking_signature(self):
        """Test BookingPath has correct signature."""
        booking_path = HealthcareReferralJourney.BookingPath
        assert booking_path._signature == BookingSignature

    def test_booking_accumulates_rejected_doctors(self):
        """Test BookingPath accumulates rejected doctors."""
        booking_path = HealthcareReferralJourney.BookingPath
        accumulate = booking_path._accumulate

        assert "rejected_doctors" in accumulate
        assert "selected_doctor" in accumulate
        assert "selected_slot" in accumulate

    def test_booking_next_pathway(self):
        """Test BookingPath transitions to confirmation."""
        booking_path = HealthcareReferralJourney.BookingPath
        assert booking_path._next == "confirmation"

    def test_faq_signature(self):
        """Test FAQPath has correct signature."""
        faq_path = HealthcareReferralJourney.FAQPath
        assert faq_path._signature == FAQSignature

    def test_faq_has_return_behavior(self):
        """Test FAQPath has ReturnToPrevious behavior."""
        faq_path = HealthcareReferralJourney.FAQPath

        assert faq_path._return_behavior is not None
        assert isinstance(faq_path._return_behavior, ReturnToPrevious)
        assert faq_path._return_behavior.preserve_context is True
        assert faq_path._return_behavior.max_depth == 3

    def test_faq_no_next_pathway(self):
        """Test FAQPath has no __next__ (uses return behavior instead)."""
        faq_path = HealthcareReferralJourney.FAQPath
        assert faq_path._next is None

    def test_persuasion_signature(self):
        """Test PersuasionPath has correct signature."""
        persuasion_path = HealthcareReferralJourney.PersuasionPath
        assert persuasion_path._signature == PersuasionSignature

    def test_persuasion_next_pathway(self):
        """Test PersuasionPath returns to booking."""
        persuasion_path = HealthcareReferralJourney.PersuasionPath
        assert persuasion_path._next == "booking"

    def test_confirmation_signature(self):
        """Test ConfirmationPath has correct signature."""
        confirmation_path = HealthcareReferralJourney.ConfirmationPath
        assert confirmation_path._signature == ConfirmationSignature

    def test_confirmation_is_terminal(self):
        """Test ConfirmationPath is terminal (no __next__)."""
        confirmation_path = HealthcareReferralJourney.ConfirmationPath
        assert confirmation_path._next is None
        assert confirmation_path._return_behavior is None


class TestPathwayGuidelines:
    """Test pathway-specific guidelines."""

    def test_intake_has_guidelines(self):
        """Test IntakePath has pathway-specific guidelines."""
        intake_path = HealthcareReferralJourney.IntakePath
        guidelines = intake_path._guidelines

        assert len(guidelines) > 0
        # Check for specific guideline content
        guidelines_text = " ".join(guidelines).lower()
        assert "clarifying" in guidelines_text or "proceed" in guidelines_text

    def test_booking_has_guidelines(self):
        """Test BookingPath has pathway-specific guidelines."""
        booking_path = HealthcareReferralJourney.BookingPath
        guidelines = booking_path._guidelines

        assert len(guidelines) > 0
        guidelines_text = " ".join(guidelines).lower()
        assert "rejected" in guidelines_text or "filter" in guidelines_text

    def test_faq_has_guidelines(self):
        """Test FAQPath has pathway-specific guidelines."""
        faq_path = HealthcareReferralJourney.FAQPath
        guidelines = faq_path._guidelines

        assert len(guidelines) > 0


class TestPipelineConfiguration:
    """Test pathway pipeline configuration."""

    def test_all_pathways_use_sequential_pipeline(self):
        """Test that all pathways use sequential pipeline (single agent)."""
        pathways = [
            HealthcareReferralJourney.IntakePath,
            HealthcareReferralJourney.BookingPath,
            HealthcareReferralJourney.FAQPath,
            HealthcareReferralJourney.PersuasionPath,
            HealthcareReferralJourney.ConfirmationPath,
        ]

        for pathway in pathways:
            assert (
                pathway._pipeline == "sequential"
            ), f"{pathway.__name__} should use sequential pipeline"


class TestJourneyConfig:
    """Test journey configuration."""

    def test_default_config_values(self):
        """Test default configuration has expected values."""
        assert default_config.intent_detection_model == "gpt-4o-mini"
        assert default_config.intent_confidence_threshold == 0.75
        assert default_config.max_pathway_depth == 15
        assert default_config.error_recovery == "graceful"
        assert default_config.context_persistence == "memory"

    def test_production_config_values(self):
        """Test production configuration has expected values."""
        assert production_config.context_persistence == "dataflow"
        assert production_config.pathway_timeout_seconds >= 90.0
        assert production_config.max_retries >= 5


class TestJourneyInstantiation:
    """Test journey instance creation."""

    def test_journey_creates_with_session_id(self):
        """Test journey can be instantiated with session ID."""
        journey = HealthcareReferralJourney(session_id="test-session")

        assert journey.session_id == "test-session"
        assert journey.config is not None

    def test_journey_creates_with_custom_config(self):
        """Test journey can be instantiated with custom config."""
        from kaizen.journey import JourneyConfig

        custom_config = JourneyConfig(
            intent_confidence_threshold=0.9,
            max_pathway_depth=20,
        )

        journey = HealthcareReferralJourney(
            session_id="test-session",
            config=custom_config,
        )

        assert journey.config.intent_confidence_threshold == 0.9
        assert journey.config.max_pathway_depth == 20

    def test_journey_has_manager(self):
        """Test journey creates a PathwayManager."""
        journey = HealthcareReferralJourney(session_id="test-session")

        assert journey.manager is not None

    def test_journey_pathways_property(self):
        """Test journey.pathways returns copy of pathways."""
        journey = HealthcareReferralJourney(session_id="test-session")

        pathways = journey.pathways
        assert "intake" in pathways
        assert len(pathways) == 5

        # Verify it's a copy (mutation doesn't affect original)
        pathways["test"] = "value"
        assert "test" not in journey.pathways

    def test_journey_transitions_property(self):
        """Test journey.transitions returns copy of transitions."""
        journey = HealthcareReferralJourney(session_id="test-session")

        transitions = journey.transitions
        assert len(transitions) >= 3

        # Verify it's a copy
        original_len = len(journey.transitions)
        transitions.append("test")
        assert len(journey.transitions) == original_len


class TestSignatureIntegration:
    """Test signature field extraction for pathways."""

    def test_intake_signature_fields(self):
        """Test IntakeSignature has expected fields."""
        sig = IntakeSignature()

        # Input fields
        assert hasattr(sig, "patient_message")
        assert hasattr(sig, "conversation_history")

        # Output fields
        assert hasattr(sig, "symptoms")
        assert hasattr(sig, "severity")
        assert hasattr(sig, "preferences")
        assert hasattr(sig, "response")
        assert hasattr(sig, "ready_for_booking")

    def test_booking_signature_fields(self):
        """Test BookingSignature has expected fields."""
        sig = BookingSignature()

        # Input fields
        assert hasattr(sig, "patient_message")
        assert hasattr(sig, "symptoms")
        assert hasattr(sig, "preferences")
        assert hasattr(sig, "rejected_doctors")

        # Output fields
        assert hasattr(sig, "suggested_doctors")
        assert hasattr(sig, "selected_doctor")
        assert hasattr(sig, "booking_complete")

    def test_faq_signature_fields(self):
        """Test FAQSignature has expected fields."""
        sig = FAQSignature()

        assert hasattr(sig, "question")
        assert hasattr(sig, "current_context")
        assert hasattr(sig, "answer")
        assert hasattr(sig, "question_resolved")
        assert hasattr(sig, "response")

    def test_persuasion_signature_fields(self):
        """Test PersuasionSignature has expected fields."""
        sig = PersuasionSignature()

        assert hasattr(sig, "patient_message")
        assert hasattr(sig, "symptoms")
        assert hasattr(sig, "concerns_addressed")
        assert hasattr(sig, "ready_to_proceed")

    def test_confirmation_signature_fields(self):
        """Test ConfirmationSignature has expected fields."""
        sig = ConfirmationSignature()

        assert hasattr(sig, "doctor")
        assert hasattr(sig, "slot")
        assert hasattr(sig, "confirmation_number")
        assert hasattr(sig, "response")


class TestSignatureIntent:
    """Test signature __intent__ definitions."""

    def test_intake_has_intent(self):
        """Test IntakeSignature has intent."""
        assert IntakeSignature.__intent__ is not None
        assert (
            "symptom" in IntakeSignature.__intent__.lower()
            or "collect" in IntakeSignature.__intent__.lower()
        )

    def test_booking_has_intent(self):
        """Test BookingSignature has intent."""
        assert BookingSignature.__intent__ is not None
        assert (
            "specialist" in BookingSignature.__intent__.lower()
            or "booking" in BookingSignature.__intent__.lower()
        )

    def test_faq_has_intent(self):
        """Test FAQSignature has intent."""
        assert FAQSignature.__intent__ is not None
        assert (
            "answer" in FAQSignature.__intent__.lower()
            or "question" in FAQSignature.__intent__.lower()
        )

    def test_persuasion_has_intent(self):
        """Test PersuasionSignature has intent."""
        assert PersuasionSignature.__intent__ is not None
        assert (
            "hesitant" in PersuasionSignature.__intent__.lower()
            or "confident" in PersuasionSignature.__intent__.lower()
        )

    def test_confirmation_has_intent(self):
        """Test ConfirmationSignature has intent."""
        assert ConfirmationSignature.__intent__ is not None
        assert "confirm" in ConfirmationSignature.__intent__.lower()


class TestSignatureGuidelines:
    """Test signature __guidelines__ definitions."""

    def test_intake_has_guidelines(self):
        """Test IntakeSignature has guidelines."""
        guidelines = IntakeSignature.__guidelines__
        assert len(guidelines) > 0
        assert any(
            "empathetic" in g.lower() or "acknowledge" in g.lower() for g in guidelines
        )

    def test_booking_has_guidelines(self):
        """Test BookingSignature has guidelines."""
        guidelines = BookingSignature.__guidelines__
        assert len(guidelines) > 0
        assert any(
            "rejected" in g.lower() or "never suggest" in g.lower() for g in guidelines
        )

    def test_faq_has_guidelines(self):
        """Test FAQSignature has guidelines."""
        guidelines = FAQSignature.__guidelines__
        assert len(guidelines) > 0

    def test_persuasion_has_guidelines(self):
        """Test PersuasionSignature has guidelines."""
        guidelines = PersuasionSignature.__guidelines__
        assert len(guidelines) > 0
        assert any(
            "pushy" in g.lower() or "empathetic" in g.lower() for g in guidelines
        )

    def test_confirmation_has_guidelines(self):
        """Test ConfirmationSignature has guidelines."""
        guidelines = ConfirmationSignature.__guidelines__
        assert len(guidelines) > 0
        assert any(
            "summarize" in g.lower() or "detail" in g.lower() for g in guidelines
        )

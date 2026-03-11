"""
End-to-End Tests for Healthcare Referral Journey

Tests complete journey flows with OpenAI (real API, NO MOCKING).
These are Tier 3 tests requiring OpenAI API key.

Prerequisites:
    - OPENAI_API_KEY environment variable set
    - Or .env file with OPENAI_API_KEY

Run:
    pytest examples/journey/healthcare_referral/tests/test_e2e.py -v -m e2e

Cost Estimate:
    - Each test uses approximately $0.01-0.05 in API calls
    - Full test suite: ~$0.50
"""

import asyncio
import os
from typing import Any, Dict

import pytest

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from examples.journey.healthcare_referral.agents import (
    BookingAgent,
    BookingAgentConfig,
    ConfirmationAgent,
    ConfirmationAgentConfig,
    FAQAgent,
    FAQAgentConfig,
    IntakeAgent,
    IntakeAgentConfig,
    PersuasionAgent,
    PersuasionAgentConfig,
)
from examples.journey.healthcare_referral.journey import (
    HealthcareReferralJourney,
    default_config,
)
from kaizen.journey import JourneyConfig


def has_openai_key() -> bool:
    """Check if OpenAI API key is available."""
    return bool(os.getenv("OPENAI_API_KEY"))


# Skip all tests if OpenAI key not available
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not has_openai_key(), reason="OPENAI_API_KEY not set. Add to .env file."
    ),
]


@pytest.fixture
def openai_config():
    """Create OpenAI-based agent configs."""
    return {
        "intake": IntakeAgentConfig(llm_provider="openai", model="gpt-4o-mini"),
        "booking": BookingAgentConfig(llm_provider="openai", model="gpt-4o-mini"),
        "faq": FAQAgentConfig(llm_provider="openai", model="gpt-4o-mini"),
        "persuasion": PersuasionAgentConfig(llm_provider="openai", model="gpt-4o-mini"),
        "confirmation": ConfirmationAgentConfig(
            llm_provider="openai", model="gpt-4o-mini"
        ),
    }


@pytest.fixture
def openai_agents(openai_config):
    """Create real agents with OpenAI."""
    from examples.journey.healthcare_referral.agents.booking_agent import (
        MockDoctorDatabase,
    )

    return {
        "intake_agent": IntakeAgent(openai_config["intake"]),
        "booking_agent": BookingAgent(
            openai_config["booking"], doctor_database=MockDoctorDatabase()
        ),
        "faq_agent": FAQAgent(openai_config["faq"]),
        "persuasion_agent": PersuasionAgent(openai_config["persuasion"]),
        "confirmation_agent": ConfirmationAgent(openai_config["confirmation"]),
    }


@pytest.fixture
def e2e_journey_config():
    """Create journey config for E2E tests."""
    return JourneyConfig(
        intent_detection_model="gpt-4o-mini",
        intent_confidence_threshold=0.75,
        context_persistence="memory",
        max_pathway_depth=15,
        pathway_timeout_seconds=60.0,
    )


class TestE2EIntakeFlow:
    """E2E tests for intake flow."""

    @pytest.mark.asyncio
    async def test_intake_extracts_comprehensive_info(self, openai_config):
        """Test intake extracts symptoms, severity, and preferences."""
        agent = IntakeAgent(openai_config["intake"])

        result = await agent.process_intake(
            patient_message=(
                "I've been having moderate back pain for about 3 weeks now. "
                "It's worse when I sit for long periods. "
                "I'd prefer a female doctor if possible, and morning appointments work best. "
                "I have Blue Cross insurance."
            ),
            conversation_history=[],
        )

        # Should have comprehensive extraction
        assert "response" in result

        # Should extract symptoms
        if "symptoms" in result and result["symptoms"]:
            assert any("back" in s.lower() for s in result["symptoms"])

        # Should identify severity
        if "severity" in result and result["severity"]:
            assert result["severity"].lower() in [
                "mild",
                "moderate",
                "severe",
                "urgent",
            ]

        # Should extract preferences
        if "preferences" in result and result["preferences"]:
            prefs = result["preferences"]
            assert any(key in str(prefs).lower() for key in ["female", "morning"])

    @pytest.mark.asyncio
    async def test_intake_asks_clarifying_questions(self, openai_config):
        """Test intake asks for more info when needed."""
        agent = IntakeAgent(openai_config["intake"])

        result = await agent.process_intake(
            patient_message="My back hurts",
            conversation_history=[],
        )

        assert "response" in result
        response = result["response"]

        # Should ask clarifying questions
        assert "?" in response or any(
            phrase in response.lower()
            for phrase in ["tell me more", "how long", "describe", "when did"]
        )

        # Should NOT be ready for booking yet
        if "ready_for_booking" in result:
            assert result["ready_for_booking"] is False


class TestE2EFAQFlow:
    """E2E tests for FAQ flow."""

    @pytest.mark.asyncio
    async def test_faq_answers_specialist_question(self, openai_config):
        """Test FAQ answers question about specialists."""
        agent = FAQAgent(openai_config["faq"])

        result = await agent.answer_question(
            question="What's the difference between an orthopedist and a physical therapist?",
            current_context={"symptoms": ["back pain"]},
        )

        assert "response" in result or "answer" in result
        response = result.get("response", result.get("answer", ""))

        # Should mention both specialists
        response_lower = response.lower()
        assert "orthopedist" in response_lower or "orthopedic" in response_lower
        assert (
            "physical therapist" in response_lower
            or "physical therapy" in response_lower
        )

    @pytest.mark.asyncio
    async def test_faq_stays_in_scope(self, openai_config):
        """Test FAQ stays within healthcare referral scope."""
        agent = FAQAgent(openai_config["faq"])

        result = await agent.answer_question(
            question="What's the weather like today?",
            current_context={},
        )

        assert "response" in result
        response = result["response"].lower()

        # Should politely redirect or explain scope
        assert any(
            phrase in response
            for phrase in [
                "healthcare",
                "referral",
                "booking",
                "appointment",
                "outside",
                "scope",
                "help you",
                "medical",
            ]
        )


class TestE2EPersuasionFlow:
    """E2E tests for persuasion flow."""

    @pytest.mark.asyncio
    async def test_persuasion_addresses_cost_concern(self, openai_config):
        """Test persuasion addresses cost concerns empathetically."""
        agent = PersuasionAgent(openai_config["persuasion"])

        result = await agent.address_hesitation(
            patient_message="I'm worried about the cost. I don't know if I can afford this.",
            symptoms=["back pain", "stiffness"],
            hesitation_reason="cost",
        )

        assert "response" in result
        response = result["response"].lower()

        # Should acknowledge concern
        assert any(
            phrase in response
            for phrase in [
                "understand",
                "concern",
                "cost",
                "insurance",
                "affordable",
                "worth",
            ]
        )

    @pytest.mark.asyncio
    async def test_persuasion_not_pushy(self, openai_config):
        """Test persuasion respects patient's hesitation."""
        agent = PersuasionAgent(openai_config["persuasion"])

        result = await agent.address_hesitation(
            patient_message="I need more time to think about this.",
            symptoms=["mild back pain"],
            hesitation_reason="timing",
        )

        assert "response" in result
        response = result["response"].lower()

        # Should NOT be pushy
        assert not any(
            phrase in response
            for phrase in ["must book now", "don't wait", "you have to"]
        )

        # Should respect their timing
        assert any(
            phrase in response
            for phrase in [
                "understand",
                "take your time",
                "when you're ready",
                "here",
                "available",
            ]
        )


class TestE2ECompleteJourney:
    """E2E tests for complete journey flow."""

    @pytest.mark.asyncio
    async def test_complete_intake_to_booking(self, openai_agents, e2e_journey_config):
        """Test complete flow from intake to booking."""
        journey = HealthcareReferralJourney(
            session_id="e2e-test-complete-001",
            config=e2e_journey_config,
        )

        for agent_id, agent in openai_agents.items():
            journey.register_agent(agent_id, agent)

        session = await journey.start()
        assert session.current_pathway_id == "intake"

        # Initial symptom description
        r1 = await journey.process_message(
            "I've been having moderate back pain for two weeks. "
            "It's worse when I sit at my desk."
        )
        assert r1.pathway_id == "intake"
        assert r1.message is not None
        assert len(r1.message) > 0

        # Provide preferences
        r2 = await journey.process_message(
            "I prefer morning appointments with a female doctor. "
            "I have Aetna insurance."
        )

        # May still be in intake or moved to booking
        assert r2.pathway_id in ["intake", "booking"]

        # If still in intake, confirm ready
        if r2.pathway_id == "intake":
            r3 = await journey.process_message(
                "Yes, I think that's all the information. I'm ready to see doctors."
            )
            # Should now be in booking or have booking options
            assert r3.message is not None

    @pytest.mark.asyncio
    async def test_faq_detour_and_return(self, openai_agents, e2e_journey_config):
        """Test FAQ detour from booking and return."""
        journey = HealthcareReferralJourney(
            session_id="e2e-test-faq-001",
            config=e2e_journey_config,
        )

        for agent_id, agent in openai_agents.items():
            journey.register_agent(agent_id, agent)

        await journey.start()

        # Quick intake
        await journey.process_message(
            "I have moderate back pain for 2 weeks. "
            "I prefer morning appointments with a female doctor. "
            "I have Blue Cross insurance. I'm ready to book."
        )

        # Trigger FAQ with question
        faq_response = await journey.process_message(
            "What's the difference between an orthopedist and a chiropractor?"
        )

        # Should be in FAQ pathway or have answered inline
        assert faq_response.message is not None
        response_lower = faq_response.message.lower()
        assert (
            "orthopedist" in response_lower
            or "orthopedic" in response_lower
            or "doctor" in response_lower
        )


class TestE2EEdgeCases:
    """E2E tests for edge cases."""

    @pytest.mark.asyncio
    async def test_handles_empty_message(self, openai_agents, e2e_journey_config):
        """Test journey handles empty or minimal messages gracefully."""
        journey = HealthcareReferralJourney(
            session_id="e2e-test-empty-001",
            config=e2e_journey_config,
        )

        for agent_id, agent in openai_agents.items():
            journey.register_agent(agent_id, agent)

        await journey.start()

        # Send minimal message
        response = await journey.process_message("hi")

        # Should respond gracefully
        assert response.message is not None
        assert len(response.message) > 0

    @pytest.mark.asyncio
    async def test_handles_off_topic_message(self, openai_agents, e2e_journey_config):
        """Test journey handles off-topic messages."""
        journey = HealthcareReferralJourney(
            session_id="e2e-test-offtopic-001",
            config=e2e_journey_config,
        )

        for agent_id, agent in openai_agents.items():
            journey.register_agent(agent_id, agent)

        await journey.start()

        # Send off-topic message
        response = await journey.process_message(
            "What do you think about the latest sports game?"
        )

        # Should redirect to healthcare context
        assert response.message is not None
        # Should mention healthcare/booking context
        response_lower = response.message.lower()
        assert any(
            phrase in response_lower
            for phrase in ["health", "help", "appoint", "symptom", "special", "doctor"]
        )


class TestE2EQualityAssurance:
    """E2E tests for response quality."""

    @pytest.mark.asyncio
    async def test_intake_response_is_empathetic(self, openai_config):
        """Test intake responses show empathy."""
        agent = IntakeAgent(openai_config["intake"])

        result = await agent.process_intake(
            patient_message="I've been in constant pain for weeks and I'm really worried.",
            conversation_history=[],
        )

        assert "response" in result
        response = result["response"].lower()

        # Should show empathy
        assert any(
            phrase in response
            for phrase in [
                "sorry to hear",
                "understand",
                "must be",
                "that sounds",
                "here to help",
                "concerned",
                "difficult",
            ]
        )

    @pytest.mark.asyncio
    async def test_booking_explains_doctor_matches(self, openai_config):
        """Test booking explains why doctors are good matches."""
        from examples.journey.healthcare_referral.agents.booking_agent import (
            MockDoctorDatabase,
        )

        agent = BookingAgent(
            openai_config["booking"],
            doctor_database=MockDoctorDatabase(),
        )

        result = await agent.find_doctors(
            patient_message="Show me specialists for my back pain",
            symptoms=["back pain", "stiffness"],
            preferences={"time_preference": "morning"},
            rejected_doctors=[],
        )

        assert "response" in result
        response = result["response"]

        # Response should explain matches
        assert len(response) > 100  # Substantial explanation

    @pytest.mark.asyncio
    async def test_confirmation_is_comprehensive(self, openai_config):
        """Test confirmation includes all necessary details."""
        agent = ConfirmationAgent(openai_config["confirmation"])

        result = await agent.confirm_booking(
            doctor={
                "id": "dr-chen-001",
                "name": "Dr. Sarah Chen",
                "specialty": "Orthopedics",
                "location": "Downtown Medical Center",
                "telehealth": True,
            },
            slot="2024-01-15T09:00:00",
            patient_info={
                "symptoms": ["back pain", "stiffness"],
                "insurance": "Blue Cross",
            },
        )

        assert "response" in result
        response = result["response"].lower()

        # Should include key details
        assert "dr" in response or "chen" in response or "doctor" in response
        assert any(time in response for time in ["9", "morning", "january", "15"])

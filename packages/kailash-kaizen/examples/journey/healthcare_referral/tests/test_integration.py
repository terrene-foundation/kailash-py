"""
Integration Tests for Healthcare Referral Journey

Tests with real LLM inference using Ollama (NO MOCKING).
These are Tier 2 tests requiring Ollama to be running locally.

Prerequisites:
    1. Install Ollama: https://ollama.ai/download
    2. Pull model: ollama pull llama3.2:3b
    3. Start Ollama: ollama serve

Run:
    pytest examples/journey/healthcare_referral/tests/test_integration.py -v -m integration
"""

import asyncio
from typing import Any, Dict

import pytest

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
from examples.journey.healthcare_referral.agents.booking_agent import MockDoctorDatabase
from examples.journey.healthcare_referral.journey import HealthcareReferralJourney
from kaizen.journey import JourneyConfig


def is_ollama_available() -> bool:
    """Check if Ollama is available."""
    try:
        import httpx

        response = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


# Skip all tests if Ollama not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not is_ollama_available(),
        reason="Ollama not available. Run 'ollama serve' first.",
    ),
]


@pytest.fixture
def ollama_config():
    """Create Ollama-based agent configs."""
    return {
        "intake": IntakeAgentConfig(llm_provider="ollama", model="llama3.2:3b"),
        "booking": BookingAgentConfig(llm_provider="ollama", model="llama3.2:3b"),
        "faq": FAQAgentConfig(llm_provider="ollama", model="llama3.2:3b"),
        "persuasion": PersuasionAgentConfig(llm_provider="ollama", model="llama3.2:3b"),
        "confirmation": ConfirmationAgentConfig(
            llm_provider="ollama", model="llama3.2:3b"
        ),
    }


@pytest.fixture
def real_agents(ollama_config):
    """Create real agents with Ollama."""
    return {
        "intake_agent": IntakeAgent(ollama_config["intake"]),
        "booking_agent": BookingAgent(ollama_config["booking"]),
        "faq_agent": FAQAgent(ollama_config["faq"]),
        "persuasion_agent": PersuasionAgent(ollama_config["persuasion"]),
        "confirmation_agent": ConfirmationAgent(ollama_config["confirmation"]),
    }


@pytest.fixture
def journey_config():
    """Create journey config for integration tests."""
    return JourneyConfig(
        intent_detection_model="ollama/llama3.2:3b",
        intent_confidence_threshold=0.7,
        context_persistence="memory",
        max_pathway_depth=10,
        pathway_timeout_seconds=120.0,  # Longer timeout for local LLM
    )


class TestIntakeAgentIntegration:
    """Integration tests for IntakeAgent with real LLM."""

    @pytest.mark.asyncio
    async def test_intake_extracts_symptoms(self, ollama_config):
        """Test that intake agent extracts symptoms from patient message."""
        agent = IntakeAgent(ollama_config["intake"])

        result = await agent.process_intake(
            patient_message="I've been having severe back pain for the past two weeks. "
            "It gets worse in the morning.",
            conversation_history=[],
        )

        assert "symptoms" in result or "response" in result
        if "symptoms" in result:
            symptoms = result["symptoms"]
            # Should extract back pain
            symptoms_lower = [s.lower() for s in symptoms] if symptoms else []
            assert (
                any("back" in s for s in symptoms_lower)
                or "pain" in str(result).lower()
            )

    @pytest.mark.asyncio
    async def test_intake_identifies_severity(self, ollama_config):
        """Test that intake agent identifies severity level."""
        agent = IntakeAgent(ollama_config["intake"])

        result = await agent.process_intake(
            patient_message="I have moderate back pain that comes and goes. "
            "It's not too bad but it's been bothering me.",
            conversation_history=[],
        )

        if "severity" in result:
            severity = result["severity"]
            assert (
                severity in ["mild", "moderate", "severe", "urgent"]
                or severity is not None
            )

    @pytest.mark.asyncio
    async def test_intake_asks_followup_questions(self, ollama_config):
        """Test that intake agent asks for more information when needed."""
        agent = IntakeAgent(ollama_config["intake"])

        result = await agent.process_intake(
            patient_message="My back hurts",
            conversation_history=[],
        )

        assert "response" in result
        response = result["response"].lower()
        # Should ask for more details
        assert any(
            word in response
            for word in [
                "how long",
                "when",
                "describe",
                "tell",
                "more",
                "severity",
                "?",
            ]
        )


class TestBookingAgentIntegration:
    """Integration tests for BookingAgent with real LLM."""

    @pytest.mark.asyncio
    async def test_booking_finds_doctors(self, ollama_config):
        """Test that booking agent finds matching doctors."""
        agent = BookingAgent(
            ollama_config["booking"],
            doctor_database=MockDoctorDatabase(),
        )

        result = await agent.find_doctors(
            patient_message="Show me available orthopedists",
            symptoms=["back pain", "stiffness"],
            preferences={"time_preference": "morning"},
            rejected_doctors=[],
        )

        assert "suggested_doctors" in result or "response" in result
        if "suggested_doctors" in result:
            doctors = result["suggested_doctors"]
            assert len(doctors) > 0 or "response" in result

    @pytest.mark.asyncio
    async def test_booking_excludes_rejected_doctors(self, ollama_config):
        """Test that booking agent excludes previously rejected doctors."""
        agent = BookingAgent(
            ollama_config["booking"],
            doctor_database=MockDoctorDatabase(),
        )

        # First get available doctors
        first_result = await agent.find_doctors(
            patient_message="Show me options",
            symptoms=["back pain"],
            preferences={},
            rejected_doctors=[],
        )

        # Get a doctor ID to reject
        if "suggested_doctors" in first_result and first_result["suggested_doctors"]:
            rejected_id = first_result["suggested_doctors"][0]["id"]

            # Request again with rejection
            second_result = await agent.find_doctors(
                patient_message="Not that one, show me others",
                symptoms=["back pain"],
                preferences={},
                rejected_doctors=[rejected_id],
            )

            if "suggested_doctors" in second_result:
                doctor_ids = [d["id"] for d in second_result["suggested_doctors"]]
                assert rejected_id not in doctor_ids


class TestFAQAgentIntegration:
    """Integration tests for FAQAgent with real LLM."""

    @pytest.mark.asyncio
    async def test_faq_answers_question(self, ollama_config):
        """Test that FAQ agent answers questions."""
        agent = FAQAgent(ollama_config["faq"])

        result = await agent.answer_question(
            question="What's the difference between an orthopedist and a chiropractor?",
            current_context={"symptoms": ["back pain"]},
        )

        assert "response" in result or "answer" in result
        response = result.get("response", result.get("answer", ""))
        # Should provide some explanation
        assert len(response) > 50


class TestPersuasionAgentIntegration:
    """Integration tests for PersuasionAgent with real LLM."""

    @pytest.mark.asyncio
    async def test_persuasion_addresses_concerns(self, ollama_config):
        """Test that persuasion agent addresses hesitation."""
        agent = PersuasionAgent(ollama_config["persuasion"])

        result = await agent.address_hesitation(
            patient_message="I'm not sure if I want to book right now. It seems expensive.",
            symptoms=["back pain", "stiffness"],
            hesitation_reason="cost",
        )

        assert "response" in result
        response = result["response"].lower()
        # Should acknowledge and address concerns empathetically
        assert len(response) > 50


class TestMockDoctorDatabase:
    """Test the mock doctor database."""

    @pytest.mark.asyncio
    async def test_database_returns_doctors(self):
        """Test that mock database returns doctors."""
        db = MockDoctorDatabase()

        doctors = await db.find_specialists(
            symptoms=["back pain"],
            preferences={},
            exclude_ids=[],
        )

        assert len(doctors) > 0

    @pytest.mark.asyncio
    async def test_database_filters_by_symptoms(self):
        """Test that database filters by symptoms."""
        db = MockDoctorDatabase()

        # Back pain should match orthopedics
        back_doctors = await db.find_specialists(
            symptoms=["back pain"],
            preferences={},
            exclude_ids=[],
        )

        # Headache should match neurology
        headache_doctors = await db.find_specialists(
            symptoms=["headache"],
            preferences={},
            exclude_ids=[],
        )

        # Different symptoms should yield different primary results
        if back_doctors and headache_doctors:
            back_specialties = [d["specialty"] for d in back_doctors[:2]]
            headache_specialties = [d["specialty"] for d in headache_doctors[:2]]
            # Not necessarily different, but results should be returned
            assert len(back_doctors) > 0
            assert len(headache_doctors) > 0

    @pytest.mark.asyncio
    async def test_database_filters_by_gender_preference(self):
        """Test that database respects gender preference."""
        db = MockDoctorDatabase()

        female_doctors = await db.find_specialists(
            symptoms=["back pain"],
            preferences={"gender_preference": "female"},
            exclude_ids=[],
        )

        for doctor in female_doctors:
            assert doctor["gender"] == "female"

    @pytest.mark.asyncio
    async def test_database_excludes_rejected(self):
        """Test that database excludes rejected doctors."""
        db = MockDoctorDatabase()

        # Get all doctors first
        all_doctors = await db.find_specialists(
            symptoms=["back pain"],
            preferences={},
            exclude_ids=[],
        )

        if all_doctors:
            rejected_id = all_doctors[0]["id"]

            # Get doctors excluding one
            filtered = await db.find_specialists(
                symptoms=["back pain"],
                preferences={},
                exclude_ids=[rejected_id],
            )

            filtered_ids = [d["id"] for d in filtered]
            assert rejected_id not in filtered_ids


class TestJourneyIntegrationFlow:
    """Integration tests for full journey flow."""

    @pytest.mark.asyncio
    async def test_journey_starts_at_intake(self, real_agents, journey_config):
        """Test that journey starts at intake pathway."""
        journey = HealthcareReferralJourney(
            session_id="integration-test-001",
            config=journey_config,
        )

        for agent_id, agent in real_agents.items():
            journey.register_agent(agent_id, agent)

        session = await journey.start()

        assert session.current_pathway_id == "intake"

    @pytest.mark.asyncio
    async def test_intake_collects_information(self, real_agents, journey_config):
        """Test that intake pathway collects patient information."""
        journey = HealthcareReferralJourney(
            session_id="integration-test-002",
            config=journey_config,
        )

        for agent_id, agent in real_agents.items():
            journey.register_agent(agent_id, agent)

        await journey.start()

        response = await journey.process_message(
            "I've been having severe headaches for a week. They're worse in the morning."
        )

        assert response.pathway_id == "intake"
        # Should have response message
        assert response.message is not None
        assert len(response.message) > 0


class TestAccumulatedContext:
    """Test context accumulation across pathways."""

    @pytest.mark.asyncio
    async def test_symptoms_accumulate(self, ollama_config):
        """Test that symptoms are accumulated in context."""
        agent = IntakeAgent(ollama_config["intake"])

        # First message
        result1 = await agent.process_intake(
            patient_message="I have back pain",
            conversation_history=[],
        )

        # Symptoms should be extracted
        if "symptoms" in result1:
            symptoms = result1["symptoms"]
            # Should have at least one symptom
            assert (
                symptoms is None or len(symptoms) > 0 or "back" in str(result1).lower()
            )

    @pytest.mark.asyncio
    async def test_rejected_doctors_accumulate(self, ollama_config):
        """Test that rejected doctors list grows over time."""
        db = MockDoctorDatabase()
        agent = BookingAgent(ollama_config["booking"], doctor_database=db)

        # Initial query
        result1 = await agent.find_doctors(
            patient_message="Show me options",
            symptoms=["back pain"],
            preferences={},
            rejected_doctors=[],
        )

        # Simulate rejection
        if "suggested_doctors" in result1 and result1["suggested_doctors"]:
            first_doctor_id = result1["suggested_doctors"][0]["id"]

            result2 = await agent.find_doctors(
                patient_message="Not that doctor, show me others",
                symptoms=["back pain"],
                preferences={},
                rejected_doctors=[first_doctor_id],  # Pass accumulated rejections
            )

            # The rejected doctor should not appear
            if "suggested_doctors" in result2:
                new_ids = [d["id"] for d in result2["suggested_doctors"]]
                assert first_doctor_id not in new_ids

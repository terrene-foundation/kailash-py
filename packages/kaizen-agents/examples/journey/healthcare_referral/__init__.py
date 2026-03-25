"""
Healthcare Referral Journey - Reference Implementation

This example demonstrates Layer 5 Journey Orchestration with:
- Multi-pathway navigation (5 pathways)
- Intent-driven transitions
- Context accumulation
- Detour pathways with return behavior
- Persuasion and confirmation patterns

Use Case:
    Patient wants to see a specialist for their health concern.
    The journey guides them through:
    1. Intake - Collecting symptoms, severity, preferences, insurance
    2. Booking - Finding and selecting a doctor
    3. Confirmation - Finalizing the appointment

    With detour pathways for:
    - FAQ - Answering questions (returns to previous)
    - Persuasion - Addressing hesitation

Example:
    from examples.journey.healthcare_referral import (
        HealthcareReferralJourney,
        default_config,
        IntakeAgent,
        BookingAgent,
        FAQAgent,
        PersuasionAgent,
    )

    journey = HealthcareReferralJourney(session_id="patient-123")
    journey.register_agent("intake_agent", IntakeAgent())
    journey.register_agent("booking_agent", BookingAgent())
    journey.register_agent("faq_agent", FAQAgent())
    journey.register_agent("persuasion_agent", PersuasionAgent())

    session = await journey.start()
    response = await journey.process_message("I need to see a specialist for my back pain")
"""

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
from examples.journey.healthcare_referral.signatures import (
    BookingSignature,
    ConfirmationSignature,
    FAQSignature,
    IntakeSignature,
    PersuasionSignature,
)

__all__ = [
    # Journey
    "HealthcareReferralJourney",
    "default_config",
    # Signatures
    "IntakeSignature",
    "BookingSignature",
    "FAQSignature",
    "PersuasionSignature",
    "ConfirmationSignature",
    # Agents
    "IntakeAgent",
    "IntakeAgentConfig",
    "BookingAgent",
    "BookingAgentConfig",
    "FAQAgent",
    "FAQAgentConfig",
    "PersuasionAgent",
    "PersuasionAgentConfig",
    "ConfirmationAgent",
    "ConfirmationAgentConfig",
]

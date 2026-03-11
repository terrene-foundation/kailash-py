"""
Healthcare Referral Journey - Main Journey Definition

Defines the complete healthcare referral journey with 5 nested pathways,
global transitions, and context accumulation.

Architecture:
    +-------------------------------------------------------------------------------+
    |                    HEALTHCARE REFERRAL JOURNEY                                 |
    |                                                                                |
    |  +-------------------------------------------------------------------------+  |
    |  |                           INTAKE PATHWAY                                |  |
    |  |  Collect: symptoms, severity, preferences, insurance                    |  |
    |  |  Accumulate: symptoms, severity, preferences, insurance_info            |  |
    |  |  Next: booking                                                          |  |
    |  +---------------------------------+---------------------------------------+  |
    |                                    |                                          |
    |                                    v                                          |
    |  +-------------------------------------------------------------------------+  |
    |  |                          BOOKING PATHWAY                                |  |
    |  |  Find: available doctors matching preferences                           |  |
    |  |  Present: options with times                                            |  |
    |  |  Handle: doctor rejections -> accumulate rejected_doctors               |  |
    |  |  Next: confirmation (on selection)                                      |  |
    |  +---------------------------------+---------------------------------------+  |
    |                                    |                                          |
    |          +-------------------------+-------------------------+                |
    |          |                         |                         |                |
    |          v                         v                         v                |
    |  +---------------+  +----------------------+  +--------------------+          |
    |  |  FAQ PATHWAY  |  | PERSUASION PATHWAY   |  | CONFIRMATION       |          |
    |  |  (detour)     |  | (when user hesitates)|  | PATHWAY            |          |
    |  |               |  |                      |  |                    |          |
    |  |  Return to    |  |  Highlight benefits  |  |  Confirm details   |          |
    |  |  previous     |  |  Address concerns    |  |  Send confirmation |          |
    |  |  pathway      |  |  Next: booking       |  |  End journey       |          |
    |  +---------------+  +----------------------+  +--------------------+          |
    |                                                                                |
    +-------------------------------------------------------------------------------+

Usage:
    from examples.journey.healthcare_referral.journey import (
        HealthcareReferralJourney,
        default_config,
    )

    journey = HealthcareReferralJourney(session_id="patient-123")
    journey.register_agent("intake_agent", intake_agent)
    session = await journey.start()
    response = await journey.process_message("I need to see a specialist")
"""

from examples.journey.healthcare_referral.signatures.booking import BookingSignature
from examples.journey.healthcare_referral.signatures.confirmation import (
    ConfirmationSignature,
)
from examples.journey.healthcare_referral.signatures.faq import FAQSignature
from examples.journey.healthcare_referral.signatures.intake import IntakeSignature
from examples.journey.healthcare_referral.signatures.persuasion import (
    PersuasionSignature,
)
from kaizen.journey import (
    ConditionTrigger,
    IntentTrigger,
    Journey,
    JourneyConfig,
    Pathway,
    Transition,
)
from kaizen.journey.behaviors import ReturnToPrevious


class HealthcareReferralJourney(Journey):
    """
    Healthcare specialist referral journey.

    Guides patients through the process of booking a specialist appointment:

    1. **Intake** - Collecting symptoms, severity, preferences, and insurance
    2. **Booking** - Finding and selecting a doctor from available options
    3. **Confirmation** - Finalizing the appointment

    With detour pathways for:
    - **FAQ** - Answering questions (returns to previous pathway)
    - **Persuasion** - Addressing hesitation (returns to booking)

    Key Features:
    - Intent-based global transitions (FAQ from any pathway)
    - Context accumulation (symptoms, preferences, rejected_doctors)
    - ReturnToPrevious behavior for FAQ detour
    - Rejection tracking to avoid re-suggesting doctors

    Example:
        >>> journey = HealthcareReferralJourney(session_id="patient-123")
        >>> journey.register_agent("intake_agent", IntakeAgent())
        >>> journey.register_agent("booking_agent", BookingAgent())
        >>> journey.register_agent("faq_agent", FAQAgent())
        >>> journey.register_agent("persuasion_agent", PersuasionAgent())
        >>> journey.register_agent("confirmation_agent", ConfirmationAgent())
        >>>
        >>> session = await journey.start()
        >>> response = await journey.process_message("I have back pain")
        >>> print(f"Current pathway: {response.pathway_id}")
    """

    __entry_pathway__ = "intake"

    __transitions__ = [
        # Global FAQ transition - triggers from any pathway
        # Handles questions like "What is a specialist?", "How does insurance work?"
        Transition(
            trigger=IntentTrigger(
                patterns=[
                    "what is",
                    "what are",
                    "what's",
                    "how does",
                    "how do",
                    "can you explain",
                    "tell me about",
                    "question",
                    "help",
                    "difference between",
                ],
                use_llm_fallback=True,
                confidence_threshold=0.75,
            ),
            from_pathway="*",  # Any pathway
            to_pathway="faq",
            priority=10,
        ),
        # Hesitation detection - triggers during booking only
        # Handles messages like "I'm not sure", "Maybe I should wait"
        Transition(
            trigger=IntentTrigger(
                patterns=[
                    "not sure",
                    "not certain",
                    "hesitant",
                    "unsure",
                    "maybe later",
                    "think about it",
                    "i don't know",
                    "need to think",
                    "on second thought",
                ],
                use_llm_fallback=True,
                confidence_threshold=0.70,
            ),
            from_pathway=["booking"],  # Only from booking
            to_pathway="persuasion",
            priority=5,
        ),
        # Cancellation request - handles explicit cancellation
        Transition(
            trigger=IntentTrigger(
                patterns=[
                    "cancel",
                    "stop",
                    "nevermind",
                    "never mind",
                    "forget it",
                    "quit",
                    "exit",
                ],
                use_llm_fallback=False,  # Exact match only for safety
                confidence_threshold=0.90,
            ),
            from_pathway="*",
            to_pathway=None,  # End journey
            priority=20,  # High priority to catch explicit cancellation
        ),
        # Booking complete condition - transition to confirmation
        Transition(
            trigger=ConditionTrigger(
                condition=lambda ctx: ctx.get("booking_complete", False),
                description="Booking complete, proceed to confirmation",
            ),
            from_pathway="booking",
            to_pathway="confirmation",
            priority=1,
        ),
        # Intake ready condition - transition to booking
        Transition(
            trigger=ConditionTrigger(
                condition=lambda ctx: ctx.get("ready_for_booking", False),
                description="Intake complete, proceed to booking",
            ),
            from_pathway="intake",
            to_pathway="booking",
            priority=1,
        ),
    ]

    # =========================================================================
    # INTAKE PATHWAY
    # =========================================================================
    class IntakePath(Pathway):
        """
        Collect patient symptoms and preferences.

        This is the entry pathway where we gather information about:
        - Symptoms and their severity
        - Patient preferences (time, gender, telehealth, location)
        - Insurance information

        Accumulated fields persist across pathways for use in booking.
        """

        __signature__ = IntakeSignature
        __agents__ = ["intake_agent"]
        __pipeline__ = "sequential"

        # Accumulate these fields for later pathways
        __accumulate__ = [
            "symptoms",
            "severity",
            "preferences",
            "insurance_info",
        ]

        # Pathway-specific guidelines (merged with signature)
        __guidelines__ = [
            "If patient provides minimal info, ask clarifying questions",
            "Proceed to booking only when ready_for_booking is True",
            "Be patient with gradual information collection across multiple turns",
        ]

        # Transition to booking when ready (also handled by condition trigger)
        __next__ = "booking"

    # =========================================================================
    # BOOKING PATHWAY
    # =========================================================================
    class BookingPath(Pathway):
        """
        Present doctor options and handle selection.

        Uses accumulated symptoms and preferences to find matching doctors.
        Tracks rejected doctors to avoid re-suggesting them.

        The booking is complete when selected_doctor and selected_slot are set.
        """

        __signature__ = BookingSignature
        __agents__ = ["booking_agent"]
        __pipeline__ = "sequential"

        # Track rejected doctors across turns
        __accumulate__ = [
            "rejected_doctors",
            "selected_doctor",
            "selected_slot",
            "booking_complete",
        ]

        __guidelines__ = [
            "Filter out rejected doctors from suggestions",
            "Present at most 3 options per turn",
            "Explain why each doctor is a good match for the patient's symptoms",
        ]

        # Transition to confirmation when complete (also handled by condition trigger)
        __next__ = "confirmation"

    # =========================================================================
    # FAQ PATHWAY (Detour)
    # =========================================================================
    class FAQPath(Pathway):
        """
        Answer patient questions.

        This is a detour pathway that can be triggered from any other pathway
        when the patient has a question. After answering, the journey returns
        to the previous pathway with context preserved.

        Example questions:
        - "What's the difference between an orthopedist and a chiropractor?"
        - "How does my insurance work for referrals?"
        - "What should I expect at my first visit?"
        """

        __signature__ = FAQSignature
        __agents__ = ["faq_agent"]
        __pipeline__ = "sequential"

        # Return to previous pathway after answering
        __return_behavior__ = ReturnToPrevious(
            preserve_context=True,
            max_depth=3,  # Prevent too many nested detours
        )

        __guidelines__ = [
            "After answering, offer to return to the booking process",
            "Keep answers focused and not overly long",
        ]

    # =========================================================================
    # PERSUASION PATHWAY
    # =========================================================================
    class PersuasionPath(Pathway):
        """
        Address hesitation and encourage booking.

        Triggered when patient expresses uncertainty during booking.
        Aims to address concerns empathetically without being pushy.

        After addressing concerns, returns to booking pathway.
        """

        __signature__ = PersuasionSignature
        __agents__ = ["persuasion_agent"]
        __pipeline__ = "sequential"

        __guidelines__ = [
            "Be empathetic, not pushy",
            "Acknowledge their concerns before addressing them",
            "Respect their decision if they want to wait",
        ]

        # Return to booking after addressing concerns
        __next__ = "booking"

    # =========================================================================
    # CONFIRMATION PATHWAY
    # =========================================================================
    class ConfirmationPath(Pathway):
        """
        Confirm the booking.

        Terminal pathway - no __next__ defined.
        Provides complete confirmation with:
        - Appointment details (date, time, doctor, location)
        - Preparation instructions
        - Cancellation/rescheduling information
        """

        __signature__ = ConfirmationSignature
        __agents__ = ["confirmation_agent"]
        __pipeline__ = "sequential"

        __guidelines__ = [
            "Provide a complete, well-formatted confirmation",
            "End with a warm, reassuring message",
        ]

        # Terminal pathway - no __next__


# ============================================================================
# DEFAULT CONFIGURATION
# ============================================================================

default_config = JourneyConfig(
    # Intent detection
    intent_detection_model="gpt-4o-mini",
    intent_confidence_threshold=0.75,
    intent_cache_ttl_seconds=300,
    # Pathway execution
    max_pathway_depth=15,  # Allow reasonable nesting (intake -> faq -> booking -> faq -> etc.)
    pathway_timeout_seconds=60.0,
    # Context
    max_context_size_bytes=1024 * 512,  # 512KB
    context_persistence="memory",  # Use "dataflow" for production persistence
    # Error handling
    error_recovery="graceful",
    max_retries=3,
)


# Alternate configuration for production with DataFlow persistence
production_config = JourneyConfig(
    intent_detection_model="gpt-4o-mini",
    intent_confidence_threshold=0.75,
    intent_cache_ttl_seconds=600,  # Longer cache in production
    max_pathway_depth=15,
    pathway_timeout_seconds=90.0,  # More time in production
    max_context_size_bytes=1024 * 1024,  # 1MB
    context_persistence="dataflow",  # Persistent storage
    error_recovery="graceful",
    max_retries=5,
)


__all__ = [
    "HealthcareReferralJourney",
    "default_config",
    "production_config",
]

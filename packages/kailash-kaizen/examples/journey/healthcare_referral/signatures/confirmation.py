"""
Confirmation Signature - Booking Finalization

Confirms and finalizes the appointment booking with all necessary details.
"""

from typing import Any, Dict

from kaizen.signatures import InputField, OutputField, Signature


class ConfirmationSignature(Signature):
    """
    Confirm and finalize the appointment booking.

    This signature is used in the terminal confirmation pathway to provide
    the patient with a clear summary of their booking, preparation instructions,
    and a warm closing message.

    Key Features:
        - Summarizes all booking details clearly
        - Includes date, time, doctor name, location/telehealth link
        - Provides preparation instructions
        - Includes cancellation/rescheduling information
        - Ends with a reassuring message

    Example:
        >>> agent = ConfirmationAgent(config)
        >>> result = agent.run(
        ...     doctor={"id": "dr-chen-002", "name": "Dr. Sarah Chen", "specialty": "Orthopedics"},
        ...     slot="2024-01-15T09:00:00",
        ...     patient_info={"symptoms": ["back pain"], "insurance": "Blue Cross"}
        ... )
        >>> print(result["confirmation_number"])
        "HC-2024-0115-001"
    """

    __intent__ = "Provide clear appointment confirmation with all necessary details"

    __guidelines__ = [
        "Summarize all booking details clearly and completely",
        "Include date, time, doctor name, specialty, and location or telehealth link",
        "Mention what to bring or prepare for the appointment",
        "Provide cancellation and rescheduling information",
        "End with a warm, reassuring message",
        "Format the confirmation in an easy-to-read structure",
        "Include the confirmation number prominently",
    ]

    # Inputs
    doctor: Dict[str, Any] = InputField(
        desc="Selected doctor details including id, name, specialty, location, telehealth_link"
    )
    slot: str = InputField(desc="Selected appointment slot in ISO format")
    patient_info: Dict[str, Any] = InputField(
        desc="Patient information including symptoms, preferences, insurance collected during intake"
    )

    # Outputs
    confirmation_number: str = OutputField(
        desc="Generated unique confirmation number (e.g., HC-2024-0115-001)"
    )
    confirmation_summary: str = OutputField(
        desc="Structured summary of appointment details (date, time, doctor, location)"
    )
    preparation_instructions: str = OutputField(
        desc="What to prepare or bring to the appointment"
    )
    response: str = OutputField(
        desc="Complete confirmation message to patient including all details and warm closing"
    )

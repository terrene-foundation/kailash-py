"""
Booking Signature - Doctor Matching and Selection

Presents available doctors matching patient preferences and handles
doctor selection with rejected doctors tracking.
"""

from typing import Any, Dict, List, Optional

from kaizen.signatures import InputField, OutputField, Signature


class BookingSignature(Signature):
    """
    Present and handle doctor booking options.

    This signature is used during the booking phase to match patients with
    appropriate specialists based on their symptoms and preferences, present
    options, and handle the selection process including doctor rejections.

    Key Features:
        - Tracks rejected doctors to avoid re-suggesting them
        - Presents at most 3 options per turn to avoid overwhelming the patient
        - Explains why each doctor is a good match for the patient's needs

    Example:
        >>> agent = BookingAgent(config)
        >>> result = agent.run(
        ...     patient_message="I'd like to see a back specialist",
        ...     symptoms=["back pain", "stiffness"],
        ...     preferences={"time_preference": "morning", "gender_preference": "female"},
        ...     rejected_doctors=["dr-smith-001"]
        ... )
        >>> print(result["suggested_doctors"])
        [{"id": "dr-chen-002", "name": "Dr. Chen", ...}]
    """

    __intent__ = "Match patients with appropriate specialists and facilitate booking"

    __guidelines__ = [
        "Present no more than 3 options at a time",
        "Highlight relevant specialties for the patient's symptoms",
        "Respect patient preferences (time, gender, telehealth, location)",
        "If a doctor is rejected, acknowledge and offer alternatives",
        "Never suggest previously rejected doctors",
        "Explain why each doctor is a good match",
        "Confirm selected time slot before finalizing",
        "If no suitable doctors are available, explain and offer alternatives",
    ]

    # Inputs
    patient_message: str = InputField(
        desc="Patient's booking-related message or selection"
    )
    symptoms: List[str] = InputField(desc="Patient symptoms from intake phase")
    preferences: Dict[str, Any] = InputField(
        desc="Patient preferences from intake (time, gender, telehealth, location)"
    )
    rejected_doctors: List[str] = InputField(
        desc="List of doctor IDs the patient has rejected in this session", default=[]
    )
    available_doctors: List[Dict[str, Any]] = InputField(
        desc="List of available doctors from database query", default=[]
    )

    # Outputs
    suggested_doctors: List[Dict[str, Any]] = OutputField(
        desc="List of suggested doctors with id, name, specialty, available_slots, rating, and match_reason"
    )
    selected_doctor: Optional[Dict[str, Any]] = OutputField(
        desc="Doctor selected by patient including id, name, specialty (if selection made)"
    )
    selected_slot: Optional[str] = OutputField(
        desc="Appointment slot selected in ISO format (if selection made)"
    )
    new_rejected_doctors: List[str] = OutputField(
        desc="New doctor IDs rejected in this turn", default=[]
    )
    response: str = OutputField(
        desc="Natural language response presenting options or confirming selection"
    )
    booking_complete: bool = OutputField(
        desc="Whether booking is complete with doctor and slot selected, ready for confirmation"
    )

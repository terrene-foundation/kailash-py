"""
Intake Signature - Patient Information Collection

Gathers patient symptoms, severity, preferences, and insurance information
for specialist referral.
"""

from typing import Any, Dict, List, Optional

from kaizen.signatures import InputField, OutputField, Signature


class IntakeSignature(Signature):
    """
    Gather patient information for healthcare referral.

    This signature is used during the intake phase to collect comprehensive
    information about the patient's symptoms, severity, preferences, and
    insurance before proceeding to doctor booking.

    Example:
        >>> agent = IntakeAgent(config)
        >>> result = agent.run(
        ...     patient_message="I've been having back pain for a few weeks",
        ...     conversation_history=[]
        ... )
        >>> print(result["symptoms"])
        ['back pain']
        >>> print(result["ready_for_booking"])
        False  # Need more information
    """

    __intent__ = (
        "Collect comprehensive patient symptoms and preferences for specialist referral"
    )

    __guidelines__ = [
        "Start by acknowledging the patient's concern",
        "Ask about symptoms before demographics",
        "Use empathetic, non-clinical language",
        "Identify both physical symptoms and patient preferences",
        "Confirm understanding before proceeding to booking",
        "Be patient if information comes in gradually over multiple turns",
        "Summarize collected information before transitioning",
    ]

    # Inputs
    patient_message: str = InputField(
        desc="Patient's description of their condition and needs"
    )
    conversation_history: List[Dict[str, Any]] = InputField(
        desc="Previous conversation turns for context", default=[]
    )

    # Outputs
    symptoms: List[str] = OutputField(
        desc="Extracted list of symptoms (e.g., ['back pain', 'stiffness', 'numbness'])"
    )
    severity: str = OutputField(
        desc="Assessed severity level: 'mild', 'moderate', 'severe', or 'urgent'"
    )
    preferences: Dict[str, Any] = OutputField(
        desc="Patient preferences including time_preference, gender_preference, telehealth_ok, location_preference"
    )
    insurance_info: Optional[str] = OutputField(
        desc="Insurance provider and plan information if mentioned"
    )
    response: str = OutputField(
        desc="Natural language response to the patient, asking for any missing information or confirming readiness"
    )
    ready_for_booking: bool = OutputField(
        desc="Whether sufficient information has been collected to proceed to booking (symptoms, severity, and at least basic preferences)"
    )

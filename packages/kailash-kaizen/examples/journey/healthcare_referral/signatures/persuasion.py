"""
Persuasion Signature - Hesitation Handling

Addresses patient hesitation and highlights booking benefits
while respecting their decision.
"""

from typing import Any, Dict, List, Optional

from kaizen.signatures import InputField, OutputField, Signature


class PersuasionSignature(Signature):
    """
    Address hesitation and highlight booking benefits.

    This signature is used when a patient expresses hesitation during the
    booking process. It aims to help hesitant patients feel confident about
    booking their appointment while respecting their autonomy.

    Key Features:
        - Acknowledges the patient's concerns empathetically
        - Does not pressure or be pushy
        - Highlights benefits relevant to the patient's specific symptoms
        - Addresses common concerns (cost, time commitment, etc.)
        - Offers specific next steps if they want to proceed

    Example:
        >>> agent = PersuasionAgent(config)
        >>> result = agent.run(
        ...     patient_message="I'm not sure if I want to book right now...",
        ...     symptoms=["back pain", "stiffness"],
        ...     hesitation_reason="cost concerns"
        ... )
        >>> print(result["concerns_addressed"])
        ["cost", "time_commitment"]
    """

    __intent__ = "Help hesitant patients feel confident about booking their appointment"

    __guidelines__ = [
        "Acknowledge the patient's hesitation or concern first",
        "Do not be pushy - respect their decision to wait or decline",
        "Highlight specific benefits relevant to their symptoms",
        "Address common concerns (cost, time commitment, fear of diagnosis)",
        "Offer specific next steps if they want to proceed",
        "Provide reassurance without making false promises",
        "If they still want to wait, be supportive and leave the door open",
    ]

    # Inputs
    patient_message: str = InputField(desc="Patient's hesitant or uncertain message")
    symptoms: List[str] = InputField(desc="Patient symptoms to personalize benefits")
    hesitation_reason: Optional[str] = InputField(
        desc="Identified reason for hesitation if known (cost, time, fear, uncertainty)",
        default=None,
    )
    current_context: Dict[str, Any] = InputField(
        desc="Current journey context including selected doctor info if any", default={}
    )

    # Outputs
    response: str = OutputField(
        desc="Empathetic response addressing concerns and offering support"
    )
    concerns_addressed: List[str] = OutputField(
        desc="List of concerns addressed in the response (e.g., ['cost', 'time_commitment'])"
    )
    ready_to_proceed: bool = OutputField(
        desc="Whether patient indicates readiness to continue with booking"
    )

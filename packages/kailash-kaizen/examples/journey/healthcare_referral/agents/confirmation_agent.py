"""
Confirmation Agent - Booking Finalization

Extends BaseAgent with ConfirmationSignature for finalizing
appointment bookings with complete confirmation details.
"""

import random
import string
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from examples.journey.healthcare_referral.signatures.confirmation import (
    ConfirmationSignature,
)
from kaizen.core.base_agent import BaseAgent


@dataclass
class ConfirmationAgentConfig:
    """
    Configuration for ConfirmationAgent.

    Attributes:
        llm_provider: LLM provider to use
        model: Model name
        temperature: Sampling temperature (lower for consistent formatting)
        max_tokens: Maximum tokens in response
    """

    llm_provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.5  # Lower for consistent formatting
    max_tokens: int = 1000


def generate_confirmation_number() -> str:
    """
    Generate a unique confirmation number.

    Format: HC-YYYYMMDD-XXX where XXX is a random alphanumeric string.

    Returns:
        Unique confirmation number string.
    """
    date_part = datetime.now().strftime("%Y%m%d")
    random_part = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"HC-{date_part}-{random_part}"


class ConfirmationAgent(BaseAgent):
    """
    Agent for finalizing appointment bookings.

    Generates a complete confirmation with:
    - Appointment details (date, time, doctor, location)
    - Confirmation number
    - Preparation instructions
    - Cancellation/rescheduling information

    This is the terminal pathway agent - journey ends after confirmation.

    Example:
        >>> config = ConfirmationAgentConfig(llm_provider="ollama", model="llama3.2:3b")
        >>> agent = ConfirmationAgent(config)
        >>> result = await agent.confirm_booking(
        ...     doctor={"name": "Dr. Chen", "specialty": "Orthopedics"},
        ...     slot="2024-01-15T09:00:00",
        ...     patient_info={"symptoms": ["back pain"], "insurance": "Blue Cross"}
        ... )
        >>> print(result["confirmation_number"])
        "HC-20240112-AB3X"
    """

    def __init__(self, config: Optional[ConfirmationAgentConfig] = None):
        """
        Initialize ConfirmationAgent.

        Args:
            config: Agent configuration (defaults to ConfirmationAgentConfig())
        """
        config = config or ConfirmationAgentConfig()
        super().__init__(
            config=config,
            signature=ConfirmationSignature(),
        )

    async def confirm_booking(
        self,
        doctor: Dict[str, Any],
        slot: str,
        patient_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate booking confirmation.

        Args:
            doctor: Selected doctor details
            slot: Selected appointment slot (ISO format)
            patient_info: Patient information from intake

        Returns:
            Dict containing:
            - confirmation_number: Unique confirmation ID
            - confirmation_summary: Structured appointment details
            - preparation_instructions: What to prepare/bring
            - response: Complete confirmation message
        """
        # Generate confirmation number
        confirmation_number = generate_confirmation_number()

        # Run agent with pre-generated confirmation number
        result = await self.run_async(
            doctor=doctor,
            slot=slot,
            patient_info=patient_info,
        )

        # Ensure confirmation number is set (LLM might generate its own)
        result["confirmation_number"] = confirmation_number

        return result

    def confirm_booking_sync(
        self,
        doctor: Dict[str, Any],
        slot: str,
        patient_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Synchronous version of confirm_booking.

        For use in non-async contexts.
        """
        confirmation_number = generate_confirmation_number()

        result = self.run(
            doctor=doctor,
            slot=slot,
            patient_info=patient_info,
        )

        result["confirmation_number"] = confirmation_number

        return result


__all__ = [
    "ConfirmationAgent",
    "ConfirmationAgentConfig",
    "generate_confirmation_number",
]

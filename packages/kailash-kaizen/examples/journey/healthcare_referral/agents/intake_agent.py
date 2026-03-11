"""
Intake Agent - Patient Information Collection

Extends BaseAgent with IntakeSignature for collecting patient information
during the intake phase of the healthcare referral journey.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from examples.journey.healthcare_referral.signatures.intake import IntakeSignature
from kaizen.core.base_agent import BaseAgent


@dataclass
class IntakeAgentConfig:
    """
    Configuration for IntakeAgent.

    Attributes:
        llm_provider: LLM provider to use (openai, ollama, etc.)
        model: Model name (gpt-4o, llama3.2:3b, etc.)
        temperature: Sampling temperature (0-1)
        max_tokens: Maximum tokens in response
    """

    llm_provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 1000


class IntakeAgent(BaseAgent):
    """
    Agent for patient intake during healthcare referral.

    Collects comprehensive patient information including:
    - Symptoms and severity
    - Preferences (time, gender, telehealth, location)
    - Insurance information

    The agent uses empathetic language and asks clarifying questions
    to gather sufficient information before proceeding to booking.

    Example:
        >>> config = IntakeAgentConfig(llm_provider="ollama", model="llama3.2:3b")
        >>> agent = IntakeAgent(config)
        >>> result = await agent.process_intake(
        ...     patient_message="I've been having back pain for weeks",
        ...     conversation_history=[]
        ... )
        >>> print(result["symptoms"])
        ['back pain']
        >>> print(result["ready_for_booking"])
        False
    """

    def __init__(self, config: Optional[IntakeAgentConfig] = None):
        """
        Initialize IntakeAgent.

        Args:
            config: Agent configuration (defaults to IntakeAgentConfig())
        """
        config = config or IntakeAgentConfig()
        super().__init__(
            config=config,
            signature=IntakeSignature(),
        )

    async def process_intake(
        self,
        patient_message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Process patient message during intake phase.

        Args:
            patient_message: Patient's message describing their condition
            conversation_history: Previous conversation turns

        Returns:
            Dict containing:
            - symptoms: List of extracted symptoms
            - severity: Severity level
            - preferences: Patient preferences dict
            - insurance_info: Insurance information if provided
            - response: Agent's response
            - ready_for_booking: Whether sufficient info collected
        """
        return await self.run_async(
            patient_message=patient_message,
            conversation_history=conversation_history or [],
        )

    def process_intake_sync(
        self,
        patient_message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous version of process_intake.

        For use in non-async contexts like CLI scripts.
        """
        return self.run(
            patient_message=patient_message,
            conversation_history=conversation_history or [],
        )


__all__ = [
    "IntakeAgent",
    "IntakeAgentConfig",
]

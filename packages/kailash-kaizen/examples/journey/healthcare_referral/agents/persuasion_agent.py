"""
Persuasion Agent - Hesitation Handling

Extends BaseAgent with PersuasionSignature for addressing patient
hesitation during the booking process.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from examples.journey.healthcare_referral.signatures.persuasion import (
    PersuasionSignature,
)
from kaizen.core.base_agent import BaseAgent


@dataclass
class PersuasionAgentConfig:
    """
    Configuration for PersuasionAgent.

    Attributes:
        llm_provider: LLM provider to use
        model: Model name
        temperature: Sampling temperature (slightly lower for consistency)
        max_tokens: Maximum tokens in response
    """

    llm_provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.6  # Slightly lower for more consistent, empathetic responses
    max_tokens: int = 800


class PersuasionAgent(BaseAgent):
    """
    Agent for addressing patient hesitation during booking.

    Triggered when a patient expresses uncertainty, this agent:
    - Acknowledges concerns empathetically
    - Highlights benefits relevant to their symptoms
    - Addresses common concerns (cost, time, fear)
    - Respects their decision without being pushy

    Example:
        >>> config = PersuasionAgentConfig(llm_provider="ollama", model="llama3.2:3b")
        >>> agent = PersuasionAgent(config)
        >>> result = await agent.address_hesitation(
        ...     patient_message="I'm not sure if I want to book right now...",
        ...     symptoms=["back pain", "stiffness"],
        ...     hesitation_reason="cost concerns"
        ... )
        >>> print(result["concerns_addressed"])
        ["cost", "time_commitment"]
    """

    def __init__(self, config: Optional[PersuasionAgentConfig] = None):
        """
        Initialize PersuasionAgent.

        Args:
            config: Agent configuration (defaults to PersuasionAgentConfig())
        """
        config = config or PersuasionAgentConfig()
        super().__init__(
            config=config,
            signature=PersuasionSignature(),
        )

    async def address_hesitation(
        self,
        patient_message: str,
        symptoms: List[str],
        hesitation_reason: Optional[str] = None,
        current_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Address patient hesitation about booking.

        Args:
            patient_message: Patient's hesitant message
            symptoms: Patient symptoms for personalized benefits
            hesitation_reason: Identified reason if known
            current_context: Current journey context

        Returns:
            Dict containing:
            - response: Empathetic response addressing concerns
            - concerns_addressed: List of concerns addressed
            - ready_to_proceed: Whether patient is ready to continue
        """
        return await self.run_async(
            patient_message=patient_message,
            symptoms=symptoms,
            hesitation_reason=hesitation_reason,
            current_context=current_context or {},
        )

    def address_hesitation_sync(
        self,
        patient_message: str,
        symptoms: List[str],
        hesitation_reason: Optional[str] = None,
        current_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous version of address_hesitation.

        For use in non-async contexts.
        """
        return self.run(
            patient_message=patient_message,
            symptoms=symptoms,
            hesitation_reason=hesitation_reason,
            current_context=current_context or {},
        )


__all__ = [
    "PersuasionAgent",
    "PersuasionAgentConfig",
]

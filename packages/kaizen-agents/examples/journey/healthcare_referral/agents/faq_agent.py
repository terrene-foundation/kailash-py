"""
FAQ Agent - Question Answering

Extends BaseAgent with FAQSignature for answering patient questions
during the healthcare referral journey.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from examples.journey.healthcare_referral.signatures.faq import FAQSignature
from kaizen.core.base_agent import BaseAgent


@dataclass
class FAQAgentConfig:
    """
    Configuration for FAQAgent.

    Attributes:
        llm_provider: LLM provider to use
        model: Model name
        temperature: Sampling temperature
        max_tokens: Maximum tokens in response
    """

    llm_provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 800


class FAQAgent(BaseAgent):
    """
    Agent for answering patient questions about healthcare referrals.

    Handles common questions like:
    - "What's the difference between an orthopedist and a chiropractor?"
    - "How does my insurance work for referrals?"
    - "What should I expect at my first visit?"

    The agent provides clear, concise answers while staying within scope
    (healthcare referral process) and offers to return to the main flow.

    Example:
        >>> config = FAQAgentConfig(llm_provider="ollama", model="llama3.2:3b")
        >>> agent = FAQAgent(config)
        >>> result = await agent.answer_question(
        ...     question="What's the difference between a physical therapist and an orthopedist?",
        ...     current_context={"symptoms": ["back pain"]}
        ... )
        >>> print(result["answer"])
        "An orthopedist is a medical doctor who specializes in..."
    """

    def __init__(self, config: Optional[FAQAgentConfig] = None):
        """
        Initialize FAQAgent.

        Args:
            config: Agent configuration (defaults to FAQAgentConfig())
        """
        config = config or FAQAgentConfig()
        super().__init__(
            config=config,
            signature=FAQSignature(),
        )

    async def answer_question(
        self,
        question: str,
        current_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Answer a patient question.

        Args:
            question: Patient's question
            current_context: Current journey context for personalized answers

        Returns:
            Dict containing:
            - answer: The answer to the question
            - question_resolved: Whether the question is fully answered
            - response: Full response including offer to continue
        """
        return await self.run_async(
            question=question,
            current_context=current_context or {},
        )

    def answer_question_sync(
        self,
        question: str,
        current_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous version of answer_question.

        For use in non-async contexts.
        """
        return self.run(
            question=question,
            current_context=current_context or {},
        )


__all__ = [
    "FAQAgent",
    "FAQAgentConfig",
]

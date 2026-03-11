"""
Chain-of-Thought Reasoning Agent - Refactored with BaseAgent Architecture

Demonstrates step-by-step reasoning with BaseAgent + async strategy:
- 441 lines → ~120 lines (73% reduction)
- Signature-based CoT reasoning structure
- Built-in error handling, logging, performance tracking via mixins
- Enterprise-grade with minimal code
- Uses async strategy by default for better concurrency
"""

from dataclasses import dataclass, field
from typing import Any, Dict

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature


@dataclass
class CoTConfig:
    """Configuration for Chain-of-Thought Agent."""

    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.1
    max_tokens: int = 1500
    timeout: int = 45
    retry_attempts: int = 3
    reasoning_steps: int = 5
    confidence_threshold: float = 0.7
    enable_verification: bool = True
    provider_config: Dict[str, Any] = field(default_factory=dict)


class ChainOfThoughtSignature(Signature):
    """
    Chain-of-Thought signature for structured step-by-step reasoning.

    Enables transparent problem decomposition with explicit reasoning chains.
    """

    problem: str = InputField(desc="Complex problem requiring step-by-step reasoning")
    context: str = InputField(desc="Additional context or constraints", default="")

    step1: str = OutputField(desc="First reasoning step: Problem understanding")
    step2: str = OutputField(
        desc="Second reasoning step: Data identification and organization"
    )
    step3: str = OutputField(
        desc="Third reasoning step: Systematic calculation or analysis"
    )
    step4: str = OutputField(desc="Fourth reasoning step: Solution verification")
    step5: str = OutputField(desc="Fifth reasoning step: Final answer formulation")
    final_answer: str = OutputField(desc="Complete, verified solution to the problem")
    confidence: float = OutputField(desc="Confidence score 0.0-1.0 for the solution")


class ChainOfThoughtAgent(BaseAgent):
    """
    Chain-of-Thought Agent using BaseAgent architecture.

    Inherits from BaseAgent:
    - Signature-based structured CoT reasoning
    - Error handling (ErrorHandlingMixin)
    - Performance tracking (PerformanceMixin)
    - Structured logging (LoggingMixin)
    - Workflow generation for Core SDK integration
    """

    def __init__(self, config: CoTConfig):
        """Initialize Chain-of-Thought agent with BaseAgent infrastructure."""
        # Create agent configuration with timeout in provider_config
        provider_cfg = config.provider_config.copy() if config.provider_config else {}
        provider_cfg["timeout"] = config.timeout

        agent_config = BaseAgentConfig(
            llm_provider=config.llm_provider,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            provider_config=provider_cfg,
            # Enable enterprise features via mixins
            logging_enabled=True,
            performance_enabled=True,
            error_handling_enabled=True,
        )

        # Initialize BaseAgent with default async strategy (CoT uses single-shot with structured reasoning)
        # No explicit strategy = uses AsyncSingleShotStrategy by default (Task 0A.3)
        super().__init__(config=agent_config, signature=ChainOfThoughtSignature())

        self.cot_config = config

    def solve_problem(self, problem: str, context: str = "") -> Dict[str, Any]:
        """
        Solve a complex problem using Chain-of-Thought reasoning.

        Args:
            problem: Complex problem requiring step-by-step reasoning
            context: Optional additional context or constraints

        Returns:
            Dict containing step1-step5, final_answer, confidence
        """
        # Input validation
        if not problem or not problem.strip():
            return {
                "error": "INVALID_INPUT",
                "final_answer": "Please provide a clear problem to solve.",
                "confidence": 0.0,
                "step1": "No problem provided",
                "step2": "",
                "step3": "",
                "step4": "",
                "step5": "",
            }

        # Execute via BaseAgent (handles logging, performance tracking, error handling)
        result = self.run(
            problem=problem.strip(), context=context.strip() if context else ""
        )

        # Validate confidence threshold (with safe get)
        confidence = result.get("confidence", 0)
        if confidence < self.cot_config.confidence_threshold:
            result["warning"] = (
                f"Low confidence ({confidence:.2f} < {self.cot_config.confidence_threshold})"
            )

        # Add verification flag if enabled
        if self.cot_config.enable_verification:
            result["verified"] = confidence >= self.cot_config.confidence_threshold

        return result

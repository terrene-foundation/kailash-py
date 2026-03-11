"""
ChainOfThoughtAgent - Production-Ready Step-by-Step Reasoning Agent

Zero-config usage:
    from kaizen.agents import ChainOfThoughtAgent

    agent = ChainOfThoughtAgent()
    result = agent.run(problem="What is 15 * 23?")
    print(result["final_answer"])
    print(f"Confidence: {result['confidence']}")

Progressive configuration:
    agent = ChainOfThoughtAgent(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.1,
        confidence_threshold=0.8
    )

Environment variable support:
    KAIZEN_LLM_PROVIDER=openai
    KAIZEN_MODEL=gpt-4
    KAIZEN_TEMPERATURE=0.1
    KAIZEN_MAX_TOKENS=1500
"""

import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional

from kailash.nodes.base import NodeMetadata
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


@dataclass
class ChainOfThoughtConfig:
    """
    Configuration for Chain-of-Thought Agent.

    All parameters have sensible defaults and can be overridden via:
    1. Constructor arguments (highest priority)
    2. Environment variables (KAIZEN_*)
    3. Default values (lowest priority)
    """

    llm_provider: str = field(
        default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    )
    model: str = field(default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-4"))
    temperature: float = field(
        default_factory=lambda: float(os.getenv("KAIZEN_TEMPERATURE", "0.1"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_TOKENS", "1500"))
    )
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
    Production-ready Chain-of-Thought Reasoning Agent.

    Features:
    - Zero-config with sensible defaults
    - Progressive configuration (override as needed)
    - Environment variable support
    - Step-by-step reasoning with transparency
    - Confidence scoring and verification
    - Built-in error handling and logging
    - Async-first execution (AsyncSingleShotStrategy)

    Usage:
        # Zero-config (easiest)
        agent = ChainOfThoughtAgent()
        result = agent.run(problem="Calculate 15 * 23 step by step")

        # With configuration
        agent = ChainOfThoughtAgent(
            llm_provider="openai",
            model="gpt-4",
            temperature=0.1,
            confidence_threshold=0.8,
            enable_verification=True
        )

        # View reasoning steps
        result = agent.run(problem="What is the capital of France?")
        print(result["step1"])  # Problem understanding
        print(result["step2"])  # Data identification
        print(result["final_answer"])
        print(f"Verified: {result.get('verified', False)}")

    Configuration:
        llm_provider: LLM provider (default: "openai", env: KAIZEN_LLM_PROVIDER)
        model: Model name (default: "gpt-4", env: KAIZEN_MODEL)
        temperature: Sampling temperature (default: 0.1, env: KAIZEN_TEMPERATURE)
        max_tokens: Maximum tokens (default: 1500, env: KAIZEN_MAX_TOKENS)
        timeout: Request timeout seconds (default: 45)
        retry_attempts: Retry count on failure (default: 3)
        reasoning_steps: Number of reasoning steps (default: 5)
        confidence_threshold: Minimum acceptable confidence (default: 0.7)
        enable_verification: Add verification flag to results (default: True)
        provider_config: Additional provider-specific config (default: {})

    Returns:
        Dict with keys:
        - step1 to step5: str - Individual reasoning steps
        - final_answer: str - Complete solution
        - confidence: float - Confidence score 0.0-1.0
        - verified: bool (optional) - True if confidence >= threshold (when enabled)
        - warning: str (optional) - Warning if confidence below threshold
        - error: str (optional) - Error code if validation fails
    """

    # Node metadata for Studio discovery
    metadata = NodeMetadata(
        name="ChainOfThoughtAgent",
        description="Step-by-step reasoning agent with transparent thought process and verification",
        version="1.0.0",
        tags={
            "ai",
            "kaizen",
            "reasoning",
            "chain-of-thought",
            "verification",
            "step-by-step",
        },
    )

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        retry_attempts: Optional[int] = None,
        reasoning_steps: Optional[int] = None,
        confidence_threshold: Optional[float] = None,
        enable_verification: Optional[bool] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        config: Optional[ChainOfThoughtConfig] = None,
        **kwargs,
    ):
        """
        Initialize Chain-of-Thought agent with zero-config defaults.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max tokens
            timeout: Override default timeout
            retry_attempts: Override default retry attempts
            reasoning_steps: Override default reasoning steps count
            confidence_threshold: Override default confidence threshold
            enable_verification: Enable/disable verification flag
            provider_config: Additional provider-specific configuration
            config: Full config object (overrides individual params)
        """
        # If config object provided, use it; otherwise build from parameters
        if config is None:
            config = ChainOfThoughtConfig()

            # Override defaults with provided parameters
            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)
            if temperature is not None:
                config = replace(config, temperature=temperature)
            if max_tokens is not None:
                config = replace(config, max_tokens=max_tokens)
            if timeout is not None:
                config = replace(config, timeout=timeout)
            if retry_attempts is not None:
                config = replace(config, retry_attempts=retry_attempts)
            if reasoning_steps is not None:
                config = replace(config, reasoning_steps=reasoning_steps)
            if confidence_threshold is not None:
                config = replace(config, confidence_threshold=confidence_threshold)
            if enable_verification is not None:
                config = replace(config, enable_verification=enable_verification)
            if provider_config is not None:
                config = replace(config, provider_config=provider_config)

        # Merge timeout into provider_config
        if config.timeout and (
            not config.provider_config or "timeout" not in config.provider_config
        ):
            provider_cfg = (
                config.provider_config.copy() if config.provider_config else {}
            )
            provider_cfg["timeout"] = config.timeout
            config = replace(config, provider_config=provider_cfg)

        # Initialize BaseAgent with auto-config extraction
        super().__init__(
            config=config,
            signature=ChainOfThoughtSignature(),
            **kwargs,
            # strategy omitted - uses AsyncSingleShotStrategy by default
        )

        self.cot_config = config

    def run(self, problem: str, context: str = "", **kwargs) -> Dict[str, Any]:
        """
        Solve a complex problem using Chain-of-Thought reasoning.

        Overrides BaseAgent.run() to add input validation and post-processing.

        Args:
            problem: Complex problem requiring step-by-step reasoning
            context: Optional additional context or constraints
            **kwargs: Additional keyword arguments for BaseAgent.run()

        Returns:
            Dictionary containing:
            - step1-step5: Individual reasoning steps
            - final_answer: Complete solution
            - confidence: Confidence score (0.0-1.0)
            - verified: Optional verification flag (if enabled)
            - warning: Optional warning if confidence is low
            - error: Optional error code if validation fails

        Example:
            >>> agent = ChainOfThoughtAgent()
            >>> result = agent.run(problem="Calculate 15 * 23")
            >>> print(result["step1"])
            Understanding the problem: We need to multiply 15 by 23
            >>> print(result["final_answer"])
            345
            >>> print(result["confidence"])
            0.95
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

        # Execute via BaseAgent (handles logging, performance, error handling)
        result = super().run(
            problem=problem.strip(),
            context=context.strip() if context else "",
            **kwargs,
        )

        # Handle cases where the LLM returned plain text instead of structured JSON
        # (e.g., mock provider or models that don't follow JSON instructions).
        # Extract what we can from the raw response text.
        if "final_answer" not in result and "response" in result:
            raw_response = result["response"]
            if isinstance(raw_response, str):
                result = self._extract_from_text_response(raw_response)

        # Validate confidence threshold
        confidence = result.get("confidence", 0)
        if confidence < self.cot_config.confidence_threshold:
            result["warning"] = (
                f"Low confidence ({confidence:.2f} < {self.cot_config.confidence_threshold})"
            )

        # Add verification flag if enabled
        if self.cot_config.enable_verification:
            result["verified"] = confidence >= self.cot_config.confidence_threshold

        return result

    def _extract_from_text_response(self, text: str) -> Dict[str, Any]:
        """
        Extract structured fields from a plain-text LLM response.

        When the LLM (or mock provider) returns plain text instead of JSON,
        this method parses the text into the expected ChainOfThought output
        fields by splitting on step markers and extracting a final answer.
        """
        import re

        result: Dict[str, Any] = {}
        remaining = text

        # Try to extract numbered steps (e.g., "Step 1:", "Step 2:", "1.", "2.")
        step_pattern = re.compile(
            r"(?:step\s*(\d+)[:\.]|^(\d+)[\.\)])\s*(.*?)(?=(?:step\s*\d+[:\.]|\d+[\.\)]|final\s*answer|$))",
            re.IGNORECASE | re.DOTALL,
        )
        matches = step_pattern.findall(remaining)

        for match in matches:
            step_num = match[0] or match[1]
            step_text = match[2].strip()
            if step_num and 1 <= int(step_num) <= 5:
                result[f"step{step_num}"] = step_text

        # Extract final answer if explicitly labeled
        final_pattern = re.compile(
            r"final\s*answer[:\s]*(.*)", re.IGNORECASE | re.DOTALL
        )
        final_match = final_pattern.search(remaining)
        if final_match:
            result["final_answer"] = final_match.group(1).strip()

        # Fill in missing steps with empty strings
        for i in range(1, 6):
            if f"step{i}" not in result:
                result[f"step{i}"] = ""

        # If no final answer was extracted, use the full text
        if "final_answer" not in result or not result["final_answer"]:
            result["final_answer"] = text.strip()

        # Default confidence for text-parsed responses
        result["confidence"] = result.get("confidence", 0.5)

        return result


# Convenience function for quick usage
def solve(problem: str, **kwargs) -> str:
    """
    Quick one-liner for solving problems without creating an agent instance.

    Args:
        problem: The problem to solve
        **kwargs: Optional configuration (llm_provider, model, temperature, etc.)

    Returns:
        The final answer string

    Example:
        >>> from kaizen.agents.specialized.chain_of_thought import solve
        >>> answer = solve("What is 15 * 23?")
        >>> print(answer)
        345
    """
    agent = ChainOfThoughtAgent(**kwargs)
    result = agent.run(problem=problem)
    return result.get("final_answer", "No answer generated")

"""
SimpleQAAgent - Production-Ready Question Answering Agent

Zero-config usage:
    from kaizen.agents import SimpleQAAgent

    agent = SimpleQAAgent()
    result = agent.run(question="What is AI?")
    print(result["answer"])

Progressive configuration:
    agent = SimpleQAAgent(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.7
    )

Environment variable support:
    KAIZEN_LLM_PROVIDER=openai
    KAIZEN_MODEL=gpt-4
    KAIZEN_TEMPERATURE=0.7
"""

import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional

from kailash.nodes.base import NodeMetadata
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


@dataclass
class SimpleQAConfig:
    """
    Configuration for SimpleQA Agent.

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
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_TOKENS", "300"))
    )
    timeout: int = 30
    retry_attempts: int = 3
    min_confidence_threshold: float = 0.5
    max_turns: Optional[int] = None  # None = memory disabled (opt-in)
    provider_config: Dict[str, Any] = field(default_factory=dict)


class QASignature(Signature):
    """Answer questions accurately and concisely with confidence scoring."""

    question: str = InputField(desc="The question to answer")
    context: str = InputField(desc="Additional context if available", default="")

    answer: str = OutputField(desc="Clear, accurate answer")
    confidence: float = OutputField(desc="Confidence score 0.0-1.0")
    reasoning: str = OutputField(desc="Brief explanation of reasoning")


class SimpleQAAgent(BaseAgent):
    """
    Production-ready Question Answering Agent.

    Features:
    - Zero-config with sensible defaults
    - Progressive configuration (override as needed)
    - Environment variable support
    - Async-first execution (AsyncSingleShotStrategy)
    - Optional memory (enable with max_turns parameter)
    - Structured I/O with confidence scoring
    - Built-in error handling and logging

    Usage:
        # Zero-config (easiest)
        agent = SimpleQAAgent()
        result = agent.run(question="What is AI?")

        # With configuration
        agent = SimpleQAAgent(
            llm_provider="openai",
            model="gpt-4",
            temperature=0.7,
            max_turns=10  # Enable memory with 10-turn limit
        )

        # With session for memory continuity
        result = agent.run(question="What is AI?", session_id="user_123")
        result = agent.run(question="Can you elaborate?", session_id="user_123")

    Configuration:
        llm_provider: LLM provider (default: "openai", env: KAIZEN_LLM_PROVIDER)
        model: Model name (default: "gpt-4", env: KAIZEN_MODEL)
        temperature: Sampling temperature (default: 0.1, env: KAIZEN_TEMPERATURE)
        max_tokens: Maximum tokens (default: 300, env: KAIZEN_MAX_TOKENS)
        timeout: Request timeout seconds (default: 30)
        retry_attempts: Retry count on failure (default: 3)
        min_confidence_threshold: Minimum acceptable confidence (default: 0.5)
        max_turns: Memory limit in turns, None=disabled (default: None)
        provider_config: Additional provider-specific config (default: {})

    Returns:
        Dict with keys:
        - answer: str - The answer to the question
        - confidence: float - Confidence score 0.0-1.0
        - reasoning: str - Brief explanation
        - warning: str (optional) - Warning if confidence below threshold
        - error: str (optional) - Error code if validation fails
    """

    # Node metadata for Studio discovery
    metadata = NodeMetadata(
        name="SimpleQAAgent",
        description="Simple question answering agent with confidence scoring",
        version="1.0.0",
        tags={"ai", "kaizen", "qa", "simple", "question-answering"},
    )

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        retry_attempts: Optional[int] = None,
        min_confidence_threshold: Optional[float] = None,
        max_turns: Optional[int] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        config: Optional[SimpleQAConfig] = None,
        **kwargs,
    ):
        """
        Initialize SimpleQA agent with zero-config defaults.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max tokens
            timeout: Override default timeout
            retry_attempts: Override default retry attempts
            min_confidence_threshold: Override default confidence threshold
            max_turns: Enable memory with turn limit (None=disabled)
            provider_config: Additional provider-specific configuration
            config: Full config object (overrides individual params)
        """
        # If config object provided, use it; otherwise build from parameters
        if config is None:
            config = SimpleQAConfig()

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
            if min_confidence_threshold is not None:
                config = replace(
                    config, min_confidence_threshold=min_confidence_threshold
                )
            if max_turns is not None:
                config = replace(config, max_turns=max_turns)
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

        # Initialize memory if max_turns is set
        memory = None
        if isinstance(config.max_turns, int) and config.max_turns >= 0:
            from kaizen.memory.buffer import BufferMemory

            memory = BufferMemory(
                max_turns=config.max_turns if config.max_turns > 0 else None
            )

        # Initialize BaseAgent with auto-config extraction
        super().__init__(
            config=config,
            signature=QASignature(),
            memory=memory,
            **kwargs,
            # strategy omitted - uses AsyncSingleShotStrategy by default
        )

        self.qa_config = config

    def run(
        self,
        question: str,
        context: str = "",
        session_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Universal execution method for SimpleQA agent.

        Args:
            question: The question to answer
            context: Optional additional context
            session_id: Optional session ID for memory continuity
            **kwargs: Additional parameters passed to BaseAgent.run()

        Returns:
            Dictionary containing:
            - answer: The answer to the question
            - confidence: Confidence score (0.0-1.0)
            - reasoning: Brief explanation of reasoning
            - warning: Optional warning if confidence is low
            - error: Optional error code if validation fails

        Example:
            >>> agent = SimpleQAAgent()
            >>> result = agent.run(question="What is the capital of France?")
            >>> print(result["answer"])
            Paris
            >>> print(result["confidence"])
            0.95
        """
        # Input validation
        if not question or not question.strip():
            return {
                "answer": "Please provide a clear question for me to answer.",
                "confidence": 0.0,
                "reasoning": "Empty or invalid input received",
                "error": "INVALID_INPUT",
            }

        # Execute via BaseAgent (handles logging, performance, error handling)
        result = super().run(
            question=question.strip(),
            context=context.strip() if context else "",
            session_id=session_id,
            **kwargs,
        )

        # Validate confidence threshold
        confidence = result.get("confidence", 0)
        if confidence < self.qa_config.min_confidence_threshold:
            result["warning"] = (
                f"Low confidence ({confidence:.2f} < {self.qa_config.min_confidence_threshold})"
            )

        return result


# Convenience function for quick usage
def ask(question: str, **kwargs) -> str:
    """
    Quick one-liner for simple Q&A without creating an agent instance.

    Args:
        question: The question to ask
        **kwargs: Optional configuration (llm_provider, model, temperature, etc.)

    Returns:
        The answer string

    Example:
        >>> from kaizen.agents.specialized.simple_qa import ask
        >>> answer = ask("What is AI?")
        >>> print(answer)
        Artificial Intelligence (AI) is...
    """
    agent = SimpleQAAgent(**kwargs)
    result = agent.run(question=question)
    return result.get("answer", "No answer generated")

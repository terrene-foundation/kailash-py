"""
SelfReflectionAgent - Production-Ready Iterative Self-Improvement

Zero-config usage:
    from kaizen.agents import SelfReflectionAgent

    agent = SelfReflectionAgent()
    result = agent.run(task="Write a blog post about AI")
    print(f"Final quality: {result['quality_score']}")
    print(f"Cycles: {len(result['reflection_history'])}")

Progressive configuration:
    agent = SelfReflectionAgent(
        llm_provider="openai",
        model="gpt-4",
        max_cycles=5,
        improvement_threshold=0.9
    )

Environment variable support:
    KAIZEN_LLM_PROVIDER=openai
    KAIZEN_MODEL=gpt-3.5-turbo
    KAIZEN_TEMPERATURE=0.7
    KAIZEN_MAX_CYCLES=3
    KAIZEN_IMPROVEMENT_THRESHOLD=0.8
"""

import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from kailash.nodes.base import NodeMetadata
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.multi_cycle import MultiCycleStrategy


class ReflectionSignature(Signature):
    """Signature for self-reflection cycle."""

    task: str = InputField(desc="Task to complete")
    previous_attempt: str = InputField(desc="Previous attempt (if any)", default="")
    previous_critique: str = InputField(desc="Previous critique (if any)", default="")

    attempt: str = OutputField(desc="Current attempt at completing the task")
    critique: str = OutputField(desc="Critical analysis of the attempt")
    quality_score: float = OutputField(desc="Self-assessed quality score (0.0-1.0)")
    improvements_needed: list = OutputField(desc="List of specific improvements needed")


@dataclass
class SelfReflectionConfig:
    """
    Configuration for Self-Reflection Agent.

    All parameters have sensible defaults and can be overridden via:
    1. Constructor arguments (highest priority)
    2. Environment variables (KAIZEN_*)
    3. Default values (lowest priority)
    """

    # LLM configuration
    llm_provider: str = field(
        default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    )
    model: str = field(
        default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-3.5-turbo")
    )
    temperature: float = field(
        default_factory=lambda: float(os.getenv("KAIZEN_TEMPERATURE", "0.7"))
    )

    # Reflection configuration
    max_cycles: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_CYCLES", "3"))
    )
    improvement_threshold: float = field(
        default_factory=lambda: float(os.getenv("KAIZEN_IMPROVEMENT_THRESHOLD", "0.8"))
    )

    # Technical configuration
    timeout: int = 30
    retry_attempts: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)


class SelfReflectionAgent(BaseAgent):
    """
    Production-ready Self-Reflection Agent using MultiCycleStrategy.

    Features:
    - Zero-config with sensible defaults (3 cycles, 0.8 threshold)
    - Iterative self-improvement through reflection
    - Quality-driven convergence
    - Reflection history tracking
    - Built-in error handling and logging via BaseAgent

    Inherits from BaseAgent:
    - Signature-based reflection pattern
    - Multi-cycle execution via MultiCycleStrategy
    - Error handling (ErrorHandlingMixin)
    - Performance tracking (PerformanceMixin)
    - Structured logging (LoggingMixin)

    Use Cases:
    - Content refinement (blog posts, marketing copy)
    - Code improvement and optimization
    - Quality assurance for generated outputs
    - Iterative problem solving
    - Self-critique workflows

    Performance:
    - Multiple LLM calls per task (max_cycles)
    - Quality-driven early stopping
    - Typical cycles: 2-3 for convergence
    - Final quality: Usually >0.8

    Reflection Process:
    1. Initial attempt at task
    2. Self-critique of attempt
    3. Improved attempt based on critique
    4. Repeat until quality threshold met or max cycles reached

    Usage:
        # Zero-config (3 cycles, 0.8 threshold)
        agent = SelfReflectionAgent()

        result = agent.run(task="Write a blog post about AI")
        print(f"Final attempt: {result['attempt']}")
        print(f"Quality score: {result['quality_score']}")
        print(f"Cycles: {len(result['reflection_history'])}")

        # Custom configuration
        agent = SelfReflectionAgent(
            llm_provider="openai",
            model="gpt-4",
            max_cycles=5,
            improvement_threshold=0.9
        )

        # Review reflection history
        result = agent.run(task="Optimize this code")
        for i, cycle in enumerate(result['reflection_history'], 1):
            print(f"Cycle {i}: Quality {cycle['quality_score']}")
            print(f"  Improvements: {cycle['improvements_needed']}")
    """

    # Node metadata for Studio discovery
    metadata = NodeMetadata(
        name="SelfReflectionAgent",
        description="Iterative self-improvement through reflection and quality convergence",
        version="1.0.0",
        tags={"ai", "kaizen", "reflection", "self-improvement", "quality", "iterative"},
    )

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_cycles: Optional[int] = None,
        improvement_threshold: Optional[float] = None,
        timeout: Optional[int] = None,
        retry_attempts: Optional[int] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        config: Optional[SelfReflectionConfig] = None,
        **kwargs,
    ):
        """
        Initialize Self-Reflection Agent with zero-config defaults.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature
            max_cycles: Maximum reflection cycles
            improvement_threshold: Quality threshold for convergence (0.0-1.0)
            timeout: Override default timeout
            retry_attempts: Override default retry attempts
            provider_config: Additional provider-specific configuration
            config: Full config object (overrides individual params)
        """
        # If config object provided, use it; otherwise build from parameters
        if config is None:
            config = SelfReflectionConfig()

            # Override defaults with provided parameters
            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)
            if temperature is not None:
                config = replace(config, temperature=temperature)
            if max_cycles is not None:
                config = replace(config, max_cycles=max_cycles)
            if improvement_threshold is not None:
                config = replace(config, improvement_threshold=improvement_threshold)
            if timeout is not None:
                config = replace(config, timeout=timeout)
            if retry_attempts is not None:
                config = replace(config, retry_attempts=retry_attempts)
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

        # Store config for convergence check
        self.reflection_config = config
        self.reflection_history = []

        # Use MultiCycleStrategy for iterative refinement
        strategy = MultiCycleStrategy(
            max_cycles=config.max_cycles, convergence_check=self._check_quality
        )

        # Initialize BaseAgent
        super().__init__(
            config=config,  # Auto-converted to BaseAgentConfig
            signature=ReflectionSignature(),
            strategy=strategy,
            **kwargs,
        )

    def _check_quality(self, cycle_results: List[Dict[str, Any]]) -> bool:
        """
        Check if quality threshold is met.

        Args:
            cycle_results: Results from all cycles so far

        Returns:
            bool: True if quality meets threshold (converged)
        """
        if not cycle_results:
            return False

        last_result = cycle_results[-1]
        quality_score = last_result.get("quality_score", 0.0)

        # Converge if quality is high enough
        return quality_score >= self.reflection_config.improvement_threshold

    def run(
        self,
        task: str,
        previous_attempt: str = "",
        previous_critique: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Complete task with iterative self-improvement.

        Overrides BaseAgent.run() to add input validation and reflection history tracking.

        Args:
            task: Task description
            previous_attempt: Previous attempt (used internally by multi-cycle strategy)
            previous_critique: Previous critique (used internally by multi-cycle strategy)
            **kwargs: Additional keyword arguments for BaseAgent.run()

        Returns:
            Dict[str, Any]: Final result with attempt, improvement history, and metadata

        Example:
            >>> agent = SelfReflectionAgent()
            >>> result = agent.run(task="Write a blog post about AI")
            >>> print(f"Final attempt: {result['attempt']}")
            >>> print(f"Quality score: {result['quality_score']}")
            >>> print(f"Total cycles: {len(result['reflection_history'])}")
        """
        if not task or not task.strip():
            return {
                "attempt": "No task provided.",
                "critique": "Cannot reflect on empty task.",
                "quality_score": 0.0,
                "improvements_needed": [],
                "error": "INVALID_INPUT",
            }

        # Reset history (only on initial call, not recursive calls)
        if not previous_attempt and not previous_critique:
            self.reflection_history = []

        # Execute multi-cycle reflection
        result = super().run(
            task=task.strip(),
            previous_attempt=previous_attempt,
            previous_critique=previous_critique,
            **kwargs,
        )

        # Add reflection history
        result["reflection_history"] = self.reflection_history

        return result

    def get_reflection_history(self) -> List[Dict[str, Any]]:
        """
        Get history of all reflection cycles.

        Returns:
            List[Dict[str, Any]]: Reflection history with attempts, critiques, and scores

        Example:
            >>> agent = SelfReflectionAgent()
            >>> result = agent.reflect("Write code")
            >>> history = agent.get_reflection_history()
            >>> for i, cycle in enumerate(history, 1):
            ...     print(f"Cycle {i}: Quality {cycle['quality_score']}")
        """
        return self.reflection_history


# Convenience function for quick self-reflection
def reflect_and_improve(
    task: str,
    max_cycles: int = 3,
    improvement_threshold: float = 0.8,
    llm_provider: str = "openai",
    model: str = "gpt-3.5-turbo",
) -> Dict[str, Any]:
    """
    Quick self-reflection with default configuration.

    Args:
        task: Task to complete with self-improvement
        max_cycles: Maximum reflection cycles
        improvement_threshold: Quality threshold for convergence
        llm_provider: LLM provider to use
        model: Model to use

    Returns:
        Dict with final attempt, reflection history, and quality score

    Example:
        >>> from kaizen.agents.specialized.self_reflection import reflect_and_improve
        >>>
        >>> result = reflect_and_improve(
        ...     "Write a blog post about machine learning",
        ...     max_cycles=5,
        ...     improvement_threshold=0.9
        ... )
        >>> print(f"Quality: {result['quality_score']}")
        >>> print(f"Cycles: {len(result['reflection_history'])}")
    """
    agent = SelfReflectionAgent(
        max_cycles=max_cycles,
        improvement_threshold=improvement_threshold,
        llm_provider=llm_provider,
        model=model,
    )

    return agent.run(task=task)

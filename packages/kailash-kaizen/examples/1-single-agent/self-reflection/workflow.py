"""
Self-Reflection Agent - Iterative Improvement with MultiCycle

Demonstrates self-improvement through reflection:
- Generate initial attempt
- Critique own work
- Improve based on critique
- Multiple refinement cycles
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.multi_cycle import MultiCycleStrategy


@dataclass
class ReflectionConfig:
    """Configuration for self-reflection agent."""

    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_cycles: int = 3
    improvement_threshold: float = 0.8
    provider_config: Dict[str, Any] = field(default_factory=dict)


class ReflectionSignature(Signature):
    """Signature for self-reflection cycle."""

    task: str = InputField(desc="Task to complete")
    previous_attempt: str = InputField(desc="Previous attempt (if any)", default="")
    previous_critique: str = InputField(desc="Previous critique (if any)", default="")

    attempt: str = OutputField(desc="Current attempt at completing the task")
    critique: str = OutputField(desc="Critical analysis of the attempt")
    quality_score: float = OutputField(desc="Self-assessed quality score (0.0-1.0)")
    improvements_needed: list = OutputField(desc="List of specific improvements needed")


class SelfReflectionAgent(BaseAgent):
    """
    Self-Reflection Agent using MultiCycleStrategy.

    Iteratively improves outputs through:
    1. Initial attempt
    2. Self-critique
    3. Improved attempt based on critique
    4. Repeat until quality threshold met or max cycles reached
    """

    def __init__(self, config: ReflectionConfig):
        """Initialize self-reflection agent."""
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        # Use MultiCycleStrategy for iterative refinement
        strategy = MultiCycleStrategy(
            max_cycles=config.max_cycles, convergence_check=self._check_quality
        )

        super().__init__(
            config=config, signature=ReflectionSignature(), strategy=strategy
        )

        self.reflection_config = config
        self.reflection_history = []

    def _check_quality(self, cycle_results: List[Dict[str, Any]]) -> bool:
        """Check if quality threshold is met."""
        if not cycle_results:
            return False

        last_result = cycle_results[-1]
        quality_score = last_result.get("quality_score", 0.0)

        # Converge if quality is high enough
        return quality_score >= self.reflection_config.improvement_threshold

    def reflect_and_improve(self, task: str) -> Dict[str, Any]:
        """
        Complete task with iterative self-improvement.

        Args:
            task: Task description

        Returns:
            Dict with final attempt, improvement history, and metadata
        """
        if not task or not task.strip():
            return {
                "attempt": "No task provided.",
                "critique": "Cannot reflect on empty task.",
                "quality_score": 0.0,
                "improvements_needed": [],
                "error": "INVALID_INPUT",
            }

        # Reset history
        self.reflection_history = []

        # Execute multi-cycle reflection
        result = self.run(task=task.strip(), previous_attempt="", previous_critique="")

        # Add reflection history
        result["reflection_history"] = self.reflection_history

        return result

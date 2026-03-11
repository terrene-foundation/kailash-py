"""
HandoffPattern - Multi-Agent Handoff Coordination Pattern

Production-ready handoff pattern with dynamic tier escalation based on complexity.
Provides zero-config factory function with progressive configuration support.

Pattern Components:
- HandoffAgent: Evaluates task complexity and executes or escalates
- TaskEvaluationSignature: Evaluates if agent can handle task
- TaskExecutionSignature: Executes task at tier level
- HandoffPattern: Pattern container with convenience methods

Usage:
    # Zero-config usage (creates 3 tiers automatically)
    from kaizen.orchestration.patterns import create_handoff_pattern

    pattern = create_handoff_pattern()
    result = pattern.execute_with_handoff(
        task="Debug complex distributed system issue",
        context="Production incident - high priority",
        max_tier=3
    )

    # Check which tier handled it
    print(f"Handled by tier: {result['final_tier']}")
    print(f"Escalations: {result['escalation_count']}")

    # Get full handoff trail
    history = pattern.get_handoff_history(result['execution_id'])

Architecture:
    Task → [Tier 1 Agent] → Evaluate Complexity
              ↓ (if can handle)
          Execute & Return
              ↓ (if too complex)
       [Tier 2 Agent] → Evaluate Complexity
              ↓ (if can handle)
          Execute & Return
              ↓ (if too complex)
       [Tier 3 Agent] → Execute & Return

Author: Kaizen Framework Team
Created: 2025-10-04 (Phase 3, Multi-Agent Patterns)
"""

import json
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.orchestration.patterns.base_pattern import BaseMultiAgentPattern
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Signature Definitions
# ============================================================================


class TaskEvaluationSignature(Signature):
    """Signature for evaluating if agent can handle task."""

    task: str = InputField(desc="Task description")
    tier_level: int = InputField(desc="Current tier level")
    context: str = InputField(desc="Additional context (optional)", default="")

    can_handle: str = OutputField(desc="'yes' or 'no'", default="no")
    complexity_score: float = OutputField(desc="Complexity 0.0-1.0", default=0.5)
    reasoning: str = OutputField(desc="Why can/cannot handle", default="")
    requires_tier: int = OutputField(desc="Required tier level", default=1)


class TaskExecutionSignature(Signature):
    """Signature for executing task at tier level."""

    task: str = InputField(desc="Task to execute")
    tier_level: int = InputField(desc="Current tier level")
    context: str = InputField(desc="Additional context (optional)", default="")

    result: str = OutputField(desc="Task result")
    confidence: float = OutputField(desc="Result confidence 0.0-1.0", default=0.8)
    execution_metadata: str = OutputField(desc="Metadata (JSON)", default="{}")


# ============================================================================
# HandoffAgent Implementation
# ============================================================================


class HandoffAgent(BaseAgent):
    """
    HandoffAgent: Evaluates task complexity and executes or escalates.

    Responsibilities:
    - Evaluate task complexity at current tier level
    - Execute task if within capability
    - Make handoff decision if too complex
    - Write handoff decisions to shared memory

    Shared Memory Behavior:
    - Writes handoff decisions with tags: ["handoff", "tier", execution_id, "tier_<N>"]
    - Importance: 0.8 for evaluations
    - Segment: "handoff_decisions"
    """

    def __init__(
        self,
        config: BaseAgentConfig,
        shared_memory: SharedMemoryPool,
        tier_level: int,
        agent_id: str,
    ):
        """
        Initialize HandoffAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for handoff coordination
            tier_level: Tier level (1=basic, higher=more capable)
            agent_id: Unique identifier for this agent
        """
        super().__init__(
            config=config,
            signature=TaskEvaluationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.tier_level = tier_level

    def evaluate_task(self, task: str, context: str = "") -> Dict[str, Any]:
        """
        Evaluate if this tier can handle the task.

        Args:
            task: Task description
            context: Additional context

        Returns:
            Evaluation result with can_handle, complexity_score, reasoning, requires_tier
        """
        # Execute evaluation via base agent
        result = self.run(
            task=task,
            tier_level=self.tier_level,
            context=context,
            session_id=f"eval_{uuid.uuid4().hex[:8]}",
        )

        # Parse can_handle
        can_handle = result.get("can_handle", "no")

        # Parse complexity_score (ensure float 0-1)
        complexity_score = result.get("complexity_score", 0.5)
        if isinstance(complexity_score, str):
            try:
                complexity_score = float(complexity_score)
            except ValueError as e:
                logger.debug(
                    f"Could not parse complexity_score '{complexity_score}': {e}"
                )
                complexity_score = 0.5
        complexity_score = max(0.0, min(1.0, complexity_score))

        # Parse requires_tier (ensure int)
        requires_tier = result.get("requires_tier", self.tier_level)
        if isinstance(requires_tier, str):
            try:
                requires_tier = int(requires_tier)
            except ValueError as e:
                logger.debug(f"Could not parse requires_tier '{requires_tier}': {e}")
                requires_tier = self.tier_level

        # Parse reasoning
        reasoning = result.get("reasoning", "")

        evaluation = {
            "can_handle": can_handle,
            "complexity_score": complexity_score,
            "reasoning": reasoning,
            "requires_tier": requires_tier,
        }

        # Write evaluation to shared memory
        if self.shared_memory:
            execution_id = f"handoff_{uuid.uuid4().hex[:8]}"

            handoff_decision = "execute" if can_handle == "yes" else "escalate"

            self.shared_memory.write_insight(
                {
                    "agent_id": self.agent_id,
                    "content": json.dumps(
                        {
                            "tier_level": self.tier_level,
                            "can_handle": can_handle,
                            "complexity_score": complexity_score,
                            "reasoning": reasoning,
                            "requires_tier": requires_tier,
                            "handoff_decision": handoff_decision,
                        }
                    ),
                    "tags": [
                        "handoff",
                        "tier",
                        execution_id,
                        f"tier_{self.tier_level}",
                    ],
                    "importance": 0.8,
                    "segment": "handoff_decisions",
                    "metadata": {
                        "tier_level": self.tier_level,
                        "execution_id": execution_id,
                        "handoff_decision": handoff_decision,
                    },
                }
            )

        return evaluation

    def execute_task(self, task: str, context: str = "") -> Dict[str, Any]:
        """
        Execute task at this tier level.

        Args:
            task: Task to execute
            context: Additional context

        Returns:
            Execution result with result, confidence, execution_metadata
        """
        # Switch to execution signature temporarily
        original_signature = self.signature
        self.signature = TaskExecutionSignature()

        # Execute task
        result = self.run(
            task=task,
            tier_level=self.tier_level,
            context=context,
            session_id=f"exec_{uuid.uuid4().hex[:8]}",
        )

        # Restore signature
        self.signature = original_signature

        # Parse confidence (ensure float 0-1)
        confidence = result.get("confidence", 0.8)
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except ValueError as e:
                logger.debug(f"Could not parse confidence '{confidence}': {e}")
                confidence = 0.8
        confidence = max(0.0, min(1.0, confidence))

        # Parse execution_metadata
        execution_metadata = result.get("execution_metadata", "{}")
        if not isinstance(execution_metadata, str):
            execution_metadata = json.dumps(execution_metadata)

        return {
            "result": result.get("result", ""),
            "confidence": confidence,
            "execution_metadata": execution_metadata,
        }


# ============================================================================
# Pattern Container
# ============================================================================


@dataclass
class HandoffPattern(BaseMultiAgentPattern):
    """
    HandoffPattern: Container for handoff coordination.

    Provides convenience methods for:
    - execute_with_handoff(): Execute with automatic escalation
    - add_tier(): Add new tier to pattern
    - get_handoff_history(): Retrieve handoff decisions
    - validate_pattern(): Validate pattern configuration

    Attributes:
        tiers: Dict[int, HandoffAgent] - Tier level → Agent mapping
        shared_memory: SharedMemoryPool for coordination
    """

    tiers: Dict[int, HandoffAgent]

    def execute_with_handoff(
        self, task: str, context: str = "", max_tier: int = 3
    ) -> Dict[str, Any]:
        """
        Execute task with automatic handoff/escalation.

        Starts at tier 1, evaluates complexity, and escalates to higher
        tiers if needed until task is handled or max_tier is reached.

        Args:
            task: Task description
            context: Additional context
            max_tier: Maximum tier to escalate to

        Returns:
            Result dictionary with:
            - final_tier: Tier that handled the task
            - result: Task execution result
            - execution_id: Unique execution identifier
            - escalation_count: Number of escalations
            - confidence: Result confidence (if available)
        """
        if not self.tiers:
            raise ValueError("HandoffPattern has no tiers configured")

        execution_id = f"handoff_{uuid.uuid4().hex[:8]}"
        escalation_count = 0
        current_tier = 1

        # Ensure current_tier exists
        tier_levels = sorted(self.tiers.keys())
        if not tier_levels:
            raise ValueError("No tiers available")

        current_tier = tier_levels[0]

        while current_tier <= max_tier:
            # Get agent at current tier
            if current_tier not in self.tiers:
                # Find next available tier
                available_tiers = [t for t in tier_levels if t >= current_tier]
                if not available_tiers:
                    break
                current_tier = available_tiers[0]

            agent = self.tiers[current_tier]

            # Evaluate task
            evaluation = agent.evaluate_task(task, context)

            # Check if agent can handle
            can_handle = evaluation.get("can_handle", "no")
            if can_handle == "yes":
                # Execute at this tier
                execution_result = agent.execute_task(task, context)

                return {
                    "final_tier": current_tier,
                    "result": execution_result.get("result", ""),
                    "execution_id": execution_id,
                    "escalation_count": escalation_count,
                    "confidence": execution_result.get("confidence", 0.8),
                }
            else:
                # Check if escalation is possible
                next_tiers = [t for t in tier_levels if t > current_tier]
                if not next_tiers or current_tier >= max_tier:
                    # No more tiers or reached max - execute at current tier anyway
                    # Don't increment escalation_count since there's nowhere to escalate to
                    execution_result = agent.execute_task(task, context)

                    return {
                        "final_tier": current_tier,
                        "result": execution_result.get("result", ""),
                        "execution_id": execution_id,
                        "escalation_count": escalation_count,  # Don't increment
                        "confidence": execution_result.get("confidence", 0.5),
                    }

                # Escalate to next tier
                evaluation.get("requires_tier", current_tier + 1)
                escalation_count += 1
                current_tier = next_tiers[0]

        # Fallback: execute at highest available tier
        highest_tier = tier_levels[-1]
        agent = self.tiers[highest_tier]
        execution_result = agent.execute_task(task, context)

        return {
            "final_tier": highest_tier,
            "result": execution_result.get("result", ""),
            "execution_id": execution_id,
            "escalation_count": escalation_count,
            "confidence": execution_result.get("confidence", 0.5),
        }

    def add_tier(self, agent: HandoffAgent, tier_level: int) -> None:
        """
        Add or replace tier in pattern.

        Args:
            agent: HandoffAgent instance
            tier_level: Tier level to assign
        """
        self.tiers[tier_level] = agent

    def get_handoff_history(self, execution_id: str) -> List[Dict[str, Any]]:
        """
        Get handoff history for an execution.

        Args:
            execution_id: Execution identifier

        Returns:
            List of handoff decisions for this execution
        """
        if not self.shared_memory:
            return []

        # Read handoff decisions with this execution_id
        insights = self.shared_memory.read_relevant(
            agent_id="_pattern_",
            tags=["handoff", execution_id],
            exclude_own=False,
            limit=100,
        )

        history = []
        for insight in insights:
            content = insight.get("content", "{}")
            if isinstance(content, str):
                try:
                    decision = json.loads(content)
                    history.append(decision)
                except json.JSONDecodeError as e:
                    logger.debug(f"Could not parse handoff history content: {e}")

        return history

    def validate_pattern(self) -> bool:
        """
        Validate that pattern is properly configured.

        Checks:
        - Shared memory exists
        - Tiers exist and are not empty
        - All agents have same shared memory

        Returns:
            True if valid, False otherwise
        """
        # Check shared memory
        if not self.shared_memory:
            return False

        # Check tiers exist
        if not self.tiers or len(self.tiers) == 0:
            return False

        # Check all agents have same shared memory
        for tier_level, agent in self.tiers.items():
            if hasattr(agent, "shared_memory"):
                if agent.shared_memory is not self.shared_memory:
                    return False

        return True

    def get_agents(self) -> List[BaseAgent]:
        """
        Get all agents in this pattern.

        Returns:
            List of agent instances
        """
        return list(self.tiers.values())

    def get_agent_ids(self) -> List[str]:
        """
        Get all agent IDs in this pattern.

        Returns:
            List of agent ID strings
        """
        return [agent.agent_id for agent in self.tiers.values()]


# ============================================================================
# Factory Function
# ============================================================================


def create_handoff_pattern(
    num_tiers: int = 3,
    llm_provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    shared_memory: Optional[SharedMemoryPool] = None,
    tier_configs: Optional[Dict[int, Dict[str, Any]]] = None,
    tiers: Optional[Dict[int, HandoffAgent]] = None,
) -> HandoffPattern:
    """
    Create handoff pattern with zero-config defaults.

    Zero-Config Usage (Level 1):
        >>> pattern = create_handoff_pattern()
        >>> result = pattern.execute_with_handoff("Debug issue")

    Basic Parameters (Level 2):
        >>> pattern = create_handoff_pattern(
        ...     num_tiers=5,
        ...     model="gpt-4",
        ...     temperature=0.7
        ... )

    Tier Configs (Level 3):
        >>> pattern = create_handoff_pattern(
        ...     tier_configs={
        ...         1: {'model': 'gpt-3.5-turbo'},
        ...         2: {'model': 'gpt-4'},
        ...         3: {'model': 'gpt-4-turbo'}
        ...     }
        ... )

    Custom Agents (Level 4):
        >>> custom_tier1 = HandoffAgent(...)
        >>> custom_tier2 = HandoffAgent(...)
        >>> pattern = create_handoff_pattern(
        ...     tiers={1: custom_tier1, 2: custom_tier2}
        ... )

    Args:
        num_tiers: Number of tiers to create (default: 3)
        llm_provider: LLM provider (default: from env or "openai")
        model: Model name (default: from env or "gpt-3.5-turbo")
        temperature: Temperature (default: 0.7)
        max_tokens: Max tokens (default: 1000)
        shared_memory: Existing SharedMemoryPool (default: creates new)
        tier_configs: Override config per tier
        tiers: Pre-built HandoffAgent instances

    Returns:
        HandoffPattern: Pattern ready to use
    """
    # Validate num_tiers
    if num_tiers <= 0:
        raise ValueError(f"num_tiers must be > 0, got {num_tiers}")

    # Create shared memory if not provided
    if shared_memory is None:
        shared_memory = SharedMemoryPool()

    # If custom tiers provided, use them directly
    if tiers is not None:
        return HandoffPattern(tiers=tiers, shared_memory=shared_memory)

    # Build base config from parameters (or use defaults)
    base_config_dict = {
        "llm_provider": llm_provider or os.getenv("KAIZEN_LLM_PROVIDER", "openai"),
        "model": model or os.getenv("KAIZEN_MODEL", "gpt-3.5-turbo"),
        "temperature": temperature if temperature is not None else 0.7,
        "max_tokens": max_tokens if max_tokens is not None else 1000,
    }

    # Build tiers
    tier_agents = {}
    for tier_level in range(1, num_tiers + 1):
        # Start with base config
        tier_cfg_dict = {**base_config_dict}

        # Override with tier-specific config if provided
        if tier_configs and tier_level in tier_configs:
            tier_cfg_dict.update(tier_configs[tier_level])

        # Create config
        tier_cfg = BaseAgentConfig(**tier_cfg_dict)

        # Create agent
        agent = HandoffAgent(
            config=tier_cfg,
            shared_memory=shared_memory,
            tier_level=tier_level,
            agent_id=f"tier_{tier_level}_agent",
        )

        tier_agents[tier_level] = agent

    return HandoffPattern(tiers=tier_agents, shared_memory=shared_memory)

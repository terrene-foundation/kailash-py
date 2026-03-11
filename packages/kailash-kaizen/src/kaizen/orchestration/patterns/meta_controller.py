"""
Meta-Controller (Router) Pipeline - Capability-Based Agent Routing

Implements intelligent routing based on A2A capability matching with graceful fallback.

Pattern:
    User Request → Router → A2A Capability Matching → Best Agent → Result

Features:
- Semantic capability-based routing (A2A protocol)
- Graceful fallback when A2A unavailable
- Round-robin and random routing strategies
- Error handling with configurable fail-fast mode
- Composable via .to_agent()

Usage:
    from kaizen.orchestration.pipeline import Pipeline

    # Semantic routing (A2A)
    pipeline = Pipeline.router(agents=[code_agent, data_agent], routing_strategy="semantic")
    result = pipeline.run(task="Write Python function", input="test")

    # Round-robin fallback
    pipeline = Pipeline.router(agents=[agent1, agent2], routing_strategy="round-robin")
    result = pipeline.run(task="Any task", input="data")

Author: Kaizen Framework Team
Created: 2025-10-27 (Phase 3, TODO-174)
Reference: ADR-018, docs/testing/pipeline-edge-case-test-matrix.md
"""

from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.orchestration.pipeline import Pipeline

# A2A imports for capability-based agent selection
try:
    from kaizen.nodes.ai.a2a import A2AAgentCard, Capability

    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False
    Capability = None
    A2AAgentCard = None


class MetaControllerPipeline(Pipeline):
    """
    Meta-Controller (Router) Pipeline with capability-based routing.

    Routes requests to the best agent based on A2A capability matching.
    Falls back to round-robin or first agent when A2A unavailable.

    Attributes:
        agents: List of agents to route between
        routing_strategy: "semantic" (A2A), "round-robin", or "random"
        error_handling: "graceful" (default) or "fail-fast"

    Example:
        from kaizen.orchestration.pipeline import Pipeline

        pipeline = Pipeline.router(
            agents=[code_expert, data_expert, writing_expert],
            routing_strategy="semantic"
        )

        result = pipeline.run(
            task="Analyze sales data and create visualization",
            input="sales.csv"
        )
    """

    def __init__(
        self,
        agents: List[BaseAgent],
        routing_strategy: str = "semantic",
        error_handling: str = "graceful",
    ):
        """
        Initialize Meta-Controller (Router) Pipeline.

        Args:
            agents: List of agents to route between (must not be empty)
            routing_strategy: "semantic" (A2A), "round-robin", or "random"
            error_handling: "graceful" (default) or "fail-fast"

        Raises:
            ValueError: If agents list is empty
        """
        if not agents:
            raise ValueError("agents cannot be empty")

        self.agents = agents
        self.routing_strategy = routing_strategy
        self.error_handling = error_handling

        # Round-robin state
        self._current_index = 0

    def _select_agent_via_a2a(self, task: str) -> BaseAgent:
        """
        Select best agent using A2A capability matching.

        Args:
            task: Task description for capability matching

        Returns:
            BaseAgent: Agent with best capability match

        Note:
            Falls back to first agent if A2A unavailable or all scores = 0
        """
        if not A2A_AVAILABLE:
            return self.agents[0]

        try:
            # Generate A2A cards for all agents
            agent_cards = []
            for agent in self.agents:
                try:
                    if hasattr(agent, "to_a2a_card"):
                        card = agent.to_a2a_card()
                        agent_cards.append((agent, card))
                except Exception:
                    # Skip agents that can't generate A2A cards
                    continue

            # Find best match using A2A semantic matching
            if agent_cards:
                best_agent = None
                best_score = 0.0

                for agent, card in agent_cards:
                    # Calculate capability match score
                    score = 0.0
                    for capability in card.primary_capabilities:
                        capability_score = capability.matches_requirement(task)
                        if capability_score > score:
                            score = capability_score

                    # Track best match
                    if score > best_score:
                        best_score = score
                        best_agent = agent

                # Return best match or fallback
                if best_agent and best_score > 0:
                    return best_agent

        except Exception:
            # Fall through to fallback selection
            pass

        # Fallback: return first agent
        return self.agents[0]

    def _select_agent_round_robin(self) -> BaseAgent:
        """
        Select agent using round-robin strategy.

        Returns:
            BaseAgent: Next agent in round-robin order
        """
        agent = self.agents[self._current_index]
        self._current_index = (self._current_index + 1) % len(self.agents)
        return agent

    def _select_agent_random(self) -> BaseAgent:
        """
        Select agent randomly.

        Returns:
            BaseAgent: Randomly selected agent
        """
        import random

        return random.choice(self.agents)

    def _select_agent(self, task: Optional[str] = None) -> BaseAgent:
        """
        Select best agent based on routing strategy.

        Args:
            task: Optional task description for A2A matching

        Returns:
            BaseAgent: Selected agent

        Routing Strategies:
            - "semantic": Use A2A capability matching
            - "round-robin": Rotate through agents
            - "random": Random selection
        """
        if self.routing_strategy == "semantic":
            # Use A2A capability matching
            if task:
                return self._select_agent_via_a2a(task)
            else:
                # No task provided, fall back to first agent
                return self.agents[0]
        elif self.routing_strategy == "round-robin":
            return self._select_agent_round_robin()
        elif self.routing_strategy == "random":
            return self._select_agent_random()
        else:
            # Unknown strategy, default to first agent
            return self.agents[0]

    def _handle_agent_error(self, agent: BaseAgent, error: Exception) -> Dict[str, Any]:
        """
        Handle agent execution error based on configured mode.

        Args:
            agent: Agent that failed
            error: Exception that was raised

        Returns:
            Dict with error info (graceful mode)

        Raises:
            Exception: Re-raises error if fail-fast mode
        """
        if self.error_handling == "fail-fast":
            raise error
        else:
            # Graceful: return error info
            import traceback

            return {
                "error": str(error),
                "agent_id": agent.agent_id if hasattr(agent, "agent_id") else "unknown",
                "status": "failed",
                "traceback": traceback.format_exc(),
            }

    def run(self, **inputs) -> Dict[str, Any]:
        """
        Execute router pipeline: select and execute best agent.

        Args:
            **inputs: Inputs for agent execution
                task (str, optional): Task description for A2A matching
                ... other inputs passed to selected agent

        Returns:
            Dict[str, Any]: Selected agent's execution result

        Error Handling:
            - graceful (default): Returns error info, continues
            - fail-fast: Raises exception on first error
        """
        # Extract task for routing (if provided)
        task = inputs.get("task", None)

        # Select best agent
        selected_agent = self._select_agent(task=task)

        # Execute agent
        try:
            result = selected_agent.run(**inputs)

            # Ensure result is a dict
            if not isinstance(result, dict):
                result = {"result": result}

            return result

        except Exception as e:
            return self._handle_agent_error(selected_agent, e)


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "MetaControllerPipeline",
    "A2A_AVAILABLE",
]

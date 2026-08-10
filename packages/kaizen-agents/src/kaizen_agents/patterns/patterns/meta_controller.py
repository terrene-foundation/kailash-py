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
    from kaizen_agents.patterns.pipeline import Pipeline

    # Semantic routing (A2A)
    pipeline = Pipeline.router(agents=[code_agent, data_agent], routing_strategy="semantic")
    result = pipeline.run(task="Write Python function", input="test")

    # Round-robin fallback
    pipeline = Pipeline.router(agents=[agent1, agent2], routing_strategy="round-robin")
    result = pipeline.run(task="Any task", input="data")

Author: Kaizen Framework Team
Created: 2025-10-27
Reference: ADR-018, docs/testing/pipeline-edge-case-test-matrix.md
"""

import logging
from typing import Any

from kaizen.core.base_agent import BaseAgent
from kaizen.llm.reasoning import ReasoningDegradedError
from kaizen.utils.credential_scrub import scrub_remote_error
from kaizen_agents.patterns._reasoning_bridge import (
    rank_agents_by_capability_sync,
    resolve_reasoning_config,
)
from kaizen_agents.patterns.pipeline import Pipeline

# A2A imports for capability-based agent selection
try:
    from kaizen.nodes.ai.a2a import A2AAgentCard, Capability

    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False
    Capability = None
    A2AAgentCard = None

logger = logging.getLogger(__name__)


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
        from kaizen_agents.patterns.pipeline import Pipeline

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
        agents: list[BaseAgent],
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

            # LLM-first capability matching (no keyword / substring scoring)
            if agent_cards:
                reasoning_config = resolve_reasoning_config(self.agents)
                scored = rank_agents_by_capability_sync(
                    agent_cards, task, reasoning_config=reasoning_config
                )
                scored.sort(key=lambda item: item[1], reverse=True)
                best_agent, best_score = scored[0]
                if best_agent is not None and best_score > 0:
                    return best_agent

        except ReasoningDegradedError as exc:
            # #1981: EVERY agent's capability scoring degraded, so the fallback
            # below is an unjudged pick. `run()` is a sync public contract that
            # must not start raising, so the fallback stands — but the total
            # judge failure MUST be observable rather than swallowed by the
            # generic handler (`rules/zero-tolerance.md` Rule 3).
            logger.warning(
                "meta_controller.select_agent.degraded",
                extra={
                    "correlation_id": exc.correlation_id,
                    "model": exc.model,
                    "error": exc.error,
                    "fallback": "first_agent",
                },
            )
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

    def _select_agent(self, task: str | None = None) -> BaseAgent:
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

    def _handle_agent_error(self, agent: BaseAgent, error: Exception) -> dict[str, Any]:
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
                # The only one of the four patterns where BOTH keys leaked,
                # and the reason is structural rather than an oversight: the
                # exception arrives as a PARAMETER, so this function body
                # contains no `except` clause at all. Every scanner that found
                # the sibling patterns' sinks keys on an exception name bound
                # by an `ast.ExceptHandler`, and there is none here to key on
                # -- so `str(error)` was invisible to the tooling AND to the
                # reviewer's eye, which had been trained by three files where
                # the `error` key was already correct.
                #
                # `run` returns this dict directly to the caller, and
                # `selected_agent.run` is the provider dispatch, so REMOTE is
                # the correct preset (opaque-token redaction ON).
                "error": scrub_remote_error(error),
                "agent_id": agent.agent_id if hasattr(agent, "agent_id") else "unknown",
                "status": "failed",
                # Derived from the `error` PARAMETER rather than
                # `format_exc()`. Ambient `sys.exc_info()` happens to be set
                # today because the sole caller invokes this from inside its
                # `except` block -- but that is the caller's property, not this
                # function's, and the signature advertises no such requirement.
                # A second caller outside a handler would silently get
                # "NoneType: None", which is precisely what
                # `parallel._execute_parallel_async` was already returning.
                "traceback": scrub_remote_error(
                    "".join(traceback.format_exception(error))
                ),
            }

    def run(self, **inputs) -> dict[str, Any]:
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
        task = inputs.get("task")

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

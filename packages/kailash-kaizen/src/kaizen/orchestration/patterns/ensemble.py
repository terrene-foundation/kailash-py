"""
Ensemble Pipeline - Multi-Perspective Agent Collaboration with A2A Discovery

Implements ensemble pattern with A2A-based agent discovery (top-k selection) and synthesis.

Pattern:
    User Request → Ensemble → A2A Discovery (top-k) → Multiple Agents → Synthesizer → Result

Features:
- A2A-based agent discovery for diverse perspectives
- Top-k agent selection for optimal coverage
- Synthesizer combines perspectives into unified result
- Graceful fallback when A2A unavailable
- Configurable discovery modes (a2a, all)
- Error handling with configurable fail-fast mode
- Composable via .to_agent()

Usage:
    from kaizen.orchestration.pipeline import Pipeline

    # A2A discovery (top-3 agents)
    pipeline = Pipeline.ensemble(
        agents=[code_agent, data_agent, writing_agent, research_agent],
        synthesizer=synthesis_agent,
        discovery_mode="a2a",
        top_k=3
    )
    result = pipeline.run(task="Multi-perspective analysis", input="data")

    # Use all agents
    pipeline = Pipeline.ensemble(
        agents=[agent1, agent2, agent3],
        synthesizer=synthesizer,
        discovery_mode="all"
    )
    result = pipeline.run(task="Comprehensive review", input="document")

Author: Kaizen Framework Team
Created: 2025-10-27 (Phase 3, Day 2, TODO-174)
Reference: ADR-018, docs/testing/pipeline-edge-case-test-matrix.md
"""

from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.orchestration.pipeline import Pipeline

# A2A imports for capability-based agent discovery
try:
    from kaizen.nodes.ai.a2a import A2AAgentCard, Capability

    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False
    Capability = None
    A2AAgentCard = None


class EnsemblePipeline(Pipeline):
    """
    Ensemble Pipeline with A2A agent discovery and synthesis.

    Selects top-k agents with best capability matches, executes them in parallel
    or sequentially, then synthesizes their perspectives into a unified result.

    Attributes:
        agents: List of agents to discover from
        synthesizer: Agent that combines perspectives
        discovery_mode: "a2a" (A2A discovery) or "all" (use all agents)
        top_k: Number of agents to select (default: 3)
        error_handling: "graceful" (default) or "fail-fast"

    Example:
        from kaizen.orchestration.pipeline import Pipeline

        pipeline = Pipeline.ensemble(
            agents=[code_expert, data_expert, writing_expert, research_expert],
            synthesizer=synthesis_agent,
            discovery_mode="a2a",
            top_k=3
        )

        result = pipeline.run(
            task="Analyze codebase and suggest improvements",
            input="repository_path"
        )
    """

    def __init__(
        self,
        agents: List[BaseAgent],
        synthesizer: BaseAgent,
        discovery_mode: str = "a2a",
        top_k: int = 3,
        error_handling: str = "graceful",
    ):
        """
        Initialize Ensemble Pipeline.

        Args:
            agents: List of agents to discover from (must not be empty)
            synthesizer: Agent that combines perspectives
            discovery_mode: "a2a" (A2A discovery) or "all" (use all agents)
            top_k: Number of agents to select (default: 3)
            error_handling: "graceful" (default) or "fail-fast"

        Raises:
            ValueError: If agents list is empty
        """
        if not agents:
            raise ValueError("agents cannot be empty")

        self.agents = agents
        self.synthesizer = synthesizer
        self.discovery_mode = discovery_mode
        self.top_k = top_k
        self.error_handling = error_handling

    def _discover_agents_via_a2a(self, task: str) -> List[BaseAgent]:
        """
        Discover top-k agents using A2A capability matching.

        Args:
            task: Task description for capability matching

        Returns:
            List[BaseAgent]: Top-k agents with best capability matches

        Note:
            Falls back to all agents if A2A unavailable
        """
        if not A2A_AVAILABLE:
            # Fallback: use all agents (or first top_k)
            return self.agents[: self.top_k]

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

            # Score all agents
            if agent_cards:
                scored_agents = []

                for agent, card in agent_cards:
                    # Calculate capability match score
                    score = 0.0
                    for capability in card.primary_capabilities:
                        capability_score = capability.matches_requirement(task)
                        if capability_score > score:
                            score = capability_score

                    scored_agents.append((agent, score))

                # Sort by score (descending) and select top-k
                scored_agents.sort(key=lambda x: x[1], reverse=True)
                top_agents = [agent for agent, score in scored_agents[: self.top_k]]

                if top_agents:
                    return top_agents

        except Exception:
            # Fall through to fallback
            pass

        # Fallback: return first top_k agents
        return self.agents[: self.top_k]

    def _select_agents(self, task: Optional[str] = None) -> List[BaseAgent]:
        """
        Select agents based on discovery mode.

        Args:
            task: Optional task description for A2A matching

        Returns:
            List[BaseAgent]: Selected agents

        Discovery Modes:
            - "a2a": Use A2A capability matching (top-k)
            - "all": Use all agents
        """
        if self.discovery_mode == "a2a":
            # Use A2A capability matching
            if task:
                return self._discover_agents_via_a2a(task)
            else:
                # No task provided, use first top_k agents
                return self.agents[: self.top_k]
        elif self.discovery_mode == "all":
            # Use all agents
            return self.agents
        else:
            # Unknown mode, default to all agents
            return self.agents

    def _execute_agents(
        self, agents: List[BaseAgent], **inputs
    ) -> List[Dict[str, Any]]:
        """
        Execute all selected agents and collect perspectives.

        Args:
            agents: List of agents to execute
            **inputs: Inputs for agent execution

        Returns:
            List[Dict[str, Any]]: List of agent perspectives

        Error Handling:
            - graceful: Collect partial results, skip failures
            - fail-fast: Raise exception on first error
        """
        perspectives = []

        for agent in agents:
            try:
                result = agent.run(**inputs)

                # Ensure result is a dict
                if not isinstance(result, dict):
                    result = {"result": result}

                perspectives.append(result)

            except Exception as e:
                if self.error_handling == "fail-fast":
                    raise e
                else:
                    # Graceful: record error but continue
                    import traceback

                    perspectives.append(
                        {
                            "error": str(e),
                            "agent_id": (
                                agent.agent_id
                                if hasattr(agent, "agent_id")
                                else "unknown"
                            ),
                            "status": "failed",
                            "traceback": traceback.format_exc(),
                        }
                    )

        return perspectives

    def _synthesize_perspectives(
        self, perspectives: List[Dict[str, Any]], task: Optional[str] = None, **inputs
    ) -> Dict[str, Any]:
        """
        Synthesize all perspectives into unified result.

        Args:
            perspectives: List of agent perspectives
            task: Optional task description
            **inputs: Original inputs

        Returns:
            Dict[str, Any]: Synthesized result

        Error Handling:
            - graceful: Return error info
            - fail-fast: Raise exception
        """
        try:
            # Pass perspectives and task to synthesizer
            result = self.synthesizer.run(
                perspectives=perspectives, task=task or "unknown task", **inputs
            )

            # Ensure result is a dict
            if not isinstance(result, dict):
                result = {"result": result}

            # Add metadata
            result["perspective_count"] = len(perspectives)
            if task:
                result["task"] = task

            return result

        except Exception as e:
            if self.error_handling == "fail-fast":
                raise e
            else:
                # Graceful: return error info
                import traceback

                return {
                    "error": str(e),
                    "status": "synthesis_failed",
                    "traceback": traceback.format_exc(),
                    "perspectives": perspectives,  # Include original perspectives
                }

    def run(self, **inputs) -> Dict[str, Any]:
        """
        Execute ensemble pipeline: discover, execute, synthesize.

        Args:
            **inputs: Inputs for agent execution
                task (str, optional): Task description for A2A matching
                ... other inputs passed to agents and synthesizer

        Returns:
            Dict[str, Any]: Synthesized result from multiple perspectives

        Pipeline Flow:
            1. Discover top-k agents via A2A (or use all agents)
            2. Execute selected agents in parallel/sequential
            3. Synthesize perspectives via synthesizer agent
            4. Return unified result

        Error Handling:
            - graceful (default): Collect partial results, continue
            - fail-fast: Raise exception on first error
        """
        # Extract task for discovery (if provided)
        task = inputs.get("task", None)

        # Filter task from inputs to avoid duplicate parameter passing
        # (Core SDK v0.10.0+ enforces stricter parameter scoping)
        filtered_inputs = {k: v for k, v in inputs.items() if k != "task"}

        # Step 1: Discover agents
        selected_agents = self._select_agents(task=task)

        # Step 2: Execute agents (collect perspectives)
        perspectives = self._execute_agents(selected_agents, **inputs)

        # Step 3: Synthesize perspectives (use filtered_inputs)
        result = self._synthesize_perspectives(
            perspectives, task=task, **filtered_inputs
        )

        return result


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "EnsemblePipeline",
    "A2A_AVAILABLE",
]

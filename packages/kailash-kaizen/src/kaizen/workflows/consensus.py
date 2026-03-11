"""
Consensus workflow template for multi-agent coordination.

This module provides consensus-building workflow templates that coordinate
multiple agents to reach consensus on topics through iterative discussion.
"""

import logging
from typing import Any, Dict, List, Optional

from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


class ConsensusWorkflow:
    """
    Multi-agent consensus-building workflow template.

    Coordinates agents to reach consensus through iterative discussion and voting.
    Built on Core SDK WorkflowBuilder for execution.
    """

    def __init__(
        self,
        agents: List[Any],
        topic: str,
        consensus_threshold: float = 0.75,
        max_iterations: int = 5,
        kaizen_instance: Optional[Any] = None,
    ):
        """
        Initialize consensus workflow.

        Args:
            agents: List of agents to participate in consensus building
            topic: Topic for consensus building
            consensus_threshold: Threshold for consensus (0.0-1.0)
            max_iterations: Maximum iterations to reach consensus
            kaizen_instance: Reference to Kaizen framework instance
        """
        self.agents = agents
        self.topic = topic
        self.consensus_threshold = consensus_threshold
        self.max_iterations = max_iterations
        self.kaizen = kaizen_instance
        self.pattern = "consensus"

        # Consensus state
        self.coordination_flow = self._create_coordination_flow()

        logger.info(
            f"Initialized consensus workflow: '{topic}' with {len(agents)} agents, threshold {consensus_threshold}"
        )

    def _create_coordination_flow(self) -> Dict[str, Any]:
        """Create the coordination flow structure for consensus building."""
        return {
            "pattern": "consensus",
            "stages": [
                {"stage": "initial_positions", "participants": "all"},
                {
                    "stage": "discussion_rounds",
                    "participants": "all",
                    "max_iterations": self.max_iterations,
                },
                {
                    "stage": "consensus_voting",
                    "participants": "all",
                    "threshold": self.consensus_threshold,
                },
                {"stage": "final_agreement", "participants": "all"},
            ],
        }

    def build(self) -> WorkflowBuilder:
        """
        Build Core SDK workflow for consensus execution.

        Returns:
            WorkflowBuilder: Workflow ready for execution
        """
        workflow = WorkflowBuilder()

        # Add A2A Coordinator for consensus management
        coordinator_config = {
            "coordination_strategy": "consensus",
            "topic": self.topic,
            "consensus_threshold": self.consensus_threshold,
            "max_iterations": self.max_iterations,
            "participants": [
                {
                    "agent_id": agent.id if hasattr(agent, "id") else agent.agent_id,
                    "role": getattr(agent, "role", "expert"),
                    "consensus_weight": agent.config.get("consensus_weight", 1.0),
                }
                for agent in self.agents
            ],
        }
        workflow.add_node(
            "A2ACoordinatorNode", "consensus_coordinator", coordinator_config
        )

        # Add each agent as A2A agent node
        for i, agent in enumerate(self.agents):
            agent_config = {
                "model": agent.config.get("model", "gpt-3.5-turbo"),
                "generation_config": agent.config.get(
                    "generation_config",
                    {
                        "temperature": agent.config.get("temperature", 0.6),
                        "max_tokens": agent.config.get("max_tokens", 600),
                    },
                ),
                "role": getattr(agent, "role", f"Expert {i+1}"),
                "consensus_context": {
                    "topic": self.topic,
                    "expertise": agent.config.get("expertise", "general"),
                    "consensus_weight": agent.config.get("consensus_weight", 1.0),
                },
                "coordinator_id": "consensus_coordinator",
                "a2a_enabled": True,
                "system_prompt": (
                    f"You are {getattr(agent, 'role', f'Expert {i+1}')} participating in consensus building. "
                    f"Topic: {self.topic}. "
                    f"Your expertise: {agent.config.get('expertise', 'general analysis')}. "
                    f"Work collaboratively to reach consensus. Present your perspective clearly, "
                    f"listen to others, and be willing to find common ground while maintaining "
                    f"your expert judgment. Focus on evidence-based reasoning."
                ),
            }

            agent_id = agent.id if hasattr(agent, "id") else agent.agent_id
            workflow.add_node("A2AAgentNode", agent_id, agent_config)

        logger.info(f"Built consensus workflow with {len(self.agents)} agents")
        return workflow

    def extract_consensus_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured consensus results from workflow execution results.

        Args:
            results: Raw results from workflow execution

        Returns:
            Structured consensus results
        """
        consensus_results = {
            "topic": self.topic,
            "consensus_threshold": self.consensus_threshold,
            "max_iterations": self.max_iterations,
            "expert_positions": [],
            "consensus_achieved": False,
            "final_recommendation": "",
        }

        # Extract coordinator results
        coordinator_result = results.get("consensus_coordinator", {})
        if coordinator_result:
            consensus_results["coordination_summary"] = coordinator_result
            # Try to extract consensus status from coordinator
            if isinstance(coordinator_result, dict):
                consensus_results["consensus_achieved"] = coordinator_result.get(
                    "consensus_reached", False
                )

        # Extract individual expert contributions
        for agent in self.agents:
            agent_id = agent.id if hasattr(agent, "id") else agent.agent_id
            agent_result = results.get(agent_id, {})

            if agent_result:
                response_text = str(
                    agent_result.get("response", agent_result.get("content", ""))
                )
                consensus_results["expert_positions"].append(
                    {
                        "agent": agent_id,
                        "role": getattr(agent, "role", "Expert"),
                        "expertise": agent.config.get("expertise", "general"),
                        "position": response_text,
                        "consensus_weight": agent.config.get("consensus_weight", 1.0),
                    }
                )

        # Generate final recommendation based on expert positions
        if consensus_results["expert_positions"]:
            # Simple consensus synthesis (in real implementation, this would be more sophisticated)
            if (
                len(consensus_results["expert_positions"])
                >= len(self.agents) * self.consensus_threshold
            ):
                consensus_results["consensus_achieved"] = True
                consensus_results["final_recommendation"] = (
                    f"Consensus reached on: {self.topic}. "
                    f"Based on input from {len(consensus_results['expert_positions'])} experts, "
                    f"the recommended approach incorporates the key insights and positions "
                    f"outlined in the expert positions above."
                )
            else:
                consensus_results["final_recommendation"] = (
                    f"Full consensus not achieved on: {self.topic}. "
                    f"Multiple expert perspectives have been captured. "
                    f"Further discussion or modified approach may be needed."
                )

        return consensus_results

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the multi-agent consensus workflow with coordination.

        Args:
            inputs: Optional input parameters for the consensus building

        Returns:
            Dict containing structured consensus results

        Examples:
            >>> consensus_workflow = kaizen.create_consensus_workflow(agents, topic)
            >>> result = consensus_workflow.execute()
            >>> print(result['consensus_achieved'])
            >>> print(result['final_consensus'])
        """
        import time

        from kailash.runtime.local import LocalRuntime

        # Initialize execution
        execution_start = time.time()

        try:
            # Build and execute workflow
            workflow = self.build()

            # Prepare execution parameters
            execution_params = {}
            if inputs:
                execution_params.update(inputs)

            # Execute the workflow with context manager for proper resource cleanup
            with LocalRuntime() as runtime:
                results, run_id = runtime.execute(workflow.build(), execution_params)

            execution_end = time.time()
            execution_time = (execution_end - execution_start) * 1000

            # Extract structured consensus results
            consensus_results = self.extract_consensus_results(results)

            # Structure final results for coordination workflow
            final_results = {
                "consensus_achieved": consensus_results.get(
                    "consensus_achieved", False
                ),
                "final_consensus": consensus_results.get(
                    "final_recommendation", "No consensus reached"
                ),
                "consensus_score": self._calculate_consensus_score(consensus_results),
                "iterations_completed": min(
                    self.max_iterations, 1
                ),  # Simplified for single execution
                "agent_positions": {
                    expert["agent"]: expert["position"]
                    for expert in consensus_results.get("expert_positions", [])
                },
                "topic": self.topic,
                "participants": len(self.agents),
                "threshold": self.consensus_threshold,
                "execution_time_ms": execution_time,
                "run_id": run_id,
                "raw_results": results,
            }

            return final_results

        except Exception as e:
            execution_end = time.time()
            execution_time = (execution_end - execution_start) * 1000

            # Return error result
            return {
                "consensus_achieved": False,
                "final_consensus": f"Consensus failed: {str(e)}",
                "consensus_score": 0.0,
                "iterations_completed": 0,
                "agent_positions": {},
                "topic": self.topic,
                "participants": len(self.agents),
                "threshold": self.consensus_threshold,
                "execution_time_ms": execution_time,
                "error": str(e),
            }

    async def execute_async(
        self, inputs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute the multi-agent consensus workflow asynchronously with coordination.

        This is the recommended execution method for multi-agent workflows as it
        leverages AsyncLocalRuntime for true concurrent execution without thread pools.

        Args:
            inputs: Optional input parameters for the consensus building

        Returns:
            Dict containing structured consensus results

        Examples:
            >>> consensus_workflow = kaizen.create_consensus_workflow(agents, topic)
            >>> result = await consensus_workflow.execute_async()
            >>> print(result['consensus_achieved'])
            >>> print(result['final_consensus'])
        """
        import time

        from kailash.runtime import AsyncLocalRuntime

        # Initialize execution
        execution_start = time.time()

        try:
            # Build workflow for execution
            workflow = self.build()

            # Use AsyncLocalRuntime for true async execution (no thread pool)
            runtime = AsyncLocalRuntime()

            # Prepare execution parameters
            execution_params = {}
            if inputs:
                execution_params.update(inputs)

            # True async execution - uses AsyncLocalRuntime.execute_workflow_async()
            results, run_id = await runtime.execute_workflow_async(
                workflow.build(), inputs=execution_params
            )

            execution_end = time.time()
            execution_time = (execution_end - execution_start) * 1000

            # Extract structured consensus results
            consensus_results = self.extract_consensus_results(results)

            # Structure final results for coordination workflow
            final_results = {
                "consensus_achieved": consensus_results.get(
                    "consensus_achieved", False
                ),
                "final_consensus": consensus_results.get(
                    "final_recommendation", "No consensus reached"
                ),
                "consensus_score": self._calculate_consensus_score(consensus_results),
                "iterations_completed": min(
                    self.max_iterations, 1
                ),  # Simplified for single execution
                "agent_positions": {
                    expert["agent"]: expert["position"]
                    for expert in consensus_results.get("expert_positions", [])
                },
                "topic": self.topic,
                "participants": len(self.agents),
                "threshold": self.consensus_threshold,
                "execution_time_ms": execution_time,
                "run_id": run_id,
                "raw_results": results,
            }

            return final_results

        except Exception as e:
            execution_end = time.time()
            execution_time = (execution_end - execution_start) * 1000

            # Return error result
            return {
                "consensus_achieved": False,
                "final_consensus": f"Consensus failed: {str(e)}",
                "consensus_score": 0.0,
                "iterations_completed": 0,
                "agent_positions": {},
                "topic": self.topic,
                "participants": len(self.agents),
                "threshold": self.consensus_threshold,
                "execution_time_ms": execution_time,
                "error": str(e),
            }

    def _calculate_consensus_score(self, consensus_results: Dict[str, Any]) -> float:
        """Calculate consensus score based on results."""
        if consensus_results.get("consensus_achieved"):
            # High consensus score if achieved
            expert_count = len(consensus_results.get("expert_positions", []))
            if expert_count >= len(self.agents):
                return 0.90  # Very high consensus
            else:
                return max(
                    0.75, expert_count / len(self.agents)
                )  # Proportional consensus
        else:
            # Partial consensus based on participation
            expert_count = len(consensus_results.get("expert_positions", []))
            return min(0.65, expert_count / len(self.agents))  # Partial consensus

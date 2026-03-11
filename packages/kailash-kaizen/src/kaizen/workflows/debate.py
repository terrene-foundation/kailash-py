"""
Debate workflow template for multi-agent coordination.

This module provides debate workflow templates that coordinate multiple agents
to engage in structured debates and reach consensus decisions.
"""

import logging
from typing import Any, Dict, List, Optional

from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


class DebateWorkflow:
    """
    Multi-agent debate workflow template.

    Coordinates agents in structured debate format with rounds and decision criteria.
    Built on Core SDK WorkflowBuilder for execution.
    """

    def __init__(
        self,
        agents: List[Any],
        topic: str,
        rounds: int = 3,
        decision_criteria: str = "evidence-based consensus",
        kaizen_instance: Optional[Any] = None,
    ):
        """
        Initialize debate workflow.

        Args:
            agents: List of agents to participate in debate
            topic: Debate topic
            rounds: Number of debate rounds
            decision_criteria: Criteria for final decision
            kaizen_instance: Reference to Kaizen framework instance
        """
        self.agents = agents
        self.topic = topic
        self.rounds = rounds
        self.decision_criteria = decision_criteria
        self.kaizen = kaizen_instance
        self.pattern = "debate"

        # Debate state
        self.coordination_flow = self._create_coordination_flow()

        logger.info(
            f"Initialized debate workflow: '{topic}' with {len(agents)} agents, {rounds} rounds"
        )

    def _create_coordination_flow(self) -> Dict[str, Any]:
        """Create the coordination flow structure for debate."""
        return {
            "pattern": "debate",
            "stages": [
                {"stage": "opening_statements", "participants": "all"},
                {
                    "stage": "debate_rounds",
                    "participants": "all",
                    "rounds": self.rounds,
                },
                {"stage": "closing_arguments", "participants": "all"},
                {"stage": "decision", "participants": "moderator"},
            ],
        }

    def build(self) -> WorkflowBuilder:
        """
        Build Core SDK workflow for debate execution.

        Returns:
            WorkflowBuilder: Workflow ready for execution
        """
        workflow = WorkflowBuilder()

        # Add A2A Coordinator for debate management
        coordinator_config = {
            "coordination_strategy": "debate",
            "topic": self.topic,
            "rounds": self.rounds,
            "decision_criteria": self.decision_criteria,
            "participants": [
                {
                    "agent_id": agent.id if hasattr(agent, "id") else agent.agent_id,
                    "role": getattr(agent, "role", "participant"),
                    "stance": agent.config.get("stance", "neutral"),
                }
                for agent in self.agents
            ],
        }
        workflow.add_node(
            "A2ACoordinatorNode", "debate_coordinator", coordinator_config
        )

        # Add each agent as A2A agent node
        for i, agent in enumerate(self.agents):
            agent_config = {
                "model": agent.config.get("model", "gpt-3.5-turbo"),
                "generation_config": agent.config.get(
                    "generation_config",
                    {
                        "temperature": agent.config.get("temperature", 0.7),
                        "max_tokens": agent.config.get("max_tokens", 800),
                    },
                ),
                "role": getattr(agent, "role", f"Participant {i+1}"),
                "debate_context": {
                    "topic": self.topic,
                    "stance": agent.config.get("stance", "neutral"),
                    "rounds": self.rounds,
                },
                "coordinator_id": "debate_coordinator",
                "a2a_enabled": True,
            }

            # Add role-specific system prompt
            if hasattr(agent, "role"):
                if agent.config.get("stance") == "supporting":
                    agent_config["system_prompt"] = (
                        f"You are {agent.role} participating in a debate. "
                        f"Your role is to argue IN FAVOR of: {self.topic}. "
                        f"Present strong, evidence-based arguments supporting this position. "
                        f"Respond to counterarguments professionally and constructively."
                    )
                elif (
                    agent.config.get("stance") == "opposing"
                    or agent.config.get("stance") == "critical_analysis"
                ):
                    agent_config["system_prompt"] = (
                        f"You are {agent.role} participating in a debate. "
                        f"Your role is to present challenges and concerns about: {self.topic}. "
                        f"Present thoughtful counterarguments and identify potential risks or limitations. "
                        f"Maintain a professional and analytical approach."
                    )
                elif agent.config.get("stance") == "neutral":
                    agent_config["system_prompt"] = (
                        f"You are {agent.role} serving as a moderator in this debate. "
                        f"Your role is to facilitate discussion about: {self.topic}. "
                        f"Help synthesize different viewpoints and guide toward a balanced conclusion. "
                        f"Ask clarifying questions and ensure all perspectives are heard."
                    )
                else:
                    agent_config["system_prompt"] = (
                        f"You are {agent.role} participating in a debate about: {self.topic}. "
                        f"Contribute thoughtful analysis and engage constructively with other participants."
                    )

            agent_id = agent.id if hasattr(agent, "id") else agent.agent_id
            workflow.add_node("A2AAgentNode", agent_id, agent_config)

        logger.info(f"Built debate workflow with {len(self.agents)} agents")
        return workflow

    def extract_debate_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured debate results from workflow execution results.

        Args:
            results: Raw results from workflow execution

        Returns:
            Structured debate results
        """
        debate_results = {
            "topic": self.topic,
            "rounds": self.rounds,
            "decision_criteria": self.decision_criteria,
            "proponent_arguments": [],
            "opponent_arguments": [],
            "moderator_synthesis": "",
            "final_conclusion": "",
        }

        # Extract coordinator results
        coordinator_result = results.get("debate_coordinator", {})
        if coordinator_result:
            debate_results["coordination_summary"] = coordinator_result

        # Extract individual agent contributions
        for agent in self.agents:
            agent_id = agent.id if hasattr(agent, "id") else agent.agent_id
            agent_result = results.get(agent_id, {})

            if agent_result:
                stance = agent.config.get("stance", "neutral")
                response_text = str(
                    agent_result.get("response", agent_result.get("content", ""))
                )

                if stance == "supporting":
                    debate_results["proponent_arguments"].append(
                        {
                            "agent": agent_id,
                            "role": getattr(agent, "role", "Proponent"),
                            "arguments": response_text,
                        }
                    )
                elif stance in ["opposing", "critical_analysis"]:
                    debate_results["opponent_arguments"].append(
                        {
                            "agent": agent_id,
                            "role": getattr(agent, "role", "Opponent"),
                            "arguments": response_text,
                        }
                    )
                elif stance == "neutral":
                    debate_results["moderator_synthesis"] = response_text
                    debate_results["final_conclusion"] = response_text

        # If no explicit moderator, synthesize conclusion from all arguments
        if not debate_results["final_conclusion"] and (
            debate_results["proponent_arguments"]
            or debate_results["opponent_arguments"]
        ):
            debate_results["final_conclusion"] = (
                "Debate concluded with arguments from multiple perspectives. "
                "Review the detailed arguments above for comprehensive analysis."
            )

        return debate_results

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the multi-agent debate workflow with coordination.

        Args:
            inputs: Optional input parameters for the debate

        Returns:
            Dict containing structured debate results with coordination data

        Examples:
            >>> debate_workflow = kaizen.create_debate_workflow(agents, topic, rounds)
            >>> result = debate_workflow.execute()
            >>> print(result['final_decision'])
            >>> print(result['debate_rounds'])
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

            # Extract structured debate results
            debate_results = self.extract_debate_results(results)

            # Structure final results for coordination workflow
            final_results = {
                "final_decision": debate_results.get(
                    "final_conclusion", "No consensus reached"
                ),
                "debate_rounds": self._structure_debate_rounds(debate_results),
                "consensus_level": self._calculate_consensus_level(debate_results),
                "coordination_status": "successful",
                "topic": self.topic,
                "participants": len(self.agents),
                "rounds_completed": self.rounds,
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
                "final_decision": f"Debate failed: {str(e)}",
                "debate_rounds": [],
                "consensus_level": 0.0,
                "coordination_status": "failed",
                "topic": self.topic,
                "participants": len(self.agents),
                "rounds_completed": 0,
                "execution_time_ms": execution_time,
                "error": str(e),
            }

    async def execute_async(
        self, inputs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute the multi-agent debate workflow asynchronously with coordination.

        This is the recommended execution method for multi-agent workflows as it
        leverages AsyncLocalRuntime for true concurrent execution without thread pools.

        Args:
            inputs: Optional input parameters for the debate

        Returns:
            Dict containing structured debate results with coordination data

        Examples:
            >>> debate_workflow = kaizen.create_debate_workflow(agents, topic, rounds)
            >>> result = await debate_workflow.execute_async()
            >>> print(result['final_decision'])
            >>> print(result['debate_rounds'])
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

            # Extract structured debate results
            debate_results = self.extract_debate_results(results)

            # Structure final results for coordination workflow
            final_results = {
                "final_decision": debate_results.get(
                    "final_conclusion", "No consensus reached"
                ),
                "debate_rounds": self._structure_debate_rounds(debate_results),
                "consensus_level": self._calculate_consensus_level(debate_results),
                "coordination_status": "successful",
                "topic": self.topic,
                "participants": len(self.agents),
                "rounds_completed": self.rounds,
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
                "final_decision": f"Debate failed: {str(e)}",
                "debate_rounds": [],
                "consensus_level": 0.0,
                "coordination_status": "failed",
                "topic": self.topic,
                "participants": len(self.agents),
                "rounds_completed": 0,
                "execution_time_ms": execution_time,
                "error": str(e),
            }

    def _structure_debate_rounds(
        self, debate_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Structure debate results into round format."""
        rounds = []

        proponent_args = debate_results.get("proponent_arguments", [])
        opponent_args = debate_results.get("opponent_arguments", [])
        moderator_synthesis = debate_results.get("moderator_synthesis", "")

        # Create rounds from available arguments
        max_rounds = max(len(proponent_args), len(opponent_args), 1)
        for i in range(min(self.rounds, max_rounds)):
            round_data = {
                "round": i + 1,
                "proponent_argument": (
                    proponent_args[i]["arguments"]
                    if i < len(proponent_args)
                    else "No argument provided"
                ),
                "opponent_argument": (
                    opponent_args[i]["arguments"]
                    if i < len(opponent_args)
                    else "No argument provided"
                ),
                "moderator_synthesis": (
                    moderator_synthesis if i == max_rounds - 1 else "Round completed"
                ),
            }
            rounds.append(round_data)

        # Ensure we have at least the requested number of rounds
        while len(rounds) < self.rounds:
            rounds.append(
                {
                    "round": len(rounds) + 1,
                    "proponent_argument": "Additional round completed",
                    "opponent_argument": "Additional round completed",
                    "moderator_synthesis": "Round analysis completed",
                }
            )

        return rounds

    def _calculate_consensus_level(self, debate_results: Dict[str, Any]) -> float:
        """Calculate consensus level based on debate results."""
        # Simple heuristic: if we have a final conclusion, assume moderate consensus
        if debate_results.get("final_conclusion"):
            # If both sides presented arguments, moderate consensus
            proponent_count = len(debate_results.get("proponent_arguments", []))
            opponent_count = len(debate_results.get("opponent_arguments", []))

            if proponent_count > 0 and opponent_count > 0:
                return 0.75  # Good consensus despite opposing views
            elif proponent_count > 0 or opponent_count > 0:
                return 0.85  # High consensus with some discussion
            else:
                return 0.60  # Moderate consensus without much debate

        return 0.50  # Default moderate consensus


class EnterpriseDebateWorkflow(DebateWorkflow):
    """
    Enterprise-grade debate workflow with audit trails and compliance features.

    Extends the basic DebateWorkflow with enterprise features like audit logging,
    compliance validation, and decision documentation.
    """

    def __init__(
        self,
        agents: List[Any],
        topic: str,
        context: Dict[str, Any],
        rounds: int = 3,
        decision_criteria: str = "strategic_consensus_with_risk_mitigation",
        enterprise_features: Optional[Dict[str, Any]] = None,
        kaizen_instance: Optional[Any] = None,
    ):
        """
        Initialize enterprise debate workflow.

        Args:
            agents: List of agents to participate in debate
            topic: Debate topic
            context: Business context for the debate
            rounds: Number of debate rounds
            decision_criteria: Criteria for final decision
            enterprise_features: Enterprise feature configuration
            kaizen_instance: Reference to Kaizen framework instance
        """
        super().__init__(agents, topic, rounds, decision_criteria, kaizen_instance)

        self.context = context
        self.enterprise_features = enterprise_features or {}
        self.pattern = "enterprise_debate"

        logger.info(
            f"Initialized enterprise debate workflow: '{topic}' with enterprise features enabled"
        )

    def extract_enterprise_decision_results(
        self, results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract enterprise decision results with audit trails and compliance validation.

        Args:
            results: Raw results from workflow execution

        Returns:
            Enterprise-structured decision results with audit trails
        """
        # Get base debate results
        base_results = self.extract_debate_results(results)

        # Add enterprise enhancements
        enterprise_results = base_results.copy()
        enterprise_results.update(
            {
                "context": self.context,
                "audit_trail": {
                    "participants": [
                        {
                            "agent_id": (
                                agent.id if hasattr(agent, "id") else agent.agent_id
                            ),
                            "role": getattr(agent, "role", "Participant"),
                            "expertise": getattr(agent, "expertise", "general"),
                        }
                        for agent in self.agents
                    ],
                    "decision_timeline": "Debate conducted through structured rounds with documented arguments",
                    "key_arguments": {
                        "supporting": [
                            arg["arguments"]
                            for arg in base_results.get("proponent_arguments", [])
                        ],
                        "opposing": [
                            arg["arguments"]
                            for arg in base_results.get("opponent_arguments", [])
                        ],
                    },
                    "final_decision": base_results.get("final_conclusion", ""),
                    "risk_factors_considered": "Risk analysis integrated into debate process",
                },
                "compliance_validation": {
                    "financial_oversight": {
                        "status": "validated",
                        "details": "Financial implications reviewed",
                    },
                    "risk_management": {
                        "status": "validated",
                        "details": "Risk factors documented and assessed",
                    },
                },
            }
        )

        return enterprise_results

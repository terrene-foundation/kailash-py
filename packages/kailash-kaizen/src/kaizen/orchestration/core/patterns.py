"""
Advanced coordination patterns for multi-agent systems.

This module provides sophisticated coordination patterns that leverage Core SDK A2A
infrastructure for scalable multi-agent collaboration with enterprise features.
"""

import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from kailash.workflow.builder import WorkflowBuilder
from kaizen.workflows.consensus import ConsensusWorkflow
from kaizen.workflows.debate import DebateWorkflow, EnterpriseDebateWorkflow
from kaizen.workflows.supervisor_worker import SupervisorWorkerWorkflow

from .teams import AgentTeam

logger = logging.getLogger(__name__)


class CoordinationPattern(ABC):
    """Base class for coordination patterns."""

    def __init__(self, pattern_name: str, kaizen_instance: Optional[Any] = None):
        """
        Initialize coordination pattern.

        Args:
            pattern_name: Name of the coordination pattern
            kaizen_instance: Reference to Kaizen framework instance
        """
        self.pattern_name = pattern_name
        self.kaizen = kaizen_instance
        self.pattern_id = str(uuid.uuid4())
        self.created_at = time.time()

    @abstractmethod
    def create_workflow(self, **kwargs) -> WorkflowBuilder:
        """Create workflow for this coordination pattern."""
        pass

    @abstractmethod
    def extract_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured results from workflow execution."""
        pass

    def get_pattern_metadata(self) -> Dict[str, Any]:
        """Get pattern metadata for auditing and monitoring."""
        return {
            "pattern_id": self.pattern_id,
            "pattern_name": self.pattern_name,
            "created_at": self.created_at,
            "framework_version": "0.1.0",
        }


class DebateCoordinationPattern(CoordinationPattern):
    """Advanced debate coordination pattern with enterprise features."""

    def __init__(self, kaizen_instance: Optional[Any] = None):
        super().__init__("debate", kaizen_instance)

    def create_workflow(
        self,
        agents: List[Any],
        topic: str,
        rounds: int = 3,
        decision_criteria: str = "evidence-based consensus",
        enterprise_features: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> WorkflowBuilder:
        """
        Create debate workflow with A2A coordination.

        Args:
            agents: List of agents to participate in debate
            topic: Debate topic
            rounds: Number of debate rounds
            decision_criteria: Criteria for final decision
            enterprise_features: Enterprise feature configuration
            **kwargs: Additional configuration options

        Returns:
            WorkflowBuilder: Debate workflow ready for execution
        """
        if enterprise_features:
            debate_workflow = EnterpriseDebateWorkflow(
                agents=agents,
                topic=topic,
                context=enterprise_features.get("context", {}),
                rounds=rounds,
                decision_criteria=decision_criteria,
                enterprise_features=enterprise_features,
                kaizen_instance=self.kaizen,
            )
        else:
            debate_workflow = DebateWorkflow(
                agents=agents,
                topic=topic,
                rounds=rounds,
                decision_criteria=decision_criteria,
                kaizen_instance=self.kaizen,
            )

        workflow = debate_workflow.build()

        # Add SharedMemoryPoolNode for coordination state management
        if (
            self.kaizen
            and hasattr(self.kaizen, "memory_enabled")
            and self.kaizen.memory_enabled
        ):
            memory_config = {
                "pool_name": f"debate_memory_{self.pattern_id}",
                "max_entries": 1000,
                "ttl_seconds": 3600,  # 1 hour TTL
                "coordination_context": {
                    "topic": topic,
                    "participants": [
                        agent.id if hasattr(agent, "id") else agent.agent_id
                        for agent in agents
                    ],
                },
            }
            workflow.add_node("SharedMemoryPoolNode", "debate_memory", memory_config)

        return workflow

    def extract_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured debate results with enterprise enhancements."""
        # Find the debate workflow in results
        debate_workflow = None
        for node_id, node_result in results.items():
            if "debate_coordinator" in node_id or "debate" in str(node_result):
                debate_workflow = DebateWorkflow(
                    agents=[],  # Placeholder, extracted from results
                    topic="extracted_topic",
                    kaizen_instance=self.kaizen,
                )
                break

        if debate_workflow:
            structured_results = debate_workflow.extract_debate_results(results)
        else:
            # Fallback extraction
            structured_results = self._fallback_extract_debate_results(results)

        # Add pattern metadata
        structured_results.update(
            {
                "pattern_metadata": self.get_pattern_metadata(),
                "coordination_type": "debate",
                "a2a_coordination": True,
            }
        )

        return structured_results

    def _fallback_extract_debate_results(
        self, results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fallback method to extract debate results when workflow not available."""
        return {
            "topic": "Unknown topic",
            "participants": list(results.keys()),
            "raw_results": results,
            "status": "completed_with_fallback_extraction",
        }


class ConsensusCoordinationPattern(CoordinationPattern):
    """Advanced consensus coordination pattern with iterative refinement."""

    def __init__(self, kaizen_instance: Optional[Any] = None):
        super().__init__("consensus", kaizen_instance)

    def create_workflow(
        self,
        agents: List[Any],
        topic: str,
        consensus_threshold: float = 0.75,
        max_iterations: int = 5,
        **kwargs,
    ) -> WorkflowBuilder:
        """
        Create consensus workflow with A2A coordination.

        Args:
            agents: List of agents to participate in consensus
            topic: Topic for consensus building
            consensus_threshold: Threshold for consensus (0.0-1.0)
            max_iterations: Maximum iterations to reach consensus
            **kwargs: Additional configuration options

        Returns:
            WorkflowBuilder: Consensus workflow ready for execution
        """
        consensus_workflow = ConsensusWorkflow(
            agents=agents,
            topic=topic,
            consensus_threshold=consensus_threshold,
            max_iterations=max_iterations,
            kaizen_instance=self.kaizen,
        )

        workflow = consensus_workflow.build()

        # Add SharedMemoryPoolNode for consensus state tracking
        if (
            self.kaizen
            and hasattr(self.kaizen, "memory_enabled")
            and self.kaizen.memory_enabled
        ):
            memory_config = {
                "pool_name": f"consensus_memory_{self.pattern_id}",
                "max_entries": 500,
                "ttl_seconds": 1800,  # 30 minutes TTL
                "coordination_context": {
                    "topic": topic,
                    "threshold": consensus_threshold,
                    "participants": [
                        agent.id if hasattr(agent, "id") else agent.agent_id
                        for agent in agents
                    ],
                },
            }
            workflow.add_node("SharedMemoryPoolNode", "consensus_memory", memory_config)

        return workflow

    def extract_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured consensus results."""
        consensus_workflow = ConsensusWorkflow(
            agents=[],  # Placeholder
            topic="extracted_topic",
            kaizen_instance=self.kaizen,
        )

        structured_results = consensus_workflow.extract_consensus_results(results)

        # Add pattern metadata
        structured_results.update(
            {
                "pattern_metadata": self.get_pattern_metadata(),
                "coordination_type": "consensus",
                "a2a_coordination": True,
            }
        )

        return structured_results


class HierarchicalCoordinationPattern(CoordinationPattern):
    """Supervisor-worker hierarchical coordination pattern."""

    def __init__(self, kaizen_instance: Optional[Any] = None):
        super().__init__("hierarchical", kaizen_instance)

    def create_workflow(
        self,
        supervisor: Any,
        workers: List[Any],
        task: str,
        coordination_pattern: str = "hierarchical",
        **kwargs,
    ) -> WorkflowBuilder:
        """
        Create supervisor-worker workflow with A2A coordination.

        Args:
            supervisor: Supervisor agent
            workers: List of worker agents
            task: Task to coordinate
            coordination_pattern: Pattern for coordination
            **kwargs: Additional configuration options

        Returns:
            WorkflowBuilder: Hierarchical workflow ready for execution
        """
        hierarchical_workflow = SupervisorWorkerWorkflow(
            supervisor=supervisor,
            workers=workers,
            task=task,
            coordination_pattern=coordination_pattern,
            kaizen_instance=self.kaizen,
        )

        workflow = hierarchical_workflow.build()

        # Add SharedMemoryPoolNode for task tracking
        if (
            self.kaizen
            and hasattr(self.kaizen, "memory_enabled")
            and self.kaizen.memory_enabled
        ):
            memory_config = {
                "pool_name": f"hierarchical_memory_{self.pattern_id}",
                "max_entries": 200,
                "ttl_seconds": 7200,  # 2 hours TTL
                "coordination_context": {
                    "task": task,
                    "supervisor": (
                        supervisor.id
                        if hasattr(supervisor, "id")
                        else supervisor.agent_id
                    ),
                    "workers": [
                        worker.id if hasattr(worker, "id") else worker.agent_id
                        for worker in workers
                    ],
                },
            }
            workflow.add_node(
                "SharedMemoryPoolNode", "hierarchical_memory", memory_config
            )

        return workflow

    def extract_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured hierarchical coordination results."""
        # Create placeholder workflow for result extraction
        hierarchical_workflow = SupervisorWorkerWorkflow(
            supervisor=type(
                "MockAgent", (), {"id": "supervisor", "agent_id": "supervisor"}
            )(),
            workers=[],
            task="extracted_task",
            kaizen_instance=self.kaizen,
        )

        structured_results = hierarchical_workflow.extract_coordination_results(results)

        # Add pattern metadata
        structured_results.update(
            {
                "pattern_metadata": self.get_pattern_metadata(),
                "coordination_type": "hierarchical",
                "a2a_coordination": True,
            }
        )

        return structured_results


class TeamCoordinationPattern(CoordinationPattern):
    """Enhanced team coordination pattern with role-based collaboration."""

    def __init__(self, kaizen_instance: Optional[Any] = None):
        super().__init__("team", kaizen_instance)

    def create_workflow(
        self,
        team: AgentTeam,
        task: str,
        coordination_strategy: str = "collaborative",
        **kwargs,
    ) -> WorkflowBuilder:
        """
        Create team coordination workflow.

        Args:
            team: Agent team to coordinate
            task: Task to execute
            coordination_strategy: Coordination strategy
            **kwargs: Additional configuration options

        Returns:
            WorkflowBuilder: Team coordination workflow ready for execution
        """
        workflow = WorkflowBuilder()

        # Add A2A Coordinator for team management
        coordinator_config = {
            "coordination_strategy": coordination_strategy,
            "task": {
                "task_id": f"team_task_{int(time.time())}",
                "description": task,
                "type": "team_coordination",
                "priority": "medium",
                "required_skills": ["collaboration", "coordination"],
            },
            "team_config": {
                "name": team.name,
                "pattern": team.pattern,
                "coordination": team.coordination,
                "member_count": len(team.members),
            },
            "participants": [
                {
                    "agent_id": member.id if hasattr(member, "id") else member.agent_id,
                    "role": getattr(member, "role", "team_member"),
                    "authority_level": getattr(member, "authority_level", "member"),
                }
                for member in team.members
            ],
        }
        workflow.add_node("A2ACoordinatorNode", "team_coordinator", coordinator_config)

        # Add each team member as A2A agent node
        for i, member in enumerate(team.members):
            agent_config = {
                "model": member.config.get("model", "gpt-3.5-turbo"),
                "generation_config": member.config.get(
                    "generation_config",
                    {
                        "temperature": member.config.get("temperature", 0.7),
                        "max_tokens": member.config.get("max_tokens", 600),
                    },
                ),
                "role": getattr(member, "role", f"Team Member {i+1}"),
                "team_context": {
                    "team_name": team.name,
                    "task": task,
                    "coordination_strategy": coordination_strategy,
                    "authority_level": getattr(member, "authority_level", "member"),
                },
                "coordinator_id": "team_coordinator",
                "a2a_enabled": True,
                "system_prompt": (
                    f"You are {getattr(member, 'role', f'Team Member {i+1}')} on team '{team.name}'. "
                    f"Task: {task}. "
                    f"Coordination strategy: {coordination_strategy}. "
                    f"Work collaboratively with your team members to complete the task effectively."
                ),
            }

            agent_id = member.id if hasattr(member, "id") else member.agent_id
            workflow.add_node("A2AAgentNode", agent_id, agent_config)

        # Add SharedMemoryPoolNode for team state management
        if (
            self.kaizen
            and hasattr(self.kaizen, "memory_enabled")
            and self.kaizen.memory_enabled
        ):
            memory_config = {
                "pool_name": f"team_memory_{self.pattern_id}",
                "max_entries": 300,
                "ttl_seconds": 3600,  # 1 hour TTL
                "coordination_context": {
                    "team_name": team.name,
                    "task": task,
                    "members": [
                        member.id if hasattr(member, "id") else member.agent_id
                        for member in team.members
                    ],
                },
            }
            workflow.add_node("SharedMemoryPoolNode", "team_memory", memory_config)

        return workflow

    def extract_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured team coordination results."""
        team_results = {
            "coordination_type": "team",
            "coordinator_summary": results.get("team_coordinator", {}),
            "member_contributions": [],
            "team_performance": {},
        }

        # Extract individual member contributions
        for node_id, node_result in results.items():
            if node_id != "team_coordinator" and node_id != "team_memory":
                if node_result:
                    response_text = str(
                        node_result.get("response", node_result.get("content", ""))
                    )
                    team_results["member_contributions"].append(
                        {"agent": node_id, "contribution": response_text}
                    )

        # Add pattern metadata
        team_results.update(
            {"pattern_metadata": self.get_pattern_metadata(), "a2a_coordination": True}
        )

        return team_results


class CoordinationPatternRegistry:
    """Registry for managing coordination patterns."""

    def __init__(self, kaizen_instance: Optional[Any] = None):
        """
        Initialize pattern registry.

        Args:
            kaizen_instance: Reference to Kaizen framework instance
        """
        self.kaizen = kaizen_instance
        self._patterns: Dict[str, CoordinationPattern] = {}
        self._register_default_patterns()

    def _register_default_patterns(self):
        """Register default coordination patterns."""
        self._patterns["debate"] = DebateCoordinationPattern(self.kaizen)
        self._patterns["consensus"] = ConsensusCoordinationPattern(self.kaizen)
        self._patterns["hierarchical"] = HierarchicalCoordinationPattern(self.kaizen)
        self._patterns["team"] = TeamCoordinationPattern(self.kaizen)

    def register_pattern(self, name: str, pattern: CoordinationPattern):
        """
        Register a custom coordination pattern.

        Args:
            name: Pattern name
            pattern: Coordination pattern instance
        """
        self._patterns[name] = pattern
        logger.info(f"Registered coordination pattern: {name}")

    def get_pattern(self, name: str) -> Optional[CoordinationPattern]:
        """
        Get coordination pattern by name.

        Args:
            name: Pattern name

        Returns:
            CoordinationPattern instance or None if not found
        """
        return self._patterns.get(name)

    def list_patterns(self) -> List[str]:
        """
        List all registered pattern names.

        Returns:
            List of pattern names
        """
        return list(self._patterns.keys())

    def create_coordination_workflow(
        self, pattern_name: str, **kwargs
    ) -> Optional[WorkflowBuilder]:
        """
        Create coordination workflow using specified pattern.

        Args:
            pattern_name: Name of coordination pattern to use
            **kwargs: Pattern-specific arguments

        Returns:
            WorkflowBuilder or None if pattern not found
        """
        pattern = self.get_pattern(pattern_name)
        if pattern:
            return pattern.create_workflow(**kwargs)
        return None

    def extract_coordination_results(
        self, pattern_name: str, results: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Extract structured results using specified pattern.

        Args:
            pattern_name: Name of coordination pattern used
            results: Raw workflow execution results

        Returns:
            Structured results or None if pattern not found
        """
        pattern = self.get_pattern(pattern_name)
        if pattern:
            return pattern.extract_results(results)
        return None


# Global pattern registry instance
_global_registry: Optional[CoordinationPatternRegistry] = None


def get_global_pattern_registry(
    kaizen_instance: Optional[Any] = None,
) -> CoordinationPatternRegistry:
    """
    Get global coordination pattern registry.

    Args:
        kaizen_instance: Kaizen framework instance

    Returns:
        CoordinationPatternRegistry: Global registry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = CoordinationPatternRegistry(kaizen_instance)
    return _global_registry

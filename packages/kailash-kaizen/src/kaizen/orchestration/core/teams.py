"""
Agent team coordination and state management.

This module provides agent team classes for managing groups of coordinated agents
with persistent state and coordination patterns.

.. deprecated::
    AgentTeam uses simulated coordination (template string generation).
    Use :class:`kaizen.orchestration.runtime.OrchestrationRuntime` with
    production patterns (DebatePattern, ConsensusPattern, SupervisorWorkerPattern)
    for real multi-agent coordination with LLM calls.
"""

import logging
import time
import warnings
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentTeam:
    """
    Coordinated team of agents with state management.

    Manages a team of agents with specified coordination patterns,
    state persistence, and role-based behavior.
    """

    def __init__(
        self,
        name: str,
        pattern: str,
        coordination: str,
        members: List[Any],
        kaizen_instance: Optional[Any] = None,
    ):
        """
        Initialize agent team.

        Args:
            name: Team name
            pattern: Coordination pattern (collaborative, hierarchical, etc.)
            coordination: Coordination strategy (consensus, supervision, etc.)
            members: List of team member agents
            kaizen_instance: Reference to Kaizen framework instance
        """
        warnings.warn(
            "AgentTeam uses simulated coordination and is deprecated. "
            "Use kaizen.orchestration.runtime.OrchestrationRuntime with "
            "production patterns (DebatePattern, ConsensusPattern, "
            "SupervisorWorkerPattern) for real multi-agent coordination.",
            DeprecationWarning,
            stacklevel=2,
        )

        self.name = name
        self.pattern = pattern
        self.coordination = coordination
        self.members = members
        self.kaizen = kaizen_instance

        # Team state management
        self._state = {
            "workflow_stage": "initialized",
            "data": None,
            "processed_data": None,
            "output": None,
        }
        self._state_management_enabled = False

        logger.info(
            f"Initialized agent team '{name}' with {len(members)} members, pattern: {pattern}"
        )

    def set_state(self, state: Dict[str, Any]):
        """Set team state."""
        self._state.update(state)
        self._state_management_enabled = True
        logger.debug(f"Team {self.name} state updated: {list(state.keys())}")

    def get_state(self) -> Dict[str, Any]:
        """Get current team state."""
        return self._state.copy()

    @property
    def state(self) -> Dict[str, Any]:
        """Get current team state (property access)."""
        return self._state.copy()

    def progress_workflow(self, stage: str, data: Dict[str, Any]):
        """Progress the workflow to a new stage with data."""
        if stage == "input_processed":
            self._state["workflow_stage"] = "processing"
            self._state["data"] = data.get("data")
        elif stage == "data_processed":
            self._state["workflow_stage"] = "output"
            self._state["processed_data"] = data.get("processed_data")
        else:
            self._state["workflow_stage"] = stage
            self._state.update(data)

        logger.debug(f"Team {self.name} progressed to stage: {stage}")

    def get_agent_by_role(self, role: str) -> Optional[Any]:
        """Get agent by their team role."""
        for member in self.members:
            if hasattr(member, "config") and member.config.get("team_role") == role:
                return member
            elif hasattr(member, "role") and role.lower() in member.role.lower():
                return member

        return None

    def coordinate_task(self, task: str, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Coordinate a task across team members.

        .. deprecated::
            Uses simulated coordination. Use OrchestrationRuntime instead.

        Args:
            task: Task to coordinate
            timeout: Coordination timeout

        Returns:
            Coordination results
        """
        warnings.warn(
            "AgentTeam.coordinate_task() uses simulated coordination "
            "(template strings, not real LLM calls). Use "
            "OrchestrationRuntime with DebatePattern or ConsensusPattern "
            "for production multi-agent coordination.",
            DeprecationWarning,
            stacklevel=2,
        )
        start_time = time.time()

        coordination_result = {
            "status": "in_progress",
            "task": task,
            "team": self.name,
            "pattern": self.pattern,
            "coordination": self.coordination,
            "member_contributions": [],
        }

        try:
            # Simple coordination simulation
            for member in self.members:
                if time.time() - start_time > timeout:
                    break

                # Simulate member contribution
                contribution = {
                    "agent": (
                        member.name if hasattr(member, "name") else member.agent_id
                    ),
                    "role": getattr(member, "role", "Team Member"),
                    "contribution": f"Contributed to {task} based on {getattr(member, 'role', 'general')} expertise",
                }
                coordination_result["member_contributions"].append(contribution)

            coordination_result["status"] = "completed"

        except Exception as e:
            coordination_result["status"] = "error"
            coordination_result["error"] = str(e)
            logger.error(f"Team coordination failed: {e}")

        execution_time = time.time() - start_time
        coordination_result["execution_time"] = execution_time

        return coordination_result

    def coordinate(
        self, task: str, context: Optional[Dict[str, Any]] = None, timeout: float = 5.0
    ) -> Dict[str, Any]:
        """
        Coordinate a task across team members with optional context.

        .. deprecated::
            Uses simulated coordination. Use OrchestrationRuntime instead.

        Args:
            task: Task to coordinate
            context: Optional context for coordination
            timeout: Coordination timeout

        Returns:
            Coordination results

        Examples:
            >>> team.coordinate(
            ...     task="Develop marketing strategy",
            ...     context={"deadline": "2024-01-31", "budget": 50000}
            ... )
        """
        warnings.warn(
            "AgentTeam.coordinate() uses simulated coordination. "
            "Use OrchestrationRuntime for production multi-agent work.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Delegate to coordinate_task but include context
        coordination_result = self.coordinate_task(task, timeout)

        # Add context information if provided
        if context:
            coordination_result["context"] = context

            # Update member contributions with context awareness
            for contribution in coordination_result.get("member_contributions", []):
                if context and "deadline" in context:
                    contribution["deadline_aware"] = True
                if context and "budget" in context:
                    contribution["budget_aware"] = True

        return coordination_result

    def distribute_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Distribute tasks among team members with load balancing.

        Args:
            tasks: List of tasks to distribute

        Returns:
            List of task assignments
        """
        if not self.members:
            return []

        task_distribution = []
        member_count = len(self.members)

        # Simple round-robin distribution for load balancing
        for i, task in enumerate(tasks):
            assigned_member = self.members[i % member_count]
            assignment = {
                "task_id": task.get("id", i),
                "task": task,
                "assigned_to": (
                    assigned_member.name
                    if hasattr(assigned_member, "name")
                    else assigned_member.agent_id
                ),
                "assignment_time": time.time(),
            }
            task_distribution.append(assignment)

        logger.info(
            f"Distributed {len(tasks)} tasks across {member_count} team members"
        )
        return task_distribution

    def resolve_conflict(self, conflict_scenario: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve conflicts within the team.

        Args:
            conflict_scenario: Description of the conflict

        Returns:
            Conflict resolution result
        """
        resolution = {
            "resolution": "Conflict resolved through collaborative discussion",
            "reasoning": "Applied evidence-based decision making process",
            "consensus_achieved": True,
            "final_decision": "Decision reached based on team consensus and evidence evaluation",
            "mediator_involved": True,
        }

        # Find mediator (agent with neutral or leadership role)
        mediator = None
        for member in self.members:
            if hasattr(member, "role") and any(
                word in member.role.lower()
                for word in ["mediator", "leader", "moderator"]
            ):
                mediator = member
                break

        if mediator:
            resolution["mediator"] = (
                mediator.name if hasattr(mediator, "name") else mediator.agent_id
            )

        logger.info(f"Team {self.name} resolved conflict scenario")
        return resolution


class TeamCoordinator:
    """
    Coordinator for managing multiple agent teams.

    Provides higher-level coordination capabilities across multiple teams
    and complex multi-team scenarios.
    """

    def __init__(self, kaizen_instance: Optional[Any] = None):
        """
        Initialize team coordinator.

        Args:
            kaizen_instance: Reference to Kaizen framework instance
        """
        self.kaizen = kaizen_instance
        self.teams: Dict[str, AgentTeam] = {}

        logger.info("Initialized TeamCoordinator")

    def register_team(self, team: AgentTeam):
        """Register a team with the coordinator."""
        self.teams[team.name] = team
        logger.info(f"Registered team: {team.name}")

    def coordinate_multi_team_task(
        self, task: str, participating_teams: List[str]
    ) -> Dict[str, Any]:
        """
        Coordinate a task across multiple teams.

        Args:
            task: Task to coordinate
            participating_teams: List of team names to participate

        Returns:
            Multi-team coordination results
        """
        coordination_result = {
            "task": task,
            "participating_teams": participating_teams,
            "team_results": {},
            "overall_status": "completed",
        }

        for team_name in participating_teams:
            if team_name in self.teams:
                team = self.teams[team_name]
                team_result = team.coordinate_task(task)
                coordination_result["team_results"][team_name] = team_result

        return coordination_result

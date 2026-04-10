"""
Base Multi-Agent Pattern

Abstract base class for all multi-agent coordination patterns.
Provides common infrastructure for pattern creation, shared memory management,
and agent coordination.

All patterns accept plain BaseAgent instances -- role and behaviour come from
the agent's config/system_prompt, not from specialised subclasses.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from kaizen.memory.shared_memory import SharedMemoryPool


@dataclass
class BaseMultiAgentPattern(ABC):
    """
    Abstract base class for multi-agent coordination patterns.

    All multi-agent patterns extend this base class and provide:
    - Shared memory pool for agent coordination (auto-created if not provided)
    - Agent initialization and management
    - Pattern-specific coordination logic
    - Convenience methods for common operations

    Agents are plain ``BaseAgent`` instances -- role comes from
    ``config.system_prompt``, not from specialised subclasses.

    Attributes:
        shared_memory: SharedMemoryPool instance for agent coordination.

    Example:
        >>> class MyPattern(BaseMultiAgentPattern):
        ...     agent1: MyAgent1
        ...     agent2: MyAgent2
        ...
        ...     def coordinate(self) -> Dict[str, Any]:
        ...         # Pattern-specific coordination logic
        ...         pass
    """

    shared_memory: SharedMemoryPool

    @abstractmethod
    def get_agents(self) -> list[Any]:
        """
        Get all agents in this pattern.

        Returns:
            List of agent instances

        Example:
            >>> pattern = SupervisorWorkerPattern(...)
            >>> agents = pattern.get_agents()
            >>> print(f"Pattern has {len(agents)} agents")
        """
        pass

    @abstractmethod
    def get_agent_ids(self) -> list[str]:
        """
        Get all agent IDs in this pattern.

        Returns:
            List of agent ID strings

        Example:
            >>> pattern = SupervisorWorkerPattern(...)
            >>> agent_ids = pattern.get_agent_ids()
            >>> print(f"Agent IDs: {agent_ids}")
        """
        pass

    def get_agent_names(self) -> list[str]:
        """
        Get human-readable names of all agents in this pattern.

        Falls back to agent_id when no ``name`` attribute is present.

        Returns:
            List of agent name strings
        """
        names: list[str] = []
        for agent in self.get_agents():
            name = getattr(agent, "name", None) or getattr(
                agent, "agent_id", str(agent)
            )
            names.append(str(name))
        return names

    def clear_shared_memory(self):
        """
        Clear all insights from shared memory.

        Useful for resetting pattern state between requests.

        Example:
            >>> pattern = SupervisorWorkerPattern(...)
            >>> pattern.delegate("task 1")
            >>> pattern.clear_shared_memory()  # Reset for next request
            >>> pattern.delegate("task 2")
        """
        if self.shared_memory:
            # Clear all insights (use private attribute _insights)
            self.shared_memory._insights.clear()

    def get_shared_insights(
        self,
        tags: list[str] | None = None,
        agent_id: str | None = None,
        segment: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve insights from shared memory with optional filtering.

        Args:
            tags: Filter by tags (returns insights matching ANY tag)
            agent_id: Filter by agent ID
            segment: Filter by memory segment

        Returns:
            List of matching insights

        Example:
            >>> pattern = SupervisorWorkerPattern(...)
            >>> # Get all pending tasks
            >>> tasks = pattern.get_shared_insights(tags=["task", "pending"])
            >>> # Get all insights from supervisor
            >>> supervisor_insights = pattern.get_shared_insights(agent_id="supervisor_1")
        """
        if not self.shared_memory:
            return []

        # Use read_relevant with appropriate filters
        # If no agent_id specified, use a dummy one and exclude_own=False to get all
        return self.shared_memory.read_relevant(
            agent_id=agent_id or "_pattern_",
            tags=tags,
            exclude_own=False,  # Get all insights
            segments=[segment] if segment else None,
            limit=1000,  # Large number to get all insights
        )

    def count_insights_by_tags(self, tags: list[str]) -> int:
        """
        Count insights matching given tags.

        Args:
            tags: Tags to match (ANY match)

        Returns:
            Count of matching insights

        Example:
            >>> pattern = SupervisorWorkerPattern(...)
            >>> pattern.delegate("Process documents", num_tasks=5)
            >>> pending_count = pattern.count_insights_by_tags(["task", "pending"])
            >>> print(f"Pending tasks: {pending_count}")  # 5
        """
        insights = self.get_shared_insights(tags=tags)
        return len(insights)

    def validate_pattern(self) -> bool:
        """
        Validate that pattern is properly initialized.

        Checks:
        - Shared memory exists
        - All agents are initialized
        - Agent IDs are unique

        Returns:
            True if pattern is valid, False otherwise

        Example:
            >>> pattern = create_supervisor_worker_pattern()
            >>> if pattern.validate_pattern():
            ...     print("Pattern ready to use")
            ... else:
            ...     print("Pattern initialization failed")
        """
        # Check shared memory
        if not self.shared_memory:
            return False

        # Check agents exist
        agents = self.get_agents()
        if not agents or len(agents) == 0:
            return False

        # Check agent IDs are unique
        agent_ids = self.get_agent_ids()
        if len(agent_ids) != len(set(agent_ids)):
            # Duplicate agent IDs found
            return False

        # Check all agents have the same shared memory instance
        for agent in agents:
            if (
                hasattr(agent, "shared_memory")
                and agent.shared_memory is not self.shared_memory
            ):
                return False

        return True

    def __str__(self) -> str:
        """String representation of pattern."""
        agents = self.get_agents()
        agent_ids = self.get_agent_ids()
        return f"{self.__class__.__name__}(agents={len(agents)}, agent_ids={agent_ids})"

    def __repr__(self) -> str:
        """Detailed representation of pattern."""
        return self.__str__()

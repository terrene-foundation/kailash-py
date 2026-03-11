# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Registry-Aware Orchestration Runtime.

This module integrates AgentRegistry with TrustAwareOrchestrationRuntime
for capability-based and health-aware agent selection.

Key Features:
- Capability-based agent discovery for task assignment
- Health-aware selection (skip unhealthy agents)
- Automatic agent discovery from registry
- Load balancing across available agents

Example:
    runtime = RegistryAwareRuntime(
        trust_operations=trust_ops,
        agent_registry=registry,
        health_monitor=health_monitor,
    )

    status = await runtime.execute_workflow_with_discovery(
        tasks=tasks,
        context=context,
        required_capabilities=["analyze", "report"],
    )
"""

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from eatp.operations import TrustOperations
from eatp.orchestration.exceptions import OrchestrationTrustError
from eatp.orchestration.execution_context import TrustExecutionContext
from eatp.orchestration.runtime import (
    TrustAwareOrchestrationRuntime,
    TrustAwareRuntimeConfig,
    TrustedTaskResult,
    TrustedWorkflowStatus,
)
from eatp.registry.agent_registry import AgentRegistry, DiscoveryQuery
from eatp.registry.health import AgentHealthMonitor, HealthStatus
from eatp.registry.models import AgentMetadata, AgentStatus

logger = logging.getLogger(__name__)


class AgentSelector(ABC):
    """
    Abstract base class for agent selection strategies.

    Implement this to create custom agent selection logic for
    workflow task assignment.
    """

    @abstractmethod
    async def select_agent(
        self,
        task: Any,
        context: TrustExecutionContext,
        available_agents: List[AgentMetadata],
    ) -> Optional[str]:
        """
        Select an agent for a task.

        Args:
            task: Task to assign.
            context: Current execution context.
            available_agents: Agents available for selection.

        Returns:
            Selected agent ID or None if no suitable agent.
        """
        pass


class CapabilityBasedSelector(AgentSelector):
    """
    Select agents based on required capabilities.

    Matches task requirements to agent capabilities, selecting
    agents that have all required capabilities.
    """

    def __init__(
        self,
        required_capabilities: Optional[List[str]] = None,
        prefer_specialized: bool = True,
    ):
        """
        Initialize capability-based selector.

        Args:
            required_capabilities: Capabilities required for tasks.
            prefer_specialized: If True, prefer agents with fewer
                extra capabilities (more specialized).
        """
        self._required_capabilities = set(required_capabilities or [])
        self._prefer_specialized = prefer_specialized

    async def select_agent(
        self,
        task: Any,
        context: TrustExecutionContext,
        available_agents: List[AgentMetadata],
    ) -> Optional[str]:
        """Select agent with required capabilities."""
        # Get task-specific capabilities if available
        task_caps = self._required_capabilities.copy()
        if isinstance(task, dict) and "required_capabilities" in task:
            task_caps.update(task["required_capabilities"])

        # Filter agents with required capabilities
        capable_agents = []
        for agent in available_agents:
            agent_caps = set(agent.capabilities)
            if task_caps.issubset(agent_caps):
                capable_agents.append(agent)

        if not capable_agents:
            logger.warning(f"No agents found with capabilities {task_caps}")
            return None

        # Select based on specialization preference
        if self._prefer_specialized:
            # Sort by number of capabilities (fewer = more specialized)
            capable_agents.sort(key=lambda a: len(a.capabilities))

        # Return first suitable agent
        return capable_agents[0].agent_id


class HealthAwareSelector(AgentSelector):
    """
    Select agents based on health status.

    Wraps another selector to filter out unhealthy agents
    before selection.
    """

    def __init__(
        self,
        inner_selector: AgentSelector,
        health_monitor: AgentHealthMonitor,
        min_health_status: HealthStatus = HealthStatus.HEALTHY,
    ):
        """
        Initialize health-aware selector.

        Args:
            inner_selector: Selector to use after health filtering.
            health_monitor: Health monitor for status checks.
            min_health_status: Minimum acceptable health status.
        """
        self._inner_selector = inner_selector
        self._health_monitor = health_monitor
        self._min_health = min_health_status

    async def select_agent(
        self,
        task: Any,
        context: TrustExecutionContext,
        available_agents: List[AgentMetadata],
    ) -> Optional[str]:
        """Select agent with acceptable health status."""
        # Filter by health
        healthy_agents = []
        for agent in available_agents:
            # Use check_agent() which returns HealthStatus directly
            status = await self._health_monitor.check_agent(agent.agent_id)
            if self._is_acceptable_health(status):
                healthy_agents.append(agent)

        if not healthy_agents:
            logger.warning(
                f"No healthy agents available "
                f"(min status: {self._min_health.value})"
            )
            return None

        # Delegate to inner selector
        return await self._inner_selector.select_agent(task, context, healthy_agents)

    def _is_acceptable_health(self, status: HealthStatus) -> bool:
        """Check if health status is acceptable."""
        # The actual health statuses are: HEALTHY, STALE, SUSPENDED, UNKNOWN
        # We consider HEALTHY as the best, then STALE (degraded), then SUSPENDED/UNKNOWN
        health_order = [
            HealthStatus.HEALTHY,
            HealthStatus.STALE,  # Stale = degraded (still responding but not recent)
            HealthStatus.SUSPENDED,
            HealthStatus.UNKNOWN,
        ]
        try:
            current_idx = health_order.index(status)
            min_idx = health_order.index(self._min_health)
            return current_idx <= min_idx
        except ValueError:
            return False


class RoundRobinSelector(AgentSelector):
    """
    Select agents in round-robin fashion.

    Distributes tasks evenly across available agents.
    """

    def __init__(self):
        self._last_index = -1
        self._lock = asyncio.Lock()

    async def select_agent(
        self,
        task: Any,
        context: TrustExecutionContext,
        available_agents: List[AgentMetadata],
    ) -> Optional[str]:
        """Select next agent in round-robin order."""
        if not available_agents:
            return None

        async with self._lock:
            self._last_index = (self._last_index + 1) % len(available_agents)
            return available_agents[self._last_index].agent_id


class RandomSelector(AgentSelector):
    """Select agents randomly."""

    async def select_agent(
        self,
        task: Any,
        context: TrustExecutionContext,
        available_agents: List[AgentMetadata],
    ) -> Optional[str]:
        """Select random agent."""
        if not available_agents:
            return None
        return random.choice(available_agents).agent_id


@dataclass
class RegistryAwareRuntimeConfig(TrustAwareRuntimeConfig):
    """Configuration for RegistryAwareRuntime."""

    # Registry integration
    auto_discover_agents: bool = True
    refresh_agents_interval_seconds: float = 60.0
    exclude_suspended_agents: bool = True

    # Selection
    default_selector: str = "capability"  # "capability", "round_robin", "random"
    prefer_specialized_agents: bool = True

    # Health integration
    health_aware_selection: bool = True
    min_health_status: HealthStatus = HealthStatus.HEALTHY


class RegistryAwareRuntime(TrustAwareOrchestrationRuntime):
    """
    Orchestration runtime with agent registry integration.

    Extends TrustAwareOrchestrationRuntime with:
    - Automatic agent discovery from registry
    - Capability-based agent selection
    - Health-aware task assignment
    - Load balancing across agents

    Example:
        >>> runtime = RegistryAwareRuntime(
        ...     trust_operations=trust_ops,
        ...     agent_registry=registry,
        ...     health_monitor=health_monitor,
        ...     config=RegistryAwareRuntimeConfig(
        ...         health_aware_selection=True,
        ...     )
        ... )
        >>>
        >>> status = await runtime.execute_workflow_with_discovery(
        ...     tasks=["task1", "task2", "task3"],
        ...     context=context,
        ...     required_capabilities=["analyze"],
        ... )
    """

    def __init__(
        self,
        trust_operations: TrustOperations,
        agent_registry: AgentRegistry,
        health_monitor: Optional[AgentHealthMonitor] = None,
        config: Optional[RegistryAwareRuntimeConfig] = None,
    ):
        """
        Initialize registry-aware runtime.

        Args:
            trust_operations: TrustOperations for verification.
            agent_registry: AgentRegistry for agent discovery.
            health_monitor: Optional health monitor for health-aware selection.
            config: Runtime configuration.
        """
        self._config = config or RegistryAwareRuntimeConfig()
        super().__init__(
            trust_operations=trust_operations,
            agent_registry=agent_registry,
            config=self._config,
        )

        self._registry = agent_registry
        self._health_monitor = health_monitor

        # Agent cache
        self._agent_cache: List[AgentMetadata] = []
        self._last_refresh: Optional[datetime] = None
        self._cache_lock = asyncio.Lock()

        # Create default selector
        self._default_selector = self._create_default_selector()

        logger.info("RegistryAwareRuntime initialized")

    def _create_default_selector(self) -> AgentSelector:
        """Create the default agent selector based on config."""
        # Base selector
        if self._config.default_selector == "round_robin":
            base_selector = RoundRobinSelector()
        elif self._config.default_selector == "random":
            base_selector = RandomSelector()
        else:
            base_selector = CapabilityBasedSelector(
                prefer_specialized=self._config.prefer_specialized_agents
            )

        # Wrap with health-aware if configured
        if self._config.health_aware_selection and self._health_monitor:
            return HealthAwareSelector(
                inner_selector=base_selector,
                health_monitor=self._health_monitor,
                min_health_status=self._config.min_health_status,
            )

        return base_selector

    async def discover_agents(
        self,
        capabilities: Optional[List[str]] = None,
        status: Optional[AgentStatus] = None,
        agent_type: Optional[str] = None,
    ) -> List[AgentMetadata]:
        """
        Discover agents from registry.

        Args:
            capabilities: Required capabilities to filter by.
            status: Required status to filter by.
            agent_type: Optional agent type to filter by.

        Returns:
            List of matching agents.
        """
        query = DiscoveryQuery(
            capabilities=capabilities or [],
            status=status or AgentStatus.ACTIVE,
            agent_type=agent_type,
        )

        agents = await self._registry.discover(query)

        # Filter suspended agents if configured
        if self._config.exclude_suspended_agents:
            agents = [a for a in agents if a.status != AgentStatus.SUSPENDED]

        return agents

    async def refresh_agent_cache(self) -> None:
        """Refresh the agent cache from registry."""
        async with self._cache_lock:
            self._agent_cache = await self.discover_agents()
            self._last_refresh = datetime.now(timezone.utc)
            logger.debug(f"Refreshed agent cache: {len(self._agent_cache)} agents")

    async def _get_available_agents(
        self,
        required_capabilities: Optional[List[str]] = None,
    ) -> List[AgentMetadata]:
        """Get available agents, refreshing cache if needed."""
        # Check if cache needs refresh
        should_refresh = False
        if self._last_refresh is None:
            should_refresh = True
        else:
            age = (datetime.now(timezone.utc) - self._last_refresh).total_seconds()
            if age > self._config.refresh_agents_interval_seconds:
                should_refresh = True

        if should_refresh:
            await self.refresh_agent_cache()

        # Filter by capabilities if specified
        agents = self._agent_cache
        if required_capabilities:
            required_set = set(required_capabilities)
            agents = [a for a in agents if required_set.issubset(set(a.capabilities))]

        return agents

    async def select_agent_for_task(
        self,
        task: Any,
        context: TrustExecutionContext,
        required_capabilities: Optional[List[str]] = None,
        selector: Optional[AgentSelector] = None,
    ) -> Optional[str]:
        """
        Select an agent for a task.

        Args:
            task: Task to assign.
            context: Current execution context.
            required_capabilities: Capabilities required for task.
            selector: Custom selector (uses default if None).

        Returns:
            Selected agent ID or None.
        """
        # Get available agents
        agents = await self._get_available_agents(required_capabilities)

        if not agents:
            logger.warning("No available agents for task selection")
            return None

        # Use provided selector or default
        agent_selector = selector or self._default_selector

        return await agent_selector.select_agent(task, context, agents)

    async def execute_workflow_with_discovery(
        self,
        tasks: List[Any],
        context: TrustExecutionContext,
        required_capabilities: Optional[List[str]] = None,
        task_executor: Optional[Callable[[str, Any], Any]] = None,
        selector: Optional[AgentSelector] = None,
    ) -> TrustedWorkflowStatus:
        """
        Execute workflow with automatic agent discovery.

        Discovers suitable agents from registry and assigns tasks
        based on capabilities and health.

        Args:
            tasks: List of tasks to execute.
            context: Execution context.
            required_capabilities: Capabilities required for tasks.
            task_executor: Function to execute tasks.
            selector: Custom agent selector.

        Returns:
            TrustedWorkflowStatus with execution results.
        """

        # Create agent selector function for parent
        async def agent_selector_fn(task: Any) -> str:
            agent_id = await self.select_agent_for_task(
                task=task,
                context=context,
                required_capabilities=required_capabilities,
                selector=selector,
            )
            if not agent_id:
                raise OrchestrationTrustError(
                    f"No suitable agent found for task: {task}"
                )
            return agent_id

        # Execute using parent's workflow execution
        return await self.execute_trusted_workflow(
            tasks=tasks,
            context=context,
            agent_selector=agent_selector_fn,
            task_executor=task_executor,
        )

    async def execute_parallel_with_discovery(
        self,
        tasks: List[Any],
        context: TrustExecutionContext,
        required_capabilities: Optional[List[str]] = None,
        max_agents: Optional[int] = None,
        task_executor: Optional[Callable[[str, Any], Any]] = None,
    ) -> TrustedWorkflowStatus:
        """
        Execute tasks in parallel across discovered agents.

        Distributes tasks across multiple agents for parallel execution.

        Args:
            tasks: List of tasks to execute.
            context: Execution context.
            required_capabilities: Capabilities required for tasks.
            max_agents: Maximum number of agents to use.
            task_executor: Function to execute tasks.

        Returns:
            TrustedWorkflowStatus with execution results.
        """
        # Discover available agents
        agents = await self._get_available_agents(required_capabilities)

        if not agents:
            raise OrchestrationTrustError(
                "No suitable agents available for parallel execution"
            )

        # Limit agents if specified
        if max_agents and len(agents) > max_agents:
            agents = agents[:max_agents]

        # Distribute tasks across agents
        task_groups: Dict[str, List[Any]] = {agent.agent_id: [] for agent in agents}

        for i, task in enumerate(tasks):
            agent_id = agents[i % len(agents)].agent_id
            task_groups[agent_id].append(task)

        # Execute in parallel
        return await self.execute_parallel_trusted_workflow(
            task_groups=task_groups,
            context=context,
            task_executor=task_executor,
        )

    def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry integration statistics."""
        return {
            "cached_agents": len(self._agent_cache),
            "last_refresh": (
                self._last_refresh.isoformat() if self._last_refresh else None
            ),
            "health_aware_selection": self._config.health_aware_selection,
            "default_selector": self._config.default_selector,
        }

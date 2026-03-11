"""
Agent Registry - Centralized Agent Lifecycle Management

Production-ready registry for managing agents across multiple OrchestrationRuntime
instances. Supports distributed agent discovery, capability-based search, and
cross-runtime coordination for scaling beyond 100 agents.

Architecture:
    AgentRegistry
    ├── In-memory registry (fast lookup)
    ├── Capability indexing (semantic search)
    ├── Runtime tracking (multi-runtime coordination)
    ├── Health monitoring (distributed health checks)
    └── Event broadcasting (cross-runtime updates)

Usage:
    from kaizen.orchestration.registry import AgentRegistry

    # Create centralized registry
    registry = AgentRegistry()

    # Register agent from runtime 1
    agent_id = await registry.register_agent(
        agent=my_agent,
        runtime_id="runtime_1",
        metadata={"capability": "code_generation"}
    )

    # Discover agents from runtime 2
    agents = await registry.find_agents_by_capability("code_generation")

    # Deregister agent
    await registry.deregister_agent(agent_id, runtime_id="runtime_1")

Performance Targets:
- Lookup: < 1ms for ID-based lookups
- Search: < 50ms for capability-based searches
- Registration: < 10ms for agent registration
- Scalability: Support 1000+ agents across 10+ runtimes
- Availability: 99.9% uptime with distributed deployment

Author: Kaizen Framework Team
Created: 2025-11-06 (TODO-179: Agent Registry)
Reference: Based on OrchestrationRuntime and AgentPoolManagerNode patterns
"""

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from kaizen.core.base_agent import BaseAgent
from kaizen.orchestration.runtime import AgentMetadata, AgentStatus

# Try to import A2A for capability-based routing
try:
    from kaizen.nodes.ai.a2a import A2AAgentCard

    A2A_AVAILABLE = True
except ImportError:
    A2AAgentCard = None
    A2A_AVAILABLE = False


# ============================================================================
# Configuration and Enums
# ============================================================================


class RegistryEventType(str, Enum):
    """Registry event types for cross-runtime coordination."""

    AGENT_REGISTERED = "agent_registered"
    AGENT_DEREGISTERED = "agent_deregistered"
    AGENT_STATUS_CHANGED = "agent_status_changed"
    AGENT_HEARTBEAT = "agent_heartbeat"
    RUNTIME_JOINED = "runtime_joined"
    RUNTIME_LEFT = "runtime_left"


@dataclass
class RegistryEvent:
    """Event for cross-runtime coordination."""

    event_type: RegistryEventType
    agent_id: Optional[str] = None
    runtime_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRegistryConfig:
    """Configuration for AgentRegistry."""

    # Agent management
    enable_heartbeat_monitoring: bool = True  # Monitor agent heartbeats
    heartbeat_timeout: float = 60.0  # Heartbeat timeout in seconds
    auto_deregister_timeout: float = 300.0  # Auto-deregister timeout (5 minutes)

    # Search and indexing
    enable_capability_indexing: bool = True  # Index agents by capability
    rebuild_index_interval: float = 300.0  # Rebuild index interval (5 minutes)

    # Event broadcasting
    enable_event_broadcasting: bool = True  # Broadcast events to listeners
    event_queue_size: int = 1000  # Max event queue size

    # Performance tuning
    max_concurrent_queries: int = 100  # Max concurrent queries
    query_timeout: float = 5.0  # Query timeout in seconds


# ============================================================================
# Agent Registry Implementation
# ============================================================================


class AgentRegistry:
    """
    Centralized registry for managing agents across multiple OrchestrationRuntime instances.

    Provides agent discovery, capability-based search, and cross-runtime coordination
    for scaling beyond 100 agents. Supports distributed deployment with event broadcasting.

    Example:
        registry = AgentRegistry()
        agent_id = await registry.register_agent(agent, runtime_id="runtime_1")
        agents = await registry.find_agents_by_capability("code_generation")
    """

    def __init__(self, config: Optional[AgentRegistryConfig] = None):
        """
        Initialize AgentRegistry.

        Args:
            config: Optional configuration (uses defaults if not provided)
        """
        self.config = config or AgentRegistryConfig()

        # Agent registry: {agent_id: AgentMetadata}
        self.agents: Dict[str, AgentMetadata] = {}

        # Runtime tracking: {runtime_id: Set[agent_id]}
        self.runtime_agents: Dict[str, Set[str]] = defaultdict(set)

        # Capability index: {capability: Set[agent_id]}
        self.capability_index: Dict[str, Set[str]] = defaultdict(set)

        # Status index: {status: Set[agent_id]}
        self.status_index: Dict[AgentStatus, Set[str]] = defaultdict(set)

        # Event listeners: {event_type: List[callback]}
        self.event_listeners: Dict[RegistryEventType, List[Callable]] = defaultdict(
            list
        )

        # Event queue for broadcasting
        self.event_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.config.event_queue_size
        )

        # Background tasks
        self._running = False
        self._heartbeat_monitor_task: Optional[asyncio.Task] = None
        self._event_broadcaster_task: Optional[asyncio.Task] = None
        self._index_rebuilder_task: Optional[asyncio.Task] = None

        # Performance metrics
        self._total_queries = 0
        self._total_registrations = 0
        self._total_deregistrations = 0

        # Concurrency control
        self._query_semaphore = asyncio.Semaphore(self.config.max_concurrent_queries)
        self._registry_lock = asyncio.Lock()

    # ========================================================================
    # Lifecycle Management
    # ========================================================================

    async def start(self):
        """Start registry background tasks."""
        self._running = True

        # Start heartbeat monitoring
        if self.config.enable_heartbeat_monitoring:
            self._heartbeat_monitor_task = asyncio.create_task(
                self._monitor_heartbeats()
            )

        # Start event broadcaster
        if self.config.enable_event_broadcasting:
            self._event_broadcaster_task = asyncio.create_task(self._broadcast_events())

        # Start index rebuilder
        if self.config.enable_capability_indexing:
            self._index_rebuilder_task = asyncio.create_task(self._rebuild_indexes())

    async def shutdown(self):
        """Shutdown registry and cleanup."""
        self._running = False

        # Cancel background tasks
        tasks = [
            self._heartbeat_monitor_task,
            self._event_broadcaster_task,
            self._index_rebuilder_task,
        ]

        for task in tasks:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Clear all data
        self.agents.clear()
        self.runtime_agents.clear()
        self.capability_index.clear()
        self.status_index.clear()

    # ========================================================================
    # Agent Registration and Deregistration
    # ========================================================================

    async def register_agent(
        self,
        agent: BaseAgent,
        runtime_id: str,
        agent_id: Optional[str] = None,
        max_concurrency: int = 10,
        memory_limit_mb: int = 512,
        budget_limit_usd: float = 1.0,
    ) -> str:
        """
        Register agent with runtime association.

        Args:
            agent: BaseAgent instance to register
            runtime_id: ID of runtime registering the agent
            agent_id: Optional custom agent ID (auto-generated if not provided)
            max_concurrency: Max concurrent tasks for this agent
            memory_limit_mb: Memory limit in MB
            budget_limit_usd: Budget limit in USD

        Returns:
            agent_id: Unique agent identifier

        Raises:
            ValueError: If agent_id already exists
        """
        async with self._registry_lock:
            # Generate agent ID if not provided
            if agent_id is None:
                agent_id = agent.agent_id or f"agent_{uuid.uuid4().hex[:8]}"

            # Guard clause: Prevent duplicate agent registration
            if agent_id in self.agents:
                raise ValueError(f"Agent with ID '{agent_id}' is already registered")

            # Get A2A capability card if available
            a2a_card = None
            if A2A_AVAILABLE and hasattr(agent, "_a2a_card"):
                a2a_card = agent._a2a_card

            # Create agent metadata
            metadata = AgentMetadata(
                agent_id=agent_id,
                agent=agent,
                a2a_card=a2a_card,
                max_concurrency=max_concurrency,
                memory_limit_mb=memory_limit_mb,
                budget_limit_usd=budget_limit_usd,
                status=AgentStatus.ACTIVE,
                last_heartbeat=datetime.now(),
            )

            # Store in registry
            self.agents[agent_id] = metadata

            # Track runtime association
            is_first_agent_from_runtime = len(self.runtime_agents[runtime_id]) == 0
            self.runtime_agents[runtime_id].add(agent_id)

            # Index agent
            await self._index_agent(agent_id, metadata)

            # Emit RUNTIME_JOINED if first agent from this runtime
            if is_first_agent_from_runtime:
                await self._emit_event(
                    RegistryEvent(
                        event_type=RegistryEventType.RUNTIME_JOINED,
                        runtime_id=runtime_id,
                        metadata={},
                    )
                )

            # Broadcast event
            await self._emit_event(
                RegistryEvent(
                    event_type=RegistryEventType.AGENT_REGISTERED,
                    agent_id=agent_id,
                    runtime_id=runtime_id,
                    metadata={"capabilities": self._extract_capabilities(a2a_card)},
                )
            )

            # Update metrics
            self._total_registrations += 1

            return agent_id

    async def deregister_agent(self, agent_id: str, runtime_id: str) -> bool:
        """
        Deregister agent from registry.

        Args:
            agent_id: Agent identifier to deregister
            runtime_id: ID of runtime deregistering the agent

        Returns:
            True if agent was deregistered, False if not found
        """
        async with self._registry_lock:
            if agent_id not in self.agents:
                return False

            # Remove from registry
            metadata = self.agents[agent_id]
            del self.agents[agent_id]

            # Remove from runtime tracking
            if runtime_id in self.runtime_agents:
                self.runtime_agents[runtime_id].discard(agent_id)
                is_last_agent_from_runtime = len(self.runtime_agents[runtime_id]) == 0

            # Remove from indexes (before changing status)
            await self._deindex_agent(agent_id, metadata)

            # Mark as OFFLINE after deindexing
            metadata.status = AgentStatus.OFFLINE

            # Broadcast event
            await self._emit_event(
                RegistryEvent(
                    event_type=RegistryEventType.AGENT_DEREGISTERED,
                    agent_id=agent_id,
                    runtime_id=runtime_id,
                )
            )

            # Emit RUNTIME_LEFT if last agent from this runtime
            if is_last_agent_from_runtime:
                await self._emit_event(
                    RegistryEvent(
                        event_type=RegistryEventType.RUNTIME_LEFT,
                        runtime_id=runtime_id,
                        metadata={},
                    )
                )

            # Update metrics
            self._total_deregistrations += 1

            return True

    # ========================================================================
    # Agent Discovery and Search
    # ========================================================================

    async def get_agent(self, agent_id: str) -> Optional[AgentMetadata]:
        """
        Get agent metadata by ID.

        Args:
            agent_id: Agent identifier

        Returns:
            AgentMetadata or None if not found
        """
        return self.agents.get(agent_id)

    async def list_agents(
        self,
        runtime_id: Optional[str] = None,
        status_filter: Optional[AgentStatus] = None,
    ) -> List[AgentMetadata]:
        """
        List agents with optional filters.

        Args:
            runtime_id: Optional runtime ID filter
            status_filter: Optional status filter

        Returns:
            List of agent metadata
        """
        agents = []

        # Filter by runtime
        if runtime_id:
            agent_ids = self.runtime_agents.get(runtime_id, set())
            agents = [self.agents[aid] for aid in agent_ids if aid in self.agents]
        else:
            agents = list(self.agents.values())

        # Filter by status
        if status_filter:
            agents = [a for a in agents if a.status == status_filter]

        return agents

    async def find_agents_by_capability(
        self, capability: str, status_filter: Optional[AgentStatus] = AgentStatus.ACTIVE
    ) -> List[AgentMetadata]:
        """
        Find agents by capability using semantic matching.

        Args:
            capability: Capability to search for
            status_filter: Optional status filter (default: ACTIVE)

        Returns:
            List of matching agent metadata sorted by relevance
        """
        async with self._query_semaphore:
            self._total_queries += 1

            matching_agents = []

            # Search through all agents
            for agent_id, metadata in self.agents.items():
                # Filter by status
                if status_filter and metadata.status != status_filter:
                    continue

                # Check A2A card
                if metadata.a2a_card:
                    # Extract capabilities
                    capabilities = self._extract_capabilities(metadata.a2a_card)

                    # Simple text matching (can be enhanced with semantic similarity)
                    for cap in capabilities:
                        if self._capability_matches(capability, cap):
                            matching_agents.append(
                                (metadata, self._calculate_match_score(capability, cap))
                            )
                            break

            # Sort by match score (highest first)
            matching_agents.sort(key=lambda x: x[1], reverse=True)

            return [agent for agent, score in matching_agents]

    async def find_agents_by_runtime(self, runtime_id: str) -> List[AgentMetadata]:
        """
        Find all agents registered to a specific runtime.

        Args:
            runtime_id: Runtime identifier

        Returns:
            List of agent metadata
        """
        agent_ids = self.runtime_agents.get(runtime_id, set())
        return [self.agents[aid] for aid in agent_ids if aid in self.agents]

    async def find_agents_by_status(self, status: AgentStatus) -> List[AgentMetadata]:
        """
        Find all agents with a specific status.

        Args:
            status: Agent status

        Returns:
            List of agent metadata
        """
        agent_ids = self.status_index.get(status, set())
        return [self.agents[aid] for aid in agent_ids if aid in self.agents]

    # ========================================================================
    # Agent Status Management
    # ========================================================================

    async def update_agent_status(
        self, agent_id: str, status: AgentStatus, runtime_id: Optional[str] = None
    ) -> bool:
        """
        Update agent status.

        Args:
            agent_id: Agent identifier
            status: New agent status
            runtime_id: Optional runtime ID for event tracking

        Returns:
            True if status was updated, False if agent not found
        """
        async with self._registry_lock:
            if agent_id not in self.agents:
                return False

            metadata = self.agents[agent_id]
            old_status = metadata.status
            metadata.status = status

            # Update status index
            self.status_index[old_status].discard(agent_id)
            self.status_index[status].add(agent_id)

            # Broadcast event
            await self._emit_event(
                RegistryEvent(
                    event_type=RegistryEventType.AGENT_STATUS_CHANGED,
                    agent_id=agent_id,
                    runtime_id=runtime_id,
                    metadata={
                        "old_status": old_status.value,
                        "new_status": status.value,
                    },
                )
            )

            return True

    async def update_agent_heartbeat(self, agent_id: str) -> bool:
        """
        Update agent heartbeat timestamp.

        Args:
            agent_id: Agent identifier

        Returns:
            True if heartbeat was updated, False if agent not found
        """
        if agent_id not in self.agents:
            return False

        metadata = self.agents[agent_id]
        metadata.last_heartbeat = datetime.now()

        return True

    # ========================================================================
    # Event Management
    # ========================================================================

    def subscribe(self, event_type: RegistryEventType, callback: Callable):
        """
        Subscribe to registry events.

        Args:
            event_type: Event type to subscribe to
            callback: Async callback function (event: RegistryEvent) -> None
        """
        self.event_listeners[event_type].append(callback)

    def unsubscribe(self, event_type: RegistryEventType, callback: Callable):
        """
        Unsubscribe from registry events.

        Args:
            event_type: Event type to unsubscribe from
            callback: Callback function to remove
        """
        if callback in self.event_listeners[event_type]:
            self.event_listeners[event_type].remove(callback)

    async def _emit_event(self, event: RegistryEvent):
        """Emit event to queue for broadcasting."""
        if self.config.enable_event_broadcasting:
            try:
                await self.event_queue.put(event)
            except asyncio.QueueFull:
                # Drop event if queue is full
                pass

    async def _broadcast_events(self):
        """Background task: Broadcast events to listeners."""
        while self._running:
            try:
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)

                # Notify listeners
                listeners = self.event_listeners.get(event.event_type, [])
                for listener in listeners:
                    try:
                        if asyncio.iscoroutinefunction(listener):
                            await listener(event)
                        else:
                            listener(event)
                    except Exception:
                        pass  # Ignore listener errors

            except asyncio.TimeoutError:
                continue

    # ========================================================================
    # Background Tasks
    # ========================================================================

    async def _monitor_heartbeats(self):
        """Background task: Monitor agent heartbeats and auto-deregister stale agents."""
        while self._running:
            await asyncio.sleep(self.config.heartbeat_timeout)

            now = datetime.now()
            stale_agents = []

            for agent_id, metadata in list(self.agents.items()):
                time_since_heartbeat = (now - metadata.last_heartbeat).total_seconds()

                if time_since_heartbeat > self.config.auto_deregister_timeout:
                    stale_agents.append(agent_id)

            # Auto-deregister stale agents
            for agent_id in stale_agents:
                # Find runtime ID
                runtime_id = None
                for rid, agent_ids in self.runtime_agents.items():
                    if agent_id in agent_ids:
                        runtime_id = rid
                        break

                await self.deregister_agent(agent_id, runtime_id or "unknown")

    async def _rebuild_indexes(self):
        """Background task: Rebuild capability and status indexes."""
        while self._running:
            await asyncio.sleep(self.config.rebuild_index_interval)

            async with self._registry_lock:
                # Rebuild capability index
                self.capability_index.clear()
                self.status_index.clear()

                for agent_id, metadata in self.agents.items():
                    await self._index_agent(agent_id, metadata)

    # ========================================================================
    # Indexing Helpers
    # ========================================================================

    async def _index_agent(self, agent_id: str, metadata: AgentMetadata):
        """Index agent by capability and status."""
        # Index by status
        self.status_index[metadata.status].add(agent_id)

        # Index by capability
        if self.config.enable_capability_indexing and metadata.a2a_card:
            capabilities = self._extract_capabilities(metadata.a2a_card)
            for cap in capabilities:
                self.capability_index[cap.lower()].add(agent_id)

    async def _deindex_agent(self, agent_id: str, metadata: AgentMetadata):
        """Remove agent from indexes."""
        # Remove from status index
        self.status_index[metadata.status].discard(agent_id)

        # Remove from capability index
        if metadata.a2a_card:
            capabilities = self._extract_capabilities(metadata.a2a_card)
            for cap in capabilities:
                self.capability_index[cap.lower()].discard(agent_id)

    def _extract_capabilities(self, a2a_card: Optional[Dict]) -> List[str]:
        """Extract capabilities from A2A card."""
        if not a2a_card:
            return []

        capabilities = []

        # Check different A2A card formats
        if isinstance(a2a_card, dict):
            # Check for "capability" field
            if "capability" in a2a_card:
                capabilities.append(a2a_card["capability"])

            # Check for "capabilities" field
            if "capabilities" in a2a_card:
                caps = a2a_card["capabilities"]
                if isinstance(caps, list):
                    capabilities.extend(caps)
                elif isinstance(caps, str):
                    capabilities.append(caps)

        return capabilities

    def _capability_matches(self, query: str, capability: str) -> bool:
        """Check if capability matches query (case-insensitive substring match)."""
        return query.lower() in capability.lower()

    def _calculate_match_score(self, query: str, capability: str) -> float:
        """
        Calculate match score between query and capability.

        Uses simple word overlap as similarity metric (Jaccard similarity).

        Args:
            query: Query string
            capability: Capability string

        Returns:
            Match score between 0.0 and 1.0
        """
        query_words = set(query.lower().split())
        cap_words = set(capability.lower().split())

        if not query_words or not cap_words:
            return 0.0

        intersection = len(query_words & cap_words)
        union = len(query_words | cap_words)

        return intersection / union if union > 0 else 0.0

    # ========================================================================
    # Metrics and Observability
    # ========================================================================

    async def get_metrics(self) -> Dict[str, Any]:
        """
        Get registry performance metrics.

        Returns:
            Metrics dictionary
        """
        total_agents = len(self.agents)
        total_runtimes = len(self.runtime_agents)

        # Status distribution
        status_counts = {
            status.value: len(agent_ids)
            for status, agent_ids in self.status_index.items()
        }

        # Runtime distribution
        runtime_distribution = {
            runtime_id: len(agent_ids)
            for runtime_id, agent_ids in self.runtime_agents.items()
        }

        return {
            "total_agents": total_agents,
            "total_runtimes": total_runtimes,
            "status_distribution": status_counts,
            "runtime_distribution": runtime_distribution,
            "total_queries": self._total_queries,
            "total_registrations": self._total_registrations,
            "total_deregistrations": self._total_deregistrations,
            "capability_index_size": len(self.capability_index),
        }

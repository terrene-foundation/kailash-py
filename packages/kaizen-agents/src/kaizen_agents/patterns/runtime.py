"""
OrchestrationRuntime - Multi-Agent Orchestration System

Production-ready orchestration runtime for 10-100 agent scaling with:
- Agent lifecycle management (register/deregister, health monitoring)
- Task distribution with A2A semantic routing
- Resource management (concurrency limits, budget enforcement)
- Error handling (retry, circuit breaker, failover)
- Monitoring and observability (progress tracking, metrics)

Architecture:
    OrchestrationRuntime
    ├── AsyncLocalRuntime (async execution engine)
    ├── SupervisorWorkerPattern (task delegation)
    ├── MetaControllerPipeline (semantic routing)
    ├── SharedMemoryPool (agent coordination)
    └── HookManager (observability)

Usage:
    from kaizen_agents.patterns.runtime import OrchestrationRuntime
    from kaizen_agents.agents import SimpleQAAgent
    from kailash.workflow.builder import WorkflowBuilder

    # Create runtime
    runtime = OrchestrationRuntime(
        max_concurrent_agents=10,
        enable_progress_tracking=True
    )
    await runtime.start()

    # Option 1: Execute Core SDK workflows via AsyncLocalRuntime
    # Build programmatic workflow
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "task1", {"code": "result = 'Hello'"})
    workflow = builder.build()

    # Execute with level-based parallelism
    result = await runtime.execute_workflow(workflow, inputs={})
    print(result["results"])  # Node execution results

    # Option 2: Multi-agent orchestration
    # Register agents
    qa_agent_id = await runtime.register_agent(
        SimpleQAAgent(config),
        max_concurrency=5,
        budget_limit_usd=1.0
    )

    # Execute multi-agent workflow
    results = await runtime.execute_multi_agent_workflow(
        tasks=["Task 1", "Task 2", "Task 3"],
        routing_strategy="semantic"
    )

    await runtime.shutdown()

Performance Targets:
- Throughput: 10,000 tasks/hour
- Latency: < 100ms orchestration overhead per agent
- Scalability: 100 agents in 10 seconds
- A2A Matching: < 50ms per selection
- Memory: < 512MB per pipeline
- Reliability: 99.9% success rate (with retry)

Author: Kaizen Framework Team
Created: 2025-11-05 (Phase 4, Orchestration Runtime)
Reference: Based on kaizen-specialist analysis and existing coordination patterns
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

# Kailash SDK imports for workflow execution
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kaizen.core.autonomy.hooks import HookManager
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.llm.reasoning import ReasoningDegradedError, llm_text_similarity
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.utils.credential_scrub import scrub_local_error

logger = logging.getLogger(__name__)

# Set availability flag for AsyncLocalRuntime
ASYNC_RUNTIME_AVAILABLE = True

# Execution modes `_build_workflow_from_agents` implements. Anything else
# raises rather than silently degrading to "parallel".
#
# "sequential" and "hybrid" were previously DOCUMENTED here but neither ever
# worked (see `_build_workflow_from_agents`), so restricting the set removes no
# working behaviour — it replaces two broken paths with one actionable error.
_WORKFLOW_BUILD_MODES = frozenset({"parallel"})

# Optional imports (may not be available in all versions)
try:
    from kailash.runtime import ResourceRegistry
except ImportError:
    ResourceRegistry = None

try:
    from kailash.workflow.base import Workflow
except ImportError:
    Workflow = None

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


class AgentStatus(StrEnum):
    """Agent health status."""

    ACTIVE = "active"  # Healthy and available
    DEGRADED = "degraded"  # Operational but limited (e.g., budget exceeded)
    UNHEALTHY = "unhealthy"  # Not responding or failed health check
    OFFLINE = "offline"  # Manually deregistered


class RoutingStrategy(StrEnum):
    """Task routing strategy."""

    SEMANTIC = "semantic"  # A2A capability-based routing (recommended)
    ROUND_ROBIN = "round-robin"  # Simple round-robin distribution
    RANDOM = "random"  # Random selection
    LEAST_LOADED = "least-loaded"  # Select agent with fewest active tasks


class ErrorHandlingMode(StrEnum):
    """Error handling mode."""

    GRACEFUL = "graceful"  # Continue on errors, return partial results
    FAIL_FAST = "fail-fast"  # Stop on first error
    CIRCUIT_BREAKER = "circuit-breaker"  # Use circuit breaker pattern


@dataclass
class RetryPolicy:
    """Retry policy configuration."""

    max_retries: int = 3  # Maximum retry attempts
    initial_delay: float = 1.0  # Initial delay in seconds
    backoff_factor: float = 2.0  # Backoff multiplier for exponential backoff
    max_delay: float = 30.0  # Maximum delay in seconds
    exceptions: tuple = (Exception,)  # Exceptions to retry


@dataclass
class OrchestrationRuntimeConfig:
    """Configuration for OrchestrationRuntime."""

    # Concurrency and resource limits
    max_concurrent_agents: int = 10  # Max concurrent agent executions
    max_queue_size: int = 1000  # Max task queue size

    # Routing and distribution
    default_routing_strategy: str = "semantic"  # Default task routing strategy
    enable_semantic_routing: bool = True  # Enable A2A capability matching

    # Health monitoring
    enable_health_monitoring: bool = True  # Enable background health checks
    health_check_interval: float = 30.0  # Health check interval in seconds
    heartbeat_timeout: float = 30.0  # Heartbeat staleness threshold

    # Error handling and retry
    default_retry_policy: RetryPolicy | None = None  # Default retry policy
    retry_policy: RetryPolicy | None = (
        None  # Alias for default_retry_policy (test compat)
    )
    error_handling: ErrorHandlingMode = (
        ErrorHandlingMode.GRACEFUL
    )  # Error handling mode
    enable_circuit_breaker: bool = True  # Enable circuit breaker pattern
    circuit_breaker_threshold: float = 0.5  # Error rate threshold (0.0-1.0)
    circuit_breaker_failure_threshold: int = 5  # Number of failures to trip breaker
    circuit_breaker_window: int = 100  # Error rate window (num requests)
    circuit_breaker_recovery_timeout: float = 30.0  # Recovery timeout in seconds

    # Resource management
    enable_budget_enforcement: bool = True  # Enforce agent budget limits
    max_budget_usd: float | None = None  # Global budget limit (None = no limit)
    enable_rate_limiting: bool = True  # Enable rate limiting

    # Monitoring and observability
    enable_progress_tracking: bool = True  # Enable real-time progress tracking
    enable_metrics: bool = True  # Enable performance metrics
    hook_manager: HookManager | None = None  # Hook manager for observability

    # Graceful shutdown
    graceful_shutdown_timeout: float = 30.0  # Max time for graceful shutdown


# ============================================================================
# Agent Metadata and Workflow Status
# ============================================================================


@dataclass
class AgentMetadata:
    """Metadata for registered agent."""

    agent_id: str  # Unique agent identifier
    agent: BaseAgent  # Agent instance
    a2a_card: A2AAgentCard | None = None  # A2A capability card

    # Resource constraints
    max_concurrency: int = 10  # Max concurrent tasks for this agent
    memory_limit_mb: int = 512  # Memory limit in MB
    budget_limit_usd: float = 1.0  # Budget limit in USD

    # Status and tracking
    status: AgentStatus = AgentStatus.ACTIVE  # Current health status
    last_heartbeat: datetime = field(
        default_factory=datetime.now
    )  # Last heartbeat timestamp
    active_tasks: int = 0  # Current active task count
    completed_tasks: int = 0  # Total completed tasks
    failed_tasks: int = 0  # Total failed tasks
    budget_spent_usd: float = 0.0  # Total budget spent

    # Performance metrics
    total_execution_time: float = 0.0  # Total execution time (seconds)
    avg_execution_time: float = 0.0  # Average execution time (seconds)
    error_count: int = 0  # Error count for circuit breaker
    request_count: int = 0  # Request count for circuit breaker


@dataclass
class WorkflowStatus:
    """Status tracking for multi-agent workflow."""

    workflow_id: str  # Unique workflow identifier
    total_tasks: int  # Total task count
    completed_tasks: int = 0  # Completed task count
    failed_tasks: int = 0  # Failed task count
    start_time: datetime = field(default_factory=datetime.now)  # Workflow start time
    estimated_completion: datetime | None = None  # Estimated completion time
    results: list[dict[str, Any]] = field(default_factory=list)  # Task results


# ============================================================================
# OrchestrationRuntime Implementation
# ============================================================================


class OrchestrationRuntime:
    """
    Production-ready orchestration runtime for 10-100 agent scaling.

    Provides agent lifecycle management, task distribution with A2A semantic routing,
    resource management, error handling, and monitoring.

    Example:
        runtime = OrchestrationRuntime(max_concurrent_agents=10)
        agent_id = await runtime.register_agent(agent, max_concurrency=5)
        results = await runtime.execute_multi_agent_workflow(tasks, routing_strategy="semantic")
    """

    def __init__(self, config: OrchestrationRuntimeConfig | None = None):
        """
        Initialize OrchestrationRuntime.

        Args:
            config: Optional configuration (uses defaults if not provided)
        """
        self.config = config or OrchestrationRuntimeConfig()

        # NEW: Create AsyncLocalRuntime for workflow execution (composition pattern)
        # This provides level-based parallelism, semaphore control, and thread pool
        # Reference: kaizen-specialist guidance on AsyncLocalRuntime integration
        if ASYNC_RUNTIME_AVAILABLE:
            # Build AsyncLocalRuntime kwargs - only include resource_registry if available
            # Note: execution_timeout is handled by OrchestrationRuntime, not passed to AsyncLocalRuntime
            runtime_kwargs = {
                "max_concurrent_nodes": self.config.max_concurrent_agents,
                "enable_analysis": True,
                "enable_profiling": True,
            }

            # Optional: Add ResourceRegistry if available
            if ResourceRegistry is not None:
                runtime_kwargs["resource_registry"] = ResourceRegistry()

            self.async_runtime = AsyncLocalRuntime(**runtime_kwargs)
        else:
            self.async_runtime = None  # Fallback to manual execution if unavailable

        # Agent registry
        self.agents: dict[str, AgentMetadata] = {}

        # Task queue with priority support and concurrency control
        # PriorityQueue orders by (priority, item) - lower priority value = higher priority
        self.task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(
            maxsize=self.config.max_queue_size
        )
        # Semaphore to limit concurrent agent executions
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent_agents)

        # Workflow tracking
        self.workflows: dict[str, WorkflowStatus] = {}

        # Shared memory pool for agent coordination
        self.shared_memory = SharedMemoryPool()

        # Hook manager for observability
        self.hook_manager = self.config.hook_manager or HookManager()

        # Runtime state
        self._running = False
        self._health_monitor_task: asyncio.Task | None = None
        self._round_robin_index = 0  # For round-robin routing
        self._is_shutting_down = False  # Shutdown flag

        # Circuit breaker state per agent (closed, open, half-open)
        self._circuit_breaker_state: dict[str, str] = {}
        # Circuit breaker failure counts per agent
        self._circuit_breaker_failures: dict[str, int] = {}
        # Circuit breaker open timestamps for recovery timeout
        self._circuit_breaker_open_time: dict[str, datetime] = {}

        # Active task tracking for execution monitoring
        self._active_tasks: dict[str, asyncio.Task] = {}

        # Budget tracking for cost enforcement
        self._total_budget_spent: float = 0.0

        # Execution history for audit trail (bounded to prevent OOM in long-running processes)
        self._execution_history: deque = deque(maxlen=10000)

        # Total tasks executed counter
        self._total_tasks_executed: int = 0

        # AsyncLocalRuntime for level-based parallelism
        self._async_runtime: AsyncLocalRuntime | None = None

        # Retry policy - use retry_policy if set, otherwise default_retry_policy
        if (
            self.config.retry_policy is None
            and self.config.default_retry_policy is None
        ):
            self.config.default_retry_policy = RetryPolicy()
        elif (
            self.config.retry_policy is not None
            and self.config.default_retry_policy is None
        ):
            self.config.default_retry_policy = self.config.retry_policy

    # ========================================================================
    # Agent Lifecycle Management
    # ========================================================================

    async def register_agent(
        self,
        agent: BaseAgent,
        agent_id: str | None = None,
        max_concurrency: int = 10,
        memory_limit_mb: int = 512,
        budget_limit_usd: float = 1.0,
    ) -> str:
        """
        Register agent with resource constraints.

        Args:
            agent: BaseAgent instance to register
            agent_id: Optional custom agent ID (auto-generated if not provided)
            max_concurrency: Max concurrent tasks for this agent
            memory_limit_mb: Memory limit in MB
            budget_limit_usd: Budget limit in USD

        Returns:
            agent_id: Unique agent identifier

        Example:
            agent_id = await runtime.register_agent(
                SimpleQAAgent(config),
                max_concurrency=5,
                budget_limit_usd=1.0
            )
        """
        # Generate agent ID if not provided
        if agent_id is None:
            agent_id = agent.agent_id or f"agent_{uuid.uuid4().hex[:8]}"

        # Guard clause: Prevent duplicate agent registration
        if agent_id in self.agents:
            raise ValueError(f"Agent with ID '{agent_id}' is already registered")

        # Get A2A capability card if available
        a2a_card = None
        if A2A_AVAILABLE and hasattr(agent, "to_a2a_card"):
            with contextlib.suppress(Exception):
                a2a_card = agent.to_a2a_card()

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

        # Initialize circuit breaker state (starts as "closed" = healthy)
        if self.config.enable_circuit_breaker:
            self._circuit_breaker_state[agent_id] = "closed"

        # Start health monitoring if not already running
        if self.config.enable_health_monitoring and not self._health_monitor_task:
            self._health_monitor_task = asyncio.create_task(
                self._monitor_agent_health()
            )

        return agent_id

    async def deregister_agent(self, agent_id: str) -> bool:
        """
        Deregister agent from runtime.

        Args:
            agent_id: Agent identifier to deregister

        Returns:
            True if agent was deregistered, False if not found
        """
        if agent_id in self.agents:
            metadata = self.agents[agent_id]
            metadata.status = AgentStatus.OFFLINE
            del self.agents[agent_id]
            return True
        return False

    async def get_agent_status(self, agent_id: str) -> dict[str, Any] | None:
        """
        Get agent status and metrics.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent status dictionary or None if not found
        """
        if agent_id not in self.agents:
            return None

        metadata = self.agents[agent_id]
        return {
            "agent_id": metadata.agent_id,
            "status": metadata.status.value,
            "active_tasks": metadata.active_tasks,
            "completed_tasks": metadata.completed_tasks,
            "failed_tasks": metadata.failed_tasks,
            "budget_spent_usd": metadata.budget_spent_usd,
            "budget_limit_usd": metadata.budget_limit_usd,
            "avg_execution_time": metadata.avg_execution_time,
            "last_heartbeat": metadata.last_heartbeat.isoformat(),
        }

    async def list_agents(
        self, status_filter: AgentStatus | None = None
    ) -> list[dict[str, Any]]:
        """
        List all registered agents with optional status filter.

        Args:
            status_filter: Optional status filter (e.g., AgentStatus.ACTIVE)

        Returns:
            List of agent status dictionaries
        """
        agents = []
        for agent_id, metadata in self.agents.items():
            if status_filter is None or metadata.status == status_filter:
                agent_status = await self.get_agent_status(agent_id)
                if agent_status:
                    agents.append(agent_status)
        return agents

    async def _monitor_agent_health(self):
        """Background task: Monitor agent health every N seconds."""
        while self._running or self.agents:
            await asyncio.sleep(self.config.health_check_interval)

            for _agent_id, metadata in list(self.agents.items()):
                # Check heartbeat staleness
                time_since_heartbeat = (
                    datetime.now() - metadata.last_heartbeat
                ).total_seconds()
                if time_since_heartbeat > self.config.heartbeat_timeout:
                    metadata.status = AgentStatus.UNHEALTHY

                # Check budget limit
                if (
                    self.config.enable_budget_enforcement
                    and metadata.budget_spent_usd >= metadata.budget_limit_usd
                ):
                    metadata.status = AgentStatus.DEGRADED

                # Check circuit breaker
                if self.config.enable_circuit_breaker and metadata.request_count > 0:
                    error_rate = metadata.error_count / metadata.request_count
                    if error_rate > self.config.circuit_breaker_threshold:
                        metadata.status = AgentStatus.DEGRADED

    # ========================================================================
    # Task Routing and Distribution
    # ========================================================================

    async def route_task(
        self, task: str, strategy: RoutingStrategy | None = None
    ) -> BaseAgent | None:
        """
        Route task to best agent using specified strategy.

        Args:
            task: Task description
            strategy: Optional routing strategy (uses config default if not provided)

        Returns:
            Selected agent or None if no agents available

        Raises:
            ReasoningDegradedError: SEMANTIC strategy only — every candidate
                capability degraded (#1981), so no ranking exists. See
                `_route_semantic`.

        Example:
            agent = await runtime.route_task("Analyze sales data", strategy="semantic")
        """
        if not self.agents:
            return None

        # Use default strategy if not specified
        if strategy is None:
            strategy = RoutingStrategy(self.config.default_routing_strategy)

        # Get healthy agents only
        healthy_agents = [
            (agent_id, metadata)
            for agent_id, metadata in self.agents.items()
            if metadata.status == AgentStatus.ACTIVE
        ]

        if not healthy_agents:
            # No healthy agents, try degraded agents as fallback
            healthy_agents = [
                (agent_id, metadata)
                for agent_id, metadata in self.agents.items()
                if metadata.status == AgentStatus.DEGRADED
            ]

        if not healthy_agents:
            return None

        # Route based on strategy
        if strategy == RoutingStrategy.SEMANTIC and self.config.enable_semantic_routing:
            chosen = await self._route_semantic(task, healthy_agents)
        elif strategy == RoutingStrategy.LEAST_LOADED:
            chosen = await self._route_least_loaded(healthy_agents)
        elif strategy == RoutingStrategy.RANDOM:
            chosen = await self._route_random(healthy_agents)
        else:  # ROUND_ROBIN
            chosen = await self._route_round_robin(healthy_agents)

        # The strategy helpers return the (agent_id, metadata) CANDIDATE TUPLE
        # rather than the agent object. That is what lets `_route_task` recover
        # the ID without a reverse lookup: mapping an agent OBJECT back to an ID
        # is ambiguous when two ids share one instance, and doing so collapsed
        # round-robin to a single agent. This surface's own contract is
        # unchanged — it still returns the agent.
        return chosen[1].agent if chosen is not None else None

    async def _route_semantic(self, task: str, agents: list[tuple]) -> tuple | None:
        """Route using A2A capability matching (best-fit selection).

        Capability scoring is delegated to the LLM via
        `kaizen.llm.reasoning.llm_capability_match` (for Capability objects)
        and `kaizen.llm.reasoning.llm_text_similarity` (for plain-string
        capability names). Deterministic word-overlap scoring was removed to
        comply with `rules/agent-reasoning.md` MUST Rule 1.

        Degraded judgments (#1981): a capability the judge could not score is
        SKIPPED, never scored at a fabricated 0.0. An agent all of whose
        capabilities degraded has UNKNOWN fit and takes no part in the
        ranking.

        Raises:
            ReasoningDegradedError: Every candidate capability degraded, so
                nothing was scoreable. Falling through to round-robin here
                would hide a total judge failure behind a plausible-looking
                assignment — the arbitrary order #1981 exists to eliminate.
                A round where capabilities WERE scored but all scored 0.0 is
                a genuine no-match and keeps the round-robin fallback.
        """
        best_agent = None
        best_score = 0.0
        scored_capabilities = 0
        degraded_agents: list[str] = []
        degraded_model = "unknown"

        reasoning_config = self._resolve_reasoning_config(agents)

        for agent_id, metadata in agents:
            if metadata.a2a_card is None:
                continue

            # Handle both dict and object access for a2a_card
            a2a_card = metadata.a2a_card
            capabilities = None

            if isinstance(a2a_card, dict):
                # Dictionary access (from to_a2a_card() return)
                capabilities = a2a_card.get("capabilities", [])
                if not capabilities:
                    capabilities = a2a_card.get("primary_capabilities", [])
            else:
                # Object access (A2AAgentCard instance)
                capabilities = getattr(a2a_card, "primary_capabilities", None)
                if capabilities is None:
                    capabilities = getattr(a2a_card, "capabilities", [])

            if not capabilities:
                continue

            # Calculate capability match score via LLM (not keyword overlap)
            agent_scored = 0
            agent_degraded = 0
            for cap in capabilities:
                try:
                    score = await self._score_capability(
                        cap, task, reasoning_config, agent_id=agent_id
                    )
                except ReasoningDegradedError as exc:
                    # This capability's fit is UNKNOWN, not zero.
                    agent_degraded += 1
                    degraded_model = exc.model
                    continue

                agent_scored += 1
                scored_capabilities += 1
                if score > best_score:
                    best_agent = (agent_id, metadata)
                    best_score = score

            if agent_degraded and agent_scored == 0:
                degraded_agents.append(agent_id)

        if degraded_agents:
            if scored_capabilities == 0:
                raise ReasoningDegradedError(
                    "runtime.route_semantic",
                    model=degraded_model,
                    correlation_id=f"route_semantic_{uuid.uuid4().hex[:8]}",
                    error=(
                        f"the capability judge degraded for all "
                        f"{len(degraded_agents)} candidate agent(s): "
                        f"{', '.join(degraded_agents)}"
                    ),
                )
            logger.warning(
                "route_semantic.degraded",
                extra={
                    "candidates": len(agents),
                    "scored_capabilities": scored_capabilities,
                    "degraded_agents": degraded_agents,
                },
            )

        # Fallback to round-robin if no match found
        if best_agent is None:
            if scored_capabilities == 0 and not degraded_agents:
                # NOT the #1981 degradation case — nothing degraded, there was
                # nothing to rank on: no candidate carried an `a2a_card`, or
                # every card's capability list was empty, so the judge was
                # never consulted at all.
                #
                # The two neighbouring outcomes are both loud — an
                # all-degraded round raises, a partially-degraded one WARNs —
                # while this one returned a round-robin pick indistinguishable
                # from a ranked result. The caller asked for SEMANTIC routing
                # and received positional selection with no signal, which is
                # the silent-fallback mode `rules/zero-tolerance.md` Rule 3
                # blocks.
                #
                # WARN rather than raise: unlike a judge failure this is a
                # registration-shape issue the operator fixes by populating the
                # cards, and raising would break a documented
                # `BaseAgent | None` surface. The ranking genuinely cannot be
                # performed either way — the defect was the silence, not the
                # fallback.
                logger.warning(
                    "route_semantic.no_capability_data",
                    extra={
                        "candidates": len(agents),
                        "reason": (
                            "SEMANTIC routing requested but no candidate agent "
                            "exposed capabilities to rank; falling back to "
                            "round-robin (positional, not semantic)"
                        ),
                        "remedy": (
                            "populate primary_capabilities on the agents' A2A "
                            "cards, or select a non-SEMANTIC routing strategy"
                        ),
                    },
                )
            return await self._route_round_robin(agents)

        return best_agent

    def _resolve_reasoning_config(self, agents: list[tuple]) -> BaseAgentConfig | None:
        """Return a BaseAgentConfig to use for LLM-based routing decisions.

        Picks the first registered agent's config so the routing judge shares
        the host agent's model selection. Returns None when no agent has a
        usable config, in which case the reasoning helpers fall back to
        `.env`-defined defaults.
        """
        for _agent_id, metadata in agents:
            agent = getattr(metadata, "agent", None)
            if agent is None:
                continue
            candidate = getattr(agent, "config", None)
            if isinstance(candidate, BaseAgentConfig):
                return candidate
        return None

    async def _score_capability(
        self,
        cap: Any,
        task: str,
        reasoning_config: BaseAgentConfig | None,
        *,
        agent_id: str | None = None,
    ) -> float:
        """Score a capability against a task using LLM reasoning.

        Accepts:
            - Capability dataclass instances (sync `matches_requirement`; it
              awaits nothing and the whole A2A call chain is sync — see #1973)
            - Capability-like objects exposing an async `matches_requirement`
            - Legacy test mocks with a single-positional `matches_requirement`
            - Plain strings (capability name only) — scored via LLM similarity

        Returns 0.0 on any INFRASTRUCTURE exception so a single LLM failure
        cannot sink the entire routing decision; a WARN log captures the
        failure so `rules/observability.md` MUST Rule 5 still triages it.

        Raises:
            ReasoningDegradedError: The judge returned no usable score
                (#1981). Deliberately NOT flattened to 0.0 — the caller
                (`_route_semantic`) skips the capability instead, so a
                degraded judgment can never out-rank or tie a real one.
        """
        correlation_id = f"route_{agent_id or 'unknown'}"

        if isinstance(cap, str):
            try:
                return llm_text_similarity(
                    text_a=task,
                    text_b=cap,
                    config=reasoning_config,
                    correlation_id=correlation_id,
                )
            except ReasoningDegradedError as exc:
                logger.warning(
                    "route_semantic.similarity_degraded",
                    extra={
                        "correlation_id": correlation_id,
                        "agent_id": agent_id,
                        "helper": exc.helper,
                        "model": exc.model,
                        "error": exc.error,
                    },
                )
                raise
            except Exception as exc:
                logger.warning(
                    "route_semantic.similarity_failed",
                    extra={
                        "correlation_id": correlation_id,
                        "agent_id": agent_id,
                        "error": scrub_local_error(exc),
                    },
                )
                return 0.0

        matcher = getattr(cap, "matches_requirement", None)
        if matcher is None:
            return 0.0

        try:
            if inspect.iscoroutinefunction(matcher):
                return await matcher(
                    task, config=reasoning_config, correlation_id=correlation_id
                )
            # #1973: `Capability.matches_requirement` is sync (it awaits
            # nothing), so the judge config MUST be propagated on this branch
            # too — otherwise the routing judge silently falls back to `.env`
            # defaults instead of the host agent's model. Legacy single-arg
            # mocks raise TypeError here and are retried positionally below.
            result = matcher(
                task, config=reasoning_config, correlation_id=correlation_id
            )
            if inspect.iscoroutine(result):
                return await result
            return float(result)
        except ReasoningDegradedError as exc:
            # `Capability.matches_requirement` delegates to
            # `llm_capability_match`, so the typed signal reaches here too.
            # Ordered BEFORE the generic handler so it is not flattened.
            logger.warning(
                "route_semantic.capability_match_degraded",
                extra={
                    "correlation_id": correlation_id,
                    "agent_id": agent_id,
                    "helper": exc.helper,
                    "model": exc.model,
                    "error": exc.error,
                },
            )
            raise
        except TypeError:
            # Legacy sync mock with single-arg signature
            try:
                result = matcher(task)
                return float(result)
            except ReasoningDegradedError as exc:
                logger.warning(
                    "route_semantic.legacy_capability_match_degraded",
                    extra={
                        "correlation_id": correlation_id,
                        "agent_id": agent_id,
                        "helper": exc.helper,
                        "model": exc.model,
                        "error": exc.error,
                    },
                )
                raise
            except Exception as exc:
                logger.warning(
                    "route_semantic.capability_match_failed",
                    extra={
                        "correlation_id": correlation_id,
                        "agent_id": agent_id,
                        "error": scrub_local_error(exc),
                    },
                )
                return 0.0
        except Exception as exc:
            logger.warning(
                "route_semantic.capability_match_failed",
                extra={
                    "correlation_id": correlation_id,
                    "agent_id": agent_id,
                    "error": scrub_local_error(exc),
                },
            )
            return 0.0

    async def _route_least_loaded(self, agents: list[tuple]) -> tuple | None:
        """Route to agent with fewest active tasks. Returns the CANDIDATE TUPLE."""
        return min(agents, key=lambda x: x[1].active_tasks)

    async def _route_random(self, agents: list[tuple]) -> tuple:
        """Route to random agent."""
        import random

        return random.choice(agents)

    async def _route_round_robin(self, agents: list[tuple]) -> tuple:
        """Route using round-robin distribution."""
        # Normalise on READ, not only on write. `_round_robin_index` is
        # RUNTIME-scoped and persists across calls, while `agents` is a
        # PER-CALL candidate list whose length varies — a deregistration, or
        # the health monitor marking an agent UNHEALTHY, shrinks the pool
        # below an index a previous larger-pool call already stored.
        #
        # Writing `(index + 1) % len(agents)` only bounds the index against
        # the length seen on THIS call; the very next call with a shorter list
        # indexes out of range and raises IndexError, aborting the whole
        # routing call rather than degrading. Reproduced with no forced state:
        # 3 agents, two ordinary ROUND_ROBIN routes (index -> 2), deregister
        # one, third route -> IndexError.
        #
        # This guard already existed in `_route_task`'s now-deleted private
        # round-robin copy and was missing here, in the live path — the
        # duplicate-implementation drift that clause is about.
        index = self._round_robin_index % len(agents)
        self._round_robin_index = (index + 1) % len(agents)
        return agents[index]

    # ========================================================================
    # Workflow Execution (AsyncLocalRuntime Integration)
    # ========================================================================

    async def execute_workflow(
        self,
        workflow: Workflow,
        inputs: dict[str, Any] | None = None,
        workflow_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a Core SDK Workflow using AsyncLocalRuntime's level-based parallelism.

        This method demonstrates AsyncLocalRuntime integration for executing
        programmatically-built workflows (via WorkflowBuilder) through the
        OrchestrationRuntime infrastructure.

        Args:
            workflow: Core SDK Workflow object (from WorkflowBuilder.build())
            inputs: Optional input parameters for workflow execution
            workflow_id: Optional workflow ID for tracking (generates UUID if not provided)

        Returns:
            Dictionary containing workflow results and execution metadata:
                {
                    "workflow_id": str,
                    "results": Dict[str, Any],  # Node execution results
                    "run_id": str,              # AsyncLocalRuntime run ID
                    "status": str,              # "completed" or "failed"
                    "execution_time": float,    # Total execution time in seconds
                    "error": Optional[str]      # Error message if failed
                }

        Example:
            from kailash.workflow.builder import WorkflowBuilder

            # Build workflow
            builder = WorkflowBuilder()
            builder.add_node("EchoNode", "echo1", {"message": "Hello"})
            workflow = builder.build()

            # Execute via OrchestrationRuntime
            results = await runtime.execute_workflow(workflow, inputs={})

        Reference:
            - kaizen-specialist guidance: "Wrap AsyncLocalRuntime, don't extend it"
            - Composition pattern from __init__() (lines 229-241)
            - AsyncLocalRuntime docs: kailash.runtime.AsyncLocalRuntime
        """
        if not ASYNC_RUNTIME_AVAILABLE or self.async_runtime is None:
            raise RuntimeError(
                "AsyncLocalRuntime not available. Install with: pip install kailash>=0.10.4"
            )

        # Generate workflow ID for tracking
        if workflow_id is None:
            workflow_id = f"workflow_{uuid.uuid4().hex[:8]}"

        start_time = time.time()

        try:
            # Execute workflow via AsyncLocalRuntime (composition pattern)
            # This leverages:
            # - Level-based parallelism (automatic dependency-respecting concurrency)
            # - Semaphore control (max_concurrent_nodes limit)
            # - Thread pool (for sync nodes)
            # - Resource management (shared ResourceRegistry)
            results, run_id = await self.async_runtime.execute_workflow_async(
                workflow, inputs=inputs or {}
            )

            execution_time = time.time() - start_time

            return {
                "workflow_id": workflow_id,
                "results": results,
                "run_id": run_id,
                "status": "completed",
                "execution_time": execution_time,
            }

        except Exception as e:
            execution_time = time.time() - start_time

            return {
                "workflow_id": workflow_id,
                "results": {},
                "run_id": None,
                "status": "failed",
                "execution_time": execution_time,
                "error": scrub_local_error(e),
            }

    # ========================================================================
    # Multi-Agent Workflow Execution
    # ========================================================================

    async def execute_multi_agent_workflow(
        self,
        tasks: list[str],
        routing_strategy: str | None = None,
        error_handling: str = "graceful",
        max_concurrent: int | None = None,
    ) -> dict[str, Any]:
        """
        Execute multiple tasks across agents with level-based parallelism via AsyncLocalRuntime.

        AsyncLocalRuntime Integration replaces worker queue pattern with workflow-based execution for true concurrency.

        Pattern: Route tasks to agents → Build workflow → Execute via AsyncLocalRuntime
        Result: 10-100 agents executing concurrently (level-based parallelism)

        Args:
            tasks: List of task descriptions
            routing_strategy: Optional routing strategy (semantic, round-robin, etc.)
            error_handling: Error handling mode (graceful, fail-fast)
            max_concurrent: Optional max concurrent tasks (uses config default if not provided)

        Returns:
            Workflow results dictionary with completion status and task results

        Raises:
            ReasoningDegradedError: `error_handling="fail-fast"` ONLY, and
                only when SEMANTIC routing degraded for a task (#1981). Under
                the default `"graceful"` mode the degradation is recorded as a
                failed task carrying `degraded: True` instead — mirroring how
                the execution phase below already honours `error_handling`.

        Example:
            results = await runtime.execute_multi_agent_workflow(
                tasks=["Analyze data", "Generate code", "Write documentation"],
                routing_strategy="semantic",
                error_handling="graceful"
            )
        """
        # Generate workflow ID
        workflow_id = f"workflow_{uuid.uuid4().hex[:8]}"

        # Create workflow status
        workflow_status = WorkflowStatus(
            workflow_id=workflow_id, total_tasks=len(tasks)
        )

        # INVARIANT: `self.workflows` only ever holds workflows whose ROUTING
        # phase completed.
        #
        # `route_task` below can raise (`ReasoningDegradedError`, #1981) and
        # `error_handling="fail-fast"` re-raises it. Publishing the status
        # object BEFORE the fallible routing loop left a phantom entry behind
        # on that path: `get_workflow_status()` reported it as perpetually
        # in-flight (total_tasks=N, completed=0, failed=0) and NOTHING could
        # ever clear it, because the caller never received the generated
        # `workflow_id` — the function raised before returning it. Publishing
        # AFTER routing is chosen over rolling back on the error path because
        # it has no rollback race and loses no observability: the id is not
        # knowable to any caller until this method returns.
        # (`workflow_status` is a local until then, so the routing loop's own
        # bookkeeping below is unaffected.)

        # Route tasks to agents. Pair each agent WITH its task so a task that
        # fails to route cannot shift the agent->task mapping of the tasks
        # that follow it.
        routed: list[tuple[BaseAgent, str]] = []
        for task in tasks:
            try:
                agent = await self.route_task(
                    task,
                    strategy=(
                        RoutingStrategy(routing_strategy) if routing_strategy else None
                    ),
                )
            except ReasoningDegradedError as exc:
                # #1981 second-order: SEMANTIC routing raises when the
                # capability judge degraded for EVERY candidate, rather than
                # handing back an arbitrarily-ordered agent. Honour the same
                # `error_handling` policy the execution phase below uses.
                logger.warning(
                    "execute_multi_agent_workflow.routing_degraded",
                    extra={
                        "workflow_id": workflow_id,
                        "error_handling": error_handling,
                        "correlation_id": exc.correlation_id,
                        "helper": exc.helper,
                        "model": exc.model,
                        "error": exc.error,
                    },
                )
                if error_handling == "fail-fast":
                    # Nothing was published to `self.workflows`, so the
                    # invariant above holds with no cleanup needed.
                    raise
                # Graceful: this task failed, the workflow continues. The
                # `degraded` marker is what keeps a total judge failure
                # distinguishable from the genuine "No agents available"
                # no-match recorded below — the same float/`[]`/`None`
                # collision #1981 exists to eliminate.
                workflow_status.failed_tasks += 1
                workflow_status.results.append(
                    {
                        "task": task,
                        "status": "failed",
                        "degraded": True,
                        "error": scrub_local_error(exc),
                        "degraded_helper": exc.helper,
                        "degraded_model": exc.model,
                        "correlation_id": exc.correlation_id,
                    }
                )
                continue

            if agent is None:
                # No agents available for this task
                workflow_status.failed_tasks += 1
                workflow_status.results.append(
                    {"task": task, "status": "failed", "error": "No agents available"}
                )
            else:
                routed.append((agent, task))

        # Routing completed — the workflow is now admitted and observable.
        self.workflows[workflow_id] = workflow_status

        selected_agents = [agent for agent, _task in routed]

        # Build workflow from agents (enables level-based parallelism)
        if selected_agents:
            assigned_tasks = [task for _agent, task in routed]

            workflow = self._build_workflow_from_agents(
                selected_agents,
                assigned_tasks,
                mode="parallel",  # No dependencies, maximize concurrency
            )

            try:
                # Execute workflow via AsyncLocalRuntime (level-based parallelism)
                results, run_id = await self._async_runtime.execute_workflow_async(
                    workflow.build(), inputs={}
                )

                # Extract results from workflow execution
                for i, (agent, task) in enumerate(
                    zip(selected_agents, assigned_tasks, strict=False)
                ):
                    node_id = f"agent_{i}_{agent.agent_id}"

                    if node_id in results:
                        # Successful execution
                        workflow_status.completed_tasks += 1
                        workflow_status.results.append(
                            {
                                "task": task,
                                "agent_id": agent.agent_id,
                                "status": "completed",
                                "result": results[node_id],
                                "run_id": run_id,
                            }
                        )
                    else:
                        # Failed execution (node not in results)
                        workflow_status.failed_tasks += 1
                        workflow_status.results.append(
                            {
                                "task": task,
                                "agent_id": agent.agent_id,
                                "status": "failed",
                                "error": "Workflow execution failed",
                            }
                        )

            except Exception as e:
                # Workflow execution error
                if error_handling == "fail-fast":
                    # Re-raise error to fail immediately
                    raise

                # Graceful error handling: mark all tasks as failed
                for agent, task in zip(selected_agents, assigned_tasks, strict=False):
                    workflow_status.failed_tasks += 1
                    workflow_status.results.append(
                        {
                            "task": task,
                            "agent_id": agent.agent_id,
                            "status": "failed",
                            "error": scrub_local_error(e),
                        }
                    )

        # Return workflow results
        return {
            "workflow_id": workflow_id,
            "total_tasks": workflow_status.total_tasks,
            "completed_tasks": workflow_status.completed_tasks,
            "failed_tasks": workflow_status.failed_tasks,
            "success_rate": (
                workflow_status.completed_tasks / workflow_status.total_tasks
                if workflow_status.total_tasks > 0
                else 0.0
            ),
            "results": workflow_status.results,
        }

    async def _execute_with_retry(
        self, agent: BaseAgent, task: str, retry_policy: RetryPolicy | None = None
    ) -> dict[str, Any]:
        """
        Execute agent with retry logic and exponential backoff.

        Args:
            agent: Agent to execute
            task: Task to execute
            retry_policy: Optional retry policy (uses config default if not provided)

        Returns:
            Execution result dictionary
        """
        # Use config default if not specified
        if retry_policy is None:
            retry_policy = self.config.default_retry_policy

        # Find agent metadata
        agent_metadata = None
        for metadata in self.agents.values():
            if metadata.agent == agent:
                agent_metadata = metadata
                break

        # Execute with retry
        for attempt in range(retry_policy.max_retries):
            try:
                # Check resource limits
                if agent_metadata:
                    # Wait if at concurrency limit
                    while agent_metadata.active_tasks >= agent_metadata.max_concurrency:
                        await asyncio.sleep(0.1)

                    # Check budget
                    if self.config.enable_budget_enforcement and (
                        agent_metadata.budget_spent_usd
                        >= agent_metadata.budget_limit_usd
                    ):
                        return {
                            "task": task,
                            "status": "failed",
                            "error": "Budget limit exceeded",
                            "agent_id": agent_metadata.agent_id,
                        }

                    # Increment active task counter
                    agent_metadata.active_tasks += 1
                    agent_metadata.request_count += 1

                # Execute agent
                start_time = time.time()

                if hasattr(agent, "run_async"):
                    result = await agent.run_async(task=task)
                else:
                    # Fallback to sync execution in thread pool
                    result = await asyncio.to_thread(agent.run, task=task)

                execution_time = time.time() - start_time

                # Update metadata
                if agent_metadata:
                    agent_metadata.active_tasks -= 1
                    agent_metadata.completed_tasks += 1
                    agent_metadata.last_heartbeat = datetime.now()
                    agent_metadata.total_execution_time += execution_time
                    agent_metadata.avg_execution_time = (
                        agent_metadata.total_execution_time
                        / agent_metadata.completed_tasks
                    )

                    # Track budget if available
                    cost = result.get("cost", 0.0) if isinstance(result, dict) else 0.0
                    agent_metadata.budget_spent_usd += cost

                return {
                    "task": task,
                    "status": "completed",
                    "result": result,
                    "execution_time": execution_time,
                    "agent_id": (
                        agent_metadata.agent_id if agent_metadata else "unknown"
                    ),
                    "attempts": attempt + 1,
                }

            except retry_policy.exceptions as e:
                # Update error count
                if agent_metadata:
                    agent_metadata.active_tasks -= 1
                    agent_metadata.error_count += 1

                if attempt < retry_policy.max_retries - 1:
                    # Calculate backoff delay using backoff_factor (exponential backoff)
                    delay = min(
                        retry_policy.initial_delay
                        * (retry_policy.backoff_factor**attempt),
                        retry_policy.max_delay,
                    )

                    await asyncio.sleep(delay)
                else:
                    # Final attempt failed
                    if agent_metadata:
                        agent_metadata.failed_tasks += 1

                    return {
                        "task": task,
                        "status": "failed",
                        "error": scrub_local_error(e),
                        "agent_id": (
                            agent_metadata.agent_id if agent_metadata else "unknown"
                        ),
                        "attempts": retry_policy.max_retries,
                    }

        # Should not reach here
        return {
            "task": task,
            "status": "failed",
            "error": "Unknown error",
            "attempts": retry_policy.max_retries,
        }

    # ========================================================================
    # Monitoring and Observability
    # ========================================================================

    async def get_workflow_status(self, workflow_id: str) -> dict[str, Any] | None:
        """
        Get workflow execution status and progress.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Workflow status dictionary or None if not found
        """
        if workflow_id not in self.workflows:
            return None

        status = self.workflows[workflow_id]

        # Calculate completion percentage
        completion_pct = (
            (status.completed_tasks + status.failed_tasks) / status.total_tasks * 100
            if status.total_tasks > 0
            else 0.0
        )

        # Calculate ETA
        if status.completed_tasks > 0:
            elapsed = (datetime.now() - status.start_time).total_seconds()
            avg_time_per_task = elapsed / status.completed_tasks
            remaining_tasks = (
                status.total_tasks - status.completed_tasks - status.failed_tasks
            )
            eta_seconds = avg_time_per_task * remaining_tasks
            estimated_completion = datetime.now() + timedelta(seconds=eta_seconds)
        else:
            estimated_completion = None

        return {
            "workflow_id": workflow_id,
            "total_tasks": status.total_tasks,
            "completed_tasks": status.completed_tasks,
            "failed_tasks": status.failed_tasks,
            "completion_percentage": completion_pct,
            "start_time": status.start_time.isoformat(),
            "estimated_completion": (
                estimated_completion.isoformat() if estimated_completion else None
            ),
        }

    async def get_metrics(self) -> dict[str, Any]:
        """
        Get runtime performance metrics.

        Returns:
            Metrics dictionary with runtime statistics
        """
        total_agents = len(self.agents)
        active_agents = sum(
            1 for m in self.agents.values() if m.status == AgentStatus.ACTIVE
        )
        degraded_agents = sum(
            1 for m in self.agents.values() if m.status == AgentStatus.DEGRADED
        )
        unhealthy_agents = sum(
            1 for m in self.agents.values() if m.status == AgentStatus.UNHEALTHY
        )

        total_completed = sum(m.completed_tasks for m in self.agents.values())
        total_failed = sum(m.failed_tasks for m in self.agents.values())
        total_budget_spent = sum(m.budget_spent_usd for m in self.agents.values())

        # Calculate average execution time
        total_execution_time = sum(m.total_execution_time for m in self.agents.values())
        avg_execution_time = (
            total_execution_time / total_completed if total_completed > 0 else 0.0
        )

        return {
            "total_agents": total_agents,
            "active_agents": active_agents,
            "degraded_agents": degraded_agents,
            "unhealthy_agents": unhealthy_agents,
            "total_completed_tasks": total_completed,
            "total_failed_tasks": total_failed,
            "total_tasks_executed": self._total_tasks_executed,  # For test compatibility
            "success_rate": (
                total_completed / (total_completed + total_failed)
                if (total_completed + total_failed) > 0
                else 0.0
            ),
            "total_budget_spent_usd": total_budget_spent,
            "total_budget_spent": total_budget_spent,  # Alias for test compatibility
            "avg_execution_time_seconds": avg_execution_time,
        }

    # ========================================================================
    # Lifecycle Management
    # ========================================================================

    async def start(self):
        """Start orchestration runtime."""
        self._running = True

        # Initialize AsyncLocalRuntime for level-based parallelism
        # Must be created in async context to use AsyncLocalRuntime
        self._async_runtime = AsyncLocalRuntime(
            max_concurrent_nodes=self.config.max_concurrent_agents
        )

        # Start health monitoring
        if self.config.enable_health_monitoring:
            self._health_monitor_task = asyncio.create_task(
                self._monitor_agent_health()
            )

    async def shutdown(self, graceful: bool = True, timeout: float = 30.0):
        """
        Shutdown orchestration runtime.

        Args:
            graceful: If True, wait for active tasks to complete; if False, cancel immediately
            timeout: Graceful shutdown timeout in seconds
        """
        self._running = False
        self._is_shutting_down = True

        if graceful:
            # Wait for active tasks to complete (with timeout)
            start_time = time.time()
            while time.time() - start_time < timeout:
                active_count = sum(m.active_tasks for m in self.agents.values())
                # Also check _active_tasks dictionary
                if active_count == 0 and len(self._active_tasks) == 0:
                    break
                await asyncio.sleep(0.1)
        else:
            # Immediate shutdown - cancel all active tasks
            for _task_id, task in list(self._active_tasks.items()):
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                        await asyncio.wait_for(asyncio.shield(task), timeout=0.1)

        # Clear active tasks
        self._active_tasks.clear()

        # Cancel health monitoring
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_monitor_task

        # Clear agents
        self.agents.clear()
        self.workflows.clear()

    # ========================================================================
    # Additional Helper Methods (for testing compatibility)
    # ========================================================================

    async def execute_task(
        self, agent_id: str, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Execute a single task on a specific agent.

        Args:
            agent_id: ID of agent to execute task on
            inputs: Task input parameters

        Returns:
            Task execution results

        Raises:
            ValueError: If agent not found
            RuntimeError: If budget exceeded or agent unavailable
        """
        start_time = time.time()

        # Check if agent exists
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not found")

        agent_metadata = self.agents[agent_id]
        agent = agent_metadata.agent

        # Check circuit breaker with recovery timeout
        if self.config.enable_circuit_breaker:
            cb_state = self._circuit_breaker_state.get(agent_id, "closed")
            if cb_state == "open":
                # Check if recovery timeout has passed
                open_time = self._circuit_breaker_open_time.get(agent_id)
                if open_time:
                    elapsed = (datetime.now() - open_time).total_seconds()
                    if elapsed >= self.config.circuit_breaker_recovery_timeout:
                        # Move to half-open state
                        self._circuit_breaker_state[agent_id] = "half-open"
                    else:
                        raise RuntimeError(f"Circuit breaker open for agent {agent_id}")
                else:
                    raise RuntimeError(f"Circuit breaker open for agent {agent_id}")

        # Check global budget if configured
        max_budget = self.config.max_budget_usd
        if max_budget is not None:
            task_cost = self._calculate_task_cost(agent_id, inputs)
            if self._total_budget_spent + task_cost > max_budget:
                raise RuntimeError(
                    f"Global budget exceeded: ${self._total_budget_spent + task_cost:.2f} > ${max_budget:.2f}"
                )

        # Get retry policy
        retry_policy = self.config.retry_policy or self.config.default_retry_policy

        # Determine if we should retry based on error handling mode
        error_handling = self.config.error_handling
        should_retry = error_handling != ErrorHandlingMode.FAIL_FAST

        # Execute with retry logic, using semaphore for concurrency control
        max_attempts = retry_policy.max_retries if should_retry else 1
        last_error = None

        # Acquire semaphore to limit concurrent executions
        async with self.semaphore:
            for attempt in range(max_attempts):
                try:
                    # Execute agent via internal helper (allows test mocking)
                    if hasattr(agent, "run") and callable(agent.run):
                        result = await self._execute_agent_task(agent, inputs)
                    else:
                        result = {"result": "success"}

                    # Success - update counters
                    duration = time.time() - start_time
                    self._total_tasks_executed += 1
                    agent_metadata.completed_tasks += 1

                    # Reset circuit breaker on success (especially from half-open state)
                    if self.config.enable_circuit_breaker:
                        self._circuit_breaker_state[agent_id] = "closed"
                        self._circuit_breaker_failures[agent_id] = 0

                    # Record execution history
                    if self.config.enable_progress_tracking:
                        self._execution_history.append(
                            {
                                "agent_id": agent_id,
                                "status": "success",
                                "timestamp": datetime.now().isoformat(),
                                "duration_seconds": duration,
                                "inputs": inputs,
                                "attempt": attempt + 1,
                            }
                        )

                    return result

                except Exception as e:
                    last_error = e
                    agent_metadata.error_count += 1

                    # Update circuit breaker failure count
                    if self.config.enable_circuit_breaker:
                        failures = self._circuit_breaker_failures.get(agent_id, 0) + 1
                        self._circuit_breaker_failures[agent_id] = failures

                        # Check if we should trip the circuit breaker
                        threshold = self.config.circuit_breaker_failure_threshold
                        if failures >= threshold:
                            self._circuit_breaker_state[agent_id] = "open"
                            self._circuit_breaker_open_time[agent_id] = datetime.now()

                    # If fail-fast mode, raise immediately
                    if error_handling == ErrorHandlingMode.FAIL_FAST:
                        raise

                    # If this was the last attempt, mark agent unhealthy and raise
                    if attempt >= max_attempts - 1:
                        agent_metadata.status = AgentStatus.UNHEALTHY
                        agent_metadata.failed_tasks += 1

                        # Record failed execution
                        if self.config.enable_progress_tracking:
                            duration = time.time() - start_time
                            self._execution_history.append(
                                {
                                    "agent_id": agent_id,
                                    "status": "failed",
                                    "timestamp": datetime.now().isoformat(),
                                    "duration_seconds": duration,
                                    "error": scrub_local_error(e),
                                    "attempts": attempt + 1,
                                }
                            )
                        raise

                    # Calculate backoff delay for retry
                    delay = min(
                        retry_policy.initial_delay
                        * (retry_policy.backoff_factor**attempt),
                        retry_policy.max_delay,
                    )
                    await asyncio.sleep(delay)

            # Should not reach here, but just in case
            if last_error:
                raise last_error
            return {"status": "unknown"}

    async def check_agent_health(self, agent_id: str) -> bool:
        """
        Check health of a specific agent.

        Args:
            agent_id: ID of agent to check

        Returns:
            True if agent is healthy, False otherwise
        """
        if agent_id not in self.agents:
            return False

        agent_metadata = self.agents[agent_id]
        agent = agent_metadata.agent

        try:
            # Simple health check - try to run with minimal input
            await asyncio.wait_for(agent.run(task="health_check"), timeout=5.0)

            # Update status to idle if successful
            agent_metadata.status = AgentStatus.ACTIVE
            return True

        except Exception:
            # Mark as failed
            agent_metadata.status = AgentStatus.UNHEALTHY
            agent_metadata.error_count += 1  # Use error_count consistently
            return False

    async def _route_task(self, task: str, available_agents: list[str]) -> str | None:
        """
        Route a task within an explicit candidate subset, returning the agent ID.

        ID-returning adapter over the SAME strategy helpers the public
        `route_task` uses, so each strategy has exactly ONE implementation.

        This method previously carried its own inline copy of all four
        strategies, and that duplication is what let the SEMANTIC copy drift
        onto a card attribute that does not exist. It read
        `getattr(a2a_card, "capabilities", [])`, but `A2AAgentCard` declares
        `primary_capabilities` / `secondary_capabilities` /
        `emerging_capabilities` and no `capabilities` at all — and for the dict
        card shape `getattr` never sees dict KEYS either. So the list was `[]`
        for BOTH shapes, the scoring loop never executed, the judge was invoked
        ZERO times, and every SEMANTIC route returned `available_agents[0]`:
        deterministic, unreasoned, and completely silent.

        That mattered beyond this method, because `_route_task` has no
        production caller — its only consumer is the #1981 regression suite. A
        vacuous oracle meant #1981's second-order assertions were passing
        against a fixture shape (`SimpleNamespace(capabilities=[...])`) that no
        production path can emit, so the guard on a closed CRITICAL was not
        actually guarding.

        Delegating removes the second implementation rather than patching the
        accessor in it: patching would fix this instance and leave the
        divergence that produced it.

        Args:
            task: Task description
            available_agents: List of candidate agent IDs

        Returns:
            Selected agent ID, or None when no candidate is ACTIVE.

        Raises:
            ReasoningDegradedError: SEMANTIC strategy only — every candidate
                capability degraded (#1981), so no ranking exists. Raised by
                `_route_semantic`, which now owns this contract outright.
        """
        if not available_agents:
            return None

        candidates = [
            (agent_id, self.agents[agent_id])
            for agent_id in available_agents
            if agent_id in self.agents
            and self.agents[agent_id].status == AgentStatus.ACTIVE
        ]

        if not candidates:
            return None

        strategy = self.config.default_routing_strategy
        if isinstance(strategy, str):
            strategy = RoutingStrategy(strategy)

        # Same dispatch as `route_task`, including the `enable_semantic_routing`
        # gate. That gate is NEW here: the inline copy ignored it, so disabling
        # semantic routing left this path still attempting it. Aligning is the
        # point of the delegation — a config flag that binds one routing entry
        # point and not the other is the same divergence in miniature.
        if strategy == RoutingStrategy.SEMANTIC and self.config.enable_semantic_routing:
            selected = await self._route_semantic(task, candidates)
        elif strategy == RoutingStrategy.LEAST_LOADED:
            selected = await self._route_least_loaded(candidates)
        elif strategy == RoutingStrategy.RANDOM:
            selected = await self._route_random(candidates)
        else:
            selected = await self._route_round_robin(candidates)

        if selected is None:
            # `_route_semantic` returns None on a genuine no-match (everything
            # scored, nothing scored above zero). Preserve the documented
            # `str | None` contract rather than inventing a positional pick.
            return None

        # The helpers hand back the (agent_id, metadata) tuple, so the ID is
        # carried directly. An earlier revision reverse-mapped the returned
        # agent OBJECT to an id by identity (`metadata.agent is selected`);
        # that is ambiguous when two ids share ONE agent instance, and it
        # silently collapsed round-robin to the first matching id
        # (['a1','a1','a1','a1'] where the deleted implementation gave
        # ['a1','a2','a1','a2']). Carrying the id removes the ambiguity
        # instead of tie-breaking it.
        return selected[0]

    async def _execute_agent_task(
        self, agent, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Internal execution helper for tests.

        Args:
            agent: Agent instance
            inputs: Task inputs

        Returns:
            Execution results
        """
        return await agent.run(**inputs)

    def _calculate_task_cost(self, agent_id: str, inputs: dict[str, Any]) -> float:
        """
        Calculate estimated cost for a task.

        Args:
            agent_id: ID of agent
            inputs: Task inputs

        Returns:
            Estimated cost in USD
        """
        # Simple cost estimation (can be enhanced)
        agent_metadata = self.agents.get(agent_id)
        if not agent_metadata:
            return 0.0

        # Estimate based on input size and agent type
        input_size = len(str(inputs))
        base_cost = 0.001  # $0.001 per task
        size_cost = input_size * 0.000001  # $0.000001 per character

        return base_cost + size_cost

    def get_execution_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """
        Get execution history.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of execution records
        """
        history = list(self._execution_history)
        if limit:
            history = history[-limit:]
        return history

    @staticmethod
    def _llm_node_config_for(agent: BaseAgent, task: str) -> dict[str, Any]:
        """Map one agent + its task onto ``LLMAgentNode``'s declared parameters.

        ``BaseAgent.to_workflow()`` is the SINGLE source of truth for the
        agent -> ``LLMAgentNode`` config mapping (provider, model,
        system_prompt, generation_config, provider_config, response_format,
        ungoverned). This method reuses it rather than re-deriving the mapping,
        so there is exactly ONE implementation of that contract.

        The task is conveyed as the node's ``messages`` parameter — the OpenAI
        conversation shape ``LLMAgentNode.get_parameters()`` declares and
        ``_prepare_conversation()`` consumes. It MUST NOT be passed as a
        ``task`` key: ``task`` is not a declared node parameter, so the runtime
        drops it with only a ``WARNING [NODE] Unknown parameter(s)`` line and
        the node then runs with ``messages=[]`` — an LLM call carrying NO
        instruction, whose mock/provider response still returns
        ``success: True``. ``execute_multi_agent_workflow`` counts that as a
        completed task, reporting a 100% success rate for a workflow that never
        conveyed any work (``rules/zero-tolerance.md`` Rule 2, "fake
        integration via a missing handoff field").

        Args:
            agent: Agent whose config supplies provider/model/system_prompt.
            task: Task description conveyed to the LLM as the user turn.

        Returns:
            Node config dict using only parameters ``LLMAgentNode`` declares.

        Raises:
            TypeError: ``agent`` does not expose ``to_workflow()`` (e.g. the
                deprecated ``kaizen.core.agents.Agent``, which is not a
                ``BaseAgent`` and exposes ``compile_to_workflow()`` instead).
            ValueError: ``agent.to_workflow()`` does not map onto exactly one
                ``LLMAgentNode``, so no level-parallel node can be built for it.
        """
        # Typed guard rather than an opaque `AttributeError: 'X' object has no
        # attribute 'to_workflow'` from the line below
        # (`rules/zero-tolerance.md` Rule 3a). `register_agent` is typed
        # `BaseAgent`; the deprecated `kaizen.core.agents.Agent` is a separate
        # class hierarchy with `compile_to_workflow()` and no `to_workflow()`.
        if not hasattr(agent, "to_workflow"):
            raise TypeError(
                f"Agent {getattr(agent, 'agent_id', agent)!r} of type "
                f"{type(agent).__name__} does not expose to_workflow(); "
                "OrchestrationRuntime requires a kaizen.core.base_agent."
                "BaseAgent to derive its LLMAgentNode configuration."
            )

        agent_workflow = agent.to_workflow()
        llm_specs = [
            spec
            for spec in agent_workflow.nodes.values()
            if spec.get("type") == "LLMAgentNode"
        ]
        if len(llm_specs) != 1:
            raise ValueError(
                f"Agent {agent.agent_id!r} does not map onto exactly one "
                f"LLMAgentNode (to_workflow() produced {len(llm_specs)}); "
                "OrchestrationRuntime cannot build a level-parallel workflow "
                "node for it."
            )

        # Copy: WorkflowBuilder.add_node stores the config dict BY REFERENCE and
        # to_workflow() memoizes its builder, so mutating it in place would
        # corrupt the agent's own workflow with this task's messages.
        node_config = dict(llm_specs[0].get("config") or {})

        # Provider/model are whatever `to_workflow()` resolved from the agent's
        # config and the environment. No hardcoded fallbacks here: a literal
        # provider would silently override an agent configured for another one
        # (`agent.config` exposes `llm_provider`, never `provider`, so the old
        # `hasattr(agent.config, "provider")` probe was ALWAYS False and every
        # agent was forced onto "openai"), and a literal model name is BLOCKED
        # by `rules/env-models.md`. An unresolvable provider stays None and
        # reaches LLMAgentNode's typed #1947 ConfigurationError, which the
        # caller's `error_handling` policy then reports per task.
        node_config["messages"] = [{"role": "user", "content": task}]
        return node_config

    def _build_workflow_from_agents(
        self, agents: list[BaseAgent], tasks: list[str], mode: str = "parallel"
    ) -> WorkflowBuilder:
        """
        Build Kailash workflow from list of agents for level-based parallelism.

        AsyncLocalRuntime Integration creates workflow where each agent becomes an LLMAgentNode.
        AsyncLocalRuntime enables true concurrent execution (10-100 agents).

        Args:
            agents: List of BaseAgent instances
            tasks: List of task descriptions (1:1 with agents)
            mode: Execution mode. Only ``"parallel"`` (no dependencies between
                agent nodes) is implemented; any other value raises.

        Returns:
            WorkflowBuilder instance with nodes for each agent

        Raises:
            ValueError: ``mode`` is not a supported mode, or an agent does not
                map onto exactly one ``LLMAgentNode``.

        Example:
            workflow = self._build_workflow_from_agents(
                agents=[agent1, agent2, agent3],
                tasks=["Task 1", "Task 2", "Task 3"],
                mode="parallel"
            )
            results, run_id = await self._async_runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )
        """
        # Fail loud on an unsupported mode. Two modes were previously
        # advertised in this docstring and neither ever worked:
        #
        #   "hybrid"     — its entire implementation was the comment
        #                  `# hybrid mode: implement batch-based connections
        #                  (future enhancement)`, so it silently behaved as
        #                  "parallel": a deferred-implementation placeholder
        #                  (`rules/zero-tolerance.md` Rule 2) presenting as a
        #                  silent fallback (Rule 3). No batch-size parameter
        #                  exists on this signature or on
        #                  OrchestrationRuntimeConfig to give it a meaning, so
        #                  it is rejected rather than guessed at.
        #
        #   "sequential" — chained via
        #                  `add_connection(prev, node_id, "output", "input")`,
        #                  but WorkflowBuilder.add_connection's signature is
        #                  (from_node, from_output, to_node, to_input). That
        #                  call therefore asked for a node literally named
        #                  "output" and raised WorkflowValidationError
        #                  ("Target node 'output' not found in workflow") on
        #                  every use since introduction. Correcting the
        #                  argument order alone does NOT make it work: the only
        #                  declared LLMAgentNode input that could receive a
        #                  prior agent's turn is `messages` (a list), while the
        #                  node emits `response` (a dict) — a field-mapped
        #                  connection between them would deliver a dict where
        #                  `_prepare_conversation()` extends a list, producing
        #                  garbage. Real chaining needs a transform node
        #                  between the two agents, which no caller specifies.
        #
        # Both call sites pass mode="parallel". Restricting the set removes no
        # working behaviour; it replaces a broken build and a silent alias with
        # one actionable error. A typo ("squential") is now loud too.
        if mode not in _WORKFLOW_BUILD_MODES:
            raise ValueError(
                f"Unsupported workflow build mode {mode!r}. "
                f"Supported modes: {sorted(_WORKFLOW_BUILD_MODES)}. "
                "('sequential' and 'hybrid' were previously documented but "
                "never implemented — see the comment in "
                "_build_workflow_from_agents.)"
            )

        workflow = WorkflowBuilder()

        # Create LLMAgentNode for each agent. parallel mode adds no
        # connections: the nodes execute independently, which is what gives
        # AsyncLocalRuntime its level-based concurrency.
        for i, (agent, task) in enumerate(zip(agents, tasks, strict=False)):
            node_id = f"agent_{i}_{agent.agent_id}"
            workflow.add_node(
                "LLMAgentNode",
                node_id,
                self._llm_node_config_for(agent, task),
            )

        return workflow

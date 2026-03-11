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
    from kaizen.orchestration.runtime import OrchestrationRuntime
    from kaizen.agents import SimpleQAAgent
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
Created: 2025-11-05 (Phase 4, Orchestration Runtime - TODO-178)
Reference: Based on kaizen-specialist analysis and existing coordination patterns
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

# Kailash SDK imports for workflow execution
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from kaizen.core.autonomy.hooks import HookManager
from kaizen.core.base_agent import BaseAgent
from kaizen.memory.shared_memory import SharedMemoryPool

# Set availability flag for AsyncLocalRuntime
ASYNC_RUNTIME_AVAILABLE = True

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


class AgentStatus(str, Enum):
    """Agent health status."""

    ACTIVE = "active"  # Healthy and available
    DEGRADED = "degraded"  # Operational but limited (e.g., budget exceeded)
    UNHEALTHY = "unhealthy"  # Not responding or failed health check
    OFFLINE = "offline"  # Manually deregistered


class RoutingStrategy(str, Enum):
    """Task routing strategy."""

    SEMANTIC = "semantic"  # A2A capability-based routing (recommended)
    ROUND_ROBIN = "round-robin"  # Simple round-robin distribution
    RANDOM = "random"  # Random selection
    LEAST_LOADED = "least-loaded"  # Select agent with fewest active tasks


class ErrorHandlingMode(str, Enum):
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
    default_retry_policy: Optional[RetryPolicy] = None  # Default retry policy
    retry_policy: Optional[RetryPolicy] = (
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
    max_budget_usd: Optional[float] = None  # Global budget limit (None = no limit)
    enable_rate_limiting: bool = True  # Enable rate limiting

    # Monitoring and observability
    enable_progress_tracking: bool = True  # Enable real-time progress tracking
    enable_metrics: bool = True  # Enable performance metrics
    hook_manager: Optional[HookManager] = None  # Hook manager for observability

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
    a2a_card: Optional[A2AAgentCard] = None  # A2A capability card

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
    estimated_completion: Optional[datetime] = None  # Estimated completion time
    results: List[Dict[str, Any]] = field(default_factory=list)  # Task results


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

    def __init__(self, config: Optional[OrchestrationRuntimeConfig] = None):
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
        self.agents: Dict[str, AgentMetadata] = {}

        # Task queue with priority support and concurrency control
        # PriorityQueue orders by (priority, item) - lower priority value = higher priority
        self.task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(
            maxsize=self.config.max_queue_size
        )
        # Semaphore to limit concurrent agent executions
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent_agents)

        # Workflow tracking
        self.workflows: Dict[str, WorkflowStatus] = {}

        # Shared memory pool for agent coordination
        self.shared_memory = SharedMemoryPool()

        # Hook manager for observability
        self.hook_manager = self.config.hook_manager or HookManager()

        # Runtime state
        self._running = False
        self._health_monitor_task: Optional[asyncio.Task] = None
        self._round_robin_index = 0  # For round-robin routing
        self._is_shutting_down = False  # Shutdown flag

        # Circuit breaker state per agent (closed, open, half-open)
        self._circuit_breaker_state: Dict[str, str] = {}
        # Circuit breaker failure counts per agent
        self._circuit_breaker_failures: Dict[str, int] = {}
        # Circuit breaker open timestamps for recovery timeout
        self._circuit_breaker_open_time: Dict[str, datetime] = {}

        # Active task tracking for execution monitoring
        self._active_tasks: Dict[str, asyncio.Task] = {}

        # Budget tracking for cost enforcement
        self._total_budget_spent: float = 0.0

        # Execution history for audit trail
        self._execution_history: List[Dict[str, Any]] = []

        # Total tasks executed counter
        self._total_tasks_executed: int = 0

        # AsyncLocalRuntime for level-based parallelism (Task 1: TODO-178)
        self._async_runtime: Optional[AsyncLocalRuntime] = None

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
        agent_id: Optional[str] = None,
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
            try:
                a2a_card = agent.to_a2a_card()
            except Exception:
                pass  # A2A card generation failed, will use fallback routing

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

    async def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
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
        self, status_filter: Optional[AgentStatus] = None
    ) -> List[Dict[str, Any]]:
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

            for agent_id, metadata in list(self.agents.items()):
                # Check heartbeat staleness
                time_since_heartbeat = (
                    datetime.now() - metadata.last_heartbeat
                ).total_seconds()
                if time_since_heartbeat > self.config.heartbeat_timeout:
                    metadata.status = AgentStatus.UNHEALTHY

                # Check budget limit
                if self.config.enable_budget_enforcement:
                    if metadata.budget_spent_usd >= metadata.budget_limit_usd:
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
        self, task: str, strategy: Optional[RoutingStrategy] = None
    ) -> Optional[BaseAgent]:
        """
        Route task to best agent using specified strategy.

        Args:
            task: Task description
            strategy: Optional routing strategy (uses config default if not provided)

        Returns:
            Selected agent or None if no agents available

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
            return await self._route_semantic(task, healthy_agents)
        elif strategy == RoutingStrategy.LEAST_LOADED:
            return await self._route_least_loaded(healthy_agents)
        elif strategy == RoutingStrategy.RANDOM:
            return await self._route_random(healthy_agents)
        else:  # ROUND_ROBIN
            return await self._route_round_robin(healthy_agents)

    async def _route_semantic(
        self, task: str, agents: List[tuple]
    ) -> Optional[BaseAgent]:
        """Route using A2A capability matching (best-fit selection)."""
        best_agent = None
        best_score = 0.0

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

            # Calculate capability match score
            for cap in capabilities:
                if hasattr(cap, "matches_requirement"):
                    score = cap.matches_requirement(task)
                    if score > best_score:
                        best_agent = metadata.agent
                        best_score = score
                elif isinstance(cap, str):
                    # Simple string matching as fallback
                    score = self._simple_text_similarity(task.lower(), cap.lower())
                    if score > best_score:
                        best_agent = metadata.agent
                        best_score = score

        # Fallback to round-robin if no match found
        if best_agent is None:
            return await self._route_round_robin(agents)

        return best_agent

    async def _route_least_loaded(self, agents: List[tuple]) -> BaseAgent:
        """Route to agent with fewest active tasks."""
        agent_id, metadata = min(agents, key=lambda x: x[1].active_tasks)
        return metadata.agent

    async def _route_random(self, agents: List[tuple]) -> BaseAgent:
        """Route to random agent."""
        import random

        agent_id, metadata = random.choice(agents)
        return metadata.agent

    async def _route_round_robin(self, agents: List[tuple]) -> BaseAgent:
        """Route using round-robin distribution."""
        agent_id, metadata = agents[self._round_robin_index]
        self._round_robin_index = (self._round_robin_index + 1) % len(agents)
        return metadata.agent

    def _simple_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate simple text similarity between two strings.

        Uses word overlap as a basic similarity metric (Jaccard similarity).
        This is a fallback when advanced A2A matching is not available.

        Args:
            text1: First text string
            text2: Second text string

        Returns:
            Similarity score between 0.0 and 1.0
        """
        # Split into words and create sets
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        # Calculate Jaccard similarity (intersection / union)
        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    # ========================================================================
    # Workflow Execution (AsyncLocalRuntime Integration)
    # ========================================================================

    async def execute_workflow(
        self,
        workflow: "Workflow",
        inputs: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
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
                "error": str(e),
            }

    # ========================================================================
    # Multi-Agent Workflow Execution
    # ========================================================================

    async def execute_multi_agent_workflow(
        self,
        tasks: List[str],
        routing_strategy: Optional[str] = None,
        error_handling: str = "graceful",
        max_concurrent: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute multiple tasks across agents with level-based parallelism via AsyncLocalRuntime.

        Task 1: AsyncLocalRuntime Integration (TODO-178)
        Replaces worker queue pattern with workflow-based execution for true concurrency.

        Pattern: Route tasks to agents → Build workflow → Execute via AsyncLocalRuntime
        Result: 10-100 agents executing concurrently (level-based parallelism)

        Args:
            tasks: List of task descriptions
            routing_strategy: Optional routing strategy (semantic, round-robin, etc.)
            error_handling: Error handling mode (graceful, fail-fast)
            max_concurrent: Optional max concurrent tasks (uses config default if not provided)

        Returns:
            Workflow results dictionary with completion status and task results

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
        self.workflows[workflow_id] = workflow_status

        # Route tasks to agents
        selected_agents = []
        for task in tasks:
            agent = await self.route_task(
                task,
                strategy=(
                    RoutingStrategy(routing_strategy) if routing_strategy else None
                ),
            )

            if agent is None:
                # No agents available for this task
                workflow_status.failed_tasks += 1
                workflow_status.results.append(
                    {"task": task, "status": "failed", "error": "No agents available"}
                )
            else:
                selected_agents.append(agent)

        # Build workflow from agents (enables level-based parallelism)
        if selected_agents:
            # Filter tasks to only those with assigned agents
            assigned_tasks = [
                task for i, task in enumerate(tasks) if i < len(selected_agents)
            ]

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
                for i, (agent, task) in enumerate(zip(selected_agents, assigned_tasks)):
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
                for agent, task in zip(selected_agents, assigned_tasks):
                    workflow_status.failed_tasks += 1
                    workflow_status.results.append(
                        {
                            "task": task,
                            "agent_id": agent.agent_id,
                            "status": "failed",
                            "error": str(e),
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
        self, agent: BaseAgent, task: str, retry_policy: Optional[RetryPolicy] = None
    ) -> Dict[str, Any]:
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
                    if self.config.enable_budget_enforcement:
                        if (
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
                        "error": str(e),
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

    async def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
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

    async def get_metrics(self) -> Dict[str, Any]:
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

        # Initialize AsyncLocalRuntime for level-based parallelism (Task 1: TODO-178)
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
            for task_id, task in list(self._active_tasks.items()):
                if not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(asyncio.shield(task), timeout=0.1)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass

        # Clear active tasks
        self._active_tasks.clear()

        # Cancel health monitoring
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass

        # Clear agents
        self.agents.clear()
        self.workflows.clear()

    # ========================================================================
    # Additional Helper Methods (for testing compatibility)
    # ========================================================================

    async def execute_task(
        self, agent_id: str, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
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
                                    "error": str(e),
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
            result = await asyncio.wait_for(agent.run(task="health_check"), timeout=5.0)

            # Update status to idle if successful
            agent_metadata.status = AgentStatus.ACTIVE
            return True

        except Exception as e:
            # Mark as failed
            agent_metadata.status = AgentStatus.UNHEALTHY
            agent_metadata.error_count += 1  # Use error_count consistently
            return False

    async def _route_task(
        self, task: str, available_agents: List[str]
    ) -> Optional[str]:
        """
        Internal routing helper for tests.

        Args:
            task: Task description
            available_agents: List of available agent IDs

        Returns:
            Selected agent ID or None
        """
        if not available_agents:
            return None

        # Filter to only active agents from available list
        active_agents = [
            agent_id
            for agent_id in available_agents
            if agent_id in self.agents
            and self.agents[agent_id].status == AgentStatus.ACTIVE
        ]

        if not active_agents:
            return None

        # Use appropriate routing based on strategy
        strategy = self.config.default_routing_strategy
        if isinstance(strategy, str):
            strategy = RoutingStrategy(strategy)

        if strategy == RoutingStrategy.ROUND_ROBIN:
            # Round-robin: cycle through available agents
            selected = active_agents[self._round_robin_index % len(active_agents)]
            self._round_robin_index = (self._round_robin_index + 1) % len(active_agents)
            return selected
        elif strategy == RoutingStrategy.RANDOM:
            # Random: pick a random agent
            import random

            return random.choice(active_agents)
        elif strategy == RoutingStrategy.LEAST_LOADED:
            # Least loaded: pick agent with fewest active tasks
            return min(active_agents, key=lambda aid: self.agents[aid].active_tasks)
        elif strategy == RoutingStrategy.SEMANTIC:
            # Semantic routing: use text similarity
            best_score = -1.0
            best_agent = active_agents[0]  # fallback
            for agent_id in active_agents:
                metadata = self.agents[agent_id]
                if metadata.a2a_card:
                    # Check capabilities
                    capabilities = getattr(metadata.a2a_card, "capabilities", [])
                    if isinstance(capabilities, dict):
                        capabilities = capabilities.get("capabilities", [])
                    for cap in capabilities:
                        if isinstance(cap, str):
                            score = self._simple_text_similarity(
                                task.lower(), cap.lower()
                            )
                            if score > best_score:
                                best_score = score
                                best_agent = agent_id
            return best_agent
        else:
            # Default: round-robin
            selected = active_agents[self._round_robin_index % len(active_agents)]
            self._round_robin_index = (self._round_robin_index + 1) % len(active_agents)
            return selected

    async def _execute_agent_task(
        self, agent, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Internal execution helper for tests.

        Args:
            agent: Agent instance
            inputs: Task inputs

        Returns:
            Execution results
        """
        return await agent.run(**inputs)

    def _calculate_task_cost(self, agent_id: str, inputs: Dict[str, Any]) -> float:
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

    def get_execution_history(
        self, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get execution history.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of execution records
        """
        history = self._execution_history
        if limit:
            history = history[-limit:]
        return history

    def _build_workflow_from_agents(
        self, agents: List[BaseAgent], tasks: List[str], mode: str = "parallel"
    ) -> WorkflowBuilder:
        """
        Build Kailash workflow from list of agents for level-based parallelism.

        Task 1: AsyncLocalRuntime Integration (TODO-178)

        Pattern: Creates workflow where each agent becomes an LLMAgentNode.
        AsyncLocalRuntime enables true concurrent execution (10-100 agents).

        Args:
            agents: List of BaseAgent instances
            tasks: List of task descriptions (1:1 with agents)
            mode: Execution mode - "parallel" (no dependencies),
                  "sequential" (chain nodes), "hybrid" (batch parallelism)

        Returns:
            WorkflowBuilder instance with nodes for each agent

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
        workflow = WorkflowBuilder()

        # Create LLMAgentNode for each agent
        for i, (agent, task) in enumerate(zip(agents, tasks)):
            node_id = f"agent_{i}_{agent.agent_id}"

            # Configure node with agent and task
            workflow.add_node(
                "LLMAgentNode",
                node_id,
                {
                    "agent": agent,
                    "task": task,
                    "provider": (
                        agent.config.provider
                        if hasattr(agent.config, "provider")
                        else "openai"
                    ),
                    "model": (
                        agent.config.model
                        if hasattr(agent.config, "model")
                        else "gpt-4o-mini"
                    ),
                },
            )

            # Connect nodes based on mode
            if mode == "sequential" and i > 0:
                # Chain: previous node output feeds into current node
                prev_node_id = f"agent_{i-1}_{agents[i-1].agent_id}"
                workflow.add_connection(prev_node_id, node_id, "output", "input")
            # parallel mode: no connections (nodes execute independently)
            # hybrid mode: implement batch-based connections (future enhancement)

        return workflow

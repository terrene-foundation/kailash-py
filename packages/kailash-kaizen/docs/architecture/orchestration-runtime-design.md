# OrchestrationRuntime API Design Document

**Version**: 1.0
**Date**: 2025-11-17
**Status**: Design Complete - Ready for Implementation
**Related**: TODO-178 Phase 1 Foundation

## Executive Summary

OrchestrationRuntime is a multi-agent workflow orchestration system built on AsyncLocalRuntime (Core SDK v0.10.4+). It enables concurrent execution of multiple agent workflows with unified observability, resource coordination, and enterprise features.

**Architecture**:
```
OrchestrationRuntime (NEW)
├── Execution Engine: AsyncLocalRuntime (EXISTING - v0.10.4)
├── State Management: DataFlow Integration (NEW)
├── Coordination: Nexus Integration (NEW)
└── Enterprise Features (NEW)
```

**Key Design Principles**:
1. **Composition Over Inheritance** - Wrap AsyncLocalRuntime, don't extend
2. **Async-First** - All methods use async/await (no sync wrappers)
3. **Shared Resources** - Single ResourceRegistry across all workflows
4. **Two-Level Concurrency** - Agent-level + Global-level limits
5. **Zero-Config** - Automatic MCP discovery, health monitoring, progress tracking

## 1. AsyncLocalRuntime Integration

### 1.1 Core Capabilities (v0.10.4+)

**Level-Based Parallelism**:
- Reference: `async_local.py:307-337`
- Computes execution levels for dependency-respecting concurrency
- Executes independent nodes in parallel within each level
- Pattern: `asyncio.gather(*tasks)` for level execution

**Semaphore Control**:
- Reference: `async_local.py:552-565`
- Lazy initialization: created on first access
- Limits concurrent node executions: `max_concurrent_nodes=10`
- Pattern: `async with self.execution_semaphore:`

**Thread Pool for Sync Nodes**:
- Reference: `async_local.py:1162-1171`
- ThreadPoolExecutor for backwards compatibility
- Pattern: `await loop.run_in_executor(self.thread_pool, execute_sync)`

**ExecutionContext**:
- Reference: `async_local.py:87-250`
- Resource access via ResourceRegistry
- Connection lifecycle management
- Cleanup guarantees via context manager
- Metrics collection (node durations, resource usage)

**Return Structure**:
- Reference: `async_local.py:647-758`
- Consistent: `(results, run_id)` tuple
- results: Dict[str, Any] - node_id → output mapping
- run_id: str - unique execution identifier

### 1.2 Configuration Parameters

**AsyncLocalRuntime Constructor**:
```python
AsyncLocalRuntime(
    resource_registry: Optional[ResourceRegistry] = None,
    max_concurrent_nodes: int = 10,           # Agent-level concurrency
    enable_analysis: bool = True,             # Workflow optimization
    enable_profiling: bool = True,            # Performance metrics
    thread_pool_size: int = 4,                # Sync node thread pool
    execution_timeout: Optional[int] = 300,   # Timeout in seconds
    **kwargs,                                 # BaseRuntime parameters
)
```

**Inherited from BaseRuntime** (29 parameters):
- `debug`, `enable_cycles`, `enable_async` (forced True)
- `connection_validation`: "off"/"warn"/"strict"
- `conditional_execution`: "route_data"/"skip_branches"
- `enable_monitoring`, `enable_security`, `enable_audit`
- Circuit breaker, retry policy, connection pool configs

## 2. OrchestrationRuntime API Design

### 2.1 Core Architecture

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import asyncio
from datetime import datetime

from kailash.runtime import AsyncLocalRuntime, ResourceRegistry
from kaizen.core.base_agent import BaseAgent
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.orchestration.enums import AgentStatus, RoutingStrategy, HealthStatus


@dataclass
class AgentMetadata:
    """Metadata for registered agent."""
    agent_id: str
    agent: BaseAgent
    a2a_card: Dict[str, Any]  # Agent-to-Agent card for routing
    max_concurrency: int = 5
    budget_limit_usd: float = 1.0

    # Runtime state
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    budget_spent_usd: float = 0.0
    total_execution_time: float = 0.0
    avg_execution_time: float = 0.0
    error_count: int = 0
    last_health_check: Optional[datetime] = None
    status: AgentStatus = AgentStatus.HEALTHY


@dataclass
class OrchestrationRuntimeConfig:
    """Configuration for OrchestrationRuntime."""
    max_concurrent_agents: int = 10        # Agent-level concurrency
    max_concurrent_workflows: int = 20     # Global workflow concurrency
    enable_progress_tracking: bool = True
    enable_health_monitoring: bool = True
    health_check_interval: float = 60.0    # seconds
    execution_timeout: int = 300           # seconds
    enable_circuit_breakers: bool = True
    error_threshold: float = 0.5           # 50% error rate
    circuit_reset_timeout: float = 60.0    # seconds

    # Hook manager for observability
    hook_manager: Optional[Any] = None     # HookManager instance


class OrchestrationRuntime:
    """
    Multi-agent orchestration runtime built on AsyncLocalRuntime.

    Features:
    - Concurrent multi-agent workflow execution
    - Semantic routing to specialist agents
    - Budget tracking and enforcement
    - Health monitoring and circuit breakers
    - Unified observability via hooks
    - Resource coordination across agents

    Architecture:
        OrchestrationRuntime
        ├── AsyncLocalRuntime (workflow execution)
        ├── AgentRegistry (agent lifecycle)
        ├── TaskQueue (task distribution)
        ├── ResourceCoordinator (budget, limits)
        └── MetricsCollector (observability)
    """

    def __init__(
        self,
        config: OrchestrationRuntimeConfig,
        resource_registry: Optional[ResourceRegistry] = None,
        shared_memory: Optional[SharedMemoryPool] = None,
    ):
        """
        Initialize OrchestrationRuntime.

        Args:
            config: Runtime configuration
            resource_registry: Shared resource registry (database pools, caches)
            shared_memory: Shared memory pool for agent coordination
        """
        self.config = config

        # Create AsyncLocalRuntime (shared execution engine)
        self.async_runtime = AsyncLocalRuntime(
            resource_registry=resource_registry,
            max_concurrent_nodes=config.max_concurrent_agents,
            execution_timeout=config.execution_timeout,
            enable_analysis=True,
            enable_profiling=True,
        )

        # Agent registry
        self.agents: Dict[str, AgentMetadata] = {}

        # Task queue
        self.task_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

        # Active workflows tracking
        self.active_workflows: Dict[str, Any] = {}

        # Concurrency control (global)
        self.workflow_semaphore = asyncio.Semaphore(config.max_concurrent_workflows)

        # Shared memory for agent coordination
        self.shared_memory = shared_memory

        # Metrics collector
        self.metrics_collector = MetricsCollector() if config.enable_progress_tracking else None

        # Health monitoring
        self.health_monitor = None
        if config.enable_health_monitoring:
            self.health_monitor = HealthMonitor(
                check_interval=config.health_check_interval,
                runtime=self,
            )

        # Circuit breakers
        self.circuit_breakers: Dict[str, CircuitBreakerState] = {}

        # Hook manager for observability
        self.hook_manager = config.hook_manager

    # === Agent Registration ===

    async def register_agent(
        self,
        agent: BaseAgent,
        max_concurrency: int = 5,
        budget_limit_usd: float = 1.0,
    ) -> str:
        """
        Register agent with orchestration runtime.

        Args:
            agent: BaseAgent instance to register
            max_concurrency: Maximum concurrent tasks for this agent
            budget_limit_usd: Budget limit in USD

        Returns:
            Agent ID for reference
        """
        import uuid

        agent_id = f"agent_{uuid.uuid4().hex[:8]}"

        # Extract A2A card for semantic routing
        a2a_card = self._extract_a2a_card(agent)

        # Create metadata
        self.agents[agent_id] = AgentMetadata(
            agent_id=agent_id,
            agent=agent,
            a2a_card=a2a_card,
            max_concurrency=max_concurrency,
            budget_limit_usd=budget_limit_usd,
            status=AgentStatus.HEALTHY,
        )

        return agent_id

    def _extract_a2a_card(self, agent: BaseAgent) -> Dict[str, Any]:
        """Extract Agent-to-Agent capability card."""
        return {
            "name": getattr(agent, "name", "unknown"),
            "description": getattr(agent, "description", ""),
            "capabilities": getattr(agent, "capabilities", []),
            "specialization": getattr(agent, "specialization", "general"),
        }

    # === Multi-Agent Workflow Execution ===

    async def execute_multi_agent_workflow(
        self,
        tasks: List[Any],
        routing_strategy: RoutingStrategy = RoutingStrategy.SEMANTIC,
    ) -> Dict[str, Any]:
        """
        Execute multi-agent workflow with task distribution.

        Strategy:
        1. Route tasks to agents (semantic/round-robin/least-loaded)
        2. Create workflow for each agent (WorkflowBuilder)
        3. Execute workflows concurrently (AsyncLocalRuntime)
        4. Collect and aggregate results

        Args:
            tasks: List of tasks to distribute
            routing_strategy: Routing strategy to use

        Returns:
            Aggregated results from all agents
        """
        import uuid

        workflow_id = f"workflow_{uuid.uuid4().hex[:8]}"

        # Route tasks to agents
        task_assignments = await self._route_tasks(tasks, routing_strategy)

        # Create workflows for each agent
        agent_workflows = []
        for agent_id, agent_tasks in task_assignments.items():
            workflow = self._create_agent_workflow(agent_id, agent_tasks)
            agent_workflows.append((agent_id, workflow))

        # Execute workflows concurrently with global semaphore
        async with self.workflow_semaphore:
            results = await asyncio.gather(*[
                self._execute_agent_workflow(agent_id, workflow)
                for agent_id, workflow in agent_workflows
            ])

        return self._aggregate_results(results)

    async def _execute_agent_workflow(
        self, agent_id: str, workflow
    ) -> Dict[str, Any]:
        """
        Execute single agent workflow using AsyncLocalRuntime.

        Integration Points:
        - Uses AsyncLocalRuntime.execute_workflow_async()
        - Tracks agent-level concurrency
        - Enforces budget limits
        - Records metrics
        - Circuit breaker protection
        """
        import time

        agent_metadata = self.agents[agent_id]

        # Budget enforcement
        if agent_metadata.budget_spent_usd >= agent_metadata.budget_limit_usd:
            raise BudgetExceededError(
                f"Agent {agent_id} exceeded budget: "
                f"${agent_metadata.budget_spent_usd:.3f} / ${agent_metadata.budget_limit_usd:.3f}"
            )

        # Concurrency limit
        if agent_metadata.active_tasks >= agent_metadata.max_concurrency:
            raise ConcurrencyLimitError(
                f"Agent {agent_id} at max concurrency: {agent_metadata.active_tasks}"
            )

        # Update state
        agent_metadata.active_tasks += 1
        start_time = time.time()

        try:
            # Execute via AsyncLocalRuntime
            results, run_id = await self.async_runtime.execute_workflow_async(
                workflow,
                inputs={}
            )

            # Update metrics
            execution_time = time.time() - start_time
            agent_metadata.completed_tasks += 1
            agent_metadata.total_execution_time += execution_time
            agent_metadata.avg_execution_time = (
                agent_metadata.total_execution_time / agent_metadata.completed_tasks
            )

            return {
                "agent_id": agent_id,
                "results": results,
                "run_id": run_id,
                "execution_time": execution_time,
            }

        except Exception as e:
            agent_metadata.failed_tasks += 1
            agent_metadata.error_count += 1
            raise

        finally:
            agent_metadata.active_tasks -= 1

    # === Task Routing ===

    async def _route_tasks(
        self, tasks: List[Any], strategy: RoutingStrategy
    ) -> Dict[str, List[Any]]:
        """Route tasks to agents based on strategy."""
        if strategy == RoutingStrategy.SEMANTIC:
            return await self._semantic_routing(tasks)
        elif strategy == RoutingStrategy.ROUND_ROBIN:
            return self._round_robin_routing(tasks)
        elif strategy == RoutingStrategy.LEAST_LOADED:
            return self._least_loaded_routing(tasks)
        else:
            raise ValueError(f"Unknown routing strategy: {strategy}")

    async def _semantic_routing(self, tasks: List[Any]) -> Dict[str, List[Any]]:
        """Route tasks based on agent capabilities (semantic matching)."""
        # TODO: Implement semantic matching using A2A cards
        pass

    def _round_robin_routing(self, tasks: List[Any]) -> Dict[str, List[Any]]:
        """Round-robin task distribution."""
        assignments = {agent_id: [] for agent_id in self.agents.keys()}
        agent_ids = list(self.agents.keys())

        for i, task in enumerate(tasks):
            agent_id = agent_ids[i % len(agent_ids)]
            assignments[agent_id].append(task)

        return assignments

    def _least_loaded_routing(self, tasks: List[Any]) -> Dict[str, List[Any]]:
        """Route to least loaded agents."""
        assignments = {agent_id: [] for agent_id in self.agents.keys()}

        for task in tasks:
            # Find agent with minimum active tasks
            least_loaded = min(
                self.agents.values(),
                key=lambda a: a.active_tasks
            )
            assignments[least_loaded.agent_id].append(task)

        return assignments

    # === Workflow Building ===

    def _create_agent_workflow(self, agent_id: str, tasks: List[Any]):
        """Create workflow for agent execution."""
        from kailash.workflow.builder import WorkflowBuilder

        # TODO: Convert tasks to workflow nodes
        builder = WorkflowBuilder()
        # ... workflow construction
        return builder.build()

    # === Result Aggregation ===

    def _aggregate_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate results from multiple agents."""
        return {
            "workflow_results": results,
            "total_agents": len(results),
            "successful": sum(1 for r in results if "error" not in r),
            "failed": sum(1 for r in results if "error" in r),
        }

    # === Health Monitoring ===

    async def start_health_monitoring(self):
        """Start background health monitoring."""
        if self.health_monitor:
            await self.health_monitor.start()

    async def stop_health_monitoring(self):
        """Stop health monitoring."""
        if self.health_monitor:
            await self.health_monitor.stop()

    # === Cleanup ===

    async def cleanup(self):
        """Cleanup runtime resources."""
        # Stop health monitoring
        await self.stop_health_monitoring()

        # Cleanup AsyncLocalRuntime
        if hasattr(self.async_runtime, 'cleanup'):
            await self.async_runtime.cleanup()


# === Supporting Classes ===

@dataclass
class CircuitBreakerState:
    """Circuit breaker state for agent."""
    error_count: int = 0
    request_count: int = 0
    is_open: bool = False
    last_failure_time: Optional[datetime] = None


class MetricsCollector:
    """Collect and aggregate metrics across agents."""

    def __init__(self):
        self.metrics: Dict[str, Any] = {}

    def record_execution(self, agent_id: str, duration: float, success: bool):
        """Record execution metrics."""
        if agent_id not in self.metrics:
            self.metrics[agent_id] = {
                "executions": 0,
                "successes": 0,
                "failures": 0,
                "total_duration": 0.0,
            }

        self.metrics[agent_id]["executions"] += 1
        self.metrics[agent_id]["total_duration"] += duration

        if success:
            self.metrics[agent_id]["successes"] += 1
        else:
            self.metrics[agent_id]["failures"] += 1


class HealthMonitor:
    """Background health monitoring for agents."""

    def __init__(self, check_interval: float, runtime: OrchestrationRuntime):
        self.check_interval = check_interval
        self.runtime = runtime
        self.task: Optional[asyncio.Task] = None

    async def start(self):
        """Start health monitoring loop."""
        self.task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        """Stop health monitoring."""
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self):
        """Health check loop."""
        while True:
            try:
                await asyncio.sleep(self.check_interval)
                await self._check_all_agents()
            except asyncio.CancelledError:
                break

    async def _check_all_agents(self):
        """Check health of all registered agents."""
        for agent_metadata in self.runtime.agents.values():
            # Update last health check time
            agent_metadata.last_health_check = datetime.now()

            # Check error rate
            if agent_metadata.completed_tasks > 0:
                error_rate = agent_metadata.error_count / agent_metadata.completed_tasks
                if error_rate > 0.5:
                    agent_metadata.status = AgentStatus.DEGRADED


# === Exceptions ===

class BudgetExceededError(Exception):
    """Raised when agent exceeds budget limit."""
    pass


class ConcurrencyLimitError(Exception):
    """Raised when agent hits concurrency limit."""
    pass
```

### 2.2 Resource Sharing Pattern

```python
class ResourceCoordinator:
    """Coordinate resource usage across agents."""

    def __init__(self, resource_registry: ResourceRegistry):
        self.resource_registry = resource_registry
        self.resource_locks: Dict[str, asyncio.Lock] = {}
        self.resource_usage: Dict[str, int] = defaultdict(int)

    async def acquire_resource(self, resource_name: str, agent_id: str) -> Any:
        """Acquire resource with coordination."""
        self.resource_usage[resource_name] += 1
        resource = await self.resource_registry.get_resource(resource_name)
        return resource

    async def release_resource(self, resource_name: str, agent_id: str):
        """Release resource."""
        self.resource_usage[resource_name] -= 1
```

### 2.3 State Management Integration

```python
class StateManager:
    """Manage agent state across workflows."""

    def __init__(self, shared_memory: SharedMemoryPool):
        self.shared_memory = shared_memory
        self.state_locks: Dict[str, asyncio.Lock] = {}

    async def get_agent_state(self, agent_id: str) -> Dict[str, Any]:
        """Get agent state from shared memory."""
        state = await self.shared_memory.get(f"agent_state:{agent_id}")
        return state or {}

    async def update_agent_state(self, agent_id: str, updates: Dict[str, Any]):
        """Update agent state atomically."""
        async with self._get_lock(agent_id):
            current_state = await self.get_agent_state(agent_id)
            current_state.update(updates)
            await self.shared_memory.set(f"agent_state:{agent_id}", current_state)
```

## 3. Implementation Plan

### Phase 1: Foundation (Week 1)

**Subtask 1.1: Design OrchestrationRuntime API** ✅ COMPLETE
- Consulted sdk-navigator on AsyncLocalRuntime capabilities
- Documented API design in this file
- Defined integration points with AsyncLocalRuntime

**Subtask 1.2: Implement Core Runtime** (3 days)
- Create `src/kaizen/orchestration/runtime.py`
- Implement OrchestrationRuntime class
- Agent registration with metadata tracking
- Basic workflow execution via AsyncLocalRuntime wrapper

**Subtask 1.3: Add Resource Coordination** (2 days)
- Shared ResourceRegistry pattern
- Two-level concurrency control (agent + global)
- Budget tracking and enforcement

### Phase 2: Agent Coordination (Week 2)

**Subtask 2.1: Task Routing** (3 days)
- Round-robin routing
- Least-loaded routing
- Semantic routing (A2A card matching)

**Subtask 2.2: Health Monitoring** (2 days)
- Background health check loop
- Circuit breaker pattern
- Status tracking (HEALTHY/DEGRADED/OFFLINE)

### Phase 3: Enterprise Features (Week 3)

**Subtask 3.1: Observability Integration** (2 days)
- Hook integration for unified monitoring
- Metrics collection and aggregation
- Progress tracking

**Subtask 3.2: DataFlow/Nexus Integration** (3 days)
- State persistence via DataFlow
- Distributed coordination via Nexus

## 4. Testing Strategy

**Tier 2 Integration Tests**:
- Agent registration and lifecycle
- Workflow execution via AsyncLocalRuntime
- Resource coordination (ResourceRegistry)
- Budget enforcement
- Health monitoring

**Tier 3 E2E Tests**:
- Multi-agent workflow execution (10+ agents)
- Semantic routing accuracy
- Circuit breaker behavior
- State persistence across restarts
- 10,000 tasks/hour throughput

## 5. Success Criteria

1. ✅ **AsyncLocalRuntime Integration**: Wrapper pattern with all capabilities preserved
2. ✅ **API Design**: Clean, intuitive, async-first
3. ✅ **Resource Sharing**: Single ResourceRegistry, no connection exhaustion
4. ✅ **Concurrency Control**: Two-level limits (agent + global)
5. ✅ **State Management**: SharedMemoryPool integration via ExecutionContext

## 6. References

**Core SDK**:
- `async_local.py`: AsyncLocalRuntime implementation (1356 lines)
- `local.py`: LocalRuntime with mixins (4570 lines)
- `builder.py`: WorkflowBuilder API (1307 lines)

**Kaizen**:
- `src/kaizen/orchestration/runtime.py`: Current implementation
- `src/kaizen/orchestration/registry.py`: AgentRegistry
- `test_orchestration_runtime_e2e.py`: E2E tests

**Examples**:
- `examples/orchestration/orchestration-patterns/`: Reference patterns
- `test_async_runtime_integration.py`: AsyncLocalRuntime integration tests

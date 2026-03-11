"""
SupervisorWorkerPattern - Multi-Agent Coordination Pattern

Production-ready supervisor-worker pattern with centralized task delegation.
Provides zero-config factory function with progressive configuration support.

Pattern Components:
- SupervisorAgent: Breaks requests into tasks, delegates, aggregates results
- WorkerAgent: Executes assigned tasks independently
- CoordinatorAgent: Monitors progress and tracks active workers
- SupervisorWorkerPattern: Pattern container with convenience methods

Usage:
    # Zero-config
    from kaizen.orchestration.patterns import create_supervisor_worker_pattern

    pattern = create_supervisor_worker_pattern()
    tasks = pattern.delegate("Process 100 documents")
    results = pattern.aggregate_results(tasks[0]["request_id"])

    # Progressive configuration
    pattern = create_supervisor_worker_pattern(
        num_workers=5,
        model="gpt-4",
        temperature=0.7
    )

Architecture:
    User Request → SupervisorAgent (delegates)
                → SharedMemoryPool (writes tasks)
                → WorkerAgents (read & execute)
                → SharedMemoryPool (write results)
                → SupervisorAgent (aggregates)
                → Final Result

Author: Kaizen Framework Team
Created: 2025-10-04 (Phase 3, Multi-Agent Patterns)
Reference: examples/2-multi-agent/supervisor-worker/workflow.py
"""

import json
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.orchestration.patterns.base_pattern import BaseMultiAgentPattern
from kaizen.signatures import InputField, OutputField, Signature

# A2A imports for capability-based agent selection
try:
    from kaizen.nodes.ai.a2a import A2AAgentCard, Capability

    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False
    Capability = None
    A2AAgentCard = None


# ============================================================================
# Signature Definitions
# ============================================================================


class TaskDelegationSignature(Signature):
    """Signature for supervisor task delegation."""

    request: str = InputField(desc="User request to process")
    num_tasks: int = InputField(desc="Number of tasks to create", default=3)

    tasks: str = OutputField(desc="Tasks to delegate (JSON list)", default="[]")
    delegation_plan: str = OutputField(desc="Delegation plan", default="")


class TaskExecutionSignature(Signature):
    """Signature for worker task execution."""

    task_description: str = InputField(desc="Task to execute")
    task_id: str = InputField(desc="Unique task identifier")

    result: str = OutputField(desc="Task execution result")
    status: str = OutputField(desc="Execution status", default="completed")


class ResultAggregationSignature(Signature):
    """Signature for supervisor result aggregation."""

    task_results: str = InputField(desc="All task results (JSON list)")
    request: str = InputField(desc="Original request")

    final_result: str = OutputField(desc="Aggregated final result")
    summary: str = OutputField(desc="Summary of results")


class ProgressMonitoringSignature(Signature):
    """Signature for coordinator progress monitoring."""

    insights: str = InputField(desc="All insights from shared memory (JSON list)")

    active_workers: str = OutputField(desc="Active workers (JSON list)", default="[]")
    pending_tasks: int = OutputField(desc="Number of pending tasks", default=0)
    completed_tasks: int = OutputField(desc="Number of completed tasks", default=0)


# ============================================================================
# Agent Implementations
# ============================================================================


class SupervisorAgent(BaseAgent):
    """
    SupervisorAgent: Breaks requests into tasks, delegates to workers, aggregates results.

    Responsibilities:
    - Receive user requests
    - Break requests into discrete tasks
    - Delegate tasks to available workers
    - Monitor task completion
    - Aggregate results from workers
    - Handle failures and reassignments

    Shared Memory Behavior:
    - Writes tasks with tags: ["task", "pending", request_id, worker_id]
    - Reads results with tags: ["result", "completed", request_id]
    - Importance: 0.8 for tasks, 0.9 for failures
    - Segments: "tasks", "results", "errors"
    """

    def __init__(
        self, config: BaseAgentConfig, shared_memory: SharedMemoryPool, agent_id: str
    ):
        """
        Initialize SupervisorAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
        """
        super().__init__(
            config=config,
            signature=TaskDelegationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        # A2A capability matching is available via worker to_a2a_card() method
        self.a2a_coordinator = "capability_matching" if A2A_AVAILABLE else None

    def select_worker_for_task(
        self, task: str, available_workers: List[BaseAgent], return_score: bool = False
    ) -> Any:
        """
        Select best worker for task using A2A capability matching.

        Replaces manual hardcoded selection logic with semantic capability matching
        using Google A2A protocol. Falls back to round-robin if A2A unavailable.

        Args:
            task: Task description
            available_workers: List of available worker agents
            return_score: If True, return dict with worker and score

        Returns:
            Selected worker agent, or dict with worker and score if return_score=True
        """
        if not available_workers:
            return None if not return_score else {"worker": None, "score": 0.0}

        # Try A2A capability matching first
        if self.a2a_coordinator and A2A_AVAILABLE:
            try:
                # Generate A2A cards for all workers
                worker_cards = []
                for worker in available_workers:
                    try:
                        if hasattr(worker, "to_a2a_card"):
                            card = worker.to_a2a_card()
                            worker_cards.append((worker, card))
                    except Exception:
                        # Skip workers that can't generate A2A cards
                        continue

                # Find best match using A2A semantic matching
                if worker_cards:
                    best_worker = None
                    best_score = 0.0

                    for worker, card in worker_cards:
                        # Calculate capability match score
                        score = 0.0
                        for capability in card.primary_capabilities:
                            capability_score = capability.matches_requirement(task)
                            if capability_score > score:
                                score = capability_score

                        # Track best match
                        if score > best_score:
                            best_score = score
                            best_worker = worker

                    if best_worker:
                        if return_score:
                            return {"worker": best_worker, "score": best_score}
                        return best_worker

            except Exception:
                # Fall through to fallback selection
                pass

        # Fallback: Round-robin selection (backward compatible)
        selected_worker = available_workers[0]

        if return_score:
            return {"worker": selected_worker, "score": 0.5}
        return selected_worker

    def delegate(
        self,
        request: str,
        available_workers: Optional[List[str]] = None,
        num_tasks: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Delegate request to workers by breaking into tasks.

        Args:
            request: User request to process
            available_workers: List of available worker IDs
            num_tasks: Number of tasks to create

        Returns:
            List of tasks created and delegated
        """
        # Handle edge case: num_tasks = 0
        if num_tasks == 0:
            return []

        # Generate request ID
        request_id = f"request_{uuid.uuid4().hex[:8]}"

        # Execute task delegation via base agent
        result = self.run(
            request=request, num_tasks=num_tasks, session_id=f"delegate_{request_id}"
        )

        # Parse tasks
        tasks_str = result.get("tasks", "[]")
        if isinstance(tasks_str, str):
            try:
                tasks = json.loads(tasks_str)
            except json.JSONDecodeError:
                # Create default tasks if parsing fails
                tasks = [
                    {
                        "task_id": f"task_{i}",
                        "description": f"Subtask {i} of: {request}",
                    }
                    for i in range(num_tasks)
                ]
        else:
            tasks = tasks_str

        # Ensure we have correct number of tasks
        if len(tasks) < num_tasks:
            # Pad with default tasks
            for i in range(len(tasks), num_tasks):
                tasks.append(
                    {
                        "task_id": f"task_{i}",
                        "description": f"Subtask {i} of: {request}",
                    }
                )
        elif len(tasks) > num_tasks:
            # Truncate to requested number of tasks
            tasks = tasks[:num_tasks]

        # Normalize tasks to ensure they're dictionaries
        normalized_tasks = []
        for i, task in enumerate(tasks):
            if isinstance(task, str):
                # Convert string to dict
                normalized_tasks.append({"task_id": f"task_{i}", "description": task})
            elif isinstance(task, dict):
                normalized_tasks.append(task)
            else:
                # Handle unexpected type
                normalized_tasks.append(
                    {"task_id": f"task_{i}", "description": str(task)}
                )

        tasks = normalized_tasks

        # Assign tasks to workers (round-robin)
        if available_workers is None:
            available_workers = ["worker_1", "worker_2", "worker_3"]

        for i, task in enumerate(tasks):
            task["task_id"] = task.get("task_id", f"task_{uuid.uuid4().hex[:8]}")
            task["assigned_to"] = available_workers[i % len(available_workers)]
            task["request_id"] = request_id

            # Write task to shared memory
            if self.shared_memory:
                self.shared_memory.write_insight(
                    {
                        "agent_id": self.agent_id,
                        "content": json.dumps(task),
                        "tags": ["task", "pending", request_id, task["assigned_to"]],
                        "importance": 0.8,
                        "segment": "tasks",
                        "metadata": {
                            "task_id": task["task_id"],
                            "assigned_to": task["assigned_to"],
                            "request_id": request_id,
                        },
                    }
                )

        return tasks

    def aggregate_results(self, request_id: str) -> Dict[str, Any]:
        """
        Aggregate results from workers for a request.

        Args:
            request_id: Request identifier

        Returns:
            Aggregated results
        """
        # Read results from shared memory
        results = []
        if self.shared_memory:
            results = self.shared_memory.read_relevant(
                agent_id=self.agent_id,
                tags=["result", "completed", request_id],
                exclude_own=True,
                limit=50,
            )

        # Extract task results
        task_results = []
        for insight in results:
            metadata = insight.get("metadata", {})
            task_results.append(
                {
                    "task_id": metadata.get("task_id"),
                    "result": insight.get("content"),
                    "worker": insight.get("agent_id"),
                }
            )

        # Execute aggregation via base agent (switch signature temporarily)
        original_signature = self.signature
        self.signature = ResultAggregationSignature()

        result = self.run(
            task_results=json.dumps(task_results),
            request="Original request",
            session_id=f"aggregate_{request_id}",
        )

        # Switch back
        self.signature = original_signature

        return {
            "final_result": result.get("final_result", ""),
            "summary": result.get("summary", ""),
            "task_results": task_results,
        }

    def check_all_tasks_completed(self, request_id: str) -> bool:
        """
        Check if all tasks for a request are completed.

        Args:
            request_id: Request identifier

        Returns:
            True if all tasks completed, False otherwise
        """
        if not self.shared_memory:
            return False

        # Count pending tasks
        pending = self.shared_memory.read_relevant(
            agent_id=self.agent_id,
            tags=["task", "pending", request_id],
            exclude_own=False,
        )

        # Count completed tasks
        completed = self.shared_memory.read_relevant(
            agent_id=self.agent_id,
            tags=["result", "completed", request_id],
            exclude_own=True,
        )

        # All complete if no pending tasks and we have results
        return len(pending) > 0 and len(completed) >= len(pending)

    def check_failures(self, request_id: str) -> List[Dict[str, Any]]:
        """
        Check for failed tasks.

        Args:
            request_id: Request identifier

        Returns:
            List of failed tasks
        """
        if not self.shared_memory:
            return []

        failures = self.shared_memory.read_relevant(
            agent_id=self.agent_id,
            tags=["error", "failed", request_id],
            exclude_own=True,
            limit=50,
        )

        return failures

    def reassign_task(self, task: Dict[str, Any], new_worker: str) -> Dict[str, Any]:
        """
        Reassign a task to a different worker.

        Args:
            task: Task to reassign
            new_worker: New worker ID

        Returns:
            Updated task
        """
        task["assigned_to"] = new_worker

        # Write reassigned task to shared memory
        if self.shared_memory:
            self.shared_memory.write_insight(
                {
                    "agent_id": self.agent_id,
                    "content": json.dumps(task),
                    "tags": ["task", "pending", task.get("request_id", ""), new_worker],
                    "importance": 0.9,  # Higher importance for reassigned tasks
                    "segment": "tasks",
                    "metadata": {
                        "task_id": task["task_id"],
                        "assigned_to": new_worker,
                        "request_id": task.get("request_id", ""),
                        "reassigned": True,
                    },
                }
            )

        return task


class WorkerAgent(BaseAgent):
    """
    WorkerAgent: Executes assigned tasks independently.

    Responsibilities:
    - Read assigned tasks from shared memory
    - Execute tasks independently
    - Write results to shared memory
    - Mark tasks as completed
    - Report failures

    Shared Memory Behavior:
    - Reads tasks with tags: ["task", "pending", agent_id]
    - Writes results with tags: ["result", "completed", request_id]
    - Importance: 0.8 for results, 0.9 for errors
    - Segments: "results", "errors"
    """

    def __init__(
        self, config: BaseAgentConfig, shared_memory: SharedMemoryPool, agent_id: str
    ):
        """
        Initialize WorkerAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
        """
        super().__init__(
            config=config,
            signature=TaskExecutionSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

    def get_assigned_tasks(self) -> List[Dict[str, Any]]:
        """
        Get tasks assigned to this worker.

        Returns:
            List of assigned tasks
        """
        if not self.shared_memory:
            return []

        # Read tasks assigned to this worker
        # Use only worker_id as tag to filter specifically for this worker
        insights = self.shared_memory.read_relevant(
            agent_id=self.agent_id,
            tags=[self.agent_id],  # Only filter by worker ID to be specific
            exclude_own=True,
            limit=10,
        )

        tasks = []
        for insight in insights:
            content = insight.get("content", "{}")
            if isinstance(content, str):
                try:
                    task = json.loads(content)
                    # Double-check it's a task and assigned to this worker
                    if task.get("assigned_to") == self.agent_id:
                        tasks.append(task)
                except json.JSONDecodeError:
                    continue

        return tasks

    def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task and write result to shared memory.

        Args:
            task: Task to execute

        Returns:
            Task result
        """
        task_id = task.get("task_id", "unknown")
        description = task.get("description", "")
        request_id = task.get("request_id", "")

        # Execute task via base agent
        result = self.run(
            task_description=description,
            task_id=task_id,
            session_id=f"execute_{task_id}",
        )

        # Write result to shared memory
        if self.shared_memory:
            self.shared_memory.write_insight(
                {
                    "agent_id": self.agent_id,
                    "content": result.get("result", ""),
                    "tags": ["result", "completed", request_id],
                    "importance": 0.8,
                    "segment": "results",
                    "metadata": {
                        "task_id": task_id,
                        "status": result.get("status", "completed"),
                    },
                }
            )

        return {
            "task_id": task_id,
            "result": result.get("result", ""),
            "status": result.get("status", "completed"),
        }


class CoordinatorAgent(BaseAgent):
    """
    CoordinatorAgent: Monitors progress and handles conflicts.

    Responsibilities:
    - Monitor worker progress
    - Detect conflicts (duplicate task assignments)
    - Track active workers
    - Report system status

    Shared Memory Behavior:
    - Reads ALL insights (exclude_own=False)
    - Does NOT write to shared memory (monitoring only)
    - Monitors segments: "tasks", "results", "progress", "errors"
    """

    def __init__(
        self, config: BaseAgentConfig, shared_memory: SharedMemoryPool, agent_id: str
    ):
        """
        Initialize CoordinatorAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
        """
        super().__init__(
            config=config,
            signature=ProgressMonitoringSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

    def monitor_progress(self) -> Dict[str, Any]:
        """
        Monitor progress of all workers.

        Returns:
            Progress information
        """
        if not self.shared_memory:
            return {"active_workers": [], "pending_tasks": 0, "completed_tasks": 0}

        # Read all insights
        all_insights = self.shared_memory.read_all()

        # Execute monitoring via base agent
        result = self.run(
            insights=json.dumps(all_insights),
            session_id=f"monitor_{uuid.uuid4().hex[:8]}",
        )

        # Parse results
        active_workers_str = result.get("active_workers", "[]")
        if isinstance(active_workers_str, str):
            try:
                active_workers = json.loads(active_workers_str)
            except json.JSONDecodeError:
                active_workers = []
        else:
            active_workers = active_workers_str

        # Ensure proper types for return values
        pending_tasks = result.get("pending_tasks", 0)
        completed_tasks = result.get("completed_tasks", 0)

        # Coerce to integers
        if not isinstance(pending_tasks, int):
            try:
                pending_tasks = int(pending_tasks) if pending_tasks else 0
            except (ValueError, TypeError):
                pending_tasks = 0

        if not isinstance(completed_tasks, int):
            try:
                completed_tasks = int(completed_tasks) if completed_tasks else 0
            except (ValueError, TypeError):
                completed_tasks = 0

        return {
            "active_workers": active_workers,
            "pending_tasks": pending_tasks,
            "completed_tasks": completed_tasks,
        }


# ============================================================================
# Pattern Container
# ============================================================================


@dataclass
class SupervisorWorkerPattern(BaseMultiAgentPattern):
    """
    SupervisorWorkerPattern: Container for supervisor-worker coordination.

    Provides convenience methods for common operations:
    - delegate(): Delegate request to workers
    - aggregate_results(): Aggregate worker results
    - monitor_progress(): Monitor execution progress

    Attributes:
        supervisor: SupervisorAgent instance
        workers: List of WorkerAgent instances
        coordinator: CoordinatorAgent instance
        shared_memory: SharedMemoryPool for coordination
        a2a_coordinator: A2ACoordinator for capability-based selection
    """

    supervisor: SupervisorAgent
    workers: List[WorkerAgent]
    coordinator: CoordinatorAgent

    def __post_init__(self):
        """Initialize A2A coordinator after dataclass initialization."""
        # A2A coordinator delegates to supervisor's coordinator
        self.a2a_coordinator = (
            self.supervisor.a2a_coordinator if self.supervisor else None
        )

    def delegate(
        self, request: str, num_tasks: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Convenience method: Delegate request to workers.

        Args:
            request: User request to process
            num_tasks: Number of tasks (defaults to number of workers)

        Returns:
            List of delegated tasks
        """
        if num_tasks is None:
            num_tasks = len(self.workers)

        worker_ids = [w.agent_id for w in self.workers]
        return self.supervisor.delegate(
            request, available_workers=worker_ids, num_tasks=num_tasks
        )

    def aggregate_results(self, request_id: str) -> Dict[str, Any]:
        """
        Convenience method: Aggregate results from workers.

        Args:
            request_id: Request identifier

        Returns:
            Aggregated results
        """
        return self.supervisor.aggregate_results(request_id)

    def monitor_progress(self) -> Dict[str, Any]:
        """
        Convenience method: Monitor execution progress.

        Returns:
            Progress information
        """
        return self.coordinator.monitor_progress()

    def get_agents(self) -> List[BaseAgent]:
        """
        Get all agents in this pattern.

        Returns:
            List of agent instances (filters out None agents)
        """
        agents = []
        if self.supervisor:
            agents.append(self.supervisor)
        agents.extend(self.workers)
        if self.coordinator:
            agents.append(self.coordinator)
        return agents

    def get_agent_ids(self) -> List[str]:
        """
        Get all agent IDs in this pattern.

        Returns:
            List of agent ID strings
        """
        return [agent.agent_id for agent in self.get_agents() if agent is not None]

    async def execute_async(
        self, request: str, num_tasks: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute supervisor-worker pattern asynchronously using AsyncLocalRuntime.

        This method provides async execution for Docker/FastAPI environments.
        For synchronous execution in CLI/scripts, use the delegate() and
        aggregate_results() methods directly.

        Args:
            request: User request to process
            num_tasks: Number of tasks (defaults to number of workers)

        Returns:
            Dict with final_result, summary, and task_results

        Example:
            >>> pattern = create_supervisor_worker_pattern()
            >>> result = await pattern.execute_async("Process 100 documents", num_tasks=5)
            >>> print(result['final_result'])
        """
        # Delegate tasks to workers
        tasks = self.delegate(request, num_tasks=num_tasks)

        # Get request_id from first task
        if not tasks:
            return {
                "final_result": "No tasks created",
                "summary": "Request completed with 0 tasks",
                "task_results": [],
            }

        request_id = tasks[0].get("request_id")

        # Execute tasks with workers (async simulation)
        for task in tasks:
            assigned_worker_id = task.get("assigned_to")
            # Find the worker
            worker = next(
                (w for w in self.workers if w.agent_id == assigned_worker_id), None
            )
            if worker:
                worker.execute_task(task)

        # Aggregate results
        return self.supervisor.aggregate_results(request_id)


# ============================================================================
# Factory Function
# ============================================================================


def create_supervisor_worker_pattern(
    num_workers: int = 3,
    llm_provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    shared_memory: Optional[SharedMemoryPool] = None,
    supervisor_config: Optional[Dict[str, Any]] = None,
    worker_config: Optional[Dict[str, Any]] = None,
    coordinator_config: Optional[Dict[str, Any]] = None,
) -> SupervisorWorkerPattern:
    """
    Create supervisor-worker pattern with zero-config defaults.

    Zero-Config Usage:
        >>> pattern = create_supervisor_worker_pattern()
        >>> tasks = pattern.delegate("Process documents")

    Progressive Configuration:
        >>> pattern = create_supervisor_worker_pattern(
        ...     num_workers=5,
        ...     model="gpt-4",
        ...     temperature=0.7
        ... )

    Separate Agent Configs:
        >>> pattern = create_supervisor_worker_pattern(
        ...     num_workers=3,
        ...     supervisor_config={'model': 'gpt-4'},
        ...     worker_config={'model': 'gpt-3.5-turbo'}
        ... )

    Args:
        num_workers: Number of worker agents (default: 3)
        llm_provider: LLM provider (default: from env or "openai")
        model: Model name (default: from env or "gpt-3.5-turbo")
        temperature: Temperature (default: 0.7)
        max_tokens: Max tokens (default: 1000)
        shared_memory: Existing SharedMemoryPool (default: creates new)
        supervisor_config: Override supervisor config
        worker_config: Override worker config
        coordinator_config: Override coordinator config

    Returns:
        SupervisorWorkerPattern: Pattern ready to use
    """
    # Create shared memory if not provided
    if shared_memory is None:
        shared_memory = SharedMemoryPool()

    # Build base config from parameters (or use defaults)
    base_config_dict = {
        "llm_provider": llm_provider or os.getenv("KAIZEN_LLM_PROVIDER", "openai"),
        "model": model or os.getenv("KAIZEN_MODEL", "gpt-3.5-turbo"),
        "temperature": temperature if temperature is not None else 0.7,
        "max_tokens": max_tokens if max_tokens is not None else 1000,
    }

    # Build supervisor config
    supervisor_cfg_dict = {**base_config_dict}
    if supervisor_config:
        supervisor_cfg_dict.update(supervisor_config)
    supervisor_cfg = BaseAgentConfig(**supervisor_cfg_dict)

    # Build worker config
    worker_cfg_dict = {**base_config_dict}
    if worker_config:
        worker_cfg_dict.update(worker_config)
    worker_cfg = BaseAgentConfig(**worker_cfg_dict)

    # Build coordinator config
    coordinator_cfg_dict = {**base_config_dict}
    if coordinator_config:
        coordinator_cfg_dict.update(coordinator_config)
    coordinator_cfg = BaseAgentConfig(**coordinator_cfg_dict)

    # Create agents
    supervisor = SupervisorAgent(
        config=supervisor_cfg, shared_memory=shared_memory, agent_id="supervisor_1"
    )

    workers = [
        WorkerAgent(
            config=worker_cfg, shared_memory=shared_memory, agent_id=f"worker_{i+1}"
        )
        for i in range(num_workers)
    ]

    coordinator = CoordinatorAgent(
        config=coordinator_cfg, shared_memory=shared_memory, agent_id="coordinator_1"
    )

    return SupervisorWorkerPattern(
        supervisor=supervisor,
        workers=workers,
        coordinator=coordinator,
        shared_memory=shared_memory,
    )

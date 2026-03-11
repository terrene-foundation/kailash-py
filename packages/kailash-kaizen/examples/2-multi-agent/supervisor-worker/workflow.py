"""
Supervisor-Worker Multi-Agent Pattern.

This example demonstrates centralized coordination with task delegation using
SharedMemoryPool from Phase 2 (Week 3). The supervisor breaks requests into
tasks, delegates to workers, and aggregates results.

Agents:
1. SupervisorAgent - Breaks requests into tasks, delegates, aggregates results
2. WorkerAgent - Executes assigned tasks independently
3. CoordinatorAgent - Monitors progress, handles conflicts

Key Features:
- Centralized task delegation
- Parallel worker execution
- Result aggregation
- Progress monitoring
- Conflict resolution
- Error handling and task reassignment

Architecture:
    User Request
         |
         v
    SupervisorAgent
         |
         v (writes tasks to SharedMemoryPool)
    SharedMemoryPool ["task", "pending"]
         |
         v (workers read tasks)
    WorkerAgent(s) (execute in parallel)
         |
         v (write results to SharedMemoryPool)
    SharedMemoryPool ["result", "completed"]
         |
         v (supervisor reads results)
    SupervisorAgent (aggregates)
         |
         v
    Final Result

Use Cases:
- Parallel document processing
- Data pipeline orchestration
- Distributed task execution
- Batch job processing

Author: Kaizen Framework Team
Created: 2025-10-02 (Phase 5, Task 5E.1)
Reference: Phase 4 shared-insights example
"""

import json
import uuid
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# Signature definitions


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


# Agent implementations


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
    - Writes tasks with tags: ["task", "pending", request_id]
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
        self.signature = ResultAggregationSignature()
        result = self.run(
            task_results=json.dumps(task_results),
            request="Original request",
            session_id=f"aggregate_{request_id}",
        )
        # Switch back
        self.signature = TaskDelegationSignature()

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
        insights = self.shared_memory.read_relevant(
            agent_id=self.agent_id,
            tags=["task", "pending", self.agent_id],
            exclude_own=True,
            limit=10,
        )

        tasks = []
        for insight in insights:
            content = insight.get("content", "{}")
            if isinstance(content, str):
                try:
                    task = json.loads(content)
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

        return {
            "active_workers": active_workers,
            "pending_tasks": result.get("pending_tasks", 0),
            "completed_tasks": result.get("completed_tasks", 0),
        }

    def resolve_conflicts(self) -> Dict[str, Any]:
        """
        Detect and resolve conflicts.

        Returns:
            Conflict resolution information
        """
        if not self.shared_memory:
            return {"conflicts_found": 0, "resolutions": []}

        # Read conflict-related insights
        conflicts = self.shared_memory.read_relevant(
            agent_id=self.agent_id, tags=["conflict"], exclude_own=False, limit=50
        )

        # Group by task_id to find duplicates
        task_assignments = {}
        for insight in conflicts:
            metadata = insight.get("metadata", {})
            task_id = metadata.get("task_id")
            if task_id:
                if task_id not in task_assignments:
                    task_assignments[task_id] = []
                task_assignments[task_id].append(insight["agent_id"])

        # Find conflicts (task assigned to multiple workers)
        conflicts_found = []
        for task_id, workers in task_assignments.items():
            if len(workers) > 1:
                conflicts_found.append({"task_id": task_id, "workers": workers})

        return {"conflicts_found": len(conflicts_found), "resolutions": conflicts_found}


# Workflow function


def supervisor_worker_workflow(
    request: str, num_workers: int = 2, num_tasks: int = 3
) -> Dict[str, Any]:
    """
    Run supervisor-worker multi-agent workflow.

    This workflow demonstrates centralized task delegation:
    1. SupervisorAgent breaks request into tasks
    2. Tasks are written to SharedMemoryPool
    3. WorkerAgents read and execute tasks in parallel
    4. Workers write results to SharedMemoryPool
    5. SupervisorAgent aggregates results
    6. CoordinatorAgent monitors progress

    Args:
        request: User request to process
        num_workers: Number of worker agents to create
        num_tasks: Number of tasks to create

    Returns:
        Dictionary containing:
        - request: Original request
        - tasks: Tasks created
        - results: Individual task results
        - final_result: Aggregated result
        - stats: Shared memory statistics
    """
    # Setup shared memory pool
    shared_pool = SharedMemoryPool()
    config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

    # Create agents
    supervisor = SupervisorAgent(config, shared_pool, agent_id="supervisor_1")
    coordinator = CoordinatorAgent(config, shared_pool, agent_id="coordinator_1")

    # Create workers
    workers = []
    worker_ids = []
    for i in range(num_workers):
        worker_id = f"worker_{i+1}"
        worker = WorkerAgent(config, shared_pool, agent_id=worker_id)
        workers.append(worker)
        worker_ids.append(worker_id)

    print(f"\n{'='*60}")
    print(f"Supervisor-Worker Pattern: {request}")
    print(f"{'='*60}\n")

    # Step 1: Supervisor delegates tasks
    print("Step 1: Supervisor delegating tasks...")
    tasks = supervisor.delegate(
        request, available_workers=worker_ids, num_tasks=num_tasks
    )
    print(f"  - Created {len(tasks)} tasks")
    print(f"  - Assigned to {len(worker_ids)} workers")

    # Step 2: Workers execute tasks
    print("\nStep 2: Workers executing tasks...")
    task_results = []
    for worker in workers:
        assigned_tasks = worker.get_assigned_tasks()
        print(f"  - {worker.agent_id}: {len(assigned_tasks)} tasks")
        for task in assigned_tasks:
            result = worker.execute_task(task)
            task_results.append(result)

    # Step 3: Coordinator monitors
    print("\nStep 3: Coordinator monitoring progress...")
    progress = coordinator.monitor_progress()
    print(f"  - Active workers: {len(progress.get('active_workers', []))}")
    print(f"  - Pending tasks: {progress.get('pending_tasks', 0)}")
    print(f"  - Completed tasks: {progress.get('completed_tasks', 0)}")

    # Step 4: Supervisor aggregates results
    print("\nStep 4: Supervisor aggregating results...")
    request_id = tasks[0].get("request_id", "") if tasks else ""
    aggregated = supervisor.aggregate_results(request_id)
    print(f"  - Final result: {aggregated.get('final_result', 'N/A')[:100]}...")
    print(f"  - Aggregated {len(task_results)} task results")

    # Show shared memory stats
    stats = shared_pool.get_stats()
    print(f"\n{'='*60}")
    print("Shared Memory Statistics:")
    print(f"{'='*60}")
    print(f"  - Total insights: {stats['insight_count']}")
    print(f"  - Agents involved: {stats['agent_count']}")
    print(f"  - Tag distribution: {stats['tag_distribution']}")
    print(f"  - Segment distribution: {stats['segment_distribution']}")
    print(f"{'='*60}\n")

    return {
        "request": request,
        "tasks": tasks,
        "results": task_results,
        "final_result": aggregated.get("final_result", ""),
        "stats": stats,
    }


# Main execution
if __name__ == "__main__":
    # Run example workflow
    result = supervisor_worker_workflow(
        "Process 5 customer support tickets", num_workers=3, num_tasks=5
    )

    print("\nWorkflow Complete!")
    print(f"Request: {result['request']}")
    print(f"Tasks created: {len(result['tasks'])}")
    print(f"Results: {len(result['results'])}")
    print(f"Final result: {result['final_result']}")

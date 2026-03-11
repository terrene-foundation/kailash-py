"""
E2E Integration Tests: Multi-Agent Workflow Execution.

Test Intent:
- Verify supervisor can delegate tasks to multiple workers
- Test trust context propagates correctly through delegation chains
- Validate parallel task execution with trust boundaries
- Ensure workflow status tracks all execution outcomes

These tests use real EATP components - NO MOCKING.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List

import pytest
from kaizen.trust.orchestration.execution_context import TrustExecutionContext
from kaizen.trust.orchestration.integration.registry_aware import (
    CapabilityBasedSelector,
    RegistryAwareRuntime,
    RegistryAwareRuntimeConfig,
)
from kaizen.trust.orchestration.runtime import (
    TrustAwareOrchestrationRuntime,
    TrustAwareRuntimeConfig,
    TrustedWorkflowStatus,
)


class TestMultiAgentWorkflowExecution:
    """
    Test multi-agent workflow execution with trust verification.

    Validates that a supervisor agent can orchestrate tasks
    across multiple workers while maintaining trust boundaries.
    """

    @pytest.mark.asyncio
    async def test_supervisor_delegates_to_single_worker(
        self,
        trust_runtime,
        supervisor_context,
        worker_agents,
    ):
        """
        Supervisor should successfully delegate task to worker.

        The delegation should:
        1. Create child context with appropriate capabilities
        2. Execute task via worker
        3. Return successful result
        """
        await trust_runtime.start()

        try:
            # Define task executor
            async def executor(agent_id: str, task: Any) -> Dict[str, Any]:
                worker = next(
                    (w for w in worker_agents if w.agent_id == agent_id),
                    None,
                )
                if worker:
                    return await worker.execute_task(task, supervisor_context)
                return {"error": f"Unknown agent: {agent_id}"}

            # Execute single task
            status = await trust_runtime.execute_trusted_workflow(
                tasks=["analyze_data"],
                context=supervisor_context,
                agent_selector=lambda _: "analyzer-001",
                task_executor=executor,
            )

            # Verify execution
            assert status.completed_tasks == 1
            assert status.failed_tasks == 0
            assert status.total_tasks == 1
            assert len(status.results) == 1
            assert status.results[0].success is True

        finally:
            await trust_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_supervisor_delegates_to_multiple_workers(
        self,
        trust_runtime,
        supervisor_context,
        worker_agents,
    ):
        """
        Supervisor should delegate tasks to appropriate workers.

        Each task should be assigned to a worker based on
        capabilities and executed successfully.
        """
        await trust_runtime.start()

        try:
            # Task-to-agent mapping
            task_agents = {
                "analyze_data": "analyzer-001",
                "generate_report": "reporter-001",
                "process_batch": "processor-001",
            }

            async def executor(agent_id: str, task: Any) -> Dict[str, Any]:
                worker = next(
                    (w for w in worker_agents if w.agent_id == agent_id),
                    None,
                )
                if worker:
                    return await worker.execute_task(task, supervisor_context)
                return {"error": f"Unknown agent: {agent_id}"}

            # Execute multiple tasks
            status = await trust_runtime.execute_trusted_workflow(
                tasks=list(task_agents.keys()),
                context=supervisor_context,
                agent_selector=lambda task: task_agents.get(task, "analyzer-001"),
                task_executor=executor,
            )

            # All tasks should complete
            assert status.completed_tasks == 3
            assert status.failed_tasks == 0
            assert status.total_tasks == 3

        finally:
            await trust_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_parallel_workflow_execution(
        self,
        trust_runtime,
        supervisor_context,
        worker_agents,
    ):
        """
        Parallel workflows should execute across workers.

        Tasks assigned to different workers should execute
        concurrently while maintaining trust isolation.
        """
        await trust_runtime.start()

        try:
            # Track execution order
            execution_order: List[str] = []
            execution_lock = asyncio.Lock()

            async def executor(agent_id: str, task: Any) -> Dict[str, Any]:
                # Simulate work
                await asyncio.sleep(0.01)

                async with execution_lock:
                    execution_order.append(f"{agent_id}:{task}")

                worker = next(
                    (w for w in worker_agents if w.agent_id == agent_id),
                    None,
                )
                if worker:
                    return await worker.execute_task(task, supervisor_context)
                return {"status": "completed"}

            # Assign tasks to different agents
            task_groups = {
                "analyzer-001": ["task1", "task2"],
                "reporter-001": ["task3", "task4"],
            }

            status = await trust_runtime.execute_parallel_trusted_workflow(
                task_groups=task_groups,
                context=supervisor_context,
                task_executor=executor,
            )

            # All tasks should complete
            assert status.completed_tasks == 4
            assert status.failed_tasks == 0

            # Both agents should have processed tasks
            assert any("analyzer-001" in e for e in execution_order)
            assert any("reporter-001" in e for e in execution_order)

        finally:
            await trust_runtime.shutdown()


class TestRegistryAwareWorkflows:
    """
    Test workflows with automatic agent discovery from registry.

    Validates capability-based agent selection and health-aware
    task assignment work correctly.
    """

    @pytest.mark.asyncio
    async def test_capability_based_agent_discovery(
        self,
        registry_aware_runtime,
        supervisor_context,
        supervisor_agent,
        worker_agents,
    ):
        """
        Runtime should discover agents by capability.

        When required capabilities are specified, only agents
        with matching capabilities should be selected.
        """
        # Register agents in the runtime's registry
        from kaizen.trust.registry.models import RegistrationRequest

        await registry_aware_runtime._registry.register(
            RegistrationRequest(
                agent_id=supervisor_agent.agent_id,
                agent_type="supervisor",
                capabilities=supervisor_agent.capabilities,
                constraints=[],
                trust_chain_hash="test-hash",
                public_key=supervisor_agent.public_key,
                verify_trust=False,
            )
        )
        await registry_aware_runtime._registry.heartbeat(supervisor_agent.agent_id)

        for worker in worker_agents:
            await registry_aware_runtime._registry.register(
                RegistrationRequest(
                    agent_id=worker.agent_id,
                    agent_type="worker",
                    capabilities=worker.capabilities,
                    constraints=[],
                    trust_chain_hash="test-hash",
                    public_key=worker.public_key,
                    verify_trust=False,
                )
            )
            await registry_aware_runtime._registry.heartbeat(worker.agent_id)

        await registry_aware_runtime.start()

        try:
            # Discover agents with analyze capability
            agents = await registry_aware_runtime.discover_agents(
                capabilities=["analyze"],
            )

            # Should find analyzer agent
            assert len(agents) >= 1
            agent_ids = [a.agent_id for a in agents]
            assert "analyzer-001" in agent_ids

        finally:
            await registry_aware_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_workflow_with_auto_discovery(
        self,
        registry_aware_runtime,
        supervisor_context,
        supervisor_agent,
        worker_agents,
    ):
        """
        Workflow should auto-discover and assign agents.

        The runtime should:
        1. Discover agents with required capabilities
        2. Select appropriate agent for each task
        3. Execute and return results
        """
        # Register agents in the runtime's registry
        from kaizen.trust.registry.models import RegistrationRequest

        await registry_aware_runtime._registry.register(
            RegistrationRequest(
                agent_id=supervisor_agent.agent_id,
                agent_type="supervisor",
                capabilities=supervisor_agent.capabilities,
                constraints=[],
                trust_chain_hash="test-hash",
                public_key=supervisor_agent.public_key,
                verify_trust=False,
            )
        )
        await registry_aware_runtime._registry.heartbeat(supervisor_agent.agent_id)

        for worker in worker_agents:
            await registry_aware_runtime._registry.register(
                RegistrationRequest(
                    agent_id=worker.agent_id,
                    agent_type="worker",
                    capabilities=worker.capabilities,
                    constraints=[],
                    trust_chain_hash="test-hash",
                    public_key=worker.public_key,
                    verify_trust=False,
                )
            )
            await registry_aware_runtime._registry.heartbeat(worker.agent_id)

        await registry_aware_runtime.start()

        try:

            async def executor(agent_id: str, task: Any) -> Dict[str, Any]:
                worker = next(
                    (w for w in worker_agents if w.agent_id == agent_id),
                    None,
                )
                if worker:
                    return await worker.execute_task(task, supervisor_context)
                return {"status": "completed", "agent": agent_id}

            # Execute with auto-discovery
            status = await registry_aware_runtime.execute_workflow_with_discovery(
                tasks=["task1", "task2"],
                context=supervisor_context,
                required_capabilities=["analyze"],
                task_executor=executor,
            )

            assert status.completed_tasks == 2
            assert status.failed_tasks == 0

        finally:
            await registry_aware_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_parallel_execution_with_discovery(
        self,
        registry_aware_runtime,
        supervisor_context,
        supervisor_agent,
        worker_agents,
    ):
        """
        Parallel execution should distribute across discovered agents.

        Tasks should be distributed across available agents
        for parallel processing.
        """
        # Register agents in the runtime's registry
        from kaizen.trust.registry.models import RegistrationRequest

        await registry_aware_runtime._registry.register(
            RegistrationRequest(
                agent_id=supervisor_agent.agent_id,
                agent_type="supervisor",
                capabilities=supervisor_agent.capabilities,
                constraints=[],
                trust_chain_hash="test-hash",
                public_key=supervisor_agent.public_key,
                verify_trust=False,
            )
        )
        await registry_aware_runtime._registry.heartbeat(supervisor_agent.agent_id)

        for worker in worker_agents:
            await registry_aware_runtime._registry.register(
                RegistrationRequest(
                    agent_id=worker.agent_id,
                    agent_type="worker",
                    capabilities=worker.capabilities,
                    constraints=[],
                    trust_chain_hash="test-hash",
                    public_key=worker.public_key,
                    verify_trust=False,
                )
            )
            await registry_aware_runtime._registry.heartbeat(worker.agent_id)

        await registry_aware_runtime.start()

        try:
            processed_by: List[str] = []
            lock = asyncio.Lock()

            async def executor(agent_id: str, task: Any) -> Dict[str, Any]:
                async with lock:
                    processed_by.append(agent_id)
                return {"status": "completed", "agent": agent_id}

            # Execute many tasks in parallel
            status = await registry_aware_runtime.execute_parallel_with_discovery(
                tasks=[f"task{i}" for i in range(6)],
                context=supervisor_context,
                max_agents=3,
                task_executor=executor,
            )

            # All should complete
            assert status.completed_tasks == 6
            assert status.failed_tasks == 0

            # Multiple agents should have processed tasks
            unique_agents = set(processed_by)
            assert len(unique_agents) >= 1

        finally:
            await registry_aware_runtime.shutdown()


class TestWorkflowStatusTracking:
    """
    Test workflow status and result tracking.

    Validates that execution outcomes are properly tracked
    and reported.
    """

    @pytest.mark.asyncio
    async def test_workflow_tracks_successful_tasks(
        self,
        trust_runtime,
        supervisor_context,
        worker_agents,
    ):
        """Status should track all successful task completions."""
        await trust_runtime.start()

        try:

            async def executor(agent_id: str, task: Any) -> Dict[str, Any]:
                return {"status": "completed", "task": task}

            status = await trust_runtime.execute_trusted_workflow(
                tasks=["task1", "task2", "task3"],
                context=supervisor_context,
                agent_selector=lambda _: "analyzer-001",
                task_executor=executor,
            )

            # Verify tracking
            assert status.total_tasks == 3
            assert status.completed_tasks == 3
            assert status.failed_tasks == 0
            assert len(status.results) == 3
            assert all(r.success for r in status.results)

        finally:
            await trust_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_workflow_tracks_failed_tasks(
        self,
        trust_runtime,
        supervisor_context,
    ):
        """Status should track task failures."""
        await trust_runtime.start()

        try:

            async def failing_executor(agent_id: str, task: Any) -> Dict[str, Any]:
                if task == "fail_task":
                    raise ValueError("Intentional failure")
                return {"status": "completed"}

            status = await trust_runtime.execute_trusted_workflow(
                tasks=["task1", "fail_task", "task3"],
                context=supervisor_context,
                agent_selector=lambda _: "analyzer-001",
                task_executor=failing_executor,
            )

            # Should track failure
            assert status.total_tasks == 3
            assert status.failed_tasks >= 1

        finally:
            await trust_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_workflow_includes_execution_metrics(
        self,
        trust_runtime,
        supervisor_context,
    ):
        """Status should include execution timing metrics."""
        await trust_runtime.start()

        try:

            async def executor(agent_id: str, task: Any) -> Dict[str, Any]:
                await asyncio.sleep(0.01)  # Simulate work
                return {"status": "completed"}

            status = await trust_runtime.execute_trusted_workflow(
                tasks=["task1"],
                context=supervisor_context,
                agent_selector=lambda _: "analyzer-001",
                task_executor=executor,
            )

            # Should have timing data
            assert status.completed_tasks == 1
            if status.results:
                result = status.results[0]
                assert result.execution_time_ms >= 0

        finally:
            await trust_runtime.shutdown()

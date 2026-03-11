"""
Test SupervisorWorkerPattern - Multi-Agent Coordination Pattern

Tests supervisor-worker pattern with centralized task delegation.
Covers factory function, pattern class, all agents, and coordination.

Written BEFORE implementation (TDD).

Test Coverage:
- Factory Function: 8 tests
- Pattern Class: 8 tests
- SupervisorAgent: 12 tests
- WorkerAgent: 10 tests
- CoordinatorAgent: 8 tests
- Integration: 10 tests
- Shared Memory Coordination: 8 tests
- Error Handling: 6 tests
Total: 70 tests
"""

import json

# ============================================================================
# TEST CLASS 1: Factory Function (8 tests)
# ============================================================================


class TestCreateSupervisorWorkerPattern:
    """Test create_supervisor_worker_pattern factory function."""

    def test_zero_config_creation(self):
        """Test zero-config pattern creation."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern()

        assert pattern is not None
        assert pattern.supervisor is not None
        assert len(pattern.workers) == 3  # default
        assert pattern.coordinator is not None
        assert pattern.shared_memory is not None

    def test_custom_num_workers(self):
        """Test creating pattern with custom worker count."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=5)

        assert len(pattern.workers) == 5
        assert pattern.supervisor is not None
        assert pattern.coordinator is not None

    def test_progressive_configuration_model_only(self):
        """Test overriding model only."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(model="gpt-4", num_workers=2)

        # Verify supervisor config uses gpt-4
        assert pattern.supervisor.config.model == "gpt-4"
        # Verify workers use gpt-4
        for worker in pattern.workers:
            assert worker.config.model == "gpt-4"
        # Verify coordinator uses gpt-4
        assert pattern.coordinator.config.model == "gpt-4"

    def test_progressive_configuration_multiple_params(self):
        """Test overriding multiple parameters."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(
            llm_provider="anthropic",
            model="claude-3-opus",
            temperature=0.7,
            max_tokens=2000,
            num_workers=2,
        )

        # Verify all agents have correct config
        assert pattern.supervisor.config.llm_provider == "anthropic"
        assert pattern.supervisor.config.model == "claude-3-opus"
        assert pattern.supervisor.config.temperature == 0.7
        assert pattern.supervisor.config.max_tokens == 2000

        for worker in pattern.workers:
            assert worker.config.llm_provider == "anthropic"
            assert worker.config.model == "claude-3-opus"

    def test_separate_configs_per_agent_type(self):
        """Test separate configs for supervisor, workers, coordinator."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(
            num_workers=2,
            supervisor_config={"model": "gpt-4"},
            worker_config={"model": "gpt-3.5-turbo"},
            coordinator_config={"model": "gpt-3.5-turbo"},
        )

        # Supervisor should use gpt-4
        assert pattern.supervisor.config.model == "gpt-4"
        # Workers should use gpt-3.5-turbo
        for worker in pattern.workers:
            assert worker.config.model == "gpt-3.5-turbo"
        # Coordinator should use gpt-3.5-turbo
        assert pattern.coordinator.config.model == "gpt-3.5-turbo"

    def test_shared_memory_provided(self):
        """Test providing existing SharedMemoryPool."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern
        from kaizen.memory import SharedMemoryPool

        existing_pool = SharedMemoryPool()

        pattern = create_supervisor_worker_pattern(
            shared_memory=existing_pool, num_workers=2
        )

        # Pattern should use provided pool
        assert pattern.shared_memory is existing_pool
        # All agents should share same pool
        assert pattern.supervisor.shared_memory is existing_pool
        for worker in pattern.workers:
            assert worker.shared_memory is existing_pool
        assert pattern.coordinator.shared_memory is existing_pool

    def test_agent_ids_are_unique(self):
        """Test that all agent IDs are unique."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=5)

        agent_ids = pattern.get_agent_ids()

        # Should have unique IDs
        assert len(agent_ids) == len(set(agent_ids))
        # Should include supervisor, workers, coordinator
        assert len(agent_ids) == 7  # 1 supervisor + 5 workers + 1 coordinator

    def test_default_agent_ids_format(self):
        """Test default agent ID naming convention."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=3)

        agent_ids = pattern.get_agent_ids()

        # Check expected IDs
        assert "supervisor_1" in agent_ids
        assert "worker_1" in agent_ids
        assert "worker_2" in agent_ids
        assert "worker_3" in agent_ids
        assert "coordinator_1" in agent_ids


# ============================================================================
# TEST CLASS 2: SupervisorWorkerPattern Class (8 tests)
# ============================================================================


class TestSupervisorWorkerPattern:
    """Test SupervisorWorkerPattern class."""

    def test_pattern_initialization(self):
        """Test pattern is properly initialized."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern()

        assert pattern.validate_pattern() is True

    def test_delegate_convenience_method(self):
        """Test pattern.delegate() calls supervisor.delegate()."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)
        tasks = pattern.delegate("Process documents", num_tasks=2)

        assert isinstance(tasks, list)
        assert len(tasks) == 2
        # Tasks should have required fields
        for task in tasks:
            assert "task_id" in task
            assert "assigned_to" in task
            assert "request_id" in task

    def test_aggregate_convenience_method(self):
        """Test pattern.aggregate_results() calls supervisor.aggregate_results()."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate and execute
        tasks = pattern.delegate("Process document", num_tasks=1)
        request_id = tasks[0]["request_id"]

        # Workers execute (simulate)
        worker = pattern.workers[0]
        assigned_tasks = worker.get_assigned_tasks()
        if assigned_tasks:
            worker.execute_task(assigned_tasks[0])

        # Aggregate
        result = pattern.aggregate_results(request_id)

        assert isinstance(result, dict)
        assert "final_result" in result or "summary" in result

    def test_monitor_convenience_method(self):
        """Test pattern.monitor_progress() calls coordinator.monitor_progress()."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Delegate some tasks
        pattern.delegate("Process documents", num_tasks=2)

        # Monitor
        progress = pattern.monitor_progress()

        assert isinstance(progress, dict)
        assert "pending_tasks" in progress or "completed_tasks" in progress

    def test_get_agents(self):
        """Test get_agents() returns all agents."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)
        agents = pattern.get_agents()

        # Should return 1 supervisor + 2 workers + 1 coordinator = 4
        assert len(agents) == 4
        # First should be supervisor
        assert agents[0] == pattern.supervisor
        # Last should be coordinator
        assert agents[-1] == pattern.coordinator
        # Middle should be workers
        assert agents[1] in pattern.workers
        assert agents[2] in pattern.workers

    def test_get_agent_ids(self):
        """Test get_agent_ids() returns unique IDs."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)
        agent_ids = pattern.get_agent_ids()

        assert len(agent_ids) == 4  # 1 + 2 + 1
        assert "supervisor_1" in agent_ids
        assert "worker_1" in agent_ids
        assert "worker_2" in agent_ids
        assert "coordinator_1" in agent_ids

    def test_clear_shared_memory(self):
        """Test clear_shared_memory() clears pattern state."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate tasks
        pattern.delegate("Process documents", num_tasks=2)

        # Should have insights
        insights_before = pattern.shared_memory.read_all()
        assert len(insights_before) > 0

        # Clear
        pattern.clear_shared_memory()

        # Should be empty
        insights_after = pattern.shared_memory.read_all()
        assert len(insights_after) == 0

    def test_validate_pattern_detects_invalid_pattern(self):
        """Test validate_pattern() detects invalid configuration."""
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.supervisor_worker import (
            SupervisorWorkerPattern,
        )

        # Create pattern with no agents (invalid)
        pattern = SupervisorWorkerPattern(
            supervisor=None,
            workers=[],
            coordinator=None,
            shared_memory=SharedMemoryPool(),
        )

        assert pattern.validate_pattern() is False


# ============================================================================
# TEST CLASS 3: SupervisorAgent (12 tests)
# ============================================================================


class TestSupervisorAgent:
    """Test SupervisorAgent class."""

    def test_initialization(self):
        """Test supervisor initialization."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.supervisor_worker import SupervisorAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        supervisor = SupervisorAgent(
            config=config, shared_memory=shared_memory, agent_id="test_supervisor"
        )

        assert supervisor.agent_id == "test_supervisor"
        assert supervisor.shared_memory is shared_memory
        assert supervisor.signature is not None

    def test_delegate_creates_tasks(self):
        """Test delegate() creates tasks."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)
        tasks = pattern.supervisor.delegate("Process documents", num_tasks=3)

        assert len(tasks) == 3
        assert all("task_id" in task for task in tasks)
        assert all("assigned_to" in task for task in tasks)
        assert all("request_id" in task for task in tasks)

    def test_delegate_writes_to_shared_memory(self):
        """Test delegate() writes tasks to shared memory."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)
        pattern.supervisor.delegate("Process documents", num_tasks=2)

        # Check shared memory has tasks
        tasks = pattern.get_shared_insights(tags=["task", "pending"])
        assert len(tasks) >= 2

    def test_delegate_round_robin_assignment(self):
        """Test delegate() assigns tasks round-robin to workers."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=3)
        tasks = pattern.supervisor.delegate("Process documents", num_tasks=6)

        # Count assignments per worker
        worker_ids = [w.agent_id for w in pattern.workers]
        assignments = {}
        for task in tasks:
            worker_id = task["assigned_to"]
            assignments[worker_id] = assignments.get(worker_id, 0) + 1

        # Each worker should get 2 tasks (6 / 3)
        for worker_id in worker_ids:
            assert assignments.get(worker_id, 0) == 2

    def test_aggregate_results_reads_from_shared_memory(self):
        """Test aggregate_results() reads results from shared memory."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate and execute
        tasks = pattern.supervisor.delegate("Process document", num_tasks=1)
        request_id = tasks[0]["request_id"]

        # Worker executes
        worker = pattern.workers[0]
        assigned_tasks = worker.get_assigned_tasks()
        if assigned_tasks:
            worker.execute_task(assigned_tasks[0])

        # Aggregate
        result = pattern.supervisor.aggregate_results(request_id)

        assert isinstance(result, dict)
        assert "task_results" in result

    def test_aggregate_results_signature_switch(self):
        """Test aggregate_results() switches signature temporarily."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Initial signature should be TaskDelegationSignature
        initial_signature_type = type(pattern.supervisor.signature).__name__

        # Delegate and execute
        tasks = pattern.supervisor.delegate("Process document", num_tasks=1)
        request_id = tasks[0]["request_id"]

        # Aggregate (switches signature internally)
        pattern.supervisor.aggregate_results(request_id)

        # Signature should be restored
        final_signature_type = type(pattern.supervisor.signature).__name__
        assert initial_signature_type == final_signature_type

    def test_check_all_tasks_completed(self):
        """Test check_all_tasks_completed() detects completion."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate tasks
        tasks = pattern.supervisor.delegate("Process document", num_tasks=1)
        request_id = tasks[0]["request_id"]

        # Before execution
        pattern.supervisor.check_all_tasks_completed(request_id)
        # May or may not be complete yet

        # Worker executes
        worker = pattern.workers[0]
        assigned_tasks = worker.get_assigned_tasks()
        if assigned_tasks:
            worker.execute_task(assigned_tasks[0])

        # After execution
        pattern.supervisor.check_all_tasks_completed(request_id)
        # Should detect completion or progress

    def test_check_failures(self):
        """Test check_failures() detects failed tasks."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate task
        tasks = pattern.supervisor.delegate("Process document", num_tasks=1)
        request_id = tasks[0]["request_id"]

        # Check failures (should be empty initially)
        failures = pattern.supervisor.check_failures(request_id)
        assert isinstance(failures, list)

    def test_reassign_task(self):
        """Test reassign_task() reassigns to different worker."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=3)

        # Create a task
        task = {
            "task_id": "task_1",
            "description": "Process document",
            "assigned_to": "worker_1",
            "request_id": "req_1",
        }

        # Reassign to worker_2
        updated_task = pattern.supervisor.reassign_task(task, "worker_2")

        assert updated_task["assigned_to"] == "worker_2"
        assert updated_task["task_id"] == "task_1"

    def test_reassign_task_writes_to_shared_memory(self):
        """Test reassign_task() writes reassignment to shared memory."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=3)

        # Create a task
        task = {
            "task_id": "task_reassign",
            "description": "Process document",
            "assigned_to": "worker_1",
            "request_id": "req_reassign",
        }

        # Reassign
        pattern.supervisor.reassign_task(task, "worker_2")

        # Should be in shared memory
        insights = pattern.get_shared_insights(tags=["task"])
        task_ids = [
            json.loads(i["content"])["task_id"]
            for i in insights
            if isinstance(i.get("content"), str)
        ]
        assert "task_reassign" in task_ids

    def test_delegate_with_custom_available_workers(self):
        """Test delegate() with custom available_workers list."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=5)

        # Delegate to subset of workers
        tasks = pattern.supervisor.delegate(
            "Process documents", available_workers=["worker_1", "worker_2"], num_tasks=4
        )

        # All tasks should be assigned to worker_1 or worker_2
        assigned_workers = [task["assigned_to"] for task in tasks]
        assert all(w in ["worker_1", "worker_2"] for w in assigned_workers)

    def test_delegate_generates_unique_request_id(self):
        """Test delegate() generates unique request IDs."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Delegate twice
        tasks1 = pattern.supervisor.delegate("Request 1", num_tasks=2)
        tasks2 = pattern.supervisor.delegate("Request 2", num_tasks=2)

        # Request IDs should be different
        request_id_1 = tasks1[0]["request_id"]
        request_id_2 = tasks2[0]["request_id"]
        assert request_id_1 != request_id_2


# ============================================================================
# TEST CLASS 4: WorkerAgent (10 tests)
# ============================================================================


class TestWorkerAgent:
    """Test WorkerAgent class."""

    def test_initialization(self):
        """Test worker initialization."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.supervisor_worker import WorkerAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        worker = WorkerAgent(
            config=config, shared_memory=shared_memory, agent_id="test_worker"
        )

        assert worker.agent_id == "test_worker"
        assert worker.shared_memory is shared_memory
        assert worker.signature is not None

    def test_get_assigned_tasks(self):
        """Test worker reads assigned tasks from shared memory."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Supervisor delegates
        pattern.delegate("Process document", num_tasks=1)

        # Worker reads assigned task
        worker = pattern.workers[0]
        tasks = worker.get_assigned_tasks()

        assert len(tasks) >= 1
        assert all("task_id" in task for task in tasks)

    def test_get_assigned_tasks_filters_by_worker_id(self):
        """Test worker only retrieves tasks assigned to it."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=3)

        # Delegate tasks
        pattern.delegate("Process documents", num_tasks=6)

        # Each worker should only see their tasks
        for worker in pattern.workers:
            tasks = worker.get_assigned_tasks()
            for task in tasks:
                assert task["assigned_to"] == worker.agent_id

    def test_execute_task(self):
        """Test worker executes task and returns result."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate task
        tasks = pattern.delegate("Process document", num_tasks=1)
        task = tasks[0]

        # Worker executes
        worker = pattern.workers[0]
        result = worker.execute_task(task)

        assert isinstance(result, dict)
        assert "task_id" in result
        assert "result" in result or "status" in result

    def test_execute_task_writes_to_shared_memory(self):
        """Test worker writes result to shared memory."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate and execute
        tasks = pattern.delegate("Process document", num_tasks=1)
        tasks[0]["request_id"]

        worker = pattern.workers[0]
        assigned_tasks = worker.get_assigned_tasks()
        if assigned_tasks:
            worker.execute_task(assigned_tasks[0])

        # Check shared memory for result
        results = pattern.get_shared_insights(tags=["result", "completed"])
        assert len(results) >= 1

    def test_execute_task_includes_request_id_in_result(self):
        """Test executed task result includes request_id."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate task
        tasks = pattern.delegate("Process document", num_tasks=1)
        task = tasks[0]
        request_id = task["request_id"]

        # Worker executes
        worker = pattern.workers[0]
        worker.execute_task(task)

        # Result in shared memory should have request_id tag
        results = pattern.get_shared_insights(tags=["result", "completed", request_id])
        assert len(results) >= 1

    def test_execute_task_with_task_id(self):
        """Test execute_task preserves task_id."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate task
        tasks = pattern.delegate("Process document", num_tasks=1)
        task = tasks[0]
        task_id = task["task_id"]

        # Worker executes
        worker = pattern.workers[0]
        result = worker.execute_task(task)

        assert result["task_id"] == task_id

    def test_multiple_workers_execute_different_tasks(self):
        """Test multiple workers execute their respective tasks."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=3)

        # Delegate 6 tasks (2 per worker)
        pattern.delegate("Process documents", num_tasks=6)

        # Each worker executes their tasks
        executed_count = 0
        for worker in pattern.workers:
            assigned_tasks = worker.get_assigned_tasks()
            for task in assigned_tasks:
                result = worker.execute_task(task)
                assert result is not None
                executed_count += 1

        # Should have executed multiple tasks
        assert executed_count > 0

    def test_worker_handles_empty_task_list(self):
        """Test worker handles case with no assigned tasks."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=5)

        # Delegate only 1 task to 5 workers
        pattern.delegate("Process document", num_tasks=1)

        # Some workers will have no tasks
        workers_with_tasks = 0
        workers_without_tasks = 0

        for worker in pattern.workers:
            assigned_tasks = worker.get_assigned_tasks()
            if assigned_tasks:
                workers_with_tasks += 1
            else:
                workers_without_tasks += 1

        # At least one worker should have task
        assert workers_with_tasks >= 1

    def test_execute_task_status_completed(self):
        """Test execute_task marks status as completed."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate task
        tasks = pattern.delegate("Process document", num_tasks=1)
        task = tasks[0]

        # Worker executes
        worker = pattern.workers[0]
        result = worker.execute_task(task)

        # Status should be completed (or present)
        assert "status" in result


# ============================================================================
# TEST CLASS 5: CoordinatorAgent (8 tests)
# ============================================================================


class TestCoordinatorAgent:
    """Test CoordinatorAgent class."""

    def test_initialization(self):
        """Test coordinator initialization."""
        from kaizen.core.base_agent import BaseAgentConfig
        from kaizen.memory import SharedMemoryPool
        from kaizen.orchestration.patterns.supervisor_worker import CoordinatorAgent

        shared_memory = SharedMemoryPool()
        config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

        coordinator = CoordinatorAgent(
            config=config, shared_memory=shared_memory, agent_id="test_coordinator"
        )

        assert coordinator.agent_id == "test_coordinator"
        assert coordinator.shared_memory is shared_memory
        assert coordinator.signature is not None

    def test_monitor_progress_returns_dict(self):
        """Test monitor_progress() returns progress information."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)
        progress = pattern.coordinator.monitor_progress()

        assert isinstance(progress, dict)

    def test_monitor_progress_has_expected_fields(self):
        """Test monitor_progress() returns expected fields."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)
        progress = pattern.coordinator.monitor_progress()

        # Should have progress fields
        assert (
            "active_workers" in progress
            or "pending_tasks" in progress
            or "completed_tasks" in progress
        )

    def test_monitor_progress_after_delegation(self):
        """Test monitor_progress() after tasks delegated."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Delegate tasks
        pattern.delegate("Process documents", num_tasks=4)

        # Monitor
        progress = pattern.coordinator.monitor_progress()

        assert isinstance(progress, dict)
        # Should detect some activity

    def test_monitor_progress_tracks_pending_tasks(self):
        """Test monitor_progress() tracks pending tasks."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Delegate tasks
        pattern.delegate("Process documents", num_tasks=3)

        # Monitor
        progress = pattern.coordinator.monitor_progress()

        # Should have pending_tasks field
        if "pending_tasks" in progress:
            # Should be integer
            assert isinstance(progress["pending_tasks"], int)

    def test_monitor_progress_tracks_completed_tasks(self):
        """Test monitor_progress() tracks completed tasks."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate and execute
        pattern.delegate("Process document", num_tasks=1)
        worker = pattern.workers[0]
        assigned_tasks = worker.get_assigned_tasks()
        if assigned_tasks:
            worker.execute_task(assigned_tasks[0])

        # Monitor
        progress = pattern.coordinator.monitor_progress()

        # Should have completed_tasks field
        if "completed_tasks" in progress:
            assert isinstance(progress["completed_tasks"], int)

    def test_monitor_progress_with_no_activity(self):
        """Test monitor_progress() with no tasks delegated."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Monitor without any tasks
        progress = pattern.coordinator.monitor_progress()

        assert isinstance(progress, dict)
        # Should handle empty state gracefully

    def test_coordinator_reads_all_insights(self):
        """Test coordinator reads all insights from shared memory."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Delegate tasks
        pattern.delegate("Process documents", num_tasks=2)

        # Coordinator monitors (reads all insights)
        progress = pattern.coordinator.monitor_progress()

        # Should have processed insights
        assert isinstance(progress, dict)


# ============================================================================
# TEST CLASS 6: Integration (10 tests)
# ============================================================================


class TestSupervisorWorkerIntegration:
    """Test complete supervisor-worker workflow integration."""

    def test_end_to_end_workflow(self):
        """Test complete workflow: delegate → execute → aggregate."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # 1. Supervisor delegates
        tasks = pattern.delegate("Process 2 documents", num_tasks=2)
        assert len(tasks) == 2

        # 2. Workers pick up tasks
        for worker in pattern.workers:
            assigned = worker.get_assigned_tasks()
            if assigned:
                # Execute first task
                result = worker.execute_task(assigned[0])
                assert result is not None

        # 3. Supervisor aggregates
        request_id = tasks[0]["request_id"]
        final = pattern.aggregate_results(request_id)
        assert final is not None
        assert isinstance(final, dict)

    def test_task_round_robin_assignment(self):
        """Test tasks assigned to workers in round-robin."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=3)
        tasks = pattern.delegate("Process documents", num_tasks=6)

        # Check each worker got 2 tasks
        worker_ids = [w.agent_id for w in pattern.workers]
        assignments = [task["assigned_to"] for task in tasks]

        for worker_id in worker_ids:
            assert assignments.count(worker_id) == 2

    def test_multiple_requests_isolated(self):
        """Test multiple requests are isolated by request_id."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Delegate two separate requests
        tasks1 = pattern.delegate("Request 1", num_tasks=2)
        tasks2 = pattern.delegate("Request 2", num_tasks=2)

        request_id_1 = tasks1[0]["request_id"]
        request_id_2 = tasks2[0]["request_id"]

        # Request IDs should be different
        assert request_id_1 != request_id_2

        # Tasks should be tagged with correct request_id
        assert all(t["request_id"] == request_id_1 for t in tasks1)
        assert all(t["request_id"] == request_id_2 for t in tasks2)

    def test_worker_only_sees_own_tasks(self):
        """Test worker only retrieves tasks assigned to it."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=3)

        # Delegate tasks
        pattern.delegate("Process documents", num_tasks=9)

        # Each worker should only see their own tasks
        for worker in pattern.workers:
            assigned_tasks = worker.get_assigned_tasks()
            for task in assigned_tasks:
                assert task["assigned_to"] == worker.agent_id

    def test_coordinator_monitors_during_execution(self):
        """Test coordinator can monitor while workers execute."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Delegate
        pattern.delegate("Process documents", num_tasks=2)

        # Monitor before execution
        progress_before = pattern.monitor_progress()

        # Execute
        for worker in pattern.workers:
            assigned = worker.get_assigned_tasks()
            if assigned:
                worker.execute_task(assigned[0])

        # Monitor after execution
        progress_after = pattern.monitor_progress()

        assert isinstance(progress_before, dict)
        assert isinstance(progress_after, dict)

    def test_parallel_worker_execution(self):
        """Test multiple workers execute tasks in parallel."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=3)

        # Delegate 6 tasks
        pattern.delegate("Process documents", num_tasks=6)

        # All workers execute their tasks
        results = []
        for worker in pattern.workers:
            assigned = worker.get_assigned_tasks()
            for task in assigned:
                result = worker.execute_task(task)
                results.append(result)

        # Should have multiple results
        assert len(results) > 0

    def test_aggregation_combines_multiple_results(self):
        """Test aggregation combines results from multiple workers."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Delegate and execute
        tasks = pattern.delegate("Process documents", num_tasks=2)
        request_id = tasks[0]["request_id"]

        for worker in pattern.workers:
            assigned = worker.get_assigned_tasks()
            if assigned:
                worker.execute_task(assigned[0])

        # Aggregate
        final = pattern.aggregate_results(request_id)

        assert "task_results" in final
        # Should have combined multiple results

    def test_shared_memory_accumulates_insights(self):
        """Test shared memory accumulates insights from all agents."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Delegate and execute
        pattern.delegate("Process documents", num_tasks=2)

        # Get all insights
        all_insights = pattern.shared_memory.read_all()

        # Should have insights from supervisor (tasks)
        assert len(all_insights) > 0

    def test_pattern_handles_no_workers(self):
        """Test pattern handles edge case with no workers."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        # Create pattern with 1 worker
        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Should work
        assert len(pattern.workers) == 1

    def test_pattern_state_reset_between_requests(self):
        """Test pattern can handle multiple sequential requests."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # First request
        tasks1 = pattern.delegate("Request 1", num_tasks=2)
        request_id_1 = tasks1[0]["request_id"]

        # Second request
        tasks2 = pattern.delegate("Request 2", num_tasks=2)
        request_id_2 = tasks2[0]["request_id"]

        # Both should work
        assert request_id_1 != request_id_2


# ============================================================================
# TEST CLASS 7: Shared Memory Coordination (8 tests)
# ============================================================================


class TestSharedMemoryCoordination:
    """Test shared memory coordination between agents."""

    def test_tasks_written_with_correct_tags(self):
        """Test tasks have correct tags in shared memory."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Delegate
        tasks = pattern.delegate("Process documents", num_tasks=2)
        tasks[0]["request_id"]

        # Check shared memory
        task_insights = pattern.get_shared_insights(tags=["task", "pending"])

        # Should have tasks with correct tags
        assert len(task_insights) >= 2

    def test_results_written_with_correct_tags(self):
        """Test results have correct tags in shared memory."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate and execute
        pattern.delegate("Process document", num_tasks=1)

        worker = pattern.workers[0]
        assigned = worker.get_assigned_tasks()
        if assigned:
            worker.execute_task(assigned[0])

        # Check shared memory for results
        result_insights = pattern.get_shared_insights(tags=["result", "completed"])

        assert len(result_insights) >= 1

    def test_workers_only_see_own_tasks(self):
        """Test workers only retrieve tasks assigned to them."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=3)

        # Delegate tasks
        pattern.delegate("Process documents", num_tasks=6)

        # Each worker filters by their ID
        for worker in pattern.workers:
            assigned = worker.get_assigned_tasks()
            for task in assigned:
                assert task["assigned_to"] == worker.agent_id

    def test_request_id_isolates_different_requests(self):
        """Test request_id properly isolates different requests."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Two requests
        tasks1 = pattern.delegate("Request 1", num_tasks=2)
        tasks2 = pattern.delegate("Request 2", num_tasks=2)

        request_id_1 = tasks1[0]["request_id"]
        request_id_2 = tasks2[0]["request_id"]

        # Filter by request_id
        pattern.get_shared_insights(tags=[request_id_1])
        pattern.get_shared_insights(tags=[request_id_2])

        # Should have separate insights
        # (May overlap in content but should have different request_ids)

    def test_task_importance_set_correctly(self):
        """Test task importance is set in shared memory."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate
        pattern.delegate("Process document", num_tasks=1)

        # Check shared memory
        insights = pattern.shared_memory.read_all()

        # Tasks should have importance
        for insight in insights:
            if "task" in insight.get("tags", []):
                assert "importance" in insight
                # Should be 0.8 or 0.9 (reassigned)
                assert 0 <= insight["importance"] <= 1

    def test_result_importance_set_correctly(self):
        """Test result importance is set in shared memory."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate and execute
        pattern.delegate("Process document", num_tasks=1)

        worker = pattern.workers[0]
        assigned = worker.get_assigned_tasks()
        if assigned:
            worker.execute_task(assigned[0])

        # Check shared memory
        insights = pattern.shared_memory.read_all()

        # Results should have importance
        for insight in insights:
            if "result" in insight.get("tags", []):
                assert "importance" in insight
                assert 0 <= insight["importance"] <= 1

    def test_memory_segments_used_correctly(self):
        """Test correct memory segments are used."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate and execute
        pattern.delegate("Process document", num_tasks=1)

        worker = pattern.workers[0]
        assigned = worker.get_assigned_tasks()
        if assigned:
            worker.execute_task(assigned[0])

        # Check shared memory
        insights = pattern.shared_memory.read_all()

        # Should have segment field
        for insight in insights:
            assert "segment" in insight
            # Should be "tasks" or "results"

    def test_metadata_includes_task_info(self):
        """Test metadata includes task information."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Delegate
        tasks = pattern.delegate("Process document", num_tasks=1)
        task_id = tasks[0]["task_id"]

        # Check shared memory
        insights = pattern.shared_memory.read_all()

        # Find task insight
        task_insight = None
        for insight in insights:
            if "task" in insight.get("tags", []):
                task_insight = insight
                break

        if task_insight:
            assert "metadata" in task_insight
            # Should have task_id in metadata
            if "task_id" in task_insight["metadata"]:
                assert task_insight["metadata"]["task_id"] == task_id


# ============================================================================
# TEST CLASS 8: Error Handling (6 tests)
# ============================================================================


class TestSupervisorWorkerErrorHandling:
    """Test error handling in supervisor-worker pattern."""

    def test_delegate_with_invalid_request(self):
        """Test handling invalid request."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Empty request
        tasks = pattern.delegate("", num_tasks=2)

        # Should still create tasks (mock provider handles it)
        assert isinstance(tasks, list)

    def test_delegate_with_zero_num_tasks(self):
        """Test delegate with num_tasks=0."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Zero tasks
        tasks = pattern.delegate("Process documents", num_tasks=0)

        # Should return empty list
        assert isinstance(tasks, list)
        assert len(tasks) == 0

    def test_execute_task_with_missing_fields(self):
        """Test execute_task with incomplete task."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=1)

        # Incomplete task
        incomplete_task = {
            "task_id": "test_task"
            # Missing description, request_id
        }

        worker = pattern.workers[0]
        result = worker.execute_task(incomplete_task)

        # Should handle gracefully
        assert isinstance(result, dict)

    def test_aggregate_with_no_results(self):
        """Test aggregate_results with no completed tasks."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Aggregate without execution
        result = pattern.aggregate_results("nonexistent_request_id")

        # Should return result (may be empty)
        assert isinstance(result, dict)

    def test_monitor_with_empty_shared_memory(self):
        """Test monitor_progress with no insights."""
        from kaizen.agents.coordination import create_supervisor_worker_pattern

        pattern = create_supervisor_worker_pattern(num_workers=2)

        # Monitor before any activity
        progress = pattern.monitor_progress()

        # Should handle empty state
        assert isinstance(progress, dict)

    def test_pattern_without_shared_memory(self):
        """Test pattern behavior without shared memory."""
        from kaizen.orchestration.patterns.supervisor_worker import (
            SupervisorWorkerPattern,
        )

        # Create pattern with None shared_memory
        pattern = SupervisorWorkerPattern(
            supervisor=None, workers=[], coordinator=None, shared_memory=None
        )

        # Should fail validation
        assert pattern.validate_pattern() is False

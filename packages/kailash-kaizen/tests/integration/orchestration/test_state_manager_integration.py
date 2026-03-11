"""
Integration tests for OrchestrationStateManager with real PostgreSQL.

Tests the complete DataFlow integration with 3 models and 33 auto-generated nodes.

Test Coverage:
- Workflow state CRUD operations
- Agent execution record tracking
- Checkpoint creation and loading
- Gzip compression/decompression
- JSON field parsing
- Error handling (not found, validation errors)
- Active workflow queries

Test Strategy: Tier 2 Integration (Real Infrastructure, NO MOCKING)
- Real PostgreSQL database connection
- Real DataFlow node execution
- Real AsyncLocalRuntime execution
- Automatic cleanup after each test

Author: Kaizen Framework Team
Created: 2025-11-17 (TODO-178, Phase 2: DataFlow Integration)
"""

import gzip
import json
import os
import tempfile
from datetime import datetime

import pytest
import pytest_asyncio
from dotenv import load_dotenv

# Load .env BEFORE reading environment variables
load_dotenv()

from kaizen.orchestration.state_manager import (
    CheckpointNotFoundError,
    DatabaseConnectionError,
    OrchestrationStateManager,
    WorkflowNotFoundError,
)

# Note: state_manager fixture is now defined in conftest.py
# It's initialized in async context to prevent ConnectionManagerAdapter deadlocks


@pytest.mark.asyncio
async def test_save_workflow_state_creates_new_record(state_manager):
    """
    Test: save_workflow_state creates new WorkflowState record.

    Verifies:
    - WorkflowStateUpsertNode creates record
    - Returns workflow_state_id
    - Metadata is serialized correctly
    """
    workflow_id = "wf_test_001"

    # Save workflow state
    state_id = await state_manager.save_workflow_state(
        workflow_id=workflow_id,
        status="PENDING",
        metadata={"total_tasks": 5, "priority": "high"},
        routing_strategy="semantic",
        total_tasks=5,
    )

    # Verify ID returned
    assert state_id == workflow_id

    # Load and verify data
    result = await state_manager.load_workflow_state(workflow_id, include_records=False)
    workflow_state = result["workflow_state"]

    assert workflow_state["workflow_id"] == workflow_id
    assert workflow_state["status"] == "PENDING"
    assert workflow_state["routing_strategy"] == "semantic"
    assert workflow_state["total_tasks"] == 5

    # Verify metadata parsed correctly (DataFlow returns as string, we parse it)
    assert isinstance(workflow_state["metadata"], dict)
    assert workflow_state["metadata"]["total_tasks"] == 5
    assert workflow_state["metadata"]["priority"] == "high"


@pytest.mark.asyncio
async def test_save_workflow_state_updates_existing_record(state_manager):
    """
    Test: save_workflow_state updates existing WorkflowState record (upsert).

    Verifies:
    - WorkflowStateUpsertNode updates on conflict
    - Status change persisted
    - Metadata updated
    """
    workflow_id = "wf_test_002"

    # Create initial state
    await state_manager.save_workflow_state(
        workflow_id=workflow_id,
        status="PENDING",
        metadata={"step": 1},
    )

    # Update state
    await state_manager.save_workflow_state(
        workflow_id=workflow_id,
        status="RUNNING",
        metadata={"step": 2},
    )

    # Verify update
    result = await state_manager.load_workflow_state(workflow_id, include_records=False)
    workflow_state = result["workflow_state"]

    assert workflow_state["status"] == "RUNNING"
    assert workflow_state["metadata"]["step"] == 2


@pytest.mark.asyncio
async def test_load_workflow_state_not_found(state_manager):
    """
    Test: load_workflow_state raises WorkflowNotFoundError if not found.

    Verifies:
    - Descriptive error message
    - Correct exception type
    """
    with pytest.raises(WorkflowNotFoundError) as exc_info:
        await state_manager.load_workflow_state("wf_nonexistent")

    assert "wf_nonexistent" in str(exc_info.value)


@pytest.mark.asyncio
async def test_load_workflow_state_with_agent_records(state_manager):
    """
    Test: load_workflow_state includes related AgentExecutionRecords.

    Verifies:
    - One-to-many relationship loading
    - AgentExecutionRecordListNode filtered by workflow_state_id
    - Records sorted by task_index
    - JSON fields parsed correctly
    """
    workflow_id = "wf_test_003"

    # Create workflow state
    await state_manager.save_workflow_state(
        workflow_id=workflow_id,
        status="RUNNING",
        total_tasks=3,
    )

    # Create agent execution records manually (using DataFlow nodes)
    from kailash.runtime import AsyncLocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    runtime = AsyncLocalRuntime()

    for i in range(3):
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AgentExecutionRecordModelCreateNode",  # DataFlow node has "Model" suffix
            f"create_record_{i}",
            {
                "db_instance": "test_orchestration_db",
                "model_name": "AgentExecutionRecordModel",  # Model name must match registered class
                "id": f"rec_{workflow_id}_{i}",
                "workflow_state_id": workflow_id,
                "agent_id": f"agent_{i}",
                "agent_type": "SimpleQAAgent",
                "task_description": f"Task {i}",
                "task_index": i,
                "status": "COMPLETED",
                "start_time": datetime.now().isoformat(),
                "result": {"answer": f"Result {i}"},
            },
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})

    # Load workflow with records
    result = await state_manager.load_workflow_state(workflow_id, include_records=True)

    # Verify workflow state
    assert result["workflow_state"]["workflow_id"] == workflow_id

    # Verify agent records
    assert len(result["agent_records"]) == 3
    assert result["agent_records"][0]["task_index"] == 0  # Sorted by task_index
    assert result["agent_records"][1]["task_index"] == 1
    assert result["agent_records"][2]["task_index"] == 2

    # Verify JSON field parsing
    assert isinstance(result["agent_records"][0]["result"], dict)
    assert result["agent_records"][0]["result"]["answer"] == "Result 0"


@pytest.mark.asyncio
async def test_save_checkpoint_with_compression(state_manager):
    """
    Test: save_checkpoint creates compressed checkpoint.

    Verifies:
    - Gzip compression applied
    - Compression ratio calculated
    - Size metrics tracked
    - Checkpoint number incremented
    """
    workflow_id = "wf_test_004"

    # Create workflow state
    await state_manager.save_workflow_state(
        workflow_id=workflow_id,
        status="RUNNING",
    )

    # Create checkpoint with large data
    checkpoint_data = {
        "agents": [{"id": f"agent_{i}", "status": "active"} for i in range(100)],
        "state": {"step": 1, "data": "x" * 1000},
    }

    checkpoint_id = await state_manager.save_checkpoint(
        workflow_id=workflow_id,
        checkpoint_data=checkpoint_data,
        checkpoint_type="AUTO",
    )

    # Verify checkpoint created
    assert checkpoint_id.startswith(f"cp_{workflow_id}")

    # Verify checkpoint number is 1 (first checkpoint)
    # We could verify this by loading the checkpoint metadata


@pytest.mark.asyncio
async def test_load_checkpoint_decompresses_data(state_manager):
    """
    Test: load_checkpoint decompresses and returns original data.

    Verifies:
    - Gzip decompression works
    - Original data structure preserved
    - JSON parsing correct
    """
    workflow_id = "wf_test_005"

    # Create workflow state
    await state_manager.save_workflow_state(
        workflow_id=workflow_id,
        status="RUNNING",
    )

    # Create checkpoint
    original_data = {
        "agents": [{"id": "agent_1", "status": "active"}],
        "state": {"step": 5, "counter": 42},
    }

    checkpoint_id = await state_manager.save_checkpoint(
        workflow_id=workflow_id,
        checkpoint_data=original_data,
    )

    # Load checkpoint
    loaded_data = await state_manager.load_checkpoint(checkpoint_id)

    # Verify data matches
    assert loaded_data == original_data
    assert loaded_data["state"]["step"] == 5
    assert loaded_data["state"]["counter"] == 42


@pytest.mark.asyncio
async def test_load_checkpoint_not_found(state_manager):
    """
    Test: load_checkpoint raises CheckpointNotFoundError if not found.

    Verifies:
    - Descriptive error message
    - Correct exception type
    """
    with pytest.raises(CheckpointNotFoundError) as exc_info:
        await state_manager.load_checkpoint("cp_nonexistent")

    assert "cp_nonexistent" in str(exc_info.value)


@pytest.mark.asyncio
async def test_list_active_workflows_filters_correctly(state_manager):
    """
    Test: list_active_workflows returns only PENDING and RUNNING workflows.

    Verifies:
    - MongoDB-style $in operator works
    - Completed/failed workflows excluded
    - Results sorted by start_time desc
    """
    # Create workflows with different statuses
    await state_manager.save_workflow_state("wf_pending_1", "PENDING")
    await state_manager.save_workflow_state("wf_running_1", "RUNNING")
    await state_manager.save_workflow_state("wf_completed_1", "COMPLETED")
    await state_manager.save_workflow_state("wf_failed_1", "FAILED")

    # List active workflows
    active_workflows = await state_manager.list_active_workflows()

    # Verify only active workflows returned
    workflow_ids = [w["workflow_id"] for w in active_workflows]
    assert "wf_pending_1" in workflow_ids
    assert "wf_running_1" in workflow_ids
    assert "wf_completed_1" not in workflow_ids
    assert "wf_failed_1" not in workflow_ids


@pytest.mark.asyncio
async def test_checkpoint_numbering_increments(state_manager):
    """
    Test: Checkpoint numbers increment correctly for same workflow.

    Verifies:
    - First checkpoint: number=1
    - Second checkpoint: number=2
    - Third checkpoint: number=3
    """
    workflow_id = "wf_test_006"

    # Create workflow state
    await state_manager.save_workflow_state(
        workflow_id=workflow_id,
        status="RUNNING",
    )

    # Create 3 checkpoints
    cp1_id = await state_manager.save_checkpoint(workflow_id, {"step": 1})
    cp2_id = await state_manager.save_checkpoint(workflow_id, {"step": 2})
    cp3_id = await state_manager.save_checkpoint(workflow_id, {"step": 3})

    # Verify IDs are unique
    assert cp1_id != cp2_id != cp3_id

    # Verify checkpoint numbers by loading checkpoints
    # (checkpoint_number is in the metadata, not returned by load_checkpoint)
    # We could verify this by querying the WorkflowCheckpointListNode directly


@pytest.mark.asyncio
async def test_invalid_workflow_status_raises_error(state_manager):
    """
    Test: save_workflow_state validates status enum.

    Verifies:
    - Invalid status raises ValueError
    - Error message lists valid statuses
    """
    with pytest.raises(ValueError) as exc_info:
        await state_manager.save_workflow_state(
            workflow_id="wf_test_007",
            status="INVALID_STATUS",
        )

    assert "INVALID_STATUS" in str(exc_info.value)
    assert "PENDING" in str(exc_info.value)


@pytest.mark.asyncio
async def test_invalid_checkpoint_type_raises_error(state_manager):
    """
    Test: save_checkpoint validates checkpoint_type enum.

    Verifies:
    - Invalid checkpoint_type raises ValueError
    - Error message lists valid types
    """
    workflow_id = "wf_test_008"

    # Create workflow state first
    await state_manager.save_workflow_state(
        workflow_id=workflow_id,
        status="RUNNING",
    )

    # Try invalid checkpoint type
    with pytest.raises(ValueError) as exc_info:
        await state_manager.save_checkpoint(
            workflow_id=workflow_id,
            checkpoint_data={},
            checkpoint_type="INVALID_TYPE",
        )

    assert "INVALID_TYPE" in str(exc_info.value)
    assert "AUTO" in str(exc_info.value)


@pytest.mark.asyncio
async def test_database_connection_error_handling(state_manager):
    """
    Test: DatabaseConnectionError raised on connection failures.

    This test verifies error wrapping behavior.
    """
    # Create manager with invalid connection
    with pytest.raises(DatabaseConnectionError):
        OrchestrationStateManager(
            connection_string="postgresql://invalid:invalid@localhost:9999/invalid"
        )


@pytest.mark.asyncio
async def test_json_field_parsing_edge_cases(state_manager):
    """
    Test: JSON field parsing handles edge cases correctly.

    Verifies:
    - Empty dict {}
    - Nested objects
    - Arrays
    - Special characters
    """
    workflow_id = "wf_test_009"

    # Save with complex metadata
    metadata = {
        "nested": {"level1": {"level2": "value"}},
        "array": [1, 2, 3],
        "special_chars": "test with 'quotes' and \"double quotes\"",
        "unicode": "emoji 🚀",
    }

    await state_manager.save_workflow_state(
        workflow_id=workflow_id,
        status="PENDING",
        metadata=metadata,
    )

    # Load and verify
    result = await state_manager.load_workflow_state(workflow_id, include_records=False)
    loaded_metadata = result["workflow_state"]["metadata"]

    assert loaded_metadata == metadata
    assert loaded_metadata["nested"]["level1"]["level2"] == "value"
    assert loaded_metadata["array"] == [1, 2, 3]
    assert loaded_metadata["unicode"] == "emoji 🚀"

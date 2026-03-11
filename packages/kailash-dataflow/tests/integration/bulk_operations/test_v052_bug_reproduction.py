"""
EXACT Reproduction of v0.5.2 Bugs

This file reproduces the EXACT bugs reported by the user in v0.5.2:
- Bug #1: BulkDeleteNode with empty filter fails during execution
- Bug #2: BulkCreateNode reports "Unsupported bulk operation: bulk_create"

These tests use WorkflowBuilder pattern with auto-generated DataFlow nodes
(not standalone node instantiation).
"""

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def setup_agent_memory_table(test_suite):
    """Create agent_memory table matching user's production schema."""
    connection_string = test_suite.config.url

    # Drop and create table with correct pluralized name
    # DataFlow converts AgentMemory -> agent_memorys (adds 's')
    drop_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="DROP TABLE IF EXISTS agent_memorys CASCADE",
        validate_queries=False,
    )
    await drop_node.async_run()
    await drop_node.cleanup()

    setup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="""
        CREATE TABLE agent_memorys (
            id SERIAL PRIMARY KEY,
            workflow_run_id INTEGER NOT NULL,
            agent_id VARCHAR(100) NOT NULL,
            memory_type VARCHAR(50) NOT NULL,
            key VARCHAR(100) NOT NULL,
            value JSONB NOT NULL,
            importance_score FLOAT DEFAULT 0.5,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        validate_queries=False,
    )
    await setup_node.async_run()
    await setup_node.cleanup()

    # Insert test data
    insert_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="""
        INSERT INTO agent_memorys (workflow_run_id, agent_id, memory_type, key, value, importance_score)
        VALUES
            (1, 'agent1', 'insight', 'key1', '{"data": "value1"}', 0.8),
            (1, 'agent1', 'insight', 'key2', '{"data": "value2"}', 0.7),
            (2, 'agent2', 'context', 'key3', '{"data": "value3"}', 0.6),
            (2, 'agent2', 'context', 'key4', '{"data": "value4"}', 0.5),
            (3, 'agent1', 'insight', 'key5', '{"data": "value5"}', 0.9)
        """,
        validate_queries=False,
    )
    await insert_node.async_run()
    await insert_node.cleanup()

    yield connection_string

    # Cleanup
    cleanup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="DROP TABLE IF EXISTS agent_memorys CASCADE",
        validate_queries=False,
    )
    await cleanup_node.async_run()
    await cleanup_node.cleanup()


class TestBug1_BulkDeleteEmptyFilter:
    """
    Bug #1: BulkDeleteNode with empty filter fails during execution

    Error: "Operation failed (no error details provided)"
    Root Cause: v0.5.2 fixed detection but execution still fails
    """

    @pytest.mark.asyncio
    async def test_bulk_delete_empty_filter_via_workflow(
        self, setup_agent_memory_table
    ):
        """
        EXACT reproduction from user's bug report.

        Expected: Should delete all records with filter={}
        Actual (v0.5.2): "Operation failed (no error details)"
        """
        connection_string = setup_agent_memory_table

        # Create DataFlow instance with auto-generated nodes
        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class AgentMemory:
            workflow_run_id: int
            agent_id: str
            memory_type: str
            key: str
            value: dict
            importance_score: float = 0.5

        # Use WorkflowBuilder with auto-generated BulkDeleteNode
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AgentMemoryBulkDeleteNode",
            "delete_all",
            {
                "filter": {},  # Empty filter = delete all
                "confirmed": True,
                "safe_mode": False,  # Disable safe mode
            },
        )

        runtime = LocalRuntime()

        # THIS SHOULD WORK but fails in v0.5.2 with "Operation failed"
        results, run_id = runtime.execute(workflow.build())

        delete_result = results.get("delete_all")
        assert delete_result is not None, "No result returned from bulk delete"

        # Should have deleted all 5 records
        assert delete_result.get(
            "success"
        ), f"Delete failed: {delete_result.get('error')}"
        assert (
            delete_result.get("deleted") == 5
        ), f"Expected 5 deleted, got {delete_result.get('deleted')}"

    @pytest.mark.asyncio
    async def test_bulk_delete_empty_filter_without_confirmation_fails(
        self, setup_agent_memory_table
    ):
        """
        Test that empty filter WITHOUT confirmed=True raises proper error.

        Expected: Clear validation error about missing confirmation
        Actual (v0.5.2): Generic "Operation failed" or unclear error
        """
        from kailash.sdk_exceptions import RuntimeExecutionError

        connection_string = setup_agent_memory_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class AgentMemory:
            workflow_run_id: int
            agent_id: str
            memory_type: str
            key: str
            value: dict
            importance_score: float = 0.5

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AgentMemoryBulkDeleteNode",
            "delete_all",
            {
                "filter": {},  # Empty filter
                # Missing confirmed=True - safe_mode defaults to True
            },
        )

        runtime = LocalRuntime()

        # Should raise RuntimeExecutionError with clear message about confirmation
        with pytest.raises(RuntimeExecutionError) as exc_info:
            results, run_id = runtime.execute(workflow.build())

        error_msg = str(exc_info.value)
        # Should fail with CLEAR error message
        assert (
            "confirmed" in error_msg.lower() or "confirmation" in error_msg.lower()
        ), f"Error should mention confirmation requirement, got: {error_msg}"
        assert (
            "empty filter" in error_msg.lower()
        ), f"Error should mention empty filter, got: {error_msg}"


class TestBug2_BulkCreateUnsupportedOperation:
    """
    Bug #2: BulkCreateNode reports "Unsupported bulk operation: bulk_create"

    Root Cause: Line 1799 still uses truthiness check on data
    Expected: Should work with data=[] or data parameter
    """

    @pytest.mark.asyncio
    async def test_bulk_create_with_data_via_workflow(self, setup_agent_memory_table):
        """
        EXACT reproduction from user's bug report.

        Expected: Should create 1 record
        Actual (v0.5.2): "Unsupported bulk operation: bulk_create"
        """
        connection_string = setup_agent_memory_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class AgentMemory:
            workflow_run_id: int
            agent_id: str
            memory_type: str
            key: str
            value: dict
            importance_score: float = 0.5

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AgentMemoryBulkCreateNode",
            "create",
            {
                "data": [  # Using 'data' parameter (not 'records')
                    {
                        "workflow_run_id": 100,
                        "agent_id": "test_agent",
                        "memory_type": "insight",
                        "key": "test_key",
                        "value": {"data": "test_value"},
                        "importance_score": 0.8,
                    }
                ]
            },
        )

        runtime = LocalRuntime()

        # THIS FAILS IN v0.5.2 with "Unsupported bulk operation: bulk_create"
        results, run_id = runtime.execute(workflow.build())

        create_result = results.get("create")
        assert create_result is not None, "No result returned from bulk create"

        # Should have created 1 record
        assert create_result.get(
            "success"
        ), f"Create failed: {create_result.get('error')}"
        assert (
            create_result.get("inserted") == 1
        ), f"Expected 1 inserted, got {create_result.get('inserted')}"

    @pytest.mark.asyncio
    async def test_bulk_create_with_empty_data_list(self, setup_agent_memory_table):
        """
        Test bulk_create with empty data list [].

        Expected: Should handle gracefully (either success with 0 or clear error)
        Actual (v0.5.2): "Unsupported bulk operation: bulk_create"
        """
        connection_string = setup_agent_memory_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class AgentMemory:
            workflow_run_id: int
            agent_id: str
            memory_type: str
            key: str
            value: dict
            importance_score: float = 0.5

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AgentMemoryBulkCreateNode",
            "create_empty",
            {"data": []},  # Empty list
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        create_result = results.get("create_empty")
        assert create_result is not None, "No result returned from bulk create"

        # Should either succeed with 0 inserted OR have clear error (not "Unsupported operation")
        if create_result.get("success"):
            assert (
                create_result.get("inserted", 0) == 0
            ), "Should have 0 insertions for empty data"
        else:
            error_msg = create_result.get("error", "")
            assert (
                "Unsupported bulk operation" not in error_msg
            ), f"Should not report 'Unsupported operation', got: {error_msg}"
            assert (
                "No data" in error_msg or "empty" in error_msg.lower()
            ), f"Error should mention empty data, got: {error_msg}"


class TestBug3_GenericErrorMessages:
    """
    Bug #3: Error messages lack debugging information

    Expected: Detailed error messages with context
    Actual (v0.5.2): "Operation failed (no error details provided)"
    """

    @pytest.mark.asyncio
    async def test_error_messages_provide_context(self, setup_agent_memory_table):
        """
        Test that errors include helpful debugging information.

        Expected: Error should include operation type, parameters, root cause
        Actual (v0.5.2): Generic "Operation failed"

        This test verifies that bulk operations with invalid parameters provide clear,
        detailed error messages rather than generic "Operation failed" messages.
        """
        from kailash.sdk_exceptions import RuntimeExecutionError

        connection_string = setup_agent_memory_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class AgentMemory:
            workflow_run_id: int
            agent_id: str
            memory_type: str
            key: str
            value: dict
            importance_score: float = 0.5

        # Test bulk_delete with empty filter but no confirmation
        # This should produce a detailed error about the confirmation requirement
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AgentMemoryBulkDeleteNode",
            "delete_without_confirm",
            {
                "filter": {},  # Empty filter without confirmation
            },
        )

        runtime = LocalRuntime()

        # Should raise RuntimeExecutionError with detailed message
        with pytest.raises(RuntimeExecutionError) as exc_info:
            results, run_id = runtime.execute(workflow.build())

        error_msg = str(exc_info.value)

        # Error should NOT be generic
        assert error_msg != "Operation failed", f"Error too generic: {error_msg}"
        assert (
            error_msg != "Operation failed (no error details provided)"
        ), f"No details provided: {error_msg}"

        # Error should mention what went wrong with specific details
        assert len(error_msg) > 20, f"Error message too short: {error_msg}"
        assert (
            "confirmed" in error_msg.lower()
        ), f"Error should mention 'confirmed' requirement: {error_msg}"
        assert (
            "empty filter" in error_msg.lower()
        ), f"Error should mention 'empty filter': {error_msg}"

"""
Quick verification test for async fixture pattern.

This test verifies that the StateManager fixture in conftest.py
correctly initializes in async context and uses AsyncLocalRuntime.
"""

import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_state_manager_async_initialization(state_manager):
    """
    Test that state_manager is correctly initialized in async context.

    Verifies:
    1. StateManager is created
    2. ConnectionManagerAdapter detects async context
    3. AsyncLocalRuntime is used (not LocalRuntime)
    """
    # Verify StateManager exists
    assert state_manager is not None, "StateManager should be initialized"

    # Verify ConnectionManagerAdapter async detection
    if (
        hasattr(state_manager.db, "_migration_system")
        and state_manager.db._migration_system is not None
    ):
        adapter = state_manager.db._migration_system._connection_adapter

        # Check async context detection
        assert adapter._is_async is True, (
            f"ConnectionManagerAdapter should detect async context. "
            f"Got _is_async={adapter._is_async}"
        )

        # Check runtime type
        from kailash.runtime import AsyncLocalRuntime

        assert isinstance(adapter._runtime, AsyncLocalRuntime), (
            f"Should use AsyncLocalRuntime in async context. "
            f"Got {type(adapter._runtime).__name__}"
        )

        print("✅ StateManager correctly initialized in async context")
        print(f"✅ ConnectionManagerAdapter._is_async = {adapter._is_async}")
        print(f"✅ Runtime type = {type(adapter._runtime).__name__}")
    else:
        pytest.skip("Migration system not initialized (test mode or disabled)")


@pytest.mark.asyncio
async def test_basic_workflow_state_operation(state_manager):
    """
    Test that basic workflow state operations work without deadlock.

    This is the key test - if it completes without timeout, the fix works.
    """
    import uuid

    workflow_id = f"test_verify_{uuid.uuid4().hex[:8]}"

    # Save workflow state (should not deadlock)
    state_id = await state_manager.save_workflow_state(
        workflow_id=workflow_id,
        status="PENDING",
        metadata={"test": "verify_async"},
        total_tasks=1,
    )

    assert state_id == workflow_id, f"Expected {workflow_id}, got {state_id}"

    # Load workflow state (should not deadlock)
    result = await state_manager.load_workflow_state(workflow_id, include_records=False)

    assert result["workflow_state"]["workflow_id"] == workflow_id
    assert result["workflow_state"]["status"] == "PENDING"

    print(f"✅ Successfully completed workflow state operations for {workflow_id}")
    print("✅ No deadlock occurred - async fixture pattern is working!")


if __name__ == "__main__":
    # Run with: pytest test_async_fixture.py -v -s
    pytest.main([__file__, "-v", "-s"])

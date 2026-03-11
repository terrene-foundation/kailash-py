"""
Minimal Reproduction Test: Event Loop Closure Bug in DataFlow 0.7.3

This test demonstrates the event loop closure bug that occurs when using
LocalRuntime with sequential DataFlow operations.

**Expected Behavior**: Both workflows should execute successfully.

**Actual Behavior**: First workflow succeeds, second workflow fails with
"Event loop is closed" error.

**Root Cause**: AsyncSQLDatabaseNode caches connection pools globally by
event loop ID. LocalRuntime creates a new event loop for each execute() call,
causing cache misses and stale pool references.

Date: 2025-10-27
Severity: HIGH - Blocks sequential database operations in tests
"""

import pytest
from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow


@pytest.mark.integration
@pytest.mark.bug_reproduction
class TestEventLoopClosureBug:
    """Minimal reproduction of the event loop closure bug."""

    def test_sequential_workflows_fail_with_localruntime(self):
        """
        BUG REPRODUCTION: Sequential workflows fail with LocalRuntime.

        Steps:
        1. Execute first workflow (CREATE) → SUCCESS ✅
        2. Execute second workflow (READ) → FAILURE ❌ "Event loop is closed"

        This test SHOULD FAIL until the bug is fixed.
        """
        # Setup: Create DataFlow instance with PostgreSQL
        db = DataFlow(
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
            auto_migrate=True,
        )

        # Register minimal model
        @db.model
        class TestUser:
            id: str
            name: str
            email: str

        # Initialize DataFlow (creates tables)
        import asyncio

        asyncio.run(db.initialize())

        # Runtime instance
        runtime = LocalRuntime()

        # ============================================================
        # WORKFLOW 1: CREATE - This should SUCCEED ✅
        # ============================================================
        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "TestUserCreateNode",
            "create",
            {"id": "test-user-1", "name": "Alice Test", "email": "alice@test.com"},
        )

        print("\n========== EXECUTING WORKFLOW 1 (CREATE) ==========")
        try:
            results1, run_id1 = runtime.execute(workflow1.build())
            print(f"✅ Workflow 1 SUCCESS: Created user {results1['create']['id']}")
            assert results1["create"]["id"] == "test-user-1"
        except Exception as e:
            pytest.fail(f"❌ Workflow 1 FAILED (unexpected): {e}")

        # ============================================================
        # WORKFLOW 2: READ - This should SUCCEED but FAILS ❌
        # ============================================================
        workflow2 = WorkflowBuilder()
        workflow2.add_node("TestUserReadNode", "read", {"id": "test-user-1"})

        print("\n========== EXECUTING WORKFLOW 2 (READ) ==========")
        try:
            results2, run_id2 = runtime.execute(workflow2.build())
            print(f"✅ Workflow 2 SUCCESS: Read user {results2['read']['name']}")
            assert results2["read"]["name"] == "Alice Test"
        except Exception as e:
            print(f"❌ Workflow 2 FAILED: {e}")

            # Validate error message confirms event loop closure
            error_msg = str(e).lower()
            assert (
                "event loop" in error_msg or "closed" in error_msg
            ), f"Expected 'event loop' or 'closed' in error, got: {e}"

            # This is the EXPECTED FAILURE until bug is fixed
            pytest.xfail(
                "BUG CONFIRMED: Event loop closure blocks sequential workflows"
            )

    def test_combined_workflow_succeeds_with_localruntime(self):
        """
        WORKAROUND VALIDATION: Combined workflow succeeds (same event loop).

        When both operations are in the SAME workflow, they share the same
        event loop and the bug does not occur.

        This test SHOULD PASS (demonstrates workaround).
        """
        # Setup
        db = DataFlow(
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
            auto_migrate=True,
        )

        @db.model
        class TestUser2:
            id: str
            name: str
            email: str

        import asyncio

        asyncio.run(db.initialize())

        # Single workflow with both CREATE and READ
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TestUser2CreateNode",
            "create",
            {"id": "test-user-2", "name": "Bob Test", "email": "bob@test.com"},
        )
        workflow.add_node("TestUser2ReadNode", "read", {"id": "test-user-2"})
        workflow.add_connection("create", "id", "read", "id")

        # Execute combined workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Both operations should succeed
        assert results["create"]["id"] == "test-user-2"
        assert results["read"]["name"] == "Bob Test"
        print("✅ Combined workflow SUCCESS: Both operations in same event loop")

    def test_asynclocalruntime_comparison(self):
        """
        COMPARISON TEST: Validate AsyncLocalRuntime behavior.

        AsyncLocalRuntime uses a persistent event loop, which SHOULD avoid
        the cache key mismatch issue.

        This test helps us understand production vs test behavior differences.
        """
        from kailash.runtime import AsyncLocalRuntime

        # Setup
        db = DataFlow(
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
            auto_migrate=True,
        )

        @db.model
        class TestUser3:
            id: str
            name: str
            email: str

        import asyncio

        asyncio.run(db.initialize())

        # Use AsyncLocalRuntime
        runtime = AsyncLocalRuntime()

        # Workflow 1: CREATE
        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "TestUser3CreateNode",
            "create",
            {"id": "test-user-3", "name": "Charlie Test", "email": "charlie@test.com"},
        )

        # Workflow 2: READ
        workflow2 = WorkflowBuilder()
        workflow2.add_node("TestUser3ReadNode", "read", {"id": "test-user-3"})

        # Execute both workflows with AsyncLocalRuntime
        async def run_test():
            results1, _ = await runtime.execute_workflow_async(
                workflow1.build(), inputs={}
            )
            print(
                f"✅ AsyncLocalRuntime Workflow 1 SUCCESS: {results1['create']['id']}"
            )

            results2, _ = await runtime.execute_workflow_async(
                workflow2.build(), inputs={}
            )
            print(
                f"✅ AsyncLocalRuntime Workflow 2 SUCCESS: {results2['read']['name']}"
            )

            return results1, results2

        results1, results2 = asyncio.run(run_test())

        assert results1["create"]["id"] == "test-user-3"
        assert results2["read"]["name"] == "Charlie Test"
        print("✅ AsyncLocalRuntime: Both sequential workflows succeeded")


@pytest.mark.integration
@pytest.mark.bug_investigation
class TestEventLoopCacheKeyValidation:
    """Validate the cache key hypothesis with empirical evidence."""

    def test_cache_key_differences_between_executions(self):
        """
        INVESTIGATION: Confirm that cache keys differ between LocalRuntime executions.

        This test instruments AsyncSQLDatabaseNode to capture actual cache keys
        generated during workflow execution.

        Expected: Different event loop IDs → Different cache keys
        """
        # Setup
        db = DataFlow(
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
            auto_migrate=True,
        )

        @db.model
        class TestUser4:
            id: str
            name: str

        import asyncio

        asyncio.run(db.initialize())

        runtime = LocalRuntime()

        # Patch _generate_pool_key to capture keys
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        original_generate = AsyncSQLDatabaseNode._generate_pool_key
        captured_keys = []

        def instrumented_generate(self):
            key = original_generate(self)
            captured_keys.append(key)
            print(f"CAPTURED POOL KEY: {key}")
            return key

        AsyncSQLDatabaseNode._generate_pool_key = instrumented_generate

        try:
            # Execute first workflow
            workflow1 = WorkflowBuilder()
            workflow1.add_node(
                "TestUser4CreateNode",
                "create1",
                {"id": "test-user-4a", "name": "User 4A"},
            )
            runtime.execute(workflow1.build())

            # Execute second workflow
            workflow2 = WorkflowBuilder()
            workflow2.add_node(
                "TestUser4CreateNode",
                "create2",
                {"id": "test-user-4b", "name": "User 4B"},
            )

            try:
                runtime.execute(workflow2.build())
            except Exception as e:
                print(f"Second workflow failed (expected): {e}")

            # Analyze captured keys
            print("\n========== CACHE KEY ANALYSIS ==========")
            print(f"Total keys captured: {len(captured_keys)}")
            for i, key in enumerate(captured_keys, 1):
                loop_id = key.split("|")[0]
                print(f"Execution {i} - Loop ID: {loop_id}")
                print(f"Full key: {key}\n")

            # Validate hypothesis: Different loop IDs
            if len(captured_keys) >= 2:
                key1_loop_id = captured_keys[0].split("|")[0]
                key2_loop_id = captured_keys[1].split("|")[0]

                print(f"Loop ID 1: {key1_loop_id}")
                print(f"Loop ID 2: {key2_loop_id}")
                print(f"Different loops: {key1_loop_id != key2_loop_id}")

                # This confirms the cache key hypothesis
                assert (
                    key1_loop_id != key2_loop_id
                ), "BUG: Expected different event loop IDs between executions"

                print("✅ HYPOTHESIS CONFIRMED: Different event loop IDs per execution")

        finally:
            # Restore original method
            AsyncSQLDatabaseNode._generate_pool_key = original_generate


if __name__ == "__main__":
    """
    Run minimal reproduction directly:

    $ python -m pytest tests/bug_reproduction/test_event_loop_closure_minimal.py -xvs

    Expected output:
    - test_sequential_workflows_fail_with_localruntime: XFAIL (bug confirmed)
    - test_combined_workflow_succeeds_with_localruntime: PASS (workaround works)
    - test_asynclocalruntime_comparison: PASS (production safe)
    - test_cache_key_differences_between_executions: PASS (hypothesis confirmed)
    """
    pytest.main([__file__, "-xvs"])

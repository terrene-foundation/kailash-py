"""
Minimal reproduction test for DATAFLOW-CACHE-ASYNC-001

This test confirms the async/await bug in ListNodeCacheIntegration
when used with InMemoryCache.
"""

import asyncio

from dataflow import DataFlow

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


async def test_list_node_cache_bug():
    """
    Reproduce the TypeError: 'coroutine' object does not support item assignment

    This bug occurs when:
    1. Redis is not available (InMemoryCache fallback)
    2. ListNode operations use cache
    3. ListNodeCacheIntegration calls async methods without await
    """
    print("=" * 80)
    print("DATAFLOW-CACHE-ASYNC-001: Reproduction Test")
    print("=" * 80)

    # Use in-memory database (no Redis)
    db = DataFlow(":memory:")

    # Define model
    @db.model
    class Session:
        id: str
        token_hash: str
        is_active: bool
        user_id: str

    # Initialize database
    await db.initialize()

    # Create a test session first
    create_workflow = WorkflowBuilder()
    create_workflow.add_node(
        "SessionCreateNode",
        "create_session",
        {
            "id": "sess-123",
            "token_hash": "test_hash",
            "is_active": True,
            "user_id": "user-456",
        },
    )

    runtime = AsyncLocalRuntime()
    create_results, _ = await runtime.execute_workflow_async(
        create_workflow.build(), inputs={}
    )
    print(f"\n✅ Created test session: {create_results['create_session']['id']}")

    # Now test ListNode with cache enabled (BUG TRIGGER)
    print("\n🔍 Testing ListNode with cache enabled...")
    print(
        "   This should trigger: TypeError: 'coroutine' object does not support item assignment"
    )
    print()

    workflow = WorkflowBuilder()
    workflow.add_node(
        "SessionListNode",
        "read_session",
        {
            "db_instance": None,  # Use default
            "model_name": "Session",
            "filter": {"token_hash": "test_hash", "is_active": True},
            "limit": 1,
            # enable_cache defaults to True - this triggers the bug!
        },
    )

    try:
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )
        print("❌ BUG NOT REPRODUCED - Test passed unexpectedly!")
        print(f"Results: {results}")
        return False
    except TypeError as e:
        if "'coroutine' object does not support item assignment" in str(e):
            print("✅ BUG CONFIRMED!")
            print(f"   Error: {e}")
            print("\n   This confirms the bug report:")
            print("   - InMemoryCache.get() returns unawaited coroutine")
            print("   - ListNodeCacheIntegration doesn't await it")
            print("   - _add_cache_metadata() tries to assign to coroutine object")
            return True
        else:
            print(f"❌ Different TypeError occurred: {e}")
            raise
    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")
        raise


async def test_with_cache_disabled_workaround():
    """
    Confirm the workaround (disable cache) works
    """
    print("\n" + "=" * 80)
    print("Testing Workaround: Disable Cache")
    print("=" * 80)

    db = DataFlow(":memory:")

    @db.model
    class Session:
        id: str
        token_hash: str
        is_active: bool
        user_id: str

    await db.initialize()

    # Create test session
    create_workflow = WorkflowBuilder()
    create_workflow.add_node(
        "SessionCreateNode",
        "create_session",
        {
            "id": "sess-123",
            "token_hash": "test_hash",
            "is_active": True,
            "user_id": "user-456",
        },
    )

    runtime = AsyncLocalRuntime()
    await runtime.execute_workflow_async(create_workflow.build(), inputs={})

    # Test with cache disabled (workaround)
    print("\n🔧 Testing ListNode with enable_cache=False...")

    workflow = WorkflowBuilder()
    workflow.add_node(
        "SessionListNode",
        "read_session",
        {
            "db_instance": None,
            "model_name": "Session",
            "filter": {"token_hash": "test_hash", "is_active": True},
            "limit": 1,
            "enable_cache": False,  # WORKAROUND: Disable cache
        },
    )

    try:
        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
        print("✅ WORKAROUND CONFIRMED - Works with cache disabled!")
        print(f"   Found {len(results.get('read_session', []))} sessions")
        return True
    except Exception as e:
        print(f"❌ Workaround failed: {e}")
        raise


async def main():
    """Run all reproduction tests"""
    print("\n" + "=" * 80)
    print("DATAFLOW-CACHE-ASYNC-001: Bug Reproduction Suite")
    print("=" * 80)
    print()

    # Test 1: Reproduce bug
    bug_confirmed = await test_list_node_cache_bug()

    # Test 2: Confirm workaround
    workaround_works = await test_with_cache_disabled_workaround()

    # Summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Bug Reproduced:      {'✅ YES' if bug_confirmed else '❌ NO'}")
    print(f"Workaround Works:    {'✅ YES' if workaround_works else '❌ NO'}")
    print()

    if bug_confirmed:
        print("Root Cause:")
        print("  1. CacheBackend.auto_detect() falls back to InMemoryCache (async)")
        print(
            "  2. ListNodeCacheIntegration.execute_with_cache() calls cache methods WITHOUT await"
        )
        print("  3. InMemoryCache.get() returns unawaited coroutine")
        print(
            "  4. _add_cache_metadata() tries to assign to coroutine object → TypeError"
        )
        print()
        print("Affected Nodes:")
        print(
            "  - All DataFlow-generated ListNodes (SessionListNode, UserListNode, etc.)"
        )
        print()
        print("Suggested Fix:")
        print("  - Make ListNodeCacheIntegration properly await async cache methods")
        print("  - OR detect cache backend type and use appropriate sync/async calls")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

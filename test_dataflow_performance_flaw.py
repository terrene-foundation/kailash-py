"""
Test to validate the DataFlow migration loop performance flaw.

This test demonstrates the critical design flaw where ensure_table_exists()
is called on EVERY database operation without any caching, causing
10-11 workflow executions per operation.
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# Setup logging to see the migration workflows
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Add DataFlow to path
sys.path.insert(0, str(Path(__file__).parent / "apps/kailash-dataflow/src"))

from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime


async def test_performance_issue():
    """
    Demonstrate the performance issue with a simple create operation.

    Expected: <100ms for 2 INSERT operations
    Actual: 1000-2000ms+ due to migration workflows
    """
    print("\n" + "="*80)
    print("DataFlow Migration Loop Performance Test")
    print("="*80)

    # Create temporary database
    import tempfile
    db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_url = f"sqlite:///{db_file.name}"

    print(f"\nDatabase: {db_url}")
    print(f"Testing: Simple CREATE operation (2 records)")
    print(f"Expected time: <100ms")
    print("-"*80)

    # Initialize DataFlow
    print("\n1. Initializing DataFlow instance...")
    start = time.time()
    db = DataFlow(db_url)
    init_time = time.time() - start
    print(f"   ✓ Initialization: {init_time*1000:.0f}ms")

    # Define simple model
    print("\n2. Defining User model...")
    @db.model
    class User:
        id: str
        name: str
        email: str

    print("   ✓ Model defined")

    # Test 1: First CREATE operation
    print("\n3. First CREATE operation (will trigger migration)...")
    print("   Expected: Migration runs once (~500-1000ms)")
    workflow1 = WorkflowBuilder()
    workflow1.add_node("UserCreateNode", "create_user_1", {
        "id": "user-1",
        "name": "Alice",
        "email": "alice@example.com"
    })

    runtime = LocalRuntime()
    start = time.time()
    results1, _ = runtime.execute(workflow1.build())
    create1_time = time.time() - start
    print(f"   ✓ First CREATE: {create1_time*1000:.0f}ms")

    # Test 2: Second CREATE operation (the problem!)
    print("\n4. Second CREATE operation (table already exists)...")
    print("   Expected: <10ms (just INSERT, table exists)")
    print("   Actual: Will show if migration runs AGAIN (the bug!)")
    workflow2 = WorkflowBuilder()
    workflow2.add_node("UserCreateNode", "create_user_2", {
        "id": "user-2",
        "name": "Bob",
        "email": "bob@example.com"
    })

    start = time.time()
    results2, _ = runtime.execute(workflow2.build())
    create2_time = time.time() - start
    print(f"   ✓ Second CREATE: {create2_time*1000:.0f}ms")

    # Test 3: Third CREATE operation
    print("\n5. Third CREATE operation...")
    workflow3 = WorkflowBuilder()
    workflow3.add_node("UserCreateNode", "create_user_3", {
        "id": "user-3",
        "name": "Charlie",
        "email": "charlie@example.com"
    })

    start = time.time()
    results3, _ = runtime.execute(workflow3.build())
    create3_time = time.time() - start
    print(f"   ✓ Third CREATE: {create3_time*1000:.0f}ms")

    # Analysis
    print("\n" + "="*80)
    print("PERFORMANCE ANALYSIS")
    print("="*80)

    print(f"\nFirst CREATE:  {create1_time*1000:.0f}ms (migration expected)")
    print(f"Second CREATE: {create2_time*1000:.0f}ms")
    print(f"Third CREATE:  {create3_time*1000:.0f}ms")

    # Check for the bug
    ACCEPTABLE_THRESHOLD = 100  # ms

    if create2_time * 1000 > ACCEPTABLE_THRESHOLD:
        print(f"\n❌ BUG CONFIRMED: Second operation took {create2_time*1000:.0f}ms")
        print(f"   Table already exists, should be <{ACCEPTABLE_THRESHOLD}ms")
        print(f"   Performance degradation: {(create2_time*1000/10):.0f}x slower than expected")
        print(f"\n   This confirms NO CACHING of table existence checks!")
        print(f"   Migration workflows run on EVERY operation!")
        return False
    else:
        print(f"\n✅ FIXED: Second operation took only {create2_time*1000:.0f}ms")
        print(f"   Caching appears to be working!")
        return True

    # Cleanup
    import os
    os.unlink(db_file.name)


if __name__ == "__main__":
    print("\nStarting DataFlow Performance Flaw Validation Test...")
    print("This test will demonstrate if migration workflows run on every operation.\n")

    # Run test
    result = asyncio.run(test_performance_issue())

    if not result:
        print("\n" + "="*80)
        print("CRITICAL FLAW CONFIRMED")
        print("="*80)
        print("\nRecommendation: Implement _ensured_tables caching as proposed in report.")
        sys.exit(1)
    else:
        print("\n" + "="*80)
        print("ISSUE RESOLVED")
        print("="*80)
        sys.exit(0)

"""
Test to replicate BulkDeleteNode closure bug.
Expected: BulkDeleteNode should delete from actual database.
Actual: BulkDeleteNode deletes from :memory: database (bug).
"""

import tempfile
from pathlib import Path

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow


def test_bulk_delete_bug():
    """Replicate the BulkDeleteNode bug."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_url = f"sqlite:///{db_path}"
        print(f"\n=== Testing with database: {db_url} ===\n")

        # 1. Create DataFlow instance with file-based SQLite database
        db = DataFlow(database_url=db_url, auto_migrate=True)

        # 2. Define and register model
        @db.model
        class TestMessage:
            id: str
            conversation_id: str
            content: str

        # 3. Create test records
        print("Step 1: Creating 5 test records...")
        workflow = WorkflowBuilder()
        for i in range(5):
            workflow.add_node(
                "TestMessageCreateNode",
                f"create_{i}",
                {
                    "id": f"msg_{i}",
                    "conversation_id": "session_123",
                    "content": f"Message {i}",
                },
            )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())
        print("✓ Created 5 records\n")

        # 4. Verify records exist
        print("Step 2: Verifying records exist...")
        list_workflow = WorkflowBuilder()
        list_workflow.add_node(
            "TestMessageListNode",
            "list_messages",
            {
                "filter": {"conversation_id": "session_123"},
                "enable_cache": False,  # Disable cache for accurate count
            },
        )
        results, _ = runtime.execute(list_workflow.build())
        count_before = len(results["list_messages"]["records"])
        print(f"✓ Found {count_before} records before deletion\n")

        # 5. Attempt bulk delete
        print("Step 3: Attempting bulk delete...")
        delete_workflow = WorkflowBuilder()
        delete_workflow.add_node(
            "TestMessageBulkDeleteNode",
            "bulk_delete",
            {
                "filter": {"conversation_id": "session_123"},
                "safe_mode": False,
            },
        )

        results, _ = runtime.execute(delete_workflow.build())
        delete_result = results["bulk_delete"]
        print(f"Delete result: {delete_result}\n")

        # 6. Verify deletion
        print("Step 4: Verifying deletion...")
        list_workflow2 = WorkflowBuilder()
        list_workflow2.add_node(
            "TestMessageListNode",
            "list_after_delete",
            {
                "filter": {"conversation_id": "session_123"},
                "enable_cache": False,  # Disable cache to see fresh data
            },
        )
        results, _ = runtime.execute(list_workflow2.build())
        count_after = len(results["list_after_delete"]["records"])
        print(f"Found {count_after} records after deletion\n")

        # 7. Verify the bug
        print("=== BUG VERIFICATION ===")
        print(f"Records before delete: {count_before}")
        print(f"Records after delete: {count_after}")
        print(f"Delete result: {delete_result}")

        if count_after == 0:
            print("\n✅ BUG IS FIXED: Bulk delete worked correctly!")
            return True
        else:
            print("\n❌ BUG CONFIRMED: Records still exist after bulk delete!")
            print("   Expected: 0 records")
            print(f"   Actual: {count_after} records")
            print(
                "   This confirms the bug - BulkDeleteNode is using :memory: database"
            )
            return False


if __name__ == "__main__":
    test_bulk_delete_bug()

"""
Direct SQLite check to verify if DELETE actually persists.
"""

import asyncio
import sqlite3
import tempfile
from pathlib import Path

from dataflow import DataFlow


async def test_direct_sqlite_check():
    """Test if DELETE persists to the database file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_url = f"sqlite:///{db_path}"
        print(f"\n=== Testing with database: {db_url} ===\n")

        # 1. Create DataFlow instance
        db = DataFlow(database_url=db_url, auto_migrate=True)

        # 2. Define model
        @db.model
        class TestMessage:
            id: str
            conversation_id: str
            content: str

        # 3. Create records using workflows (which triggers table creation)
        print("Step 1: Creating 5 test records using workflows...")
        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

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

        # 5. Check with direct SQLite connection BEFORE delete
        print("Step 2: Direct SQLite check BEFORE delete...")
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT COUNT(*) FROM test_messages WHERE conversation_id = 'session_123'"
        )
        count_before = cursor.fetchone()[0]
        conn.close()
        print(f"✓ Direct SQLite shows {count_before} records BEFORE delete\n")

        # 6. Delete using bulk API
        print("Step 3: Executing bulk delete...")
        delete_result = await db.bulk.bulk_delete(
            model_name="TestMessage",
            filter_criteria={"conversation_id": "session_123"},
            safe_mode=False,
        )
        print(f"Delete result: {delete_result}\n")

        # 7. Check with direct SQLite connection AFTER delete
        print("Step 4: Direct SQLite check AFTER delete...")
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT COUNT(*) FROM test_messages WHERE conversation_id = 'session_123'"
        )
        count_after = cursor.fetchone()[0]
        cursor2 = conn.execute("SELECT * FROM test_messages")
        all_rows = cursor2.fetchall()
        conn.close()
        print(f"Records remaining: {count_after}")
        print(f"All rows in table: {all_rows}\n")

        # 8. Verify
        print("=== RESULT ==")
        print(f"Direct SQLite BEFORE: {count_before}")
        print(f"Direct SQLite AFTER: {count_after}")
        print(f"Delete success_count: {delete_result.get('success_count', 0)}")

        if count_after == 0:
            print("\n✅ SUCCESS: DELETE persisted to database file!")
            return True
        else:
            print("\n❌ FAILURE: DELETE did not persist!")
            return False


if __name__ == "__main__":
    asyncio.run(test_direct_sqlite_check())

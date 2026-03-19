#!/usr/bin/env python3
"""Final comprehensive fix for remaining unit test issues."""

import os
import re
import sys
from pathlib import Path

# Fix 1: test_migration_trigger_system.py - Mock DataFlow._initialize_database properly
MIGRATION_TRIGGER_FIX = """
# Add proper mocking for DataFlow initialization
import unittest.mock as mock

# Patch at module level to prevent real database connections
mock.patch('dataflow.core.engine.create_engine', mock.MagicMock()).start()
mock.patch('dataflow.adapters.postgresql.asyncpg', mock.MagicMock()).start()
mock.patch('dataflow.adapters.postgresql.create_async_engine', mock.MagicMock()).start()
"""

# Fix 2: test_migration_history_manager.py - Fix AsyncMock usage
HISTORY_MANAGER_FIXES = [
    # Fix mock_connection setup
    (
        "mock_connection = AsyncMock()",
        """mock_connection = Mock()
        mock_connection.execute = AsyncMock()
        mock_connection.fetch = AsyncMock()
        mock_connection.fetchrow = AsyncMock()
        mock_connection.fetchall = AsyncMock()
        mock_connection.fetchone = AsyncMock()""",
    ),
]

# Fix 3: test_batched_migration_executor_integration.py - Fix undefined variables
EXECUTOR_FIXES = [
    # Add missing mock_pool_connection definition
    (
        "async def test_execute_batch_sequential_with_retry_success",
        '''async def test_execute_batch_sequential_with_retry_success(self, executor_with_manager, connection_manager):
        """Test sequential execution with retry logic that eventually succeeds."""
        sql_statements = ["CREATE TABLE test (id INTEGER)"]
        mock_pool_connection = Mock()''',
    ),
]


def apply_fixes():
    """Apply all fixes to test files."""

    # Fix test_migration_trigger_system.py
    trigger_file = Path("")
    if trigger_file.exists():
        with open(trigger_file, "r") as f:
            content = f.read()

        # Add module-level patches after imports if not already present
        if "mock.patch('dataflow.core.engine.create_engine" not in content:
            # Find the import section
            import_end = content.find("class TestMigrationTriggerSystem")
            if import_end > 0:
                content = (
                    content[:import_end]
                    + MIGRATION_TRIGGER_FIX
                    + "\n\n"
                    + content[import_end:]
                )
                with open(trigger_file, "w") as f:
                    f.write(content)
                print(f"Fixed {trigger_file.name}")

    # Fix test_migration_history_manager.py
    history_file = Path("")
    if history_file.exists():
        with open(history_file, "r") as f:
            content = f.read()

        # Replace simple AsyncMock() with proper setup
        content = re.sub(
            r"mock_connection = AsyncMock\(\)\s*\n",
            """mock_connection = Mock()
        mock_connection.execute = AsyncMock()
        mock_connection.fetch = AsyncMock()
        mock_connection.fetchrow = AsyncMock()
        mock_connection.fetchall = AsyncMock()
        mock_connection.fetchone = AsyncMock()
        mock_connection.cursor = Mock()
        """,
            content,
        )

        with open(history_file, "w") as f:
            f.write(content)
        print(f"Fixed {history_file.name}")

    # Fix test_batched_migration_executor_integration.py
    executor_file = Path("")
    if executor_file.exists():
        with open(executor_file, "r") as f:
            lines = f.readlines()

        modified = False
        for i, line in enumerate(lines):
            # Fix missing mock_pool_connection in retry test
            if "async def test_execute_batch_sequential_with_retry_success" in line:
                # Check next few lines for mock_pool_connection
                found = False
                for j in range(i, min(i + 10, len(lines))):
                    if "mock_pool_connection" in lines[j]:
                        found = True
                        break

                if not found:
                    # Insert after sql_statements line
                    for j in range(i, min(i + 10, len(lines))):
                        if "sql_statements = " in lines[j]:
                            lines.insert(
                                j + 1, "        mock_pool_connection = Mock()\n"
                            )
                            modified = True
                            break

        if modified:
            with open(executor_file, "w") as f:
                f.writelines(lines)
            print(f"Fixed {executor_file.name}")

    print("\n✅ Applied final fixes to unit tests")
    return 0


if __name__ == "__main__":
    sys.exit(apply_fixes())

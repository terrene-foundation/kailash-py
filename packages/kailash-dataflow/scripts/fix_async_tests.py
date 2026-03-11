#!/usr/bin/env python3
"""
Fix all async mock issues in DataFlow tests.

This script systematically fixes async context manager and mock issues.
"""

import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
TESTS_DIR = BASE_DIR / "tests"


def fix_async_mock_patterns(content: str) -> str:
    """Fix common async mock patterns in tests."""

    # Pattern 1: Mock cursor needs to be AsyncMock with async execute
    content = re.sub(
        r"mock_cursor = Mock\(\)",
        "mock_cursor = AsyncMock()\n        mock_cursor.execute = AsyncMock()",
        content,
    )

    # Pattern 2: Add async context managers for cursor
    if (
        "mock_cursor_ctx = AsyncMock()" not in content
        and "mock_connection.cursor" in content
    ):
        # Find places where we need to add async context manager
        pattern = r"(mock_connection\.cursor\.return_value = )(Mock\(\)|mock_cursor)"
        replacement = r"""mock_cursor_ctx = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.execute = AsyncMock()
        mock_cursor_ctx.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_connection.cursor.return_value = mock_cursor_ctx"""

        content = re.sub(pattern, replacement, content)

    # Pattern 3: Add async context managers for transaction
    if (
        "mock_transaction = AsyncMock()" not in content
        and "connection.transaction" in content
    ):
        pattern = r"(mock_connection\.transaction\.return_value = )(Mock\(\))"
        replacement = r"""mock_transaction = AsyncMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
        mock_transaction.__aexit__ = AsyncMock(return_value=None)
        mock_connection.transaction.return_value = mock_transaction"""

        content = re.sub(pattern, replacement, content)

    return content


def fix_batched_executor_tests(file_path: Path) -> bool:
    """Fix batched migration executor test issues."""
    with open(file_path, "r") as f:
        content = f.read()

    original = content

    # Fix all remaining test methods that need async mocks
    test_methods = [
        "test_execute_batch_sequential_with_retry_success",
        "test_execute_batch_parallel_with_manager",
        "test_execute_single_statement_with_connection_and_manager",
        "test_execute_single_statement_without_manager",
        "test_error_handling_with_connection_cleanup",
    ]

    for method in test_methods:
        # Find the test method
        pattern = rf"(async def {method}\([^)]+\):.*?)(mock_cursor = Mock\(\)|mock_pool_connection = Mock\(\))"

        def replacer(match):
            prefix = match.group(1)
            # Add proper async mocking setup
            return (
                prefix
                + """# Setup async context managers for mock connection
        mock_transaction = AsyncMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
        mock_transaction.__aexit__ = AsyncMock(return_value=None)

        mock_cursor_ctx = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.execute = AsyncMock()
        mock_cursor_ctx.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor_ctx.__aexit__ = AsyncMock(return_value=None)"""
            )

        content = re.sub(pattern, replacer, content, flags=re.DOTALL)

    if content != original:
        with open(file_path, "w") as f:
            f.write(content)
        return True
    return False


def fix_migration_connection_manager_tests(file_path: Path) -> bool:
    """Fix migration connection manager test issues."""
    with open(file_path, "r") as f:
        content = f.read()

    original = content

    # Fix execute_with_retry tests
    if "test_execute_with_retry" in content:
        # These tests need proper async mock setup
        content = re.sub(
            r"mock_operation = Mock\(\)", "mock_operation = AsyncMock()", content
        )

        # Fix side_effect for async operations
        content = re.sub(
            r'mock_operation\.side_effect = \[Exception\("Retry 1"\), Exception\("Retry 2"\), None\]',
            'mock_operation.side_effect = [Exception("Retry 1"), Exception("Retry 2"), None]',
            content,
        )

    if content != original:
        with open(file_path, "w") as f:
            f.write(content)
        return True
    return False


def fix_migration_history_tests(file_path: Path) -> bool:
    """Fix migration history manager test issues."""
    with open(file_path, "r") as f:
        content = f.read()

    original = content

    # These tests need the execute method to be properly mocked
    if "mock_connection.execute" in content:
        content = re.sub(
            r"mock_connection = Mock\(\)",
            "mock_connection = AsyncMock()\n        mock_connection.execute = AsyncMock()",
            content,
        )

    # Fix fetch methods
    content = re.sub(
        r"mock_connection\.fetch\.return_value",
        "mock_connection.fetch = AsyncMock()\n        mock_connection.fetch.return_value",
        content,
    )

    if content != original:
        with open(file_path, "w") as f:
            f.write(content)
        return True
    return False


def main():
    """Main execution."""
    print("🔧 Fixing async test issues...")

    # Fix batched executor tests
    executor_test = (
        TESTS_DIR / "unit" / "test_batched_migration_executor_integration.py"
    )
    if executor_test.exists():
        if fix_batched_executor_tests(executor_test):
            print(f"✅ Fixed {executor_test.name}")

    # Fix connection manager tests
    conn_mgr_test = TESTS_DIR / "unit" / "test_migration_connection_manager.py"
    if conn_mgr_test.exists():
        if fix_migration_connection_manager_tests(conn_mgr_test):
            print(f"✅ Fixed {conn_mgr_test.name}")

    # Fix history manager tests
    history_test = TESTS_DIR / "unit" / "test_migration_history_manager.py"
    if history_test.exists():
        if fix_migration_history_tests(history_test):
            print(f"✅ Fixed {history_test.name}")

    # Fix trigger system tests
    trigger_test = TESTS_DIR / "unit" / "test_migration_trigger_system.py"
    if trigger_test.exists():
        with open(trigger_test, "r") as f:
            content = f.read()

        original = content
        content = fix_async_mock_patterns(content)

        if content != original:
            with open(trigger_test, "w") as f:
                f.write(content)
            print(f"✅ Fixed {trigger_test.name}")

    print("\n📊 Running tests to verify fixes...")
    os.system("python -m pytest tests/unit --tb=no -q --timeout=1 2>&1 | tail -3")


if __name__ == "__main__":
    main()

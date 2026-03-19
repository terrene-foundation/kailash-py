#!/usr/bin/env python3
"""
Fix remaining unit test issues in DataFlow.

This script fixes:
1. AsyncMock import issues
2. Missing fixture references
3. Test parameter mismatches
4. Mock setup issues for async context managers
"""

import os
import re
import sys
from pathlib import Path


def fix_asyncmock_imports(file_path):
    """Fix AsyncMock import issues."""
    with open(file_path, "r") as f:
        content = f.read()

    # Check if AsyncMock is used but not imported
    if "AsyncMock" in content and "from unittest.mock import" in content:
        # Find the import line
        import_pattern = r"from unittest\.mock import ([^\\n]+)"
        match = re.search(import_pattern, content)
        if match:
            imports = match.group(1)
            if "AsyncMock" not in imports:
                # Add AsyncMock to imports
                imports_list = [i.strip() for i in imports.split(",")]
                if "AsyncMock" not in imports_list:
                    imports_list.append("AsyncMock")
                    new_imports = ", ".join(imports_list)
                    content = re.sub(
                        import_pattern,
                        f"from unittest.mock import {new_imports}",
                        content,
                    )
                    with open(file_path, "w") as f:
                        f.write(content)
                    print(f"Fixed AsyncMock import in {file_path}")
                    return True
    return False


def fix_fixture_references(file_path):
    """Fix missing fixture references in test methods."""
    with open(file_path, "r") as f:
        content = f.read()

    # Pattern for test methods using undefined fixtures
    patterns_to_fix = [
        # Fix schema_cache fixture reference
        (
            r"def test_get_cached_schema_respects_ttl_expiration\(self, schema_cache\):",
            "def test_get_cached_schema_respects_ttl_expiration(self):",
        ),
    ]

    modified = False
    for pattern, replacement in patterns_to_fix:
        if re.search(pattern, content):
            content = re.sub(pattern, replacement, content)
            modified = True

    if modified:
        with open(file_path, "w") as f:
            f.write(content)
        print(f"Fixed fixture references in {file_path}")
        return True
    return False


def fix_mock_cursor_setup(file_path):
    """Fix mock cursor setup for async operations."""
    with open(file_path, "r") as f:
        content = f.read()

    # Fix cursor context manager setup
    patterns_to_fix = [
        # Fix duplicate mock setup
        (
            r"mock_cursor_ctx\.__aenter__ = AsyncMock\(return_value=mock_cursor\)\s+mock_cursor_ctx\.__aexit__ = AsyncMock\(return_value=None\)\s+mock_cursor = Mock\(\)\s+mock_pool_connection\.cursor\.return_value = mock_cursor",
            "mock_cursor_ctx.__aenter__ = AsyncMock(return_value=mock_cursor)\\nmock_cursor_ctx.__aexit__ = AsyncMock(return_value=None)\\nmock_pool_connection.cursor.return_value = mock_cursor_ctx",
        ),
    ]

    modified = False
    for pattern, replacement in patterns_to_fix:
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            modified = True

    if modified:
        with open(file_path, "w") as f:
            f.write(content)
        print(f"Fixed mock cursor setup in {file_path}")
        return True
    return False


def fix_undefined_variables(file_path):
    """Fix undefined variable issues."""
    with open(file_path, "r") as f:
        lines = f.readlines()

    modified = False
    new_lines = []

    for i, line in enumerate(lines):
        # Check for undefined mock_pool_connection
        if "mock_pool_connection" in line and i > 0:
            # Check if it's defined in the function
            func_start = i
            while func_start > 0 and not lines[func_start].strip().startswith("def "):
                func_start -= 1

            func_content = "".join(lines[func_start:i])
            if (
                "mock_pool_connection = " not in func_content
                and "mock_pool_connection = Mock()" not in func_content
            ):
                # Add definition before first use
                if "sql_statements = " in lines[i - 1]:
                    new_lines.append(lines[i - 1])
                    new_lines.append("        mock_pool_connection = Mock()\n")
                    modified = True
                    continue

        new_lines.append(line)

    if modified:
        with open(file_path, "w") as f:
            f.writelines(new_lines)
        print(f"Fixed undefined variables in {file_path}")
        return True
    return False


def main():
    """Main function to fix all unit test issues."""
    test_dir = Path("")

    if not test_dir.exists():
        print(f"Test directory not found: {test_dir}")
        return 1

    fixed_count = 0

    # Process all Python test files
    for test_file in test_dir.rglob("test_*.py"):
        if fix_asyncmock_imports(test_file):
            fixed_count += 1
        if fix_fixture_references(test_file):
            fixed_count += 1
        if fix_mock_cursor_setup(test_file):
            fixed_count += 1
        if fix_undefined_variables(test_file):
            fixed_count += 1

    print(f"\nFixed {fixed_count} issues in unit tests")

    # Run unit tests to verify fixes
    print("\nRunning unit tests to verify fixes...")
    os.chdir("")
    result = os.system("python -m pytest tests/unit/ -x --tb=short --quiet")

    if result == 0:
        print("\n✅ All unit tests passing!")
    else:
        print(f"\n❌ Some tests still failing. Exit code: {result}")

    return result


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Script to fix remaining test failures in DataFlow.

This systematically identifies and fixes common test issues.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

BASE_DIR = Path(__file__).parent.parent
TESTS_DIR = BASE_DIR / "tests"


def run_tests_and_get_failures() -> List[Dict]:
    """Run tests and parse failure output."""
    cmd = ["python", "-m", "pytest", "tests/unit", "--tb=short", "-q", "--timeout=1"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR)

    failures = []
    lines = result.stdout.split("\n")

    for line in lines:
        if "FAILED" in line:
            # Parse test path and test name
            parts = line.split("::")
            if len(parts) >= 2:
                test_file = parts[0].replace("FAILED ", "")
                test_name = "::".join(parts[1:])
                failures.append({"file": test_file, "test": test_name, "full": line})

    return failures


def fix_mock_connection_issues(file_path: Path) -> bool:
    """Fix MockConnection not defined errors."""
    try:
        with open(file_path, "r") as f:
            content = f.read()

        original = content

        # Add MockConnection class if missing
        if "MockConnection" in content and "class MockConnection" not in content:
            mock_class = '''
class MockConnection:
    """Mock connection for testing."""
    def __init__(self, conn_id):
        self.id = conn_id
        self.closed = False

    def close(self):
        self.closed = True

    def cursor(self):
        return Mock()

'''
            # Add after imports
            import_end = content.find("\n\n\nclass")
            if import_end > 0:
                content = (
                    content[:import_end] + "\n" + mock_class + content[import_end:]
                )

        # Fix unittest style assertions
        content = re.sub(
            r"self\.assertEqual\((.*?),\s*(.*?)\)", r"assert \1 == \2", content
        )
        content = re.sub(
            r"self\.assertIn\((.*?),\s*(.*?)\)", r"assert \1 in \2", content
        )
        content = re.sub(r"self\.assertIsNone\((.*?)\)", r"assert \1 is None", content)
        content = re.sub(
            r"self\.assertIsNotNone\((.*?)\)", r"assert \1 is not None", content
        )
        content = re.sub(r"self\.assertTrue\((.*?)\)", r"assert \1", content)
        content = re.sub(r"self\.assertFalse\((.*?)\)", r"assert not \1", content)

        # Fix missing ConnectionPriority references
        content = re.sub(r"self\.ConnectionPriority\.", "ConnectionPriority.", content)

        # Fix missing self references in pytest tests
        content = re.sub(r"self\.connection_manager", "connection_manager", content)
        content = re.sub(
            r"self\.connection_pool", "connection_manager._connection_pool", content
        )

        if content != original:
            with open(file_path, "w") as f:
                f.write(content)
            return True

        return False
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False


def fix_import_errors(file_path: Path) -> bool:
    """Fix import errors for DataFlow modules."""
    try:
        with open(file_path, "r") as f:
            content = f.read()

        original = content

        # Ensure ConnectionPriority is imported if used
        if (
            "ConnectionPriority" in content
            and "from dataflow.migrations.migration_connection_manager import"
            in content
        ):
            import_line = "from dataflow.migrations.migration_connection_manager import"
            if (
                "ConnectionPriority"
                not in content[
                    content.find(import_line) : content.find(
                        "\n", content.find(import_line)
                    )
                ]
            ):
                # Add ConnectionPriority to imports
                content = re.sub(
                    r"(from dataflow\.migrations\.migration_connection_manager import \([\s\S]*?)\)",
                    r"\1,\n    ConnectionPriority)",
                    content,
                )

        if content != original:
            with open(file_path, "w") as f:
                f.write(content)
            return True

        return False
    except Exception as e:
        print(f"Error fixing imports in {file_path}: {e}")
        return False


def main():
    """Main execution."""
    print("🔧 Fixing remaining test failures...")

    # Get current failures
    failures = run_tests_and_get_failures()
    print(f"Found {len(failures)} test failures to fix")

    # Group failures by file
    files_to_fix = {}
    for failure in failures:
        file_path = failure["file"]
        if file_path not in files_to_fix:
            files_to_fix[file_path] = []
        files_to_fix[file_path].append(failure["test"])

    # Fix each file
    fixed_count = 0
    for file_path, tests in files_to_fix.items():
        full_path = BASE_DIR / file_path
        if full_path.exists():
            print(f"\nFixing {file_path} ({len(tests)} failing tests)...")

            # Apply fixes
            fixed = False
            if "migration_connection_manager" in file_path:
                fixed = fix_mock_connection_issues(full_path) or fixed
                fixed = fix_import_errors(full_path) or fixed

            if fixed:
                print(f"  ✅ Applied fixes to {file_path}")
                fixed_count += 1

    print(f"\n📊 Summary: Fixed {fixed_count} files")

    # Run tests again to check improvement
    print("\n🧪 Running tests to verify fixes...")
    cmd = ["python", "-m", "pytest", "tests/unit", "--tb=no", "-q", "--timeout=1"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR)

    # Parse results
    output_lines = result.stdout.split("\n")
    for line in output_lines:
        if "passed" in line and "failed" in line:
            print(f"\n📈 Test Results: {line}")
            break


if __name__ == "__main__":
    main()

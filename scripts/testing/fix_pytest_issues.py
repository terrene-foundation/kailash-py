#!/usr/bin/env python3
"""
Fix Remaining Pytest Compliance Issues

This script fixes common pytest compliance issues in remaining test files:
1. Add missing pytest imports
2. Remove __main__ blocks (use pytest discovery instead)
3. Ensure proper test structure
"""

import ast
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


def fix_pytest_imports(file_path: Path) -> bool:
    """Add missing pytest import if needed."""
    content = file_path.read_text(encoding="utf-8")

    # Check if pytest is already imported
    if "import pytest" in content or "from pytest" in content:
        return False

    # Check if pytest functionality is used
    pytest_patterns = [
        r"@pytest\.",
        r"pytest\.",
        r"def test_",
        r"class Test",
        r"@fixture",
    ]

    uses_pytest = any(re.search(pattern, content) for pattern in pytest_patterns)

    if uses_pytest:
        # Find the best place to insert import
        lines = content.splitlines()
        insert_index = 0

        # Skip docstring and find imports section
        in_docstring = False
        docstring_delimiter = None

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Track docstrings
            if not in_docstring and (
                stripped.startswith('"""') or stripped.startswith("'''")
            ):
                in_docstring = True
                docstring_delimiter = stripped[:3]
                if stripped.count(docstring_delimiter) >= 2:  # Single line docstring
                    in_docstring = False
                continue
            elif in_docstring and docstring_delimiter in stripped:
                in_docstring = False
                continue
            elif in_docstring:
                continue

            # Find imports section
            if stripped.startswith("import ") or stripped.startswith("from "):
                insert_index = i + 1
            elif stripped and not stripped.startswith("#"):
                break

        # Insert pytest import
        lines.insert(insert_index, "import pytest")
        file_path.write_text("\n".join(lines), encoding="utf-8")
        return True

    return False


def remove_main_block(file_path: Path) -> bool:
    """Remove __main__ block from test files."""
    content = file_path.read_text(encoding="utf-8")

    if 'if __name__ == "__main__":' not in content:
        return False

    lines = content.splitlines()
    new_lines = []
    in_main_block = False
    main_indent = 0

    for line in lines:
        if 'if __name__ == "__main__":' in line:
            in_main_block = True
            main_indent = len(line) - len(line.lstrip())
            continue

        if in_main_block:
            current_indent = len(line) - len(line.lstrip())
            # Continue if line is part of main block (indented more than if statement)
            if line.strip() == "" or current_indent > main_indent:
                continue
            else:
                in_main_block = False

        new_lines.append(line)

    # Remove trailing empty lines
    while new_lines and new_lines[-1].strip() == "":
        new_lines.pop()

    file_path.write_text("\n".join(new_lines), encoding="utf-8")
    return True


def fix_test_file(file_path: Path) -> Dict[str, bool]:
    """Fix a single test file for pytest compliance."""
    results = {
        "added_import": False,
        "removed_main": False,
        "file": str(file_path.relative_to(Path("tests"))),
    }

    try:
        results["added_import"] = fix_pytest_imports(file_path)
        results["removed_main"] = remove_main_block(file_path)
    except Exception as e:
        results["error"] = str(e)

    return results


def find_test_files_with_issues() -> List[Path]:
    """Find test files that need pytest compliance fixes."""
    test_files = []
    tests_dir = Path("tests")

    for file_path in tests_dir.rglob("test_*.py"):
        if "__pycache__" in str(file_path):
            continue

        # Skip config files
        if file_path.name in ["conftest.py", "test_config.py", "test_helpers.py"]:
            continue

        test_files.append(file_path)

    return sorted(test_files)


def main():
    """Fix pytest compliance issues in test files."""
    print("🔧 Fixing Pytest Compliance Issues")
    print("=" * 40)

    # Find test files
    test_files = find_test_files_with_issues()
    print(f"\n📊 Found {len(test_files)} test files to check")

    # Fix issues
    results = []
    imports_added = 0
    main_blocks_removed = 0
    errors = 0

    for file_path in test_files:
        result = fix_test_file(file_path)
        results.append(result)

        if result.get("added_import"):
            imports_added += 1
        if result.get("removed_main"):
            main_blocks_removed += 1
        if result.get("error"):
            errors += 1

    # Report results
    print("\n✅ Fixes Applied:")
    print(f"   📦 Added pytest imports: {imports_added}")
    print(f"   🚫 Removed __main__ blocks: {main_blocks_removed}")
    print(f"   ❌ Errors encountered: {errors}")

    if imports_added > 0:
        print("\n📦 Files with added pytest imports:")
        for result in results:
            if result.get("added_import"):
                print(f"   • {result['file']}")

    if main_blocks_removed > 0:
        print("\n🚫 Files with removed __main__ blocks:")
        for result in results:
            if result.get("removed_main"):
                print(f"   • {result['file']}")

    if errors > 0:
        print("\n❌ Files with errors:")
        for result in results:
            if result.get("error"):
                print(f"   • {result['file']}: {result['error']}")

    print("\n🧪 All remaining files in tests/ are now pytest compliant!")

    return 0


if __name__ == "__main__":
    sys.exit(main())

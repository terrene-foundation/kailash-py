#!/usr/bin/env python3
"""Fix broken try blocks in test files."""

import re
from pathlib import Path


def fix_broken_try_blocks(file_path: Path):
    """Fix broken try blocks by removing incomplete try statements."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        original_content = content
        lines = content.split("\n")
        fixed_lines = []

        i = 0
        while i < len(lines):
            line = lines[i]

            # Look for pattern: try: followed by pass and comment, then actual code
            if (
                re.match(r"^\s*try:\s*$", line)
                and i + 1 < len(lines)
                and i + 2 < len(lines)
                and "pass" in lines[i + 1]
                and lines[i + 2].strip().startswith("#")
            ):

                # Skip the try, pass, and comment lines
                i += 3

                # Continue with the actual code that was intended
                continue
            else:
                fixed_lines.append(line)
                i += 1

        content = "\n".join(fixed_lines)

        if content != original_content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Fixed broken try blocks in: {file_path}")
            return True

        return False

    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False


def main():
    test_dir = Path("tests/unit")
    error_files = [
        "test_access_control.py",
        "test_async_sql_parameter_types.py",
        "test_base_with_acl.py",
        "test_connection_actor_functional.py",
        "test_core_coverage_boost.py",
        "test_data_retention_functional.py",
        "test_deferred_configuration.py",
        "test_enterprise_parameter_injection.py",
        "test_enterprise_parameter_injection_comprehensive.py",
        "test_pythoncode_default_params.py",
    ]

    fixes_applied = 0
    for filename in error_files:
        file_path = test_dir / filename
        if file_path.exists():
            if fix_broken_try_blocks(file_path):
                fixes_applied += 1
        else:
            print(f"File not found: {file_path}")

    print(f"\nTotal files fixed: {fixes_applied}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Complete Test Reorganization

This script completes the test reorganization by moving remaining files.
"""

import os
import shutil
from pathlib import Path


def move_remaining_tests():
    """Move any remaining test files from old directories."""
    old_dirs = [
        "tests/test_api",
        "tests/test_cli",
        "tests/test_enterprise",
        "tests/test_middleware",
        "tests/test_nodes",
        "tests/test_refactored_architecture",
        "tests/test_runtime",
        "tests/test_schema",
        "tests/test_security",
        "tests/test_tracking",
        "tests/test_utils",
        "tests/test_validation",
        "tests/test_visualization",
        "tests/test_workflow",
    ]

    moved_count = 0

    for old_dir in old_dirs:
        if not os.path.exists(old_dir):
            continue

        for root, dirs, files in os.walk(old_dir):
            for file in files:
                if file == "__init__.py" or file.endswith(".pyc"):
                    continue

                if file.endswith(".py"):
                    source = os.path.join(root, file)

                    # Determine target based on path
                    if "enterprise" in root:
                        if "security" in root:
                            target_dir = "tests/integration/enterprise/security"
                        elif "auth" in root:
                            target_dir = "tests/integration/enterprise/auth"
                        elif "compliance" in root:
                            target_dir = "tests/integration/enterprise/compliance"
                        else:
                            target_dir = "tests/integration/enterprise"
                    elif "test_nodes" in old_dir:
                        target_dir = "tests/unit/nodes"
                    elif "test_workflow" in old_dir:
                        target_dir = "tests/unit/workflow"
                    elif "test_runtime" in old_dir:
                        target_dir = "tests/unit/runtime"
                    elif "test_middleware" in old_dir:
                        target_dir = "tests/unit/middleware"
                    else:
                        # Extract category from directory name
                        category = old_dir.replace("tests/test_", "")
                        target_dir = f"tests/unit/{category}"

                    os.makedirs(target_dir, exist_ok=True)
                    target = os.path.join(target_dir, file)

                    if os.path.exists(target):
                        print(f"Skipping (already exists): {source}")
                        continue

                    print(f"Moving: {source} -> {target}")
                    shutil.move(source, target)
                    moved_count += 1

    return moved_count


def remove_old_directories():
    """Remove old test directories after moving files."""
    old_dirs = [
        "tests/test_api",
        "tests/test_cli",
        "tests/test_enterprise",
        "tests/test_middleware",
        "tests/test_nodes",
        "tests/test_refactored_architecture",
        "tests/test_runtime",
        "tests/test_schema",
        "tests/test_security",
        "tests/test_tracking",
        "tests/test_utils",
        "tests/test_validation",
        "tests/test_visualization",
        "tests/test_workflow",
    ]

    removed_count = 0

    for old_dir in old_dirs:
        if os.path.exists(old_dir):
            try:
                shutil.rmtree(old_dir)
                print(f"Removed directory: {old_dir}")
                removed_count += 1
            except Exception as e:
                print(f"Error removing {old_dir}: {e}")

    return removed_count


def create_missing_init_files():
    """Create __init__.py files in all test directories."""
    created_count = 0

    for root, dirs, files in os.walk("tests"):
        if "__pycache__" in root:
            continue

        init_file = os.path.join(root, "__init__.py")
        if not os.path.exists(init_file):
            Path(init_file).touch()
            print(f"Created: {init_file}")
            created_count += 1

    return created_count


def main():
    """Main function."""
    print("Completing test reorganization...\n")

    # Move remaining tests
    moved = move_remaining_tests()
    print(f"\nMoved {moved} remaining test files")

    # Remove old directories
    removed = remove_old_directories()
    print(f"Removed {removed} old directories")

    # Create __init__.py files
    created = create_missing_init_files()
    print(f"Created {created} __init__.py files")

    print("\nReorganization complete!")


if __name__ == "__main__":
    main()

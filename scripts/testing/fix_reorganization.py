#!/usr/bin/env python3
"""
Fix Reorganization Issues

This script fixes incorrectly created directories with .py extensions.
"""

import os
import shutil
from pathlib import Path


def fix_py_directories():
    """Find and fix directories ending with .py"""
    fixes_made = 0

    # Find all directories ending with .py
    for root, dirs, files in os.walk("tests"):
        for dir_name in list(dirs):  # Use list() to avoid modifying while iterating
            if dir_name.endswith(".py"):
                dir_path = os.path.join(root, dir_name)

                # Look for test files inside this directory
                for file in os.listdir(dir_path):
                    if file.endswith(".py") and file != "__init__.py":
                        source_file = os.path.join(dir_path, file)

                        # Move the file up one level
                        parent_dir = os.path.dirname(dir_path)
                        target_file = os.path.join(parent_dir, file)

                        print(f"Moving: {source_file} -> {target_file}")
                        if os.path.exists(target_file):
                            print(f"  Warning: {target_file} already exists, skipping")
                            continue

                        shutil.move(source_file, target_file)
                        fixes_made += 1

                # Try to remove the directory after moving files
                try:
                    # Remove __init__.py if it exists
                    init_file = os.path.join(dir_path, "__init__.py")
                    if os.path.exists(init_file):
                        os.remove(init_file)

                    # Remove any __pycache__ directories
                    pycache_dir = os.path.join(dir_path, "__pycache__")
                    if os.path.exists(pycache_dir):
                        shutil.rmtree(pycache_dir)

                    # Now try to remove the empty directory
                    os.rmdir(dir_path)
                    print(f"Removed directory: {dir_path}")
                except OSError as e:
                    print(f"  Warning: Could not remove {dir_path}: {e}")

    return fixes_made


def cleanup_empty_dirs():
    """Remove empty directories"""
    removed = 0

    # Walk bottom-up to remove empty dirs
    for root, dirs, files in os.walk("tests", topdown=False):
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            try:
                if not os.listdir(dir_path):
                    os.rmdir(dir_path)
                    print(f"Removed empty directory: {dir_path}")
                    removed += 1
            except OSError:
                pass

    return removed


def create_init_files():
    """Create __init__.py files in all test directories"""
    created = 0

    for root, dirs, files in os.walk("tests"):
        # Skip __pycache__ directories
        if "__pycache__" in root:
            continue

        init_file = os.path.join(root, "__init__.py")
        if not os.path.exists(init_file):
            Path(init_file).touch()
            print(f"Created: {init_file}")
            created += 1

    return created


def main():
    print("Fixing test reorganization issues...\n")

    # Fix .py directories
    fixes = fix_py_directories()
    print(f"\nFixed {fixes} incorrectly created directories")

    # Clean up empty directories
    removed = cleanup_empty_dirs()
    print(f"Removed {removed} empty directories")

    # Create __init__.py files
    created = create_init_files()
    print(f"Created {created} __init__.py files")

    print("\nReorganization fixes complete!")


if __name__ == "__main__":
    main()

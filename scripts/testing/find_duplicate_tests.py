#!/usr/bin/env python3
"""
Find Duplicate Test Files

This script finds test files with duplicate names or similar content.

Usage:
    python scripts/testing/find_duplicate_tests.py
"""

import hashlib
import os
from collections import defaultdict
from pathlib import Path


def get_file_hash(file_path: str) -> str:
    """Get MD5 hash of file content."""
    with open(file_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def find_duplicate_tests():
    """Find duplicate test files by name and content."""
    # Track files by name and content hash
    files_by_name = defaultdict(list)
    files_by_content = defaultdict(list)

    # Search for test files
    test_patterns = ["test_*.py", "*_test.py"]
    search_dirs = ["tests", "examples"]

    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue

        for root, dirs, files in os.walk(search_dir):
            for file in files:
                # Check if it's a test file
                if any(
                    file.endswith(pattern.replace("*", ""))
                    or file.startswith(pattern.replace("*", "").replace(".py", ""))
                    for pattern in test_patterns
                ):

                    file_path = os.path.join(root, file)
                    file_name = os.path.basename(file)

                    # Track by name
                    files_by_name[file_name].append(file_path)

                    # Track by content
                    try:
                        file_hash = get_file_hash(file_path)
                        files_by_content[file_hash].append(file_path)
                    except Exception as e:
                        print(f"Error reading {file_path}: {e}")

    # Report duplicates by name
    print("=== Duplicate Test Files by Name ===\n")
    duplicate_count = 0
    for file_name, paths in files_by_name.items():
        if len(paths) > 1:
            duplicate_count += 1
            print(f"{file_name}:")
            for path in paths:
                print(f"  - {path}")
            print()

    if duplicate_count == 0:
        print("No duplicate file names found.\n")
    else:
        print(f"Found {duplicate_count} files with duplicate names.\n")

    # Report duplicates by content
    print("=== Duplicate Test Files by Content ===\n")
    content_duplicate_count = 0
    for file_hash, paths in files_by_content.items():
        if len(paths) > 1:
            content_duplicate_count += 1
            print("Files with identical content:")
            for path in paths:
                print(f"  - {path}")
            print()

    if content_duplicate_count == 0:
        print("No files with identical content found.\n")
    else:
        print(
            f"Found {content_duplicate_count} sets of files with identical content.\n"
        )

    # Summary
    print("=== Summary ===")
    print(
        f"Total test files scanned: {sum(len(paths) for paths in files_by_name.values())}"
    )
    print(f"Duplicate file names: {duplicate_count}")
    print(f"Duplicate content sets: {content_duplicate_count}")


if __name__ == "__main__":
    find_duplicate_tests()

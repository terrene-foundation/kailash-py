#!/usr/bin/env python3
"""Fix AsyncMock import issues in test files."""

import os
import re
from pathlib import Path


def fix_asyncmock_import(file_path):
    """Fix AsyncMock import corruption in file."""
    with open(file_path, "r") as f:
        content = f.read()

    # Fix various corrupted AsyncMock patterns
    patterns = [
        (
            r"from unittest\.mock import ([^,]*,\s*)?Asy,\s*AsyncMockncMock",
            r"from unittest.mock import \1AsyncMock",
        ),
        (
            r"from unittest\.mock import Asy,\s*AsyncMockncMock",
            r"from unittest.mock import AsyncMock",
        ),
        (r",\s*Asy,\s*AsyncMockncMock", ", AsyncMock"),
        # Add AsyncMock if missing but used
        (
            r"from unittest\.mock import ((?!AsyncMock)[^\\n]+)$",
            lambda m: (
                f"from unittest.mock import {m.group(1)}, AsyncMock"
                if "AsyncMock" in content and "AsyncMock" not in m.group(1)
                else m.group(0)
            ),
        ),
    ]

    modified = False
    for pattern, replacement in patterns:
        if re.search(pattern, content, re.MULTILINE):
            if callable(replacement):
                content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            else:
                content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            modified = True

    if modified:
        with open(file_path, "w") as f:
            f.write(content)
        return True
    return False


def main():
    test_dir = Path(
        ""
    )

    fixed_files = []
    for test_file in test_dir.rglob("test_*.py"):
        if fix_asyncmock_import(test_file):
            fixed_files.append(test_file.name)
            print(f"Fixed: {test_file.name}")

    print(f"\n✅ Fixed {len(fixed_files)} files")
    return 0


if __name__ == "__main__":
    main()

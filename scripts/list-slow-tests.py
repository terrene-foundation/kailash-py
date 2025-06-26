#!/usr/bin/env python3
"""List all unit tests that have sleep/timeout calls."""

import os
import re


def has_sleep_or_timeout(file_path):
    """Check if a test file contains sleep or timeout calls."""
    try:
        with open(file_path, "r") as f:
            content = f.read()

        # Check for various sleep patterns
        sleep_patterns = [
            r"time\.sleep\s*\(",
            r"asyncio\.sleep\s*\(",
            r"await\s+asyncio\.sleep\s*\(",
            r"sleep\s*\(",
        ]

        for pattern in sleep_patterns:
            if re.search(pattern, content):
                return True

        return False
    except Exception:
        return False


def main():
    """Find all unit test files with sleep/timeout calls."""
    slow_tests = []

    test_dir = "tests/unit"
    if os.path.exists(test_dir):
        for root, dirs, files in os.walk(test_dir):
            for file in files:
                if file.startswith("test_") and file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    if has_sleep_or_timeout(file_path):
                        # Convert to module path
                        rel_path = os.path.relpath(file_path, "tests/unit")
                        module_path = rel_path.replace(os.sep, ".")[:-3]  # Remove .py
                        slow_tests.append(f"tests/unit/{rel_path}")

    print("# Unit tests with sleep/timeout calls that should be excluded from CI:")
    for test in sorted(slow_tests):
        print(test)

    print(f"\n# Total: {len(slow_tests)} files")


if __name__ == "__main__":
    main()

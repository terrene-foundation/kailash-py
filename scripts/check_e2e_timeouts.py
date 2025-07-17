#!/usr/bin/env python3
"""
Script to check E2E tests for potential timeout issues.
"""

import re
import sys
from pathlib import Path


def check_file(file_path):
    """Check a single file for timeout issues."""
    issues = []

    with open(file_path, "r") as f:
        lines = f.readlines()

    for i, line in enumerate(lines, 1):
        # Check for large iteration counts
        if match := re.search(r"range\((\d{3,})\)", line):
            count = int(match.group(1))
            if count >= 100:
                issues.append(
                    {
                        "file": file_path,
                        "line": i,
                        "issue": f"Large iteration count: range({count})",
                        "content": line.strip(),
                    }
                )

        # Check for long sleeps
        if match := re.search(r"sleep\((\d+\.?\d*)\)", line):
            duration = float(match.group(1))
            if duration >= 1.0:
                issues.append(
                    {
                        "file": file_path,
                        "line": i,
                        "issue": f"Long sleep: sleep({duration})",
                        "content": line.strip(),
                    }
                )

        # Check for high worker counts
        if match := re.search(r"max_workers=(\d+)", line):
            workers = int(match.group(1))
            if workers >= 20:
                issues.append(
                    {
                        "file": file_path,
                        "line": i,
                        "issue": f"High worker count: max_workers={workers}",
                        "content": line.strip(),
                    }
                )

        # Check for long test durations
        if "minutes" in line and ("duration" in line or "timeout" in line):
            if match := re.search(r"(\d+)\s*\*?\s*60", line):
                minutes = int(match.group(1))
                if minutes >= 1:
                    issues.append(
                        {
                            "file": file_path,
                            "line": i,
                            "issue": f"Long duration: {minutes} minutes",
                            "content": line.strip(),
                        }
                    )

    return issues


def main():
    """Main function."""
    e2e_dir = Path("tests/e2e")

    all_issues = []

    # Find all Python test files
    test_files = list(e2e_dir.rglob("test_*.py"))

    print(f"Checking {len(test_files)} E2E test files for timeout issues...\n")

    for test_file in sorted(test_files):
        issues = check_file(test_file)
        all_issues.extend(issues)

    if all_issues:
        print(f"Found {len(all_issues)} potential timeout issues:\n")

        current_file = None
        for issue in all_issues:
            if issue["file"] != current_file:
                current_file = issue["file"]
                print(f"\n{current_file.relative_to('tests/e2e')}:")

            print(f"  Line {issue['line']}: {issue['issue']}")
            print(f"    {issue['content']}")
    else:
        print("✅ No timeout issues found!")

    return len(all_issues)


if __name__ == "__main__":
    sys.exit(main())

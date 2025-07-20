#!/usr/bin/env python3
"""Script to analyze and help fix sleep calls in tests.

This script scans test files for sleep patterns and provides recommendations
for replacing them with proper synchronization techniques.

Usage:
    python tests/utils/fix_test_sleeps.py [--fix] [--check]

    --check: Exit with error code if problematic sleeps are found (for CI)
    --fix: Attempt to automatically fix simple cases (experimental)
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


class SleepPattern:
    """Represents a sleep pattern found in code."""

    def __init__(
        self, file_path: str, line_num: int, line: str, sleep_type: str, duration: float
    ):
        self.file_path = file_path
        self.line_num = line_num
        self.line = line.strip()
        self.sleep_type = sleep_type
        self.duration = duration
        self.has_comment = "#" in line
        self.comment = ""
        if self.has_comment:
            self.comment = line.split("#", 1)[1].strip()

    @property
    def severity(self) -> str:
        """Categorize severity based on duration."""
        if self.duration >= 1.0:
            return "CRITICAL"
        elif self.duration >= 0.5:
            return "MODERATE"
        else:
            return "LOW"

    def __str__(self):
        return f"{self.file_path}:{self.line_num} [{self.severity}] {self.sleep_type}({self.duration})"


def find_sleep_patterns(directory: str) -> List[SleepPattern]:
    """Find all sleep patterns in test files."""
    patterns = []

    # Regular expressions for different sleep patterns
    time_sleep_re = re.compile(r"time\.sleep\s*\(\s*([0-9.]+)\s*\)")
    asyncio_sleep_re = re.compile(r"await\s+asyncio\.sleep\s*\(\s*([0-9.]+)\s*\)")
    pg_sleep_re = re.compile(r"pg_sleep\s*\(\s*([0-9.]+)\s*\)")

    for root, dirs, files in os.walk(directory):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != "__pycache__"]

        for file in files:
            if file.endswith(".py") and file.startswith("test_"):
                file_path = os.path.join(root, file)

                with open(file_path, "r") as f:
                    for line_num, line in enumerate(f, 1):
                        # Check for time.sleep
                        match = time_sleep_re.search(line)
                        if match:
                            duration = float(match.group(1))
                            patterns.append(
                                SleepPattern(
                                    file_path, line_num, line, "time.sleep", duration
                                )
                            )

                        # Check for asyncio.sleep
                        match = asyncio_sleep_re.search(line)
                        if match:
                            duration = float(match.group(1))
                            patterns.append(
                                SleepPattern(
                                    file_path, line_num, line, "asyncio.sleep", duration
                                )
                            )

                        # Check for pg_sleep
                        match = pg_sleep_re.search(line)
                        if match:
                            duration = float(match.group(1))
                            patterns.append(
                                SleepPattern(
                                    file_path, line_num, line, "pg_sleep", duration
                                )
                            )

    return patterns


def categorize_patterns(patterns: List[SleepPattern]) -> Dict[str, List[SleepPattern]]:
    """Categorize patterns by type and severity."""
    categories = {
        "critical": [],
        "moderate": [],
        "low": [],
        "pg_sleep": [],
        "justified": [],
    }

    for pattern in patterns:
        # PostgreSQL sleeps are special
        if pattern.sleep_type == "pg_sleep":
            categories["pg_sleep"].append(pattern)
        # Patterns with explanatory comments might be justified
        elif pattern.has_comment and any(
            word in pattern.comment.lower()
            for word in [
                "simulate",
                "test",
                "delay",
                "wait",
                "timeout",
                "backoff",
                "rate",
            ]
        ):
            categories["justified"].append(pattern)
        # Categorize by severity
        elif pattern.severity == "CRITICAL":
            categories["critical"].append(pattern)
        elif pattern.severity == "MODERATE":
            categories["moderate"].append(pattern)
        else:
            categories["low"].append(pattern)

    return categories


def suggest_fix(pattern: SleepPattern) -> str:
    """Suggest a fix for a sleep pattern."""
    if pattern.sleep_type == "pg_sleep":
        return "PostgreSQL sleep - usually acceptable for timeout testing"

    # Check comment for context
    if pattern.has_comment:
        comment_lower = pattern.comment.lower()

        if "startup" in comment_lower or "service" in comment_lower:
            return "Use wait_for_http_health() or wait_for_port()"
        elif (
            "cache" in comment_lower
            or "ttl" in comment_lower
            or "expir" in comment_lower
        ):
            return "Use CacheTestHelper with shorter TTL"
        elif "container" in comment_lower or "docker" in comment_lower:
            return "Use wait_for_container_health()"
        elif "completion" in comment_lower or "finish" in comment_lower:
            return "Use EventWaiter or wait_for_condition()"
        elif "database" in comment_lower or "connection" in comment_lower:
            return "Use wait_for_database_ready()"

    # Generic suggestions based on duration
    if pattern.duration >= 1.0:
        return "Replace with condition-based waiting using wait_for_condition()"
    elif pattern.duration >= 0.5:
        return "Consider using wait_for_condition() with shorter timeout"
    else:
        return "May be acceptable if simulating realistic delays"


def print_report(categories: Dict[str, List[SleepPattern]]):
    """Print analysis report."""
    print("=" * 80)
    print("TEST SLEEP ANALYSIS REPORT")
    print("=" * 80)
    print()

    # Summary
    total = sum(len(patterns) for patterns in categories.values())
    print(f"Total sleep patterns found: {total}")
    print(f"  Critical (>= 1s): {len(categories['critical'])}")
    print(f"  Moderate (0.5-0.9s): {len(categories['moderate'])}")
    print(f"  Low (< 0.5s): {len(categories['low'])}")
    print(f"  PostgreSQL sleeps: {len(categories['pg_sleep'])}")
    print(f"  Justified (commented): {len(categories['justified'])}")
    print()

    # Critical issues
    if categories["critical"]:
        print("CRITICAL ISSUES - Fix these first:")
        print("-" * 80)
        for pattern in sorted(
            categories["critical"], key=lambda p: p.duration, reverse=True
        ):
            print(f"\n{pattern}")
            print(f"  Line: {pattern.line}")
            print(f"  Fix: {suggest_fix(pattern)}")

    # Moderate issues
    if categories["moderate"]:
        print("\n\nMODERATE ISSUES - Consider fixing:")
        print("-" * 80)
        for pattern in sorted(
            categories["moderate"], key=lambda p: p.duration, reverse=True
        ):
            print(f"\n{pattern}")
            print(f"  Line: {pattern.line}")
            print(f"  Fix: {suggest_fix(pattern)}")

    # Summary by file
    print("\n\nFILES WITH MOST SLEEP CALLS:")
    print("-" * 80)
    file_counts = {}
    for category_patterns in categories.values():
        for pattern in category_patterns:
            file_counts[pattern.file_path] = file_counts.get(pattern.file_path, 0) + 1

    for file_path, count in sorted(
        file_counts.items(), key=lambda x: x[1], reverse=True
    )[:10]:
        print(f"{count:3d} sleeps in {file_path}")


def main():
    parser = argparse.ArgumentParser(description="Analyze sleep patterns in tests")
    parser.add_argument(
        "--check", action="store_true", help="Exit with error if critical sleeps found"
    )
    parser.add_argument(
        "--fix", action="store_true", help="Attempt to fix simple cases (experimental)"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    # Find test directories
    test_dirs = ["tests/integration", "tests/e2e"]

    all_patterns = []
    for test_dir in test_dirs:
        if os.path.exists(test_dir):
            patterns = find_sleep_patterns(test_dir)
            all_patterns.extend(patterns)

    # Categorize patterns
    categories = categorize_patterns(all_patterns)

    # Output results
    if args.json:
        import json

        output = {
            "total": len(all_patterns),
            "critical": len(categories["critical"]),
            "moderate": len(categories["moderate"]),
            "low": len(categories["low"]),
            "patterns": [
                {
                    "file": pattern.file_path,
                    "line": pattern.line_num,
                    "type": pattern.sleep_type,
                    "duration": pattern.duration,
                    "severity": pattern.severity,
                    "suggestion": suggest_fix(pattern),
                }
                for pattern in all_patterns
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print_report(categories)

    # Check mode for CI
    if args.check and categories["critical"]:
        print(
            f"\n\nERROR: Found {len(categories['critical'])} critical sleep patterns!"
        )
        print("Fix these before committing.")
        sys.exit(1)

    # Experimental fix mode
    if args.fix:
        print("\n\nWARNING: Automatic fixing is experimental and may break tests!")
        print("This will add import for wait_conditions and update simple cases.")
        response = input("Continue? [y/N] ")
        if response.lower() == "y":
            # TODO: Implement automatic fixing for simple cases
            print("Automatic fixing not yet implemented.")


if __name__ == "__main__":
    main()

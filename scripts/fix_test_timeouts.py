#!/usr/bin/env python3
"""
Script to identify and help fix test timeout violations.

Usage:
    python scripts/fix_test_timeouts.py
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


def run_tests_with_timeout(test_path: str, timeout: int) -> Tuple[bool, List[str]]:
    """Run tests with timeout and return violating tests."""
    cmd = [
        "pytest",
        test_path,
        f"--timeout={timeout}",
        "--timeout-method=thread",
        "-v",
        "--tb=no",
    ]

    print(f"\n🔍 Running {test_path} with {timeout}s timeout...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Find tests that timed out
    timeout_tests = []
    lines = result.stdout.split("\n") + result.stderr.split("\n")

    current_test = None
    for line in lines:
        # Match test name
        if "::" in line and "PASSED" not in line and "FAILED" not in line:
            current_test = line.strip()
        # Check for timeout
        if "Timeout" in line and current_test:
            timeout_tests.append(current_test)
            current_test = None

    return len(timeout_tests) == 0, timeout_tests


def find_long_sleeps(file_path: Path) -> List[Tuple[int, str]]:
    """Find lines with long asyncio.sleep calls."""
    long_sleeps = []

    try:
        with open(file_path, "r") as f:
            lines = f.readlines()

        for i, line in enumerate(lines, 1):
            # Find asyncio.sleep with values >= 1
            match = re.search(r"asyncio\.sleep\((\d+(?:\.\d+)?)\)", line)
            if match:
                sleep_time = float(match.group(1))
                if sleep_time >= 1.0:
                    long_sleeps.append((i, line.strip()))
    except Exception:
        pass

    return long_sleeps


def suggest_fixes(test_file: str):
    """Suggest fixes for a test file."""
    path = Path(test_file)
    if not path.exists():
        return

    print(f"\n📝 Analyzing {test_file}...")

    # Check for long sleeps
    long_sleeps = find_long_sleeps(path)
    if long_sleeps:
        print("  ⚠️  Found long sleep calls:")
        for line_num, line in long_sleeps:
            print(f"    Line {line_num}: {line}")
            print("    Fix: Replace with asyncio.sleep(0.1) or smaller value")

    # Check for common patterns
    content = path.read_text()

    if "health_check_interval" in content and "30" in content:
        print("  ⚠️  Found slow health check interval (30s)")
        print("    Fix: Use health_check_interval=0.1")

    if "max_lifetime" in content and "3600" in content:
        print("  ⚠️  Found long max_lifetime (1 hour)")
        print("    Fix: Use max_lifetime=60.0 for tests")

    if "_cleanup()" in content and "finally:" in content:
        print("  ℹ️  Has cleanup in finally block - good!")
    else:
        print("  ⚠️  May need cleanup in finally block for actors/pools")


def main():
    """Main function."""
    print("🚀 Test Timeout Violation Finder")
    print("================================")

    # Define test tiers and their timeouts
    tiers = [
        ("tests/unit/", 1, "Unit tests"),
        ("tests/integration/", 5, "Integration tests"),
        ("tests/e2e/", 10, "E2E tests"),
    ]

    all_violations = []

    for test_path, timeout, description in tiers:
        if not Path(test_path).exists():
            continue

        success, violations = run_tests_with_timeout(test_path, timeout)

        if success:
            print(f"✅ {description}: All tests complete within {timeout}s")
        else:
            print(
                f"❌ {description}: {len(violations)} tests exceed {timeout}s timeout"
            )
            all_violations.extend(violations)

            for test in violations[:5]:  # Show first 5
                print(f"   - {test}")
            if len(violations) > 5:
                print(f"   ... and {len(violations) - 5} more")

    if all_violations:
        print("\n📋 Fixing Timeout Violations")
        print("============================")

        # Extract unique test files
        test_files = set()
        for violation in all_violations:
            # Extract file path from test name
            if "::" in violation:
                file_part = violation.split("::")[0]
                test_files.add(file_part)

        for test_file in sorted(test_files)[:10]:  # Analyze first 10 files
            suggest_fixes(test_file)

        print("\n💡 General Tips:")
        print("  1. Replace long sleeps: asyncio.sleep(10) → asyncio.sleep(0.1)")
        print("  2. Mock external services instead of real calls")
        print("  3. Use smaller datasets for tests")
        print("  4. Add proper cleanup in finally blocks")
        print("  5. Use shorter timeouts for database operations")
    else:
        print("\n🎉 All tests complete within timeout limits!")


if __name__ == "__main__":
    main()

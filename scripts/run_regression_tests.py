#!/usr/bin/env python3
"""
Regression Test Runner - Tiered testing for the Kailash SDK

This script runs tests in tiers to quickly identify regressions while
managing the large test suite (1,844 tests).

Usage:
    python scripts/run_regression_tests.py --tier 1  # Quick smoke test (2 min)
    python scripts/run_regression_tests.py --tier 2  # Fast regression (10 min)
    python scripts/run_regression_tests.py --tier 3  # Full regression (45-60 min)
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple

# Test tiers configuration
TIERS = {
    1: {
        "name": "Smoke Tests",
        "markers": "critical or smoke",
        "exclude_markers": "slow or docker",
        "max_duration": 120,  # 2 minutes
        "fail_fast": True,
        "parallel": True,
    },
    2: {
        "name": "Fast Regression",
        "markers": "not slow",
        "exclude_markers": "docker or external",
        "max_duration": 600,  # 10 minutes
        "fail_fast": False,
        "parallel": True,
    },
    3: {
        "name": "Full Regression",
        "markers": "",  # All tests
        "exclude_markers": "",
        "max_duration": 3600,  # 60 minutes
        "fail_fast": False,
        "parallel": False,  # Some tests may not be thread-safe
    },
}

# Critical test paths that must always pass
CRITICAL_PATHS = [
    "tests/unit/nodes/admin/test_unified_admin_schema.py",
    "tests/unit/nodes/test_workflow_node.py",
    "tests/unit/nodes/test_workflow_connection_pool.py",
    "tests/unit/runtime/test_async_local.py",
    "tests/integration/test_admin_nodes_integration.py",
    "tests/integration/test_enhanced_gateway_production.py",
    "tests/integration/test_async_runtime_integration.py::TestAsyncRuntimeRealWorld::test_database_etl_pipeline",
    "tests/integration/test_async_workflow_builder_integration.py",
]


def run_command(cmd: List[str], timeout: int = None) -> Tuple[int, str, str]:
    """Run a command and return (return_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout} seconds"


def run_tier_tests(tier: int) -> bool:
    """Run tests for a specific tier."""
    config = TIERS[tier]
    print(f"\n{'='*60}")
    print(f"Running Tier {tier}: {config['name']}")
    print(f"{'='*60}\n")

    # Build pytest command
    cmd = ["pytest"]

    # Add markers
    if config["markers"]:
        cmd.extend(["-m", config["markers"]])

    # Add parallel execution
    if config["parallel"]:
        cmd.extend(["-n", "auto"])

    # Add fail fast
    if config["fail_fast"]:
        cmd.extend(["--maxfail", "1"])

    # Add verbosity and reporting
    cmd.extend(
        [
            "-v",
            "--tb=short",
            "--durations=10",
            f"--junit-xml=tier{tier}_results.xml",
        ]
    )

    # Run tests
    start_time = time.time()
    return_code, stdout, stderr = run_command(cmd, timeout=config["max_duration"])
    duration = time.time() - start_time

    # Print results
    print(stdout)
    if stderr:
        print(f"\nErrors:\n{stderr}")

    print(f"\n{'='*60}")
    print(f"Tier {tier} completed in {duration:.2f} seconds")

    if return_code == 0:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")

    print(f"{'='*60}\n")

    return return_code == 0


def run_critical_paths() -> bool:
    """Run only the most critical test files."""
    print("\n🔥 Running Critical Path Tests...")

    cmd = ["pytest"] + CRITICAL_PATHS + ["-v", "--tb=short", "--maxfail=5"]

    return_code, stdout, stderr = run_command(cmd, timeout=60)

    print(stdout)
    if stderr:
        print(f"\nErrors:\n{stderr}")

    return return_code == 0


def analyze_test_suite():
    """Analyze the test suite and provide statistics."""
    print("\n📊 Analyzing Test Suite...")

    # Count total tests
    cmd = ["pytest", "--collect-only", "-q"]
    _, stdout, _ = run_command(cmd)
    total_tests = len([line for line in stdout.split("\n") if "test_" in line])

    # Count slow tests
    cmd = ["pytest", "-m", "slow", "--collect-only", "-q"]
    _, stdout, _ = run_command(cmd)
    slow_tests = len([line for line in stdout.split("\n") if "test_" in line])

    # Count test files
    test_files = list(Path("tests").rglob("test_*.py"))

    print(
        f"""
Test Suite Statistics:
- Total test files: {len(test_files)}
- Total tests: {total_tests}
- Fast tests: {total_tests - slow_tests}
- Slow tests: {slow_tests}
- Test density: {total_tests / len(test_files):.1f} tests per file
"""
    )


def main():
    parser = argparse.ArgumentParser(description="Run regression tests in tiers")
    parser.add_argument(
        "--tier",
        type=int,
        choices=[1, 2, 3],
        default=2,
        help="Test tier to run (1=smoke, 2=fast, 3=full)",
    )
    parser.add_argument(
        "--critical-only",
        action="store_true",
        help="Run only critical path tests",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze test suite statistics",
    )

    args = parser.parse_args()

    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    # Run requested action
    if args.analyze:
        analyze_test_suite()
        return

    if args.critical_only:
        success = run_critical_paths()
    else:
        success = run_tier_tests(args.tier)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

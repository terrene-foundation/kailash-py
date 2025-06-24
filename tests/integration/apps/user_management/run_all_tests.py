#!/usr/bin/env python3
"""Script to run all user management tests and generate a report."""

import subprocess
import sys
from datetime import datetime


def run_test(test_path, description):
    """Run a test and return results."""
    print(f"\n{'='*80}")
    print(f"Running: {description}")
    print(f"Test: {test_path}")
    print("=" * 80)

    try:
        result = subprocess.run(
            ["pytest", test_path, "-v", "-q"], capture_output=True, text=True
        )

        success = result.returncode == 0
        output = result.stdout if success else result.stderr

        return {
            "test": test_path,
            "description": description,
            "success": success,
            "output": output,
            "errors": result.stderr if not success else "",
        }
    except Exception as e:
        return {
            "test": test_path,
            "description": description,
            "success": False,
            "output": "",
            "errors": str(e),
        }


def main():
    """Run all user management tests."""
    tests = [
        # Working tests
        (
            "tests/integration/apps/user_management/test_admin_nodes_docker_integration.py",
            "Admin Nodes Docker Integration Tests",
        ),
        # Performance tests (may have issues)
        (
            "tests/integration/apps/user_management/test_performance_and_load.py::TestPerformanceAndLoad::test_concurrent_operations",
            "Concurrent Operations Performance Test",
        ),
        (
            "tests/integration/apps/user_management/test_performance_and_load.py::TestPerformanceAndLoad::test_pagination_performance",
            "Pagination Performance Test",
        ),
    ]

    results = []
    passed = 0
    failed = 0

    print(
        f"\nUser Management Test Suite - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print("=" * 80)

    for test_path, description in tests:
        result = run_test(test_path, description)
        results.append(result)

        if result["success"]:
            passed += 1
            print("✅ PASSED")
        else:
            failed += 1
            print("❌ FAILED")
            if result["errors"]:
                print(f"Errors: {result['errors'][:200]}...")

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Total tests: {len(tests)}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} ❌")
    print(f"Success rate: {(passed/len(tests)*100):.1f}%")

    # Save report
    with open("test_report.txt", "w") as f:
        f.write(f"User Management Test Report - {datetime.now()}\n")
        f.write("=" * 80 + "\n\n")

        for result in results:
            f.write(f"Test: {result['description']}\n")
            f.write(f"Path: {result['test']}\n")
            f.write(f"Status: {'PASSED' if result['success'] else 'FAILED'}\n")
            if not result["success"] and result["errors"]:
                f.write(f"Errors:\n{result['errors']}\n")
            f.write("-" * 40 + "\n\n")

    print("\nReport saved to test_report.txt")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

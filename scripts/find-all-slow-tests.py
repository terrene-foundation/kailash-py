#!/usr/bin/env python3
"""Find all slow tests by running them and measuring execution time."""

import os
import re
import subprocess
import time


def find_test_files():
    """Find all test files in tests/unit."""
    test_files = []
    for root, dirs, files in os.walk("tests/unit"):
        for file in files:
            if file.startswith("test_") and file.endswith(".py"):
                test_files.append(os.path.join(root, file))
    return sorted(test_files)


def measure_test_time(test_file, max_time=30):
    """Measure execution time of a test file."""
    start = time.time()
    try:
        # Run pytest with timeout
        result = subprocess.run(
            ["pytest", test_file, "-v", "--tb=no", "-x"],
            capture_output=True,
            text=True,
            timeout=max_time,
        )
        elapsed = time.time() - start

        # Count number of tests
        test_count = len(re.findall(r"PASSED", result.stdout))

        return elapsed, test_count, result.returncode == 0
    except subprocess.TimeoutExpired:
        return max_time, 0, False
    except Exception as e:
        return 0, 0, False


def main():
    """Find all slow test files."""
    print("Finding slow test files (this may take a while)...")
    print("=" * 80)

    test_files = find_test_files()
    slow_files = []

    for test_file in test_files:
        print(f"Testing {test_file}...", end=" ", flush=True)
        elapsed, test_count, success = measure_test_time(test_file)

        if elapsed > 0:
            avg_time = elapsed / max(test_count, 1)
            print(f"{elapsed:.2f}s ({test_count} tests, {avg_time:.3f}s/test)")

            # Consider slow if total time > 2s OR average time per test > 0.1s
            if elapsed > 2.0 or avg_time > 0.1:
                slow_files.append((test_file, elapsed, test_count, avg_time))
        else:
            print("FAILED")

    print("\n" + "=" * 80)
    print("SLOW TEST FILES (>2s total or >0.1s/test):")
    print("=" * 80)

    slow_files.sort(key=lambda x: x[1], reverse=True)

    for file, elapsed, count, avg in slow_files:
        print(f"{elapsed:6.2f}s | {count:3d} tests | {avg:5.3f}s/test | {file}")

    print(f"\nTotal slow files: {len(slow_files)}")

    # Generate exclusion list
    print("\n" + "=" * 80)
    print("PYTEST IGNORE FLAGS:")
    print("=" * 80)

    for file, _, _, _ in slow_files:
        print(f"--ignore={file}")


if __name__ == "__main__":
    main()

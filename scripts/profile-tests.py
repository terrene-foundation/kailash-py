#!/usr/bin/env python3
"""
Profile test execution times to identify slow tests.
Usage: python scripts/profile-tests.py
"""

import json
import subprocess
import sys
from pathlib import Path


def run_pytest_profile():
    """Run pytest with profiling to identify slow tests."""
    print("🔍 Profiling test execution times...")

    # Run pytest with durations report
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "--durations=50",  # Show 50 slowest tests
        "--duration-min=0.1",  # Only show tests taking > 0.1s
        "-v",
        "--tb=no",  # No traceback
        "-q",  # Quiet
        "--no-header",
        "--json-report",
        "--json-report-file=test-timings.json",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        print("\n📊 Test Duration Report:")
        print("=" * 60)

        # Parse the durations from output
        lines = result.stdout.split("\n")
        in_durations = False
        slow_tests = []

        for line in lines:
            if "slowest durations" in line:
                in_durations = True
                continue
            if in_durations and line.strip():
                if line.startswith("="):
                    break
                # Parse duration line
                parts = line.split()
                if len(parts) >= 2 and parts[0].replace(".", "").isdigit():
                    duration = float(parts[0].rstrip("s"))
                    test_name = " ".join(parts[1:])
                    slow_tests.append((duration, test_name))

        # Show slowest tests
        if slow_tests:
            print("\n⏱️  Slowest Tests:")
            for duration, test_name in slow_tests[:20]:
                print(f"  {duration:6.2f}s - {test_name}")

            # Categorize by module
            print("\n📁 Slow Tests by Module:")
            module_times = {}
            for duration, test_name in slow_tests:
                if "::" in test_name:
                    module = test_name.split("::")[0]
                    module_times[module] = module_times.get(module, 0) + duration

            for module, total_time in sorted(
                module_times.items(), key=lambda x: x[1], reverse=True
            )[:10]:
                print(f"  {total_time:6.2f}s - {module}")

        # Check if json report exists
        if Path("test-timings.json").exists():
            with open("test-timings.json") as f:
                report = json.load(f)
                print("\n📈 Summary:")
                print(f"  Total tests: {report['summary']['total']}")
                print(f"  Total duration: {report['duration']:.2f}s")
                if report["summary"]["total"] > 0:
                    print(
                        f"  Average per test: {report['duration'] / report['summary']['total']:.2f}s"
                    )

    except subprocess.CalledProcessError as e:
        print(f"❌ Error running pytest: {e}")
        print(f"Output: {e.output}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        # Cleanup
        if Path("test-timings.json").exists():
            Path("test-timings.json").unlink()


def suggest_optimizations():
    """Suggest optimizations based on common patterns."""
    print("\n💡 Optimization Suggestions:")
    print("=" * 60)

    suggestions = [
        "1. Mark slow integration tests with @pytest.mark.slow",
        "2. Use pytest-xdist for parallel execution: pytest -n auto",
        "3. Split tests into groups for CI parallelization",
        "4. Mock external dependencies and file I/O",
        "5. Use fixtures to share expensive setup",
        "6. Consider pytest-benchmark for performance tests",
        "7. Use pytest.mark.parametrize efficiently",
        "8. Cache test dependencies in CI",
    ]

    for suggestion in suggestions:
        print(f"  {suggestion}")

    print("\n🚀 Quick Wins:")
    print("  - Run only changed tests: pytest --lf (last failed)")
    print("  - Skip slow tests in CI: pytest -m 'not slow'")
    print("  - Use pytest-split for distributed testing")
    print("  - Enable pytest caching: --cache-show")


if __name__ == "__main__":
    print("🏃 Kailash Test Performance Profiler")
    print("=" * 60)

    # Check if pytest is available
    try:
        subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        print(
            "❌ pytest not found. Please install: pip install pytest pytest-json-report"
        )
        sys.exit(1)

    run_pytest_profile()
    suggest_optimizations()

    print("\n✅ Profiling complete!")

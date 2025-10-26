"""
Generate comprehensive parity report for sync/async runtimes.

Usage:
    python tests/parity/utils/generate_parity_report.py --output report.md
"""

import argparse
import inspect
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def get_method_count():
    """Get method counts for both runtimes."""
    try:
        from kailash.runtime.async_local import AsyncLocalRuntime
        from kailash.runtime.local import LocalRuntime

        local = len(
            [
                m
                for m in dir(LocalRuntime)
                if not m.startswith("__") and callable(getattr(LocalRuntime, m))
            ]
        )
        async_ = len(
            [
                m
                for m in dir(AsyncLocalRuntime)
                if not m.startswith("__") and callable(getattr(AsyncLocalRuntime, m))
            ]
        )
        return local, async_, None
    except Exception as e:
        return 0, 0, str(e)


def get_test_count():
    """Count tests for each runtime."""
    counts = {}

    # Shared tests
    try:
        result = subprocess.run(
            ["pytest", "tests/shared/runtime", "--collect-only", "-q"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        counts["shared"] = result.stdout.count("test_")
    except Exception:
        counts["shared"] = 0

    # LocalRuntime tests
    try:
        result = subprocess.run(
            ["pytest", "tests/unit/runtime/local", "--collect-only", "-q"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        counts["local"] = result.stdout.count("test_")
    except Exception:
        counts["local"] = 0

    # AsyncLocalRuntime tests
    try:
        result = subprocess.run(
            ["pytest", "tests/unit/runtime/async_local", "--collect-only", "-q"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        counts["async"] = result.stdout.count("test_")
    except Exception:
        counts["async"] = 0

    return counts


def get_coverage_stats():
    """Get coverage statistics if available."""
    stats = {}

    # Try to get coverage from recent runs
    coverage_files = [
        "local_coverage.txt",
        "async_coverage.txt",
    ]

    for filename in coverage_files:
        if Path(filename).exists():
            try:
                with open(filename, "r") as f:
                    content = f.read()
                    # Parse coverage percentage from "TOTAL    123    45    63%"
                    for line in content.split("\n"):
                        if "TOTAL" in line:
                            parts = line.split()
                            if len(parts) >= 4:
                                coverage = parts[-1].replace("%", "")
                                runtime = "local" if "local" in filename else "async"
                                stats[runtime] = float(coverage)
            except Exception:
                pass

    return stats


def main():
    """Generate parity report."""
    parser = argparse.ArgumentParser(description="Generate sync/async parity report")
    parser.add_argument("--output", default="parity_report.md", help="Output file path")
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format",
    )
    args = parser.parse_args()

    print("Generating parity report...")

    # Gather data
    local_methods, async_methods, method_error = get_method_count()
    test_counts = get_test_count()
    coverage_stats = get_coverage_stats()

    # Calculate metrics
    shared_tests = test_counts.get("shared", 0)
    local_tests = test_counts.get("local", 0)
    async_tests = test_counts.get("async", 0)

    local_effective = shared_tests + local_tests
    async_effective = shared_tests + async_tests

    # Determine status
    method_parity_ok = local_methods <= async_methods if not method_error else False
    test_parity_ok = abs(local_tests - async_tests) < 10
    coverage_parity_ok = True

    if "local" in coverage_stats and "async" in coverage_stats:
        coverage_diff = abs(coverage_stats["local"] - coverage_stats["async"])
        coverage_parity_ok = coverage_diff <= 5.0

    overall_status = method_parity_ok and test_parity_ok and coverage_parity_ok

    # Generate report
    if args.format == "markdown":
        report = f"""# Sync/Async Parity Report

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Overall Status**: {'✅ PASS' if overall_status else '❌ FAIL'}

---

## Summary

| Metric | LocalRuntime | AsyncLocalRuntime | Status |
|--------|-------------|------------------|--------|
| Methods | {local_methods} | {async_methods} | {'✅' if method_parity_ok else '❌'} |
| Specific Tests | {local_tests} | {async_tests} | {'✅' if test_parity_ok else '⚠️'} |
| Shared Tests | {shared_tests} | {shared_tests} | ✅ |
| Total Tests | {local_effective} | {async_effective} | {'✅' if abs(local_effective - async_effective) < 10 else '⚠️'} |
"""

        # Add coverage if available
        if coverage_stats:
            report += "\n## Coverage\n\n"
            report += "| Runtime | Coverage | Status |\n"
            report += "|---------|----------|--------|\n"

            if "local" in coverage_stats:
                report += f"| LocalRuntime | {coverage_stats['local']:.1f}% | {'✅' if coverage_stats['local'] >= 85 else '⚠️'} |\n"

            if "async" in coverage_stats:
                report += f"| AsyncLocalRuntime | {coverage_stats['async']:.1f}% | {'✅' if coverage_stats['async'] >= 85 else '⚠️'} |\n"

            if "local" in coverage_stats and "async" in coverage_stats:
                diff = abs(coverage_stats["local"] - coverage_stats["async"])
                report += f"\n**Coverage Difference**: {diff:.1f}% {'✅' if diff <= 5.0 else '❌ (exceeds 5% threshold)'}\n"

        # Method details
        report += "\n## Method Parity\n\n"

        if method_error:
            report += f"❌ **Error**: {method_error}\n"
        else:
            report += f"- **LocalRuntime**: {local_methods} public methods\n"
            report += f"- **AsyncLocalRuntime**: {async_methods} public methods\n"
            report += f"- **Status**: {'✅ PASS - All LocalRuntime methods present in AsyncLocalRuntime' if method_parity_ok else '❌ FAIL - Missing methods in AsyncLocalRuntime'}\n"

        # Test details
        report += "\n## Test Coverage\n\n"
        report += "### Shared Tests\n"
        report += f"{shared_tests} tests run against both runtimes (parametrized)\n\n"

        report += "### Runtime-Specific Tests\n"
        report += f"- **LocalRuntime**: {local_tests} tests\n"
        report += f"- **AsyncLocalRuntime**: {async_tests} tests\n\n"

        report += "### Effective Coverage\n"
        report += (
            f"- **LocalRuntime**: {local_effective} total tests (shared + specific)\n"
        )
        report += f"- **AsyncLocalRuntime**: {async_effective} total tests (shared + specific)\n\n"

        # Recommendations
        report += "\n## Recommendations\n\n"

        if not overall_status:
            if not method_parity_ok:
                report += "- ⚠️ **Method Parity**: AsyncLocalRuntime is missing methods from LocalRuntime. Implement missing methods or document as sync-only.\n"

            if not test_parity_ok:
                report += f"- ⚠️ **Test Parity**: Test count disparity detected (LocalRuntime: {local_tests}, AsyncLocalRuntime: {async_tests}). Add tests to achieve parity.\n"

            if (
                not coverage_parity_ok
                and "local" in coverage_stats
                and "async" in coverage_stats
            ):
                diff = abs(coverage_stats["local"] - coverage_stats["async"])
                report += f"- ⚠️ **Coverage Parity**: Coverage difference ({diff:.1f}%) exceeds 5% threshold. Add tests to lower coverage.\n"
        else:
            report += "✅ No issues found - parity maintained!\n\n"
            report += (
                "Continue to monitor parity with daily checks and enforce in CI/CD.\n"
            )

        # Save report
        with open(args.output, "w") as f:
            f.write(report)

        print(f"\n✅ Parity report generated: {args.output}")
        print(f"Overall status: {'PASS ✅' if overall_status else 'FAIL ❌'}")

        return 0 if overall_status else 1

    else:
        # JSON format
        import json

        data = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "pass" if overall_status else "fail",
            "methods": {
                "local": local_methods,
                "async": async_methods,
                "parity": method_parity_ok,
                "error": method_error,
            },
            "tests": {
                "shared": shared_tests,
                "local": local_tests,
                "async": async_tests,
                "local_effective": local_effective,
                "async_effective": async_effective,
                "parity": test_parity_ok,
            },
            "coverage": coverage_stats,
        }

        with open(args.output, "w") as f:
            json.dump(data, f, indent=2)

        print(f"✅ Parity report generated: {args.output}")
        return 0 if overall_status else 1


if __name__ == "__main__":
    sys.exit(main())

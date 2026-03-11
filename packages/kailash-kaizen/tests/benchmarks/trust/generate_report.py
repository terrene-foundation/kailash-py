#!/usr/bin/env python3
"""
Generate a comprehensive markdown report from benchmark JSON results.

Usage:
    python tests/benchmarks/trust/generate_report.py results.json > report.md
"""

import json
import statistics
import sys
from datetime import datetime
from typing import Any, Dict, List


def load_results(filename: str) -> Dict[str, Any]:
    """Load benchmark results from JSON file."""
    with open(filename, "r") as f:
        return json.load(f)


def calculate_percentile(values: List[float], percentile: int) -> float:
    """Calculate the Nth percentile from a list of values."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(len(sorted_values) * (percentile / 100.0))
    return sorted_values[min(index, len(sorted_values) - 1)]


def format_duration(seconds: float) -> str:
    """Format duration in appropriate units (ms or μs)."""
    if seconds >= 0.001:
        return f"{seconds * 1000:.3f}ms"
    else:
        return f"{seconds * 1000000:.3f}μs"


def check_target(value: float, target: float) -> str:
    """Check if value meets target and return status emoji."""
    if value < target:
        return "✅ PASS"
    elif value < target * 1.2:
        return "⚠️ WARN"
    else:
        return "❌ FAIL"


def generate_report(results: Dict[str, Any]) -> str:
    """Generate markdown report from benchmark results."""

    # Extract benchmark data
    benchmarks = results.get("benchmarks", [])

    if not benchmarks:
        return "# Error: No benchmark data found\n"

    # Group benchmarks by group
    grouped = {}
    for bench in benchmarks:
        group = bench.get("group", "ungrouped")
        if group not in grouped:
            grouped[group] = []
        grouped[group].append(bench)

    # Performance targets (from conftest.py)
    targets = {
        "establish": 0.100,  # 100ms
        "delegate": 0.050,  # 50ms
        "verify_quick": 0.005,  # 5ms
        "verify_standard": 0.050,  # 50ms
        "verify_full": 0.100,  # 100ms
        "audit": 0.020,  # 20ms
        "cache_hit": 0.001,  # 1ms
    }

    # Start building report
    report = f"""# EATP Trust Operations Performance Benchmark Report

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Executive Summary

Performance benchmarks for EATP (Enterprise Agent Trust Protocol) core operations.

**Testing Policy**: NO MOCKING - All operations use real implementations with in-memory stores.

---

"""

    # Add each group
    for group_name, group_benchmarks in grouped.items():
        report += f"\n## {group_name.upper()} Operations\n\n"

        for bench in group_benchmarks:
            name = bench.get("name", "Unknown")
            stats_data = bench.get("stats", {})

            # Extract statistics
            mean = stats_data.get("mean", 0)
            median = stats_data.get("median", 0)
            min_val = stats_data.get("min", 0)
            max_val = stats_data.get("max", 0)
            stddev = stats_data.get("stddev", 0)

            # Calculate p95 from raw data if available
            raw_data = stats_data.get("data", [])
            p95 = calculate_percentile(raw_data, 95) if raw_data else mean * 1.2

            # Determine target based on benchmark name
            target = None
            target_label = ""
            if "establish" in name.lower():
                target = targets["establish"]
                target_label = "Target: <100ms p95"
            elif "delegate" in name.lower():
                target = targets["delegate"]
                target_label = "Target: <50ms p95"
            elif "verify_quick" in name.lower():
                target = targets["verify_quick"]
                target_label = "Target: <5ms p95"
            elif "verify_standard" in name.lower():
                target = targets["verify_standard"]
                target_label = "Target: <50ms p95"
            elif "verify_full" in name.lower():
                target = targets["verify_full"]
                target_label = "Target: <100ms p95"
            elif "audit" in name.lower():
                target = targets["audit"]
                target_label = "Target: <20ms p95"
            elif "cache_hit" in name.lower() and "rate" not in name.lower():
                target = targets["cache_hit"]
                target_label = "Target: <1ms mean"

            # Format benchmark name
            clean_name = name.replace("test_benchmark_", "").replace("_", " ").title()

            report += f"### {clean_name}\n\n"

            if target_label:
                report += f"**{target_label}**\n\n"

            report += "| Metric | Value | Status |\n"
            report += "|--------|-------|--------|\n"
            report += f"| Mean | {format_duration(mean)} | "

            if target and "mean" in target_label.lower():
                report += check_target(mean, target)
            else:
                report += "-"

            report += " |\n"
            report += f"| Median | {format_duration(median)} | - |\n"
            report += f"| p95 | {format_duration(p95)} | "

            if target and "p95" in target_label.lower():
                report += check_target(p95, target)
            else:
                report += "-"

            report += " |\n"
            report += f"| Min | {format_duration(min_val)} | - |\n"
            report += f"| Max | {format_duration(max_val)} | - |\n"
            report += f"| StdDev | {format_duration(stddev)} | - |\n"
            report += f"| Rounds | {stats_data.get('rounds', 0)} | - |\n"

            report += "\n"

    # Add conclusions
    report += "\n## Conclusions\n\n"

    all_pass = True
    for bench in benchmarks:
        name = bench.get("name", "")
        stats_data = bench.get("stats", {})
        mean = stats_data.get("mean", 0)
        raw_data = stats_data.get("data", [])
        p95 = calculate_percentile(raw_data, 95) if raw_data else mean * 1.2

        # Check against targets
        if "establish" in name.lower() and p95 >= targets["establish"]:
            all_pass = False
        elif "delegate" in name.lower() and p95 >= targets["delegate"]:
            all_pass = False
        elif "verify_quick" in name.lower() and p95 >= targets["verify_quick"]:
            all_pass = False
        elif "verify_standard" in name.lower() and p95 >= targets["verify_standard"]:
            all_pass = False
        elif "verify_full" in name.lower() and p95 >= targets["verify_full"]:
            all_pass = False
        elif "audit" in name.lower() and p95 >= targets["audit"]:
            all_pass = False
        elif (
            "cache_hit" in name.lower()
            and "rate" not in name.lower()
            and mean >= targets["cache_hit"]
        ):
            all_pass = False

    if all_pass:
        report += "✅ **All performance targets met**\n\n"
        report += "The EATP trust operations meet or exceed all performance targets. "
        report += "The system is ready for production use with expected performance characteristics.\n\n"
    else:
        report += "⚠️ **Some performance targets not met**\n\n"
        report += (
            "Review the individual benchmark results above to identify operations "
        )
        report += "that need optimization.\n\n"

    # Add recommendations
    report += "\n## Recommendations\n\n"

    report += "### Short-term\n\n"
    report += (
        "1. **Monitor cache hit rate** in production to ensure >85% effectiveness\n"
    )
    report += "2. **Use VERIFY QUICK** for high-frequency operations where full validation isn't needed\n"
    report += "3. **Batch ESTABLISH operations** during agent provisioning to amortize overhead\n\n"

    report += "### Long-term\n\n"
    report += "1. **Implement chain caching** for frequently verified agents\n"
    report += "2. **Consider async verification** for non-blocking validation\n"
    report += "3. **Add database connection pooling** when using PostgreSQL backend\n"
    report += "4. **Optimize signature verification** with batching for VERIFY FULL\n\n"

    # Add environment info
    env_info = results.get("machine_info", {})
    if env_info:
        report += "\n## Environment\n\n"
        report += f"- **Node**: {env_info.get('node', 'Unknown')}\n"
        report += f"- **Python**: {env_info.get('python_version', 'Unknown')}\n"
        report += f"- **Platform**: {env_info.get('platform', 'Unknown')}\n"
        report += f"- **Processor**: {env_info.get('processor', 'Unknown')}\n"

    return report


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python generate_report.py results.json > report.md")
        sys.exit(1)

    results_file = sys.argv[1]

    try:
        results = load_results(results_file)
        report = generate_report(results)
        print(report)
    except FileNotFoundError:
        print(f"Error: File not found: {results_file}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {results_file}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

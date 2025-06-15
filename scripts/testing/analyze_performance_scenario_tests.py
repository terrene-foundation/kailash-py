#!/usr/bin/env python3
"""
Analyze Performance and Scenario Tests for Removal/Relocation

Identifies performance and scenario tests that should be:
1. Removed (redundant, obsolete, or development-only)
2. Relocated (moved to examples or performance suite)
3. Kept (essential for CI/CD validation)
"""

import ast
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set


def find_performance_scenario_tests() -> Dict[str, List[Path]]:
    """Find all performance and scenario test files."""
    tests_dir = Path("tests")
    patterns = {
        "performance": [],
        "scenario": [],
        "benchmark": [],
        "load": [],
        "stress": [],
        "e2e": [],
    }

    for test_file in tests_dir.rglob("*.py"):
        content = test_file.read_text(encoding="utf-8")
        filename = test_file.name.lower()

        # Check filename patterns
        if any(pattern in filename for pattern in ["performance", "benchmark"]):
            patterns["performance"].append(test_file)
        elif any(pattern in filename for pattern in ["scenario", "scenarios"]):
            patterns["scenario"].append(test_file)
        elif any(pattern in filename for pattern in ["load", "stress"]):
            patterns["load"].append(test_file)
        elif "e2e" in str(test_file):
            patterns["e2e"].append(test_file)

        # Check content patterns
        elif any(
            keyword in content.lower()
            for keyword in [
                "performance",
                "benchmark",
                "load test",
                "stress test",
                "scenario test",
                "large-scale",
                "throughput",
                "latency",
            ]
        ):
            if any(
                keyword in content.lower() for keyword in ["performance", "benchmark"]
            ):
                patterns["performance"].append(test_file)
            elif "scenario" in content.lower():
                patterns["scenario"].append(test_file)

    return patterns


def analyze_test_file(test_file: Path) -> Dict[str, Any]:
    """Analyze a test file to determine its characteristics."""
    try:
        content = test_file.read_text(encoding="utf-8")

        analysis = {
            "file": str(test_file.relative_to(Path("tests"))),
            "size_lines": len(content.splitlines()),
            "test_functions": [],
            "imports": [],
            "markers": [],
            "characteristics": [],
            "recommendation": "keep",
            "reason": "",
            "relocation_target": None,
        }

        # Parse AST to extract test functions and imports
        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    analysis["test_functions"].append(node.name)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        analysis["imports"].append(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    analysis["imports"].append(node.module)
        except:
            pass

        # Analyze characteristics
        if "time.sleep" in content or "asyncio.sleep" in content:
            analysis["characteristics"].append("has_delays")

        if any(
            keyword in content.lower()
            for keyword in ["1000", "10000", "large", "massive"]
        ):
            analysis["characteristics"].append("large_scale")

        if "ThreadPoolExecutor" in content or "concurrent.futures" in content:
            analysis["characteristics"].append("concurrent")

        if "psutil" in content or "memory" in content.lower():
            analysis["characteristics"].append("resource_monitoring")

        if "pytest.skip" in content:
            analysis["characteristics"].append("conditional_skip")

        if "@pytest.mark.slow" in content or "slow" in content.lower():
            analysis["characteristics"].append("slow")

        if "docker" in content.lower() or "container" in content.lower():
            analysis["characteristics"].append("docker_dependent")

        # Determine recommendation
        (
            analysis["recommendation"],
            analysis["reason"],
            analysis["relocation_target"],
        ) = determine_recommendation(
            test_file, content, analysis["characteristics"], analysis["test_functions"]
        )

        return analysis

    except Exception as e:
        return {
            "file": str(test_file.relative_to(Path("tests"))),
            "error": str(e),
            "recommendation": "review",
            "reason": f"Analysis failed: {e}",
        }


def determine_recommendation(
    test_file: Path, content: str, characteristics: List[str], test_functions: List[str]
) -> tuple[str, str, str]:
    """Determine what to do with a test file."""

    filename = test_file.name.lower()
    file_path = str(test_file)

    # Empty or placeholder files
    if "class TestPerformance:" in content and len(test_functions) <= 2:
        if any(char in characteristics for char in ["conditional_skip", "slow"]):
            return "remove", "Empty or placeholder performance test with skips", None

    # E2E directories that are empty or minimal
    if "/e2e/" in file_path and ("__init__.py" in filename or len(test_functions) == 0):
        return "remove", "Empty e2e directory or placeholder", None

    # Performance benchmarks that are development-only
    if "performance" in filename and "large_scale" in characteristics:
        if not any(
            essential in content.lower()
            for essential in ["ci", "regression", "sla", "baseline"]
        ):
            return (
                "relocate",
                "Development performance test",
                "examples/performance_benchmarks/",
            )

    # Scenario tests that are really integration examples
    if "scenario" in filename and "e2e" not in file_path:
        if "real-world" in content.lower() or "practical" in content.lower():
            return (
                "relocate",
                "Scenario test that's more of an example",
                "examples/scenarios/",
            )

    # Tests with heavy resource usage or long execution
    if "resource_monitoring" in characteristics and "large_scale" in characteristics:
        if "stress" in content.lower() or "load" in content.lower():
            return (
                "relocate",
                "Resource-intensive test better suited for performance suite",
                "examples/performance_benchmarks/",
            )

    # Tests that always skip or are marked slow
    if "conditional_skip" in characteristics and len(test_functions) <= 3:
        return "remove", "Test that mostly skips execution", None

    # Docker-dependent tests in unit directory
    if "docker_dependent" in characteristics and "/unit/" in file_path:
        return (
            "relocate",
            "Docker-dependent test in unit directory",
            "tests/integration/",
        )

    # Keep essential tests
    if any(
        essential in content.lower()
        for essential in [
            "regression",
            "ci",
            "smoke",
            "sanity",
            "baseline",
            "threshold",
        ]
    ):
        return "keep", "Essential for CI/CD pipeline", None

    # Keep core functionality tests
    if "/unit/" in file_path and len(test_functions) >= 5:
        return "keep", "Core unit test with good coverage", None

    # Keep integration tests that test real functionality
    if "/integration/" in file_path and not (
        "large_scale" in characteristics and "slow" in characteristics
    ):
        return "keep", "Valid integration test", None

    # Default: review manually
    return "review", "Needs manual review to determine value", None


def generate_removal_relocation_report(
    analysis_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate comprehensive report with recommendations."""

    recommendations = {"remove": [], "relocate": [], "keep": [], "review": []}

    for result in analysis_results:
        rec = result.get("recommendation", "review")
        recommendations[rec].append(result)

    summary = {
        "total_files": len(analysis_results),
        "recommendations": {
            "remove": len(recommendations["remove"]),
            "relocate": len(recommendations["relocate"]),
            "keep": len(recommendations["keep"]),
            "review": len(recommendations["review"]),
        },
        "details": recommendations,
    }

    return summary


def print_analysis_report(summary: Dict[str, Any]):
    """Print detailed analysis report."""
    print("🔍 Performance/Scenario Tests Analysis Report")
    print("=" * 60)

    total = summary["total_files"]
    recs = summary["recommendations"]

    print(f"\n📊 Summary ({total} files analyzed):")
    print(f"  🗑️  Remove: {recs['remove']} files")
    print(f"  📦 Relocate: {recs['relocate']} files")
    print(f"  ✅ Keep: {recs['keep']} files")
    print(f"  🤔 Review: {recs['review']} files")

    print("\n📈 Impact:")
    removal_rate = (recs["remove"] / total) * 100 if total > 0 else 0
    relocation_rate = (recs["relocate"] / total) * 100 if total > 0 else 0
    print(
        f"  Cleanup potential: {removal_rate:.1f}% removal + {relocation_rate:.1f}% relocation"
    )

    # Detailed recommendations
    if summary["details"]["remove"]:
        print(
            f"\n🗑️  Files Recommended for REMOVAL ({len(summary['details']['remove'])}):"
        )
        for item in summary["details"]["remove"]:
            print(f"    ❌ {item['file']}")
            print(f"       Reason: {item['reason']}")

    if summary["details"]["relocate"]:
        print(
            f"\n📦 Files Recommended for RELOCATION ({len(summary['details']['relocate'])}):"
        )
        for item in summary["details"]["relocate"]:
            print(f"    📁 {item['file']} → {item['relocation_target']}")
            print(f"       Reason: {item['reason']}")

    if summary["details"]["keep"]:
        print(f"\n✅ Files to KEEP ({len(summary['details']['keep'])}):")
        for item in summary["details"]["keep"][:5]:  # Show first 5
            print(f"    ✅ {item['file']}")
            print(f"       Reason: {item['reason']}")
        if len(summary["details"]["keep"]) > 5:
            print(f"    ... and {len(summary['details']['keep']) - 5} more")

    if summary["details"]["review"]:
        print(
            f"\n🤔 Files Needing MANUAL REVIEW ({len(summary['details']['review'])}):"
        )
        for item in summary["details"]["review"]:
            print(f"    ❓ {item['file']}")
            print(f"       Reason: {item['reason']}")


def generate_action_script(summary: Dict[str, Any]) -> str:
    """Generate shell script to implement recommendations."""
    script_lines = [
        "#!/bin/bash",
        "# Performance/Scenario Tests Cleanup Script",
        "# Generated automatically - review before executing",
        "",
        "set -e",
        "",
        "echo '🔧 Implementing performance/scenario test cleanup...'",
        "",
    ]

    # Remove files
    if summary["details"]["remove"]:
        script_lines.append("echo '🗑️  Removing obsolete test files...'")
        for item in summary["details"]["remove"]:
            file_path = f"tests/{item['file']}"
            script_lines.append(f"rm -f '{file_path}'  # {item['reason']}")
        script_lines.append("")

    # Create relocation directories
    relocation_dirs = set()
    for item in summary["details"]["relocate"]:
        if item["relocation_target"]:
            relocation_dirs.add(item["relocation_target"])

    if relocation_dirs:
        script_lines.append("echo '📁 Creating relocation directories...'")
        for dir_path in sorted(relocation_dirs):
            script_lines.append(f"mkdir -p '{dir_path}'")
        script_lines.append("")

    # Move files
    if summary["details"]["relocate"]:
        script_lines.append("echo '📦 Relocating test files...'")
        for item in summary["details"]["relocate"]:
            if item["relocation_target"]:
                src = f"tests/{item['file']}"
                dst = f"{item['relocation_target']}{Path(item['file']).name}"
                script_lines.append(f"mv '{src}' '{dst}'  # {item['reason']}")
        script_lines.append("")

    script_lines.extend(
        [
            "echo '✅ Cleanup completed!'",
            "echo '📊 Summary:'",
            f"echo '  Removed: {len(summary['details']['remove'])} files'",
            f"echo '  Relocated: {len(summary['details']['relocate'])} files'",
            f"echo '  Kept: {len(summary['details']['keep'])} files'",
            "",
        ]
    )

    return "\n".join(script_lines)


def main():
    """Main analysis function."""
    print("🚀 Starting Performance/Scenario Tests Analysis")

    # Find test files
    test_patterns = find_performance_scenario_tests()

    all_files = []
    for pattern_name, files in test_patterns.items():
        all_files.extend(files)

    # Remove duplicates
    unique_files = list(set(all_files))

    print(f"\n📋 Found {len(unique_files)} performance/scenario test files:")
    for pattern_name, files in test_patterns.items():
        if files:
            print(f"  {pattern_name}: {len(files)} files")

    # Analyze each file
    analysis_results = []
    for test_file in unique_files:
        analysis = analyze_test_file(test_file)
        analysis_results.append(analysis)

    # Generate report
    summary = generate_removal_relocation_report(analysis_results)
    print_analysis_report(summary)

    # Generate action script
    action_script = generate_action_script(summary)

    script_path = Path("scripts/testing/cleanup_performance_tests.sh")
    script_path.write_text(action_script)
    script_path.chmod(0o755)

    print(f"\n🔧 Generated cleanup script: {script_path}")
    print("Review the script before executing!")

    # Return exit code based on findings
    total_cleanup = (
        summary["recommendations"]["remove"] + summary["recommendations"]["relocate"]
    )
    if total_cleanup > 0:
        return 0  # Success - found items to clean up
    else:
        return 1  # No cleanup needed


if __name__ == "__main__":
    sys.exit(main())

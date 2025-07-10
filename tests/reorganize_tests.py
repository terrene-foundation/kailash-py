#!/usr/bin/env python3
"""
Script to analyze and reorganize tests according to the test organization policy.
Identifies tests with sleep calls and categorizes them for proper placement.
"""

import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

# Test categories based on sleep usage patterns
CATEGORIES = {
    "timing_simulation": {
        "pattern": r"sleep\([0-9.]+\).*#.*[Ss]imulat",
        "action": "refactor",
        "reason": "Uses sleep to simulate timing - should use mocked time",
    },
    "real_timing": {
        "pattern": r"sleep.*#.*[Ww]ait|[Dd]elay|[Tt]ime",
        "action": "move_to_integration",
        "reason": "Requires real time delays - belongs in integration",
    },
    "health_check": {
        "pattern": r"sleep.*health|monitoring",
        "action": "move_to_integration",
        "reason": "Health check/monitoring tests need real timing",
    },
    "stress_test": {
        "pattern": r"stress|load|performance",
        "action": "move_to_e2e",
        "reason": "Performance/stress tests belong in e2e",
    },
    "background_task": {
        "pattern": r"background.*task.*sleep|while.*True.*sleep",
        "action": "move_to_integration",
        "reason": "Background tasks require real async behavior",
    },
}


def analyze_test_file(filepath: Path) -> Dict[str, any]:
    """Analyze a test file for sleep usage and categorize it."""
    with open(filepath, "r") as f:
        content = f.read()

    # Find all sleep calls
    sleep_calls = re.findall(r"(.*sleep\(.*\).*)", content)

    # Check for test markers
    has_integration_marker = "@pytest.mark.integration" in content
    has_slow_marker = "@pytest.mark.slow" in content
    has_unit_marker = "@pytest.mark.unit" in content

    # Categorize based on patterns
    category = None
    for cat_name, cat_info in CATEGORIES.items():
        if re.search(cat_info["pattern"], content, re.IGNORECASE):
            category = cat_name
            break

    # Count test functions
    test_count = len(re.findall(r"^(?:async )?def test_", content, re.MULTILINE))

    return {
        "path": filepath,
        "sleep_count": len(sleep_calls),
        "sleep_examples": sleep_calls[:3],  # First 3 examples
        "category": category,
        "test_count": test_count,
        "markers": {
            "integration": has_integration_marker,
            "slow": has_slow_marker,
            "unit": has_unit_marker,
        },
    }


def get_recommendation(analysis: Dict) -> Dict[str, str]:
    """Get recommendation for what to do with a test file."""
    if analysis["sleep_count"] == 0:
        return {"action": "keep", "reason": "No sleep calls"}

    if analysis["category"]:
        cat_info = CATEGORIES[analysis["category"]]
        return {"action": cat_info["action"], "reason": cat_info["reason"]}

    # Default based on sleep count
    if analysis["sleep_count"] > 5:
        return {
            "action": "move_to_integration",
            "reason": f"High sleep count ({analysis['sleep_count']})",
        }

    return {"action": "refactor", "reason": "Few sleep calls - can be mocked"}


def main():
    """Main function to analyze and categorize tests."""
    unit_tests_dir = Path("tests/unit")

    # Find all test files with sleep calls
    test_files = []
    for root, dirs, files in os.walk(unit_tests_dir):
        for file in files:
            if file.startswith("test_") and file.endswith(".py"):
                filepath = Path(root) / file
                # Quick check for sleep
                with open(filepath, "r") as f:
                    if "sleep" in f.read():
                        test_files.append(filepath)

    print(f"Found {len(test_files)} test files with sleep calls in unit/")
    print("=" * 80)

    # Analyze each file
    analyses = []
    for filepath in sorted(test_files):
        analysis = analyze_test_file(filepath)
        recommendation = get_recommendation(analysis)
        analysis["recommendation"] = recommendation
        analyses.append(analysis)

        # Print summary
        rel_path = filepath.relative_to("tests/unit")
        print(f"\n{rel_path}")
        print(f"  Sleep calls: {analysis['sleep_count']}")
        print(f"  Test count: {analysis['test_count']}")
        print(f"  Category: {analysis['category'] or 'uncategorized'}")
        print(f"  Action: {recommendation['action']}")
        print(f"  Reason: {recommendation['reason']}")

        if analysis["sleep_examples"]:
            print("  Examples:")
            for ex in analysis["sleep_examples"][:2]:
                print(f"    {ex.strip()}")

    # Summary by action
    print("\n" + "=" * 80)
    print("SUMMARY BY ACTION:")
    action_counts = {}
    for analysis in analyses:
        action = analysis["recommendation"]["action"]
        action_counts[action] = action_counts.get(action, 0) + 1

    for action, count in sorted(action_counts.items()):
        print(f"  {action}: {count} files")

    # Generate move commands
    print("\n" + "=" * 80)
    print("RECOMMENDED MOVES:")
    for analysis in analyses:
        if analysis["recommendation"]["action"].startswith("move_to_"):
            src = analysis["path"]
            target_dir = analysis["recommendation"]["action"].replace("move_to_", "")
            rel_path = src.relative_to("tests/unit")
            dest = Path(f"tests/{target_dir}") / rel_path
            print(f"mv {src} {dest}")


if __name__ == "__main__":
    main()

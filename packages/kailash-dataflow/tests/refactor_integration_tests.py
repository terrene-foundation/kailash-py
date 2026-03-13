#!/usr/bin/env python3
"""
Script to refactor integration tests to use IntegrationTestSuite.
This script helps automate the conversion of hardcoded database URLs
to use the standardized IntegrationTestSuite fixture system.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

# Patterns to detect hardcoded database configurations
HARDCODED_PATTERNS = [
    # Direct PostgreSQL URLs
    (r'postgresql://[^"\']+@localhost:543[0-9][^"\']*', "HARDCODED_URL"),
    # TEST_DATABASE_URL environment variable
    (r'os\.getenv\(["\']TEST_DATABASE_URL["\']\s*(?:,\s*[^)]+)?\)', "ENV_VAR"),
    # Direct asyncpg.connect calls
    (r"asyncpg\.connect\([^)]+\)", "DIRECT_CONNECT"),
    # Database URL assignments
    (r'db_url\s*=\s*["\']postgresql://[^"\']+["\']\s*', "URL_ASSIGNMENT"),
]

# Template for the new fixture
FIXTURE_TEMPLATE = '''from tests.infrastructure.test_harness import IntegrationTestSuite

@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite
'''


def find_integration_test_files(base_path: str) -> List[Path]:
    """Find all Python test files in integration directory."""
    integration_path = Path(base_path) / "tests" / "integration"
    return list(integration_path.rglob("test_*.py"))


def detect_hardcoded_patterns(file_path: Path) -> List[Tuple[int, str, str]]:
    """Detect hardcoded database patterns in a file."""
    issues = []

    with open(file_path, "r") as f:
        lines = f.readlines()

    for line_num, line in enumerate(lines, 1):
        for pattern, pattern_type in HARDCODED_PATTERNS:
            if re.search(pattern, line):
                issues.append((line_num, pattern_type, line.strip()))

    return issues


def generate_refactoring_report(base_path: str):
    """Generate a report of all files that need refactoring."""
    test_files = find_integration_test_files(base_path)

    report = []
    for file_path in test_files:
        issues = detect_hardcoded_patterns(file_path)
        if issues:
            report.append(
                {"file": str(file_path.relative_to(base_path)), "issues": issues}
            )

    return report


def suggest_refactoring(file_content: str) -> str:
    """Suggest refactored code using IntegrationTestSuite."""
    suggestions = []

    # Check if IntegrationTestSuite is already imported
    if "IntegrationTestSuite" not in file_content:
        suggestions.append(
            "Add import: from tests.infrastructure.test_harness import IntegrationTestSuite"
        )

    # Check for test_suite fixture
    if "@pytest.fixture" in file_content and "test_suite" not in file_content:
        suggestions.append("Add the test_suite fixture (see FIXTURE_TEMPLATE)")

    # Suggest replacements
    if "os.getenv" in file_content and "TEST_DATABASE_URL" in file_content:
        suggestions.append(
            "Replace os.getenv('TEST_DATABASE_URL') with test_suite.config.url"
        )

    if "asyncpg.connect" in file_content:
        suggestions.append("Replace asyncpg.connect() with test_suite.get_connection()")

    if "postgresql://" in file_content:
        suggestions.append(
            "Replace hardcoded PostgreSQL URLs with test_suite.config.url"
        )

    return suggestions


def main():
    """Main function to run the refactoring analysis."""
    base_path = ""

    print("🔍 Analyzing integration tests for refactoring needs...")
    print("=" * 60)

    report = generate_refactoring_report(base_path)

    print(f"\nFound {len(report)} files that need refactoring:\n")

    for item in report:
        print(f"📄 {item['file']}")
        for line_num, pattern_type, line_content in item["issues"]:
            print(f"   Line {line_num} [{pattern_type}]: {line_content[:80]}...")
        print()

    print("\n📋 Summary:")
    print(f"Total files needing refactoring: {len(report)}")

    total_issues = sum(len(item["issues"]) for item in report)
    print(f"Total hardcoded patterns found: {total_issues}")

    print("\n✨ Refactoring Guidelines:")
    print("1. Add IntegrationTestSuite import")
    print("2. Create test_suite fixture")
    print("3. Replace hardcoded URLs with test_suite.config.url")
    print("4. Replace asyncpg.connect with test_suite.get_connection()")
    print("5. Remove os.getenv('TEST_DATABASE_URL') calls")

    # Save report to file
    report_path = Path(base_path) / "tests" / "integration_refactor_report.txt"
    with open(report_path, "w") as f:
        f.write("Integration Test Refactoring Report\n")
        f.write("=" * 60 + "\n\n")

        for item in report:
            f.write(f"File: {item['file']}\n")
            for line_num, pattern_type, line_content in item["issues"]:
                f.write(f"  Line {line_num} [{pattern_type}]: {line_content}\n")
            f.write("\n")

        f.write(f"\nTotal files: {len(report)}\n")
        f.write(f"Total issues: {total_issues}\n")

    print(f"\n📁 Report saved to: {report_path}")


if __name__ == "__main__":
    main()

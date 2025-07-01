#!/usr/bin/env python3
"""
Migration script to help teams transition from mock-based API tests to Docker-based tests.

This script:
1. Identifies test files using mocks instead of real services
2. Provides instructions for migration
3. Can be run in CI to enforce the policy
"""

import ast
import os
import sys
from pathlib import Path
from typing import List, Tuple


def find_mock_imports(file_path: Path) -> List[str]:
    """Find mock-related imports in a Python file."""
    mock_imports = []

    try:
        with open(file_path, "r") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "mock" in node.module:
                    mock_imports.append(
                        f"from {node.module} import {', '.join(n.name for n in node.names)}"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "mock" in alias.name.lower():
                        mock_imports.append(f"import {alias.name}")
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")

    return mock_imports


def check_for_patch_usage(file_path: Path) -> List[Tuple[int, str]]:
    """Find lines using @patch or with patch() in a file."""
    patch_usage = []

    try:
        with open(file_path, "r") as f:
            lines = f.readlines()

        for i, line in enumerate(lines, 1):
            if "@patch" in line or "with patch" in line:
                patch_usage.append((i, line.strip()))
    except Exception as e:
        print(f"Error reading {file_path}: {e}")

    return patch_usage


def scan_integration_tests(base_path: Path) -> dict:
    """Scan integration tests for mock usage."""
    results = {}
    integration_path = base_path / "tests" / "integration"

    if not integration_path.exists():
        print(f"Integration test directory not found: {integration_path}")
        return results

    for py_file in integration_path.rglob("*.py"):
        # Skip __pycache__ and other non-test files
        if "__pycache__" in str(py_file) or not py_file.name.startswith("test_"):
            continue

        mock_imports = find_mock_imports(py_file)
        patch_usage = check_for_patch_usage(py_file)

        if mock_imports or patch_usage:
            results[str(py_file)] = {
                "mock_imports": mock_imports,
                "patch_usage": patch_usage,
            }

    return results


def generate_migration_report(violations: dict) -> str:
    """Generate a detailed migration report."""
    report = ["# Integration Test Mock Usage Report\n"]
    report.append(f"Found {len(violations)} files with potential violations:\n")

    for file_path, issues in violations.items():
        report.append(f"\n## {file_path}")

        if issues["mock_imports"]:
            report.append("\n### Mock Imports Found:")
            for import_stmt in issues["mock_imports"]:
                report.append(f"- `{import_stmt}`")

        if issues["patch_usage"]:
            report.append("\n### Patch Usage Found:")
            for line_num, line in issues["patch_usage"]:
                report.append(f"- Line {line_num}: `{line}`")

        report.append("\n### Migration Steps:")
        report.append("1. Remove mock imports")
        report.append("2. Ensure Docker services are running:")
        report.append("   ```bash")
        report.append("   docker-compose -f tests/utils/docker-compose.test.yml up -d")
        report.append("   ```")
        report.append(
            "3. Replace mocked calls with real HTTP requests to mock-api service"
        )
        report.append(
            "4. See `tests/integration/nodes/test_api_with_real_docker_services.py` for examples"
        )

    return "\n".join(report)


def main():
    """Main entry point."""
    # Find project root
    current_path = Path(__file__).parent.parent

    print("Scanning integration tests for mock usage...")
    violations = scan_integration_tests(current_path)

    # Exclude legitimate test fixture files
    legitimate_files = [
        "test_fixtures.py",  # Tests the testing framework itself
        "conftest.py",  # May contain test fixtures
    ]

    filtered_violations = {}
    for file_path, issues in violations.items():
        if not any(legit in file_path for legit in legitimate_files):
            filtered_violations[file_path] = issues

    if filtered_violations:
        report = generate_migration_report(filtered_violations)
        print(report)

        # Write report to file
        report_path = current_path / "INTEGRATION_TEST_MIGRATION_REPORT.md"
        with open(report_path, "w") as f:
            f.write(report)
        print(f"\nDetailed report written to: {report_path}")

        # Exit with error code for CI
        sys.exit(1)
    else:
        print("\n✅ No mock usage violations found in integration tests!")
        sys.exit(0)


if __name__ == "__main__":
    main()

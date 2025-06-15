#!/usr/bin/env python3
"""
Test Reorganization Script

This script reorganizes test files into a proper structure:
- Unit tests: Fast, isolated component tests
- Integration tests: Tests that combine multiple components
- E2E tests: End-to-end business scenario tests

Usage:
    python scripts/testing/reorganize_tests.py [--dry-run]
"""

import argparse
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

# Test categorization patterns
UNIT_TEST_PATTERNS = [
    r"test_.*validation.*\.py$",
    r"test_.*schema.*\.py$",
    r"test_.*metadata.*\.py$",
    r"test_.*base\.py$",
    r"test_.*conftest\.py$",
    r"test_.*node\.py$",
    r"test_.*utils.*\.py$",
    r"test_.*template.*\.py$",
    r"test_.*export\.py$",
]

INTEGRATION_TEST_PATTERNS = [
    r".*integration.*\.py$",
    r"test_.*workflow.*\.py$",
    r"test_.*runtime.*\.py$",
    r"test_.*execution.*\.py$",
    r"test_.*cycle.*\.py$",
    r"test_.*gateway.*\.py$",
    r"test_.*api.*\.py$",
    r"test_.*communication.*\.py$",
]

E2E_TEST_PATTERNS = [
    r"test_.*enterprise.*\.py$",
    r"test_.*performance.*\.py$",
    r"test_.*scenario.*\.py$",
    r"test_.*comprehensive.*\.py$",
    r"test_.*example.*\.py$",
]

# Mapping of old paths to new paths
TEST_MAPPINGS = {
    # Examples that should be tests
    "examples/feature_examples/": "tests/",
    # Specific directory mappings
    "test_nodes/": "unit/nodes/",
    "test_middleware/": "unit/middleware/",
    "test_runtime/": "unit/runtime/",
    "test_workflow/": "unit/workflow/",
    "test_validation/": "unit/validation/",
    "test_utils/": "unit/utils/",
    "test_schema/": "unit/schema/",
    "test_tracking/": "unit/tracking/",
    "test_visualization/": "unit/visualization/",
    "test_security/": "unit/security/",
    "test_cli/": "unit/cli/",
    "test_api/": "integration/api/",
    "test_enterprise/": "integration/enterprise/",
    "test_refactored_architecture/": "integration/architecture/",
}

# Files to exclude from reorganization
EXCLUDE_FILES = [
    "__init__.py",
    "conftest.py",
    "README.md",
    ".gitignore",
]


class TestReorganizer:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.base_path = Path.cwd()
        self.moves = []
        self.errors = []

    def categorize_test(self, file_path: str) -> str:
        """Categorize a test file as unit, integration, or e2e."""
        file_name = os.path.basename(file_path)

        # Check patterns in order of specificity
        for pattern in E2E_TEST_PATTERNS:
            if re.search(pattern, file_name):
                return "e2e"

        for pattern in INTEGRATION_TEST_PATTERNS:
            if re.search(pattern, file_name):
                return "integration"

        for pattern in UNIT_TEST_PATTERNS:
            if re.search(pattern, file_name):
                return "unit"

        # Default categorization based on content
        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Look for integration test indicators
            if any(
                indicator in content
                for indicator in [
                    "LocalRuntime",
                    "AsyncLocalRuntime",
                    "workflow.execute",
                    "runtime.execute",
                    "integration",
                    "end_to_end",
                ]
            ):
                return "integration"

            # Look for unit test indicators
            if any(
                indicator in content
                for indicator in ["mock", "Mock", "patch", "@patch", "unit"]
            ):
                return "unit"

        except Exception:
            pass

        # Default to unit test
        return "unit"

    def determine_new_path(self, old_path: str) -> str:
        """Determine the new path for a test file."""
        # Normalize path
        old_path = old_path.replace(str(self.base_path) + "/", "")

        # Check if file is in examples directory
        if old_path.startswith("examples/"):
            # Extract the test file name and relevant path parts
            parts = old_path.split("/")

            # Find the category (nodes, workflows, etc.)
            if "nodes" in parts:
                idx = parts.index("nodes")
                if idx + 1 < len(parts):
                    category = f"nodes/{parts[idx + 1]}"
                else:
                    category = "nodes"
            elif "workflows" in parts:
                category = "workflows"
            elif "runtime" in parts:
                category = "runtime"
            elif "integrations" in parts:
                category = "integrations"
            else:
                category = "misc"

            file_name = os.path.basename(old_path)
            test_type = self.categorize_test(old_path)

            return f"tests/{test_type}/{category}/{file_name}"

        # Check specific mappings
        for old_pattern, new_pattern in TEST_MAPPINGS.items():
            if old_pattern in old_path:
                new_path = old_path.replace(old_pattern, new_pattern)
                # Ensure it starts with tests/
                if not new_path.startswith("tests/"):
                    new_path = "tests/" + new_path
                return new_path

        # Default case - categorize and place appropriately
        test_type = self.categorize_test(old_path)
        file_name = os.path.basename(old_path)

        # Extract subdirectory if present
        if "/test_" in old_path:
            parts = old_path.split("/")
            for i, part in enumerate(parts):
                if part.startswith("test_") and i > 0:
                    subdir = parts[i].replace("test_", "")
                    return f"tests/{test_type}/{subdir}/{file_name}"

        return f"tests/{test_type}/{file_name}"

    def find_test_files(self) -> List[str]:
        """Find all test files in the project."""
        test_files = []

        # Search in tests directory
        for root, dirs, files in os.walk("tests"):
            for file in files:
                if file.endswith("_test.py") or file.startswith("test_"):
                    if file not in EXCLUDE_FILES:
                        test_files.append(os.path.join(root, file))

        # Search in examples directory for misplaced tests
        for root, dirs, files in os.walk("examples"):
            for file in files:
                if "test" in file.lower() and file.endswith(".py"):
                    if file not in EXCLUDE_FILES:
                        test_files.append(os.path.join(root, file))

        return test_files

    def plan_moves(self) -> List[Tuple[str, str]]:
        """Plan all file moves without executing them."""
        test_files = self.find_test_files()
        moves = []

        for old_path in test_files:
            new_path = self.determine_new_path(old_path)

            # Skip if already in correct location
            if old_path == new_path:
                continue

            moves.append((old_path, new_path))

        return moves

    def execute_move(self, old_path: str, new_path: str):
        """Execute a single file move."""
        try:
            # Create destination directory
            new_dir = os.path.dirname(new_path)
            os.makedirs(new_dir, exist_ok=True)

            # Move the file
            if not self.dry_run:
                shutil.move(old_path, new_path)
                print(f"Moved: {old_path} -> {new_path}")
            else:
                print(f"Would move: {old_path} -> {new_path}")

        except Exception as e:
            self.errors.append(f"Error moving {old_path}: {str(e)}")

    def reorganize(self):
        """Execute the test reorganization."""
        print("Analyzing test files...")
        moves = self.plan_moves()

        if not moves:
            print("No files need to be moved!")
            return

        print(f"\nFound {len(moves)} files to reorganize")

        if self.dry_run:
            print("\n--- DRY RUN MODE ---")

        # Execute moves
        for old_path, new_path in moves:
            self.execute_move(old_path, new_path)

        # Print summary
        print(f"\n{'Would move' if self.dry_run else 'Moved'} {len(moves)} files")

        if self.errors:
            print(f"\nErrors encountered: {len(self.errors)}")
            for error in self.errors:
                print(f"  - {error}")

        # Create __init__.py files
        if not self.dry_run:
            self.create_init_files()

    def create_init_files(self):
        """Create __init__.py files in all test directories."""
        for root, dirs, files in os.walk("tests"):
            init_file = os.path.join(root, "__init__.py")
            if not os.path.exists(init_file):
                Path(init_file).touch()
                print(f"Created: {init_file}")


def main():
    parser = argparse.ArgumentParser(description="Reorganize test files")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    args = parser.parse_args()

    reorganizer = TestReorganizer(dry_run=args.dry_run)
    reorganizer.reorganize()


if __name__ == "__main__":
    main()

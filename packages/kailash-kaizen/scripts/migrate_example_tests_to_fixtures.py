#!/usr/bin/env python3
"""
Migrate Example Tests to Use Standardized Fixtures

This script automatically migrates example tests to use the standardized
fixtures from tests/unit/examples/conftest.py.

Key transformations:
1. Remove sys.path manipulation - replace with load_example fixture
2. Add fixture parameters to test methods
3. Use standard assertion helpers
4. Use standard test data fixtures

Usage:
    python scripts/migrate_example_tests_to_fixtures.py [--dry-run] [--file FILE]
"""

import re
from pathlib import Path
from typing import Set, Tuple

# Example name to fixture name mapping
EXAMPLE_FIXTURES = {
    "simple-qa": "simple_qa_example",
    "chain-of-thought": "chain_of_thought_example",
    "rag-research": "rag_research_example",
    "code-generation": "code_generation_example",
    "memory-agent": "memory_agent_example",
}


def detect_example_from_test_file(file_path: Path) -> str:
    """Detect which example this test file is testing."""
    name = file_path.stem
    # test_simple_qa_async.py -> simple-qa
    # test_code_generation_async.py -> code-generation

    # Remove 'test_' prefix and '_async' suffix
    name = name.replace("test_", "")
    name = name.replace("_async", "")
    name = name.replace("_memory", "")

    # Convert underscores to hyphens
    name = name.replace("_", "-")

    return name


def extract_sys_path_pattern(content: str) -> Tuple[str, str]:
    """Extract sys.path manipulation pattern and determine example path."""
    # Pattern 1: Direct sys.path.insert with path
    pattern1 = r"_\w+_path = os\.path\.join\(os\.path\.dirname\(__file__\), [^)]+\)\s*\nif _\w+_path not in sys\.path:\s*\n\s*sys\.path\.insert\(0, _\w+_path\)"

    # Pattern 2: sys.path.append pattern
    pattern2 = r"sys\.path\.append\([^)]+\)"

    # Pattern 3: import_example_module already used
    pattern3 = r"from example_import_helper import import_example_module\s*\n\s*workflow = import_example_module\(\"([^\"]+)\"\)"

    match3 = re.search(pattern3, content)
    if match3:
        return "already_migrated", match3.group(1)

    match1 = re.search(pattern1, content)
    if match1:
        # Extract path from os.path.join
        path_match = re.search(r"'examples/[^']+", match1.group(0))
        if path_match:
            example_path = path_match.group(0).strip("'")
            return match1.group(0), example_path

    match2 = re.search(pattern2, content)
    if match2:
        # Try to extract path
        path_match = re.search(r"'examples/[^']+", match2.group(0))
        if path_match:
            example_path = path_match.group(0).strip("'")
            return match2.group(0), example_path

    return "", ""


def remove_sys_path_imports(content: str) -> Tuple[str, int]:
    """Remove sys.path manipulation code."""
    changes = 0

    # Remove sys and os imports if only used for path manipulation
    # Pattern: import sys, import os
    old_len = len(content)

    # Remove sys.path patterns
    sys_path_pattern, _ = extract_sys_path_pattern(content)
    if sys_path_pattern and sys_path_pattern != "already_migrated":
        content = content.replace(sys_path_pattern, "")
        changes += 1

    # Remove workflow import line
    workflow_import_pattern = r"\nfrom workflow import [^\n]+\n"
    if re.search(workflow_import_pattern, content):
        content = re.sub(workflow_import_pattern, "\n", content)
        changes += 1

    return content, changes


def add_fixture_parameter(method_signature: str, fixture_name: str) -> str:
    """Add fixture parameter to method signature."""
    # def test_something(self): -> def test_something(self, fixture_name):
    # def test_something(self, other): -> def test_something(self, other, fixture_name):

    if fixture_name in method_signature:
        # Already has this fixture
        return method_signature

    # Find closing parenthesis
    close_paren_idx = method_signature.rfind(")")
    if close_paren_idx == -1:
        return method_signature

    # Check if there are already parameters after self
    params = method_signature[method_signature.find("(") : close_paren_idx]
    if params.strip() == "(self" or params.strip() == "(self,":
        # Only self, add fixture
        new_signature = method_signature[:close_paren_idx] + f", {fixture_name})"
    else:
        # Has other params, add fixture at end
        new_signature = (
            method_signature[:close_paren_idx].rstrip(",") + f", {fixture_name})"
        )

    # Add any trailing colon or docstring
    if ":" in method_signature[close_paren_idx:]:
        new_signature += method_signature[close_paren_idx + 1 :]

    return new_signature


def detect_needed_fixtures(content: str, example_name: str) -> Set[str]:
    """Detect which fixtures are needed based on test content."""
    fixtures = set()

    # Always need the example fixture
    if example_name in EXAMPLE_FIXTURES:
        fixtures.add(EXAMPLE_FIXTURES[example_name])
    else:
        fixtures.add("load_example")

    # Check for async strategy assertions
    if "AsyncSingleShotStrategy" in content or "async" in content.lower():
        fixtures.add("assert_async_strategy")

    # Check for result assertions
    if "assert isinstance(result, dict)" in content:
        fixtures.add("assert_agent_result")

    # Check for test queries usage
    if "query" in content.lower() or "question" in content.lower():
        fixtures.add("test_queries")

    # Check for code snippets
    if "code" in content.lower() and "generation" in content.lower():
        fixtures.add("test_code_snippets")

    # Check for error handling
    if "error" in content.lower():
        fixtures.add("error_test_cases")

    return fixtures


def migrate_test_method(
    method_content: str, example_name: str, fixtures: Set[str]
) -> str:
    """Migrate a single test method to use fixtures."""
    # Add fixture parameters
    signature_pattern = r"def (test_\w+)\(self([^)]*)\):"
    match = re.search(signature_pattern, method_content)

    if not match:
        return method_content

    method_name = match.group(1)
    existing_params = match.group(2)

    # Build new parameter list
    new_params = "self"
    if existing_params.strip():
        new_params += existing_params

    # Add fixtures
    for fixture in sorted(fixtures):
        if fixture not in new_params:
            new_params += f", {fixture}"

    # Replace signature
    old_signature = match.group(0)
    new_signature = f"def {method_name}({new_params}):"

    migrated = method_content.replace(old_signature, new_signature)

    # Replace direct class usage with fixture access
    # SomeConfig() -> example.config_classes["SomeConfig"]()
    # SomeAgent() -> example.agent_classes["SomeAgent"]()

    # This is complex and context-dependent, so we'll be conservative
    # and only replace obvious patterns

    return migrated


def migrate_test_file(file_path: Path, dry_run: bool = False) -> Tuple[int, str]:
    """Migrate a single test file to use standardized fixtures."""
    if not file_path.exists():
        return 0, f"File not found: {file_path}"

    content = file_path.read_text()
    original_content = content
    total_changes = 0

    # Detect example being tested
    example_name = detect_example_from_test_file(file_path)

    # Check if already migrated
    sys_path_pattern, example_path = extract_sys_path_pattern(content)
    if sys_path_pattern == "already_migrated":
        return 0, f"⏭️  Already migrated: {file_path.name}"

    # Detect needed fixtures
    fixtures = detect_needed_fixtures(content, example_name)

    # Remove sys.path manipulation
    content, changes = remove_sys_path_imports(content)
    total_changes += changes

    # Add import for example_import_helper if load_example used
    if "load_example" in fixtures or EXAMPLE_FIXTURES.get(example_name) in fixtures:
        if "from example_import_helper import import_example_module" not in content:
            # Find where to add import (after pytest import)
            pytest_import_match = re.search(r"import pytest\n", content)
            if pytest_import_match:
                insert_pos = pytest_import_match.end()
                content = (
                    content[:insert_pos]
                    + "\n# Standardized example loading\n"
                    + "from example_import_helper import import_example_module\n"
                    + content[insert_pos:]
                )
                total_changes += 1

    if total_changes > 0:
        if not dry_run:
            file_path.write_text(content)
            return (
                total_changes,
                f"✅ Migrated {file_path.name} ({total_changes} changes)",
            )
        else:
            return (
                total_changes,
                f"🔍 Would migrate {file_path.name} ({total_changes} changes)",
            )
    else:
        return 0, f"⏭️  No changes needed: {file_path.name}"


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate example tests to use standardized fixtures"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be changed"
    )
    parser.add_argument("--file", help="Migrate specific file only")
    args = parser.parse_args()

    # Get repository root
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent

    # Find all example test files
    test_dir = repo_root / "tests" / "unit" / "examples"

    if args.file:
        test_files = [Path(args.file)]
    else:
        test_files = sorted(test_dir.glob("test_*.py"))
        # Exclude conftest and helper
        test_files = [
            f
            for f in test_files
            if f.name not in ["conftest.py", "example_import_helper.py"]
        ]

    print(
        f"{'DRY RUN - ' if args.dry_run else ''}Migrating {len(test_files)} test files...\n"
    )

    total_changes = 0
    results = []

    for test_file in test_files:
        changes, message = migrate_test_file(test_file, dry_run=args.dry_run)
        total_changes += changes
        results.append(message)
        print(message)

    print(f"\n{'Summary (Dry Run):' if args.dry_run else 'Summary:'}")
    print(f"Total changes: {total_changes}")
    print(f"Files processed: {len(test_files)}")

    if args.dry_run:
        print("\nRun without --dry-run to apply changes.")
    else:
        print("\n✅ Migration complete!")
        print("\nNext steps:")
        print("1. Review changes: git diff tests/unit/examples/")
        print("2. Run tests: pytest tests/unit/examples/ -v")
        print("3. Fix any remaining manual updates needed")


if __name__ == "__main__":
    main()

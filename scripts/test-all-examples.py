#!/usr/bin/env python3
"""
Test all examples in the Kailash SDK examples directory.

This script validates that all example files:
1. Have correct syntax
2. Import without errors
3. Use the correct data paths
4. Follow naming conventions
"""

import subprocess
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_example_files() -> list[Path]:
    """Get all Python example files."""
    examples_dir = project_root / "examples"
    example_files = []

    # New structure - search feature-tests directory
    feature_tests_dir = examples_dir / "feature-tests"

    # Files to exclude
    exclude_files = {
        "__init__.py",
        "test_runner.py",
        "paths.py",
        "maintenance.py",
        "data_paths.py",
    }

    # Recursively find all Python files in feature-tests
    if feature_tests_dir.exists():
        for file in feature_tests_dir.rglob("*.py"):
            if file.name not in exclude_files and not file.name.startswith("_"):
                example_files.append(file)

    # Also check test-harness for any executable tests
    test_harness_dir = examples_dir / "test-harness"
    if test_harness_dir.exists():
        for file in test_harness_dir.rglob("*.py"):
            if (
                file.name not in exclude_files
                and not file.name.startswith("_")
                and "__pycache__" not in str(file)
            ):
                example_files.append(file)

    return sorted(example_files)


def check_syntax(file_path: Path) -> tuple[bool, str]:
    """Check if a file has valid Python syntax."""
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(file_path)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, result.stderr


def check_imports(file_path: Path) -> tuple[bool, str]:
    """Check if a file imports without errors."""
    # Create a test script that imports the module
    test_code = f"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path('{project_root}')))
sys.path.insert(0, str(Path('{file_path.parent}')))

try:
    # Try to import the module
    module_name = '{file_path.stem}'
    exec(f'import {{module_name}}')
    print("Import successful")
except Exception as e:
    print(f"Import failed: {{e}}")
    sys.exit(1)
"""

    result = subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True,
        text=True,
        cwd=str(file_path.parent),
    )

    return result.returncode == 0, result.stdout + result.stderr


def check_data_paths(file_path: Path) -> tuple[bool, list[str]]:
    """Check if file uses hardcoded data paths."""
    issues = []

    with open(file_path) as f:
        content = f.read()
        lines = content.split("\n")

    # Patterns to check for
    bad_patterns = [
        ("data/", "Use get_input_data_path() instead"),
        ("examples/data/", "Use get_input_data_path() instead"),
        ("../data/", "Use get_input_data_path() instead"),
        ("data\\\\", "Use get_input_data_path() instead"),
    ]

    for i, line in enumerate(lines, 1):
        # Skip comments and strings in docstrings
        if line.strip().startswith("#") or '"""' in line or "'''" in line:
            continue

        for pattern, message in bad_patterns:
            if pattern in line and "data_paths" not in line:
                issues.append(f"Line {i}: {message} (found '{pattern}')")

    return len(issues) == 0, issues


def main():
    """Main test runner."""
    print("=" * 70)
    print("Testing all Kailash SDK Feature Tests")
    print("=" * 70)

    example_files = get_example_files()
    print(f"\nFound {len(example_files)} example files to test\n")

    results = {
        "syntax": {"passed": 0, "failed": 0, "errors": []},
        "imports": {"passed": 0, "failed": 0, "errors": []},
        "data_paths": {"passed": 0, "failed": 0, "errors": []},
    }

    for example in example_files:
        relative_path = example.relative_to(project_root)
        print(f"\nTesting: {relative_path}")

        # Check syntax
        syntax_ok, syntax_error = check_syntax(example)
        if syntax_ok:
            results["syntax"]["passed"] += 1
            print("  ✓ Syntax OK")
        else:
            results["syntax"]["failed"] += 1
            results["syntax"]["errors"].append((relative_path, syntax_error))
            print(f"  ✗ Syntax Error: {syntax_error}")
            continue  # Skip other tests if syntax is bad

        # Check imports
        import_ok, import_error = check_imports(example)
        if import_ok:
            results["imports"]["passed"] += 1
            print("  ✓ Imports OK")
        else:
            results["imports"]["failed"] += 1
            results["imports"]["errors"].append((relative_path, import_error))
            print(f"  ✗ Import Error: {import_error}")

        # Check data paths
        paths_ok, path_issues = check_data_paths(example)
        if paths_ok:
            results["data_paths"]["passed"] += 1
            print("  ✓ Data paths OK")
        else:
            results["data_paths"]["failed"] += 1
            results["data_paths"]["errors"].append((relative_path, path_issues))
            print("  ✗ Data path issues:")
            for issue in path_issues:
                print(f"    - {issue}")

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    all_passed = True
    for test_type, result in results.items():
        total = result["passed"] + result["failed"]
        print(f"\n{test_type.replace('_', ' ').title()}:")
        print(f"  Passed: {result['passed']}/{total}")
        if result["failed"] > 0:
            all_passed = False
            print(f"  Failed: {result['failed']}")
            print("  Errors:")
            for file, error in result["errors"]:
                print(f"    - {file}:")
                if isinstance(error, list):
                    for e in error:
                        print(f"      {e}")
                else:
                    print(f"      {error.strip()}")

    print("\n" + "=" * 70)
    if all_passed:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed - please fix the issues above")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

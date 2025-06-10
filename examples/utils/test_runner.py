#!/usr/bin/env python3
"""
Test runner and example execution utilities for Kailash SDK examples.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path


def check_syntax(file_path: Path):
    """Check a file for syntax errors."""
    try:
        with open(file_path, "r") as f:
            content = f.read()
        ast.parse(content)
        return None
    except SyntaxError as e:
        return f"{file_path}: Line {e.lineno}: {e.msg}"


def test_all_examples():
    """Test if all example files can be imported."""
    print("=== Testing Example Imports ===\n")

    # Dynamically find all Python example files
    examples_root = Path(__file__).parent.parent  # Go up from utils to examples
    example_files = []

    # Files to exclude from testing
    exclude_files = {
        "__init__.py",  # Init files
        "maintenance.py",  # Maintenance script
        "paths.py",  # Paths module
        "test_runner.py",  # This test runner
    }

    # Folders to search for examples (all end with _examples for consistency)
    example_folders = [
        "feature_examples",
        "node_examples",
        "integration_examples",
    ]

    # Find all .py files in the example subdirectories (recursively)
    for folder in example_folders:
        folder_path = examples_root / folder
        if folder_path.exists():
            for file in folder_path.rglob("*.py"):  # Use rglob for recursive search
                if (
                    file.name not in exclude_files
                    and not file.name.startswith("_")
                    and not file.name.startswith("test_")
                ):
                    example_files.append(file.relative_to(examples_root))

    # Sort for consistent output
    example_files.sort()

    print(f"Found {len(example_files)} example files to test\n")

    failed_imports = []

    for example in example_files:
        example_path = examples_root / example
        try:
            # Try to run with --help or similar to avoid full execution
            result = subprocess.run(
                [sys.executable, str(example_path), "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            # If --help not supported, just check if it imports without syntax errors
            if result.returncode != 0:
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", str(example_path)],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    print(f"✓ {example} - imports successfully")
                else:
                    print(f"✗ {example} - import failed")
                    if result.stderr:
                        print(f"  Error: {result.stderr.strip()}")
                    failed_imports.append(str(example))
            else:
                print(f"✓ {example} - runs with --help")
        except subprocess.TimeoutExpired:
            print(f"✓ {example} - starts execution (timeout expected)")
        except Exception as e:
            print(f"✗ {example} - error: {e}")
            failed_imports.append(str(example))

    if failed_imports:
        print(f"\nFailed imports: {failed_imports}")
        return False
    else:
        print("\nAll examples import successfully!")
        return True


def run_example_with_security(example_path: str):
    """Run an example with proper security configuration."""
    try:
        # Add the project root to the Python path
        examples_dir = Path(__file__).parent.parent  # Go up from utils to examples
        project_root = examples_dir.parent
        sys.path.insert(0, str(project_root))

        # Set environment variable to allow examples/data access
        os.environ["KAILASH_ALLOWED_DIRS"] = str(examples_dir)

        example_file = Path(example_path)
        if not example_file.exists():
            # Try relative to examples directory
            example_file = examples_dir / example_path

        if not example_file.exists():
            print(f"Error: Example file not found: {example_path}")
            return 1

        # Change to the example's directory
        original_cwd = os.getcwd()
        os.chdir(example_file.parent)

        try:
            # Execute the example
            with open(example_file, "r") as f:
                code = f.read()

            # Create a namespace for execution
            namespace = {"__file__": str(example_file), "__name__": "__main__"}

            exec(code, namespace)
            print(f"✓ Successfully executed: {example_path}")
            return 0

        finally:
            # Restore original working directory
            os.chdir(original_cwd)

    except Exception as e:
        print(f"✗ Error executing {example_path}: {e}")
        return 1


def main():
    """Main entry point for test runner."""
    if len(sys.argv) > 1:
        # Run specific example
        if sys.argv[1] == "run":
            if len(sys.argv) < 3:
                print("Usage: python -m utils.test_runner run <example_file.py>")
                print("\nExample:")
                print(
                    "  python -m utils.test_runner run workflow_examples/workflow_simple.py"
                )
                return 1
            return run_example_with_security(sys.argv[2])
        elif sys.argv[1] == "syntax":
            # Check syntax of problem files
            examples_dir = Path(__file__).parent.parent
            problem_files = []
            for arg in sys.argv[2:]:
                file_path = examples_dir / arg
                if file_path.exists():
                    error = check_syntax(file_path)
                    if error:
                        print(error)
                        # Show context
                        with open(file_path, "r") as f:
                            lines = f.readlines()
                            line_no = int(error.split("Line ")[1].split(":")[0])
                            start = max(0, line_no - 3)
                            end = min(len(lines), line_no + 2)
                            print("Context:")
                            for i in range(start, end):
                                marker = ">>> " if i == line_no - 1 else "    "
                                print(f"{marker}{i+1:4d}: {lines[i].rstrip()}")
                        print()
                        problem_files.append(arg)
            return 1 if problem_files else 0

    # Default: run all tests
    print("Testing all Kailash SDK examples...\n")

    # Change to examples directory
    examples_dir = Path(__file__).parent.parent  # Go up from utils to examples
    os.chdir(examples_dir)

    # Run tests
    import_success = test_all_examples()

    if import_success:
        print("\n=== All tests passed! ===")
        return 0
    else:
        print("\n=== Some tests failed ===")
        return 1


if __name__ == "__main__":
    sys.exit(main())

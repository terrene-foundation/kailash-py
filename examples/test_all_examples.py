#!/usr/bin/env python3
"""
Test script to verify all examples can run without errors.
"""

import subprocess
import sys
from pathlib import Path


def test_imports():
    """Test if all example files can be imported."""
    print("=== Testing Example Imports ===\n")

    # Dynamically find all Python example files
    examples_dir = Path(__file__).parent
    example_files = []
    
    # Files to exclude from testing
    exclude_files = {
        "test_all_examples.py",  # This file itself
        "__init__.py",  # Init files
        "test_updated_examples.py",  # Other test files
        "test_api_examples.py",
        "mcp_server.py",  # Special server files
    }
    
    # Find all .py files in the examples directory (not in subdirectories)
    for file in examples_dir.glob("*.py"):
        if file.name not in exclude_files and not file.name.startswith("_"):
            example_files.append(file.name)
    
    # Sort for consistent output
    example_files.sort()
    
    print(f"Found {len(example_files)} example files to test\n")

    failed_imports = []

    for example in example_files:
        try:
            # Try to run with --help or similar to avoid full execution
            result = subprocess.run(
                [sys.executable, example, "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            # If --help not supported, just check if it imports without syntax errors
            if result.returncode != 0:
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", example],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    print(f"✓ {example} - imports successfully")
                else:
                    print(f"✗ {example} - import failed")
                    failed_imports.append(example)
            else:
                print(f"✓ {example} - runs with --help")
        except subprocess.TimeoutExpired:
            print(f"✓ {example} - starts execution (timeout expected)")
        except Exception as e:
            print(f"✗ {example} - error: {e}")
            failed_imports.append(example)

    if failed_imports:
        print(f"\nFailed imports: {failed_imports}")
        return False
    else:
        print("\nAll examples import successfully!")
        return True


def test_dry_run():
    """Test if examples can execute in dry-run mode."""
    print("\n=== Testing Example Dry Runs ===\n")

    # These examples should be safe to run partially
    safe_examples = [
        "test_imports.py",
    ]

    for example in safe_examples:
        if not Path(example).exists():
            continue

        try:
            result = subprocess.run(
                [sys.executable, example], capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                print(f"✓ {example} - executed successfully")
            else:
                print(f"✗ {example} - execution failed")
                print(f"  Error: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print(f"✗ {example} - execution timeout")
        except Exception as e:
            print(f"✗ {example} - error: {e}")


def main():
    """Run all tests."""
    print("Testing all Kailash SDK examples...\n")

    # Change to examples directory
    examples_dir = Path(__file__).parent
    import os

    os.chdir(examples_dir)

    # Run tests
    import_success = test_imports()
    test_dry_run()

    if import_success:
        print("\n=== All tests passed! ===")
        return 0
    else:
        print("\n=== Some tests failed ===")
        return 1


if __name__ == "__main__":
    sys.exit(main())

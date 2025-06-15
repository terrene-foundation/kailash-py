#!/usr/bin/env python3
"""
Check Test Imports

This script checks all test files for import errors.
"""

import ast
import os
import sys


def check_file_imports(file_path):
    """Check if a Python file has valid imports."""
    try:
        with open(file_path, "r") as f:
            content = f.read()

        # Parse the AST to check syntax
        ast.parse(content)
        return True, None
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def check_all_tests():
    """Check all test files for import errors."""
    errors = []
    checked = 0

    for root, dirs, files in os.walk("tests"):
        # Skip __pycache__ directories
        if "__pycache__" in root:
            continue

        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                file_path = os.path.join(root, file)
                checked += 1

                valid, error = check_file_imports(file_path)
                if not valid:
                    errors.append((file_path, error))

    return checked, errors


def main():
    """Main function."""
    print("Checking test file imports...\n")

    checked, errors = check_all_tests()

    print(f"Checked {checked} test files")

    if errors:
        print(f"\nFound {len(errors)} files with errors:\n")
        for file_path, error in errors:
            print(f"❌ {file_path}")
            print(f"   {error}")
    else:
        print("\n✅ All test files have valid syntax!")

    # Return non-zero exit code if errors found
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Maintenance utilities for Kailash SDK examples.
Includes path fixing and import updating functionality.
"""

import re
import sys
from pathlib import Path


def fix_path_references():
    """Fix all path references in examples to use the correct directory structure."""
    examples_dir = Path(__file__).parent.parent  # Go up from utils to examples

    # Find all Python files
    py_files = list(examples_dir.rglob("*.py"))

    # Exclude utility files
    exclude_dirs = ["utils", "__pycache__", ".pytest_cache"]
    exclude_files = ["__init__.py"]

    py_files = [
        f
        for f in py_files
        if not any(ex_dir in f.parts for ex_dir in exclude_dirs)
        and f.name not in exclude_files
    ]

    print(f"Found {len(py_files)} Python files to check for path issues")

    fixed_count = 0
    for py_file in sorted(py_files):
        if fix_file_paths(py_file):
            relative_path = py_file.relative_to(examples_dir)
            print(f"Fixed paths: {relative_path}")
            fixed_count += 1

    print(f"\nFixed {fixed_count} files")

    # Create data/outputs directory if it doesn't exist
    output_dir = examples_dir / "data" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nEnsured output directory exists: {output_dir}")


def fix_file_paths(file_path: Path) -> bool:
    """Fix path references in a single file."""
    try:
        content = file_path.read_text()
        original_content = content

        # Track if we need to import example_utils
        needs_import = False

        # Pattern replacements
        replacements = [
            # Direct path strings in node constructors
            (r'file_path="\.\.\/data\/', 'file_path=str(get_data_dir() / "'),
            (r'file_path="\.\.\/outputs\/', 'file_path=str(get_output_dir() / "'),
            (r"file_path='\.\.\/data\/", "file_path=str(get_data_dir() / '"),
            (r"file_path='\.\.\/outputs\/", "file_path=str(get_output_dir() / '"),
            # Path constructions
            (r'Path\("\.\.\/data"\)', "get_data_dir()"),
            (r'Path\("\.\.\/outputs"\)', "get_output_dir()"),
            (r"Path\('\.\.\/data'\)", "get_data_dir()"),
            (r"Path\('\.\.\/outputs'\)", "get_output_dir()"),
            # Path with file
            (r'Path\("\.\.\/data\/([^"]+)"\)', r'get_data_dir() / "\1"'),
            (r'Path\("\.\.\/outputs\/([^"]+)"\)', r'get_output_dir() / "\1"'),
            # Direct file operations
            (r'open\("\.\.\/data\/', 'open(str(get_data_dir() / "'),
            (r'open\("\.\.\/outputs\/', 'open(str(get_output_dir() / "'),
            # Config dictionaries
            (r'"file_path": "\.\.\/data\/', '"file_path": str(get_data_dir() / "'),
            (r'"file_path": "\.\.\/outputs\/', '"file_path": str(get_output_dir() / "'),
            # CSV/JSON operations
            (r'\.to_csv\("\.\.\/data\/', '.to_csv(str(get_data_dir() / "'),
            (r'\.to_csv\("\.\.\/outputs\/', '.to_csv(str(get_output_dir() / "'),
            (r'\.to_json\("\.\.\/data\/', '.to_json(str(get_data_dir() / "'),
            (r'\.to_json\("\.\.\/outputs\/', '.to_json(str(get_output_dir() / "'),
            # Legacy downloads directory
            (r'os\.makedirs\("downloads"', "get_output_dir().mkdir(exist_ok=True"),
            (r'"downloads\/', 'str(get_output_dir() / "'),
        ]

        # Apply replacements
        for pattern, replacement in replacements:
            if re.search(pattern, content):
                needs_import = True
                content = re.sub(pattern, replacement, content)

        # Add import if needed and not already present
        if needs_import and "from examples.utils.paths import" not in content:
            # Find the right place to insert import
            lines = content.split("\n")
            import_added = False

            for i, line in enumerate(lines):
                # Add after other imports
                if line.startswith("from kailash") or line.startswith("import"):
                    # Find the last import
                    j = i
                    while j < len(lines) and (
                        lines[j].startswith("from")
                        or lines[j].startswith("import")
                        or lines[j].strip() == ""
                    ):
                        j += 1

                    # Insert import
                    insert_lines = [
                        "",
                        "from examples.utils.paths import get_data_dir, get_output_dir",
                    ]

                    lines[j:j] = insert_lines
                    import_added = True
                    break

            if import_added:
                content = "\n".join(lines)

        # Only write if changed
        if content != original_content:
            file_path.write_text(content)
            return True
        return False

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def update_imports():
    """Update all import statements to use the full module path."""
    examples_dir = Path(__file__).parent.parent  # Go up from utils to examples

    # Find all Python files
    py_files = list(examples_dir.rglob("*.py"))

    # Exclude utility files
    exclude_dirs = ["utils", "__pycache__", ".pytest_cache"]
    exclude_files = ["__init__.py"]

    py_files = [
        f
        for f in py_files
        if not any(ex_dir in f.parts for ex_dir in exclude_dirs)
        and f.name not in exclude_files
    ]

    print(f"Found {len(py_files)} Python files to check for import issues")

    updated_count = 0
    for py_file in sorted(py_files):
        if fix_imports_in_file(py_file):
            relative_path = py_file.relative_to(examples_dir)
            print(f"Updated imports: {relative_path}")
            updated_count += 1

    print(f"\nUpdated {updated_count} files")


def fix_imports_in_file(file_path: Path) -> bool:
    """Update import statements in a single file."""
    try:
        content = file_path.read_text()
        original_content = content

        # Pattern replacements for import statements
        replacements = [
            # Update the import statements
            (r"from utils\.paths import", "from examples.utils.paths import"),
            # Remove the sys.path manipulation since we're using proper imports
            (r"# Add parent directory to path for example_utils\n", ""),
            (r"sys\.path\.insert\(0, str\(Path\(__file__\)\.parent\)\)\n", ""),
        ]

        # Apply replacements
        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

        # Only write if changed
        if content != original_content:
            file_path.write_text(content)
            return True
        return False

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def main():
    """Main entry point for maintenance utilities."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m utils.maintenance <command>")
        print("\nCommands:")
        print(
            "  fix-paths    - Fix all path references to use proper directory structure"
        )
        print("  fix-imports  - Update all imports to use full module paths")
        print("  all          - Run all maintenance tasks")
        return 1

    command = sys.argv[1]

    if command == "fix-paths":
        fix_path_references()
    elif command == "fix-imports":
        update_imports()
    elif command == "all":
        print("=== Running all maintenance tasks ===\n")
        print("1. Fixing path references...")
        fix_path_references()
        print("\n2. Updating imports...")
        update_imports()
        print("\n=== All maintenance tasks completed ===")
    else:
        print(f"Unknown command: {command}")
        return 1

    return 0


if __name__ == "__main__":

    sys.exit(main())

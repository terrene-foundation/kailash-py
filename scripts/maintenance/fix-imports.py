#!/usr/bin/env python3
"""
Fix common import errors and code issues in example files.

This script consolidates functionality from fix-common-imports.py and fix-examples.py
to provide comprehensive fixing of common issues found in SDK examples.
"""

import argparse
import os
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Get project root
project_root = Path(__file__).parent.parent.parent

# Comprehensive list of fixes combining both original scripts
IMPORT_FIXES = [
    # AI nodes - MonitoredLLMAgentNode doesn't exist
    (
        "from kailash.nodes.ai import MonitoredLLMAgentNode",
        "from kailash.nodes.ai import LLMAgentNode",
    ),
    (
        r"from kailash\.nodes\.ai import (.*)MonitoredLLMAgentNode(.*)",
        r"from kailash.nodes.ai import \1LLMAgentNode\2",
    ),
    (
        r"from kailash\.nodes\.ai\.monitored_llm import MonitoredLLMAgentNode",
        r"from kailash.nodes.ai import LLMAgentNode",
    ),
    ("MonitoredLLMAgentNode(", "LLMAgentNode(enable_monitoring=True,"),
    (r"MonitoredLLMAgentNode\(", r"LLMAgentNode(enable_monitoring=True, "),
    # Runtime fixes - LocalWorkflowRunner should be LocalRuntime
    (
        "from kailash.runtime import LocalWorkflowRunner",
        "from kailash.runtime import LocalRuntime",
    ),
    (
        r"from kailash\.runtime\.local import LocalWorkflowRunner",
        r"from kailash.runtime.local import LocalRuntime",
    ),
    ("LocalWorkflowRunner(", "LocalRuntime("),
    (r"LocalWorkflowRunner\(\)", r"LocalRuntime()"),
    ("runner.run()", "runner.execute()"),
    (".run(workflow", ".execute(workflow"),
    # Visualization - these nodes don't exist yet
    ("from kailash.visualization", "# from kailash.visualization"),
    ("VisualizationDashboard", "# VisualizationDashboard"),
    # Node renames
    (
        "from kailash.nodes.auth import EnhancedAccessControlManager",
        "from kailash.nodes.auth import AccessControlManager",
    ),
    ("EnhancedAccessControlManager(", "AccessControlManager("),
    # Data paths fixes
    (
        r"from kailash\.utils\.data_paths import",
        r"from examples.utils.data_paths import",
    ),
    # Remove route parameter from connect (deprecated)
    (
        r"\.connect\([^,]+,\s*[^,]+,\s*route=[^)]+\)",
        lambda m: m.group(0).split(",route=")[0] + ")",
    ),
    # Secure logger formatting
    (r'logger\.info\("([^"]+)",\s*([^)]+)\)', r'logger.info(f"\1: {\2}")'),
    (r'logger\.error\("([^"]+)",\s*([^)]+)\)', r'logger.error(f"\1: {\2}")'),
    (r'logger\.warning\("([^"]+)",\s*([^)]+)\)', r'logger.warning(f"\1: {\2}")'),
]

# Files to skip
SKIP_FILES = {
    "test_results.json",
    "__pycache__",
    ".pyc",
    ".git",
}


def should_skip_file(path: Path) -> bool:
    """Check if file should be skipped."""
    return any(skip in str(path) for skip in SKIP_FILES)


def fix_file(file_path: Path, verbose: bool = False) -> Tuple[bool, List[str]]:
    """Fix common issues in a single file."""
    if should_skip_file(file_path):
        return False, []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return False, [f"Error reading: {e}"]

    original_content = content
    changes = []

    # Apply all fixes
    for fix in IMPORT_FIXES:
        if isinstance(fix, tuple) and len(fix) == 2:
            old, new = fix
            if callable(new):
                # Handle regex replacements with callbacks
                pattern = old
                matches = re.findall(pattern, content)
                if matches:
                    content = re.sub(pattern, new, content)
                    changes.append(f"Fixed regex pattern: {pattern}")
            elif old.startswith("r'") or "\\" in old:
                # Handle regex patterns
                pattern = old.strip("r'").strip("'") if old.startswith("r'") else old
                if re.search(pattern, content):
                    content = re.sub(pattern, new, content)
                    changes.append(f"Fixed regex: {pattern} → {new}")
            else:
                # Handle simple string replacements
                if old in content:
                    content = content.replace(old, new)
                    changes.append(f"Replaced: {old} → {new}")

    # Fix duplicate imports
    content, import_changes = fix_duplicate_imports(content)
    changes.extend(import_changes)

    # Save if changed
    if content != original_content:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True, changes
        except Exception as e:
            return False, [f"Error writing: {e}"]

    return False, []


def fix_duplicate_imports(content: str) -> Tuple[str, List[str]]:
    """Fix duplicate imports in content."""
    lines = content.split("\n")
    seen_imports: Set[str] = set()
    fixed_lines = []
    changes = []

    for line in lines:
        if line.strip().startswith("from ") or line.strip().startswith("import "):
            # Check for duplicate imports on same line
            if ", " in line and line.count("import") == 1:
                parts = line.split("import")[1].strip()
                imports = [imp.strip() for imp in parts.split(",")]
                unique_imports = list(
                    dict.fromkeys(imports)
                )  # Remove duplicates preserving order
                if len(imports) != len(unique_imports):
                    line = (
                        line.split("import")[0] + "import " + ", ".join(unique_imports)
                    )
                    changes.append(f"Fixed duplicate imports in line: {line}")

            # Check for completely duplicate import lines
            import_key = line.strip()
            if import_key not in seen_imports:
                seen_imports.add(import_key)
                fixed_lines.append(line)
            else:
                changes.append(f"Removed duplicate import: {line.strip()}")
        else:
            fixed_lines.append(line)

    return "\n".join(fixed_lines), changes


def main():
    """Main execution."""
    parser = argparse.ArgumentParser(
        description="Fix common import errors and code issues in example files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fix all Python files in examples directory
  python scripts/maintenance/fix-imports.py

  # Fix specific file
  python scripts/maintenance/fix-imports.py --file examples/some_example.py

  # Verbose output showing all changes
  python scripts/maintenance/fix-imports.py --verbose

  # Dry run to see what would be changed
  python scripts/maintenance/fix-imports.py --dry-run
        """,
    )

    parser.add_argument(
        "--file", "-f", type=Path, help="Fix specific file instead of all examples"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output of all changes",
    )
    parser.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="Show what would be changed without making changes",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=project_root / "examples",
        help="Directory to search for Python files (default: examples/)",
    )

    args = parser.parse_args()

    print("🔧 Fixing Common Import Errors and Code Issues")
    print("=" * 60)

    # Determine files to process
    if args.file:
        if not args.file.exists():
            print(f"❌ File not found: {args.file}")
            return 1
        python_files = [args.file]
    else:
        python_files = list(args.directory.rglob("*.py"))
        python_files = [f for f in python_files if not should_skip_file(f)]

    print(f"Found {len(python_files)} Python files to process")

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")

    print()

    fixed_count = 0
    error_count = 0
    total_changes = 0

    for file_path in python_files:
        if args.dry_run:
            # For dry run, read and process but don't write
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                original_content = content

                # Simulate all fixes
                for fix in IMPORT_FIXES:
                    if isinstance(fix, tuple) and len(fix) == 2:
                        old, new = fix
                        if not callable(new) and old in content:
                            content = content.replace(old, new)

                if content != original_content:
                    print(f"📝 Would fix: {file_path.relative_to(project_root)}")
                    fixed_count += 1
            except Exception as e:
                print(
                    f"❌ Error processing: {file_path.relative_to(project_root)} - {e}"
                )
                error_count += 1
        else:
            # Normal processing
            fixed, changes = fix_file(file_path, args.verbose)

            if fixed:
                fixed_count += 1
                total_changes += len(changes)
                print(f"✅ Fixed: {file_path.relative_to(project_root)}")
                if args.verbose:
                    for change in changes:
                        print(f"   - {change}")
                else:
                    # Show first few changes
                    for change in changes[:3]:
                        print(f"   - {change}")
                    if len(changes) > 3:
                        print(f"   ... and {len(changes) - 3} more changes")
            elif changes:  # Has errors
                error_count += 1
                print(f"❌ Error: {file_path.relative_to(project_root)}")
                print(f"   - {changes[0]}")

    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    if args.dry_run:
        print(f"  📝 Would fix: {fixed_count} files")
        print(f"  ❌ Errors: {error_count} files")
        print(
            f"  ⏭️  No changes needed: {len(python_files) - fixed_count - error_count} files"
        )
    else:
        print(f"  ✅ Fixed: {fixed_count} files")
        print(f"  🔧 Total changes: {total_changes}")
        print(f"  ❌ Errors: {error_count} files")
        print(
            f"  ⏭️  No changes needed: {len(python_files) - fixed_count - error_count} files"
        )

    if fixed_count > 0 and not args.dry_run:
        print("\n💡 Re-run the test suite to see improvements!")
        print("   python -m pytest tests/")

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    exit(main())

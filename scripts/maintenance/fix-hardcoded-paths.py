#!/usr/bin/env python3
"""
Script to find and report remaining hardcoded output paths in the codebase.
"""

import os
import re
from pathlib import Path


def find_hardcoded_outputs(project_root):
    """Find Python files with hardcoded output paths."""

    patterns = [
        r'"outputs/',  # "outputs/...
        r"'outputs/",  # 'outputs/...
        r'Path\("outputs',  # Path("outputs...
        r"Path\('outputs",  # Path('outputs...
        r"\.mkdir.*outputs",  # .mkdir(...outputs...)
        r"makedirs.*outputs",  # makedirs(...outputs...)
        r'"cycle_analysis_output',
        r"'cycle_analysis_output",
    ]

    issues = []

    for root, dirs, files in os.walk(project_root):
        # Skip certain directories
        if any(
            skip in root
            for skip in [
                ".git",
                "__pycache__",
                ".pytest_cache",
                "node_modules",
                "data/outputs",
            ]
        ):
            continue

        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file

                try:
                    with open(file_path, encoding="utf-8") as f:
                        content = f.read()

                    for line_num, line in enumerate(content.splitlines(), 1):
                        for pattern in patterns:
                            if re.search(pattern, line):
                                # Skip if it's already using data_paths
                                if "get_output_data_path" in line:
                                    continue
                                # Skip comments and docstrings
                                if line.strip().startswith(
                                    "#"
                                ) or line.strip().startswith('"""'):
                                    continue

                                issues.append(
                                    {
                                        "file": str(
                                            file_path.relative_to(project_root)
                                        ),
                                        "line": line_num,
                                        "content": line.strip(),
                                        "pattern": pattern,
                                    }
                                )

                except Exception as e:
                    print(f"Error reading {file_path}: {e}")

    return issues


def main():
    """Find and report hardcoded output paths."""

    project_root = Path(__file__).parent.parent

    print("🔍 Searching for hardcoded output paths...")
    print("=" * 80)

    issues = find_hardcoded_outputs(project_root)

    if issues:
        print(f"\n⚠️  Found {len(issues)} hardcoded output paths:\n")

        # Group by file
        by_file = {}
        for issue in issues:
            if issue["file"] not in by_file:
                by_file[issue["file"]] = []
            by_file[issue["file"]].append(issue)

        for file_path, file_issues in sorted(by_file.items()):
            print(f"\n📄 {file_path}:")
            for issue in file_issues:
                print(f"   Line {issue['line']:4d}: {issue['content'][:80]}")

        print("\n" + "=" * 80)
        print("💡 To fix these issues:")
        print("1. Add: from examples.utils.data_paths import get_output_data_path")
        print(
            "2. Replace hardcoded paths with: get_output_data_path('subdir/filename')"
        )
        print("3. Use ensure_output_dir_exists() instead of os.makedirs('outputs')")
    else:
        print("\n✅ No hardcoded output paths found!")

    print("\nDone!")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Ensure All Files in tests/ are Proper Pytest Tests

This script identifies and fixes files in tests/ directory that are not proper pytest tests:
1. Example/demo files that should be in examples/
2. Utility scripts that should be in scripts/
3. Non-test Python files
4. Files without proper pytest structure

Generates move/fix actions to ensure tests/ contains only proper pytest tests.
"""

import ast
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


def analyze_python_file(file_path: Path) -> Dict[str, Any]:
    """Analyze a Python file to determine if it's a proper pytest test."""
    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        analysis = {
            "file": str(file_path.relative_to(Path("tests"))),
            "full_path": str(file_path),
            "is_proper_pytest": False,
            "is_example": False,
            "is_utility": False,
            "is_config": False,
            "should_move": False,
            "move_destination": None,
            "issues": [],
            "pytest_elements": {
                "test_functions": [],
                "test_classes": [],
                "fixtures": [],
                "imports_pytest": False,
                "has_main_block": False,
            },
            "size_lines": len(lines),
        }

        # Parse AST to analyze structure
        try:
            tree = ast.parse(content)

            # Look for pytest elements
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.name.startswith("test_"):
                        analysis["pytest_elements"]["test_functions"].append(node.name)
                    elif any(
                        decorator.id == "pytest.fixture"
                        for decorator in node.decorator_list
                        if isinstance(decorator, ast.Name)
                    ):
                        analysis["pytest_elements"]["fixtures"].append(node.name)

                elif isinstance(node, ast.ClassDef):
                    if node.name.startswith("Test"):
                        analysis["pytest_elements"]["test_classes"].append(node.name)

                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "pytest":
                            analysis["pytest_elements"]["imports_pytest"] = True

                elif isinstance(node, ast.ImportFrom):
                    if node.module == "pytest":
                        analysis["pytest_elements"]["imports_pytest"] = True

        except SyntaxError:
            analysis["issues"].append("Invalid Python syntax")

        # Check for main execution block
        if 'if __name__ == "__main__":' in content:
            analysis["pytest_elements"]["has_main_block"] = True

        # Classify file type
        file_name = file_path.name

        # Configuration files (legitimate in tests/)
        if (
            file_name in ["conftest.py", "test_config.py", "test_helpers.py"]
            or file_name == "__init__.py"
        ):
            analysis["is_config"] = True
            analysis["is_proper_pytest"] = True

        # Check for example/demo patterns
        elif any(
            keyword in content.lower()
            for keyword in [
                "example demonstrating",
                "demo",
                "demonstration",
                "this example shows",
                "tutorial",
                "walkthrough",
                "sample usage",
            ]
        ):
            analysis["is_example"] = True
            analysis["should_move"] = True
            analysis["move_destination"] = "examples/feature_examples/"

        # Check for utility script patterns
        elif (
            analysis["pytest_elements"]["has_main_block"]
            and not analysis["pytest_elements"]["test_functions"]
            and any(
                keyword in content.lower()
                for keyword in ["runner", "script", "executor", "launcher"]
            )
        ):
            analysis["is_utility"] = True
            analysis["should_move"] = True
            analysis["move_destination"] = "scripts/testing/"

        # Check if it's a proper pytest test
        elif (
            analysis["pytest_elements"]["test_functions"]
            or analysis["pytest_elements"]["test_classes"]
            or analysis["pytest_elements"]["fixtures"]
        ):
            analysis["is_proper_pytest"] = True

            # Check for pytest best practices
            if not analysis["pytest_elements"]["imports_pytest"]:
                analysis["issues"].append("Missing pytest import")

            if analysis["pytest_elements"]["has_main_block"]:
                analysis["issues"].append(
                    "Has __main__ block (should use pytest discovery)"
                )

        # Files without any test structure
        else:
            if not analysis["is_config"]:
                analysis["issues"].append(
                    "No test functions, classes, or fixtures found"
                )
                analysis["should_move"] = True

                # Determine destination based on content
                if any(
                    keyword in content.lower()
                    for keyword in ["example", "demo", "sample"]
                ):
                    analysis["move_destination"] = "examples/feature_examples/"
                else:
                    analysis["move_destination"] = "scripts/testing/"

        return analysis

    except Exception as e:
        return {
            "file": str(file_path.relative_to(Path("tests"))),
            "full_path": str(file_path),
            "error": str(e),
            "is_proper_pytest": False,
        }


def find_all_python_files() -> List[Path]:
    """Find all Python files in tests directory."""
    tests_dir = Path("tests")
    python_files = []

    for file_path in tests_dir.rglob("*.py"):
        # Skip cache directories
        if "cpython" in str(file_path) or "__pycache__" in str(file_path):
            continue
        python_files.append(file_path)

    return sorted(python_files)


def categorize_files(analyses: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Categorize files by their type and compliance status."""
    categories = {
        "proper_pytest": [],
        "config_files": [],
        "examples_to_move": [],
        "utilities_to_move": [],
        "non_compliant": [],
        "errors": [],
    }

    for analysis in analyses:
        if "error" in analysis:
            categories["errors"].append(analysis)
        elif analysis.get("is_config"):
            categories["config_files"].append(analysis)
        elif analysis.get("is_proper_pytest"):
            categories["proper_pytest"].append(analysis)
        elif analysis.get("is_example"):
            categories["examples_to_move"].append(analysis)
        elif analysis.get("is_utility"):
            categories["utilities_to_move"].append(analysis)
        else:
            categories["non_compliant"].append(analysis)

    return categories


def generate_move_script(categories: Dict[str, List[Dict[str, Any]]]) -> str:
    """Generate bash script to move non-compliant files."""
    script_lines = [
        "#!/bin/bash",
        "# Pytest Compliance Cleanup Script",
        "# Moves non-test files from tests/ to appropriate directories",
        "",
        "set -e",
        "",
        "echo '🧹 Moving non-pytest files from tests/ directory...'",
        "",
    ]

    # Create destination directories
    destinations = set()
    for category in ["examples_to_move", "utilities_to_move"]:
        for file_info in categories[category]:
            if file_info.get("move_destination"):
                destinations.add(file_info["move_destination"])

    if destinations:
        script_lines.append("# Create destination directories")
        for dest in sorted(destinations):
            script_lines.append(f"mkdir -p {dest}")
        script_lines.append("")

    # Move example files
    if categories["examples_to_move"]:
        script_lines.append("# Move example files to examples/")
        for file_info in categories["examples_to_move"]:
            src = file_info["full_path"]
            dest_dir = file_info.get("move_destination", "examples/feature_examples/")

            # Determine subdirectory based on file location
            rel_path = file_info["file"]
            if "middleware" in rel_path:
                dest_dir += "middleware/"
            elif "workflows" in rel_path:
                dest_dir += "workflows/"
            elif "nodes" in rel_path:
                dest_dir += "nodes/"
            elif "integrations" in rel_path:
                dest_dir += "integrations/"
            else:
                dest_dir += "misc/"

            script_lines.append(f"mkdir -p {dest_dir}")
            filename = Path(src).name
            script_lines.append(
                f"mv '{src}' '{dest_dir}{filename}'  # Example/demo file"
            )

    # Move utility files
    if categories["utilities_to_move"]:
        script_lines.append("")
        script_lines.append("# Move utility files to scripts/")
        for file_info in categories["utilities_to_move"]:
            src = file_info["full_path"]
            dest_dir = file_info.get("move_destination", "scripts/testing/")
            filename = Path(src).name
            script_lines.append(f"mkdir -p {dest_dir}")
            script_lines.append(f"mv '{src}' '{dest_dir}{filename}'  # Utility script")

    # Remove non-compliant files
    if categories["non_compliant"]:
        script_lines.append("")
        script_lines.append("# Remove non-compliant files")
        for file_info in categories["non_compliant"]:
            src = file_info["full_path"]
            script_lines.append(f"rm -f '{src}'  # Non-pytest file")

    script_lines.extend(
        [
            "",
            f"echo '✅ Moved {len(categories['examples_to_move'])} example files'",
            f"echo '✅ Moved {len(categories['utilities_to_move'])} utility files'",
            f"echo '✅ Removed {len(categories['non_compliant'])} non-compliant files'",
            "echo '🧪 tests/ directory now contains only proper pytest tests'",
        ]
    )

    return "\n".join(script_lines)


def main():
    """Main pytest compliance analysis."""
    print("🧪 Pytest Compliance Analysis for tests/ Directory")
    print("=" * 60)

    # Find all Python files
    python_files = find_all_python_files()
    print(f"\n📊 Found {len(python_files)} Python files in tests/")

    # Analyze each file
    print("\n🔍 Analyzing files...")
    analyses = []
    for file_path in python_files:
        analysis = analyze_python_file(file_path)
        analyses.append(analysis)

    # Categorize results
    categories = categorize_files(analyses)

    # Print summary
    print("\n📋 Analysis Results:")
    print(f"  ✅ Proper pytest tests: {len(categories['proper_pytest'])}")
    print(f"  ⚙️  Configuration files: {len(categories['config_files'])}")
    print(f"  📚 Examples to move: {len(categories['examples_to_move'])}")
    print(f"  🔧 Utilities to move: {len(categories['utilities_to_move'])}")
    print(f"  ❌ Non-compliant files: {len(categories['non_compliant'])}")
    print(f"  🚨 Error files: {len(categories['errors'])}")

    # Show details for files that need moving
    if categories["examples_to_move"]:
        print(
            f"\n📚 EXAMPLE FILES TO MOVE ({len(categories['examples_to_move'])} files):"
        )
        for file_info in categories["examples_to_move"]:
            print(f"  📄 {file_info['file']} ({file_info['size_lines']} lines)")
            print(
                f"     → {file_info.get('move_destination', 'examples/feature_examples/')}"
            )

    if categories["utilities_to_move"]:
        print(
            f"\n🔧 UTILITY FILES TO MOVE ({len(categories['utilities_to_move'])} files):"
        )
        for file_info in categories["utilities_to_move"]:
            print(f"  📄 {file_info['file']} ({file_info['size_lines']} lines)")
            print(f"     → {file_info.get('move_destination', 'scripts/testing/')}")

    if categories["non_compliant"]:
        print(f"\n❌ NON-COMPLIANT FILES ({len(categories['non_compliant'])} files):")
        for file_info in categories["non_compliant"]:
            print(f"  📄 {file_info['file']} ({file_info['size_lines']} lines)")
            for issue in file_info.get("issues", []):
                print(f"     • {issue}")

    if categories["errors"]:
        print(f"\n🚨 FILES WITH ERRORS ({len(categories['errors'])} files):")
        for file_info in categories["errors"]:
            print(
                f"  📄 {file_info['file']} - {file_info.get('error', 'Unknown error')}"
            )

    # Show proper pytest tests with issues
    pytest_with_issues = [f for f in categories["proper_pytest"] if f.get("issues")]
    if pytest_with_issues:
        print(f"\n⚠️  PYTEST TESTS WITH ISSUES ({len(pytest_with_issues)} files):")
        for file_info in pytest_with_issues:
            print(f"  📄 {file_info['file']}")
            for issue in file_info["issues"]:
                print(f"     • {issue}")

    # Generate cleanup script
    files_to_move = (
        len(categories["examples_to_move"])
        + len(categories["utilities_to_move"])
        + len(categories["non_compliant"])
    )

    if files_to_move > 0:
        script_content = generate_move_script(categories)
        script_path = Path("scripts/testing/pytest_compliance_cleanup.sh")
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_content)
        script_path.chmod(0o755)

        print(f"\n🔧 Generated cleanup script: {script_path}")
        print(f"   Will move/remove {files_to_move} files")
        print("   Run with: ./scripts/testing/pytest_compliance_cleanup.sh")
    else:
        print("\n✅ All files in tests/ are properly structured pytest tests!")

    # Final statistics
    total_test_files = len(categories["proper_pytest"])
    total_support_files = len(categories["config_files"])

    print("\n📈 Final Status:")
    print(f"   🧪 Proper pytest tests: {total_test_files}")
    print(f"   ⚙️  Support files (conftest.py, etc.): {total_support_files}")
    print(
        f"   📁 Total legitimate test files: {total_test_files + total_support_files}"
    )

    return 0 if files_to_move == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

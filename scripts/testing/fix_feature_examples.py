#!/usr/bin/env python3
"""
Fix feature examples to follow current best practices.
Based on patterns discovered during migration.
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def find_deprecated_patterns(file_path: Path) -> List[Dict]:
    """Find deprecated patterns in a Python file."""
    issues = []

    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        for line_num, line in enumerate(lines, 1):
            # Check for LLMAgentNode.run() usage (should be execute())
            if re.search(r"llm.*\.run\(", line):
                issues.append(
                    {
                        "type": "incorrect_llm_run",
                        "line": line_num,
                        "content": line.strip(),
                        "description": "LLMAgentNode.run() should be .execute() - run() is internal method",
                    }
                )

            # Check for AsyncLocalRuntime imports
            if re.search(r"from.*AsyncLocalRuntime|import.*AsyncLocalRuntime", line):
                issues.append(
                    {
                        "type": "deprecated_async_runtime",
                        "line": line_num,
                        "content": line.strip(),
                        "description": "AsyncLocalRuntime is deprecated, use LocalRuntime(enable_async=True)",
                    }
                )

            # Check for core imports
            if "from kailash.core" in line:
                issues.append(
                    {
                        "type": "deprecated_core_import",
                        "line": line_num,
                        "content": line.strip(),
                        "description": "kailash.core imports are deprecated",
                    }
                )

            # Check for PythonCodeNode.from_function parameter order
            if re.search(r'PythonCodeNode\.from_function\(\s*["\']', line):
                issues.append(
                    {
                        "type": "pythoncode_param_order",
                        "line": line_num,
                        "content": line.strip(),
                        "description": "PythonCodeNode.from_function(func, name) - function first, name second",
                    }
                )

    except Exception as e:
        issues.append(
            {
                "type": "file_error",
                "line": 0,
                "content": str(e),
                "description": f"Error reading file: {e}",
            }
        )

    return issues


def analyze_examples_directory() -> Dict:
    """Analyze all Python files in feature_examples."""
    examples_dir = Path("examples/feature_examples")
    results = {
        "files_analyzed": 0,
        "files_with_issues": 0,
        "total_issues": 0,
        "issue_summary": {},
        "file_issues": {},
    }

    python_files = list(examples_dir.rglob("*.py"))

    for file_path in python_files:
        results["files_analyzed"] += 1
        issues = find_deprecated_patterns(file_path)

        if issues:
            results["files_with_issues"] += 1
            results["total_issues"] += len(issues)
            results["file_issues"][str(file_path)] = issues

            # Count issue types
            for issue in issues:
                issue_type = issue["type"]
                if issue_type not in results["issue_summary"]:
                    results["issue_summary"][issue_type] = 0
                results["issue_summary"][issue_type] += 1

    return results


def print_analysis_report(results: Dict):
    """Print detailed analysis report."""
    print("🔍 Feature Examples Analysis Report")
    print("=" * 50)
    print(f"Files analyzed: {results['files_analyzed']}")
    print(f"Files with issues: {results['files_with_issues']}")
    print(f"Total issues found: {results['total_issues']}")

    if results["issue_summary"]:
        print("\n📊 Issue Summary:")
        for issue_type, count in results["issue_summary"].items():
            print(f"  - {issue_type}: {count}")

    if results["file_issues"]:
        print("\n📄 Detailed Issues:")
        for file_path, issues in results["file_issues"].items():
            rel_path = Path(file_path).relative_to(Path("examples/feature_examples"))
            print(f"\n{rel_path}:")
            for issue in issues:
                print(f"  Line {issue['line']}: {issue['description']}")
                print(f"    {issue['content']}")


def fix_llm_execute_usage(file_path: Path) -> bool:
    """Fix LLMAgentNode.execute() usage to .run() with provider."""
    try:
        content = file_path.read_text(encoding="utf-8")
        modified = False

        # Pattern to find llm.execute() calls
        pattern = r"(\w+\.execute\()\s*\n?\s*(.*?)\)"

        def replace_execute(match):
            nonlocal modified
            var_name = match.group(1).replace(".execute(", "")
            params = match.group(2)

            # If it's an LLM execute call, convert to run
            if "prompt" in params or "message" in params:
                modified = True
                # Add provider parameter if missing
                if "provider=" not in params:
                    return f'{var_name}.run(\n        provider="ollama",  # Added required provider\n        model="llama3.2:3b",  # Added required model\n        {params})'
                else:
                    return f"{var_name}.run({params})"
            return match.group(0)

        new_content = re.sub(pattern, replace_execute, content, flags=re.DOTALL)

        if modified:
            file_path.write_text(new_content, encoding="utf-8")
            print(f"✅ Fixed LLM execute usage in {file_path}")
            return True

    except Exception as e:
        print(f"❌ Error fixing {file_path}: {e}")

    return False


def main():
    """Main function to analyze and optionally fix issues."""
    print("🚀 Starting Feature Examples Refactoring")

    # Analyze current state
    results = analyze_examples_directory()
    print_analysis_report(results)

    # Show what would be fixed
    if results["total_issues"] > 0:
        print("\n🔧 Issues Found - Ready for Manual Review")
        print("The most critical issues to fix:")

        critical_issues = [
            "incorrect_llm_run",
            "deprecated_async_runtime",
            "deprecated_core_import",
        ]
        for issue_type in critical_issues:
            if issue_type in results["issue_summary"]:
                count = results["issue_summary"][issue_type]
                print(f"  - {issue_type}: {count} instances")

        return 1  # Exit code indicating issues found
    else:
        print("\n🎉 All feature examples are up to date!")
        return 0


if __name__ == "__main__":
    sys.exit(main())

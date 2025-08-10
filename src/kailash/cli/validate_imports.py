#!/usr/bin/env python3
"""
Command-line tool for validating import paths for production deployment.

Usage:
    python -m kailash.cli.validate_imports [path] [options]

Examples:
    # Validate current directory
    python -m kailash.cli.validate_imports

    # Validate specific directory
    python -m kailash.cli.validate_imports src/myapp

    # Fix imports (dry run)
    python -m kailash.cli.validate_imports src/myapp --fix

    # Fix imports (apply changes)
    python -m kailash.cli.validate_imports src/myapp --fix --apply
"""

import argparse
import sys
from pathlib import Path
from typing import List

from kailash.runtime.validation import ImportIssue, ImportPathValidator


def main():
    """Main entry point for import validation CLI."""
    parser = argparse.ArgumentParser(
        description="Validate Python imports for production deployment compatibility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Validate current directory
  %(prog)s src/myapp          # Validate specific directory
  %(prog)s src/myapp --fix    # Show import fixes (dry run)
  %(prog)s --file module.py   # Validate single file

For more info, see: sdk-users/7-gold-standards/absolute-imports-gold-standard.md
        """,
    )

    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to validate (directory or file, default: current directory)",
    )

    parser.add_argument(
        "--file",
        "-f",
        action="store_true",
        help="Treat path as a single file instead of directory",
    )

    parser.add_argument(
        "--fix", action="store_true", help="Show suggested fixes for import issues"
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply fixes (use with --fix, CAUTION: modifies files!)",
    )

    parser.add_argument(
        "--no-recursive", "-n", action="store_true", help="Do not scan subdirectories"
    )

    parser.add_argument(
        "--include-tests", action="store_true", help="Include test files in validation"
    )

    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show errors, no informational output",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )

    args = parser.parse_args()

    # Create validator
    validator = ImportPathValidator()

    # Validate path
    path = Path(args.path)
    if not path.exists():
        print(f"Error: Path '{path}' does not exist", file=sys.stderr)
        sys.exit(1)

    # Collect issues
    issues: List[ImportIssue] = []

    if args.file or path.is_file():
        # Validate single file
        if args.verbose:
            print(f"Validating file: {path}")
        issues = validator.validate_file(str(path))
    else:
        # Validate directory
        if args.verbose:
            print(f"Validating directory: {path}")
            print(f"Recursive: {not args.no_recursive}")
            print(f"Include tests: {args.include_tests}")
            print()

        # TODO: Add support for include_tests flag in validator
        issues = validator.validate_directory(
            str(path), recursive=not args.no_recursive
        )

    # Handle results
    if args.json:
        import json

        # Convert issues to JSON-serializable format
        issues_data = [
            {
                "file": issue.file_path,
                "line": issue.line_number,
                "import": issue.import_statement,
                "type": issue.issue_type.value,
                "severity": issue.severity,
                "message": issue.message,
                "suggestion": issue.suggestion,
            }
            for issue in issues
        ]
        print(
            json.dumps(
                {
                    "issues": issues_data,
                    "total": len(issues),
                    "critical": len([i for i in issues if i.severity == "critical"]),
                    "warnings": len([i for i in issues if i.severity == "warning"]),
                },
                indent=2,
            )
        )

    elif args.fix:
        # Show fixes
        if not issues:
            if not args.quiet:
                print("✅ No import issues found!")
            sys.exit(0)

        print(f"Found {len(issues)} import issues\n")

        # Group by file
        files_with_issues = {}
        for issue in issues:
            if issue.file_path not in files_with_issues:
                files_with_issues[issue.file_path] = []
            files_with_issues[issue.file_path].append(issue)

        for file_path, file_issues in files_with_issues.items():
            print(f"\n📄 {file_path}")
            print("-" * 60)

            if args.apply:
                # Apply fixes
                fixes = validator.fix_imports_in_file(file_path, dry_run=False)
                for original, fixed in fixes:
                    print(f"  ❌ {original}")
                    print(f"  ✅ {fixed}")
                print(f"\n  Applied {len(fixes)} fixes to {file_path}")
            else:
                # Show proposed fixes
                for issue in file_issues:
                    print(f"  Line {issue.line_number}: {issue.import_statement}")
                    print(f"  Issue: {issue.message}")
                    print(f"  Fix: {issue.suggestion}")
                    print()

        if not args.apply:
            print("\n💡 To apply these fixes, run with --fix --apply")
            print("⚠️  CAUTION: This will modify your files!")

    else:
        # Standard report
        report = validator.generate_report(issues)
        print(report)

    # Exit code based on critical issues
    critical_count = len([i for i in issues if i.severity == "critical"])
    sys.exit(1 if critical_count > 0 else 0)


if __name__ == "__main__":
    main()

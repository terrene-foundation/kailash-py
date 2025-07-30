"""
Import path validator for production deployment compatibility.

This module detects relative imports that fail in production environments
and provides guidance for absolute import patterns.

Based on Gold Standard: sdk-users/7-gold-standards/absolute-imports-gold-standard.md
"""

import ast
import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class ImportIssueType(Enum):
    """Types of import issues that can be detected."""

    RELATIVE_IMPORT = "relative_import"
    IMPLICIT_RELATIVE = "implicit_relative"
    LOCAL_IMPORT = "local_import"
    AMBIGUOUS_IMPORT = "ambiguous_import"


@dataclass
class ImportIssue:
    """Represents an import issue found in a file."""

    file_path: str
    line_number: int
    import_statement: str
    issue_type: ImportIssueType
    severity: str  # "critical", "warning", "info"
    message: str
    suggestion: str
    gold_standard_ref: str = (
        "sdk-users/7-gold-standards/absolute-imports-gold-standard.md"
    )


class ImportPathValidator:
    """
    Validates import paths for production deployment compatibility.

    Detects relative imports that work in development but fail in production
    when applications run from repository root.
    """

    def __init__(self, repo_root: Optional[str] = None):
        """
        Initialize import path validator.

        Args:
            repo_root: Repository root path. If None, tries to auto-detect.
        """
        self.repo_root = Path(repo_root) if repo_root else self._find_repo_root()
        self.sdk_modules = self._identify_sdk_modules()
        self.issues: List[ImportIssue] = []

    def _find_repo_root(self) -> Path:
        """Find repository root by looking for key markers."""
        current = Path.cwd()

        # Look for common repo markers
        markers = [".git", "pyproject.toml", "setup.py", "requirements.txt"]

        while current != current.parent:
            for marker in markers:
                if (current / marker).exists():
                    return current
            current = current.parent

        # Fallback to current directory
        return Path.cwd()

    def _identify_sdk_modules(self) -> Set[str]:
        """Identify SDK module names for import validation."""
        sdk_modules = set()

        # Check for src structure
        src_path = self.repo_root / "src"
        if src_path.exists():
            for item in src_path.iterdir():
                if item.is_dir() and (item / "__init__.py").exists():
                    sdk_modules.add(item.name)

        # Common SDK module names
        sdk_modules.update(["kailash", "dataflow", "nexus"])

        return sdk_modules

    def validate_file(self, file_path: str) -> List[ImportIssue]:
        """
        Validate imports in a single Python file.

        Args:
            file_path: Path to Python file to validate

        Returns:
            List of import issues found
        """
        file_path = Path(file_path)
        if not file_path.exists() or not file_path.suffix == ".py":
            return []

        issues = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse AST to find imports
            tree = ast.parse(content, filename=str(file_path))

            # Check each import statement
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    issue = self._check_import_from(node, file_path, content)
                    if issue:
                        issues.append(issue)
                elif isinstance(node, ast.Import):
                    issue = self._check_import(node, file_path, content)
                    if issue:
                        issues.append(issue)

        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")

        return issues

    def _check_import_from(
        self, node: ast.ImportFrom, file_path: Path, content: str
    ) -> Optional[ImportIssue]:
        """Check 'from X import Y' statements."""
        if node.level > 0:
            # Explicit relative import (from . import x, from .. import x)
            import_str = self._get_import_string(node, content)

            return ImportIssue(
                file_path=str(file_path),
                line_number=node.lineno,
                import_statement=import_str,
                issue_type=ImportIssueType.RELATIVE_IMPORT,
                severity="critical",
                message="Relative import will fail in production deployment",
                suggestion=self._generate_absolute_import_suggestion(node, file_path),
            )

        elif node.module:
            # Check for implicit relative imports
            module_parts = node.module.split(".")
            first_part = module_parts[0]

            # Check if this looks like a local module import
            if self._is_likely_local_import(first_part, file_path):
                import_str = self._get_import_string(node, content)

                return ImportIssue(
                    file_path=str(file_path),
                    line_number=node.lineno,
                    import_statement=import_str,
                    issue_type=ImportIssueType.IMPLICIT_RELATIVE,
                    severity="critical",
                    message=f"Implicit relative import '{first_part}' will fail when run from repo root",
                    suggestion=self._generate_absolute_import_suggestion(
                        node, file_path
                    ),
                )

        return None

    def _check_import(
        self, node: ast.Import, file_path: Path, content: str
    ) -> Optional[ImportIssue]:
        """Check 'import X' statements."""
        # Generally less problematic, but check for ambiguous local imports
        for alias in node.names:
            name_parts = alias.name.split(".")
            first_part = name_parts[0]

            if self._is_likely_local_import(first_part, file_path):
                import_str = f"import {alias.name}"

                return ImportIssue(
                    file_path=str(file_path),
                    line_number=node.lineno,
                    import_statement=import_str,
                    issue_type=ImportIssueType.LOCAL_IMPORT,
                    severity="warning",
                    message=f"Local module import '{first_part}' may be ambiguous in production",
                    suggestion=f"Consider using absolute import: from {self._get_module_path(file_path)} import {first_part}",
                )

        return None

    def _is_likely_local_import(self, module_name: str, file_path: Path) -> bool:
        """
        Check if a module name is likely a local/relative import.

        Returns True if:
        - Module exists as sibling to current file
        - Module is not a known SDK module
        - Module is not a standard library module
        - Module is not a legitimate top-level package
        """
        # Skip if it's a known SDK module
        if module_name in self.sdk_modules:
            return False

        # Skip if it's likely a third-party or stdlib module
        if module_name in [
            "os",
            "sys",
            "json",
            "logging",
            "typing",
            "pathlib",
            "pytest",
            "unittest",
            "numpy",
            "pandas",
            "requests",
        ]:
            return False

        # Skip common top-level package names that are meant for absolute imports
        # These are legitimate when used as project structure roots
        top_level_packages = ["src", "lib", "app", "pkg"]
        if module_name in top_level_packages:
            return False

        # Check if module exists as sibling
        parent_dir = file_path.parent
        possible_module = parent_dir / module_name
        possible_file = parent_dir / f"{module_name}.py"

        if possible_module.exists() or possible_file.exists():
            return True

        # Check common local module patterns
        local_patterns = ["contracts", "nodes", "core", "utils", "models", "schemas"]
        if module_name in local_patterns:
            return True

        return False

    def _get_import_string(self, node: ast.ImportFrom, content: str) -> str:
        """Extract the actual import string from source."""
        lines = content.split("\n")
        if 0 <= node.lineno - 1 < len(lines):
            return lines[node.lineno - 1].strip()
        return f"from {node.module} import ..."

    def _get_module_path(self, file_path: Path) -> str:
        """Get the absolute module path for a file's directory."""
        try:
            # Get relative path from repo root
            rel_path = file_path.relative_to(self.repo_root)

            # Convert to module path (excluding the filename)
            parts = list(rel_path.parts[:-1])  # Remove filename

            # Join all parts to create module path
            return ".".join(parts) if parts else ""

        except ValueError:
            # File not under repo root
            return "src.your_module"

    def _generate_absolute_import_suggestion(
        self, node: ast.ImportFrom, file_path: Path
    ) -> str:
        """Generate suggested absolute import."""
        module_base = self._get_module_path(file_path)
        # Debug
        # print(f"DEBUG: file_path={file_path}, module_base={module_base}, node.level={node.level}, node.module={node.module}")

        if node.level > 0:
            # Handle relative imports
            module_parts = module_base.split(".") if module_base else []

            # For relative imports, we need to go up 'level' directories
            # But note: for a file in package a.b.c:
            # - level 1 (.) = current package (a.b.c)
            # - level 2 (..) = parent package (a.b)
            # - level 3 (...) = grandparent (a)
            # Since we want the parent, we go up (level-1) from current
            if len(module_parts) > node.level - 1:
                # Go to the appropriate parent level
                if node.level == 1:
                    # Same directory
                    parent_parts = module_parts
                else:
                    # Go up (level-1) directories
                    parent_parts = module_parts[: -(node.level - 1)]

                if node.module:
                    # Append the relative module path
                    suggested_module = ".".join(parent_parts + node.module.split("."))
                else:
                    # Just the parent module
                    suggested_module = ".".join(parent_parts)
            else:
                # Can't go up that many levels, use what we have
                if node.module:
                    suggested_module = node.module
                else:
                    suggested_module = module_base
        else:
            # Implicit relative - the module is in the current directory
            if module_base:
                suggested_module = f"{module_base}.{node.module}"
            else:
                suggested_module = node.module

        # Format the suggestion
        if hasattr(node, "names") and node.names:
            imports = ", ".join(alias.name for alias in node.names)
            return f"from {suggested_module} import {imports}"
        else:
            return f"from {suggested_module} import ..."

    def validate_directory(
        self, directory: str, recursive: bool = True
    ) -> List[ImportIssue]:
        """
        Validate all Python files in a directory.

        Args:
            directory: Directory path to validate
            recursive: Whether to scan subdirectories

        Returns:
            List of all import issues found
        """
        directory = Path(directory)
        if not directory.exists() or not directory.is_dir():
            return []

        all_issues = []

        pattern = "**/*.py" if recursive else "*.py"
        for py_file in directory.glob(pattern):
            # Skip test files by default (can be configured)
            if "test" in py_file.name or "__pycache__" in str(py_file):
                continue

            issues = self.validate_file(py_file)
            all_issues.extend(issues)

        return all_issues

    def generate_report(self, issues: List[ImportIssue]) -> str:
        """
        Generate a human-readable report of import issues.

        Args:
            issues: List of import issues to report

        Returns:
            Formatted report string
        """
        if not issues:
            return "✅ No import issues found! All imports are production-ready."

        report = []
        report.append("🚨 IMPORT VALIDATION REPORT")
        report.append("=" * 60)
        report.append(
            f"Found {len(issues)} import issues that may fail in production\n"
        )

        # Group by severity
        critical_issues = [i for i in issues if i.severity == "critical"]
        warning_issues = [i for i in issues if i.severity == "warning"]

        if critical_issues:
            report.append("🔴 CRITICAL ISSUES (Will fail in production)")
            report.append("-" * 60)
            for issue in critical_issues:
                report.append(f"\nFile: {issue.file_path}")
                report.append(f"Line {issue.line_number}: {issue.import_statement}")
                report.append(f"Issue: {issue.message}")
                report.append(f"Fix: {issue.suggestion}")

        if warning_issues:
            report.append("\n🟡 WARNINGS (May cause issues)")
            report.append("-" * 60)
            for issue in warning_issues:
                report.append(f"\nFile: {issue.file_path}")
                report.append(f"Line {issue.line_number}: {issue.import_statement}")
                report.append(f"Issue: {issue.message}")
                report.append(f"Suggestion: {issue.suggestion}")

        report.append(
            f"\n📚 See gold standard: {issues[0].gold_standard_ref if issues else 'N/A'}"
        )

        return "\n".join(report)

    def fix_imports_in_file(
        self, file_path: str, dry_run: bool = True
    ) -> List[Tuple[str, str]]:
        """
        Attempt to fix import issues in a file.

        Args:
            file_path: Path to file to fix
            dry_run: If True, only return proposed changes without modifying file

        Returns:
            List of (original, fixed) import tuples
        """
        issues = self.validate_file(file_path)
        if not issues:
            return []

        fixes = []

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Sort issues by line number in reverse to avoid offset issues
        issues.sort(key=lambda x: x.line_number, reverse=True)

        for issue in issues:
            if issue.severity == "critical":
                line_idx = issue.line_number - 1
                if 0 <= line_idx < len(lines):
                    original = lines[line_idx].rstrip()

                    # Simple replacement based on suggestion
                    # In practice, this would need more sophisticated AST rewriting
                    fixed = lines[line_idx].replace(
                        issue.import_statement, issue.suggestion
                    )

                    fixes.append((original, fixed.rstrip()))

                    if not dry_run:
                        lines[line_idx] = fixed

        if not dry_run and fixes:
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

        return fixes

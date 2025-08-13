"""Compatibility checker for LocalRuntime migration analysis.

This module provides comprehensive static analysis of codebases to identify
potential compatibility issues when migrating to the enhanced LocalRuntime.
It analyzes usage patterns, configuration parameters, and provides detailed
recommendations for migration.
"""

import ast
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


class IssueType(Enum):
    """Categories of compatibility issues."""

    BREAKING_CHANGE = "breaking_change"
    DEPRECATED_PARAMETER = "deprecated_parameter"
    CONFIGURATION_UPDATE = "configuration_update"
    PERFORMANCE_OPTIMIZATION = "performance_optimization"
    SECURITY_ENHANCEMENT = "security_enhancement"
    FEATURE_MIGRATION = "feature_migration"
    ENTERPRISE_UPGRADE = "enterprise_upgrade"


class IssueSeverity(Enum):
    """Severity levels for compatibility issues."""

    CRITICAL = "critical"  # Blocks migration
    HIGH = "high"  # Requires immediate attention
    MEDIUM = "medium"  # Should be addressed
    LOW = "low"  # Optional optimization
    INFO = "info"  # Informational only


@dataclass
class CompatibilityIssue:
    """Represents a compatibility issue found during analysis."""

    issue_type: IssueType
    severity: IssueSeverity
    description: str
    file_path: str
    line_number: int
    code_snippet: str
    recommendation: str
    migration_effort: str  # "low", "medium", "high"
    automated_fix: bool = False
    breaking_change: bool = False
    enterprise_feature: bool = False


@dataclass
class AnalysisResult:
    """Results of compatibility analysis."""

    total_files_analyzed: int
    issues: List[CompatibilityIssue] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    migration_complexity: str = "unknown"
    estimated_effort_days: float = 0.0
    enterprise_opportunities: List[str] = field(default_factory=list)


class CompatibilityChecker:
    """Analyzes codebases for LocalRuntime compatibility issues."""

    def __init__(self):
        """Initialize the compatibility checker."""
        self.deprecated_parameters = {
            "enable_parallel": "Use max_concurrency parameter instead",
            "thread_pool_size": "Use max_concurrency parameter instead",
            "memory_limit": "Use resource_limits parameter instead",
            "timeout": "Use resource_limits parameter instead",
            "log_level": "Use debug parameter or logging configuration",
            "cache_enabled": "Use enterprise caching nodes instead",
            "retry_count": "Use retry_policy_config parameter",
        }

        self.breaking_changes = {
            "execute_sync": "Method renamed to execute()",
            "execute_async": "Use enable_async=True parameter instead",
            "get_results": "Results now returned directly from execute()",
            "set_context": "Use user_context parameter in constructor",
            "enable_monitoring": "Parameter moved to constructor",
        }

        self.parameter_migrations = {
            "debug_mode": "debug",
            "parallel_execution": "max_concurrency",
            "enable_security_audit": "enable_audit",
            "connection_pooling": "enable_connection_sharing",
            "persistent_resources": "persistent_mode",
        }

        self.enterprise_patterns = {
            "UserContext": "Access control and security features",
            "ResourceLimits": "Enterprise resource management",
            "AuditLog": "Compliance and audit logging",
            "MonitoringNode": "Performance monitoring capabilities",
            "SecurityNode": "Enhanced security features",
        }

    def analyze_codebase(
        self,
        root_path: Union[str, Path],
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> AnalysisResult:
        """Analyze a codebase for LocalRuntime compatibility.

        Args:
            root_path: Root directory to analyze
            include_patterns: File patterns to include (e.g., ['*.py'])
            exclude_patterns: File patterns to exclude (e.g., ['test_*'])

        Returns:
            Analysis results with issues and recommendations
        """
        root_path = Path(root_path)
        include_patterns = include_patterns or ["*.py"]
        exclude_patterns = exclude_patterns or [
            "__pycache__",
            "*.pyc",
            ".git",
            ".venv",
            "venv",
            "node_modules",
        ]

        result = AnalysisResult(total_files_analyzed=0)

        # Find Python files to analyze
        python_files = self._find_python_files(
            root_path, include_patterns, exclude_patterns
        )
        result.total_files_analyzed = len(python_files)

        # Analyze each file
        for file_path in python_files:
            try:
                file_issues = self._analyze_file(file_path)
                result.issues.extend(file_issues)
            except Exception as e:
                # Add analysis error as an issue
                error_issue = CompatibilityIssue(
                    issue_type=IssueType.BREAKING_CHANGE,
                    severity=IssueSeverity.HIGH,
                    description=f"Failed to analyze file: {str(e)}",
                    file_path=str(file_path),
                    line_number=0,
                    code_snippet="",
                    recommendation="Manual review required",
                    migration_effort="medium",
                )
                result.issues.append(error_issue)

        # Generate summary and complexity assessment
        self._generate_summary(result)
        self._assess_migration_complexity(result)
        self._identify_enterprise_opportunities(result)

        return result

    def _find_python_files(
        self, root_path: Path, include_patterns: List[str], exclude_patterns: List[str]
    ) -> List[Path]:
        """Find Python files to analyze based on patterns."""
        python_files = []

        for pattern in include_patterns:
            for file_path in root_path.rglob(pattern):
                # Check if file should be excluded
                exclude_file = False
                for exclude_pattern in exclude_patterns:
                    if exclude_pattern in str(file_path):
                        exclude_file = True
                        break

                if not exclude_file and file_path.is_file():
                    python_files.append(file_path)

        return python_files

    def _analyze_file(self, file_path: Path) -> List[CompatibilityIssue]:
        """Analyze a single Python file for compatibility issues."""
        issues = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse AST for detailed analysis
            tree = ast.parse(content)
            issues.extend(self._analyze_ast(tree, file_path, content))

            # Regex-based pattern analysis for complex patterns
            issues.extend(self._analyze_patterns(content, file_path))

        except SyntaxError as e:
            issues.append(
                CompatibilityIssue(
                    issue_type=IssueType.BREAKING_CHANGE,
                    severity=IssueSeverity.CRITICAL,
                    description=f"Syntax error in file: {str(e)}",
                    file_path=str(file_path),
                    line_number=e.lineno or 0,
                    code_snippet="",
                    recommendation="Fix syntax errors before migration",
                    migration_effort="high",
                )
            )

        return issues

    def _analyze_ast(
        self, tree: ast.AST, file_path: Path, content: str
    ) -> List[CompatibilityIssue]:
        """Analyze AST for compatibility issues."""
        issues = []
        lines = content.split("\n")

        class CompatibilityVisitor(ast.NodeVisitor):
            def __init__(self, checker):
                self.checker = checker
                self.issues = []

            def visit_Call(self, node):
                # Check for LocalRuntime instantiation
                if isinstance(node.func, ast.Name) and node.func.id == "LocalRuntime":
                    self._check_constructor_call(node)

                # Check for deprecated method calls
                if isinstance(node.func, ast.Attribute):
                    self._check_method_call(node)

                self.generic_visit(node)

            def visit_ImportFrom(self, node):
                # Check for runtime imports
                if node.module and "kailash.runtime" in node.module:
                    self._check_import(node)

                self.generic_visit(node)

            def _check_constructor_call(self, node):
                """Check LocalRuntime constructor for deprecated parameters."""
                for keyword in node.keywords:
                    param_name = keyword.arg

                    # Check deprecated parameters
                    if param_name in self.checker.deprecated_parameters:
                        line_num = keyword.lineno
                        code_snippet = (
                            lines[line_num - 1] if line_num <= len(lines) else ""
                        )

                        self.issues.append(
                            CompatibilityIssue(
                                issue_type=IssueType.DEPRECATED_PARAMETER,
                                severity=IssueSeverity.HIGH,
                                description=f"Deprecated parameter '{param_name}' used",
                                file_path=str(file_path),
                                line_number=line_num,
                                code_snippet=code_snippet.strip(),
                                recommendation=self.checker.deprecated_parameters[
                                    param_name
                                ],
                                migration_effort="low",
                                automated_fix=True,
                            )
                        )

                    # Check parameter migrations
                    elif param_name in self.checker.parameter_migrations:
                        line_num = keyword.lineno
                        code_snippet = (
                            lines[line_num - 1] if line_num <= len(lines) else ""
                        )
                        new_param = self.checker.parameter_migrations[param_name]

                        self.issues.append(
                            CompatibilityIssue(
                                issue_type=IssueType.CONFIGURATION_UPDATE,
                                severity=IssueSeverity.MEDIUM,
                                description=f"Parameter '{param_name}' should be renamed to '{new_param}'",
                                file_path=str(file_path),
                                line_number=line_num,
                                code_snippet=code_snippet.strip(),
                                recommendation=f"Replace '{param_name}' with '{new_param}'",
                                migration_effort="low",
                                automated_fix=True,
                            )
                        )

            def _check_method_call(self, node):
                """Check for deprecated method calls."""
                if hasattr(node.func, "attr"):
                    method_name = node.func.attr

                    if method_name in self.checker.breaking_changes:
                        line_num = node.lineno
                        code_snippet = (
                            lines[line_num - 1] if line_num <= len(lines) else ""
                        )

                        self.issues.append(
                            CompatibilityIssue(
                                issue_type=IssueType.BREAKING_CHANGE,
                                severity=IssueSeverity.CRITICAL,
                                description=f"Deprecated method '{method_name}' used",
                                file_path=str(file_path),
                                line_number=line_num,
                                code_snippet=code_snippet.strip(),
                                recommendation=self.checker.breaking_changes[
                                    method_name
                                ],
                                migration_effort="medium",
                                breaking_change=True,
                            )
                        )

            def _check_import(self, node):
                """Check for import-related issues."""
                for alias in node.names:
                    name = alias.name

                    # Check for enterprise feature imports
                    if name in self.checker.enterprise_patterns:
                        line_num = node.lineno
                        code_snippet = (
                            lines[line_num - 1] if line_num <= len(lines) else ""
                        )

                        self.issues.append(
                            CompatibilityIssue(
                                issue_type=IssueType.ENTERPRISE_UPGRADE,
                                severity=IssueSeverity.INFO,
                                description=f"Enterprise feature '{name}' detected",
                                file_path=str(file_path),
                                line_number=line_num,
                                code_snippet=code_snippet.strip(),
                                recommendation=f"Consider upgrading to use enhanced {name}: {self.checker.enterprise_patterns[name]}",
                                migration_effort="medium",
                                enterprise_feature=True,
                            )
                        )

        visitor = CompatibilityVisitor(self)
        visitor.visit(tree)
        issues.extend(visitor.issues)

        return issues

    def _analyze_patterns(
        self, content: str, file_path: Path
    ) -> List[CompatibilityIssue]:
        """Analyze content using regex patterns for complex issues."""
        issues = []
        lines = content.split("\n")

        # Pattern for old-style runtime usage
        old_runtime_pattern = r"runtime\.(execute_sync|execute_async|get_results)"
        for i, line in enumerate(lines):
            matches = re.finditer(old_runtime_pattern, line)
            for match in matches:
                method = match.group(1)
                issues.append(
                    CompatibilityIssue(
                        issue_type=IssueType.BREAKING_CHANGE,
                        severity=IssueSeverity.CRITICAL,
                        description=f"Old-style method '{method}' usage detected",
                        file_path=str(file_path),
                        line_number=i + 1,
                        code_snippet=line.strip(),
                        recommendation=f"Replace '{method}' with new execute() method",
                        migration_effort="medium",
                        breaking_change=True,
                    )
                )

        # Pattern for configuration dictionary usage
        config_dict_pattern = r"LocalRuntime\(.*\{.*\}"
        for i, line in enumerate(lines):
            if re.search(config_dict_pattern, line):
                issues.append(
                    CompatibilityIssue(
                        issue_type=IssueType.CONFIGURATION_UPDATE,
                        severity=IssueSeverity.HIGH,
                        description="Dictionary-style configuration detected",
                        file_path=str(file_path),
                        line_number=i + 1,
                        code_snippet=line.strip(),
                        recommendation="Use named parameters instead of configuration dictionary",
                        migration_effort="medium",
                    )
                )

        # Pattern for hardcoded resource limits
        resource_pattern = r"(memory|cpu|timeout)\s*=\s*\d+"
        for i, line in enumerate(lines):
            matches = re.finditer(resource_pattern, line, re.IGNORECASE)
            for match in matches:
                resource_type = match.group(1)
                issues.append(
                    CompatibilityIssue(
                        issue_type=IssueType.PERFORMANCE_OPTIMIZATION,
                        severity=IssueSeverity.MEDIUM,
                        description=f"Hardcoded {resource_type} limit detected",
                        file_path=str(file_path),
                        line_number=i + 1,
                        code_snippet=line.strip(),
                        recommendation=f"Move {resource_type} limit to resource_limits configuration",
                        migration_effort="low",
                        automated_fix=True,
                    )
                )

        return issues

    def _generate_summary(self, result: AnalysisResult) -> None:
        """Generate summary statistics for the analysis."""
        result.summary = {
            "total_issues": len(result.issues),
            "critical_issues": len(
                [i for i in result.issues if i.severity == IssueSeverity.CRITICAL]
            ),
            "high_issues": len(
                [i for i in result.issues if i.severity == IssueSeverity.HIGH]
            ),
            "medium_issues": len(
                [i for i in result.issues if i.severity == IssueSeverity.MEDIUM]
            ),
            "low_issues": len(
                [i for i in result.issues if i.severity == IssueSeverity.LOW]
            ),
            "breaking_changes": len([i for i in result.issues if i.breaking_change]),
            "automated_fixes": len([i for i in result.issues if i.automated_fix]),
            "enterprise_opportunities": len(
                [i for i in result.issues if i.enterprise_feature]
            ),
        }

    def _assess_migration_complexity(self, result: AnalysisResult) -> None:
        """Assess overall migration complexity and effort."""
        critical_count = result.summary.get("critical_issues", 0)
        high_count = result.summary.get("high_issues", 0)
        breaking_changes = result.summary.get("breaking_changes", 0)

        # Calculate complexity score
        complexity_score = (
            (critical_count * 3) + (high_count * 2) + (breaking_changes * 2)
        )

        if complexity_score == 0:
            result.migration_complexity = "trivial"
            result.estimated_effort_days = 0.5
        elif complexity_score <= 5:
            result.migration_complexity = "low"
            result.estimated_effort_days = 1.0
        elif complexity_score <= 15:
            result.migration_complexity = "medium"
            result.estimated_effort_days = 3.0
        elif complexity_score <= 30:
            result.migration_complexity = "high"
            result.estimated_effort_days = 7.0
        else:
            result.migration_complexity = "very_high"
            result.estimated_effort_days = 14.0

    def _identify_enterprise_opportunities(self, result: AnalysisResult) -> None:
        """Identify opportunities for enterprise feature adoption."""
        opportunities = set()

        for issue in result.issues:
            if issue.enterprise_feature:
                opportunities.add(issue.description)

            # Additional opportunities based on patterns
            if "monitoring" in issue.description.lower():
                opportunities.add("Enhanced performance monitoring and analytics")
            if "security" in issue.description.lower():
                opportunities.add("Enterprise security and access control")
            if "audit" in issue.description.lower():
                opportunities.add("Compliance and audit logging")
            if "resource" in issue.description.lower():
                opportunities.add("Advanced resource management and optimization")

        result.enterprise_opportunities = list(opportunities)

    def generate_report(
        self, result: AnalysisResult, output_format: str = "text"
    ) -> str:
        """Generate a comprehensive migration report.

        Args:
            result: Analysis results
            output_format: Report format ("text", "json", "markdown")

        Returns:
            Formatted report string
        """
        if output_format == "json":
            import json

            return json.dumps(
                {
                    "summary": result.summary,
                    "migration_complexity": result.migration_complexity,
                    "estimated_effort_days": result.estimated_effort_days,
                    "enterprise_opportunities": result.enterprise_opportunities,
                    "issues": [
                        {
                            "type": issue.issue_type.value,
                            "severity": issue.severity.value,
                            "description": issue.description,
                            "file": issue.file_path,
                            "line": issue.line_number,
                            "recommendation": issue.recommendation,
                            "effort": issue.migration_effort,
                            "automated_fix": issue.automated_fix,
                            "breaking_change": issue.breaking_change,
                        }
                        for issue in result.issues
                    ],
                },
                indent=2,
            )

        elif output_format == "markdown":
            return self._generate_markdown_report(result)

        else:  # text format
            return self._generate_text_report(result)

    def _generate_text_report(self, result: AnalysisResult) -> str:
        """Generate text format report."""
        report = []
        report.append("=" * 60)
        report.append("LocalRuntime Migration Compatibility Report")
        report.append("=" * 60)
        report.append("")

        # Summary section
        report.append("SUMMARY")
        report.append("-" * 20)
        report.append(f"Files Analyzed: {result.total_files_analyzed}")
        report.append(f"Total Issues: {result.summary.get('total_issues', 0)}")
        report.append(f"Migration Complexity: {result.migration_complexity.upper()}")
        report.append(f"Estimated Effort: {result.estimated_effort_days} days")
        report.append("")

        # Issue breakdown
        report.append("ISSUE BREAKDOWN")
        report.append("-" * 20)
        report.append(f"Critical Issues: {result.summary.get('critical_issues', 0)}")
        report.append(f"High Priority: {result.summary.get('high_issues', 0)}")
        report.append(f"Medium Priority: {result.summary.get('medium_issues', 0)}")
        report.append(f"Low Priority: {result.summary.get('low_issues', 0)}")
        report.append(f"Breaking Changes: {result.summary.get('breaking_changes', 0)}")
        report.append(
            f"Automated Fixes Available: {result.summary.get('automated_fixes', 0)}"
        )
        report.append("")

        # Critical issues first
        critical_issues = [
            i for i in result.issues if i.severity == IssueSeverity.CRITICAL
        ]
        if critical_issues:
            report.append("CRITICAL ISSUES (Must Fix)")
            report.append("-" * 30)
            for issue in critical_issues:
                report.append(f"• {issue.description}")
                report.append(f"  File: {issue.file_path}:{issue.line_number}")
                report.append(f"  Code: {issue.code_snippet}")
                report.append(f"  Fix: {issue.recommendation}")
                report.append("")

        # Enterprise opportunities
        if result.enterprise_opportunities:
            report.append("ENTERPRISE UPGRADE OPPORTUNITIES")
            report.append("-" * 35)
            for opportunity in result.enterprise_opportunities:
                report.append(f"• {opportunity}")
            report.append("")

        return "\n".join(report)

    def _generate_markdown_report(self, result: AnalysisResult) -> str:
        """Generate markdown format report."""
        report = []
        report.append("# LocalRuntime Migration Compatibility Report")
        report.append("")

        # Summary table
        report.append("## Summary")
        report.append("")
        report.append("| Metric | Value |")
        report.append("|--------|-------|")
        report.append(f"| Files Analyzed | {result.total_files_analyzed} |")
        report.append(f"| Total Issues | {result.summary.get('total_issues', 0)} |")
        report.append(
            f"| Migration Complexity | {result.migration_complexity.title()} |"
        )
        report.append(f"| Estimated Effort | {result.estimated_effort_days} days |")
        report.append("")

        # Issue breakdown
        report.append("## Issue Breakdown")
        report.append("")
        report.append("| Severity | Count |")
        report.append("|----------|-------|")
        report.append(f"| Critical | {result.summary.get('critical_issues', 0)} |")
        report.append(f"| High | {result.summary.get('high_issues', 0)} |")
        report.append(f"| Medium | {result.summary.get('medium_issues', 0)} |")
        report.append(f"| Low | {result.summary.get('low_issues', 0)} |")
        report.append("")

        # Detailed issues
        if result.issues:
            report.append("## Detailed Issues")
            report.append("")

            for severity in [
                IssueSeverity.CRITICAL,
                IssueSeverity.HIGH,
                IssueSeverity.MEDIUM,
                IssueSeverity.LOW,
            ]:
                severity_issues = [i for i in result.issues if i.severity == severity]
                if severity_issues:
                    report.append(f"### {severity.value.title()} Issues")
                    report.append("")

                    for issue in severity_issues:
                        report.append(f"**{issue.description}**")
                        report.append("")
                        report.append(
                            f"- **File:** `{issue.file_path}:{issue.line_number}`"
                        )
                        if issue.code_snippet:
                            report.append(f"- **Code:** `{issue.code_snippet}`")
                        report.append(f"- **Recommendation:** {issue.recommendation}")
                        report.append(f"- **Effort:** {issue.migration_effort}")
                        if issue.automated_fix:
                            report.append("- **Automated Fix:** Available")
                        report.append("")

        # Enterprise opportunities
        if result.enterprise_opportunities:
            report.append("## Enterprise Upgrade Opportunities")
            report.append("")
            for opportunity in result.enterprise_opportunities:
                report.append(f"- {opportunity}")
            report.append("")

        return "\n".join(report)

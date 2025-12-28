"""Tests for the CompatibilityChecker class."""

import tempfile
import textwrap
from pathlib import Path

import pytest
from kailash.migration.compatibility_checker import (
    AnalysisResult,
    CompatibilityChecker,
    CompatibilityIssue,
    IssueSeverity,
    IssueType,
)


@pytest.fixture
def checker():
    """Create a CompatibilityChecker instance for testing."""
    return CompatibilityChecker()


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with test files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test Python files
        (temp_path / "main.py").write_text(
            textwrap.dedent(
                """
            from kailash.runtime.local import LocalRuntime
            from kailash.workflow.builder import WorkflowBuilder

            # Legacy configuration
            runtime = LocalRuntime(
                enable_parallel=True,
                thread_pool_size=10,
                debug_mode=True
            )

            # Legacy method usage
            workflow = WorkflowBuilder().build()
            runtime.execute_sync(workflow)
            results = runtime.get_results()
        """
            ).strip()
        )

        (temp_path / "config.py").write_text(
            textwrap.dedent(
                """
            # Configuration with deprecated parameters
            RUNTIME_CONFIG = {
                'memory_limit': 1024,
                'timeout': 300,
                'log_level': 'DEBUG'
            }

            def get_runtime():
                from kailash.runtime.local import LocalRuntime
                return LocalRuntime(**RUNTIME_CONFIG)
        """
            ).strip()
        )

        (temp_path / "modern.py").write_text(
            textwrap.dedent(
                """
            from kailash.runtime.local import LocalRuntime
            from kailash.access_control import UserContext

            # Modern configuration
            user_context = UserContext(user_id="test")
            runtime = LocalRuntime(
                debug=True,
                max_concurrency=10,
                enable_security=True,
                user_context=user_context
            )
        """
            ).strip()
        )

        # Create subdirectory with test file
        subdir = temp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.py").write_text(
            textwrap.dedent(
                """
            from kailash.runtime.local import LocalRuntime

            # More deprecated usage
            runtime = LocalRuntime(
                enable_parallel=False,
                cache_enabled=True
            )
        """
            ).strip()
        )

        yield temp_path


class TestCompatibilityChecker:
    """Test cases for CompatibilityChecker."""

    def test_initialization(self, checker):
        """Test CompatibilityChecker initialization."""
        assert checker is not None
        assert isinstance(checker.deprecated_parameters, dict)
        assert isinstance(checker.breaking_changes, dict)
        assert isinstance(checker.parameter_migrations, dict)
        assert isinstance(checker.enterprise_patterns, dict)

    def test_analyze_codebase(self, checker, temp_project_dir):
        """Test comprehensive codebase analysis."""
        result = checker.analyze_codebase(temp_project_dir)

        assert isinstance(result, AnalysisResult)
        assert result.total_files_analyzed > 0
        assert len(result.issues) > 0
        assert isinstance(result.summary, dict)
        assert result.migration_complexity in [
            "trivial",
            "low",
            "medium",
            "high",
            "very_high",
        ]
        assert result.estimated_effort_days >= 0

    def test_deprecated_parameter_detection(self, checker, temp_project_dir):
        """Test detection of deprecated parameters."""
        result = checker.analyze_codebase(temp_project_dir)

        # Should detect deprecated parameters
        deprecated_issues = [
            issue
            for issue in result.issues
            if issue.issue_type == IssueType.DEPRECATED_PARAMETER
        ]

        assert len(deprecated_issues) > 0

        # Check specific deprecated parameters
        deprecated_params = [issue.parameter for issue in deprecated_issues]
        assert any("enable_parallel" in param for param in deprecated_params)
        assert any("thread_pool_size" in param for param in deprecated_params)

    def test_breaking_change_detection(self, checker, temp_project_dir):
        """Test detection of breaking changes."""
        result = checker.analyze_codebase(temp_project_dir)

        breaking_issues = [
            issue
            for issue in result.issues
            if issue.breaking_change or issue.issue_type == IssueType.BREAKING_CHANGE
        ]

        assert len(breaking_issues) > 0

        # Should detect execute_sync usage
        execute_sync_issues = [
            issue for issue in breaking_issues if "execute_sync" in issue.description
        ]
        assert len(execute_sync_issues) > 0

    def test_parameter_migration_detection(self, checker, temp_project_dir):
        """Test detection of parameters that need migration."""
        result = checker.analyze_codebase(temp_project_dir)

        migration_issues = [
            issue
            for issue in result.issues
            if issue.issue_type == IssueType.CONFIGURATION_UPDATE
        ]

        assert len(migration_issues) > 0

    def test_enterprise_feature_detection(self, checker, temp_project_dir):
        """Test detection of enterprise features."""
        result = checker.analyze_codebase(temp_project_dir)

        enterprise_issues = [
            issue
            for issue in result.issues
            if issue.enterprise_feature
            or issue.issue_type == IssueType.ENTERPRISE_UPGRADE
        ]

        # Modern.py has UserContext which is an enterprise feature
        assert len(enterprise_issues) > 0

    def test_complexity_assessment(self, checker, temp_project_dir):
        """Test migration complexity assessment."""
        result = checker.analyze_codebase(temp_project_dir)

        # With deprecated parameters and breaking changes, should not be trivial
        assert result.migration_complexity != "trivial"
        assert result.estimated_effort_days > 0

    def test_summary_generation(self, checker, temp_project_dir):
        """Test summary statistics generation."""
        result = checker.analyze_codebase(temp_project_dir)

        assert "total_issues" in result.summary
        assert "critical_issues" in result.summary
        assert "high_issues" in result.summary
        assert "breaking_changes" in result.summary
        assert "automated_fixes" in result.summary

        # Verify counts make sense
        total = result.summary["total_issues"]
        critical = result.summary["critical_issues"]
        high = result.summary["high_issues"]
        medium = result.summary["medium_issues"]
        low = result.summary["low_issues"]

        assert total == len(result.issues)
        assert critical + high + medium + low <= total

    def test_text_report_generation(self, checker, temp_project_dir):
        """Test text format report generation."""
        result = checker.analyze_codebase(temp_project_dir)
        report = checker.generate_report(result, "text")

        assert isinstance(report, str)
        assert len(report) > 0
        assert "Migration Compatibility Report" in report
        assert "SUMMARY" in report
        assert "ISSUE BREAKDOWN" in report

    def test_json_report_generation(self, checker, temp_project_dir):
        """Test JSON format report generation."""
        result = checker.analyze_codebase(temp_project_dir)
        report = checker.generate_report(result, "json")

        assert isinstance(report, str)

        # Should be valid JSON
        import json

        data = json.loads(report)

        assert "summary" in data
        assert "migration_complexity" in data
        assert "issues" in data
        assert isinstance(data["issues"], list)

    def test_markdown_report_generation(self, checker, temp_project_dir):
        """Test markdown format report generation."""
        result = checker.analyze_codebase(temp_project_dir)
        report = checker.generate_report(result, "markdown")

        assert isinstance(report, str)
        assert len(report) > 0
        assert "# LocalRuntime Migration Compatibility Report" in report
        assert "## Summary" in report
        assert "| Metric | Value |" in report

    def test_include_exclude_patterns(self, checker, temp_project_dir):
        """Test file inclusion and exclusion patterns."""
        # Test inclusion patterns
        result_py_only = checker.analyze_codebase(
            temp_project_dir, include_patterns=["*.py"]
        )

        # Test exclusion patterns
        result_exclude_subdir = checker.analyze_codebase(
            temp_project_dir, exclude_patterns=["subdir"]
        )

        assert (
            result_py_only.total_files_analyzed
            >= result_exclude_subdir.total_files_analyzed
        )

    def test_error_handling(self, checker):
        """Test error handling for invalid inputs."""
        # Non-existent directory
        result = checker.analyze_codebase("/non/existent/path")

        assert result.total_files_analyzed == 0
        assert len(result.issues) == 0

    def test_syntax_error_handling(self, checker):
        """Test handling of Python files with syntax errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create file with syntax error
            (temp_path / "broken.py").write_text(
                "def broken_function(\n  # Missing closing parenthesis"
            )

            result = checker.analyze_codebase(temp_path)

            # Should detect the syntax error
            syntax_errors = [
                issue
                for issue in result.issues
                if "syntax error" in issue.description.lower()
            ]
            assert len(syntax_errors) > 0

    def test_enterprise_opportunities_identification(self, checker, temp_project_dir):
        """Test identification of enterprise upgrade opportunities."""
        result = checker.analyze_codebase(temp_project_dir)

        # Should identify opportunities based on patterns in the code
        assert len(result.enterprise_opportunities) >= 0

        if result.enterprise_opportunities:
            # Should be meaningful suggestions
            for opportunity in result.enterprise_opportunities:
                assert isinstance(opportunity, str)
                assert len(opportunity) > 10  # Reasonable description length

    def test_issue_severity_assignment(self, checker, temp_project_dir):
        """Test proper severity assignment to issues."""
        result = checker.analyze_codebase(temp_project_dir)

        # Check that issues have appropriate severities
        for issue in result.issues:
            assert issue.severity in [
                IssueSeverity.CRITICAL,
                IssueSeverity.HIGH,
                IssueSeverity.MEDIUM,
                IssueSeverity.LOW,
                IssueSeverity.INFO,
            ]

            # Breaking changes should be high or critical severity
            if issue.breaking_change:
                assert issue.severity in [IssueSeverity.CRITICAL, IssueSeverity.HIGH]

    def test_automated_fix_identification(self, checker, temp_project_dir):
        """Test identification of issues that can be automatically fixed."""
        result = checker.analyze_codebase(temp_project_dir)

        automated_issues = [issue for issue in result.issues if issue.automated_fix]

        # Should have at least some automated fixes for deprecated parameters
        assert len(automated_issues) > 0

        # Automated fixes should typically be for configuration/parameter issues
        for issue in automated_issues:
            assert issue.issue_type in [
                IssueType.DEPRECATED_PARAMETER,
                IssueType.CONFIGURATION_UPDATE,
                IssueType.PERFORMANCE_OPTIMIZATION,
            ]


class TestCompatibilityIssue:
    """Test cases for CompatibilityIssue dataclass."""

    def test_creation(self):
        """Test CompatibilityIssue creation."""
        issue = CompatibilityIssue(
            issue_type=IssueType.DEPRECATED_PARAMETER,
            severity=IssueSeverity.HIGH,
            description="Test issue",
            file_path="/test/file.py",
            line_number=10,
            code_snippet="test = True",
            recommendation="Update parameter",
            migration_effort="low",
        )

        assert issue.issue_type == IssueType.DEPRECATED_PARAMETER
        assert issue.severity == IssueSeverity.HIGH
        assert issue.description == "Test issue"
        assert issue.file_path == "/test/file.py"
        assert issue.line_number == 10
        assert issue.code_snippet == "test = True"
        assert issue.recommendation == "Update parameter"
        assert issue.migration_effort == "low"
        assert issue.automated_fix is False
        assert issue.breaking_change is False
        assert issue.enterprise_feature is False


class TestAnalysisResult:
    """Test cases for AnalysisResult dataclass."""

    def test_creation(self):
        """Test AnalysisResult creation."""
        result = AnalysisResult(total_files_analyzed=5)

        assert result.total_files_analyzed == 5
        assert isinstance(result.issues, list)
        assert isinstance(result.summary, dict)
        assert result.migration_complexity == "unknown"
        assert result.estimated_effort_days == 0.0
        assert isinstance(result.enterprise_opportunities, list)


if __name__ == "__main__":
    pytest.main([__file__])

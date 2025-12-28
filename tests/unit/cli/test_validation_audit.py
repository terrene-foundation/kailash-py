"""
Unit tests for the workflow validation audit CLI tool.

Tests Task 1.6: Migration Tool
- WorkflowValidationAuditor for dry-run validation
- ValidationAuditReport for collecting results
- ReportFormatter for multiple output formats
- Fix suggestions generation
"""

import csv
import json
from io import StringIO
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.cli.validation_audit import (
    ReportFormatter,
    ValidationAuditReport,
    WorkflowValidationAuditor,
    load_workflow_from_file,
)
from kailash.runtime.validation.error_categorizer import ErrorCategory
from kailash.sdk_exceptions import WorkflowExecutionError
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow


class TestValidationAuditReport:
    """Test the ValidationAuditReport class."""

    def test_report_initialization(self):
        """Test report initialization with basic info."""
        report = ValidationAuditReport("test_workflow.py", "strict")

        assert report.workflow_path == "test_workflow.py"
        assert report.validation_mode == "strict"
        assert report.total_connections == 0
        assert len(report.passed_connections) == 0
        assert len(report.failed_connections) == 0

    def test_add_passed_connection(self):
        """Test adding passed connection info."""
        report = ValidationAuditReport("test.py", "strict")

        conn_info = {
            "id": "source.output → target.input",
            "source": "source",
            "target": "target",
            "status": "passed",
        }

        report.add_passed_connection(conn_info)
        assert len(report.passed_connections) == 1
        assert report.passed_connections[0] == conn_info

    def test_add_failed_connection(self):
        """Test adding failed connection info."""
        report = ValidationAuditReport("test.py", "strict")

        conn_info = {
            "id": "source.output → target.input",
            "source": "source",
            "target": "target",
            "status": "failed",
            "error": "Type mismatch",
            "category": "type_mismatch",
        }

        report.add_failed_connection(conn_info)
        assert len(report.failed_connections) == 1
        assert report.failed_connections[0]["error"] == "Type mismatch"

    def test_add_security_violation(self):
        """Test adding security violation."""
        report = ValidationAuditReport("test.py", "strict")

        violation = {
            "node": "sql_node",
            "details": {"message": "SQL injection detected"},
        }

        report.add_security_violation(violation)
        assert len(report.security_violations) == 1
        assert (
            report.security_violations[0]["details"]["message"]
            == "SQL injection detected"
        )

    def test_add_suggestions(self):
        """Test adding fix suggestions."""
        report = ValidationAuditReport("test.py", "strict")

        report.add_suggestion("conn1", "Add type conversion")
        report.add_suggestion("conn1", "Check output format")
        report.add_suggestion("conn2", "Add validation")

        assert len(report.suggestions["conn1"]) == 2
        assert len(report.suggestions["conn2"]) == 1

    def test_get_summary(self):
        """Test summary generation."""
        report = ValidationAuditReport("test.py", "strict")
        report.total_connections = 10

        # Add some results
        for i in range(7):
            report.add_passed_connection({"id": f"conn{i}"})
        for i in range(3):
            report.add_failed_connection({"id": f"fail{i}"})

        summary = report.get_summary()

        assert summary["total_connections"] == 10
        assert summary["passed"] == 7
        assert summary["failed"] == 3
        assert summary["pass_rate"] == 70.0


class TestWorkflowValidationAuditor:
    """Test the WorkflowValidationAuditor class."""

    def test_auditor_initialization(self):
        """Test auditor initialization."""
        auditor = WorkflowValidationAuditor(validation_mode="warn")
        assert auditor.validation_mode == "warn"
        assert auditor.categorizer is not None

    def test_audit_workflow_all_pass(self):
        """Test auditing a workflow where all connections pass."""
        # Create simple workflow
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})
        builder.add_connection("source", "result", "target", "data")
        workflow = builder.build()

        auditor = WorkflowValidationAuditor("strict")

        # Mock runtime execution to succeed
        with patch("kailash.runtime.local.LocalRuntime.execute") as mock_execute:
            mock_execute.return_value = ({"target": {"result": "test"}}, "run123")

            report = auditor.audit_workflow(workflow)

        assert report.total_connections == 1
        assert len(report.passed_connections) == 1
        assert len(report.failed_connections) == 0

    def test_audit_workflow_with_failures(self):
        """Test auditing a workflow with validation failures."""
        # Create workflow
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "source", {"code": "result = 123"})
        builder.add_node("CSVReaderNode", "reader", {"file_path": "test.csv"})
        builder.add_connection("source", "result", "reader", "file_path")
        workflow = builder.build()

        auditor = WorkflowValidationAuditor("strict")

        # Mock runtime execution to fail
        with patch("kailash.runtime.local.LocalRuntime.execute") as mock_execute:
            error = WorkflowExecutionError(
                "Validation failed for node 'reader': Type mismatch"
            )
            mock_execute.side_effect = error

            # Mock metrics
            with patch(
                "kailash.runtime.local.LocalRuntime.get_validation_metrics"
            ) as mock_metrics:
                mock_metrics.return_value = {
                    "performance_summary": {},
                    "security_report": {"most_recent_violations": []},
                }

                report = auditor.audit_workflow(workflow)

        assert report.total_connections == 1
        assert len(report.failed_connections) >= 1

    def test_generate_fix_suggestions(self):
        """Test fix suggestion generation."""
        auditor = WorkflowValidationAuditor()
        report = ValidationAuditReport("test.py", "strict")

        # Add various failed connections
        report.add_failed_connection({"id": "conn1", "category": "type_mismatch"})
        report.add_failed_connection({"id": "conn2", "category": "security_violation"})
        report.add_failed_connection({"id": "conn3", "category": "missing_parameter"})

        auditor._generate_fix_suggestions(report)

        # Check suggestions were added
        assert "conn1" in report.suggestions
        assert any("transformation" in s for s in report.suggestions["conn1"])

        assert "conn2" in report.suggestions
        assert any("sanitization" in s for s in report.suggestions["conn2"])

        assert "conn3" in report.suggestions
        assert any("required" in s for s in report.suggestions["conn3"])


class TestReportFormatter:
    """Test report formatting for different output formats."""

    def create_sample_report(self) -> ValidationAuditReport:
        """Create a sample report for testing."""
        report = ValidationAuditReport("test_workflow.py", "strict")
        report.total_connections = 3

        report.add_passed_connection(
            {
                "id": "source.output → processor.input",
                "source": "source",
                "source_port": "output",
                "target": "processor",
                "target_port": "input",
                "status": "passed",
            }
        )

        report.add_failed_connection(
            {
                "id": "data.count → reader.file_path",
                "source": "data",
                "source_port": "count",
                "target": "reader",
                "target_port": "file_path",
                "status": "failed",
                "category": "type_mismatch",
                "error": "Expected str but got int",
            }
        )

        report.add_security_violation(
            {"node": "sql_node", "details": {"message": "SQL injection detected"}}
        )

        report.add_suggestion("data.count → reader.file_path", "Add type conversion")

        return report

    def test_format_text(self):
        """Test text format output."""
        report = self.create_sample_report()

        text = ReportFormatter.format_text(report, detailed=True)

        # Check key sections
        assert "WORKFLOW VALIDATION AUDIT REPORT" in text
        assert "test_workflow.py" in text
        assert "Total Connections: 3" in text
        assert "Failed: 1" in text
        assert "Security Violations: 1" in text
        assert "FAILED CONNECTIONS" in text
        assert "data.count → reader.file_path" in text
        assert "Add type conversion" in text
        assert "MIGRATION RECOMMENDATION" in text

    def test_format_json(self):
        """Test JSON format output."""
        report = self.create_sample_report()

        json_str = ReportFormatter.format_json(report, detailed=True)
        data = json.loads(json_str)

        assert data["workflow_path"] == "test_workflow.py"
        assert data["total_connections"] == 3
        assert data["passed"] == 1
        assert data["failed"] == 1
        assert len(data["failed_connections"]) == 1
        assert data["failed_connections"][0]["category"] == "type_mismatch"

    def test_format_csv(self):
        """Test CSV format output."""
        report = self.create_sample_report()

        csv_str = ReportFormatter.format_csv(report, detailed=True)

        # Parse CSV
        reader = csv.DictReader(StringIO(csv_str))
        rows = list(reader)

        assert len(rows) == 2  # 1 passed + 1 failed

        # Check passed connection
        passed = [r for r in rows if r["Status"] == "PASSED"][0]
        assert passed["Source"] == "source"
        assert passed["Target"] == "processor"

        # Check failed connection
        failed = [r for r in rows if r["Status"] == "FAILED"][0]
        assert failed["Source"] == "data"
        assert failed["Target"] == "reader"
        assert failed["Category"] == "type_mismatch"


class TestWorkflowLoading:
    """Test workflow loading from files."""

    def test_load_workflow_from_file_not_found(self):
        """Test loading non-existent file."""
        with pytest.raises(ValueError, match="not found"):
            load_workflow_from_file("/nonexistent/workflow.py")

    def test_load_workflow_from_file_wrong_extension(self):
        """Test loading non-Python file."""
        with pytest.raises(ValueError, match="must be a Python file"):
            load_workflow_from_file("workflow.txt")

    @patch("pathlib.Path.exists")
    @patch("importlib.util.spec_from_file_location")
    def test_load_workflow_with_workflow_variable(self, mock_spec, mock_exists):
        """Test loading workflow from file with 'workflow' variable."""
        mock_exists.return_value = True

        # Mock the module loading
        mock_module = MagicMock()
        mock_workflow = Mock(spec=Workflow)
        mock_module.workflow = mock_workflow

        mock_spec_obj = MagicMock()
        mock_spec_obj.loader = MagicMock()
        mock_spec.return_value = mock_spec_obj

        with patch("importlib.util.module_from_spec", return_value=mock_module):
            workflow = load_workflow_from_file("test_workflow.py")

        assert workflow == mock_workflow
        assert hasattr(workflow, "_source_file")


class TestCLIIntegration:
    """Test CLI integration points."""

    @patch("sys.argv", ["validation_audit", "test_workflow.py"])
    @patch("kailash.cli.validation_audit.load_workflow_from_file")
    @patch("kailash.cli.validation_audit.WorkflowValidationAuditor")
    def test_main_cli_text_output(self, mock_auditor_class, mock_load):
        """Test CLI with text output."""
        # Mock workflow loading
        mock_workflow = Mock(spec=Workflow)
        mock_load.return_value = mock_workflow

        # Mock auditor
        mock_auditor = Mock()
        mock_report = self.create_mock_report()
        mock_auditor.audit_workflow.return_value = mock_report
        mock_auditor_class.return_value = mock_auditor

        # Capture output
        with patch("builtins.print") as mock_print:
            from kailash.cli.validation_audit import main

            main()

        # Check output was printed
        mock_print.assert_called()
        output = mock_print.call_args[0][0]
        assert "WORKFLOW VALIDATION AUDIT REPORT" in output

    def create_mock_report(self):
        """Create a mock report for testing."""
        report = Mock(spec=ValidationAuditReport)
        report.workflow_path = "test.py"
        report.validation_mode = "strict"
        report.total_connections = 1
        report.passed_connections = []
        report.failed_connections = []
        report.security_violations = []
        report.warnings = []
        report.suggestions = {}
        report.performance_metrics = {}
        report.get_summary.return_value = {
            "workflow_path": "test.py",
            "timestamp": "2025-07-20T12:00:00",
            "validation_mode": "strict",
            "total_connections": 1,
            "passed": 1,
            "failed": 0,
            "security_violations": 0,
            "warnings": 0,
            "pass_rate": 100.0,
        }
        return report

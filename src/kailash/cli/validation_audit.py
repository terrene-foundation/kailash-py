#!/usr/bin/env python3
"""
Workflow Validation Audit Tool

A CLI tool for auditing workflow connections and generating migration reports
to help users transition to strict connection validation mode.

Usage:
    python -m kailash.cli.validation_audit <workflow_file> [options]

Options:
    --format          Output format: text, json, csv (default: text)
    --output          Output file path (default: stdout)
    --mode            Validation mode to test: off, warn, strict (default: strict)
    --detailed        Include detailed validation results
    --fix-suggestions Show suggestions for fixing validation issues
"""

import argparse
import csv
import importlib.machinery
import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kailash.nodes import NodeRegistry
from kailash.runtime.local import LocalRuntime
from kailash.runtime.validation.error_categorizer import ErrorCategorizer
from kailash.runtime.validation.metrics import (
    get_metrics_collector,
    reset_global_metrics,
)
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow


class ValidationAuditReport:
    """Container for validation audit results."""

    def __init__(self, workflow_path: str, validation_mode: str):
        self.workflow_path = workflow_path
        self.validation_mode = validation_mode
        self.timestamp = datetime.now().isoformat()
        self.total_connections = 0
        self.passed_connections = []
        self.failed_connections = []
        self.security_violations = []
        self.warnings = []
        self.suggestions = {}
        self.performance_metrics = {}

    def add_passed_connection(self, connection_info: Dict[str, Any]) -> None:
        """Add a passed connection validation."""
        self.passed_connections.append(connection_info)

    def add_failed_connection(self, connection_info: Dict[str, Any]) -> None:
        """Add a failed connection validation."""
        self.failed_connections.append(connection_info)

    def add_security_violation(self, violation_info: Dict[str, Any]) -> None:
        """Add a security violation."""
        self.security_violations.append(violation_info)

    def add_warning(self, warning: str) -> None:
        """Add a general warning."""
        self.warnings.append(warning)

    def add_suggestion(self, connection_id: str, suggestion: str) -> None:
        """Add a fix suggestion for a connection."""
        if connection_id not in self.suggestions:
            self.suggestions[connection_id] = []
        self.suggestions[connection_id].append(suggestion)

    def get_summary(self) -> Dict[str, Any]:
        """Get audit summary statistics."""
        return {
            "workflow_path": self.workflow_path,
            "timestamp": self.timestamp,
            "validation_mode": self.validation_mode,
            "total_connections": self.total_connections,
            "passed": len(self.passed_connections),
            "failed": len(self.failed_connections),
            "security_violations": len(self.security_violations),
            "warnings": len(self.warnings),
            "pass_rate": (
                len(self.passed_connections) / self.total_connections * 100
                if self.total_connections > 0
                else 0
            ),
        }


class WorkflowValidationAuditor:
    """Audits workflow connections for validation compliance."""

    def __init__(self, validation_mode: str = "strict"):
        self.validation_mode = validation_mode
        self.categorizer = ErrorCategorizer()

    def audit_workflow(
        self, workflow: Workflow, detailed: bool = False
    ) -> ValidationAuditReport:
        """Audit a workflow for connection validation compliance.

        Args:
            workflow: The workflow to audit
            detailed: Whether to include detailed validation results

        Returns:
            ValidationAuditReport with audit results
        """
        reset_global_metrics()  # Start fresh

        report = ValidationAuditReport(
            workflow_path=getattr(workflow, "_source_file", "unknown"),
            validation_mode=self.validation_mode,
        )

        # Count total connections
        report.total_connections = len(workflow.connections)

        # Create a test runtime with the specified validation mode
        runtime = LocalRuntime(connection_validation=self.validation_mode)

        # Perform dry run to collect validation results
        try:
            # Execute workflow in dry-run mode (if supported) or with minimal data
            results, run_id = runtime.execute(workflow, parameters={})

            # If execution succeeds, all connections passed validation
            for connection in workflow.connections:
                conn_id = f"{connection.source_node}.{connection.source_output} → {connection.target_node}.{connection.target_input}"
                report.add_passed_connection(
                    {
                        "id": conn_id,
                        "source": connection.source_node,
                        "source_port": connection.source_output,
                        "target": connection.target_node,
                        "target_port": connection.target_input,
                        "status": "passed",
                    }
                )

        except Exception as e:
            # Execution failed - analyze the error
            self._analyze_validation_failure(e, workflow, report, detailed)

        # Get metrics from the runtime
        metrics = runtime.get_validation_metrics()
        report.performance_metrics = metrics["performance_summary"]

        # Add security violations from metrics
        security_report = metrics["security_report"]
        for violation in security_report.get("most_recent_violations", []):
            report.add_security_violation(violation)

        # Add suggestions for failed connections
        self._generate_fix_suggestions(report)

        return report

    def _analyze_validation_failure(
        self,
        error: Exception,
        workflow: Workflow,
        report: ValidationAuditReport,
        detailed: bool,
    ) -> None:
        """Analyze validation failure and populate report."""
        error_msg = str(error)

        # Try to extract connection information from error
        for connection in workflow.connections:
            conn_id = f"{connection.source_node}.{connection.source_output} → {connection.target_node}.{connection.target_input}"

            # Simple heuristic: if connection nodes mentioned in error, it likely failed
            if (
                connection.source_node in error_msg
                or connection.target_node in error_msg
            ):

                # Categorize the error
                # Get node type from workflow nodes
                target_node = workflow.nodes.get(connection.target_node)
                node_type = target_node.node_type if target_node else "Unknown"

                error_category = self.categorizer.categorize_error(error, node_type)

                failure_info = {
                    "id": conn_id,
                    "source": connection.source_node,
                    "source_port": connection.source_output,
                    "target": connection.target_node,
                    "target_port": connection.target_input,
                    "status": "failed",
                    "error": error_msg if detailed else "Validation failed",
                    "category": error_category.value,
                }

                report.add_failed_connection(failure_info)
            else:
                # Assume passed if not mentioned in error
                report.add_passed_connection(
                    {
                        "id": conn_id,
                        "source": connection.source_node,
                        "source_port": connection.source_output,
                        "target": connection.target_node,
                        "target_port": connection.target_input,
                        "status": "passed",
                    }
                )

    def _generate_fix_suggestions(self, report: ValidationAuditReport) -> None:
        """Generate fix suggestions for failed connections."""
        for failed in report.failed_connections:
            conn_id = failed["id"]
            category = failed.get("category", "unknown")

            if category == "type_mismatch":
                report.add_suggestion(
                    conn_id,
                    "Add a transformation node between source and target to convert data types",
                )
                report.add_suggestion(
                    conn_id,
                    "Check if you're using the correct output port from the source node",
                )

            elif category == "missing_parameter":
                report.add_suggestion(
                    conn_id,
                    "Ensure all required parameters are provided via connections or node config",
                )
                report.add_suggestion(
                    conn_id,
                    "Add the missing connection or provide default value in node configuration",
                )

            elif category == "security_violation":
                report.add_suggestion(
                    conn_id, "Add input sanitization node before the target node"
                )
                report.add_suggestion(
                    conn_id, "Use parameterized queries for database operations"
                )
                report.add_suggestion(
                    conn_id, "Implement validation logic in the source node"
                )

            elif category == "constraint_violation":
                report.add_suggestion(
                    conn_id, "Add validation node to ensure data meets constraints"
                )
                report.add_suggestion(
                    conn_id, "Check node documentation for parameter requirements"
                )


class ReportFormatter:
    """Formats validation audit reports for different output formats."""

    @staticmethod
    def format_text(report: ValidationAuditReport, detailed: bool = False) -> str:
        """Format report as human-readable text."""
        lines = []
        summary = report.get_summary()

        # Header
        lines.append("=" * 70)
        lines.append("WORKFLOW VALIDATION AUDIT REPORT")
        lines.append("=" * 70)
        lines.append(f"Workflow: {summary['workflow_path']}")
        lines.append(f"Timestamp: {summary['timestamp']}")
        lines.append(f"Validation Mode: {summary['validation_mode']}")
        lines.append("")

        # Summary
        lines.append("SUMMARY")
        lines.append("-" * 30)
        lines.append(f"Total Connections: {summary['total_connections']}")
        lines.append(f"Passed: {summary['passed']} ({summary['pass_rate']:.1f}%)")
        lines.append(f"Failed: {summary['failed']}")
        lines.append(f"Security Violations: {summary['security_violations']}")
        lines.append("")

        # Failed connections
        if report.failed_connections:
            lines.append("FAILED CONNECTIONS")
            lines.append("-" * 30)
            for failed in report.failed_connections:
                lines.append(f"❌ {failed['id']}")
                lines.append(f"   Category: {failed.get('category', 'unknown')}")
                if detailed and "error" in failed:
                    lines.append(f"   Error: {failed['error']}")

                # Add suggestions
                conn_id = failed["id"]
                if conn_id in report.suggestions:
                    lines.append("   Suggestions:")
                    for suggestion in report.suggestions[conn_id]:
                        lines.append(f"   • {suggestion}")
                lines.append("")

        # Security violations
        if report.security_violations:
            lines.append("SECURITY VIOLATIONS")
            lines.append("-" * 30)
            for violation in report.security_violations:
                lines.append(f"🔒 {violation.get('node', 'Unknown node')}")
                lines.append(
                    f"   {violation.get('details', {}).get('message', 'Security issue detected')}"
                )
                lines.append("")

        # Warnings
        if report.warnings:
            lines.append("WARNINGS")
            lines.append("-" * 30)
            for warning in report.warnings:
                lines.append(f"⚠️  {warning}")
            lines.append("")

        # Performance metrics
        if report.performance_metrics:
            lines.append("PERFORMANCE METRICS")
            lines.append("-" * 30)
            metrics = report.performance_metrics
            if "performance_by_node_type" in metrics:
                for node_type, perf in metrics["performance_by_node_type"].items():
                    lines.append(f"{node_type}:")
                    lines.append(f"  Average: {perf['avg_ms']:.2f}ms")
                    lines.append(
                        f"  Min: {perf['min_ms']:.2f}ms, Max: {perf['max_ms']:.2f}ms"
                    )
            lines.append("")

        # Migration recommendation
        lines.append("MIGRATION RECOMMENDATION")
        lines.append("-" * 30)
        if summary["failed"] == 0 and summary["security_violations"] == 0:
            lines.append("✅ This workflow is ready for strict validation mode!")
            lines.append("   You can safely enable connection_validation='strict'")
        else:
            lines.append(
                "❗ This workflow needs updates before enabling strict validation:"
            )
            lines.append(f"   - Fix {summary['failed']} failed connections")
            if summary["security_violations"] > 0:
                lines.append(
                    f"   - Address {summary['security_violations']} security violations"
                )
            lines.append("   - Review the suggestions above for each issue")

        return "\n".join(lines)

    @staticmethod
    def format_json(report: ValidationAuditReport, detailed: bool = False) -> str:
        """Format report as JSON."""
        data = report.get_summary()
        data["passed_connections"] = report.passed_connections
        data["failed_connections"] = report.failed_connections
        data["security_violations"] = report.security_violations
        data["warnings"] = report.warnings
        data["suggestions"] = report.suggestions

        if detailed:
            data["performance_metrics"] = report.performance_metrics

        return json.dumps(data, indent=2)

    @staticmethod
    def format_csv(report: ValidationAuditReport, detailed: bool = False) -> str:
        """Format report as CSV."""
        output = []

        # Header
        headers = [
            "Connection ID",
            "Source",
            "Source Port",
            "Target",
            "Target Port",
            "Status",
            "Category",
            "Suggestions",
        ]
        if detailed:
            headers.append("Error")

        # Use string buffer for CSV
        import io

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)

        # All connections
        all_connections = []

        # Add passed connections
        for conn in report.passed_connections:
            row = [
                conn["id"],
                conn["source"],
                conn["source_port"],
                conn["target"],
                conn["target_port"],
                "PASSED",
                "",
                "",
            ]
            if detailed:
                row.append("")
            writer.writerow(row)

        # Add failed connections
        for conn in report.failed_connections:
            suggestions = "; ".join(report.suggestions.get(conn["id"], []))
            row = [
                conn["id"],
                conn["source"],
                conn["source_port"],
                conn["target"],
                conn["target_port"],
                "FAILED",
                conn.get("category", "unknown"),
                suggestions,
            ]
            if detailed:
                row.append(conn.get("error", ""))
            writer.writerow(row)

        return buffer.getvalue()


def load_workflow_from_file(file_path: str) -> Workflow:
    """Load a workflow from a Python file.

    Args:
        file_path: Path to the workflow file

    Returns:
        Loaded Workflow object

    Raises:
        ValueError: If workflow cannot be loaded
    """
    file_path = Path(file_path).resolve()

    if file_path.suffix != ".py":
        raise ValueError(f"Workflow file must be a Python file (.py): {file_path}")

    if not file_path.exists():
        raise ValueError(f"Workflow file not found: {file_path}")

    # Load the module
    spec = importlib.util.spec_from_file_location("workflow_module", file_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load workflow from: {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["workflow_module"] = module
    spec.loader.exec_module(module)

    # Find workflow in module
    workflow = None

    # Look for common patterns
    if hasattr(module, "workflow"):
        workflow = module.workflow
    elif hasattr(module, "build_workflow"):
        workflow = module.build_workflow()
    elif hasattr(module, "create_workflow"):
        workflow = module.create_workflow()
    else:
        # Look for any Workflow or WorkflowBuilder instance
        for name, obj in vars(module).items():
            if isinstance(obj, Workflow):
                workflow = obj
                break
            elif isinstance(obj, WorkflowBuilder):
                workflow = obj.build()
                break

    if workflow is None:
        raise ValueError(
            f"No workflow found in {file_path}. "
            "Expected 'workflow' variable or 'build_workflow()' function."
        )

    # Store source file for reporting
    workflow._source_file = str(file_path)

    return workflow


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Audit workflow connections for validation compliance"
    )

    parser.add_argument("workflow_file", help="Path to the workflow Python file")

    parser.add_argument(
        "--format",
        choices=["text", "json", "csv"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument("--output", help="Output file path (default: stdout)")

    parser.add_argument(
        "--mode",
        choices=["off", "warn", "strict"],
        default="strict",
        help="Validation mode to test (default: strict)",
    )

    parser.add_argument(
        "--detailed", action="store_true", help="Include detailed validation results"
    )

    parser.add_argument(
        "--fix-suggestions",
        action="store_true",
        help="Show suggestions for fixing validation issues",
    )

    args = parser.parse_args()

    try:
        # Load workflow
        workflow = load_workflow_from_file(args.workflow_file)

        # Audit workflow
        auditor = WorkflowValidationAuditor(validation_mode=args.mode)
        report = auditor.audit_workflow(workflow, detailed=args.detailed)

        # Format report
        if args.format == "json":
            output = ReportFormatter.format_json(report, args.detailed)
        elif args.format == "csv":
            output = ReportFormatter.format_csv(report, args.detailed)
        else:
            output = ReportFormatter.format_text(
                report, args.detailed or args.fix_suggestions
            )

        # Output report
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"Report saved to: {args.output}")
        else:
            print(output)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

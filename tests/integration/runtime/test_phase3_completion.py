"""Tests for Phase 3 completion features.

Tests performance monitoring, compatibility reporting, and enhanced debugging.
"""

import asyncio
from unittest.mock import Mock, patch

import pytest
from kailash.runtime.compatibility_reporter import (
    CompatibilityLevel,
    CompatibilityReporter,
)
from kailash.runtime.local import LocalRuntime
from kailash.runtime.performance_monitor import ExecutionMetrics, PerformanceMonitor
from kailash.workflow.builder import WorkflowBuilder


class TestPerformanceMonitoring:
    """Test performance monitoring features."""

    def test_performance_monitor_initialization(self):
        """Test performance monitor initialization."""
        monitor = PerformanceMonitor(
            performance_threshold=0.9, sample_size=10, min_samples=3
        )

        assert monitor.performance_threshold == 0.9
        assert monitor.sample_size == 10
        assert monitor.min_samples == 3
        assert monitor.recommended_mode == "route_data"

    def test_record_execution_metrics(self):
        """Test recording execution metrics."""
        monitor = PerformanceMonitor()

        # Record some metrics
        metrics1 = ExecutionMetrics(
            execution_time=1.0,
            node_count=10,
            skipped_nodes=5,
            execution_mode="skip_branches",
        )
        monitor.record_execution(metrics1)

        metrics2 = ExecutionMetrics(
            execution_time=2.0,
            node_count=10,
            skipped_nodes=0,
            execution_mode="route_data",
        )
        monitor.record_execution(metrics2)

        # Check metrics were recorded
        assert len(monitor.metrics["skip_branches"]) == 1
        assert len(monitor.metrics["route_data"]) == 1

    def test_should_switch_mode_insufficient_data(self):
        """Test mode switching with insufficient data."""
        monitor = PerformanceMonitor(min_samples=3)

        # Record only 2 samples
        for i in range(2):
            metrics = ExecutionMetrics(
                execution_time=1.0,
                node_count=10,
                skipped_nodes=5,
                execution_mode="skip_branches",
            )
            monitor.record_execution(metrics)

        should_switch, mode, reason = monitor.should_switch_mode("skip_branches")
        assert not should_switch
        assert reason == "Insufficient performance data"

    def test_should_switch_mode_performance_based(self):
        """Test performance-based mode switching."""
        monitor = PerformanceMonitor(performance_threshold=0.9, min_samples=3)

        # Skip the time check
        monitor._evaluation_interval = 0

        # Record faster skip_branches executions
        for i in range(3):
            metrics = ExecutionMetrics(
                execution_time=0.5,  # 0.05s per node
                node_count=10,
                skipped_nodes=10,
                execution_mode="skip_branches",
            )
            monitor.record_execution(metrics)

        # Record slower route_data executions
        for i in range(3):
            metrics = ExecutionMetrics(
                execution_time=2.0,  # 0.2s per node
                node_count=10,
                skipped_nodes=0,
                execution_mode="route_data",
            )
            monitor.record_execution(metrics)

        # Should recommend skip_branches when in route_data mode
        should_switch, mode, reason = monitor.should_switch_mode("route_data")
        assert should_switch
        assert mode == "skip_branches"
        assert "faster" in reason

    def test_performance_report(self):
        """Test performance report generation."""
        monitor = PerformanceMonitor()

        # Record some metrics
        for i in range(5):
            metrics = ExecutionMetrics(
                execution_time=1.0 + i * 0.1,
                node_count=10,
                skipped_nodes=i,
                execution_mode="skip_branches",
            )
            monitor.record_execution(metrics)

        report = monitor.get_performance_report()

        assert "recommended_mode" in report
        assert "mode_performance" in report
        assert "sample_counts" in report
        assert report["sample_counts"]["skip_branches"] == 5
        assert "skip_branches_stats" in report


class TestCompatibilityReporter:
    """Test compatibility reporting features."""

    def test_basic_workflow_compatibility(self):
        """Test compatibility analysis for basic workflow."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "source", {"code": "result = {'value': 42}"}
        )
        workflow.add_node(
            "SwitchNode",
            "switch",
            {"condition_field": "value", "operator": ">", "value": 40},
        )
        workflow.add_connection("source", "result", "switch", "input_data")

        reporter = CompatibilityReporter()
        report = reporter.analyze_workflow(workflow.build())

        assert report.overall_compatibility == CompatibilityLevel.FULLY_COMPATIBLE
        assert report.node_count == 2
        assert report.switch_count == 1
        assert len(report.detected_patterns) > 0

        # Should detect simple conditional routing
        simple_pattern = next(
            (
                p
                for p in report.detected_patterns
                if p.pattern_type == "Simple Conditional Routing"
            ),
            None,
        )
        assert simple_pattern is not None
        assert simple_pattern.compatibility == CompatibilityLevel.FULLY_COMPATIBLE

    def test_workflow_with_cycles(self):
        """Test compatibility analysis for workflow with cycles."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "a", {"code": "result = 1"})
        workflow.add_node("SwitchNode", "switch", {"operator": "==", "value": 1})
        workflow.add_node("PythonCodeNode", "b", {"code": "result = 2"})

        workflow.add_connection("a", "result", "switch", "input_data")
        workflow.add_connection("switch", "true_output", "b", "data")
        workflow.add_connection("b", "result", "a", "data")  # Create cycle

        reporter = CompatibilityReporter()
        report = reporter.analyze_workflow(workflow.build())

        assert report.overall_compatibility == CompatibilityLevel.PARTIALLY_COMPATIBLE
        assert any("cycle" in w.lower() for w in report.warnings)

    def test_multi_case_switches(self):
        """Test compatibility with multi-case switches."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "source", {"code": "result = {'priority': 'high'}"}
        )
        workflow.add_node(
            "SwitchNode",
            "switch",
            {
                "condition_field": "priority",
                "cases": ["low", "medium", "high", "critical"],
            },
        )
        workflow.add_connection("source", "result", "switch", "input_data")

        reporter = CompatibilityReporter()
        report = reporter.analyze_workflow(workflow.build())

        assert report.overall_compatibility == CompatibilityLevel.FULLY_COMPATIBLE

        # Should detect multi-case switch
        multi_case_pattern = next(
            (
                p
                for p in report.detected_patterns
                if p.pattern_type == "Multi-Case Switches"
            ),
            None,
        )
        assert multi_case_pattern is not None

    def test_markdown_report_generation(self):
        """Test markdown report generation."""
        workflow = WorkflowBuilder()
        workflow.add_node("SwitchNode", "switch", {"operator": "==", "value": 1})

        reporter = CompatibilityReporter()
        report = reporter.analyze_workflow(workflow.build())
        markdown = report.to_markdown()

        assert "# Conditional Execution Compatibility Report" in markdown
        assert "Overall Compatibility" in markdown
        assert "Detected Patterns" in markdown


class TestLocalRuntimeIntegration:
    """Test LocalRuntime integration with new features."""

    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self):
        """Test performance monitoring in LocalRuntime."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "source", {"code": "result = {'value': 42}"}
        )
        workflow.add_node(
            "SwitchNode",
            "switch",
            {"condition_field": "value", "operator": ">", "value": 40},
        )
        workflow.add_node(
            "PythonCodeNode", "true_branch", {"code": "result = {'processed': True}"}
        )
        workflow.add_node(
            "PythonCodeNode", "false_branch", {"code": "result = {'processed': False}"}
        )

        workflow.add_connection("source", "result", "switch", "input_data")
        workflow.add_connection("switch", "true_output", "true_branch", "data")
        workflow.add_connection("switch", "false_output", "false_branch", "data")

        runtime = LocalRuntime(conditional_execution="skip_branches")
        runtime.set_performance_monitoring(True)

        # Execute workflow
        results, _ = runtime.execute(workflow.build())

        # Get performance report
        perf_report = runtime.get_performance_report()
        assert perf_report is not None
        assert (
            "status" not in perf_report
            or perf_report["status"] != "Performance monitoring not initialized"
        )

    def test_compatibility_reporting_integration(self):
        """Test compatibility reporting in LocalRuntime."""
        workflow = WorkflowBuilder()
        workflow.add_node("SwitchNode", "switch", {"operator": "==", "value": 1})

        runtime = LocalRuntime()
        runtime.set_compatibility_reporting(True)

        # Generate compatibility report
        report = runtime.generate_compatibility_report(workflow.build())
        assert report is not None
        assert "overall_compatibility" in report

        # Get markdown report
        markdown = runtime.get_compatibility_report_markdown(workflow.build())
        assert "Compatibility Report" in markdown

    def test_automatic_mode_switching_disabled(self):
        """Test that automatic mode switching can be disabled."""
        runtime = LocalRuntime(conditional_execution="skip_branches")
        runtime.set_automatic_mode_switching(False)

        # Should not switch modes even with poor performance
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "node", {"code": "result = 1"})

        # Execute multiple times
        for _ in range(5):
            runtime.execute(workflow.build())

        assert runtime.conditional_execution == "skip_branches"

    def test_debug_info_generation(self):
        """Test debug info generation."""
        runtime = LocalRuntime()
        debug_info = runtime.get_execution_path_debug_info()

        assert "conditional_execution_mode" in debug_info
        assert "performance_monitoring_enabled" in debug_info
        assert "automatic_switching_enabled" in debug_info
        assert "compatibility_reporting_enabled" in debug_info
        assert "fallback_metrics" in debug_info
        assert "execution_analytics" in debug_info


class TestEnhancedDebugging:
    """Test enhanced debugging features."""

    def test_execution_path_logging(self, caplog):
        """Test that execution paths are logged properly."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "a", {"code": "result = 1"})
        workflow.add_node("SwitchNode", "switch", {"operator": "==", "value": 1})
        workflow.add_connection("a", "result", "switch", "input_data")

        runtime = LocalRuntime(conditional_execution="skip_branches", debug=True)
        runtime.execute(workflow.build())

        # Check for execution path logs
        assert any(
            "Phase 1: Executing SwitchNodes" in record.message
            for record in caplog.records
        )
        assert any("Phase 2:" in record.message for record in caplog.records)

    def test_performance_improvement_logging(self, caplog):
        """Test performance improvement logging."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "source", {"code": "result = 1"})
        workflow.add_node("SwitchNode", "switch", {"operator": "==", "value": 2})
        workflow.add_node("PythonCodeNode", "true_branch", {"code": "result = 2"})
        workflow.add_node("PythonCodeNode", "false_branch", {"code": "result = 3"})

        workflow.add_connection("source", "result", "switch", "input_data")
        workflow.add_connection("switch", "true_output", "true_branch", "data")
        workflow.add_connection("switch", "false_output", "false_branch", "data")

        runtime = LocalRuntime(conditional_execution="skip_branches")
        runtime.execute(workflow.build())

        # Should log performance improvement
        assert any(
            "reduction in executed nodes" in record.message for record in caplog.records
        )

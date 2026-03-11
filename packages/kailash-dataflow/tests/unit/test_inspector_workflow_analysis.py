"""
Unit tests for Inspector Task 2.2: Workflow Analysis Methods.

Tests dataclasses and methods:
- WorkflowSummary
- WorkflowMetrics
- ValidationIssue, WorkflowValidationReport
- WorkflowVisualizationData
- WorkflowPerformanceProfile
- workflow_summary()
- workflow_metrics()
- workflow_validation_report()
- workflow_visualization_data()
- workflow_performance_profile()
"""

import pytest
from dataflow import DataFlow
from dataflow.platform.inspector import (
    Inspector,
    ValidationIssue,
    WorkflowMetrics,
    WorkflowPerformanceProfile,
    WorkflowSummary,
    WorkflowValidationReport,
    WorkflowVisualizationData,
)

from kailash.workflow.builder import WorkflowBuilder


@pytest.fixture
def db():
    """Create a test DataFlow instance."""
    return DataFlow(database_url="sqlite:///:memory:")


@pytest.fixture
def inspector_with_workflow(db):
    """Create inspector with a simple workflow attached."""
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "start",
        {"code": "output = {'value': 1}", "outputs": {"output": "dict"}},
    )
    workflow.add_node(
        "PythonCodeNode",
        "middle",
        {
            "code": "output = {'value': input_val['value'] + 1}",
            "outputs": {"output": "dict"},
        },
    )
    workflow.add_node(
        "PythonCodeNode",
        "end",
        {
            "code": "output = {'value': input_val['value'] * 2}",
            "outputs": {"output": "dict"},
        },
    )
    workflow.add_connection("start", "output", "middle", "input_val")
    workflow.add_connection("middle", "output", "end", "input_val")

    inspector = Inspector(db)
    inspector.workflow_obj = workflow.build()
    return inspector


@pytest.fixture
def inspector_with_complex_workflow(db):
    """Create inspector with a complex workflow (cycles, bottlenecks)."""
    workflow = WorkflowBuilder()
    # Entry node
    workflow.add_node(
        "PythonCodeNode",
        "entry",
        {"code": "output = {'value': 1}", "outputs": {"output": "dict"}},
    )
    # Parallel branches
    workflow.add_node(
        "PythonCodeNode",
        "branch1",
        {
            "code": "output = {'value': input_val['value']}",
            "outputs": {"output": "dict"},
        },
    )
    workflow.add_node(
        "PythonCodeNode",
        "branch2",
        {
            "code": "output = {'value': input_val['value']}",
            "outputs": {"output": "dict"},
        },
    )
    workflow.add_node(
        "PythonCodeNode",
        "branch3",
        {
            "code": "output = {'value': input_val['value']}",
            "outputs": {"output": "dict"},
        },
    )
    # Bottleneck node (high fan-in)
    workflow.add_node(
        "PythonCodeNode",
        "bottleneck",
        {"code": "output = {'value': 1}", "outputs": {"output": "dict"}},
    )
    # Exit node
    workflow.add_node(
        "PythonCodeNode",
        "exit",
        {"code": "output = {'value': 1}", "outputs": {"output": "dict"}},
    )
    # Isolated node
    workflow.add_node(
        "PythonCodeNode",
        "isolated",
        {"code": "output = {'value': 1}", "outputs": {"output": "dict"}},
    )

    # Connections
    workflow.add_connection("entry", "output", "branch1", "input_val")
    workflow.add_connection("entry", "output", "branch2", "input_val")
    workflow.add_connection("entry", "output", "branch3", "input_val")
    workflow.add_connection("branch1", "output", "bottleneck", "input_val")
    workflow.add_connection("branch2", "output", "bottleneck", "input_val")
    workflow.add_connection("branch3", "output", "bottleneck", "input_val")
    workflow.add_connection("bottleneck", "output", "exit", "input_val")

    inspector = Inspector(db)
    inspector.workflow_obj = workflow.build()
    return inspector


@pytest.fixture
def inspector_no_workflow(db):
    """Create inspector without workflow."""
    return Inspector(db)


# =============================================================================
# DataClass Tests
# =============================================================================


class TestWorkflowSummary:
    """Test WorkflowSummary dataclass."""

    def test_creation(self):
        """Test creating WorkflowSummary."""
        summary = WorkflowSummary(
            node_count=5,
            connection_count=4,
            entry_points=["start"],
            exit_points=["end"],
            has_cycles=False,
            max_depth=3,
            complexity_score=15.5,
        )
        assert summary.node_count == 5
        assert summary.connection_count == 4
        assert summary.entry_points == ["start"]
        assert summary.exit_points == ["end"]
        assert not summary.has_cycles
        assert summary.max_depth == 3
        assert summary.complexity_score == 15.5

    def test_show_without_color(self):
        """Test show() method without color."""
        summary = WorkflowSummary(
            node_count=5,
            connection_count=4,
            entry_points=["start"],
            exit_points=["end"],
            has_cycles=False,
            max_depth=3,
            complexity_score=15.5,
        )
        output = summary.show(color=False)
        assert "Workflow Summary" in output
        assert "Nodes: 5" in output
        assert "Connections: 4" in output
        assert "Entry Points (1):" in output
        assert "- start" in output
        assert "Exit Points (1):" in output
        assert "- end" in output
        assert "Has Cycles: No" in output
        assert "Max Depth: 3" in output
        assert "Complexity Score: 15.50" in output

    def test_show_with_color(self):
        """Test show() method with color."""
        summary = WorkflowSummary(
            node_count=5,
            connection_count=4,
            entry_points=["start"],
            exit_points=["end"],
            has_cycles=True,
            max_depth=3,
            complexity_score=15.5,
        )
        output = summary.show(color=True)
        assert "\033[" in output  # ANSI escape code present
        assert "Workflow Summary" in output
        assert "Has Cycles:" in output
        assert "Yes" in output

    def test_show_multiple_entry_exit(self):
        """Test show() with multiple entry/exit points."""
        summary = WorkflowSummary(
            node_count=10,
            connection_count=12,
            entry_points=["start1", "start2", "start3"],
            exit_points=["end1", "end2"],
            has_cycles=False,
            max_depth=5,
            complexity_score=35.0,
        )
        output = summary.show(color=False)
        assert "Entry Points (3):" in output
        assert "- start1" in output
        assert "- start2" in output
        assert "- start3" in output
        assert "Exit Points (2):" in output
        assert "- end1" in output
        assert "- end2" in output


class TestWorkflowMetrics:
    """Test WorkflowMetrics dataclass."""

    def test_creation(self):
        """Test creating WorkflowMetrics."""
        metrics = WorkflowMetrics(
            total_nodes=10,
            total_connections=12,
            avg_connections_per_node=1.2,
            max_fan_out=3,
            max_fan_in=2,
            isolated_nodes=["isolated1"],
            bottleneck_nodes=["bottleneck1", "bottleneck2"],
            critical_path_length=5,
        )
        assert metrics.total_nodes == 10
        assert metrics.total_connections == 12
        assert metrics.avg_connections_per_node == 1.2
        assert metrics.max_fan_out == 3
        assert metrics.max_fan_in == 2
        assert metrics.isolated_nodes == ["isolated1"]
        assert metrics.bottleneck_nodes == ["bottleneck1", "bottleneck2"]
        assert metrics.critical_path_length == 5

    def test_show_without_issues(self):
        """Test show() method without issues."""
        metrics = WorkflowMetrics(
            total_nodes=10,
            total_connections=12,
            avg_connections_per_node=1.2,
            max_fan_out=2,
            max_fan_in=2,
            isolated_nodes=[],
            bottleneck_nodes=[],
            critical_path_length=5,
        )
        output = metrics.show(color=False)
        assert "Workflow Metrics" in output
        assert "Total Nodes: 10" in output
        assert "Total Connections: 12" in output
        assert "Avg Connections/Node: 1.20" in output
        assert "Max Fan-Out: 2" in output
        assert "Max Fan-In: 2" in output
        # No isolated/bottleneck sections when empty
        assert "Isolated Nodes" not in output
        assert "Bottleneck Nodes" not in output
        assert "Critical Path Length: 5" in output

    def test_show_with_issues(self):
        """Test show() method with issues."""
        metrics = WorkflowMetrics(
            total_nodes=10,
            total_connections=12,
            avg_connections_per_node=1.2,
            max_fan_out=5,
            max_fan_in=4,
            isolated_nodes=["isolated1", "isolated2"],
            bottleneck_nodes=["bottleneck1"],
            critical_path_length=5,
        )
        output = metrics.show(color=False)
        assert "Isolated Nodes (2):" in output
        assert "- isolated1" in output
        assert "- isolated2" in output
        assert "Bottleneck Nodes (1):" in output
        assert "- bottleneck1" in output


class TestValidationIssue:
    """Test ValidationIssue dataclass."""

    def test_creation_with_suggestion(self):
        """Test creating ValidationIssue with suggestion."""
        issue = ValidationIssue(
            severity="error",
            category="connection",
            node_id="node1",
            message="Missing required parameter",
            suggestion="Add 'param1' to node configuration",
        )
        assert issue.severity == "error"
        assert issue.category == "connection"
        assert issue.node_id == "node1"
        assert issue.message == "Missing required parameter"
        assert issue.suggestion == "Add 'param1' to node configuration"

    def test_creation_without_suggestion(self):
        """Test creating ValidationIssue without suggestion."""
        issue = ValidationIssue(
            severity="warning",
            category="structure",
            node_id=None,
            message="Workflow has cycles",
        )
        assert issue.severity == "warning"
        assert issue.category == "structure"
        assert issue.node_id is None
        assert issue.message == "Workflow has cycles"
        assert issue.suggestion is None


class TestWorkflowValidationReport:
    """Test WorkflowValidationReport dataclass."""

    def test_creation_valid(self):
        """Test creating valid WorkflowValidationReport."""
        report = WorkflowValidationReport(
            is_valid=True,
            error_count=0,
            warning_count=0,
            info_count=0,
            issues=[],
        )
        assert report.is_valid
        assert report.error_count == 0
        assert report.warning_count == 0
        assert report.info_count == 0
        assert len(report.issues) == 0

    def test_creation_with_issues(self):
        """Test creating WorkflowValidationReport with issues."""
        issues = [
            ValidationIssue("error", "connection", "node1", "Error message"),
            ValidationIssue("warning", "structure", None, "Warning message"),
            ValidationIssue("info", "performance", "node2", "Info message"),
        ]
        report = WorkflowValidationReport(
            is_valid=False,
            error_count=1,
            warning_count=1,
            info_count=1,
            issues=issues,
        )
        assert not report.is_valid
        assert report.error_count == 1
        assert report.warning_count == 1
        assert report.info_count == 1
        assert len(report.issues) == 3

    def test_show_valid_workflow(self):
        """Test show() method for valid workflow."""
        report = WorkflowValidationReport(
            is_valid=True,
            error_count=0,
            warning_count=0,
            info_count=0,
            issues=[],
        )
        output = report.show(color=False)
        assert "Validation Report" in output
        assert "✓ VALID" in output
        assert "Errors: 0" in output
        assert "Warnings: 0" in output
        assert "Info: 0" in output

    def test_show_invalid_workflow(self):
        """Test show() method for invalid workflow."""
        issues = [
            ValidationIssue(
                "error",
                "connection",
                "node1",
                "Missing parameter",
                "Add param",
            ),
            ValidationIssue("warning", "structure", None, "Has cycles"),
        ]
        report = WorkflowValidationReport(
            is_valid=False,
            error_count=1,
            warning_count=1,
            info_count=0,
            issues=issues,
        )
        output = report.show(color=False)
        assert "✗ INVALID" in output
        assert "Errors: 1" in output
        assert "Warnings: 1" in output
        assert "Missing parameter" in output
        assert "Has cycles" in output


class TestWorkflowVisualizationData:
    """Test WorkflowVisualizationData dataclass."""

    def test_creation(self):
        """Test creating WorkflowVisualizationData."""
        nodes = [
            {"id": "node1", "label": "Node 1", "type": "workflow_node"},
            {"id": "node2", "label": "Node 2", "type": "workflow_node"},
        ]
        edges = [
            {
                "id": "edge_0",
                "source": "node1",
                "target": "node2",
                "source_param": "output",
                "target_param": "input",
            }
        ]
        layout_hints = {
            "suggested_layout": "hierarchical",
            "direction": "top-to-bottom",
        }
        viz_data = WorkflowVisualizationData(
            nodes=nodes, edges=edges, layout_hints=layout_hints
        )
        assert len(viz_data.nodes) == 2
        assert len(viz_data.edges) == 1
        assert viz_data.layout_hints["suggested_layout"] == "hierarchical"

    def test_to_dict(self):
        """Test to_dict() method."""
        nodes = [{"id": "node1", "label": "Node 1"}]
        edges = [{"id": "edge_0", "source": "node1", "target": "node2"}]
        layout_hints = {"suggested_layout": "hierarchical"}
        viz_data = WorkflowVisualizationData(
            nodes=nodes, edges=edges, layout_hints=layout_hints
        )
        data_dict = viz_data.to_dict()
        assert "nodes" in data_dict
        assert "edges" in data_dict
        assert "layout_hints" in data_dict
        assert len(data_dict["nodes"]) == 1
        assert len(data_dict["edges"]) == 1
        assert data_dict["layout_hints"]["suggested_layout"] == "hierarchical"

    def test_show(self):
        """Test show() method."""
        nodes = [{"id": f"node{i}"} for i in range(5)]
        edges = [{"id": f"edge{i}"} for i in range(4)]
        layout_hints = {"suggested_layout": "circular"}
        viz_data = WorkflowVisualizationData(
            nodes=nodes, edges=edges, layout_hints=layout_hints
        )
        output = viz_data.show(color=False)
        assert "Visualization Data" in output
        assert "Nodes: 5" in output
        assert "Edges: 4" in output
        assert "Layout: circular" in output


class TestWorkflowPerformanceProfile:
    """Test WorkflowPerformanceProfile dataclass."""

    def test_creation(self):
        """Test creating WorkflowPerformanceProfile."""
        profile = WorkflowPerformanceProfile(
            estimated_execution_time_ms=150.0,
            parallelization_potential=0.6,
            sequential_bottlenecks=["bottleneck1"],
            parallel_stages=[["node1", "node2"], ["node3"]],
            resource_requirements={
                "memory_mb": 512,
                "cpu_cores": 4,
                "estimated_duration_seconds": 2.5,
            },
        )
        assert profile.estimated_execution_time_ms == 150.0
        assert profile.parallelization_potential == 0.6
        assert profile.sequential_bottlenecks == ["bottleneck1"]
        assert len(profile.parallel_stages) == 2
        assert profile.resource_requirements["memory_mb"] == 512

    def test_show(self):
        """Test show() method."""
        profile = WorkflowPerformanceProfile(
            estimated_execution_time_ms=150.0,
            parallelization_potential=0.6,
            sequential_bottlenecks=["bottleneck1", "bottleneck2"],
            parallel_stages=[["node1", "node2"], ["node3"]],
            resource_requirements={
                "memory_mb": 512,
                "cpu_cores": 4,
                "estimated_duration_seconds": 2.5,
            },
        )
        output = profile.show(color=False)
        assert "Performance Profile" in output
        assert "Estimated Execution Time: 150.00ms" in output
        assert "Parallelization Potential: 60.0%" in output
        assert "Sequential Bottlenecks (2):" in output
        assert "- bottleneck1" in output
        assert "- bottleneck2" in output
        assert "Parallel Stages: 2" in output
        assert "Resource Requirements:" in output
        assert "memory_mb: 512" in output
        assert "cpu_cores: 4" in output
        assert "estimated_duration_seconds: 2.5" in output


# =============================================================================
# Method Tests
# =============================================================================


class TestWorkflowSummaryMethod:
    """Test Inspector.workflow_summary() method."""

    def test_with_simple_workflow(self, inspector_with_workflow):
        """Test workflow_summary() with simple linear workflow."""
        summary = inspector_with_workflow.workflow_summary()
        assert summary.node_count == 3
        assert summary.connection_count == 2
        assert len(summary.entry_points) == 1
        assert "start" in summary.entry_points
        assert len(summary.exit_points) == 1
        assert "end" in summary.exit_points
        assert not summary.has_cycles
        assert summary.max_depth == 2
        assert summary.complexity_score > 0

    def test_with_complex_workflow(self, inspector_with_complex_workflow):
        """Test workflow_summary() with complex workflow."""
        summary = inspector_with_complex_workflow.workflow_summary()
        # workflow.build() excludes isolated nodes - only 6 connected nodes
        assert summary.node_count == 6
        assert summary.connection_count == 7
        assert len(summary.entry_points) >= 1
        assert summary.max_depth > 0
        assert summary.complexity_score > 0

    def test_without_workflow(self, inspector_no_workflow):
        """Test workflow_summary() without workflow."""
        summary = inspector_no_workflow.workflow_summary()
        assert summary.node_count == 0
        assert summary.connection_count == 0
        assert len(summary.entry_points) == 0
        assert len(summary.exit_points) == 0
        assert not summary.has_cycles
        assert summary.max_depth == 0
        assert summary.complexity_score == 0.0


class TestWorkflowMetricsMethod:
    """Test Inspector.workflow_metrics() method."""

    def test_with_simple_workflow(self, inspector_with_workflow):
        """Test workflow_metrics() with simple workflow."""
        metrics = inspector_with_workflow.workflow_metrics()
        assert metrics.total_nodes == 3
        assert metrics.total_connections == 2
        assert metrics.avg_connections_per_node > 0
        assert metrics.max_fan_out >= 0
        assert metrics.max_fan_in >= 0
        assert metrics.critical_path_length >= 0

    def test_with_complex_workflow(self, inspector_with_complex_workflow):
        """Test workflow_metrics() with complex workflow."""
        metrics = inspector_with_complex_workflow.workflow_metrics()
        # workflow.build() excludes isolated nodes - only 6 connected nodes
        assert metrics.total_nodes == 6
        assert metrics.total_connections == 7
        # No isolated nodes (excluded by workflow.build())
        assert len(metrics.isolated_nodes) == 0
        # Entry node has high fan-out (3 branches)
        assert len(metrics.bottleneck_nodes) == 0  # Not high enough for threshold

    def test_without_workflow(self, inspector_no_workflow):
        """Test workflow_metrics() without workflow."""
        metrics = inspector_no_workflow.workflow_metrics()
        assert metrics.total_nodes == 0
        assert metrics.total_connections == 0
        assert metrics.avg_connections_per_node == 0.0
        assert metrics.max_fan_out == 0
        assert metrics.max_fan_in == 0
        assert len(metrics.isolated_nodes) == 0
        assert len(metrics.bottleneck_nodes) == 0
        assert metrics.critical_path_length == 0


class TestWorkflowValidationReportMethod:
    """Test Inspector.workflow_validation_report() method."""

    def test_with_simple_workflow(self, inspector_with_workflow):
        """Test workflow_validation_report() with simple valid workflow."""
        report = inspector_with_workflow.workflow_validation_report()
        # Simple workflow should be valid (no errors)
        assert report.error_count == 0
        # May have warnings or info

    def test_with_complex_workflow(self, inspector_with_complex_workflow):
        """Test workflow_validation_report() with complex workflow."""
        report = inspector_with_complex_workflow.workflow_validation_report()
        # workflow.build() excludes isolated nodes - no warnings expected
        # The workflow is valid with only connected nodes
        assert report.error_count == 0

    def test_without_workflow(self, inspector_no_workflow):
        """Test workflow_validation_report() without workflow."""
        report = inspector_no_workflow.workflow_validation_report()
        # Should have error for no workflow
        assert not report.is_valid
        assert report.error_count > 0
        # Check for "No workflow attached" error
        no_workflow_errors = [
            issue for issue in report.issues if "no workflow" in issue.message.lower()
        ]
        assert len(no_workflow_errors) > 0


class TestWorkflowVisualizationDataMethod:
    """Test Inspector.workflow_visualization_data() method."""

    def test_with_simple_workflow(self, inspector_with_workflow):
        """Test workflow_visualization_data() with simple workflow."""
        viz_data = inspector_with_workflow.workflow_visualization_data()
        assert len(viz_data.nodes) == 3
        assert len(viz_data.edges) == 2
        assert "suggested_layout" in viz_data.layout_hints
        assert viz_data.layout_hints["suggested_layout"] == "hierarchical"
        # Check node structure
        for node in viz_data.nodes:
            assert "id" in node
            assert "label" in node
            assert "type" in node
            assert "is_entry" in node
            assert "is_exit" in node
        # Check edge structure
        for edge in viz_data.edges:
            assert "id" in edge
            assert "source" in edge
            assert "target" in edge
            assert "source_param" in edge
            assert "target_param" in edge

    def test_with_complex_workflow(self, inspector_with_complex_workflow):
        """Test workflow_visualization_data() with complex workflow."""
        viz_data = inspector_with_complex_workflow.workflow_visualization_data()
        # workflow.build() excludes isolated nodes - only 6 connected nodes
        assert len(viz_data.nodes) == 6
        assert len(viz_data.edges) == 7
        # Check entry/exit flags
        entry_nodes = [node for node in viz_data.nodes if node["is_entry"]]
        exit_nodes = [node for node in viz_data.nodes if node["is_exit"]]
        assert len(entry_nodes) >= 1
        assert len(exit_nodes) >= 1

    def test_without_workflow(self, inspector_no_workflow):
        """Test workflow_visualization_data() without workflow."""
        viz_data = inspector_no_workflow.workflow_visualization_data()
        assert len(viz_data.nodes) == 0
        assert len(viz_data.edges) == 0
        assert viz_data.layout_hints["suggested_layout"] == "empty"

    def test_to_dict_export(self, inspector_with_workflow):
        """Test to_dict() for JSON export compatibility."""
        viz_data = inspector_with_workflow.workflow_visualization_data()
        data_dict = viz_data.to_dict()
        # Should be JSON-serializable
        import json

        json_str = json.dumps(data_dict)
        assert json_str
        # Re-parse to verify
        parsed = json.loads(json_str)
        assert "nodes" in parsed
        assert "edges" in parsed
        assert "layout_hints" in parsed


class TestWorkflowPerformanceProfileMethod:
    """Test Inspector.workflow_performance_profile() method."""

    def test_with_simple_workflow(self, inspector_with_workflow):
        """Test workflow_performance_profile() with simple workflow."""
        profile = inspector_with_workflow.workflow_performance_profile()
        assert profile.estimated_execution_time_ms > 0
        assert 0.0 <= profile.parallelization_potential <= 1.0
        assert isinstance(profile.sequential_bottlenecks, list)
        assert isinstance(profile.parallel_stages, list)
        assert "memory_mb" in profile.resource_requirements
        assert "cpu_cores" in profile.resource_requirements
        assert "estimated_duration_seconds" in profile.resource_requirements

    def test_with_complex_workflow(self, inspector_with_complex_workflow):
        """Test workflow_performance_profile() with complex workflow."""
        profile = inspector_with_complex_workflow.workflow_performance_profile()
        assert profile.estimated_execution_time_ms > 0
        # Complex workflow should have some parallelization potential
        # (parallel branches exist)
        assert profile.parallelization_potential > 0
        # Should have parallel stages
        assert len(profile.parallel_stages) > 0

    def test_without_workflow(self, inspector_no_workflow):
        """Test workflow_performance_profile() without workflow."""
        profile = inspector_no_workflow.workflow_performance_profile()
        assert profile.estimated_execution_time_ms == 0.0
        assert profile.parallelization_potential == 0.0
        assert len(profile.sequential_bottlenecks) == 0
        assert len(profile.parallel_stages) == 0
        # Resource requirements dict should exist with zero values
        assert "memory_mb" in profile.resource_requirements
        assert "cpu_cores" in profile.resource_requirements
        assert "estimated_duration_seconds" in profile.resource_requirements


class TestIntegrationWorkflowAnalysis:
    """Integration tests for workflow analysis methods."""

    def test_full_analysis_workflow(self, inspector_with_complex_workflow):
        """Test full workflow analysis pipeline."""
        # Get summary
        summary = inspector_with_complex_workflow.workflow_summary()
        assert summary.node_count > 0

        # Get metrics
        metrics = inspector_with_complex_workflow.workflow_metrics()
        assert metrics.total_nodes == summary.node_count

        # Get validation report
        report = inspector_with_complex_workflow.workflow_validation_report()
        # workflow.build() excludes isolated nodes - should be valid
        assert report.error_count == 0

        # Get visualization data
        viz_data = inspector_with_complex_workflow.workflow_visualization_data()
        assert len(viz_data.nodes) == summary.node_count

        # Get performance profile
        profile = inspector_with_complex_workflow.workflow_performance_profile()
        assert profile.estimated_execution_time_ms > 0

    def test_show_methods_no_errors(self, inspector_with_workflow):
        """Test that all show() methods run without errors."""
        summary = inspector_with_workflow.workflow_summary()
        assert summary.show(color=True)
        assert summary.show(color=False)

        metrics = inspector_with_workflow.workflow_metrics()
        assert metrics.show(color=True)
        assert metrics.show(color=False)

        report = inspector_with_workflow.workflow_validation_report()
        assert report.show(color=True)
        assert report.show(color=False)

        viz_data = inspector_with_workflow.workflow_visualization_data()
        assert viz_data.show(color=True)
        assert viz_data.show(color=False)

        profile = inspector_with_workflow.workflow_performance_profile()
        assert profile.show(color=True)
        assert profile.show(color=False)

"""Simple validation that edge documentation examples build correctly."""

import re
from pathlib import Path

import pytest

from kailash.workflow.builder import WorkflowBuilder


def test_edge_warming_workflow_builds():
    """Test that edge warming workflow examples build."""
    workflow = WorkflowBuilder()

    workflow.add_node("EdgeWarmingNode", "warmer", {"operation": "start_warmer"})

    workflow.add_node(
        "EdgeWarmingNode",
        "predict",
        {"operation": "predict", "strategy": "time_series", "max_nodes": 3},
    )

    workflow.add_connection("warmer", "status", "predict", "parameters")

    # Should build without errors
    built = workflow.build()
    assert built is not None


def test_edge_monitoring_workflow_builds():
    """Test that edge monitoring workflow examples build."""
    workflow = WorkflowBuilder()

    workflow.add_node(
        "EdgeMonitoringNode",
        "monitor",
        {
            "operation": "start_monitor",
            "edge_nodes": ["edge-west-1", "edge-east-1"],
            "collect_interval": 10,
        },
    )

    workflow.add_node(
        "EdgeMonitoringNode",
        "metrics",
        {
            "operation": "record_metric",
            "edge_node": "edge-west-1",
            "metric_type": "latency",
            "value": 0.250,
        },
    )

    workflow.add_connection("monitor", "status", "metrics", "parameters")

    built = workflow.build()
    assert built is not None


def test_edge_migration_workflow_builds():
    """Test that edge migration workflow examples build."""
    workflow = WorkflowBuilder()

    workflow.add_node(
        "EdgeMigrationNode",
        "plan",
        {
            "operation": "plan_migration",
            "source_edge": "edge-west-1",
            "target_edge": "edge-east-1",
            "workloads": ["api-service"],
            "strategy": "live",
        },
    )

    workflow.add_node(
        "EdgeMigrationNode",
        "execute",
        {"operation": "execute_migration", "migration_id": "placeholder"},
    )

    workflow.add_connection("plan", "plan", "execute", "migration_id")

    built = workflow.build()
    assert built is not None


def test_complex_edge_workflow_builds():
    """Test that complex multi-node workflows build."""
    workflow = WorkflowBuilder()

    # Mix of edge nodes
    workflow.add_node(
        "EdgeStateMachine",
        "state",
        {
            "operation": "get_state",
            "edge_id": "edge-1",
            "state_id": "edge-1",  # EdgeStateMachine requires state_id
        },
    )

    workflow.add_node(
        "EdgeMonitoringNode",
        "monitor",
        {"operation": "start_monitor", "edge_nodes": ["edge-1"]},
    )

    workflow.add_node(
        "EdgeWarmingNode",
        "warmer",
        {"operation": "start_auto", "confidence_threshold": 0.8},
    )

    workflow.add_node(
        "EdgeMigrationNode",
        "migrate",
        {
            "operation": "plan_migration",
            "source_edge": "edge-1",
            "target_edge": "edge-2",
            "workloads": ["app"],
            "strategy": "live",
        },
    )

    # Connect them
    workflow.add_connection("state", "state", "monitor", "parameters")
    workflow.add_connection("monitor", "status", "warmer", "parameters")
    workflow.add_connection("warmer", "predictions", "migrate", "parameters")

    built = workflow.build()
    assert built is not None


def test_documentation_syntax_patterns():
    """Test that documentation follows correct syntax patterns."""
    doc_files = [
        "sdk-users/edge/predictive-warming-guide.md",
        "sdk-users/edge/edge-monitoring-guide.md",
        "sdk-users/edge/edge-migration-guide.md",
        "sdk-users/edge/EDGE_COMPUTING_SUMMARY.md",
        "sdk-users/edge/README.md",
    ]

    base_path = Path("./repos/projects/kailash_python_sdk")
    errors = []

    for doc_file in doc_files:
        path = base_path / doc_file
        if not path.exists():
            continue

        with open(path, "r") as f:
            content = f.read()

        # Check for correct node names
        if (
            "EdgeStateMachineNode" in content
            and doc_file != "DOCUMENTATION_FIXES_SUMMARY.md"
        ):
            errors.append(
                f"{doc_file}: Found 'EdgeStateMachineNode' - should be 'EdgeStateMachine'"
            )

        # Check for invalid mapping syntax
        if "mapping=" in content and "add_connection" in content:
            if "DOCUMENTATION_FIXES_SUMMARY" not in doc_file:
                errors.append(
                    f"{doc_file}: Found unsupported 'mapping=' in add_connection"
                )

    if errors:
        pytest.fail("Documentation syntax errors:\n" + "\n".join(errors))


def test_node_imports():
    """Test that edge nodes can be imported."""
    from kailash.nodes.edge import (
        EdgeMigrationNode,
        EdgeMonitoringNode,
        EdgeStateMachine,
        EdgeWarmingNode,
    )

    # Verify they're classes
    assert isinstance(EdgeWarmingNode, type)
    assert isinstance(EdgeMonitoringNode, type)
    assert isinstance(EdgeMigrationNode, type)
    assert isinstance(EdgeStateMachine, type)


def test_edge_service_imports():
    """Test that edge services can be imported."""
    from kailash.edge.migration.edge_migrator import EdgeMigrator, MigrationStrategy
    from kailash.edge.monitoring.edge_monitor import EdgeMonitor, MetricType
    from kailash.edge.prediction.predictive_warmer import (
        PredictionStrategy,
        PredictiveWarmer,
    )

    # Verify enums
    assert PredictionStrategy.TIME_SERIES.value == "time_series"
    assert MetricType.LATENCY.value == "latency"
    assert MigrationStrategy.LIVE.value == "live"


def test_documentation_files_exist():
    """Test that all Phase 3 documentation files exist."""
    required_files = [
        "sdk-users/edge/predictive-warming-guide.md",
        "sdk-users/edge/edge-monitoring-guide.md",
        "sdk-users/edge/edge-migration-guide.md",
        "sdk-users/edge/EDGE_COMPUTING_SUMMARY.md",
        "sdk-users/edge/DOCUMENTATION_FIXES_SUMMARY.md",
    ]

    base_path = Path("./repos/projects/kailash_python_sdk")

    for file_path in required_files:
        full_path = base_path / file_path
        assert full_path.exists(), f"Missing documentation file: {file_path}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

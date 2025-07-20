"""Quick validation tests for Phase 4 nodes."""

import pytest


def test_phase4_node_instantiation():
    """Test that all Phase 4 nodes can be instantiated properly."""
    from kailash.nodes.edge import (
        ResourceAnalyzerNode,
        ResourceOptimizerNode,
        ResourceScalerNode,
    )

    # Test instantiation
    analyzer = ResourceAnalyzerNode()
    scaler = ResourceScalerNode()
    optimizer = ResourceOptimizerNode()

    # Test parameter structures
    analyzer_params = analyzer.get_parameters()
    scaler_params = scaler.get_parameters()
    optimizer_params = optimizer.get_parameters()

    # Verify key parameters exist
    assert "operation" in analyzer_params
    assert "operation" in scaler_params
    assert "operation" in optimizer_params

    # Test parameter types
    assert analyzer_params["operation"].type == str
    assert scaler_params["operation"].type == str
    assert optimizer_params["operation"].type == str

    print("✅ ResourceAnalyzerNode: OK")
    print("✅ ResourceScalerNode: OK")
    print("✅ ResourceOptimizerNode: OK")


def test_phase4_service_classes():
    """Test that Phase 4 service classes work correctly."""
    from datetime import datetime

    from kailash.edge.resource import (
        CloudProvider,
        CostOptimizer,
        InstanceType,
        PredictiveScaler,
        ResourceAnalyzer,
        ResourceMetric,
        ResourceType,
    )

    # Test ResourceAnalyzer
    analyzer = ResourceAnalyzer()
    assert analyzer.history_window == 3600

    # Test PredictiveScaler
    scaler = PredictiveScaler()
    assert scaler.confidence_threshold == 0.7

    # Test CostOptimizer
    optimizer = CostOptimizer()
    assert optimizer.savings_threshold == 0.1

    # Test ResourceMetric creation
    metric = ResourceMetric(
        timestamp=datetime.now(),
        edge_node="test",
        resource_type=ResourceType.CPU,
        used=1.0,
        available=1.0,
        total=2.0,
    )
    assert metric.utilization == 50.0

    print("✅ ResourceAnalyzer: OK")
    print("✅ PredictiveScaler: OK")
    print("✅ CostOptimizer: OK")
    print("✅ ResourceMetric: OK")


def test_phase4_workflow_compatibility():
    """Test Phase 4 workflow building works correctly."""
    from kailash.workflow.builder import WorkflowBuilder

    workflow = WorkflowBuilder()

    # Add all Phase 4 nodes
    workflow.add_node(
        "ResourceAnalyzerNode",
        "analyzer",
        {
            "operation": "record_metric",
            "edge_node": "test-node",
            "resource_type": "cpu",
            "used": 2.0,
            "total": 4.0,
        },
    )

    workflow.add_node(
        "ResourceScalerNode",
        "scaler",
        {
            "operation": "record_usage",
            "edge_node": "test-node",
            "resource_type": "cpu",
            "usage": 2.0,
            "capacity": 4.0,
        },
    )

    workflow.add_node(
        "ResourceOptimizerNode",
        "optimizer",
        {
            "operation": "record_cost",
            "edge_node": "test-node",
            "resource_type": "cpu",
            "provider": "aws",
            "instance_type": "on_demand",
            "cost_per_hour": 0.10,
            "usage_hours": 24,
        },
    )

    # Test connections
    workflow.add_connection("analyzer", "status", "scaler", "parameters")
    workflow.add_connection("scaler", "status", "optimizer", "parameters")

    # Build workflow
    built = workflow.build()
    assert built is not None
    assert len(built.nodes) == 3
    assert len(built.connections) == 2

    print("✅ Multi-node workflow: OK")
    print("✅ Node connections: OK")


if __name__ == "__main__":
    test_phase4_node_instantiation()
    test_phase4_service_classes()
    test_phase4_workflow_compatibility()
    print("\n🎉 All Phase 4 validation tests passed!")

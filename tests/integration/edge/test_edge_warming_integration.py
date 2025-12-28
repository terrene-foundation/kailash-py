"""Integration tests for edge warming functionality."""

import asyncio
from datetime import datetime, timedelta

import pytest
from kailash.nodes.edge.edge_warming_node import EdgeWarmingNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestEdgeWarmingIntegration:
    """Integration tests for edge warming."""

    @pytest.mark.asyncio
    async def test_warming_workflow(self):
        """Test edge warming in a workflow."""
        # Create workflow
        workflow = WorkflowBuilder()

        # Add warming node
        workflow.add_node(
            "EdgeWarmingNode",
            "warmer",
            {
                "operation": "record_usage",
                "edge_node": "edge-west-1",
                "user_id": "test_user",
                "location": (37.7749, -122.4194),
                "workload_type": "ml_inference",
                "response_time": 0.250,
                "resource_usage": {"cpu": 0.3, "memory": 512},
            },
        )

        # Add prediction node
        workflow.add_node(
            "EdgeWarmingNode",
            "predictor",
            {"operation": "predict", "strategy": "hybrid"},
        )

        # Connect nodes
        workflow.add_connection("warmer", "output", "predictor", "data")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = await runtime.execute_async(workflow.build())

        # Verify recording
        assert results["warmer"]["status"] == "success"
        assert results["warmer"]["pattern_recorded"] is True

        # Verify prediction
        assert results["predictor"]["status"] == "success"
        assert "predictions" in results["predictor"]

    @pytest.mark.asyncio
    async def test_pattern_recording_and_prediction(self):
        """Test recording patterns and making predictions."""
        warming_node = EdgeWarmingNode()

        # Record multiple patterns
        base_time = datetime.now()
        for i in range(20):
            result = await warming_node.execute_async(
                operation="record_usage",
                edge_node="edge-1" if i % 2 == 0 else "edge-2",
                user_id=f"user{i % 3}",
                location=(37.7749 + i * 0.01, -122.4194),
                workload_type="ml_inference" if i % 3 == 0 else "data_processing",
                response_time=0.100 + i * 0.01,
                resource_usage={"cpu": 0.2 + i * 0.01, "memory": 256 + i * 10},
            )
            assert result["status"] == "success"

        # Make predictions
        result = await warming_node.execute_async(
            operation="predict", strategy="hybrid"
        )

        assert result["status"] == "success"
        assert "predictions" in result

        # Predictions should be sorted by confidence
        if len(result["predictions"]) > 1:
            confidences = [p["confidence"] for p in result["predictions"]]
            assert confidences == sorted(confidences, reverse=True)

    @pytest.mark.asyncio
    async def test_auto_warming_execution(self):
        """Test automatic warming execution."""
        warming_node = EdgeWarmingNode(confidence_threshold=0.5, max_prewarmed_nodes=3)

        # Record patterns to build history
        for i in range(10):
            await warming_node.execute_async(
                operation="record_usage",
                edge_node=f"edge-{i % 3}",
                user_id="auto_test_user",
                workload_type="batch_processing",
                response_time=0.200,
                resource_usage={"cpu": 0.4, "memory": 1024},
            )

        # Execute auto warming
        result = await warming_node.execute_async(
            operation="warm_nodes", auto_execute=True
        )

        assert result["status"] == "success"
        assert "warmed_nodes" in result
        assert len(result["warmed_nodes"]) <= 3  # Respects limit

    @pytest.mark.asyncio
    async def test_manual_node_warming(self):
        """Test manual node warming."""
        warming_node = EdgeWarmingNode()

        # Warm specific nodes
        result = await warming_node.execute_async(
            operation="warm_nodes", nodes_to_warm=["edge-manual-1", "edge-manual-2"]
        )

        assert result["status"] == "success"
        assert result["warmed_nodes"] == ["edge-manual-1", "edge-manual-2"]
        assert result["warmed_count"] == 2

    @pytest.mark.asyncio
    async def test_prediction_evaluation(self):
        """Test prediction evaluation and metrics."""
        warming_node = EdgeWarmingNode()

        # Record some patterns
        for i in range(5):
            await warming_node.execute_async(
                operation="record_usage",
                edge_node="edge-eval",
                user_id="eval_user",
                workload_type="test_workload",
                response_time=0.150,
                resource_usage={"cpu": 0.3, "memory": 512},
            )

        # Make prediction and warm
        predict_result = await warming_node.execute_async(
            operation="predict", strategy="time_series"
        )

        if predict_result["predictions"]:
            # Warm the predicted nodes
            await warming_node.execute_async(operation="warm_nodes", auto_execute=True)

            # Evaluate prediction
            eval_result = await warming_node.execute_async(
                operation="evaluate",
                edge_node=predict_result["predictions"][0]["edge_node"],
                was_used=True,
            )

            assert eval_result["status"] == "success"
            assert eval_result["evaluation_recorded"] is True

        # Get metrics
        metrics_result = await warming_node.execute_async(operation="get_metrics")

        assert metrics_result["status"] == "success"
        assert "metrics" in metrics_result
        assert "predictions_made" in metrics_result["metrics"]

    @pytest.mark.asyncio
    async def test_strategy_specific_predictions(self):
        """Test different prediction strategies."""
        warming_node = EdgeWarmingNode()

        # Record diverse patterns
        strategies_data = [
            # Time series pattern
            {"edge_node": "edge-morning", "workload_type": "morning_batch", "hour": 9},
            # Geographic pattern
            {
                "edge_node": "edge-west",
                "location": (37.7749, -122.4194),
                "workload_type": "regional",
            },
            # User behavior pattern
            {
                "edge_node": "edge-user-preferred",
                "user_id": "power_user",
                "workload_type": "user_specific",
            },
            # Workload pattern
            {
                "edge_node": "edge-ml",
                "workload_type": "ml_training",
                "resource_usage": {"cpu": 0.9, "memory": 4096},
            },
        ]

        # Record patterns for each strategy
        for data in strategies_data:
            for i in range(5):
                params = {
                    "operation": "record_usage",
                    "response_time": 0.200,
                    "resource_usage": data.get(
                        "resource_usage", {"cpu": 0.3, "memory": 512}
                    ),
                }
                params.update(data)

                if "hour" in data:
                    # Simulate time-based pattern
                    params["timestamp"] = datetime.now().replace(hour=data["hour"])

                await warming_node.execute_async(**params)

        # Test each strategy
        strategies = ["time_series", "geographic", "user_behavior", "workload"]

        for strategy in strategies:
            result = await warming_node.execute_async(
                operation="predict", strategy=strategy
            )

            assert result["status"] == "success"
            # Each strategy might produce predictions based on recorded patterns

    @pytest.mark.asyncio
    async def test_auto_warming_lifecycle(self):
        """Test starting and stopping automatic warming."""
        warming_node = EdgeWarmingNode()

        # Start auto warming
        start_result = await warming_node.execute_async(operation="start_auto")

        assert start_result["status"] == "success"
        assert start_result["auto_warming_active"] is True

        # Let it run briefly
        await asyncio.sleep(0.1)

        # Stop auto warming
        stop_result = await warming_node.execute_async(operation="stop_auto")

        assert stop_result["status"] == "success"
        assert stop_result["auto_warming_active"] is False

        # Cleanup
        await warming_node.cleanup()

    @pytest.mark.asyncio
    async def test_resource_estimation_in_predictions(self):
        """Test resource estimation in predictions."""
        warming_node = EdgeWarmingNode()

        # Record patterns with varying resource usage
        resource_patterns = [
            {"cpu": 0.2, "memory": 256},
            {"cpu": 0.5, "memory": 1024},
            {"cpu": 0.8, "memory": 2048},
            {"cpu": 0.3, "memory": 512},
            {"cpu": 0.9, "memory": 4096},
        ]

        for i, resources in enumerate(resource_patterns):
            await warming_node.execute_async(
                operation="record_usage",
                edge_node="edge-resource-test",
                workload_type="variable_load",
                response_time=0.100 * (i + 1),
                resource_usage=resources,
            )

        # Get predictions
        result = await warming_node.execute_async(
            operation="predict", strategy="workload"
        )

        if result["predictions"]:
            prediction = result["predictions"][0]

            # Should have resource estimates
            assert "resources_needed" in prediction
            assert "cpu" in prediction["resources_needed"]
            assert "memory" in prediction["resources_needed"]

            # Should be reasonable estimates (75th percentile)
            assert 0.5 <= prediction["resources_needed"]["cpu"] <= 0.9
            assert 1024 <= prediction["resources_needed"]["memory"] <= 4096

    @pytest.mark.asyncio
    async def test_confidence_threshold_configuration(self):
        """Test confidence threshold configuration."""
        # Create node with high confidence threshold
        warming_node = EdgeWarmingNode(confidence_threshold=0.9, max_prewarmed_nodes=10)

        # Record patterns
        for i in range(10):
            await warming_node.execute_async(
                operation="record_usage",
                edge_node=f"edge-{i}",
                workload_type="distributed",
                response_time=0.300,
                resource_usage={"cpu": 0.4, "memory": 768},
            )

        # Get predictions
        result = await warming_node.execute_async(
            operation="predict", strategy="hybrid"
        )

        # All predictions should meet threshold
        if result["predictions"]:
            for prediction in result["predictions"]:
                assert prediction["confidence"] >= 0.9

    @pytest.mark.asyncio
    async def test_warming_with_edge_state_integration(self):
        """Test warming integration with edge state management."""
        workflow = WorkflowBuilder()

        # Record usage pattern
        workflow.add_node(
            "EdgeWarmingNode",
            "recorder",
            {
                "operation": "record_usage",
                "edge_node": "edge-integrated",
                "workload_type": "stateful_processing",
                "response_time": 0.400,
                "resource_usage": {"cpu": 0.6, "memory": 1536},
            },
        )

        # Get warming predictions
        workflow.add_node(
            "EdgeWarmingNode",
            "predictor",
            {"operation": "predict", "strategy": "hybrid", "max_nodes": 3},
        )

        # Execute warming based on predictions
        workflow.add_node(
            "EdgeWarmingNode",
            "executor",
            {"operation": "warm_nodes", "auto_execute": True},
        )

        # Get metrics
        workflow.add_node("EdgeWarmingNode", "metrics", {"operation": "get_metrics"})

        # Connect workflow
        workflow.add_connection("recorder", "output", "predictor", "data")
        workflow.add_connection("predictor", "output", "executor", "data")
        workflow.add_connection("executor", "output", "metrics", "data")

        # Execute
        runtime = LocalRuntime()
        results, run_id = await runtime.execute_async(workflow.build())

        # Verify workflow execution
        assert all(
            results[node]["status"] == "success"
            for node in ["recorder", "predictor", "executor", "metrics"]
        )

        # Check metrics
        metrics = results["metrics"]["metrics"]
        assert "predictions_made" in metrics
        assert "warmed_nodes" in metrics

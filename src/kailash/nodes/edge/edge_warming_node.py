"""Edge warming node for predictive edge node preparation.

This node integrates predictive warming capabilities into workflows,
allowing automatic pre-warming of edge nodes based on usage patterns.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from kailash.edge.prediction.predictive_warmer import (
    PredictionStrategy,
    PredictiveWarmer,
    UsagePattern,
    WarmingDecision,
)
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode


@register_node()
class EdgeWarmingNode(AsyncNode):
    """Node for predictive edge warming operations.

    This node provides predictive warming capabilities to anticipate
    and prepare edge nodes before they're needed, reducing cold start latency.

    Example:
        >>> # Record usage pattern
        >>> result = await warming_node.execute_async(
        ...     operation="record_usage",
        ...     edge_node="edge-west-1",
        ...     user_id="user123",
        ...     location=(37.7749, -122.4194),
        ...     workload_type="ml_inference",
        ...     response_time=0.250,
        ...     resource_usage={"cpu": 0.3, "memory": 512}
        ... )

        >>> # Get warming predictions
        >>> result = await warming_node.execute_async(
        ...     operation="predict",
        ...     strategy="hybrid",
        ...     max_nodes=5
        ... )

        >>> # Execute warming
        >>> result = await warming_node.execute_async(
        ...     operation="warm_nodes",
        ...     auto_execute=True
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize edge warming node."""
        super().__init__(**kwargs)

        # Extract configuration
        history_window = kwargs.get("history_window", 7 * 24 * 60 * 60)
        prediction_horizon = kwargs.get("prediction_horizon", 300)
        confidence_threshold = kwargs.get("confidence_threshold", 0.7)
        max_prewarmed_nodes = kwargs.get("max_prewarmed_nodes", 10)

        # Initialize predictive warmer
        self.warmer = PredictiveWarmer(
            history_window=history_window,
            prediction_horizon=prediction_horizon,
            confidence_threshold=confidence_threshold,
            max_prewarmed_nodes=max_prewarmed_nodes,
        )

        self._auto_warming_task = None

    @property
    def input_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation to perform (record_usage, predict, warm_nodes, evaluate, get_metrics, start_auto, stop_auto)",
            ),
            # For record_usage
            "edge_node": NodeParameter(
                name="edge_node",
                type=str,
                required=False,
                description="Edge node identifier",
            ),
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                required=False,
                description="User identifier for pattern analysis",
            ),
            "location": NodeParameter(
                name="location",
                type=tuple,
                required=False,
                description="Geographic location (latitude, longitude)",
            ),
            "workload_type": NodeParameter(
                name="workload_type",
                type=str,
                required=False,
                default="general",
                description="Type of workload",
            ),
            "response_time": NodeParameter(
                name="response_time",
                type=float,
                required=False,
                default=0.0,
                description="Response time in seconds",
            ),
            "resource_usage": NodeParameter(
                name="resource_usage",
                type=dict,
                required=False,
                default={},
                description="Resource usage metrics",
            ),
            # For predict
            "strategy": NodeParameter(
                name="strategy",
                type=str,
                required=False,
                default="hybrid",
                description="Prediction strategy (time_series, geographic, user_behavior, workload, hybrid)",
            ),
            "max_nodes": NodeParameter(
                name="max_nodes",
                type=int,
                required=False,
                description="Maximum nodes to warm",
            ),
            # For warm_nodes
            "auto_execute": NodeParameter(
                name="auto_execute",
                type=bool,
                required=False,
                default=False,
                description="Automatically execute warming decisions",
            ),
            "nodes_to_warm": NodeParameter(
                name="nodes_to_warm",
                type=list,
                required=False,
                description="Specific nodes to warm",
            ),
            # For evaluate
            "was_used": NodeParameter(
                name="was_used",
                type=bool,
                required=False,
                description="Whether the predicted node was actually used",
            ),
            # Configuration
            "history_window": NodeParameter(
                name="history_window",
                type=int,
                required=False,
                default=7 * 24 * 60 * 60,
                description="Time window for historical analysis (seconds)",
            ),
            "prediction_horizon": NodeParameter(
                name="prediction_horizon",
                type=int,
                required=False,
                default=300,
                description="How far ahead to predict (seconds)",
            ),
            "confidence_threshold": NodeParameter(
                name="confidence_threshold",
                type=float,
                required=False,
                default=0.7,
                description="Minimum confidence for warming",
            ),
            "max_prewarmed_nodes": NodeParameter(
                name="max_prewarmed_nodes",
                type=int,
                required=False,
                default=10,
                description="Maximum nodes to keep warm",
            ),
        }

    @property
    def output_parameters(self) -> Dict[str, NodeParameter]:
        """Define output parameters."""
        return {
            "status": NodeParameter(
                name="status", type=str, description="Operation status"
            ),
            "predictions": NodeParameter(
                name="predictions",
                type=list,
                required=False,
                description="List of warming predictions",
            ),
            "warmed_nodes": NodeParameter(
                name="warmed_nodes",
                type=list,
                required=False,
                description="List of warmed edge nodes",
            ),
            "metrics": NodeParameter(
                name="metrics",
                type=dict,
                required=False,
                description="Prediction metrics",
            ),
            "pattern_recorded": NodeParameter(
                name="pattern_recorded",
                type=bool,
                required=False,
                description="Whether usage pattern was recorded",
            ),
            "auto_warming_active": NodeParameter(
                name="auto_warming_active",
                type=bool,
                required=False,
                description="Whether automatic warming is active",
            ),
        }

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get all node parameters for compatibility."""
        # Return only input parameters for validation
        return self.input_parameters

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute edge warming operation."""
        operation = kwargs["operation"]

        try:
            if operation == "record_usage":
                return await self._record_usage(kwargs)
            elif operation == "predict":
                return await self._predict_warming(kwargs)
            elif operation == "warm_nodes":
                return await self._warm_nodes(kwargs)
            elif operation == "evaluate":
                return await self._evaluate_prediction(kwargs)
            elif operation == "get_metrics":
                return await self._get_metrics()
            elif operation == "start_auto":
                return await self._start_auto_warming()
            elif operation == "stop_auto":
                return await self._stop_auto_warming()
            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            self.logger.error(f"Edge warming operation failed: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def _record_usage(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Record a usage pattern."""
        # Create usage pattern
        pattern = UsagePattern(
            timestamp=datetime.now(),
            edge_node=kwargs.get("edge_node", "unknown"),
            user_id=kwargs.get("user_id"),
            location=kwargs.get("location"),
            workload_type=kwargs.get("workload_type", "general"),
            response_time=kwargs.get("response_time", 0.0),
            resource_usage=kwargs.get("resource_usage", {}),
        )

        # Record pattern
        await self.warmer.record_usage(pattern)

        return {
            "status": "success",
            "pattern_recorded": True,
            "patterns_total": len(self.warmer.usage_history),
        }

    async def _predict_warming(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Make warming predictions."""
        # Get strategy
        strategy_name = kwargs.get("strategy", "hybrid")
        try:
            strategy = PredictionStrategy(strategy_name)
        except ValueError:
            strategy = PredictionStrategy.HYBRID

        # Make predictions
        decisions = await self.warmer.predict_warming_needs(strategy)

        # Format predictions
        predictions = []
        for decision in decisions:
            predictions.append(
                {
                    "edge_node": decision.edge_node,
                    "confidence": decision.confidence,
                    "predicted_time": decision.predicted_time.isoformat(),
                    "resources_needed": decision.resources_needed,
                    "strategy": decision.strategy_used.value,
                    "reasoning": decision.reasoning,
                }
            )

        return {
            "status": "success",
            "predictions": predictions,
            "prediction_count": len(predictions),
        }

    async def _warm_nodes(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute node warming."""
        warmed_nodes = []

        if kwargs.get("auto_execute", False):
            # Use predictions to warm nodes
            decisions = await self.warmer.predict_warming_needs()

            for decision in decisions:
                # Simulate warming
                await self._warm_single_node(
                    decision.edge_node, decision.resources_needed
                )
                warmed_nodes.append(decision.edge_node)

        elif kwargs.get("nodes_to_warm"):
            # Warm specific nodes
            for node in kwargs["nodes_to_warm"]:
                await self._warm_single_node(node, {"cpu": 0.1, "memory": 128})
                warmed_nodes.append(node)

        return {
            "status": "success",
            "warmed_nodes": warmed_nodes,
            "warmed_count": len(warmed_nodes),
        }

    async def _warm_single_node(self, edge_node: str, resources: Dict[str, float]):
        """Warm a single edge node."""
        # TODO: Implement actual edge warming
        # This would involve:
        # 1. Connecting to edge infrastructure
        # 2. Pre-allocating resources
        # 3. Loading necessary data/models
        # 4. Running health checks

        # For now, simulate warming
        self.logger.info(f"Warming edge node {edge_node} with resources {resources}")
        await asyncio.sleep(0.1)  # Simulate warming time

    async def _evaluate_prediction(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a prediction."""
        edge_node = kwargs.get("edge_node", "unknown")
        was_used = kwargs.get("was_used", False)

        self.warmer.evaluate_prediction(edge_node, was_used)

        return {
            "status": "success",
            "edge_node": edge_node,
            "was_used": was_used,
            "evaluation_recorded": True,
        }

    async def _get_metrics(self) -> Dict[str, Any]:
        """Get prediction metrics."""
        metrics = self.warmer.get_metrics()

        return {"status": "success", "metrics": metrics}

    async def _start_auto_warming(self) -> Dict[str, Any]:
        """Start automatic warming."""
        if not self._auto_warming_task:
            await self.warmer.start()
            self._auto_warming_task = self.warmer._prediction_task

        return {"status": "success", "auto_warming_active": True}

    async def _stop_auto_warming(self) -> Dict[str, Any]:
        """Stop automatic warming."""
        if self._auto_warming_task:
            await self.warmer.stop()
            self._auto_warming_task = None

        return {"status": "success", "auto_warming_active": False}

    async def cleanup(self):
        """Clean up resources."""
        if self._auto_warming_task:
            await self.warmer.stop()

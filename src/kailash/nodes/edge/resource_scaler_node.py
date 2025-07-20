"""Resource scaler node for predictive edge resource scaling.

This node integrates predictive scaling capabilities into workflows,
enabling ML-based resource demand prediction and proactive scaling.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from kailash.edge.resource.predictive_scaler import (
    PredictionHorizon,
    PredictiveScaler,
    ScalingDecision,
    ScalingPrediction,
    ScalingStrategy,
)
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode


@register_node()
class ResourceScalerNode(AsyncNode):
    """Node for predictive resource scaling operations.

    This node provides ML-based scaling predictions and automated
    scaling decisions for edge resources.

    Example:
        >>> # Record usage for predictions
        >>> result = await scaler_node.execute_async(
        ...     operation="record_usage",
        ...     edge_node="edge-west-1",
        ...     resource_type="cpu",
        ...     usage=3.2,
        ...     capacity=4.0
        ... )

        >>> # Get scaling predictions
        >>> result = await scaler_node.execute_async(
        ...     operation="predict_scaling",
        ...     strategy="hybrid",
        ...     horizons=["immediate", "short_term"]
        ... )

        >>> # Get resource forecast
        >>> result = await scaler_node.execute_async(
        ...     operation="get_forecast",
        ...     edge_node="edge-west-1",
        ...     resource_type="cpu",
        ...     forecast_minutes=60
        ... )

        >>> # Evaluate past decision
        >>> result = await scaler_node.execute_async(
        ...     operation="evaluate_decision",
        ...     decision_id="edge-1_12345",
        ...     actual_usage={"edge-1:cpu": 85.5}
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize resource scaler node."""
        super().__init__(**kwargs)

        # Extract configuration
        prediction_window = kwargs.get("prediction_window", 3600)
        update_interval = kwargs.get("update_interval", 60)
        confidence_threshold = kwargs.get("confidence_threshold", 0.7)
        scale_up_threshold = kwargs.get("scale_up_threshold", 0.8)
        scale_down_threshold = kwargs.get("scale_down_threshold", 0.3)
        min_data_points = kwargs.get("min_data_points", 30)

        # Initialize scaler
        self.scaler = PredictiveScaler(
            prediction_window=prediction_window,
            update_interval=update_interval,
            confidence_threshold=confidence_threshold,
            scale_up_threshold=scale_up_threshold,
            scale_down_threshold=scale_down_threshold,
            min_data_points=min_data_points,
        )

        self._scaler_started = False

    @property
    def input_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation to perform (record_usage, predict_scaling, get_forecast, evaluate_decision, start_scaler, stop_scaler)",
            ),
            # For record_usage
            "edge_node": NodeParameter(
                name="edge_node",
                type=str,
                required=False,
                description="Edge node identifier",
            ),
            "resource_type": NodeParameter(
                name="resource_type",
                type=str,
                required=False,
                description="Type of resource",
            ),
            "usage": NodeParameter(
                name="usage",
                type=float,
                required=False,
                description="Current resource usage",
            ),
            "capacity": NodeParameter(
                name="capacity",
                type=float,
                required=False,
                description="Total resource capacity",
            ),
            # For predict_scaling
            "strategy": NodeParameter(
                name="strategy",
                type=str,
                required=False,
                default="hybrid",
                description="Scaling strategy (reactive, predictive, scheduled, hybrid, aggressive, conservative)",
            ),
            "horizons": NodeParameter(
                name="horizons",
                type=list,
                required=False,
                description="Prediction horizons (immediate, short_term, medium_term, long_term)",
            ),
            # For get_forecast
            "forecast_minutes": NodeParameter(
                name="forecast_minutes",
                type=int,
                required=False,
                default=60,
                description="Minutes to forecast ahead",
            ),
            # For evaluate_decision
            "decision_id": NodeParameter(
                name="decision_id",
                type=str,
                required=False,
                description="Decision ID to evaluate",
            ),
            "actual_usage": NodeParameter(
                name="actual_usage",
                type=dict,
                required=False,
                description="Actual usage that occurred",
            ),
            "feedback": NodeParameter(
                name="feedback",
                type=str,
                required=False,
                description="Optional feedback on decision",
            ),
            # Configuration
            "prediction_window": NodeParameter(
                name="prediction_window",
                type=int,
                required=False,
                default=3600,
                description="Historical data window for predictions (seconds)",
            ),
            "update_interval": NodeParameter(
                name="update_interval",
                type=int,
                required=False,
                default=60,
                description="How often to update predictions (seconds)",
            ),
            "confidence_threshold": NodeParameter(
                name="confidence_threshold",
                type=float,
                required=False,
                default=0.7,
                description="Minimum confidence for scaling actions",
            ),
            "scale_up_threshold": NodeParameter(
                name="scale_up_threshold",
                type=float,
                required=False,
                default=0.8,
                description="Utilization threshold for scaling up (0-1)",
            ),
            "scale_down_threshold": NodeParameter(
                name="scale_down_threshold",
                type=float,
                required=False,
                default=0.3,
                description="Utilization threshold for scaling down (0-1)",
            ),
            "min_data_points": NodeParameter(
                name="min_data_points",
                type=int,
                required=False,
                default=30,
                description="Minimum data points for predictions",
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
                description="Scaling predictions",
            ),
            "decisions": NodeParameter(
                name="decisions",
                type=list,
                required=False,
                description="Scaling decisions",
            ),
            "forecast": NodeParameter(
                name="forecast",
                type=dict,
                required=False,
                description="Resource usage forecast",
            ),
            "usage_recorded": NodeParameter(
                name="usage_recorded",
                type=bool,
                required=False,
                description="Whether usage was recorded",
            ),
            "evaluation_result": NodeParameter(
                name="evaluation_result",
                type=dict,
                required=False,
                description="Decision evaluation result",
            ),
            "scaler_active": NodeParameter(
                name="scaler_active",
                type=bool,
                required=False,
                description="Whether scaler is active",
            ),
        }

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get all node parameters for compatibility."""
        return self.input_parameters

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute scaling operation."""
        operation = kwargs["operation"]

        try:
            if operation == "record_usage":
                return await self._record_usage(kwargs)
            elif operation == "predict_scaling":
                return await self._predict_scaling(kwargs)
            elif operation == "get_forecast":
                return await self._get_forecast(kwargs)
            elif operation == "evaluate_decision":
                return await self._evaluate_decision(kwargs)
            elif operation == "start_scaler":
                return await self._start_scaler()
            elif operation == "stop_scaler":
                return await self._stop_scaler()
            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            self.logger.error(f"Resource scaling operation failed: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def _record_usage(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Record resource usage."""
        await self.scaler.record_usage(
            edge_node=kwargs.get("edge_node", "unknown"),
            resource_type=kwargs.get("resource_type", "unknown"),
            usage=kwargs.get("usage", 0.0),
            capacity=kwargs.get("capacity", 1.0),
            timestamp=datetime.now(),
        )

        return {
            "status": "success",
            "usage_recorded": True,
            "edge_node": kwargs.get("edge_node"),
            "resource_type": kwargs.get("resource_type"),
            "utilization": (kwargs.get("usage", 0) / kwargs.get("capacity", 1) * 100),
        }

    async def _predict_scaling(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Generate scaling predictions."""
        # Parse strategy
        strategy_str = kwargs.get("strategy", "hybrid")
        try:
            strategy = ScalingStrategy(strategy_str)
        except ValueError:
            strategy = ScalingStrategy.HYBRID

        # Parse horizons
        horizon_strs = kwargs.get("horizons", ["immediate", "short_term"])
        horizons = []

        horizon_map = {
            "immediate": PredictionHorizon.IMMEDIATE,
            "short_term": PredictionHorizon.SHORT_TERM,
            "medium_term": PredictionHorizon.MEDIUM_TERM,
            "long_term": PredictionHorizon.LONG_TERM,
        }

        for h_str in horizon_strs:
            if h_str in horizon_map:
                horizons.append(horizon_map[h_str])

        if not horizons:
            horizons = [PredictionHorizon.IMMEDIATE, PredictionHorizon.SHORT_TERM]

        # Get predictions
        decisions = await self.scaler.predict_scaling_needs(
            strategy=strategy, horizons=horizons
        )

        # Extract predictions from decisions
        all_predictions = []
        for decision in decisions:
            all_predictions.extend(decision.predictions)

        return {
            "status": "success",
            "decisions": [d.to_dict() for d in decisions],
            "predictions": [p.to_dict() for p in all_predictions],
            "decision_count": len(decisions),
            "prediction_count": len(all_predictions),
            "actions_required": len(
                [d for d in decisions if d.action_plan.get("actions")]
            ),
        }

    async def _get_forecast(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get resource forecast."""
        forecast = await self.scaler.get_resource_forecast(
            edge_node=kwargs.get("edge_node", "unknown"),
            resource_type=kwargs.get("resource_type", "unknown"),
            forecast_minutes=kwargs.get("forecast_minutes", 60),
        )

        return {"status": "success", "forecast": forecast}

    async def _evaluate_decision(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a scaling decision."""
        decision_id = kwargs.get("decision_id")
        actual_usage = kwargs.get("actual_usage", {})
        feedback = kwargs.get("feedback")

        if not decision_id:
            return {"status": "error", "error": "decision_id is required"}

        await self.scaler.evaluate_scaling_decision(
            decision_id=decision_id, actual_usage=actual_usage, feedback=feedback
        )

        return {
            "status": "success",
            "evaluation_result": {
                "decision_id": decision_id,
                "evaluated": True,
                "feedback_provided": feedback is not None,
            },
        }

    async def _start_scaler(self) -> Dict[str, Any]:
        """Start background scaler."""
        if not self._scaler_started:
            await self.scaler.start()
            self._scaler_started = True

        return {"status": "success", "scaler_active": True}

    async def _stop_scaler(self) -> Dict[str, Any]:
        """Stop background scaler."""
        if self._scaler_started:
            await self.scaler.stop()
            self._scaler_started = False

        return {"status": "success", "scaler_active": False}

    async def cleanup(self):
        """Clean up resources."""
        if self._scaler_started:
            await self.scaler.stop()

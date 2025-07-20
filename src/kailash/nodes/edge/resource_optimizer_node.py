"""Resource optimizer node for intelligent cost optimization.

This node integrates cost optimization capabilities into workflows,
providing multi-cloud cost analysis and optimization recommendations.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from kailash.edge.resource.cost_optimizer import (
    CloudProvider,
    CostMetric,
    CostOptimization,
    CostOptimizer,
    InstanceType,
    OptimizationStrategy,
)
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode


@register_node()
class ResourceOptimizerNode(AsyncNode):
    """Node for cost optimization operations.

    This node provides comprehensive cost analysis and optimization
    for edge computing resources across multiple cloud providers.

    Example:
        >>> # Record cost data
        >>> result = await optimizer_node.execute_async(
        ...     operation="record_cost",
        ...     edge_node="edge-west-1",
        ...     resource_type="cpu",
        ...     provider="aws",
        ...     instance_type="on_demand",
        ...     cost_per_hour=0.10,
        ...     usage_hours=24
        ... )

        >>> # Optimize costs
        >>> result = await optimizer_node.execute_async(
        ...     operation="optimize_costs",
        ...     strategy="balance_cost_performance",
        ...     edge_nodes=["edge-west-1", "edge-west-2"]
        ... )

        >>> # Get spot recommendations
        >>> result = await optimizer_node.execute_async(
        ...     operation="get_spot_recommendations",
        ...     edge_nodes=["edge-west-1"]
        ... )

        >>> # Calculate ROI
        >>> result = await optimizer_node.execute_async(
        ...     operation="calculate_roi",
        ...     optimization_id="opt_12345",
        ...     implementation_cost=500.0
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize resource optimizer node."""
        super().__init__(**kwargs)

        # Extract configuration
        cost_history_days = kwargs.get("cost_history_days", 30)
        optimization_interval = kwargs.get("optimization_interval", 3600)
        savings_threshold = kwargs.get("savings_threshold", 0.1)
        risk_tolerance = kwargs.get("risk_tolerance", "medium")

        # Initialize optimizer
        self.optimizer = CostOptimizer(
            cost_history_days=cost_history_days,
            optimization_interval=optimization_interval,
            savings_threshold=savings_threshold,
            risk_tolerance=risk_tolerance,
        )

        self._optimizer_started = False

    @property
    def input_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation to perform (record_cost, optimize_costs, get_spot_recommendations, get_reservation_recommendations, calculate_roi, get_cost_forecast, start_optimizer, stop_optimizer)",
            ),
            # For record_cost
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
            "provider": NodeParameter(
                name="provider",
                type=str,
                required=False,
                description="Cloud provider (aws, gcp, azure, alibaba, edge_local)",
            ),
            "instance_type": NodeParameter(
                name="instance_type",
                type=str,
                required=False,
                description="Instance pricing type (on_demand, spot, reserved, savings_plan, dedicated)",
            ),
            "cost_per_hour": NodeParameter(
                name="cost_per_hour",
                type=float,
                required=False,
                description="Cost per hour for the resource",
            ),
            "usage_hours": NodeParameter(
                name="usage_hours",
                type=float,
                required=False,
                description="Hours of usage",
            ),
            "currency": NodeParameter(
                name="currency",
                type=str,
                required=False,
                default="USD",
                description="Currency for costs",
            ),
            # For optimize_costs
            "strategy": NodeParameter(
                name="strategy",
                type=str,
                required=False,
                default="balance_cost_performance",
                description="Optimization strategy (minimize_cost, balance_cost_performance, maximize_performance, predictable_cost, risk_averse)",
            ),
            "edge_nodes": NodeParameter(
                name="edge_nodes",
                type=list,
                required=False,
                description="Specific edge nodes to optimize",
            ),
            # For recommendations
            "providers": NodeParameter(
                name="providers",
                type=list,
                required=False,
                description="Specific providers to analyze",
            ),
            # For ROI calculation
            "optimization_id": NodeParameter(
                name="optimization_id",
                type=str,
                required=False,
                description="Optimization ID for ROI calculation",
            ),
            "implementation_cost": NodeParameter(
                name="implementation_cost",
                type=float,
                required=False,
                default=0.0,
                description="One-time implementation cost",
            ),
            # For forecast
            "forecast_months": NodeParameter(
                name="forecast_months",
                type=int,
                required=False,
                default=12,
                description="Months to forecast",
            ),
            "include_optimizations": NodeParameter(
                name="include_optimizations",
                type=bool,
                required=False,
                default=True,
                description="Include optimization impact in forecast",
            ),
            # Configuration
            "cost_history_days": NodeParameter(
                name="cost_history_days",
                type=int,
                required=False,
                default=30,
                description="Days of cost history to analyze",
            ),
            "optimization_interval": NodeParameter(
                name="optimization_interval",
                type=int,
                required=False,
                default=3600,
                description="How often to run optimization (seconds)",
            ),
            "savings_threshold": NodeParameter(
                name="savings_threshold",
                type=float,
                required=False,
                default=0.1,
                description="Minimum savings percentage (0-1)",
            ),
            "risk_tolerance": NodeParameter(
                name="risk_tolerance",
                type=str,
                required=False,
                default="medium",
                description="Risk tolerance (low, medium, high)",
            ),
        }

    @property
    def output_parameters(self) -> Dict[str, NodeParameter]:
        """Define output parameters."""
        return {
            "status": NodeParameter(
                name="status", type=str, description="Operation status"
            ),
            "optimizations": NodeParameter(
                name="optimizations",
                type=list,
                required=False,
                description="Cost optimization recommendations",
            ),
            "spot_recommendations": NodeParameter(
                name="spot_recommendations",
                type=list,
                required=False,
                description="Spot instance recommendations",
            ),
            "reservation_recommendations": NodeParameter(
                name="reservation_recommendations",
                type=list,
                required=False,
                description="Reserved capacity recommendations",
            ),
            "roi_analysis": NodeParameter(
                name="roi_analysis",
                type=dict,
                required=False,
                description="ROI analysis results",
            ),
            "cost_forecast": NodeParameter(
                name="cost_forecast",
                type=dict,
                required=False,
                description="Cost forecast with optimizations",
            ),
            "cost_recorded": NodeParameter(
                name="cost_recorded",
                type=bool,
                required=False,
                description="Whether cost was recorded",
            ),
            "total_savings": NodeParameter(
                name="total_savings",
                type=float,
                required=False,
                description="Total estimated savings",
            ),
            "optimizer_active": NodeParameter(
                name="optimizer_active",
                type=bool,
                required=False,
                description="Whether optimizer is active",
            ),
        }

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get all node parameters for compatibility."""
        return self.input_parameters

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute cost optimization operation."""
        operation = kwargs["operation"]

        try:
            if operation == "record_cost":
                return await self._record_cost(kwargs)
            elif operation == "optimize_costs":
                return await self._optimize_costs(kwargs)
            elif operation == "get_spot_recommendations":
                return await self._get_spot_recommendations(kwargs)
            elif operation == "get_reservation_recommendations":
                return await self._get_reservation_recommendations(kwargs)
            elif operation == "calculate_roi":
                return await self._calculate_roi(kwargs)
            elif operation == "get_cost_forecast":
                return await self._get_cost_forecast(kwargs)
            elif operation == "start_optimizer":
                return await self._start_optimizer()
            elif operation == "stop_optimizer":
                return await self._stop_optimizer()
            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            self.logger.error(f"Cost optimization operation failed: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def _record_cost(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Record cost data."""
        # Parse provider
        provider_str = kwargs.get("provider", "aws")
        try:
            provider = CloudProvider(provider_str)
        except ValueError:
            provider = CloudProvider.AWS

        # Parse instance type
        instance_type_str = kwargs.get("instance_type", "on_demand")
        try:
            instance_type = InstanceType(instance_type_str)
        except ValueError:
            instance_type = InstanceType.ON_DEMAND

        # Calculate total cost
        cost_per_hour = kwargs.get("cost_per_hour", 0.0)
        usage_hours = kwargs.get("usage_hours", 0.0)
        total_cost = cost_per_hour * usage_hours

        # Create cost metric
        cost_metric = CostMetric(
            timestamp=datetime.now(),
            edge_node=kwargs.get("edge_node", "unknown"),
            resource_type=kwargs.get("resource_type", "unknown"),
            provider=provider,
            instance_type=instance_type,
            cost_per_hour=cost_per_hour,
            usage_hours=usage_hours,
            total_cost=total_cost,
            currency=kwargs.get("currency", "USD"),
        )

        # Record cost
        await self.optimizer.record_cost(cost_metric)

        return {
            "status": "success",
            "cost_recorded": True,
            "total_cost": total_cost,
            "cost_metric": cost_metric.to_dict(),
        }

    async def _optimize_costs(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Generate cost optimizations."""
        # Parse strategy
        strategy_str = kwargs.get("strategy", "balance_cost_performance")
        try:
            strategy = OptimizationStrategy(strategy_str)
        except ValueError:
            strategy = OptimizationStrategy.BALANCE_COST_PERFORMANCE

        # Get optimization recommendations
        optimizations = await self.optimizer.optimize_costs(
            strategy=strategy, edge_nodes=kwargs.get("edge_nodes")
        )

        # Calculate total savings
        total_savings = sum(opt.estimated_savings for opt in optimizations)

        return {
            "status": "success",
            "optimizations": [opt.to_dict() for opt in optimizations],
            "optimization_count": len(optimizations),
            "total_savings": total_savings,
            "average_savings_percentage": (
                sum(opt.savings_percentage for opt in optimizations)
                / len(optimizations)
                if optimizations
                else 0
            ),
        }

    async def _get_spot_recommendations(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get spot instance recommendations."""
        recommendations = await self.optimizer.get_spot_recommendations(
            edge_nodes=kwargs.get("edge_nodes")
        )

        # Calculate total potential savings
        total_savings = sum(rec.potential_savings for rec in recommendations)

        return {
            "status": "success",
            "spot_recommendations": [rec.to_dict() for rec in recommendations],
            "recommendation_count": len(recommendations),
            "total_potential_savings": total_savings,
            "average_savings_percentage": (
                sum(
                    rec.potential_savings / rec.current_on_demand_cost * 100
                    for rec in recommendations
                    if rec.current_on_demand_cost > 0
                )
                / len(recommendations)
                if recommendations
                else 0
            ),
        }

    async def _get_reservation_recommendations(
        self, kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get reserved capacity recommendations."""
        # Parse providers
        provider_strs = kwargs.get("providers", [])
        providers = []

        for p_str in provider_strs:
            try:
                providers.append(CloudProvider(p_str))
            except ValueError:
                continue

        recommendations = await self.optimizer.get_reservation_recommendations(
            providers=providers if providers else None
        )

        # Calculate total savings
        total_savings = sum(rec.total_savings for rec in recommendations)

        return {
            "status": "success",
            "reservation_recommendations": [rec.to_dict() for rec in recommendations],
            "recommendation_count": len(recommendations),
            "total_potential_savings": total_savings,
            "average_savings_percentage": (
                sum(
                    rec.total_savings / rec.on_demand_equivalent * 100
                    for rec in recommendations
                    if rec.on_demand_equivalent > 0
                )
                / len(recommendations)
                if recommendations
                else 0
            ),
        }

    async def _calculate_roi(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate ROI for an optimization."""
        optimization_id = kwargs.get("optimization_id")
        implementation_cost = kwargs.get("implementation_cost", 0.0)

        if not optimization_id:
            return {"status": "error", "error": "optimization_id is required"}

        # Find the optimization
        optimization = None
        for opt in self.optimizer.optimizations:
            if opt.optimization_id == optimization_id:
                optimization = opt
                break

        if not optimization:
            return {
                "status": "error",
                "error": f"Optimization {optimization_id} not found",
            }

        # Calculate ROI
        roi_analysis = await self.optimizer.calculate_roi(
            optimization=optimization, implementation_cost=implementation_cost
        )

        return {"status": "success", "roi_analysis": roi_analysis}

    async def _get_cost_forecast(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get cost forecast."""
        forecast = await self.optimizer.get_cost_forecast(
            forecast_months=kwargs.get("forecast_months", 12),
            include_optimizations=kwargs.get("include_optimizations", True),
        )

        return {"status": "success", "cost_forecast": forecast}

    async def _start_optimizer(self) -> Dict[str, Any]:
        """Start background optimizer."""
        if not self._optimizer_started:
            await self.optimizer.start()
            self._optimizer_started = True

        return {"status": "success", "optimizer_active": True}

    async def _stop_optimizer(self) -> Dict[str, Any]:
        """Stop background optimizer."""
        if self._optimizer_started:
            await self.optimizer.stop()
            self._optimizer_started = False

        return {"status": "success", "optimizer_active": False}

    async def cleanup(self):
        """Clean up resources."""
        if self._optimizer_started:
            await self.optimizer.stop()

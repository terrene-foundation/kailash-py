"""Cost optimizer for intelligent edge resource cost management.

This module provides multi-cloud cost optimization, spot instance management,
reserved capacity planning, and ROI-based allocation decisions.
"""

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class CloudProvider(Enum):
    """Supported cloud providers."""

    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    ALIBABA = "alibaba"
    EDGE_LOCAL = "edge_local"


class InstanceType(Enum):
    """Instance pricing types."""

    ON_DEMAND = "on_demand"
    SPOT = "spot"
    RESERVED = "reserved"
    SAVINGS_PLAN = "savings_plan"
    DEDICATED = "dedicated"


class OptimizationStrategy(Enum):
    """Cost optimization strategies."""

    MINIMIZE_COST = "minimize_cost"
    BALANCE_COST_PERFORMANCE = "balance_cost_performance"
    MAXIMIZE_PERFORMANCE = "maximize_performance"
    PREDICTABLE_COST = "predictable_cost"
    RISK_AVERSE = "risk_averse"


@dataclass
class CostMetric:
    """Cost measurement for resources."""

    timestamp: datetime
    edge_node: str
    resource_type: str
    provider: CloudProvider
    instance_type: InstanceType
    cost_per_hour: float
    usage_hours: float
    total_cost: float
    currency: str = "USD"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "edge_node": self.edge_node,
            "resource_type": self.resource_type,
            "provider": self.provider.value,
            "instance_type": self.instance_type.value,
            "cost_per_hour": self.cost_per_hour,
            "usage_hours": self.usage_hours,
            "total_cost": self.total_cost,
            "currency": self.currency,
            "metadata": self.metadata,
        }


@dataclass
class CostOptimization:
    """Cost optimization recommendation."""

    optimization_id: str
    edge_node: str
    current_setup: Dict[str, Any]
    recommended_setup: Dict[str, Any]
    estimated_savings: float
    savings_percentage: float
    confidence: float
    implementation_effort: str  # low, medium, high
    risk_level: str  # low, medium, high
    reasoning: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "optimization_id": self.optimization_id,
            "edge_node": self.edge_node,
            "current_setup": self.current_setup,
            "recommended_setup": self.recommended_setup,
            "estimated_savings": self.estimated_savings,
            "savings_percentage": self.savings_percentage,
            "confidence": self.confidence,
            "implementation_effort": self.implementation_effort,
            "risk_level": self.risk_level,
            "reasoning": self.reasoning,
        }


@dataclass
class SpotInstanceRecommendation:
    """Spot instance optimization recommendation."""

    edge_node: str
    current_on_demand_cost: float
    spot_cost: float
    potential_savings: float
    interruption_risk: float
    recommended_strategy: str
    backup_plan: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "edge_node": self.edge_node,
            "current_on_demand_cost": self.current_on_demand_cost,
            "spot_cost": self.spot_cost,
            "potential_savings": self.potential_savings,
            "savings_percentage": (
                (self.potential_savings / self.current_on_demand_cost * 100)
                if self.current_on_demand_cost > 0
                else 0
            ),
            "interruption_risk": self.interruption_risk,
            "recommended_strategy": self.recommended_strategy,
            "backup_plan": self.backup_plan,
        }


@dataclass
class ReservationRecommendation:
    """Reserved capacity recommendation."""

    resource_type: str
    provider: CloudProvider
    commitment_length: int  # months
    upfront_cost: float
    monthly_cost: float
    on_demand_equivalent: float
    total_savings: float
    breakeven_months: int
    utilization_requirement: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resource_type": self.resource_type,
            "provider": self.provider.value,
            "commitment_length": self.commitment_length,
            "upfront_cost": self.upfront_cost,
            "monthly_cost": self.monthly_cost,
            "on_demand_equivalent": self.on_demand_equivalent,
            "total_savings": self.total_savings,
            "savings_percentage": (
                (self.total_savings / self.on_demand_equivalent * 100)
                if self.on_demand_equivalent > 0
                else 0
            ),
            "breakeven_months": self.breakeven_months,
            "utilization_requirement": self.utilization_requirement,
        }


class CostOptimizer:
    """Multi-cloud cost optimizer for edge resources."""

    def __init__(
        self,
        cost_history_days: int = 30,
        optimization_interval: int = 3600,  # 1 hour
        savings_threshold: float = 0.1,  # 10% minimum savings
        risk_tolerance: str = "medium",
    ):
        """Initialize cost optimizer.

        Args:
            cost_history_days: Days of cost history to analyze
            optimization_interval: How often to run optimization
            savings_threshold: Minimum savings percentage to recommend
            risk_tolerance: Risk tolerance (low, medium, high)
        """
        self.cost_history_days = cost_history_days
        self.optimization_interval = optimization_interval
        self.savings_threshold = savings_threshold
        self.risk_tolerance = risk_tolerance

        # Cost data storage
        self.cost_metrics: List[CostMetric] = []
        self.provider_pricing: Dict[str, Dict[str, Any]] = {}

        # Optimization history
        self.optimizations: List[CostOptimization] = []
        self.implemented_optimizations: List[str] = []

        # Background task
        self._optimization_task: Optional[asyncio.Task] = None

        self.logger = logging.getLogger(__name__)

        # Initialize default pricing data
        self._initialize_pricing_data()

    async def start(self):
        """Start background optimization."""
        if not self._optimization_task:
            self._optimization_task = asyncio.create_task(self._optimization_loop())
            self.logger.info("Cost optimizer started")

    async def stop(self):
        """Stop background optimization."""
        if self._optimization_task:
            self._optimization_task.cancel()
            try:
                await self._optimization_task
            except asyncio.CancelledError:
                pass
            self._optimization_task = None
            self.logger.info("Cost optimizer stopped")

    async def record_cost(self, cost_metric: CostMetric):
        """Record a cost metric.

        Args:
            cost_metric: Cost metric to record
        """
        self.cost_metrics.append(cost_metric)

        # Keep only recent history
        cutoff = datetime.now() - timedelta(days=self.cost_history_days)
        self.cost_metrics = [m for m in self.cost_metrics if m.timestamp > cutoff]

    async def optimize_costs(
        self,
        strategy: OptimizationStrategy = OptimizationStrategy.BALANCE_COST_PERFORMANCE,
        edge_nodes: Optional[List[str]] = None,
    ) -> List[CostOptimization]:
        """Generate cost optimization recommendations.

        Args:
            strategy: Optimization strategy
            edge_nodes: Specific edge nodes to optimize

        Returns:
            List of cost optimizations
        """
        optimizations = []

        # Get nodes to analyze
        nodes_to_analyze = edge_nodes if edge_nodes else self._get_all_edge_nodes()

        for node in nodes_to_analyze:
            # Analyze current costs
            current_costs = self._analyze_node_costs(node)

            if not current_costs:
                continue

            # Generate optimization recommendations
            node_optimizations = await self._optimize_node_costs(
                node, current_costs, strategy
            )

            optimizations.extend(node_optimizations)

        # Filter by savings threshold
        significant_optimizations = [
            opt
            for opt in optimizations
            if opt.savings_percentage >= self.savings_threshold * 100
        ]

        # Store optimizations
        self.optimizations.extend(significant_optimizations)

        return significant_optimizations

    async def get_spot_recommendations(
        self, edge_nodes: Optional[List[str]] = None
    ) -> List[SpotInstanceRecommendation]:
        """Get spot instance recommendations.

        Args:
            edge_nodes: Specific edge nodes to analyze

        Returns:
            List of spot instance recommendations
        """
        recommendations = []

        nodes_to_analyze = edge_nodes if edge_nodes else self._get_all_edge_nodes()

        for node in nodes_to_analyze:
            current_costs = self._analyze_node_costs(node)

            if not current_costs:
                continue

            # Check if spot instances would be beneficial
            spot_rec = await self._analyze_spot_opportunity(node, current_costs)

            if spot_rec and spot_rec.potential_savings > 0:
                recommendations.append(spot_rec)

        return recommendations

    async def get_reservation_recommendations(
        self, providers: Optional[List[CloudProvider]] = None
    ) -> List[ReservationRecommendation]:
        """Get reserved capacity recommendations.

        Args:
            providers: Specific providers to analyze

        Returns:
            List of reservation recommendations
        """
        recommendations = []

        providers_to_analyze = providers if providers else list(CloudProvider)

        for provider in providers_to_analyze:
            # Analyze usage patterns for this provider
            usage_patterns = self._analyze_provider_usage(provider)

            for resource_type, usage in usage_patterns.items():
                # Check if reservation would be beneficial
                reservation_rec = await self._analyze_reservation_opportunity(
                    provider, resource_type, usage
                )

                if reservation_rec and reservation_rec.total_savings > 0:
                    recommendations.append(reservation_rec)

        return recommendations

    async def calculate_roi(
        self, optimization: CostOptimization, implementation_cost: float = 0.0
    ) -> Dict[str, Any]:
        """Calculate ROI for an optimization.

        Args:
            optimization: Cost optimization to analyze
            implementation_cost: One-time implementation cost

        Returns:
            ROI analysis
        """
        monthly_savings = optimization.estimated_savings

        # Calculate payback period
        payback_months = (
            implementation_cost / monthly_savings
            if monthly_savings > 0
            else float("inf")
        )

        # Calculate 1-year ROI
        annual_savings = monthly_savings * 12
        roi_percentage = (
            ((annual_savings - implementation_cost) / implementation_cost * 100)
            if implementation_cost > 0
            else float("inf")
        )

        # Risk-adjusted ROI
        risk_multiplier = self._get_risk_multiplier(optimization.risk_level)
        risk_adjusted_roi = roi_percentage * risk_multiplier

        return {
            "optimization_id": optimization.optimization_id,
            "monthly_savings": monthly_savings,
            "annual_savings": annual_savings,
            "implementation_cost": implementation_cost,
            "payback_months": payback_months,
            "roi_percentage": roi_percentage,
            "risk_adjusted_roi": risk_adjusted_roi,
            "recommendation": self._get_roi_recommendation(
                roi_percentage, payback_months
            ),
        }

    async def get_cost_forecast(
        self, forecast_months: int = 12, include_optimizations: bool = True
    ) -> Dict[str, Any]:
        """Get cost forecast with and without optimizations.

        Args:
            forecast_months: Months to forecast
            include_optimizations: Include optimization impact

        Returns:
            Cost forecast
        """
        # Calculate current monthly spend
        current_monthly = self._calculate_current_monthly_spend()

        # Project baseline costs
        baseline_forecast = []
        optimized_forecast = []

        for month in range(forecast_months):
            # Apply growth assumptions
            growth_factor = 1 + (0.05 * month / 12)  # 5% annual growth
            baseline_cost = current_monthly * growth_factor
            baseline_forecast.append(baseline_cost)

            # Apply optimizations if requested
            if include_optimizations:
                total_savings = sum(opt.estimated_savings for opt in self.optimizations)
                optimized_cost = baseline_cost - total_savings
                optimized_forecast.append(max(0, optimized_cost))
            else:
                optimized_forecast.append(baseline_cost)

        total_baseline = sum(baseline_forecast)
        total_optimized = sum(optimized_forecast)
        total_savings = total_baseline - total_optimized

        return {
            "forecast_months": forecast_months,
            "current_monthly_spend": current_monthly,
            "baseline_forecast": baseline_forecast,
            "optimized_forecast": optimized_forecast if include_optimizations else None,
            "total_baseline_cost": total_baseline,
            "total_optimized_cost": total_optimized,
            "total_projected_savings": total_savings,
            "savings_percentage": (
                (total_savings / total_baseline * 100) if total_baseline > 0 else 0
            ),
        }

    async def _optimization_loop(self):
        """Background optimization loop."""
        while True:
            try:
                await asyncio.sleep(self.optimization_interval)

                # Run automatic optimization
                optimizations = await self.optimize_costs()

                if optimizations:
                    self.logger.info(
                        f"Found {len(optimizations)} cost optimization opportunities"
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Optimization loop error: {e}")

    def _initialize_pricing_data(self):
        """Initialize default pricing data for providers."""
        # Simplified pricing data - in production, this would come from APIs
        self.provider_pricing = {
            CloudProvider.AWS.value: {
                "cpu": {
                    "on_demand": 0.10,  # per vCPU hour
                    "spot": 0.03,
                    "reserved_1yr": 0.07,
                    "reserved_3yr": 0.05,
                },
                "memory": {
                    "on_demand": 0.01,  # per GB hour
                    "spot": 0.003,
                    "reserved_1yr": 0.007,
                    "reserved_3yr": 0.005,
                },
                "storage": {"on_demand": 0.10, "reserved": 0.08},  # per GB month
            },
            CloudProvider.GCP.value: {
                "cpu": {
                    "on_demand": 0.09,
                    "preemptible": 0.025,
                    "committed_1yr": 0.065,
                    "committed_3yr": 0.045,
                },
                "memory": {
                    "on_demand": 0.009,
                    "preemptible": 0.0025,
                    "committed_1yr": 0.0065,
                    "committed_3yr": 0.0045,
                },
            },
            CloudProvider.AZURE.value: {
                "cpu": {
                    "on_demand": 0.11,
                    "spot": 0.035,
                    "reserved_1yr": 0.075,
                    "reserved_3yr": 0.055,
                },
                "memory": {
                    "on_demand": 0.011,
                    "spot": 0.0035,
                    "reserved_1yr": 0.0075,
                    "reserved_3yr": 0.0055,
                },
            },
        }

    def _get_all_edge_nodes(self) -> List[str]:
        """Get all edge nodes from cost metrics."""
        return list(set(metric.edge_node for metric in self.cost_metrics))

    def _analyze_node_costs(self, edge_node: str) -> Dict[str, Any]:
        """Analyze costs for a specific edge node."""
        node_metrics = [m for m in self.cost_metrics if m.edge_node == edge_node]

        if not node_metrics:
            return {}

        # Group by resource type and instance type
        cost_breakdown = defaultdict(lambda: defaultdict(float))

        for metric in node_metrics:
            key = f"{metric.resource_type}_{metric.instance_type.value}"
            cost_breakdown[metric.resource_type][
                metric.instance_type.value
            ] += metric.total_cost

        # Calculate totals
        total_cost = sum(
            sum(instance_costs.values()) for instance_costs in cost_breakdown.values()
        )

        return {
            "edge_node": edge_node,
            "total_cost": total_cost,
            "cost_breakdown": dict(cost_breakdown),
            "metrics_count": len(node_metrics),
            "last_updated": max(m.timestamp for m in node_metrics),
        }

    async def _optimize_node_costs(
        self,
        edge_node: str,
        current_costs: Dict[str, Any],
        strategy: OptimizationStrategy,
    ) -> List[CostOptimization]:
        """Optimize costs for a specific node."""
        optimizations = []

        # Analyze each resource type
        for resource_type, instance_costs in current_costs["cost_breakdown"].items():
            # Check for spot instance opportunities
            spot_opt = await self._check_spot_optimization(
                edge_node, resource_type, instance_costs, strategy
            )
            if spot_opt:
                optimizations.append(spot_opt)

            # Check for reserved instance opportunities
            reserved_opt = await self._check_reserved_optimization(
                edge_node, resource_type, instance_costs, strategy
            )
            if reserved_opt:
                optimizations.append(reserved_opt)

            # Check for right-sizing opportunities
            rightsizing_opt = await self._check_rightsizing_optimization(
                edge_node, resource_type, instance_costs, strategy
            )
            if rightsizing_opt:
                optimizations.append(rightsizing_opt)

        return optimizations

    async def _check_spot_optimization(
        self,
        edge_node: str,
        resource_type: str,
        instance_costs: Dict[str, float],
        strategy: OptimizationStrategy,
    ) -> Optional[CostOptimization]:
        """Check for spot instance optimization opportunities."""
        on_demand_cost = instance_costs.get("on_demand", 0)

        if on_demand_cost == 0:
            return None

        # Get spot pricing
        spot_cost = on_demand_cost * 0.3  # Assume 70% savings
        potential_savings = on_demand_cost - spot_cost

        # Check if savings meet threshold
        savings_percentage = potential_savings / on_demand_cost * 100

        if savings_percentage < self.savings_threshold * 100:
            return None

        # Assess risk based on workload characteristics
        interruption_risk = self._assess_interruption_risk(edge_node, resource_type)

        # Strategy-based risk tolerance
        if strategy == OptimizationStrategy.RISK_AVERSE and interruption_risk > 0.3:
            return None

        if (
            strategy == OptimizationStrategy.PREDICTABLE_COST
            and interruption_risk > 0.1
        ):
            return None

        return CostOptimization(
            optimization_id=f"spot_{edge_node}_{resource_type}_{datetime.now().timestamp()}",
            edge_node=edge_node,
            current_setup={
                "instance_type": "on_demand",
                "cost": on_demand_cost,
                "resource_type": resource_type,
            },
            recommended_setup={
                "instance_type": "spot",
                "cost": spot_cost,
                "resource_type": resource_type,
                "interruption_risk": interruption_risk,
            },
            estimated_savings=potential_savings,
            savings_percentage=savings_percentage,
            confidence=0.8,
            implementation_effort="low",
            risk_level="medium" if interruption_risk > 0.2 else "low",
            reasoning=[
                f"Spot instances offer {savings_percentage:.1f}% cost savings",
                f"Interruption risk is {interruption_risk:.1%}",
                "Workload appears suitable for spot instances",
            ],
        )

    async def _check_reserved_optimization(
        self,
        edge_node: str,
        resource_type: str,
        instance_costs: Dict[str, float],
        strategy: OptimizationStrategy,
    ) -> Optional[CostOptimization]:
        """Check for reserved instance optimization opportunities."""
        on_demand_cost = instance_costs.get("on_demand", 0)

        if on_demand_cost == 0:
            return None

        # Calculate usage consistency
        usage_consistency = self._calculate_usage_consistency(edge_node, resource_type)

        # Reserved instances only make sense for consistent usage
        if usage_consistency < 0.7:
            return None

        # Calculate reserved cost (assume 30% savings for 1-year)
        reserved_cost = on_demand_cost * 0.7
        potential_savings = on_demand_cost - reserved_cost
        savings_percentage = potential_savings / on_demand_cost * 100

        if savings_percentage < self.savings_threshold * 100:
            return None

        return CostOptimization(
            optimization_id=f"reserved_{edge_node}_{resource_type}_{datetime.now().timestamp()}",
            edge_node=edge_node,
            current_setup={
                "instance_type": "on_demand",
                "cost": on_demand_cost,
                "resource_type": resource_type,
            },
            recommended_setup={
                "instance_type": "reserved_1yr",
                "cost": reserved_cost,
                "resource_type": resource_type,
                "commitment": "1 year",
            },
            estimated_savings=potential_savings,
            savings_percentage=savings_percentage,
            confidence=0.9,
            implementation_effort="low",
            risk_level="low",
            reasoning=[
                f"Reserved instances offer {savings_percentage:.1f}% cost savings",
                f"Usage consistency is {usage_consistency:.1%}",
                "1-year commitment recommended based on usage patterns",
            ],
        )

    async def _check_rightsizing_optimization(
        self,
        edge_node: str,
        resource_type: str,
        instance_costs: Dict[str, float],
        strategy: OptimizationStrategy,
    ) -> Optional[CostOptimization]:
        """Check for right-sizing optimization opportunities."""
        # Analyze actual resource utilization
        utilization = self._get_resource_utilization(edge_node, resource_type)

        if utilization is None or utilization > 0.8:  # Well utilized
            return None

        # Calculate right-sized cost
        utilization_factor = max(utilization * 1.2, 0.5)  # 20% buffer, minimum 50%
        current_cost = sum(instance_costs.values())
        rightsized_cost = current_cost * utilization_factor
        potential_savings = current_cost - rightsized_cost
        savings_percentage = potential_savings / current_cost * 100

        if savings_percentage < self.savings_threshold * 100:
            return None

        # Risk assessment
        risk_level = "low" if utilization < 0.5 else "medium"

        return CostOptimization(
            optimization_id=f"rightsize_{edge_node}_{resource_type}_{datetime.now().timestamp()}",
            edge_node=edge_node,
            current_setup={
                "instance_type": "current",
                "cost": current_cost,
                "resource_type": resource_type,
                "utilization": utilization,
            },
            recommended_setup={
                "instance_type": "rightsized",
                "cost": rightsized_cost,
                "resource_type": resource_type,
                "target_utilization": utilization_factor,
            },
            estimated_savings=potential_savings,
            savings_percentage=savings_percentage,
            confidence=0.7,
            implementation_effort="medium",
            risk_level=risk_level,
            reasoning=[
                f"Current utilization is only {utilization:.1%}",
                f"Right-sizing can save {savings_percentage:.1f}%",
                "Recommend gradual capacity reduction with monitoring",
            ],
        )

    def _assess_interruption_risk(self, edge_node: str, resource_type: str) -> float:
        """Assess interruption risk for spot instances."""
        # Simplified risk assessment
        # In production, this would analyze historical interruption data

        base_risk = 0.15  # 15% base interruption risk

        # Adjust based on resource type
        if resource_type == "gpu":
            base_risk *= 1.5  # GPUs have higher interruption risk
        elif resource_type == "memory":
            base_risk *= 0.8  # Memory instances more stable

        # Adjust based on time patterns
        # Assume we have access to usage patterns
        peak_usage = self._is_peak_usage_time()
        if peak_usage:
            base_risk *= 1.3

        return min(base_risk, 0.5)  # Cap at 50%

    def _calculate_usage_consistency(self, edge_node: str, resource_type: str) -> float:
        """Calculate usage consistency for reserved instance evaluation."""
        # Analyze usage patterns over time
        node_metrics = [
            m
            for m in self.cost_metrics
            if m.edge_node == edge_node and m.resource_type == resource_type
        ]

        if len(node_metrics) < 7:  # Need at least a week of data
            return 0.0

        # Calculate daily usage
        daily_usage = defaultdict(float)
        for metric in node_metrics:
            day = metric.timestamp.date()
            daily_usage[day] += metric.usage_hours

        usage_values = list(daily_usage.values())

        if not usage_values:
            return 0.0

        # Calculate coefficient of variation
        mean_usage = np.mean(usage_values)
        std_usage = np.std(usage_values)

        if mean_usage == 0:
            return 0.0

        cv = std_usage / mean_usage
        consistency = max(0, 1 - cv)  # Lower CV = higher consistency

        return consistency

    def _get_resource_utilization(
        self, edge_node: str, resource_type: str
    ) -> Optional[float]:
        """Get average resource utilization."""
        # This would integrate with monitoring data
        # For now, return simulated utilization

        import random

        random.seed(hash(f"{edge_node}_{resource_type}"))
        return random.uniform(0.3, 0.9)

    def _is_peak_usage_time(self) -> bool:
        """Check if current time is peak usage."""
        hour = datetime.now().hour
        # Assume peak hours are 9 AM to 6 PM
        return 9 <= hour <= 18

    async def _analyze_spot_opportunity(
        self, edge_node: str, current_costs: Dict[str, Any]
    ) -> Optional[SpotInstanceRecommendation]:
        """Analyze spot instance opportunity for a node."""
        total_on_demand = sum(
            costs.get("on_demand", 0)
            for costs in current_costs["cost_breakdown"].values()
        )

        if total_on_demand == 0:
            return None

        # Calculate potential spot savings
        spot_cost = total_on_demand * 0.3  # 70% savings
        potential_savings = total_on_demand - spot_cost

        # Assess interruption risk
        interruption_risk = self._assess_interruption_risk(edge_node, "mixed")

        # Determine strategy
        if interruption_risk < 0.1:
            strategy = "full_spot"
        elif interruption_risk < 0.3:
            strategy = "mixed_spot_on_demand"
        else:
            strategy = "diversified_spot"

        # Create backup plan
        backup_plan = {
            "strategy": "auto_fallback",
            "fallback_instances": "on_demand",
            "max_interruptions_per_day": 2,
            "auto_restart": True,
        }

        return SpotInstanceRecommendation(
            edge_node=edge_node,
            current_on_demand_cost=total_on_demand,
            spot_cost=spot_cost,
            potential_savings=potential_savings,
            interruption_risk=interruption_risk,
            recommended_strategy=strategy,
            backup_plan=backup_plan,
        )

    def _analyze_provider_usage(
        self, provider: CloudProvider
    ) -> Dict[str, Dict[str, Any]]:
        """Analyze usage patterns for a provider."""
        provider_metrics = [m for m in self.cost_metrics if m.provider == provider]

        usage_patterns = defaultdict(
            lambda: {"total_hours": 0, "consistency": 0, "monthly_cost": 0}
        )

        for metric in provider_metrics:
            patterns = usage_patterns[metric.resource_type]
            patterns["total_hours"] += metric.usage_hours
            patterns["monthly_cost"] += metric.total_cost

        return dict(usage_patterns)

    async def _analyze_reservation_opportunity(
        self, provider: CloudProvider, resource_type: str, usage: Dict[str, Any]
    ) -> Optional[ReservationRecommendation]:
        """Analyze reservation opportunity for a resource."""
        monthly_hours = usage["total_hours"]
        monthly_cost = usage["monthly_cost"]

        # Need significant usage to justify reservation
        if monthly_hours < 500:  # Less than ~70% of month
            return None

        # Calculate reservation costs
        hourly_rate = monthly_cost / monthly_hours if monthly_hours > 0 else 0

        # 1-year reservation (30% savings)
        reserved_hourly = hourly_rate * 0.7
        upfront_cost = hourly_rate * monthly_hours * 0.3  # 30% upfront
        monthly_reserved_cost = reserved_hourly * monthly_hours

        total_savings = (monthly_cost - monthly_reserved_cost) * 12
        breakeven_months = (
            upfront_cost / (monthly_cost - monthly_reserved_cost)
            if monthly_cost > monthly_reserved_cost
            else 12
        )

        if total_savings <= 0 or breakeven_months > 12:
            return None

        return ReservationRecommendation(
            resource_type=resource_type,
            provider=provider,
            commitment_length=12,
            upfront_cost=upfront_cost,
            monthly_cost=monthly_reserved_cost,
            on_demand_equivalent=monthly_cost,
            total_savings=total_savings,
            breakeven_months=int(breakeven_months),
            utilization_requirement=0.7,
        )

    def _get_risk_multiplier(self, risk_level: str) -> float:
        """Get risk multiplier for ROI calculations."""
        multipliers = {"low": 0.95, "medium": 0.85, "high": 0.7}
        return multipliers.get(risk_level, 0.85)

    def _get_roi_recommendation(
        self, roi_percentage: float, payback_months: float
    ) -> str:
        """Get ROI-based recommendation."""
        if roi_percentage > 100 and payback_months < 6:
            return "Strongly Recommended"
        elif roi_percentage > 50 and payback_months < 12:
            return "Recommended"
        elif roi_percentage > 20 and payback_months < 18:
            return "Consider"
        else:
            return "Not Recommended"

    def _calculate_current_monthly_spend(self) -> float:
        """Calculate current monthly spend."""
        # Get last 30 days of metrics
        cutoff = datetime.now() - timedelta(days=30)
        recent_metrics = [m for m in self.cost_metrics if m.timestamp > cutoff]

        return sum(m.total_cost for m in recent_metrics)

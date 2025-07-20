"""Resource analyzer node for intelligent resource management.

This node integrates resource analysis capabilities into workflows,
providing insights into resource usage patterns and bottlenecks.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from kailash.edge.resource.resource_analyzer import (
    Bottleneck,
    ResourceAnalyzer,
    ResourceMetric,
    ResourcePattern,
    ResourceType,
)
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode


@register_node()
class ResourceAnalyzerNode(AsyncNode):
    """Node for resource analysis and optimization operations.

    This node provides comprehensive resource analysis capabilities including
    pattern identification, bottleneck detection, and optimization recommendations.

    Example:
        >>> # Record resource metric
        >>> result = await analyzer_node.execute_async(
        ...     operation="record_metric",
        ...     edge_node="edge-west-1",
        ...     resource_type="cpu",
        ...     used=2.5,
        ...     total=4.0
        ... )

        >>> # Analyze resources
        >>> result = await analyzer_node.execute_async(
        ...     operation="analyze",
        ...     include_patterns=True,
        ...     include_bottlenecks=True
        ... )

        >>> # Get trends
        >>> result = await analyzer_node.execute_async(
        ...     operation="get_trends",
        ...     edge_node="edge-west-1",
        ...     duration_minutes=60
        ... )

        >>> # Get recommendations
        >>> result = await analyzer_node.execute_async(
        ...     operation="get_recommendations"
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize resource analyzer node."""
        super().__init__(**kwargs)

        # Extract configuration
        history_window = kwargs.get("history_window", 3600)
        analysis_interval = kwargs.get("analysis_interval", 60)
        anomaly_threshold = kwargs.get("anomaly_threshold", 2.5)
        pattern_confidence_threshold = kwargs.get("pattern_confidence_threshold", 0.7)

        # Initialize analyzer
        self.analyzer = ResourceAnalyzer(
            history_window=history_window,
            analysis_interval=analysis_interval,
            anomaly_threshold=anomaly_threshold,
            pattern_confidence_threshold=pattern_confidence_threshold,
        )

        self._analyzer_started = False

    @property
    def input_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation to perform (record_metric, analyze, get_trends, get_recommendations, start_analyzer, stop_analyzer)",
            ),
            # For record_metric
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
                description="Type of resource (cpu, memory, gpu, storage, network)",
            ),
            "used": NodeParameter(
                name="used",
                type=float,
                required=False,
                description="Amount of resource used",
            ),
            "available": NodeParameter(
                name="available",
                type=float,
                required=False,
                description="Amount of resource available",
            ),
            "total": NodeParameter(
                name="total",
                type=float,
                required=False,
                description="Total resource capacity",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                default={},
                description="Additional metric metadata",
            ),
            # For analyze
            "include_patterns": NodeParameter(
                name="include_patterns",
                type=bool,
                required=False,
                default=True,
                description="Include pattern analysis",
            ),
            "include_bottlenecks": NodeParameter(
                name="include_bottlenecks",
                type=bool,
                required=False,
                default=True,
                description="Include bottleneck detection",
            ),
            "include_anomalies": NodeParameter(
                name="include_anomalies",
                type=bool,
                required=False,
                default=True,
                description="Include anomaly detection",
            ),
            # For get_trends
            "duration_minutes": NodeParameter(
                name="duration_minutes",
                type=int,
                required=False,
                default=60,
                description="Duration for trend analysis",
            ),
            # Configuration
            "history_window": NodeParameter(
                name="history_window",
                type=int,
                required=False,
                default=3600,
                description="Time window for analysis (seconds)",
            ),
            "analysis_interval": NodeParameter(
                name="analysis_interval",
                type=int,
                required=False,
                default=60,
                description="Interval between analyses (seconds)",
            ),
            "anomaly_threshold": NodeParameter(
                name="anomaly_threshold",
                type=float,
                required=False,
                default=2.5,
                description="Threshold for anomaly detection (std devs)",
            ),
            "pattern_confidence_threshold": NodeParameter(
                name="pattern_confidence_threshold",
                type=float,
                required=False,
                default=0.7,
                description="Minimum confidence for patterns",
            ),
        }

    @property
    def output_parameters(self) -> Dict[str, NodeParameter]:
        """Define output parameters."""
        return {
            "status": NodeParameter(
                name="status", type=str, description="Operation status"
            ),
            "patterns": NodeParameter(
                name="patterns",
                type=list,
                required=False,
                description="Identified resource patterns",
            ),
            "bottlenecks": NodeParameter(
                name="bottlenecks",
                type=list,
                required=False,
                description="Detected bottlenecks",
            ),
            "anomalies": NodeParameter(
                name="anomalies",
                type=list,
                required=False,
                description="Detected anomalies",
            ),
            "trends": NodeParameter(
                name="trends",
                type=dict,
                required=False,
                description="Resource usage trends",
            ),
            "recommendations": NodeParameter(
                name="recommendations",
                type=list,
                required=False,
                description="Optimization recommendations",
            ),
            "analysis_summary": NodeParameter(
                name="analysis_summary",
                type=dict,
                required=False,
                description="Analysis summary",
            ),
            "metric_recorded": NodeParameter(
                name="metric_recorded",
                type=bool,
                required=False,
                description="Whether metric was recorded",
            ),
            "analyzer_active": NodeParameter(
                name="analyzer_active",
                type=bool,
                required=False,
                description="Whether analyzer is active",
            ),
        }

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get all node parameters for compatibility."""
        return self.input_parameters

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute resource analysis operation."""
        operation = kwargs["operation"]

        try:
            if operation == "record_metric":
                return await self._record_metric(kwargs)
            elif operation == "analyze":
                return await self._analyze_resources(kwargs)
            elif operation == "get_trends":
                return await self._get_trends(kwargs)
            elif operation == "get_recommendations":
                return await self._get_recommendations()
            elif operation == "start_analyzer":
                return await self._start_analyzer()
            elif operation == "stop_analyzer":
                return await self._stop_analyzer()
            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            self.logger.error(f"Resource analysis operation failed: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def _record_metric(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Record a resource metric."""
        # Parse resource type
        resource_type_str = kwargs.get("resource_type", "cpu")
        try:
            resource_type = ResourceType(resource_type_str)
        except ValueError:
            resource_type = ResourceType.CUSTOM

        # Create metric
        metric = ResourceMetric(
            timestamp=datetime.now(),
            edge_node=kwargs.get("edge_node", "unknown"),
            resource_type=resource_type,
            used=kwargs.get("used", 0.0),
            available=kwargs.get(
                "available", kwargs.get("total", 0.0) - kwargs.get("used", 0.0)
            ),
            total=kwargs.get("total", 0.0),
            metadata=kwargs.get("metadata", {}),
        )

        # Record metric
        await self.analyzer.record_metric(metric)

        return {
            "status": "success",
            "metric_recorded": True,
            "metric": metric.to_dict(),
        }

    async def _analyze_resources(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Perform resource analysis."""
        # Run analysis
        analysis = await self.analyzer.analyze_resources()

        # Filter results based on parameters
        result = {"status": "success"}

        if kwargs.get("include_patterns", True):
            result["patterns"] = analysis["patterns"]

        if kwargs.get("include_bottlenecks", True):
            result["bottlenecks"] = analysis["bottlenecks"]

        if kwargs.get("include_anomalies", True):
            result["anomalies"] = analysis["anomalies"]

        result["analysis_summary"] = analysis["summary"]

        return result

    async def _get_trends(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get resource trends."""
        # Parse parameters
        edge_node = kwargs.get("edge_node")
        resource_type_str = kwargs.get("resource_type")
        duration_minutes = kwargs.get("duration_minutes", 60)

        # Parse resource type if provided
        resource_type = None
        if resource_type_str:
            try:
                resource_type = ResourceType(resource_type_str)
            except ValueError:
                pass

        # Get trends
        trends = await self.analyzer.get_resource_trends(
            edge_node=edge_node,
            resource_type=resource_type,
            duration_minutes=duration_minutes,
        )

        return {"status": "success", "trends": trends, "trend_count": len(trends)}

    async def _get_recommendations(self) -> Dict[str, Any]:
        """Get optimization recommendations."""
        recommendations = await self.analyzer.get_optimization_recommendations()

        return {
            "status": "success",
            "recommendations": recommendations,
            "recommendation_count": len(recommendations),
        }

    async def _start_analyzer(self) -> Dict[str, Any]:
        """Start background analyzer."""
        if not self._analyzer_started:
            await self.analyzer.start()
            self._analyzer_started = True

        return {"status": "success", "analyzer_active": True}

    async def _stop_analyzer(self) -> Dict[str, Any]:
        """Stop background analyzer."""
        if self._analyzer_started:
            await self.analyzer.stop()
            self._analyzer_started = False

        return {"status": "success", "analyzer_active": False}

    async def cleanup(self):
        """Clean up resources."""
        if self._analyzer_started:
            await self.analyzer.stop()

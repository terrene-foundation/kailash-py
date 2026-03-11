"""DataFlow Monitoring Integration - SDK Enterprise Components.

This module provides DataFlow-specific monitoring nodes that leverage the
Kailash SDK's enterprise monitoring components for comprehensive observability,
performance tracking, and anomaly detection.
"""

import asyncio
from typing import Any, Dict, List, Optional

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode

# Import SDK monitoring components
from kailash.nodes.monitoring import (
    ConnectionDashboardNode,
    DeadlockDetectorNode,
    HealthCheckNode,
    MetricsCollectorNode,
    PerformanceAnomalyNode,
    PerformanceBenchmarkNode,
    RaceConditionDetectorNode,
    TransactionMetricsNode,
    TransactionMonitorNode,
)
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


@register_node()
class DataFlowTransactionMetricsNode(AsyncNode):
    """DataFlow Transaction Metrics Node leveraging SDK TransactionMetricsNode.

    Provides comprehensive transaction monitoring for DataFlow bulk operations
    with SDK enterprise monitoring capabilities.
    """

    def __init__(self, **kwargs):
        """Initialize with SDK TransactionMetricsNode integration."""
        # Extract DataFlow-specific configuration
        self.table_name = kwargs.pop("table_name", None)
        self.operation_type = kwargs.pop("operation_type", "bulk_operation")
        self.threshold_config = kwargs.pop("threshold_config", {})

        # Initialize parent first to get self.id
        super().__init__(**kwargs)

        # Initialize SDK TransactionMetricsNode with minimal parameters
        self.metrics_node = TransactionMetricsNode(node_id=f"{self.id}_metrics")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define DataFlow transaction metrics parameters."""
        return {
            "transaction_data": NodeParameter(
                name="transaction_data",
                type=dict,
                required=True,
                description="Transaction data to collect metrics for",
                auto_map_from=["data", "transaction", "operation_data"],
            ),
            "operation_type": NodeParameter(
                name="operation_type",
                type=str,
                required=False,
                default="bulk_operation",
                description="Type of DataFlow operation (bulk_create, bulk_update, etc.)",
            ),
            "table_name": NodeParameter(
                name="table_name",
                type=str,
                required=False,
                description="Database table being operated on",
            ),
            "performance_thresholds": NodeParameter(
                name="performance_thresholds",
                type=dict,
                required=False,
                default={},
                description="Performance thresholds for alerts",
            ),
            "enable_alerts": NodeParameter(
                name="enable_alerts",
                type=bool,
                required=False,
                default=True,
                description="Enable performance alerts",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Collect transaction metrics using SDK monitoring."""
        try:
            # Validate inputs
            validated_inputs = self.validate_inputs(**kwargs)

            transaction_data = validated_inputs.get("transaction_data", {})
            operation_type = validated_inputs.get("operation_type", self.operation_type)
            table_name = validated_inputs.get("table_name", self.table_name)
            thresholds = validated_inputs.get(
                "performance_thresholds", self.threshold_config
            )
            enable_alerts = validated_inputs.get("enable_alerts", True)

            # Prepare SDK metrics input
            metrics_input = {
                "transaction_id": transaction_data.get(
                    "transaction_id", f"dataflow_{operation_type}"
                ),
                "operation_type": operation_type,
                "start_time": transaction_data.get("start_time"),
                "end_time": transaction_data.get("end_time"),
                "duration": transaction_data.get("duration", 0),
                "records_processed": transaction_data.get("records_processed", 0),
                "success_count": transaction_data.get("success_count", 0),
                "failure_count": transaction_data.get("failure_count", 0),
                "table_name": table_name,
                "thresholds": thresholds,
            }

            # Execute SDK transaction metrics collection
            sdk_result = await self.metrics_node.async_run(**metrics_input)

            # Enhance with DataFlow-specific metrics
            dataflow_metrics = {
                "dataflow_operation": operation_type,
                "table": table_name,
                "bulk_performance": {
                    "records_per_second": (
                        transaction_data.get("records_processed", 0)
                        / max(transaction_data.get("duration", 1), 0.001)
                    ),
                    "success_rate": (
                        transaction_data.get("success_count", 0)
                        / max(transaction_data.get("records_processed", 1), 1)
                    ),
                    "batch_efficiency": transaction_data.get("batch_efficiency", 1.0),
                },
                "performance_grade": self._calculate_performance_grade(
                    transaction_data, thresholds
                ),
            }

            # Combine SDK and DataFlow results
            result = {
                "success": True,
                "sdk_metrics": sdk_result,
                "dataflow_metrics": dataflow_metrics,
                "operation_summary": {
                    "operation": operation_type,
                    "table": table_name,
                    "total_records": transaction_data.get("records_processed", 0),
                    "duration_seconds": transaction_data.get("duration", 0),
                    "performance_grade": dataflow_metrics["performance_grade"],
                },
            }

            # Add alerts if enabled and thresholds exceeded
            if enable_alerts:
                alerts = self._check_performance_alerts(transaction_data, thresholds)
                if alerts:
                    result["alerts"] = alerts

            return result

        except Exception as e:
            raise NodeExecutionError(
                f"DataFlow transaction metrics collection failed: {str(e)}"
            )

    def _calculate_performance_grade(
        self, transaction_data: Dict[str, Any], thresholds: Dict[str, Any]
    ) -> str:
        """Calculate performance grade based on metrics."""
        records_per_sec = transaction_data.get("records_processed", 0) / max(
            transaction_data.get("duration", 1), 0.001
        )
        success_rate = transaction_data.get("success_count", 0) / max(
            transaction_data.get("records_processed", 1), 1
        )

        target_rps = thresholds.get("target_records_per_second", 1000)
        min_success_rate = thresholds.get("min_success_rate", 0.95)

        if records_per_sec >= target_rps and success_rate >= min_success_rate:
            return "A"
        elif (
            records_per_sec >= target_rps * 0.8
            and success_rate >= min_success_rate * 0.9
        ):
            return "B"
        elif (
            records_per_sec >= target_rps * 0.6
            and success_rate >= min_success_rate * 0.8
        ):
            return "C"
        else:
            return "D"

    def _check_performance_alerts(
        self, transaction_data: Dict[str, Any], thresholds: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Check for performance threshold violations."""
        alerts = []

        records_per_sec = transaction_data.get("records_processed", 0) / max(
            transaction_data.get("duration", 1), 0.001
        )
        success_rate = transaction_data.get("success_count", 0) / max(
            transaction_data.get("records_processed", 1), 1
        )

        # Performance alerts
        if (
            "min_records_per_second" in thresholds
            and records_per_sec < thresholds["min_records_per_second"]
        ):
            alerts.append(
                {
                    "type": "performance",
                    "severity": "warning",
                    "message": f"Low throughput: {records_per_sec:.2f} records/sec (threshold: {thresholds['min_records_per_second']})",
                }
            )

        if (
            "min_success_rate" in thresholds
            and success_rate < thresholds["min_success_rate"]
        ):
            alerts.append(
                {
                    "type": "reliability",
                    "severity": "critical",
                    "message": f"Low success rate: {success_rate:.2%} (threshold: {thresholds['min_success_rate']:.2%})",
                }
            )

        if (
            "max_duration" in thresholds
            and transaction_data.get("duration", 0) > thresholds["max_duration"]
        ):
            alerts.append(
                {
                    "type": "performance",
                    "severity": "warning",
                    "message": f"Long execution time: {transaction_data.get('duration')}s (threshold: {thresholds['max_duration']}s)",
                }
            )

        return alerts


@register_node()
class DataFlowDeadlockDetectorNode(AsyncNode):
    """DataFlow Deadlock Detector leveraging SDK DeadlockDetectorNode.

    Provides deadlock detection and prevention for DataFlow database operations.
    """

    def __init__(self, **kwargs):
        """Initialize with SDK DeadlockDetectorNode integration."""
        # Extract DataFlow-specific configuration
        self.connection_string = kwargs.pop("connection_string", None)
        self.database_type = kwargs.pop("database_type", "postgresql")

        # Initialize parent
        super().__init__(**kwargs)

        # Initialize SDK DeadlockDetectorNode with minimal parameters
        self.deadlock_detector = DeadlockDetectorNode(node_id=f"{self.id}_detector")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define deadlock detection parameters."""
        return {
            "database_config": NodeParameter(
                name="database_config",
                type=dict,
                required=True,
                description="Database connection configuration",
            ),
            "detection_config": NodeParameter(
                name="detection_config",
                type=dict,
                required=False,
                default={},
                description="Deadlock detection configuration",
            ),
            "monitoring_interval": NodeParameter(
                name="monitoring_interval",
                type=int,
                required=False,
                default=30,
                description="Monitoring interval in seconds",
            ),
            "auto_resolve": NodeParameter(
                name="auto_resolve",
                type=bool,
                required=False,
                default=True,
                description="Automatically attempt to resolve deadlocks",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute deadlock detection using SDK monitoring."""
        try:
            # Validate inputs
            validated_inputs = self.validate_inputs(**kwargs)

            database_config = validated_inputs.get("database_config", {})
            detection_config = validated_inputs.get("detection_config", {})
            monitoring_interval = validated_inputs.get("monitoring_interval", 30)
            auto_resolve = validated_inputs.get("auto_resolve", True)

            # Prepare SDK input with DataFlow database context
            sdk_input = {
                "database_type": database_config.get(
                    "database_type", self.database_type
                ),
                "connection_string": database_config.get(
                    "connection_string", self.connection_string
                ),
                "detection_interval": monitoring_interval,
                "auto_resolve": auto_resolve,
                "dataflow_context": {
                    "bulk_operations": True,
                    "high_concurrency": True,
                    "table_locks": detection_config.get("monitor_table_locks", True),
                },
            }

            # Execute SDK deadlock detection
            sdk_result = await self.deadlock_detector.async_run(**sdk_input)

            # Enhance with DataFlow-specific context
            result = {
                "success": True,
                "deadlock_status": sdk_result.get("status", "clear"),
                "detected_deadlocks": sdk_result.get("deadlocks", []),
                "resolution_actions": sdk_result.get("resolutions", []),
                "dataflow_recommendations": self._generate_dataflow_recommendations(
                    sdk_result
                ),
                "monitoring_config": {
                    "interval": monitoring_interval,
                    "auto_resolve": auto_resolve,
                    "database_type": database_config.get(
                        "database_type", self.database_type
                    ),
                },
            }

            return result

        except Exception as e:
            raise NodeExecutionError(f"DataFlow deadlock detection failed: {str(e)}")

    def _generate_dataflow_recommendations(
        self, sdk_result: Dict[str, Any]
    ) -> List[str]:
        """Generate DataFlow-specific recommendations based on deadlock analysis."""
        recommendations = []

        if sdk_result.get("deadlocks"):
            recommendations.extend(
                [
                    "Consider reducing batch size to minimize lock contention",
                    "Implement exponential backoff in bulk operations",
                    "Use connection pooling to manage concurrent connections",
                    "Consider table-level partitioning for high-volume operations",
                ]
            )

        if sdk_result.get("lock_wait_time", 0) > 10:
            recommendations.append(
                "Review transaction isolation levels for bulk operations"
            )

        return recommendations


@register_node()
class DataFlowPerformanceAnomalyNode(AsyncNode):
    """DataFlow Performance Anomaly Detection leveraging SDK PerformanceAnomalyNode."""

    def __init__(self, **kwargs):
        """Initialize with SDK PerformanceAnomalyNode integration."""
        # Extract DataFlow-specific configuration
        self.baseline_config = kwargs.pop("baseline_config", {})

        # Initialize parent
        super().__init__(**kwargs)

        # Initialize SDK PerformanceAnomalyNode with minimal parameters
        self.anomaly_detector = PerformanceAnomalyNode(node_id=f"{self.id}_anomaly")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define performance anomaly detection parameters."""
        return {
            "performance_data": NodeParameter(
                name="performance_data",
                type=dict,
                required=True,
                description="Performance metrics data to analyze",
            ),
            "baseline_metrics": NodeParameter(
                name="baseline_metrics",
                type=dict,
                required=False,
                default={},
                description="Baseline performance metrics for comparison",
            ),
            "anomaly_threshold": NodeParameter(
                name="anomaly_threshold",
                type=float,
                required=False,
                default=2.0,
                description="Standard deviations for anomaly detection",
            ),
            "detection_window": NodeParameter(
                name="detection_window",
                type=int,
                required=False,
                default=100,
                description="Number of recent operations to analyze",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute performance anomaly detection using SDK monitoring."""
        try:
            # Validate inputs
            validated_inputs = self.validate_inputs(**kwargs)

            performance_data = validated_inputs.get("performance_data", {})
            baseline_metrics = validated_inputs.get(
                "baseline_metrics", self.baseline_config
            )
            threshold = validated_inputs.get("anomaly_threshold", 2.0)
            window = validated_inputs.get("detection_window", 100)

            # Prepare SDK input
            sdk_input = {
                "metrics": performance_data,
                "baseline": baseline_metrics,
                "threshold": threshold,
                "window_size": window,
                "dataflow_specific": {
                    "bulk_operation_context": True,
                    "database_metrics": True,
                },
            }

            # Execute SDK anomaly detection
            sdk_result = await self.anomaly_detector.async_run(**sdk_input)

            # Enhance with DataFlow-specific analysis
            result = {
                "success": True,
                "anomaly_detected": sdk_result.get("anomaly_detected", False),
                "anomaly_score": sdk_result.get("anomaly_score", 0.0),
                "anomalies": sdk_result.get("anomalies", []),
                "dataflow_analysis": self._analyze_dataflow_anomalies(
                    performance_data, sdk_result
                ),
                "recommendations": self._generate_performance_recommendations(
                    sdk_result
                ),
            }

            return result

        except Exception as e:
            raise NodeExecutionError(
                f"DataFlow performance anomaly detection failed: {str(e)}"
            )

    def _analyze_dataflow_anomalies(
        self, performance_data: Dict[str, Any], sdk_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze anomalies in DataFlow context."""
        analysis = {
            "bulk_operation_anomalies": [],
            "database_performance_issues": [],
            "connection_pool_anomalies": [],
        }

        for anomaly in sdk_result.get("anomalies", []):
            metric_type = anomaly.get("metric", "")

            if "records_per_second" in metric_type or "throughput" in metric_type:
                analysis["bulk_operation_anomalies"].append(
                    {
                        "metric": metric_type,
                        "severity": anomaly.get("severity", "medium"),
                        "description": "Bulk operation throughput anomaly detected",
                    }
                )
            elif "connection" in metric_type or "pool" in metric_type:
                analysis["connection_pool_anomalies"].append(
                    {
                        "metric": metric_type,
                        "severity": anomaly.get("severity", "medium"),
                        "description": "Connection pool performance anomaly",
                    }
                )
            else:
                analysis["database_performance_issues"].append(
                    {
                        "metric": metric_type,
                        "severity": anomaly.get("severity", "medium"),
                        "description": "Database performance anomaly",
                    }
                )

        return analysis

    def _generate_performance_recommendations(
        self, sdk_result: Dict[str, Any]
    ) -> List[str]:
        """Generate performance improvement recommendations."""
        recommendations = []

        if sdk_result.get("anomaly_detected", False):
            recommendations.extend(
                [
                    "Review recent bulk operation configurations",
                    "Check database connection pool settings",
                    "Monitor system resource utilization",
                    "Consider adjusting batch sizes for optimal performance",
                ]
            )

        anomaly_score = sdk_result.get("anomaly_score", 0.0)
        if anomaly_score > 3.0:
            recommendations.append("Consider immediate performance investigation")
        elif anomaly_score > 2.0:
            recommendations.append("Schedule performance review")

        return recommendations


@register_node()
class DataFlowComprehensiveMonitoringNode(AsyncNode):
    """Comprehensive DataFlow monitoring leveraging multiple SDK monitoring nodes."""

    def __init__(self, **kwargs):
        """Initialize comprehensive monitoring with all SDK components."""
        # Initialize parent
        super().__init__(**kwargs)

        # Initialize all SDK monitoring components with minimal parameters
        self.transaction_metrics = DataFlowTransactionMetricsNode(
            node_id=f"{self.id}_tx_metrics"
        )
        self.deadlock_detector = DataFlowDeadlockDetectorNode(
            node_id=f"{self.id}_deadlock"
        )
        self.anomaly_detector = DataFlowPerformanceAnomalyNode(
            node_id=f"{self.id}_anomaly"
        )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define comprehensive monitoring parameters."""
        return {
            "operation_data": NodeParameter(
                name="operation_data",
                type=dict,
                required=True,
                description="Complete operation data for monitoring",
            ),
            "database_config": NodeParameter(
                name="database_config",
                type=dict,
                required=True,
                description="Database configuration for monitoring",
            ),
            "monitoring_config": NodeParameter(
                name="monitoring_config",
                type=dict,
                required=False,
                default={},
                description="Comprehensive monitoring configuration",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute comprehensive monitoring using all SDK components."""
        try:
            # Validate inputs
            validated_inputs = self.validate_inputs(**kwargs)

            operation_data = validated_inputs.get("operation_data", {})
            database_config = validated_inputs.get("database_config", {})
            monitoring_config = validated_inputs.get("monitoring_config", {})

            # Execute all monitoring components in parallel
            monitoring_tasks = []

            # Transaction metrics
            if monitoring_config.get("enable_transaction_metrics", True):
                monitoring_tasks.append(
                    self.transaction_metrics.async_run(
                        transaction_data=operation_data,
                        performance_thresholds=monitoring_config.get(
                            "performance_thresholds", {}
                        ),
                    )
                )

            # Deadlock detection
            if monitoring_config.get("enable_deadlock_detection", True):
                monitoring_tasks.append(
                    self.deadlock_detector.async_run(
                        database_config=database_config,
                        detection_config=monitoring_config.get("deadlock_config", {}),
                    )
                )

            # Performance anomaly detection
            if monitoring_config.get("enable_anomaly_detection", True):
                monitoring_tasks.append(
                    self.anomaly_detector.async_run(
                        performance_data=operation_data.get("performance_metrics", {}),
                        baseline_metrics=monitoring_config.get("baseline_metrics", {}),
                    )
                )

            # Execute all monitoring tasks
            results = await asyncio.gather(*monitoring_tasks, return_exceptions=True)

            # Compile comprehensive monitoring report
            monitoring_report = {
                "success": True,
                "monitoring_timestamp": operation_data.get("timestamp"),
                "operation_summary": {
                    "operation": operation_data.get("operation_type", "unknown"),
                    "table": operation_data.get("table_name", "unknown"),
                    "records_processed": operation_data.get("records_processed", 0),
                    "duration": operation_data.get("duration", 0),
                },
                "monitoring_results": {},
                "overall_health": "healthy",
                "alerts": [],
                "recommendations": [],
            }

            # Process results
            result_names = [
                "transaction_metrics",
                "deadlock_detection",
                "anomaly_detection",
            ]
            for i, result in enumerate(results):
                if i < len(result_names) and not isinstance(result, Exception):
                    monitoring_report["monitoring_results"][result_names[i]] = result

                    # Collect alerts and recommendations
                    if isinstance(result, dict):
                        if "alerts" in result:
                            monitoring_report["alerts"].extend(result["alerts"])
                        if "recommendations" in result:
                            monitoring_report["recommendations"].extend(
                                result["recommendations"]
                            )

                        # Update overall health
                        if result.get("anomaly_detected"):
                            monitoring_report["overall_health"] = "warning"
                        if (
                            result.get("deadlock_status")
                            and result.get("deadlock_status") != "clear"
                        ):
                            monitoring_report["overall_health"] = "warning"

            # Deduplicate recommendations
            monitoring_report["recommendations"] = list(
                set(monitoring_report["recommendations"])
            )

            return monitoring_report

        except Exception as e:
            raise NodeExecutionError(
                f"Comprehensive DataFlow monitoring failed: {str(e)}"
            )


# Register nodes for easy import
__all__ = [
    "DataFlowTransactionMetricsNode",
    "DataFlowDeadlockDetectorNode",
    "DataFlowPerformanceAnomalyNode",
    "DataFlowComprehensiveMonitoringNode",
]

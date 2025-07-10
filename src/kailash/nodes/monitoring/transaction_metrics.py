"""Transaction metrics collection and analysis node.

This module provides comprehensive transaction performance monitoring with
support for timing, aggregation, and export to various monitoring backends.
"""

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


class MetricExportFormat(Enum):
    """Supported metric export formats."""

    JSON = "json"
    PROMETHEUS = "prometheus"
    CLOUDWATCH = "cloudwatch"
    DATADOG = "datadog"
    OPENTELEMETRY = "opentelemetry"


class AggregationType(Enum):
    """Types of metric aggregation."""

    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    P50 = "p50"
    P75 = "p75"
    P90 = "p90"
    P95 = "p95"
    P99 = "p99"
    P999 = "p999"


@dataclass
class TransactionMetric:
    """Represents a single transaction metric."""

    transaction_id: str
    name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    status: str = "pending"
    error: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    custom_metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class AggregatedMetrics:
    """Aggregated transaction metrics."""

    name: str
    count: int
    sum_duration: float
    min_duration: float
    max_duration: float
    avg_duration: float
    percentiles: Dict[str, float]
    success_count: int
    error_count: int
    error_rate: float
    tags: Dict[str, str] = field(default_factory=dict)


@register_node()
class TransactionMetricsNode(AsyncNode):
    """Node for collecting and analyzing transaction performance metrics.

    This node provides comprehensive transaction monitoring including:
    - Transaction timing and duration tracking
    - Success/failure rate monitoring
    - Latency percentile calculations (p50, p95, p99)
    - Custom metric collection
    - Multi-format export (Prometheus, CloudWatch, DataDog)
    - Real-time and batch aggregation

    Design Purpose:
    - Enable production-grade performance monitoring
    - Support SLA tracking and alerting
    - Facilitate performance troubleshooting
    - Integrate with enterprise monitoring systems

    Examples:
        >>> # Track individual transaction
        >>> metrics_node = TransactionMetricsNode()
        >>> result = await metrics_node.execute(
        ...     operation="start_transaction",
        ...     transaction_id="txn_12345",
        ...     name="order_processing",
        ...     tags={"region": "us-west", "customer_tier": "premium"}
        ... )

        >>> # Complete transaction with metrics
        >>> result = await metrics_node.execute(
        ...     operation="end_transaction",
        ...     transaction_id="txn_12345",
        ...     status="success",
        ...     custom_metrics={"items_processed": 25, "db_queries": 3}
        ... )

        >>> # Get aggregated metrics
        >>> result = await metrics_node.execute(
        ...     operation="get_aggregated",
        ...     metric_names=["order_processing"],
        ...     aggregation_window=300,  # 5 minutes
        ...     export_format="prometheus"
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize the transaction metrics node."""
        super().__init__(**kwargs)
        self._active_transactions: Dict[str, TransactionMetric] = {}
        self._completed_transactions: List[TransactionMetric] = []
        self._metric_buffer = defaultdict(list)
        self._last_aggregation_time = time.time()
        self.logger.info(f"Initialized TransactionMetricsNode: {self.id}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation to perform (start_transaction, end_transaction, get_metrics, get_aggregated)",
            ),
            "transaction_id": NodeParameter(
                name="transaction_id",
                type=str,
                required=False,
                description="Unique transaction identifier",
            ),
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                description="Transaction/metric name",
            ),
            "status": NodeParameter(
                name="status",
                type=str,
                required=False,
                default="success",
                description="Transaction status (success, error, timeout)",
            ),
            "error": NodeParameter(
                name="error",
                type=str,
                required=False,
                description="Error message if transaction failed",
            ),
            "tags": NodeParameter(
                name="tags",
                type=dict,
                required=False,
                default={},
                description="Tags for metric grouping and filtering",
            ),
            "custom_metrics": NodeParameter(
                name="custom_metrics",
                type=dict,
                required=False,
                default={},
                description="Custom metrics to attach to transaction",
            ),
            "metric_names": NodeParameter(
                name="metric_names",
                type=list,
                required=False,
                default=[],
                description="List of metric names to retrieve",
            ),
            "aggregation_window": NodeParameter(
                name="aggregation_window",
                type=float,
                required=False,
                default=60.0,
                description="Time window for aggregation in seconds",
            ),
            "aggregation_types": NodeParameter(
                name="aggregation_types",
                type=list,
                required=False,
                default=["count", "avg", "p50", "p95", "p99"],
                description="Types of aggregation to perform",
            ),
            "export_format": NodeParameter(
                name="export_format",
                type=str,
                required=False,
                default="json",
                description="Export format (json, prometheus, cloudwatch, datadog, opentelemetry)",
            ),
            "include_raw": NodeParameter(
                name="include_raw",
                type=bool,
                required=False,
                default=False,
                description="Include raw transaction data in response",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node."""
        return {
            "metrics": NodeParameter(
                name="metrics",
                type=Any,
                description="Transaction metrics in requested format",
            ),
            "transaction_count": NodeParameter(
                name="transaction_count",
                type=int,
                description="Number of transactions processed",
            ),
            "total_transactions": NodeParameter(
                name="total_transactions",
                type=int,
                description="Total number of transactions (alias for transaction_count)",
            ),
            "success_rate": NodeParameter(
                name="success_rate",
                type=float,
                description="Success rate of transactions (0.0 to 1.0)",
            ),
            "aggregations": NodeParameter(
                name="aggregations", type=dict, description="Aggregated metric data"
            ),
            "export_format": NodeParameter(
                name="export_format", type=str, description="Format of exported metrics"
            ),
            "timestamp": NodeParameter(
                name="timestamp", type=str, description="ISO timestamp of operation"
            ),
            "status": NodeParameter(
                name="status", type=str, description="Operation status"
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute transaction metrics operation."""
        operation = kwargs.get("operation")

        try:
            if operation == "start_transaction":
                return await self._start_transaction(**kwargs)
            elif operation == "end_transaction":
                return await self._end_transaction(**kwargs)
            elif operation == "complete_transaction":
                return await self._end_transaction(**kwargs)  # Same as end_transaction
            elif operation == "get_metrics":
                return await self._get_metrics(**kwargs)
            elif operation == "get_aggregated":
                return await self._get_aggregated_metrics(**kwargs)
            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            self.logger.error(f"Transaction metrics operation failed: {str(e)}")
            raise NodeExecutionError(f"Failed to process transaction metrics: {str(e)}")

    async def _start_transaction(self, **kwargs) -> Dict[str, Any]:
        """Start tracking a new transaction."""
        transaction_id = kwargs.get("transaction_id")
        if not transaction_id:
            raise ValueError("transaction_id is required for start_transaction")

        name = kwargs.get("name", "unnamed_transaction")
        tags = kwargs.get("tags", {})

        # Create new transaction metric
        metric = TransactionMetric(
            transaction_id=transaction_id,
            name=name,
            start_time=time.time(),
            tags=tags,
            status="in_progress",
        )

        self._active_transactions[transaction_id] = metric

        self.logger.debug(f"Started transaction {transaction_id} ({name})")

        return {
            "metrics": {"transaction_id": transaction_id, "status": "started"},
            "transaction_count": 1,
            "total_transactions": 1,  # Alias for backward compatibility
            "success_rate": 1.0,  # Starting transaction is optimistically successful
            "aggregations": {},
            "export_format": "json",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _end_transaction(self, **kwargs) -> Dict[str, Any]:
        """Complete a transaction and record metrics."""
        transaction_id = kwargs.get("transaction_id")
        if not transaction_id:
            raise ValueError("transaction_id is required for end_transaction")

        if transaction_id not in self._active_transactions:
            raise ValueError(f"Transaction {transaction_id} not found")

        metric = self._active_transactions.pop(transaction_id)

        # Update transaction metrics
        metric.end_time = time.time()
        metric.duration = metric.end_time - metric.start_time
        metric.status = kwargs.get("status", "success")
        metric.error = kwargs.get("error")
        metric.custom_metrics = kwargs.get("custom_metrics", {})

        # Store completed transaction
        self._completed_transactions.append(metric)
        self._metric_buffer[metric.name].append(metric)

        # Clean old metrics from buffer (keep last hour)
        cutoff_time = time.time() - 3600
        self._completed_transactions = [
            m for m in self._completed_transactions if m.start_time > cutoff_time
        ]

        self.logger.debug(
            f"Completed transaction {transaction_id} ({metric.name}) "
            f"in {metric.duration:.3f}s with status {metric.status}"
        )

        return {
            "metrics": {
                "transaction_id": transaction_id,
                "duration": metric.duration,
                "status": metric.status,
            },
            "transaction_count": 1,
            "total_transactions": 1,  # Alias for backward compatibility
            "success_rate": (
                1.0 if metric.status == "success" else 0.0
            ),  # Based on this transaction
            "aggregations": {},
            "export_format": "json",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _get_metrics(self, **kwargs) -> Dict[str, Any]:
        """Get raw transaction metrics."""
        metric_names = kwargs.get("metric_names", [])
        include_raw = kwargs.get("include_raw", False)
        export_format = MetricExportFormat(kwargs.get("export_format", "json"))

        # Filter metrics by name if specified
        if metric_names:
            filtered_metrics = [
                m for m in self._completed_transactions if m.name in metric_names
            ]
        else:
            filtered_metrics = self._completed_transactions

        # Calculate success rate
        total_metrics = len(filtered_metrics)
        successful_metrics = len([m for m in filtered_metrics if m.status == "success"])
        success_rate = successful_metrics / total_metrics if total_metrics > 0 else 1.0

        # Format output
        if export_format == MetricExportFormat.JSON:
            if include_raw:
                metrics_data = [self._serialize_metric(m) for m in filtered_metrics]
            else:
                metrics_data = {
                    "transaction_count": len(filtered_metrics),
                    "metric_names": list(set(m.name for m in filtered_metrics)),
                    "success_rate": success_rate,
                }
        else:
            metrics_data = self._format_metrics(filtered_metrics, export_format)

        return {
            "metrics": metrics_data,
            "transaction_count": len(filtered_metrics),
            "total_transactions": len(
                filtered_metrics
            ),  # Alias for backward compatibility
            "success_rate": success_rate,  # Add success rate to top level
            "aggregations": {},
            "export_format": export_format.value,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _get_aggregated_metrics(self, **kwargs) -> Dict[str, Any]:
        """Get aggregated transaction metrics."""
        metric_names = kwargs.get("metric_names", [])
        aggregation_window = kwargs.get("aggregation_window", 60.0)
        aggregation_types = kwargs.get(
            "aggregation_types", ["count", "avg", "p50", "p95", "p99"]
        )
        export_format = MetricExportFormat(kwargs.get("export_format", "json"))

        # Calculate time window
        current_time = time.time()
        window_start = current_time - aggregation_window

        # Aggregate metrics by name
        aggregations = {}

        for name, metrics in self._metric_buffer.items():
            if metric_names and name not in metric_names:
                continue

            # Filter metrics within window
            window_metrics = [
                m
                for m in metrics
                if m.start_time >= window_start and m.duration is not None
            ]

            if not window_metrics:
                continue

            # Calculate aggregations
            aggregations[name] = self._calculate_aggregations(
                window_metrics, aggregation_types
            )

        # Convert aggregations to JSON-serializable format first
        serialized_aggregations = {}
        for name, agg in aggregations.items():
            serialized_aggregations[name] = {
                "name": agg.name,
                "count": agg.count,
                "sum_duration": agg.sum_duration,
                "min_duration": agg.min_duration,
                "max_duration": agg.max_duration,
                "avg_duration": agg.avg_duration,
                "percentiles": agg.percentiles,
                "success_count": agg.success_count,
                "error_count": agg.error_count,
                "error_rate": agg.error_rate,
                "tags": agg.tags,
            }

        # Format output
        if export_format == MetricExportFormat.JSON:
            formatted_metrics = serialized_aggregations
        else:
            formatted_metrics = self._format_aggregated_metrics(
                aggregations, export_format
            )

        transaction_count = (
            sum(agg.count for agg in aggregations.values()) if aggregations else 0
        )

        # Calculate overall success rate from aggregations
        total_success = (
            sum(agg.success_count for agg in aggregations.values())
            if aggregations
            else 0
        )
        success_rate = (
            total_success / transaction_count if transaction_count > 0 else 1.0
        )

        return {
            "metrics": formatted_metrics,
            "transaction_count": transaction_count,
            "total_transactions": transaction_count,  # Alias for backward compatibility
            "success_rate": success_rate,  # Calculated from aggregations
            "aggregations": serialized_aggregations,
            "export_format": export_format.value,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    def _calculate_aggregations(
        self, metrics: List[TransactionMetric], aggregation_types: List[str]
    ) -> AggregatedMetrics:
        """Calculate aggregated metrics from transaction list."""
        if not metrics:
            return None

        durations = [m.duration for m in metrics if m.duration is not None]
        if not durations:
            return None

        # Sort durations for percentile calculations
        sorted_durations = sorted(durations)

        # Basic statistics
        count = len(metrics)
        sum_duration = sum(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        avg_duration = sum_duration / count

        # Success/error counts
        success_count = sum(1 for m in metrics if m.status == "success")
        error_count = count - success_count
        error_rate = error_count / count if count > 0 else 0.0

        # Calculate percentiles
        percentiles = {}
        percentile_mappings = {
            "p50": 50,
            "p75": 75,
            "p90": 90,
            "p95": 95,
            "p99": 99,
            "p999": 99.9,
        }

        for agg_type in aggregation_types:
            if agg_type in percentile_mappings:
                percentile = percentile_mappings[agg_type]
                index = int(len(sorted_durations) * (percentile / 100.0))
                index = min(index, len(sorted_durations) - 1)
                percentiles[agg_type] = sorted_durations[index]

        # Aggregate tags (use most common values)
        tag_counts = defaultdict(lambda: defaultdict(int))
        for metric in metrics:
            for tag_key, tag_value in metric.tags.items():
                tag_counts[tag_key][tag_value] += 1

        aggregated_tags = {}
        for tag_key, value_counts in tag_counts.items():
            # Use most common tag value
            most_common = max(value_counts.items(), key=lambda x: x[1])
            aggregated_tags[tag_key] = most_common[0]

        return AggregatedMetrics(
            name=metrics[0].name,
            count=count,
            sum_duration=sum_duration,
            min_duration=min_duration,
            max_duration=max_duration,
            avg_duration=avg_duration,
            percentiles=percentiles,
            success_count=success_count,
            error_count=error_count,
            error_rate=error_rate,
            tags=aggregated_tags,
        )

    def _serialize_metric(self, metric: TransactionMetric) -> Dict[str, Any]:
        """Serialize a transaction metric to dictionary."""
        return {
            "transaction_id": metric.transaction_id,
            "name": metric.name,
            "start_time": metric.start_time,
            "end_time": metric.end_time,
            "duration": metric.duration,
            "status": metric.status,
            "error": metric.error,
            "tags": metric.tags,
            "custom_metrics": metric.custom_metrics,
        }

    def _format_metrics(
        self, metrics: List[TransactionMetric], format: MetricExportFormat
    ) -> Union[str, Dict[str, Any]]:
        """Format metrics for export."""
        if format == MetricExportFormat.PROMETHEUS:
            return self._format_prometheus(metrics)
        elif format == MetricExportFormat.CLOUDWATCH:
            return self._format_cloudwatch(metrics)
        elif format == MetricExportFormat.DATADOG:
            return self._format_datadog(metrics)
        elif format == MetricExportFormat.OPENTELEMETRY:
            return self._format_opentelemetry(metrics)
        else:
            return [self._serialize_metric(m) for m in metrics]

    def _format_prometheus(self, metrics: List[TransactionMetric]) -> str:
        """Format metrics in Prometheus exposition format."""
        lines = []

        # Group by metric name
        by_name = defaultdict(list)
        for m in metrics:
            by_name[m.name].append(m)

        for name, metric_list in by_name.items():
            # Transaction duration histogram
            lines.append("# TYPE transaction_duration_seconds histogram")
            lines.append(
                "# HELP transaction_duration_seconds Transaction duration in seconds"
            )

            for metric in metric_list:
                if metric.duration is not None:
                    labels = self._format_prometheus_labels(metric.tags)
                    lines.append(
                        f'transaction_duration_seconds{{{labels},name="{name}"}} {metric.duration}'
                    )

            # Success/error counters
            success_count = sum(1 for m in metric_list if m.status == "success")
            error_count = len(metric_list) - success_count

            lines.append("# TYPE transaction_total counter")
            lines.append("# HELP transaction_total Total number of transactions")
            lines.append(
                f'transaction_total{{name="{name}",status="success"}} {success_count}'
            )
            lines.append(
                f'transaction_total{{name="{name}",status="error"}} {error_count}'
            )

        return "\n".join(lines)

    def _format_prometheus_labels(self, tags: Dict[str, str]) -> str:
        """Format tags as Prometheus labels."""
        label_parts = []
        for k, v in tags.items():
            # Escape quotes and backslashes
            v = v.replace("\\", "\\\\").replace('"', '\\"')
            label_parts.append(f'{k}="{v}"')
        return ",".join(label_parts)

    def _format_cloudwatch(self, metrics: List[TransactionMetric]) -> Dict[str, Any]:
        """Format metrics for AWS CloudWatch."""
        cloudwatch_metrics = []

        for metric in metrics:
            if metric.duration is not None:
                cw_metric = {
                    "MetricName": f"TransactionDuration_{metric.name}",
                    "Value": metric.duration * 1000,  # Convert to milliseconds
                    "Unit": "Milliseconds",
                    "Timestamp": datetime.fromtimestamp(
                        metric.start_time, UTC
                    ).isoformat(),
                    "Dimensions": [
                        {"Name": k, "Value": v} for k, v in metric.tags.items()
                    ],
                }
                cloudwatch_metrics.append(cw_metric)

                # Add custom metrics
                for custom_name, custom_value in metric.custom_metrics.items():
                    cw_custom = {
                        "MetricName": f"Custom_{metric.name}_{custom_name}",
                        "Value": custom_value,
                        "Unit": "Count",
                        "Timestamp": datetime.fromtimestamp(
                            metric.start_time, UTC
                        ).isoformat(),
                        "Dimensions": [
                            {"Name": k, "Value": v} for k, v in metric.tags.items()
                        ],
                    }
                    cloudwatch_metrics.append(cw_custom)

        return {"MetricData": cloudwatch_metrics}

    def _format_datadog(self, metrics: List[TransactionMetric]) -> Dict[str, Any]:
        """Format metrics for DataDog."""
        series = []

        for metric in metrics:
            if metric.duration is not None:
                # Duration metric
                dd_metric = {
                    "metric": "transaction.duration",
                    "points": [[int(metric.start_time), metric.duration]],
                    "type": "gauge",
                    "tags": [f"{k}:{v}" for k, v in metric.tags.items()]
                    + [f"transaction_name:{metric.name}"],
                }
                series.append(dd_metric)

                # Status counter
                status_metric = {
                    "metric": "transaction.count",
                    "points": [[int(metric.start_time), 1]],
                    "type": "count",
                    "tags": [f"{k}:{v}" for k, v in metric.tags.items()]
                    + [f"transaction_name:{metric.name}", f"status:{metric.status}"],
                }
                series.append(status_metric)

        return {"series": series}

    def _format_opentelemetry(self, metrics: List[TransactionMetric]) -> Dict[str, Any]:
        """Format metrics in OpenTelemetry format."""
        otel_metrics = []

        for metric in metrics:
            if metric.duration is not None:
                otel_metric = {
                    "name": "transaction.duration",
                    "description": f"Duration of {metric.name} transaction",
                    "unit": "s",
                    "data": {
                        "type": "Gauge",
                        "data_points": [
                            {
                                "attributes": {
                                    **metric.tags,
                                    "transaction.name": metric.name,
                                    "transaction.status": metric.status,
                                },
                                "time_unix_nano": int(metric.start_time * 1e9),
                                "value": metric.duration,
                            }
                        ],
                    },
                }
                otel_metrics.append(otel_metric)

        return {"resource_metrics": [{"scope_metrics": [{"metrics": otel_metrics}]}]}

    def _format_aggregated_metrics(
        self, aggregations: Dict[str, AggregatedMetrics], format: MetricExportFormat
    ) -> Union[str, Dict[str, Any]]:
        """Format aggregated metrics for export."""
        if format == MetricExportFormat.PROMETHEUS:
            lines = []

            for name, agg in aggregations.items():
                labels = self._format_prometheus_labels(agg.tags)
                base_labels = f'name="{name}"' + (f",{labels}" if labels else "")

                # Summary metrics
                lines.append("# TYPE transaction_duration_summary summary")
                lines.append(
                    f"transaction_duration_summary_count{{{base_labels}}} {agg.count}"
                )
                lines.append(
                    f"transaction_duration_summary_sum{{{base_labels}}} {agg.sum_duration}"
                )

                # Percentiles
                for percentile_name, value in agg.percentiles.items():
                    quantile = percentile_name[1:]  # Remove 'p' prefix
                    lines.append(
                        f'transaction_duration_summary{{{base_labels},quantile="0.{quantile}"}} {value}'
                    )

                # Error rate
                lines.append("# TYPE transaction_error_rate gauge")
                lines.append(
                    f"transaction_error_rate{{{base_labels}}} {agg.error_rate}"
                )

            return "\n".join(lines)

        else:
            # For other formats, return structured data
            return {
                name: {
                    "count": agg.count,
                    "duration": {
                        "sum": agg.sum_duration,
                        "min": agg.min_duration,
                        "max": agg.max_duration,
                        "avg": agg.avg_duration,
                        **agg.percentiles,
                    },
                    "success_count": agg.success_count,
                    "error_count": agg.error_count,
                    "error_rate": agg.error_rate,
                    "tags": agg.tags,
                }
                for name, agg in aggregations.items()
            }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous wrapper for compatibility."""
        import asyncio

        return asyncio.run(self.async_run(**kwargs))

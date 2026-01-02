"""Metrics collector node for system and application monitoring.

This module provides comprehensive metrics collection capabilities including
system metrics (CPU, memory, disk), application metrics, and custom metrics
with support for various output formats.
"""

import json
import logging
import os
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

import psutil
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


class MetricFormat(Enum):
    """Supported metric output formats."""

    JSON = "json"
    PROMETHEUS = "prometheus"
    OPENTELEMETRY = "opentelemetry"
    STATSD = "statsd"


class MetricType(Enum):
    """Types of metrics that can be collected."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@register_node()
class MetricsCollectorNode(AsyncNode):
    """Node for collecting system and application metrics.

    This node provides comprehensive metrics collection including:
    - System metrics: CPU, memory, disk, network usage
    - Process metrics: Resource usage for specific processes
    - Application metrics: Custom metrics from applications
    - Metric aggregation and buffering
    - Multiple output formats (JSON, Prometheus, OpenTelemetry)
    - Configurable collection intervals and filtering

    Design Purpose:
    - Provide unified metrics collection for monitoring
    - Support various monitoring backends
    - Enable performance tracking and alerting
    - Facilitate observability and debugging

    Examples:
        >>> # Collect system metrics
        >>> collector = MetricsCollectorNode()
        >>> result = await collector.execute(
        ...     metric_types=["system.cpu", "system.memory"],
        ...     format="prometheus"
        ... )

        >>> # Collect custom application metrics
        >>> result = await collector.execute(
        ...     custom_metrics=[
        ...         {"name": "requests_total", "type": "counter", "value": 1000},
        ...         {"name": "response_time", "type": "histogram", "value": 0.125}
        ...     ],
        ...     format="json"
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize the metrics collector node."""
        super().__init__(**kwargs)
        self.metric_buffer = []
        self.last_collection_time = None
        self.logger.info(f"Initialized MetricsCollectorNode: {self.id}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "metric_types": NodeParameter(
                name="metric_types",
                type=list,
                required=False,
                default=["system.cpu", "system.memory"],
                description="List of metric types to collect",
            ),
            "custom_metrics": NodeParameter(
                name="custom_metrics",
                type=list,
                required=False,
                default=[],
                description="Custom metrics to include",
            ),
            "format": NodeParameter(
                name="format",
                type=str,
                required=False,
                default="json",
                description="Output format (json, prometheus, opentelemetry, statsd)",
            ),
            "labels": NodeParameter(
                name="labels",
                type=dict,
                required=False,
                default={},
                description="Labels to add to all metrics",
            ),
            "include_process": NodeParameter(
                name="include_process",
                type=bool,
                required=False,
                default=True,
                description="Include current process metrics",
            ),
            "process_ids": NodeParameter(
                name="process_ids",
                type=list,
                required=False,
                default=[],
                description="Additional process IDs to monitor",
            ),
            "aggregate": NodeParameter(
                name="aggregate",
                type=bool,
                required=False,
                default=False,
                description="Aggregate metrics over time",
            ),
            "interval": NodeParameter(
                name="interval",
                type=float,
                required=False,
                default=60.0,
                description="Collection interval in seconds (for aggregation)",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node."""
        return {
            "metrics": NodeParameter(
                name="metrics",
                type=Any,  # Can be list or string depending on format
                description="Collected metrics in specified format",
            ),
            "metric_count": NodeParameter(
                name="metric_count",
                type=int,
                description="Number of metrics collected",
            ),
            "collection_time": NodeParameter(
                name="collection_time",
                type=float,
                description="Time taken to collect metrics",
            ),
            "timestamp": NodeParameter(
                name="timestamp",
                type=str,
                description="ISO timestamp of collection",
            ),
            "format": NodeParameter(
                name="format",
                type=str,
                description="Format of the metrics output",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Collect metrics based on configuration."""
        metric_types = kwargs.get("metric_types", ["system.cpu", "system.memory"])
        custom_metrics = kwargs.get("custom_metrics", [])
        output_format = MetricFormat(kwargs.get("format", "json"))
        labels = kwargs.get("labels", {})
        include_process = kwargs.get("include_process", True)
        process_ids = kwargs.get("process_ids", [])
        aggregate = kwargs.get("aggregate", False)
        interval = kwargs.get("interval", 60.0)

        start_time = time.time()
        collected_metrics = []

        try:
            # Collect system metrics
            if any(mt.startswith("system.") for mt in metric_types):
                system_metrics = await self._collect_system_metrics(metric_types)
                collected_metrics.extend(system_metrics)

            # Collect process metrics
            if include_process or process_ids:
                process_metrics = await self._collect_process_metrics(
                    include_current=include_process, process_ids=process_ids
                )
                collected_metrics.extend(process_metrics)

            # Add custom metrics
            if custom_metrics:
                validated_custom = self._validate_custom_metrics(custom_metrics)
                collected_metrics.extend(validated_custom)

            # Add labels to all metrics
            if labels:
                for metric in collected_metrics:
                    metric["labels"] = {**labels, **metric.get("labels", {})}

            # Handle aggregation if requested
            if aggregate:
                collected_metrics = self._aggregate_metrics(collected_metrics, interval)

            # Format output
            formatted_output = self._format_metrics(collected_metrics, output_format)

            collection_time = time.time() - start_time

            return {
                "metrics": formatted_output,
                "metric_count": len(collected_metrics),
                "collection_time": collection_time,
                "timestamp": datetime.now(UTC).isoformat(),
                "format": output_format.value,
            }

        except Exception as e:
            self.logger.error(f"Metrics collection failed: {str(e)}")
            raise NodeExecutionError(f"Failed to collect metrics: {str(e)}")

    async def _collect_system_metrics(
        self, metric_types: List[str]
    ) -> List[Dict[str, Any]]:
        """Collect system-level metrics."""
        metrics = []
        timestamp = time.time()

        # CPU metrics
        if "system.cpu" in metric_types or "system.cpu.percent" in metric_types:
            cpu_percent = psutil.cpu_percent(interval=0.1, percpu=True)
            metrics.append(
                {
                    "name": "system_cpu_usage_percent",
                    "type": MetricType.GAUGE.value,
                    "value": sum(cpu_percent) / len(cpu_percent),
                    "timestamp": timestamp,
                    "labels": {"total_cores": str(len(cpu_percent))},
                }
            )

            # Per-core metrics
            for i, percent in enumerate(cpu_percent):
                metrics.append(
                    {
                        "name": "system_cpu_core_usage_percent",
                        "type": MetricType.GAUGE.value,
                        "value": percent,
                        "timestamp": timestamp,
                        "labels": {"core": str(i)},
                    }
                )

        # Memory metrics
        if "system.memory" in metric_types:
            memory = psutil.virtual_memory()
            metrics.extend(
                [
                    {
                        "name": "system_memory_total_bytes",
                        "type": MetricType.GAUGE.value,
                        "value": memory.total,
                        "timestamp": timestamp,
                    },
                    {
                        "name": "system_memory_used_bytes",
                        "type": MetricType.GAUGE.value,
                        "value": memory.used,
                        "timestamp": timestamp,
                    },
                    {
                        "name": "system_memory_available_bytes",
                        "type": MetricType.GAUGE.value,
                        "value": memory.available,
                        "timestamp": timestamp,
                    },
                    {
                        "name": "system_memory_usage_percent",
                        "type": MetricType.GAUGE.value,
                        "value": memory.percent,
                        "timestamp": timestamp,
                    },
                ]
            )

        # Disk metrics
        if "system.disk" in metric_types:
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    metrics.extend(
                        [
                            {
                                "name": "system_disk_total_bytes",
                                "type": MetricType.GAUGE.value,
                                "value": usage.total,
                                "timestamp": timestamp,
                                "labels": {
                                    "device": partition.device,
                                    "mountpoint": partition.mountpoint,
                                },
                            },
                            {
                                "name": "system_disk_used_bytes",
                                "type": MetricType.GAUGE.value,
                                "value": usage.used,
                                "timestamp": timestamp,
                                "labels": {
                                    "device": partition.device,
                                    "mountpoint": partition.mountpoint,
                                },
                            },
                            {
                                "name": "system_disk_usage_percent",
                                "type": MetricType.GAUGE.value,
                                "value": usage.percent,
                                "timestamp": timestamp,
                                "labels": {
                                    "device": partition.device,
                                    "mountpoint": partition.mountpoint,
                                },
                            },
                        ]
                    )
                except PermissionError:
                    continue

        # Network metrics
        if "system.network" in metric_types:
            net_io = psutil.net_io_counters()
            metrics.extend(
                [
                    {
                        "name": "system_network_bytes_sent",
                        "type": MetricType.COUNTER.value,
                        "value": net_io.bytes_sent,
                        "timestamp": timestamp,
                    },
                    {
                        "name": "system_network_bytes_recv",
                        "type": MetricType.COUNTER.value,
                        "value": net_io.bytes_recv,
                        "timestamp": timestamp,
                    },
                    {
                        "name": "system_network_packets_sent",
                        "type": MetricType.COUNTER.value,
                        "value": net_io.packets_sent,
                        "timestamp": timestamp,
                    },
                    {
                        "name": "system_network_packets_recv",
                        "type": MetricType.COUNTER.value,
                        "value": net_io.packets_recv,
                        "timestamp": timestamp,
                    },
                ]
            )

        return metrics

    async def _collect_process_metrics(
        self, include_current: bool = True, process_ids: List[int] = None
    ) -> List[Dict[str, Any]]:
        """Collect process-level metrics."""
        metrics = []
        timestamp = time.time()

        pids_to_monitor = []
        if include_current:
            pids_to_monitor.append(os.getpid())
        if process_ids:
            pids_to_monitor.extend(process_ids)

        for pid in pids_to_monitor:
            try:
                process = psutil.Process(pid)

                # Process CPU usage
                cpu_percent = process.cpu_percent(interval=0.1)
                metrics.append(
                    {
                        "name": "process_cpu_usage_percent",
                        "type": MetricType.GAUGE.value,
                        "value": cpu_percent,
                        "timestamp": timestamp,
                        "labels": {
                            "pid": str(pid),
                            "name": process.name(),
                        },
                    }
                )

                # Process memory usage
                memory_info = process.memory_info()
                metrics.extend(
                    [
                        {
                            "name": "process_memory_rss_bytes",
                            "type": MetricType.GAUGE.value,
                            "value": memory_info.rss,
                            "timestamp": timestamp,
                            "labels": {
                                "pid": str(pid),
                                "name": process.name(),
                            },
                        },
                        {
                            "name": "process_memory_vms_bytes",
                            "type": MetricType.GAUGE.value,
                            "value": memory_info.vms,
                            "timestamp": timestamp,
                            "labels": {
                                "pid": str(pid),
                                "name": process.name(),
                            },
                        },
                    ]
                )

                # Process thread count
                metrics.append(
                    {
                        "name": "process_num_threads",
                        "type": MetricType.GAUGE.value,
                        "value": process.num_threads(),
                        "timestamp": timestamp,
                        "labels": {
                            "pid": str(pid),
                            "name": process.name(),
                        },
                    }
                )

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.logger.warning(f"Could not collect metrics for PID {pid}")
                continue

        return metrics

    def _validate_custom_metrics(
        self, custom_metrics: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate and normalize custom metrics."""
        validated = []
        timestamp = time.time()

        for metric in custom_metrics:
            # Validate required fields
            if "name" not in metric or "value" not in metric:
                self.logger.warning(f"Skipping invalid metric: {metric}")
                continue

            # Set defaults
            validated_metric = {
                "name": metric["name"],
                "type": metric.get("type", MetricType.GAUGE.value),
                "value": float(metric["value"]),
                "timestamp": metric.get("timestamp", timestamp),
                "labels": metric.get("labels", {}),
            }

            # Validate metric type
            try:
                MetricType(validated_metric["type"])
            except ValueError:
                validated_metric["type"] = MetricType.GAUGE.value

            validated.append(validated_metric)

        return validated

    def _aggregate_metrics(
        self, metrics: List[Dict[str, Any]], interval: float
    ) -> List[Dict[str, Any]]:
        """Aggregate metrics over time."""
        # Store metrics in buffer
        self.metric_buffer.extend(metrics)

        # Remove old metrics outside the interval window
        cutoff_time = time.time() - interval
        self.metric_buffer = [
            m for m in self.metric_buffer if m.get("timestamp", 0) > cutoff_time
        ]

        # Group metrics by name and labels
        aggregated = {}
        for metric in self.metric_buffer:
            key = (metric["name"], tuple(sorted(metric.get("labels", {}).items())))

            if key not in aggregated:
                aggregated[key] = {
                    "name": metric["name"],
                    "type": metric["type"],
                    "labels": metric.get("labels", {}),
                    "values": [],
                }

            aggregated[key]["values"].append(metric["value"])

        # Calculate aggregated values
        result = []
        for key, agg_metric in aggregated.items():
            values = agg_metric["values"]

            if agg_metric["type"] == MetricType.COUNTER.value:
                # For counters, use the latest value
                value = values[-1] if values else 0
            elif agg_metric["type"] == MetricType.GAUGE.value:
                # For gauges, use the average
                value = sum(values) / len(values) if values else 0
            else:
                # For histograms/summaries, return all values
                value = values

            result.append(
                {
                    "name": agg_metric["name"],
                    "type": agg_metric["type"],
                    "value": value,
                    "timestamp": time.time(),
                    "labels": agg_metric["labels"],
                    "sample_count": len(values),
                }
            )

        return result

    def _format_metrics(
        self, metrics: List[Dict[str, Any]], format: MetricFormat
    ) -> Union[List[Dict[str, Any]], str]:
        """Format metrics according to specified format."""
        if format == MetricFormat.JSON:
            return metrics

        elif format == MetricFormat.PROMETHEUS:
            lines = []
            for metric in metrics:
                # Build label string
                label_parts = []
                for k, v in metric.get("labels", {}).items():
                    label_parts.append(f'{k}="{v}"')
                label_str = "{" + ",".join(label_parts) + "}" if label_parts else ""

                # Format metric line
                if metric["type"] == MetricType.COUNTER.value:
                    lines.append(f"# TYPE {metric['name']} counter")
                elif metric["type"] == MetricType.GAUGE.value:
                    lines.append(f"# TYPE {metric['name']} gauge")

                lines.append(f"{metric['name']}{label_str} {metric['value']}")

            return "\n".join(lines)

        elif format == MetricFormat.OPENTELEMETRY:
            # OpenTelemetry JSON format
            otel_metrics = []
            for metric in metrics:
                otel_metric = {
                    "name": metric["name"],
                    "description": f"{metric['name']} metric",
                    "unit": "1",
                    "data": {
                        "data_points": [
                            {
                                "attributes": metric.get("labels", {}),
                                "time_unix_nano": int(metric["timestamp"] * 1e9),
                                "value": metric["value"],
                            }
                        ]
                    },
                }

                if metric["type"] == MetricType.COUNTER.value:
                    otel_metric["data"]["type"] = "Sum"
                    otel_metric["data"]["is_monotonic"] = True
                else:
                    otel_metric["data"]["type"] = "Gauge"

                otel_metrics.append(otel_metric)

            return json.dumps(
                {"resource_metrics": [{"scope_metrics": [{"metrics": otel_metrics}]}]}
            )

        elif format == MetricFormat.STATSD:
            lines = []
            for metric in metrics:
                # StatsD format: metric_name:value|type
                if metric["type"] == MetricType.COUNTER.value:
                    type_char = "c"
                elif metric["type"] == MetricType.GAUGE.value:
                    type_char = "g"
                else:
                    type_char = "ms"  # timing

                # Add tags if present
                tags = []
                for k, v in metric.get("labels", {}).items():
                    tags.append(f"{k}:{v}")
                tag_str = f"|#{','.join(tags)}" if tags else ""

                lines.append(f"{metric['name']}:{metric['value']}|{type_char}{tag_str}")

            return "\n".join(lines)

        else:
            raise ValueError(f"Unsupported format: {format}")

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous wrapper for compatibility."""
        import asyncio

        return asyncio.run(self.async_run(**kwargs))

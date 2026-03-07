"""Performance anomaly detection node with baseline learning and statistical analysis.

This module provides comprehensive performance anomaly detection capabilities with
baseline learning, statistical analysis, and classification of performance issues.
"""

import asyncio
import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    """Types of performance anomalies."""

    LATENCY_SPIKE = "latency_spike"
    THROUGHPUT_DROP = "throughput_drop"
    ERROR_RATE_INCREASE = "error_rate_increase"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    RESPONSE_TIME_VARIANCE = "response_time_variance"
    CONCURRENCY_ANOMALY = "concurrency_anomaly"
    TREND_ANOMALY = "trend_anomaly"


class AnomalySeverity(Enum):
    """Severity levels for anomalies."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DetectionMethod(Enum):
    """Anomaly detection methods."""

    STATISTICAL = "statistical"
    THRESHOLD_BASED = "threshold_based"
    ROLLING_AVERAGE = "rolling_average"
    ZSCORE = "zscore"
    IQR = "iqr"  # Interquartile Range
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    MACHINE_LEARNING = "machine_learning"


@dataclass
class PerformanceMetric:
    """Represents a performance metric data point."""

    metric_name: str
    value: float
    timestamp: float
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceBaseline:
    """Performance baseline for anomaly detection."""

    metric_name: str
    created_at: float
    updated_at: float
    sample_count: int

    # Statistical measures
    mean: float
    median: float
    std_dev: float
    min_value: float
    max_value: float
    percentiles: Dict[str, float] = field(default_factory=dict)

    # Trend analysis
    trend_slope: float = 0.0
    seasonal_pattern: List[float] = field(default_factory=list)

    # Detection thresholds
    upper_threshold: float = 0.0
    lower_threshold: float = 0.0
    variance_threshold: float = 0.0

    # Learning parameters
    learning_rate: float = 0.1
    decay_factor: float = 0.95


@dataclass
class PerformanceAnomaly:
    """Represents a detected performance anomaly."""

    anomaly_id: str
    anomaly_type: AnomalyType
    metric_name: str
    detected_at: float
    value: float
    expected_value: float
    deviation: float
    severity: AnomalySeverity
    confidence: float  # 0.0 to 1.0
    detection_method: DetectionMethod
    description: str
    impact_assessment: str
    recommended_actions: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@register_node()
class PerformanceAnomalyNode(AsyncNode):
    """Node for detecting performance anomalies using baseline learning.

    This node provides comprehensive performance anomaly detection including:
    - Baseline performance learning with adaptive algorithms
    - Statistical anomaly detection (Z-score, IQR, exponential smoothing)
    - Threshold-based anomaly detection with dynamic thresholds
    - Trend analysis and seasonal pattern detection
    - Anomaly classification with severity assessment
    - Real-time monitoring with configurable sensitivity
    - Integration with alerting systems

    Design Purpose:
    - Detect performance degradation before it impacts users
    - Learn normal performance patterns automatically
    - Provide actionable insights for performance optimization
    - Support proactive performance monitoring

    Examples:
        >>> # Initialize baseline learning
        >>> anomaly_detector = PerformanceAnomalyNode()
        >>> result = await anomaly_detector.execute(
        ...     operation="initialize_baseline",
        ...     metric_name="api_response_time",
        ...     detection_methods=["statistical", "threshold_based"],
        ...     sensitivity=0.7
        ... )

        >>> # Feed performance metrics
        >>> result = await anomaly_detector.execute(
        ...     operation="add_metric",
        ...     metric_name="api_response_time",
        ...     value=250.5,
        ...     tags={"endpoint": "/api/users", "method": "GET"}
        ... )

        >>> # Detect anomalies
        >>> result = await anomaly_detector.execute(
        ...     operation="detect_anomalies",
        ...     metric_names=["api_response_time"],
        ...     detection_window=300.0  # 5 minutes
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize the performance anomaly detector node."""
        super().__init__(**kwargs)
        self._baselines: Dict[str, PerformanceBaseline] = {}
        self._metrics_buffer: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=10000)
        )
        self._detected_anomalies: List[PerformanceAnomaly] = []
        self._monitoring_active = False
        self._background_tasks: set = set()
        self._detection_config = {
            "sensitivity": 0.8,
            "min_samples": 30,
            "learning_rate": 0.1,
            "zscore_threshold": 2.5,
            "iqr_multiplier": 1.5,
        }
        self.logger.info(f"Initialized PerformanceAnomalyNode: {self.id}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation (initialize_baseline, add_metric, detect_anomalies, get_baseline, get_anomalies, start_monitoring, stop_monitoring)",
            ),
            "metric_name": NodeParameter(
                name="metric_name",
                type=str,
                required=False,
                description="Name of the performance metric",
            ),
            "metric_names": NodeParameter(
                name="metric_names",
                type=list,
                required=False,
                default=[],
                description="List of metric names to process",
            ),
            "value": NodeParameter(
                name="value",
                type=float,
                required=False,
                description="Metric value to add",
            ),
            "timestamp": NodeParameter(
                name="timestamp",
                type=float,
                required=False,
                description="Timestamp for the metric (defaults to current time)",
            ),
            "tags": NodeParameter(
                name="tags",
                type=dict,
                required=False,
                default={},
                description="Tags for metric categorization",
            ),
            "detection_methods": NodeParameter(
                name="detection_methods",
                type=list,
                required=False,
                default=["statistical", "threshold_based"],
                description="Detection methods to use (statistical, threshold_based, rolling_average, zscore, iqr)",
            ),
            "sensitivity": NodeParameter(
                name="sensitivity",
                type=float,
                required=False,
                default=0.8,
                description="Detection sensitivity (0.0 to 1.0, higher = more sensitive)",
            ),
            "detection_window": NodeParameter(
                name="detection_window",
                type=float,
                required=False,
                default=300.0,
                description="Time window for anomaly detection in seconds",
            ),
            "min_samples": NodeParameter(
                name="min_samples",
                type=int,
                required=False,
                default=30,
                description="Minimum samples required for baseline learning",
            ),
            "learning_rate": NodeParameter(
                name="learning_rate",
                type=float,
                required=False,
                default=0.1,
                description="Learning rate for adaptive baseline updates",
            ),
            "zscore_threshold": NodeParameter(
                name="zscore_threshold",
                type=float,
                required=False,
                default=2.5,
                description="Z-score threshold for anomaly detection",
            ),
            "enable_monitoring": NodeParameter(
                name="enable_monitoring",
                type=bool,
                required=False,
                default=False,
                description="Enable continuous anomaly monitoring",
            ),
            "monitoring_interval": NodeParameter(
                name="monitoring_interval",
                type=float,
                required=False,
                default=30.0,
                description="Monitoring interval in seconds",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                default={},
                description="Additional metadata for the operation",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node."""
        return {
            "anomalies_detected": NodeParameter(
                name="anomalies_detected",
                type=list,
                description="List of detected anomalies",
            ),
            "anomaly_count": NodeParameter(
                name="anomaly_count",
                type=int,
                description="Number of anomalies detected",
            ),
            "baselines": NodeParameter(
                name="baselines", type=dict, description="Current performance baselines"
            ),
            "metrics_processed": NodeParameter(
                name="metrics_processed",
                type=int,
                description="Number of metrics processed",
            ),
            "detection_summary": NodeParameter(
                name="detection_summary",
                type=dict,
                description="Summary of detection results",
            ),
            "recommendations": NodeParameter(
                name="recommendations",
                type=list,
                description="Performance optimization recommendations",
            ),
            "monitoring_status": NodeParameter(
                name="monitoring_status",
                type=str,
                description="Current monitoring status",
            ),
            "timestamp": NodeParameter(
                name="timestamp", type=str, description="ISO timestamp of operation"
            ),
            "status": NodeParameter(
                name="status", type=str, description="Operation status"
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute performance anomaly detection operation."""
        operation = kwargs.get("operation")

        try:
            if operation == "initialize_baseline":
                return await self._initialize_baseline(**kwargs)
            elif operation == "add_metric":
                return await self._add_metric(**kwargs)
            elif operation == "detect_anomalies":
                return await self._detect_anomalies(**kwargs)
            elif operation == "get_baseline":
                return await self._get_baseline(**kwargs)
            elif operation == "get_anomalies":
                return await self._get_anomalies(**kwargs)
            elif operation == "start_monitoring":
                return await self._start_monitoring(**kwargs)
            elif operation == "stop_monitoring":
                return await self._stop_monitoring(**kwargs)
            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            self.logger.error(
                f"Performance anomaly detection operation failed: {str(e)}"
            )
            raise NodeExecutionError(f"Failed to execute anomaly detection: {str(e)}")

    async def _initialize_baseline(self, **kwargs) -> Dict[str, Any]:
        """Initialize baseline learning for a metric."""
        metric_name = kwargs.get("metric_name")
        if not metric_name:
            raise ValueError("metric_name is required for initialize_baseline")

        detection_methods = kwargs.get(
            "detection_methods", ["statistical", "threshold_based"]
        )
        sensitivity = kwargs.get("sensitivity", 0.8)
        min_samples = kwargs.get("min_samples", 30)
        learning_rate = kwargs.get("learning_rate", 0.1)

        # Update detection configuration
        self._detection_config.update(
            {
                "sensitivity": sensitivity,
                "min_samples": min_samples,
                "learning_rate": learning_rate,
            }
        )

        # Initialize baseline if it doesn't exist
        if metric_name not in self._baselines:
            current_time = time.time()
            baseline = PerformanceBaseline(
                metric_name=metric_name,
                created_at=current_time,
                updated_at=current_time,
                sample_count=0,
                mean=0.0,
                median=0.0,
                std_dev=0.0,
                min_value=float("inf"),
                max_value=float("-inf"),
                learning_rate=learning_rate,
            )
            self._baselines[metric_name] = baseline

        self.logger.info(f"Initialized baseline for metric: {metric_name}")

        return {
            "anomalies_detected": [],
            "anomaly_count": 0,
            "baselines": {
                metric_name: self._serialize_baseline(self._baselines[metric_name])
            },
            "metrics_processed": 0,
            "detection_summary": {"initialized": True, "methods": detection_methods},
            "recommendations": [],
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _add_metric(self, **kwargs) -> Dict[str, Any]:
        """Add a performance metric and update baseline."""
        metric_name = kwargs.get("metric_name")
        value = kwargs.get("value")
        timestamp = kwargs.get("timestamp", time.time())
        tags = kwargs.get("tags", {})
        metadata = kwargs.get("metadata", {})

        if not metric_name or value is None:
            raise ValueError("metric_name and value are required for add_metric")

        # Create metric object
        metric = PerformanceMetric(
            metric_name=metric_name,
            value=float(value),
            timestamp=timestamp,
            tags=tags,
            metadata=metadata,
        )

        # Add to buffer
        self._metrics_buffer[metric_name].append(metric)

        # Update baseline if it exists
        if metric_name in self._baselines:
            await self._update_baseline(metric_name, metric)

        # Check for immediate anomalies
        anomalies = []
        if metric_name in self._baselines:
            anomalies = await self._check_metric_anomalies(metric)

        self.logger.debug(f"Added metric {metric_name}={value} at {timestamp}")

        return {
            "anomalies_detected": [self._serialize_anomaly(a) for a in anomalies],
            "anomaly_count": len(anomalies),
            "baselines": {},
            "metrics_processed": 1,
            "detection_summary": {
                "immediate_check": True,
                "anomalies_found": len(anomalies),
            },
            "recommendations": [],
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _detect_anomalies(self, **kwargs) -> Dict[str, Any]:
        """Detect anomalies in performance metrics."""
        metric_names = kwargs.get("metric_names", [])
        detection_window = kwargs.get("detection_window", 300.0)
        detection_methods = kwargs.get(
            "detection_methods", ["statistical", "threshold_based"]
        )

        if not metric_names:
            metric_names = list(self._baselines.keys())

        current_time = time.time()
        window_start = current_time - detection_window

        all_anomalies = []
        detection_summary = {}

        for metric_name in metric_names:
            if metric_name not in self._baselines:
                continue

            # Get metrics within detection window
            recent_metrics = [
                m
                for m in self._metrics_buffer[metric_name]
                if m.timestamp >= window_start
            ]

            if not recent_metrics:
                continue

            # Apply different detection methods
            metric_anomalies = []
            for method in detection_methods:
                method_anomalies = await self._apply_detection_method(
                    metric_name, recent_metrics, DetectionMethod(method)
                )
                metric_anomalies.extend(method_anomalies)

            # Remove duplicates and merge similar anomalies
            unique_anomalies = self._deduplicate_anomalies(metric_anomalies)
            all_anomalies.extend(unique_anomalies)

            detection_summary[metric_name] = {
                "metrics_analyzed": len(recent_metrics),
                "anomalies_found": len(unique_anomalies),
                "methods_used": detection_methods,
            }

        # Store detected anomalies
        self._detected_anomalies.extend(all_anomalies)

        # Generate recommendations
        recommendations = self._generate_recommendations(all_anomalies)

        self.logger.info(
            f"Detected {len(all_anomalies)} anomalies across {len(metric_names)} metrics"
        )

        return {
            "anomalies_detected": [self._serialize_anomaly(a) for a in all_anomalies],
            "anomaly_count": len(all_anomalies),
            "baselines": {
                name: self._serialize_baseline(baseline)
                for name, baseline in self._baselines.items()
            },
            "metrics_processed": sum(
                s.get("metrics_analyzed", 0) for s in detection_summary.values()
            ),
            "detection_summary": detection_summary,
            "recommendations": recommendations,
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _update_baseline(self, metric_name: str, metric: PerformanceMetric):
        """Update baseline with new metric using adaptive learning."""
        baseline = self._baselines[metric_name]
        value = metric.value

        # Update sample count
        baseline.sample_count += 1

        # Update basic statistics using online algorithms
        if baseline.sample_count == 1:
            baseline.mean = value
            baseline.median = value
            baseline.min_value = value
            baseline.max_value = value
            baseline.std_dev = 0.0
        else:
            # Update mean using exponential moving average
            baseline.mean = (
                1 - baseline.learning_rate
            ) * baseline.mean + baseline.learning_rate * value

            # Update min/max
            baseline.min_value = min(baseline.min_value, value)
            baseline.max_value = max(baseline.max_value, value)

            # Update standard deviation using Welford's online algorithm
            if baseline.sample_count >= self._detection_config["min_samples"]:
                recent_metrics = list(self._metrics_buffer[metric_name])[
                    -self._detection_config["min_samples"] :
                ]
                values = [m.value for m in recent_metrics]
                baseline.std_dev = float(np.std(values))
                baseline.median = float(np.median(values))

                # Calculate percentiles
                baseline.percentiles = {
                    "p50": float(np.percentile(values, 50)),
                    "p90": float(np.percentile(values, 90)),
                    "p95": float(np.percentile(values, 95)),
                    "p99": float(np.percentile(values, 99)),
                }

                # Update thresholds based on sensitivity
                sensitivity = self._detection_config["sensitivity"]
                baseline.upper_threshold = baseline.mean + (
                    sensitivity * 2 * baseline.std_dev
                )
                baseline.lower_threshold = baseline.mean - (
                    sensitivity * 2 * baseline.std_dev
                )
                baseline.variance_threshold = baseline.std_dev * sensitivity

        baseline.updated_at = time.time()

    async def _check_metric_anomalies(
        self, metric: PerformanceMetric
    ) -> List[PerformanceAnomaly]:
        """Check a single metric for anomalies."""
        anomalies = []
        baseline = self._baselines.get(metric.metric_name)

        if (
            not baseline
            or baseline.sample_count < self._detection_config["min_samples"]
        ):
            return anomalies

        # Threshold-based detection
        if metric.value > baseline.upper_threshold:
            anomaly = self._create_anomaly(
                metric,
                baseline,
                AnomalyType.LATENCY_SPIKE,
                DetectionMethod.THRESHOLD_BASED,
                f"Value {metric.value:.2f} exceeds upper threshold {baseline.upper_threshold:.2f}",
            )
            anomalies.append(anomaly)
        elif metric.value < baseline.lower_threshold:
            anomaly = self._create_anomaly(
                metric,
                baseline,
                AnomalyType.THROUGHPUT_DROP,
                DetectionMethod.THRESHOLD_BASED,
                f"Value {metric.value:.2f} below lower threshold {baseline.lower_threshold:.2f}",
            )
            anomalies.append(anomaly)

        # Z-score based detection
        if baseline.std_dev > 0:
            zscore = abs(metric.value - baseline.mean) / baseline.std_dev
            if zscore > self._detection_config["zscore_threshold"]:
                anomaly = self._create_anomaly(
                    metric,
                    baseline,
                    AnomalyType.RESPONSE_TIME_VARIANCE,
                    DetectionMethod.ZSCORE,
                    f"Z-score {zscore:.2f} exceeds threshold {self._detection_config['zscore_threshold']}",
                )
                anomalies.append(anomaly)

        return anomalies

    async def _apply_detection_method(
        self,
        metric_name: str,
        metrics: List[PerformanceMetric],
        method: DetectionMethod,
    ) -> List[PerformanceAnomaly]:
        """Apply a specific detection method to metrics."""
        anomalies = []
        baseline = self._baselines.get(metric_name)

        if not baseline or not metrics:
            return anomalies

        values = [m.value for m in metrics]

        if method == DetectionMethod.STATISTICAL:
            # Statistical analysis using Z-score and IQR
            if len(values) >= 10:
                mean_val = np.mean(values)
                std_val = np.std(values)

                for metric in metrics:
                    if std_val > 0:
                        zscore = abs(metric.value - mean_val) / std_val
                        if zscore > self._detection_config["zscore_threshold"]:
                            anomaly = self._create_anomaly(
                                metric,
                                baseline,
                                AnomalyType.RESPONSE_TIME_VARIANCE,
                                method,
                                f"Statistical outlier with Z-score {zscore:.2f}",
                            )
                            anomalies.append(anomaly)

        elif method == DetectionMethod.IQR:
            # Interquartile Range method
            if len(values) >= 10:
                q1 = np.percentile(values, 25)
                q3 = np.percentile(values, 75)
                iqr = q3 - q1
                multiplier = self._detection_config.get("iqr_multiplier", 1.5)

                lower_bound = q1 - multiplier * iqr
                upper_bound = q3 + multiplier * iqr

                for metric in metrics:
                    if metric.value < lower_bound or metric.value > upper_bound:
                        anomaly = self._create_anomaly(
                            metric,
                            baseline,
                            AnomalyType.RESPONSE_TIME_VARIANCE,
                            method,
                            f"IQR outlier: value {metric.value:.2f} outside [{lower_bound:.2f}, {upper_bound:.2f}]",
                        )
                        anomalies.append(anomaly)

        elif method == DetectionMethod.ROLLING_AVERAGE:
            # Rolling average deviation
            if len(values) >= 10:
                window_size = min(10, len(values) // 2)
                for i in range(window_size, len(metrics)):
                    window_values = values[i - window_size : i]
                    rolling_avg = np.mean(window_values)
                    rolling_std = np.std(window_values)

                    current_metric = metrics[i]
                    if rolling_std > 0:
                        deviation = (
                            abs(current_metric.value - rolling_avg) / rolling_std
                        )
                        if deviation > 2.0:  # 2 standard deviations
                            anomaly = self._create_anomaly(
                                current_metric,
                                baseline,
                                AnomalyType.TREND_ANOMALY,
                                method,
                                f"Rolling average deviation: {deviation:.2f}",
                            )
                            anomalies.append(anomaly)

        return anomalies

    def _create_anomaly(
        self,
        metric: PerformanceMetric,
        baseline: PerformanceBaseline,
        anomaly_type: AnomalyType,
        method: DetectionMethod,
        description: str,
    ) -> PerformanceAnomaly:
        """Create an anomaly detection object."""
        expected_value = baseline.mean
        deviation = abs(metric.value - expected_value)

        # Calculate confidence based on deviation magnitude
        if baseline.std_dev > 0:
            confidence = min(1.0, deviation / (2 * baseline.std_dev))
        else:
            confidence = 1.0 if deviation > 0 else 0.0

        # Determine severity
        severity = self._determine_severity(deviation, baseline)

        # Generate recommendations
        recommendations = self._get_anomaly_recommendations(anomaly_type, metric)

        return PerformanceAnomaly(
            anomaly_id=f"anomaly_{int(time.time() * 1000000)}",
            anomaly_type=anomaly_type,
            metric_name=metric.metric_name,
            detected_at=time.time(),
            value=metric.value,
            expected_value=expected_value,
            deviation=deviation,
            severity=severity,
            confidence=confidence,
            detection_method=method,
            description=description,
            impact_assessment=self._assess_impact(anomaly_type, deviation, baseline),
            recommended_actions=recommendations,
            tags=metric.tags,
            metadata=metric.metadata,
        )

    def _determine_severity(
        self, deviation: float, baseline: PerformanceBaseline
    ) -> AnomalySeverity:
        """Determine severity based on deviation magnitude."""
        if baseline.std_dev <= 0:
            return AnomalySeverity.MEDIUM

        zscore_equivalent = deviation / baseline.std_dev

        if zscore_equivalent > 4.0:
            return AnomalySeverity.CRITICAL
        elif zscore_equivalent > 3.0:
            return AnomalySeverity.HIGH
        elif zscore_equivalent > 2.0:
            return AnomalySeverity.MEDIUM
        else:
            return AnomalySeverity.LOW

    def _assess_impact(
        self, anomaly_type: AnomalyType, deviation: float, baseline: PerformanceBaseline
    ) -> str:
        """Assess the potential impact of an anomaly."""
        impact_map = {
            AnomalyType.LATENCY_SPIKE: f"Increased response time may impact user experience. Current deviation: {deviation:.2f}ms above baseline.",
            AnomalyType.THROUGHPUT_DROP: f"Reduced system throughput may indicate capacity issues. Current drop: {deviation:.2f} below expected.",
            AnomalyType.ERROR_RATE_INCREASE: f"Higher error rate indicates system instability. Error rate increased by {deviation:.2f}%.",
            AnomalyType.RESOURCE_EXHAUSTION: f"Resource usage spike may lead to system degradation. Usage increased by {deviation:.2f} units.",
            AnomalyType.RESPONSE_TIME_VARIANCE: f"Inconsistent response times indicate system instability. Variance deviation: {deviation:.2f}.",
            AnomalyType.CONCURRENCY_ANOMALY: f"Unusual concurrency patterns may indicate load issues. Concurrency deviation: {deviation:.2f}.",
            AnomalyType.TREND_ANOMALY: f"Performance trend anomaly detected. Pattern deviation: {deviation:.2f}.",
        }
        return impact_map.get(
            anomaly_type,
            f"Performance anomaly detected with deviation: {deviation:.2f}",
        )

    def _get_anomaly_recommendations(
        self, anomaly_type: AnomalyType, metric: PerformanceMetric
    ) -> List[str]:
        """Get recommendations for handling specific anomaly types."""
        recommendation_map = {
            AnomalyType.LATENCY_SPIKE: [
                "Check for database query optimization opportunities",
                "Review recent code deployments for performance regressions",
                "Monitor system resource utilization (CPU, memory, I/O)",
                "Consider horizontal scaling if load is high",
            ],
            AnomalyType.THROUGHPUT_DROP: [
                "Investigate potential bottlenecks in request processing",
                "Check for resource contention or lock contention",
                "Review connection pool configurations",
                "Monitor downstream service dependencies",
            ],
            AnomalyType.ERROR_RATE_INCREASE: [
                "Review application logs for error patterns",
                "Check external service dependencies",
                "Validate input data quality and format",
                "Consider implementing circuit breaker patterns",
            ],
            AnomalyType.RESOURCE_EXHAUSTION: [
                "Scale up system resources (CPU, memory)",
                "Implement resource pooling and caching",
                "Review memory leaks and resource cleanup",
                "Consider load balancing and distribution",
            ],
            AnomalyType.RESPONSE_TIME_VARIANCE: [
                "Investigate intermittent performance issues",
                "Check for garbage collection or memory pressure",
                "Review caching effectiveness",
                "Monitor network latency and stability",
            ],
        }
        return recommendation_map.get(
            anomaly_type, ["Investigate performance patterns and system metrics"]
        )

    def _deduplicate_anomalies(
        self, anomalies: List[PerformanceAnomaly]
    ) -> List[PerformanceAnomaly]:
        """Remove duplicate and similar anomalies."""
        if not anomalies:
            return []

        # Sort by confidence and severity for prioritization
        sorted_anomalies = sorted(
            anomalies, key=lambda a: (a.severity.value, a.confidence), reverse=True
        )

        unique_anomalies = []
        for anomaly in sorted_anomalies:
            # Check if similar anomaly already exists
            is_duplicate = False
            for existing in unique_anomalies:
                if (
                    existing.metric_name == anomaly.metric_name
                    and existing.anomaly_type == anomaly.anomaly_type
                    and abs(existing.detected_at - anomaly.detected_at)
                    < 60.0  # Within 1 minute
                ):
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique_anomalies.append(anomaly)

        return unique_anomalies

    def _generate_recommendations(
        self, anomalies: List[PerformanceAnomaly]
    ) -> List[str]:
        """Generate overall performance optimization recommendations."""
        if not anomalies:
            return ["System performance appears normal"]

        recommendations = set()

        # Analyze anomaly patterns
        anomaly_types = [a.anomaly_type for a in anomalies]
        severity_levels = [a.severity for a in anomalies]

        # High-level recommendations based on patterns
        if AnomalyType.LATENCY_SPIKE in anomaly_types:
            recommendations.add("Implement performance monitoring and alerting")
            recommendations.add("Consider caching frequently accessed data")

        if AnomalyType.THROUGHPUT_DROP in anomaly_types:
            recommendations.add("Review system capacity and scaling policies")
            recommendations.add("Optimize database queries and connections")

        if any(s == AnomalySeverity.CRITICAL for s in severity_levels):
            recommendations.add(
                "Immediate investigation required - critical performance issue detected"
            )

        # Add specific recommendations from individual anomalies
        for anomaly in anomalies[:3]:  # Top 3 anomalies
            recommendations.update(
                anomaly.recommended_actions[:2]
            )  # Top 2 actions each

        return list(recommendations)

    async def _get_baseline(self, **kwargs) -> Dict[str, Any]:
        """Get baseline information for metrics."""
        metric_name = kwargs.get("metric_name")

        if metric_name:
            baselines = (
                {metric_name: self._serialize_baseline(self._baselines[metric_name])}
                if metric_name in self._baselines
                else {}
            )
        else:
            baselines = {
                name: self._serialize_baseline(baseline)
                for name, baseline in self._baselines.items()
            }

        return {
            "anomalies_detected": [],
            "anomaly_count": 0,
            "baselines": baselines,
            "metrics_processed": 0,
            "detection_summary": {"baselines_retrieved": len(baselines)},
            "recommendations": [],
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _get_anomalies(self, **kwargs) -> Dict[str, Any]:
        """Get detected anomalies."""
        return {
            "anomalies_detected": [
                self._serialize_anomaly(a) for a in self._detected_anomalies
            ],
            "anomaly_count": len(self._detected_anomalies),
            "baselines": {},
            "metrics_processed": 0,
            "detection_summary": {"anomalies_retrieved": len(self._detected_anomalies)},
            "recommendations": self._generate_recommendations(self._detected_anomalies),
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _start_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Start continuous anomaly monitoring."""
        interval = kwargs.get("monitoring_interval", 30.0)

        if not self._monitoring_active:
            self._monitoring_active = True
            monitoring_task = asyncio.create_task(self._monitoring_loop(interval))
            self._background_tasks.add(monitoring_task)
            monitoring_task.add_done_callback(self._background_tasks.discard)

        return {
            "anomalies_detected": [],
            "anomaly_count": 0,
            "baselines": {},
            "metrics_processed": 0,
            "detection_summary": {"monitoring_started": True, "interval": interval},
            "recommendations": [],
            "monitoring_status": "monitoring",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _stop_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Stop continuous anomaly monitoring."""
        self._monitoring_active = False

        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        self._background_tasks.clear()

        return {
            "anomalies_detected": [],
            "anomaly_count": 0,
            "baselines": {},
            "metrics_processed": 0,
            "detection_summary": {"monitoring_stopped": True},
            "recommendations": [],
            "monitoring_status": "stopped",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _monitoring_loop(self, interval: float):
        """Background monitoring loop for continuous anomaly detection."""
        while self._monitoring_active:
            try:
                await asyncio.sleep(interval)

                # Run anomaly detection on all metrics
                metric_names = list(self._baselines.keys())
                if metric_names:
                    result = await self._detect_anomalies(
                        metric_names=metric_names,
                        detection_window=interval * 2,
                    )

                    if result["anomaly_count"] > 0:
                        self.logger.warning(
                            f"Monitoring detected {result['anomaly_count']} performance anomalies"
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")

    def _serialize_baseline(self, baseline: PerformanceBaseline) -> Dict[str, Any]:
        """Serialize a baseline to dictionary."""
        return {
            "metric_name": baseline.metric_name,
            "created_at": baseline.created_at,
            "updated_at": baseline.updated_at,
            "sample_count": baseline.sample_count,
            "mean": baseline.mean,
            "median": baseline.median,
            "std_dev": baseline.std_dev,
            "min_value": baseline.min_value,
            "max_value": baseline.max_value,
            "percentiles": baseline.percentiles,
            "trend_slope": baseline.trend_slope,
            "upper_threshold": baseline.upper_threshold,
            "lower_threshold": baseline.lower_threshold,
            "variance_threshold": baseline.variance_threshold,
            "learning_rate": baseline.learning_rate,
        }

    def _serialize_anomaly(self, anomaly: PerformanceAnomaly) -> Dict[str, Any]:
        """Serialize an anomaly to dictionary."""
        return {
            "anomaly_id": anomaly.anomaly_id,
            "anomaly_type": anomaly.anomaly_type.value,
            "metric_name": anomaly.metric_name,
            "detected_at": anomaly.detected_at,
            "value": anomaly.value,
            "expected_value": anomaly.expected_value,
            "deviation": anomaly.deviation,
            "severity": anomaly.severity.value,
            "confidence": anomaly.confidence,
            "detection_method": anomaly.detection_method.value,
            "description": anomaly.description,
            "impact_assessment": anomaly.impact_assessment,
            "recommended_actions": anomaly.recommended_actions,
            "tags": anomaly.tags,
            "metadata": anomaly.metadata,
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous wrapper for compatibility."""
        import asyncio

        return asyncio.run(self.async_run(**kwargs))

    async def cleanup(self):
        """Cleanup resources when node is destroyed."""
        await self._stop_monitoring()
        await super().cleanup() if hasattr(super(), "cleanup") else None

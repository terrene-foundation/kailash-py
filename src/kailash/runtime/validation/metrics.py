"""
Performance monitoring and metrics collection for connection validation.

Tracks validation performance, security violations, and provides insights
into validation effectiveness and potential performance bottlenecks.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from kailash.runtime.validation.error_categorizer import ErrorCategory


class ValidationEventType(Enum):
    """Types of validation events to track."""

    VALIDATION_STARTED = "validation_started"
    VALIDATION_COMPLETED = "validation_completed"
    VALIDATION_FAILED = "validation_failed"
    SECURITY_VIOLATION = "security_violation"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    TYPE_COERCION = "type_coercion"
    MODE_BYPASS = "mode_bypass"


@dataclass
class ValidationMetric:
    """Single validation metric entry."""

    timestamp: datetime
    event_type: ValidationEventType
    node_id: str
    node_type: str
    duration_ms: Optional[float] = None
    error_category: Optional[ErrorCategory] = None
    validation_mode: Optional[str] = None
    connection_source: Optional[str] = None
    connection_target: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)


class ValidationMetricsCollector:
    """Collects and aggregates validation performance metrics."""

    def __init__(self, enable_detailed_logging: bool = False):
        """Initialize metrics collector.

        Args:
            enable_detailed_logging: Whether to log detailed metrics to logger
        """
        self.metrics: List[ValidationMetric] = []
        self.node_validation_times: Dict[str, List[float]] = defaultdict(list)
        self.error_counts: Dict[ErrorCategory, int] = defaultdict(int)
        self.security_violations: List[ValidationMetric] = []
        self.enable_detailed_logging = enable_detailed_logging
        self.logger = logging.getLogger("kailash.validation.metrics")

        # Performance tracking
        self._active_validations: Dict[str, float] = {}
        self._cache_stats = {"hits": 0, "misses": 0}

    def start_validation(
        self, node_id: str, node_type: str, validation_mode: str
    ) -> None:
        """Record the start of a validation operation.

        Args:
            node_id: ID of the node being validated
            node_type: Type of the node
            validation_mode: Validation mode (off, warn, strict)
        """
        self._active_validations[node_id] = time.time()

        metric = ValidationMetric(
            timestamp=datetime.now(UTC),
            event_type=ValidationEventType.VALIDATION_STARTED,
            node_id=node_id,
            node_type=node_type,
            validation_mode=validation_mode,
        )
        self.metrics.append(metric)

        if self.enable_detailed_logging:
            self.logger.debug(
                f"Validation started for {node_id} ({node_type}) in {validation_mode} mode"
            )

    def end_validation(
        self,
        node_id: str,
        node_type: str,
        success: bool,
        error_category: Optional[ErrorCategory] = None,
        connection_info: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record the end of a validation operation.

        Args:
            node_id: ID of the node that was validated
            node_type: Type of the node
            success: Whether validation succeeded
            error_category: Category of error if validation failed
            connection_info: Optional connection source/target information
        """
        # Calculate duration
        duration_ms = None
        if node_id in self._active_validations:
            start_time = self._active_validations.pop(node_id)
            duration_ms = (time.time() - start_time) * 1000  # Convert to milliseconds
            self.node_validation_times[node_type].append(duration_ms)

        # Record appropriate event
        event_type = (
            ValidationEventType.VALIDATION_COMPLETED
            if success
            else ValidationEventType.VALIDATION_FAILED
        )

        metric = ValidationMetric(
            timestamp=datetime.now(UTC),
            event_type=event_type,
            node_id=node_id,
            node_type=node_type,
            duration_ms=duration_ms,
            error_category=error_category,
            connection_source=(
                connection_info.get("source") if connection_info else None
            ),
            connection_target=(
                connection_info.get("target") if connection_info else None
            ),
        )
        self.metrics.append(metric)

        # Track error counts
        if error_category:
            self.error_counts[error_category] += 1

        if self.enable_detailed_logging:
            status = "succeeded" if success else "failed"
            duration_str = f" in {duration_ms:.2f}ms" if duration_ms else ""
            self.logger.debug(
                f"Validation {status} for {node_id} ({node_type}){duration_str}"
            )

    def record_security_violation(
        self,
        node_id: str,
        node_type: str,
        violation_details: Dict[str, Any],
        connection_info: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a security violation event.

        Args:
            node_id: ID of the node where violation occurred
            node_type: Type of the node
            violation_details: Details about the security violation
            connection_info: Optional connection source/target information
        """
        metric = ValidationMetric(
            timestamp=datetime.now(UTC),
            event_type=ValidationEventType.SECURITY_VIOLATION,
            node_id=node_id,
            node_type=node_type,
            error_category=ErrorCategory.SECURITY_VIOLATION,
            connection_source=(
                connection_info.get("source") if connection_info else None
            ),
            connection_target=(
                connection_info.get("target") if connection_info else None
            ),
            additional_data=violation_details,
        )

        self.metrics.append(metric)
        self.security_violations.append(metric)
        self.error_counts[ErrorCategory.SECURITY_VIOLATION] += 1

        # Always log security violations regardless of detailed logging setting
        self.logger.warning(
            f"SECURITY VIOLATION in {node_id} ({node_type}): {violation_details.get('message', 'Unknown')}"
        )

    def record_cache_hit(self, node_type: str) -> None:
        """Record a validation cache hit."""
        self._cache_stats["hits"] += 1

        metric = ValidationMetric(
            timestamp=datetime.now(UTC),
            event_type=ValidationEventType.CACHE_HIT,
            node_id="cache",
            node_type=node_type,
        )
        self.metrics.append(metric)

    def record_cache_miss(self, node_type: str) -> None:
        """Record a validation cache miss."""
        self._cache_stats["misses"] += 1

        metric = ValidationMetric(
            timestamp=datetime.now(UTC),
            event_type=ValidationEventType.CACHE_MISS,
            node_id="cache",
            node_type=node_type,
        )
        self.metrics.append(metric)

    def record_mode_bypass(self, node_id: str, node_type: str, mode: str) -> None:
        """Record when validation is bypassed due to mode setting.

        Args:
            node_id: ID of the node
            node_type: Type of the node
            mode: Validation mode that caused bypass
        """
        metric = ValidationMetric(
            timestamp=datetime.now(UTC),
            event_type=ValidationEventType.MODE_BYPASS,
            node_id=node_id,
            node_type=node_type,
            validation_mode=mode,
        )
        self.metrics.append(metric)

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a summary of validation performance metrics.

        Returns:
            Dictionary containing performance statistics
        """
        total_validations = sum(
            1
            for m in self.metrics
            if m.event_type
            in [
                ValidationEventType.VALIDATION_COMPLETED,
                ValidationEventType.VALIDATION_FAILED,
            ]
        )

        failed_validations = sum(
            1
            for m in self.metrics
            if m.event_type == ValidationEventType.VALIDATION_FAILED
        )

        # Calculate average validation times by node type
        avg_times = {}
        for node_type, times in self.node_validation_times.items():
            if times:
                avg_times[node_type] = {
                    "avg_ms": sum(times) / len(times),
                    "min_ms": min(times),
                    "max_ms": max(times),
                    "count": len(times),
                }

        # Cache effectiveness
        total_cache_ops = self._cache_stats["hits"] + self._cache_stats["misses"]
        cache_hit_rate = (
            self._cache_stats["hits"] / total_cache_ops * 100
            if total_cache_ops > 0
            else 0
        )

        return {
            "total_validations": total_validations,
            "failed_validations": failed_validations,
            "failure_rate": (
                failed_validations / total_validations * 100
                if total_validations > 0
                else 0
            ),
            "security_violations": len(self.security_violations),
            "error_breakdown": dict(self.error_counts),
            "performance_by_node_type": avg_times,
            "cache_stats": {
                "hits": self._cache_stats["hits"],
                "misses": self._cache_stats["misses"],
                "hit_rate": cache_hit_rate,
            },
            "mode_bypasses": sum(
                1
                for m in self.metrics
                if m.event_type == ValidationEventType.MODE_BYPASS
            ),
        }

    def get_security_report(self) -> Dict[str, Any]:
        """Get a detailed security violations report.

        Returns:
            Dictionary containing security violation details
        """
        violations_by_node = defaultdict(list)
        for violation in self.security_violations:
            violations_by_node[violation.node_type].append(
                {
                    "timestamp": violation.timestamp.isoformat(),
                    "node_id": violation.node_id,
                    "connection": f"{violation.connection_source} → {violation.connection_target}",
                    "details": violation.additional_data,
                }
            )

        return {
            "total_violations": len(self.security_violations),
            "violations_by_node_type": dict(violations_by_node),
            "most_recent_violations": [
                {
                    "timestamp": v.timestamp.isoformat(),
                    "node": f"{v.node_id} ({v.node_type})",
                    "details": v.additional_data,
                }
                for v in sorted(
                    self.security_violations, key=lambda x: x.timestamp, reverse=True
                )[:10]
            ],
        }

    def reset_metrics(self) -> None:
        """Reset all collected metrics."""
        self.metrics.clear()
        self.node_validation_times.clear()
        self.error_counts.clear()
        self.security_violations.clear()
        self._cache_stats = {"hits": 0, "misses": 0}
        self._active_validations.clear()

    def export_metrics(self) -> List[Dict[str, Any]]:
        """Export all metrics as a list of dictionaries.

        Returns:
            List of metric dictionaries for external processing
        """
        return [
            {
                "timestamp": m.timestamp.isoformat(),
                "event_type": m.event_type.value,
                "node_id": m.node_id,
                "node_type": m.node_type,
                "duration_ms": m.duration_ms,
                "error_category": m.error_category.value if m.error_category else None,
                "validation_mode": m.validation_mode,
                "connection_source": m.connection_source,
                "connection_target": m.connection_target,
                "additional_data": m.additional_data,
            }
            for m in self.metrics
        ]


# Global metrics collector instance
_global_metrics_collector = None


def get_metrics_collector() -> ValidationMetricsCollector:
    """Get the global metrics collector instance.

    Returns:
        The global ValidationMetricsCollector instance
    """
    global _global_metrics_collector
    if _global_metrics_collector is None:
        _global_metrics_collector = ValidationMetricsCollector()
    return _global_metrics_collector


def reset_global_metrics() -> None:
    """Reset the global metrics collector."""
    global _global_metrics_collector
    if _global_metrics_collector:
        _global_metrics_collector.reset_metrics()

"""Resource analyzer for intelligent edge resource management.

This module provides real-time resource analysis, pattern identification,
and bottleneck detection for edge computing infrastructure.
"""

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats


class ResourceType(Enum):
    """Types of resources to analyze."""

    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"
    STORAGE = "storage"
    NETWORK = "network"
    CUSTOM = "custom"


class BottleneckType(Enum):
    """Types of resource bottlenecks."""

    CAPACITY = "capacity"  # Not enough resources
    ALLOCATION = "allocation"  # Poor distribution
    CONTENTION = "contention"  # Resource conflicts
    FRAGMENTATION = "fragmentation"  # Wasted space
    THROTTLING = "throttling"  # Rate limiting


@dataclass
class ResourceMetric:
    """Single resource metric measurement."""

    timestamp: datetime
    edge_node: str
    resource_type: ResourceType
    used: float
    available: float
    total: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def utilization(self) -> float:
        """Calculate utilization percentage."""
        if self.total == 0:
            return 0.0
        return (self.used / self.total) * 100

    @property
    def free(self) -> float:
        """Calculate free resources."""
        return self.total - self.used

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "edge_node": self.edge_node,
            "resource_type": self.resource_type.value,
            "used": self.used,
            "available": self.available,
            "total": self.total,
            "utilization": self.utilization,
            "metadata": self.metadata,
        }


@dataclass
class ResourcePattern:
    """Identified resource usage pattern."""

    pattern_type: str
    confidence: float
    edge_nodes: List[str]
    resource_types: List[ResourceType]
    characteristics: Dict[str, Any]
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pattern_type": self.pattern_type,
            "confidence": self.confidence,
            "edge_nodes": self.edge_nodes,
            "resource_types": [rt.value for rt in self.resource_types],
            "characteristics": self.characteristics,
            "recommendations": self.recommendations,
        }


@dataclass
class Bottleneck:
    """Identified resource bottleneck."""

    bottleneck_type: BottleneckType
    severity: float  # 0-1 scale
    edge_node: str
    resource_type: ResourceType
    description: str
    impact: Dict[str, Any]
    resolution: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "bottleneck_type": self.bottleneck_type.value,
            "severity": self.severity,
            "edge_node": self.edge_node,
            "resource_type": self.resource_type.value,
            "description": self.description,
            "impact": self.impact,
            "resolution": self.resolution,
        }


class ResourceAnalyzer:
    """Analyzes resource usage patterns and identifies bottlenecks."""

    def __init__(
        self,
        history_window: int = 3600,  # 1 hour
        analysis_interval: int = 60,  # 1 minute
        anomaly_threshold: float = 2.5,  # Standard deviations
        pattern_confidence_threshold: float = 0.7,
    ):
        """Initialize resource analyzer.

        Args:
            history_window: Time window for analysis (seconds)
            analysis_interval: Interval between analyses (seconds)
            anomaly_threshold: Threshold for anomaly detection
            pattern_confidence_threshold: Minimum confidence for patterns
        """
        self.history_window = history_window
        self.analysis_interval = analysis_interval
        self.anomaly_threshold = anomaly_threshold
        self.pattern_confidence_threshold = pattern_confidence_threshold

        # Resource metrics storage
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Analysis results
        self.patterns: List[ResourcePattern] = []
        self.bottlenecks: List[Bottleneck] = []
        self.anomalies: List[Dict[str, Any]] = []

        # Background task
        self._analysis_task: Optional[asyncio.Task] = None

        self.logger = logging.getLogger(__name__)

    async def start(self):
        """Start background analysis."""
        if not self._analysis_task:
            self._analysis_task = asyncio.create_task(self._analysis_loop())
            self.logger.info("Resource analyzer started")

    async def stop(self):
        """Stop background analysis."""
        if self._analysis_task:
            self._analysis_task.cancel()
            try:
                await self._analysis_task
            except asyncio.CancelledError:
                pass
            self._analysis_task = None
            self.logger.info("Resource analyzer stopped")

    async def record_metric(self, metric: ResourceMetric):
        """Record a resource metric.

        Args:
            metric: Resource metric to record
        """
        key = f"{metric.edge_node}:{metric.resource_type.value}"
        self.metrics[key].append(metric)

        # Check for immediate issues
        await self._check_immediate_issues(metric)

    async def analyze_resources(self) -> Dict[str, Any]:
        """Perform comprehensive resource analysis.

        Returns:
            Analysis results
        """
        # Clear previous results
        self.patterns.clear()
        self.bottlenecks.clear()
        self.anomalies.clear()

        # Run all analyses
        await self._identify_patterns()
        await self._detect_bottlenecks()
        await self._detect_anomalies()

        return {
            "patterns": [p.to_dict() for p in self.patterns],
            "bottlenecks": [b.to_dict() for b in self.bottlenecks],
            "anomalies": self.anomalies,
            "summary": self._generate_summary(),
        }

    async def get_resource_trends(
        self,
        edge_node: Optional[str] = None,
        resource_type: Optional[ResourceType] = None,
        duration_minutes: int = 60,
    ) -> Dict[str, Any]:
        """Get resource usage trends.

        Args:
            edge_node: Filter by edge node
            resource_type: Filter by resource type
            duration_minutes: Duration to analyze

        Returns:
            Trend analysis
        """
        trends = {}
        cutoff = datetime.now() - timedelta(minutes=duration_minutes)

        for key, metrics in self.metrics.items():
            node, rtype = key.split(":")

            # Apply filters
            if edge_node and node != edge_node:
                continue
            if resource_type and rtype != resource_type.value:
                continue

            # Get recent metrics
            recent = [m for m in metrics if m.timestamp > cutoff]
            if not recent:
                continue

            # Calculate trends
            utilizations = [m.utilization for m in recent]
            timestamps = [(m.timestamp - cutoff).total_seconds() for m in recent]

            if len(utilizations) > 1:
                # Linear regression for trend
                slope, intercept, r_value, _, _ = stats.linregress(
                    timestamps, utilizations
                )

                trends[key] = {
                    "current": utilizations[-1],
                    "average": np.mean(utilizations),
                    "min": np.min(utilizations),
                    "max": np.max(utilizations),
                    "std_dev": np.std(utilizations),
                    "trend_slope": slope,
                    "trend_direction": (
                        "increasing"
                        if slope > 0.1
                        else "decreasing" if slope < -0.1 else "stable"
                    ),
                    "prediction_1h": (
                        intercept + slope * 3600 if abs(r_value) > 0.5 else None
                    ),
                }

        return trends

    async def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Get resource optimization recommendations.

        Returns:
            List of recommendations
        """
        recommendations = []

        # Analyze current state
        await self.analyze_resources()

        # Pattern-based recommendations
        for pattern in self.patterns:
            if pattern.confidence >= self.pattern_confidence_threshold:
                recommendations.append(
                    {
                        "type": "pattern",
                        "priority": self._calculate_priority(pattern.confidence),
                        "pattern": pattern.pattern_type,
                        "affected_nodes": pattern.edge_nodes,
                        "recommendations": pattern.recommendations,
                        "expected_improvement": pattern.characteristics.get(
                            "improvement", "10-20%"
                        ),
                    }
                )

        # Bottleneck-based recommendations
        for bottleneck in self.bottlenecks:
            if bottleneck.severity > 0.5:
                recommendations.append(
                    {
                        "type": "bottleneck",
                        "priority": self._calculate_priority(bottleneck.severity),
                        "issue": bottleneck.description,
                        "node": bottleneck.edge_node,
                        "resource": bottleneck.resource_type.value,
                        "resolutions": bottleneck.resolution,
                        "impact": bottleneck.impact,
                    }
                )

        # Sort by priority
        recommendations.sort(key=lambda x: x["priority"], reverse=True)

        return recommendations

    async def _analysis_loop(self):
        """Background analysis loop."""
        while True:
            try:
                await asyncio.sleep(self.analysis_interval)
                await self.analyze_resources()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Analysis error: {e}")

    async def _check_immediate_issues(self, metric: ResourceMetric):
        """Check for immediate issues requiring attention.

        Args:
            metric: Resource metric to check
        """
        # Critical utilization check
        if metric.utilization > 95:
            self.logger.warning(
                f"Critical {metric.resource_type.value} utilization "
                f"on {metric.edge_node}: {metric.utilization:.1f}%"
            )

        # No available resources
        if metric.available == 0 and metric.resource_type in [
            ResourceType.CPU,
            ResourceType.MEMORY,
        ]:
            self.logger.error(
                f"No {metric.resource_type.value} available " f"on {metric.edge_node}"
            )

    async def _identify_patterns(self):
        """Identify resource usage patterns."""
        # Periodic pattern detection
        periodic_pattern = await self._detect_periodic_pattern()
        if periodic_pattern:
            self.patterns.append(periodic_pattern)

        # Spike pattern detection
        spike_pattern = await self._detect_spike_pattern()
        if spike_pattern:
            self.patterns.append(spike_pattern)

        # Gradual increase pattern
        growth_pattern = await self._detect_growth_pattern()
        if growth_pattern:
            self.patterns.append(growth_pattern)

        # Imbalance pattern
        imbalance_pattern = await self._detect_imbalance_pattern()
        if imbalance_pattern:
            self.patterns.append(imbalance_pattern)

    async def _detect_periodic_pattern(self) -> Optional[ResourcePattern]:
        """Detect periodic usage patterns."""
        for key, metrics in self.metrics.items():
            if len(metrics) < 100:
                continue

            # Extract utilization time series
            utilizations = [m.utilization for m in metrics]

            # Simple FFT-based periodicity detection
            fft = np.fft.fft(utilizations)
            frequencies = np.fft.fftfreq(len(utilizations))

            # Find dominant frequency
            dominant_idx = np.argmax(np.abs(fft[1 : len(fft) // 2])) + 1
            if np.abs(fft[dominant_idx]) > len(utilizations) * 0.1:
                period = (
                    1 / frequencies[dominant_idx]
                    if frequencies[dominant_idx] != 0
                    else 0
                )

                if period > 0:
                    node, rtype = key.split(":")
                    return ResourcePattern(
                        pattern_type="periodic",
                        confidence=min(
                            np.abs(fft[dominant_idx]) / len(utilizations), 1.0
                        ),
                        edge_nodes=[node],
                        resource_types=[ResourceType(rtype)],
                        characteristics={
                            "period_seconds": abs(period * self.analysis_interval),
                            "amplitude": np.std(utilizations),
                            "improvement": "15-25%",
                        },
                        recommendations=[
                            f"Implement predictive scaling with {abs(period * self.analysis_interval):.0f}s period",
                            "Use time-based resource allocation",
                            "Consider workload scheduling optimization",
                        ],
                    )

        return None

    async def _detect_spike_pattern(self) -> Optional[ResourcePattern]:
        """Detect resource usage spikes."""
        spike_nodes = []
        spike_resources = set()

        for key, metrics in self.metrics.items():
            if len(metrics) < 10:
                continue

            utilizations = [m.utilization for m in metrics]
            mean = np.mean(utilizations)
            std = np.std(utilizations)

            # Count spikes
            spikes = sum(1 for u in utilizations if u > mean + 2 * std)

            if spikes > len(utilizations) * 0.1:  # More than 10% are spikes
                node, rtype = key.split(":")
                spike_nodes.append(node)
                spike_resources.add(ResourceType(rtype))

        if spike_nodes:
            return ResourcePattern(
                pattern_type="spike",
                confidence=0.8,
                edge_nodes=list(set(spike_nodes)),
                resource_types=list(spike_resources),
                characteristics={
                    "frequency": "frequent",
                    "impact": "high",
                    "improvement": "20-30%",
                },
                recommendations=[
                    "Implement burst capacity allocation",
                    "Use resource pooling for spike handling",
                    "Consider request rate limiting",
                    "Enable auto-scaling with aggressive policies",
                ],
            )

        return None

    async def _detect_growth_pattern(self) -> Optional[ResourcePattern]:
        """Detect gradual resource growth patterns."""
        growth_nodes = []
        growth_resources = set()

        for key, metrics in self.metrics.items():
            if len(metrics) < 50:
                continue

            # Get recent metrics
            recent = list(metrics)[-50:]
            utilizations = [m.utilization for m in recent]
            timestamps = list(range(len(utilizations)))

            # Linear regression
            slope, _, r_value, _, _ = stats.linregress(timestamps, utilizations)

            # Significant positive trend
            if slope > 0.1 and abs(r_value) > 0.7:
                node, rtype = key.split(":")
                growth_nodes.append(node)
                growth_resources.add(ResourceType(rtype))

        if growth_nodes:
            return ResourcePattern(
                pattern_type="gradual_growth",
                confidence=0.75,
                edge_nodes=list(set(growth_nodes)),
                resource_types=list(growth_resources),
                characteristics={
                    "growth_rate": "steady",
                    "risk": "capacity_exhaustion",
                    "improvement": "25-35%",
                },
                recommendations=[
                    "Plan capacity expansion",
                    "Implement predictive scaling",
                    "Review resource cleanup policies",
                    "Consider workload migration strategies",
                ],
            )

        return None

    async def _detect_imbalance_pattern(self) -> Optional[ResourcePattern]:
        """Detect resource imbalance across nodes."""
        # Group by resource type
        by_type: Dict[ResourceType, List[float]] = defaultdict(list)
        node_utils: Dict[str, float] = {}

        for key, metrics in self.metrics.items():
            if not metrics:
                continue

            node, rtype = key.split(":")
            recent_util = np.mean([m.utilization for m in list(metrics)[-10:]])

            by_type[ResourceType(rtype)].append(recent_util)
            node_utils[node] = recent_util

        # Check for imbalance
        imbalanced_resources = []
        for rtype, utils in by_type.items():
            if len(utils) > 1:
                cv = np.std(utils) / np.mean(utils) if np.mean(utils) > 0 else 0
                if cv > 0.5:  # Coefficient of variation > 0.5
                    imbalanced_resources.append(rtype)

        if imbalanced_resources:
            # Find over and under utilized nodes
            avg_util = np.mean(list(node_utils.values()))
            over_utilized = [n for n, u in node_utils.items() if u > avg_util + 20]
            under_utilized = [n for n, u in node_utils.items() if u < avg_util - 20]

            return ResourcePattern(
                pattern_type="imbalance",
                confidence=0.85,
                edge_nodes=over_utilized + under_utilized,
                resource_types=imbalanced_resources,
                characteristics={
                    "over_utilized": over_utilized,
                    "under_utilized": under_utilized,
                    "imbalance_severity": "high",
                    "improvement": "30-40%",
                },
                recommendations=[
                    "Implement load balancing strategies",
                    "Use affinity rules for better distribution",
                    "Consider workload migration from hot nodes",
                    "Enable cross-node resource sharing",
                ],
            )

        return None

    async def _detect_bottlenecks(self):
        """Detect resource bottlenecks."""
        # Capacity bottlenecks
        await self._detect_capacity_bottlenecks()

        # Allocation bottlenecks
        await self._detect_allocation_bottlenecks()

        # Contention bottlenecks
        await self._detect_contention_bottlenecks()

        # Fragmentation bottlenecks
        await self._detect_fragmentation_bottlenecks()

    async def _detect_capacity_bottlenecks(self):
        """Detect capacity bottlenecks."""
        for key, metrics in self.metrics.items():
            if not metrics:
                continue

            node, rtype = key.split(":")
            recent = list(metrics)[-10:]

            # Check sustained high utilization
            high_util_count = sum(1 for m in recent if m.utilization > 85)

            if high_util_count > len(recent) * 0.8:
                avg_util = np.mean([m.utilization for m in recent])

                self.bottlenecks.append(
                    Bottleneck(
                        bottleneck_type=BottleneckType.CAPACITY,
                        severity=min((avg_util - 85) / 15, 1.0),
                        edge_node=node,
                        resource_type=ResourceType(rtype),
                        description=f"Sustained high {rtype} utilization ({avg_util:.1f}%)",
                        impact={
                            "performance_degradation": "high",
                            "request_failures": avg_util > 95,
                            "user_impact": "significant",
                        },
                        resolution=[
                            f"Increase {rtype} capacity on {node}",
                            "Migrate workloads to other nodes",
                            "Optimize resource-intensive operations",
                            "Enable vertical scaling",
                        ],
                    )
                )

    async def _detect_allocation_bottlenecks(self):
        """Detect allocation bottlenecks."""
        # Check for poor allocation patterns
        for key, metrics in self.metrics.items():
            if len(metrics) < 20:
                continue

            node, rtype = key.split(":")

            # Look for allocation/deallocation patterns
            utils = [m.utilization for m in metrics]
            changes = np.diff(utils)

            # High variation suggests allocation issues
            if np.std(changes) > 10:
                self.bottlenecks.append(
                    Bottleneck(
                        bottleneck_type=BottleneckType.ALLOCATION,
                        severity=min(np.std(changes) / 20, 1.0),
                        edge_node=node,
                        resource_type=ResourceType(rtype),
                        description=f"Inefficient {rtype} allocation patterns",
                        impact={
                            "resource_waste": "moderate",
                            "response_variance": "high",
                            "efficiency": "low",
                        },
                        resolution=[
                            "Implement resource pooling",
                            "Use allocation caching",
                            "Optimize allocation algorithms",
                            "Review resource lifecycle management",
                        ],
                    )
                )

    async def _detect_contention_bottlenecks(self):
        """Detect resource contention."""
        # Look for patterns indicating contention
        for key, metrics in self.metrics.items():
            if len(metrics) < 30:
                continue

            node, rtype = key.split(":")

            # Get wait times from metadata if available
            wait_times = []
            for m in metrics:
                if "wait_time" in m.metadata:
                    wait_times.append(m.metadata["wait_time"])

            if wait_times and np.mean(wait_times) > 100:  # 100ms average wait
                self.bottlenecks.append(
                    Bottleneck(
                        bottleneck_type=BottleneckType.CONTENTION,
                        severity=min(np.mean(wait_times) / 500, 1.0),
                        edge_node=node,
                        resource_type=ResourceType(rtype),
                        description=f"High {rtype} contention (avg wait: {np.mean(wait_times):.0f}ms)",
                        impact={
                            "latency_increase": f"{np.mean(wait_times):.0f}ms",
                            "throughput_reduction": "significant",
                            "user_experience": "degraded",
                        },
                        resolution=[
                            "Implement resource locking optimization",
                            "Use lock-free data structures",
                            "Increase resource pool size",
                            "Review concurrent access patterns",
                        ],
                    )
                )

    async def _detect_fragmentation_bottlenecks(self):
        """Detect resource fragmentation."""
        for key, metrics in self.metrics.items():
            if not metrics:
                continue

            node, rtype = key.split(":")
            recent = list(metrics)[-5:]

            # Check for fragmentation indicators
            for m in recent:
                if m.used < m.total * 0.7 and m.available < m.total * 0.2:
                    # Used is low but available is also low = fragmentation
                    fragmentation_pct = (1 - (m.used + m.available) / m.total) * 100

                    if fragmentation_pct > 10:
                        self.bottlenecks.append(
                            Bottleneck(
                                bottleneck_type=BottleneckType.FRAGMENTATION,
                                severity=min(fragmentation_pct / 30, 1.0),
                                edge_node=node,
                                resource_type=ResourceType(rtype),
                                description=f"{rtype} fragmentation ({fragmentation_pct:.1f}%)",
                                impact={
                                    "wasted_resources": f"{fragmentation_pct:.1f}%",
                                    "allocation_failures": fragmentation_pct > 20,
                                    "efficiency": "reduced",
                                },
                                resolution=[
                                    "Implement defragmentation routine",
                                    "Use contiguous allocation strategies",
                                    "Review resource allocation sizes",
                                    "Enable resource compaction",
                                ],
                            )
                        )
                        break

    async def _detect_anomalies(self):
        """Detect resource anomalies."""
        cutoff = datetime.now() - timedelta(seconds=self.history_window)

        for key, metrics in self.metrics.items():
            if len(metrics) < 20:
                continue

            node, rtype = key.split(":")

            # Get historical data
            historical = [m for m in metrics if m.timestamp < cutoff]
            recent = [m for m in metrics if m.timestamp >= cutoff]

            if len(historical) < 10 or len(recent) < 3:
                continue

            # Calculate statistics
            hist_utils = [m.utilization for m in historical]
            recent_utils = [m.utilization for m in recent]

            mean = np.mean(hist_utils)
            std = np.std(hist_utils)

            # Check for anomalies
            for i, util in enumerate(recent_utils):
                z_score = (util - mean) / std if std > 0 else 0

                if abs(z_score) > self.anomaly_threshold:
                    self.anomalies.append(
                        {
                            "timestamp": recent[i].timestamp.isoformat(),
                            "edge_node": node,
                            "resource_type": rtype,
                            "value": util,
                            "expected_range": [mean - 2 * std, mean + 2 * std],
                            "z_score": z_score,
                            "severity": "high" if abs(z_score) > 4 else "medium",
                            "description": f"Unusual {rtype} utilization: {util:.1f}% (expected: {mean:.1f}±{std:.1f}%)",
                        }
                    )

    def _generate_summary(self) -> Dict[str, Any]:
        """Generate analysis summary."""
        # Calculate overall health score
        pattern_score = 100 - len(self.patterns) * 10
        bottleneck_score = 100 - sum(b.severity * 20 for b in self.bottlenecks)
        anomaly_score = 100 - len(self.anomalies) * 5

        health_score = max(
            0, min(100, (pattern_score + bottleneck_score + anomaly_score) / 3)
        )

        return {
            "health_score": health_score,
            "health_status": self._get_health_status(health_score),
            "total_patterns": len(self.patterns),
            "total_bottlenecks": len(self.bottlenecks),
            "total_anomalies": len(self.anomalies),
            "critical_issues": len([b for b in self.bottlenecks if b.severity > 0.8]),
            "top_recommendations": self._get_top_recommendations(),
        }

    def _get_health_status(self, score: float) -> str:
        """Get health status from score."""
        if score >= 90:
            return "excellent"
        elif score >= 75:
            return "good"
        elif score >= 60:
            return "fair"
        elif score >= 40:
            return "poor"
        else:
            return "critical"

    def _get_top_recommendations(self) -> List[str]:
        """Get top recommendations."""
        recommendations = []

        # From patterns
        for pattern in sorted(self.patterns, key=lambda p: p.confidence, reverse=True)[
            :2
        ]:
            recommendations.extend(pattern.recommendations[:1])

        # From bottlenecks
        for bottleneck in sorted(
            self.bottlenecks, key=lambda b: b.severity, reverse=True
        )[:2]:
            recommendations.extend(bottleneck.resolution[:1])

        return recommendations[:5]  # Top 5 recommendations

    def _calculate_priority(self, score: float) -> str:
        """Calculate priority from score."""
        if score >= 0.8:
            return "critical"
        elif score >= 0.6:
            return "high"
        elif score >= 0.4:
            return "medium"
        else:
            return "low"
